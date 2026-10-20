#!/usr/bin/env python3
"""
Competing Risk Analysis — CIF Plot + Cause-Specific Log-Rank Test

This skill performs cause-specific analysis + Aalen-Johansen CIF only.
For Fine-Gray subdistribution hazard, see separate skill (requires rpy2 + cmprsk).

Computes Cumulative Incidence Functions using the Aalen-Johansen estimator
(via lifelines.AalenJohansenFitter, which provides correct variance and CIs),
and compares groups with a cause-specific log-rank test.

Note: The group comparison labeled here is cause-specific log-rank
(via lifelines.multivariate_logrank_test), NOT Gray's test (which operates
on subdistribution hazards and requires cmprsk via rpy2).

Outputs: Excel (.xlsx) with CIF summary + cause-specific log-rank test, CIF plot (.png).

Usage:
    python competing_risk.py config.json                  # Full analysis
    python competing_risk.py config.json --check-missing  # Missing data report only
"""

import sys
import json
import os
import operator
import shutil
import subprocess
import tempfile
import pandas as pd
import numpy as np
# P-3 batch (2026-05-07 partitioned-flame audit): removed `import warnings;
# warnings.filterwarnings('ignore')` — global suppression hid lifelines / scipy /
# pandas convergence and data-import warnings (silent error pattern).
# 

from scipy import stats

from lifelines import AalenJohansenFitter
from lifelines.statistics import multivariate_logrank_test

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_COLORS = [
    '#E74C3C', '#3498DB', '#2ECC71', '#9B59B6', '#F39C12',
    '#1ABC9C', '#E67E22', '#34495E', '#E91E63', '#00BCD4'
]


def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    config.setdefault('filters', [])
    config.setdefault('derived_variables', [])
    config.setdefault('title', 'Competing Risk Analysis')
    config.setdefault('subtitle', '')
    config.setdefault('abbreviations', '')
    config.setdefault('missing_data_handling', 'listwise')
    config.setdefault('time_scale', None)
    config.setdefault('primary_event', 1)
    config.setdefault('fine_gray', None)

    ps = config.setdefault('plot_settings', {})
    ps.setdefault('confidence_interval', True)
    ps.setdefault('colors', None)
    ps.setdefault('x_max', None)
    ps.setdefault('x_tick_interval', None)
    ps.setdefault('y_max', None)
    ps.setdefault('figsize', [8, 6])
    ps.setdefault('dpi', 300)
    ps.setdefault('legend_position', 'upper left')
    ps.setdefault('plot_mode', 'primary_by_group')

    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Data Loading & Preprocessing
# ═══════════════════════════════════════════════════════════════════════════════

# P-2 batch (2026-05-07 partitioned-flame audit): split equality vs numeric ops.
# Equality (==, !=) must compare on original dtype, otherwise string filters like
# `sex == "F"` silently coerce to NaN and drop every row.
EQ_OPS = {'==': operator.eq, '!=': operator.ne}
NUMERIC_OPS = {'>': operator.gt, '>=': operator.ge, '<': operator.lt, '<=': operator.le}
OPS = {**EQ_OPS, **NUMERIC_OPS}


def load_data(config):
    path = config['data_file']
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.xlsx', '.xls'):
        df = pd.read_excel(path)
    elif ext == '.csv':
        df = pd.read_csv(path)
    elif ext == '.tsv':
        df = pd.read_csv(path, sep='\t')
    elif ext == '.sas7bdat':
        df = pd.read_sas(path)
    elif ext == '.dta':
        df = pd.read_stata(path)
    else:
        df = pd.read_csv(path)

    # Apply filters
    for f in config['filters']:
        col, op, val = f['column'], f['operator'], f['value']
        if op in EQ_OPS:
            # P-2 batch: equality on original dtype so string filters work
            df = df[EQ_OPS[op](df[col], val)]
        elif op in NUMERIC_OPS:
            coerced = pd.to_numeric(df[col], errors='coerce')
            n_lost = int(coerced.isna().sum() - df[col].isna().sum())
            if n_lost > 0:
                print(f"[WARNING] Filter '{col} {op} {val}': {n_lost} non-numeric "
                      f"value(s) in column '{col}' coerced to NaN and excluded.",
                      file=sys.stderr)
            df = df[NUMERIC_OPS[op](coerced, val)]
        elif op == 'in':
            df = df[df[col].isin(val)]
        elif op == 'not_in':
            df = df[~df[col].isin(val)]

    # Compute derived variables
    for dv in config['derived_variables']:
        if dv['type'] == 'coalesce':
            result = pd.to_numeric(df[dv['columns'][0]], errors='coerce')
            for c in dv['columns'][1:]:
                result = result.combine_first(pd.to_numeric(df[c], errors='coerce'))
            df[dv['name']] = result
        elif dv['type'] == 'expression':
            local_ns = {}
            for dep in dv.get('dependencies', []):
                local_ns[dep] = pd.to_numeric(df[dep], errors='coerce')
            local_ns['np'] = np
            df[dv['name']] = eval(dv['expression'], {"__builtins__": {}}, local_ns)

    return df


def prepare_data(df, config):
    """Convert columns to numeric, apply time scale, handle missing.

    P-6 audit fix (2026-05-08, cr-code-01): event column multi-level validation.
    Competing-risk uses 0=censor / 1=primary / 2+=competing convention; user
    configs may swap codes (`1=primary, 2=censor, 3=competing` is also common).
    Validates that non-NA event values are integers from declared event_labels +
    censor_code; prints event-count table for visibility.
    """
    df_work = df.copy()
    time_col = config['time_column']
    event_col = config['event_column']

    # P-6 fix: track non-numeric event values lost to coercion
    n_orig_event = int(df_work[event_col].notna().sum())
    df_work[time_col] = pd.to_numeric(df_work[time_col], errors='coerce')
    df_work[event_col] = pd.to_numeric(df_work[event_col], errors='coerce')

    n_lost = n_orig_event - int(df_work[event_col].notna().sum())
    if n_lost > 0:
        unique_orig = sorted([str(v) for v in df[event_col].dropna().unique()])[:5]
        print(f"[WARNING] Event column '{event_col}': {n_lost} non-numeric value(s) "
              f"coerced to NaN. Unique original values: {unique_orig}. Recode "
              f"the column to integers (0=censor, 1+=event types) before running.",
              file=sys.stderr)

    # P-6 fix: validate event values vs declared event_labels + censor code
    event_labels = config.get('event_labels', {})
    censor_code = config.get('censor_code', 0)
    declared_codes = {censor_code} | {int(k) for k in event_labels.keys() if str(k).lstrip('-').isdigit()}
    if not declared_codes:
        # event_labels not declared — fall back to soft check with default {0, 1, 2}
        declared_codes = {0, 1, 2}
        print(f"[WARNING] config has no 'event_labels'; using soft default "
              f"{{0=censor, 1=primary, 2=competing}}. Declare event_labels for "
              f"explicit validation.", file=sys.stderr)

    non_na_unique = sorted(int(v) for v in df_work[event_col].dropna().unique() if float(v).is_integer())
    extra = [v for v in non_na_unique if v not in declared_codes]
    if extra:
        sys.exit(
            f"[FATAL] Event column '{event_col}' has values {extra} not declared "
            f"in config. Declared codes: censor_code={censor_code}, "
            f"event_labels keys={list(event_labels.keys())}. "
            f"Update config event_labels or recode the column."
        )

    # P-6 fix: print event-count table for visibility
    counts = df_work[event_col].dropna().astype(int).value_counts().sort_index()
    print(f"[INFO] Event column '{event_col}' value counts:", file=sys.stderr)
    for code, cnt in counts.items():
        label = event_labels.get(str(int(code)), '<censor>' if code == censor_code else f'Event {code}')
        print(f"  {code}: n={cnt:5d}  ({label})", file=sys.stderr)

    if config['time_scale'] is not None:
        df_work[time_col] = df_work[time_col] / config['time_scale']

    if config['missing_data_handling'] == 'listwise':
        before_n = len(df_work)
        df_work = df_work.dropna(subset=[time_col, event_col])
        after_n = len(df_work)
        if before_n != after_n:
            print(f"  Listwise deletion: {before_n} → {after_n} rows ({before_n - after_n} removed)")

    df_work = df_work[df_work[time_col] > 0]
    return df_work


def split_groups(df, config):
    """Split dataframe into groups.

    P-1 batch (2026-05-07): dtype-aware comparison + abort on empty group.
    Previously force-coerced to numeric, which silently wiped string-coded groups
    (e.g. "control"/"treatment", "M"/"F") to NaN and continued with empty groups.
    """
    gc = config['grouping']
    col = gc['column']
    g_vals = [g['value'] for g in gc['groups']]

    if all(isinstance(v, (int, float)) for v in g_vals):
        col_vals = pd.to_numeric(df[col], errors='coerce')
    else:
        col_vals = df[col]

    groups = []
    for g in gc['groups']:
        sub = df[col_vals == g['value']]
        if len(sub) == 0:
            sys.exit(
                f"[FATAL] split_groups: group '{g['label']}' (value={g['value']!r}) "
                f"produced empty subset. Check column '{col}' values vs configured "
                f"group value."
            )
        groups.append(sub)
    return groups


# ═══════════════════════════════════════════════════════════════════════════════
# Missing Data Check
# ═══════════════════════════════════════════════════════════════════════════════

def check_missing(df, group_dfs, config):
    """Print missing data report."""
    group_labels = [g['label'] for g in config['grouping']['groups']]
    time_col = config['time_column']
    event_col = config['event_column']

    lines = []
    lines.append("=" * 100)
    lines.append("MISSING DATA REPORT — Competing Risk Analysis")
    lines.append("=" * 100)

    header_parts = [f"{'Variable':<35}", f"{'Overall':>20}"]
    for label in group_labels:
        header_parts.append(f"{label:>20}")
    lines.append("  ".join(header_parts))
    lines.append("-" * 100)

    has_missing = False

    for col, col_label in [(time_col, 'Time'), (event_col, 'Event')]:
        display_label = f"{col_label} ({col})"
        row_parts = [f"  {display_label:<33}"]
        all_pops = [("Overall", df)] + list(zip(group_labels, group_dfs))
        for pop_name, pop_df in all_pops:
            if col in pop_df.columns:
                n_miss = pd.to_numeric(pop_df[col], errors='coerce').isna().sum()
                n_total = len(pop_df)
                pct = n_miss / n_total * 100 if n_total > 0 else 0
                marker = " ⚠" if n_miss > 0 else ""
                row_parts.append(f"{n_miss}/{n_total} ({pct:.1f}%){marker:>3}")
                if n_miss > 0:
                    has_missing = True
            else:
                row_parts.append(f"{'Column not found':>20}")
                has_missing = True
        lines.append("  ".join(row_parts))

    lines.append("-" * 100)

    # Event type breakdown
    lines.append("\n  Event type breakdown (Overall):")
    event_counts = pd.to_numeric(df[event_col], errors='coerce').value_counts().sort_index()
    event_labels = config.get('event_labels', {})
    for val, count in event_counts.items():
        label = event_labels.get(str(int(val)), f"Event {int(val)}")
        if val == 0:
            label = "Censored"
        lines.append(f"    {int(val)} ({label}): {count}")

    lines.append("=" * 100)

    if not has_missing:
        lines.append("\n✓ No missing values detected.")
    else:
        lines.append("\n⚠ Missing values detected. Default handling: listwise deletion.")

    print("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════════════
# Aalen-Johansen Estimator (CIF) — via lifelines
# ═══════════════════════════════════════════════════════════════════════════════

def compute_cif(times, events, event_of_interest):
    """
    Compute Cumulative Incidence Function using lifelines.AalenJohansenFitter,
    which natively supports competing risks and provides correct variance/CIs.

    Parameters:
        times: array of follow-up times
        events: array of event codes (0=censor, 1,2,...=events)
        event_of_interest: which event code to compute CIF for

    Returns:
        cif_times: sorted unique event times (with 0 prepended)
        cif_values: CIF values at each time
        cif_ci_lo: lower bound of 95% CI at each time
        cif_ci_hi: upper bound of 95% CI at each time
    """
    times = np.asarray(times, dtype=float)
    events = np.asarray(events, dtype=float)

    n = len(times)
    if n == 0 or np.sum(events == event_of_interest) == 0:
        return (np.array([0.0]), np.array([0.0]),
                np.array([0.0]), np.array([0.0]))

    ajf = AalenJohansenFitter(calculate_variance=True)
    ajf.fit(durations=times, event_observed=events.astype(int),
            event_of_interest=int(event_of_interest))

    cif_df = ajf.cumulative_density_
    cif_times_out = cif_df.index.values.astype(float)
    cif_col = cif_df.columns[0]
    cif_values = cif_df[cif_col].values.astype(float)

    ci_df = ajf.confidence_interval_
    # lifelines AalenJohansenFitter has a known bug where the "_upper_0.95" /
    # "_lower_0.95" column labels are swapped relative to the numeric values.
    # Derive bounds by numeric min/max per row so the output is always lo<hi.
    col_a = ci_df.iloc[:, 0].values.astype(float)
    col_b = ci_df.iloc[:, 1].values.astype(float)
    ci_lo = np.minimum(col_a, col_b)
    ci_hi = np.maximum(col_a, col_b)

    ci_lo = np.clip(np.nan_to_num(ci_lo, nan=0.0), 0.0, 1.0)
    ci_hi = np.clip(np.nan_to_num(ci_hi, nan=0.0), 0.0, 1.0)

    # Ensure time 0 is present
    if len(cif_times_out) == 0 or cif_times_out[0] > 0:
        cif_times_out = np.concatenate([[0.0], cif_times_out])
        cif_values = np.concatenate([[0.0], cif_values])
        ci_lo = np.concatenate([[0.0], ci_lo])
        ci_hi = np.concatenate([[0.0], ci_hi])

    return cif_times_out, cif_values, ci_lo, ci_hi


def cif_at_time(cif_times, cif_values, cif_ci_lo, cif_ci_hi, t):
    """Get CIF value and 95% CI at a specific time point (step function, carry-forward)."""
    if len(cif_times) == 0 or t > cif_times[-1]:
        return None, None, None

    idx = np.searchsorted(cif_times, t, side='right') - 1
    idx = max(0, idx)

    return float(cif_values[idx]), float(cif_ci_lo[idx]), float(cif_ci_hi[idx])


# ═══════════════════════════════════════════════════════════════════════════════
# Cause-Specific Log-Rank Test
# ═══════════════════════════════════════════════════════════════════════════════
# Note: This is cause-specific log-rank (via lifelines.multivariate_logrank_test),
# NOT Gray's test (which requires subdistribution hazard, needs cmprsk via rpy2).

def cause_specific_logrank_test(group_times, group_events, event_of_interest):
    """
    Cause-specific log-rank test comparing cause-specific hazards between groups.
    Observations failing from competing events are treated as censored.

    Parameters:
        group_times: list of arrays, one per group
        group_events: list of arrays, one per group
        event_of_interest: event code to test

    Returns:
        test_statistic, p_value, df
    """
    n_groups = len(group_times)
    if n_groups < 2:
        return np.nan, np.nan, 0

    all_times = np.concatenate(group_times).astype(float)
    all_events = np.concatenate(group_events).astype(float)
    group_ids = np.concatenate([np.full(len(t), i) for i, t in enumerate(group_times)])

    # Treat competing events as censored (cause-specific framework)
    event_observed = (all_events == event_of_interest).astype(int)

    if event_observed.sum() == 0:
        return np.nan, np.nan, n_groups - 1

    try:
        result = multivariate_logrank_test(all_times, group_ids, event_observed)
        test_stat = float(result.test_statistic)
        p_value = float(result.p_value)
        df = n_groups - 1
    except Exception as e:
        # P-5 batch: surface the failure (was silent N/A fallback). Tests that
        # legitimately can't be computed (e.g. one-group log-rank) check earlier;
        # this catch is for unexpected lifelines / numerical errors.
        print(f"[WARNING] cause-specific log-rank test failed: "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return np.nan, np.nan, n_groups - 1

    return test_stat, p_value, df


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def _find_rscript():
    """Locate Rscript, checking PATH then common macOS/Linux install dirs."""
    found = shutil.which("Rscript")
    if found:
        return found
    for cand in (
        "/opt/homebrew/bin/Rscript",
        "/usr/local/bin/Rscript",
        "/Library/Frameworks/R.framework/Resources/bin/Rscript",
        "/usr/bin/Rscript",
    ):
        if os.path.exists(cand):
            return cand
    return None


def grays_test(group_dfs, time_col, event_col, group_labels):
    """Gray's test for equality of CIFs across groups (subdistribution hazard).

    Gray's test is the standard test when the question is whether the *cumulative
    incidence functions* differ between groups — unlike the cause-specific
    log-rank, which compares cause-specific hazards. The two can disagree.

    Implemented by shelling out to R `cmprsk::cuminc` (the reference
    implementation; `lifelines` has no Gray's test). Degrades gracefully:
    returns ``None`` when R or the cmprsk package is unavailable, so pure-Python
    installs keep working with the cause-specific log-rank only.

    Returns {event_code: (stat, pval, df)} or None.
    """
    rscript = _find_rscript()
    if rscript is None:
        print("[INFO] Gray's test skipped: Rscript not found on this system "
              "(install R + cmprsk to enable subdistribution-hazard testing).",
              file=sys.stderr)
        return None

    # Build a single long frame: time, status (0=censor, 1..k=causes), group.
    frames = []
    for gdf, label in zip(group_dfs, group_labels):
        frames.append(pd.DataFrame({
            "time": gdf[time_col].values,
            "status": gdf[event_col].values,
            "grp": label,
        }))
    long_df = pd.concat(frames, ignore_index=True).dropna(subset=["time", "status"])

    tmpdir = tempfile.mkdtemp(prefix="grays_")
    csv_path = os.path.join(tmpdir, "data.csv")
    out_path = os.path.join(tmpdir, "result.csv")
    long_df.to_csv(csv_path, index=False)

    r_code = (
        'args <- commandArgs(trailingOnly=TRUE);'
        'if (!requireNamespace("cmprsk", quietly=TRUE)) quit(status=2);'
        'd <- read.csv(args[1]);'
        'ci <- cmprsk::cuminc(ftime=d$time, fstatus=d$status, group=d$grp);'
        'tt <- ci$Tests;'
        'out <- data.frame(cause=rownames(tt), stat=tt[,"stat"], pv=tt[,"pv"], df=tt[,"df"]);'
        'write.csv(out, args[2], row.names=FALSE)'
    )
    try:
        proc = subprocess.run(
            [rscript, "-e", r_code, csv_path, out_path],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode == 2:
            print("[INFO] Gray's test skipped: R found but 'cmprsk' package not "
                  "installed (run: install.packages('cmprsk')).", file=sys.stderr)
            return None
        if proc.returncode != 0 or not os.path.exists(out_path):
            print(f"[WARNING] Gray's test failed (R rc={proc.returncode}): "
                  f"{proc.stderr.strip()[:300]}", file=sys.stderr)
            return None
        res = pd.read_csv(out_path)
        # cuminc()$Tests rownames are the cause codes (one row per cause). pandas may
        # read them as "1.0"; coerce robustly to the integer event code.
        out = {}
        for _, row in res.iterrows():
            cause_label = str(row["cause"]).strip()
            code = None
            try:
                code = int(float(cause_label))
            except ValueError:
                for tok in cause_label.replace("-", " ").split():
                    base = tok.split(".")[0]
                    if base.isdigit():
                        code = int(base)
            if code is None:
                continue
            out[code] = (float(row["stat"]), float(row["pv"]), int(row["df"]))
        return out or None
    except subprocess.TimeoutExpired:
        print("[WARNING] Gray's test timed out.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[WARNING] Gray's test error: {e}", file=sys.stderr)
        return None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def run_analysis(group_dfs, config):
    """Run CIF estimation and cause-specific log-rank test for each event type."""
    time_col = config['time_column']
    event_col = config['event_column']
    group_labels = [g['label'] for g in config['grouping']['groups']]
    event_labels = config.get('event_labels', {})
    primary_event = config['primary_event']
    time_points = config['time_points']

    # Get all event types
    all_events_combined = pd.concat([gdf[event_col] for gdf in group_dfs])
    event_types = sorted([int(x) for x in all_events_combined.unique() if x > 0])

    results = {
        'group_summaries': [],
        'cif_data': {},  # {group_label: {event_code: (times, values, ci_lo, ci_hi)}}
        'cs_logrank_tests': {},  # {event_code: (stat, pval, df)} — cause-specific log-rank
        'grays_tests': {},        # {event_code: (stat, pval, df)} — Gray's test (if R available)
        'cif_at_timepoints': {},  # {group_label: {event_code: {tp: (val, lo, hi)}}}
    }

    # Per-group summaries
    for gdf, label in zip(group_dfs, group_labels):
        T = gdf[time_col].values
        E = gdf[event_col].values
        n_total = len(T)
        event_counts = {}
        for et in event_types:
            et_label = event_labels.get(str(et), f"Event {et}")
            event_counts[et] = {'n': int(np.sum(E == et)), 'label': et_label}
        n_censored = int(np.sum(E == 0))

        results['group_summaries'].append({
            'label': label,
            'n': n_total,
            'n_censored': n_censored,
            'event_counts': event_counts
        })

    # CIF estimation per group per event type
    for gdf, label in zip(group_dfs, group_labels):
        T = gdf[time_col].values
        E = gdf[event_col].values
        results['cif_data'][label] = {}
        results['cif_at_timepoints'][label] = {}

        for et in event_types:
            cif_t, cif_v, cif_lo, cif_hi = compute_cif(T, E, et)
            results['cif_data'][label][et] = (cif_t, cif_v, cif_lo, cif_hi)

            # CIF at time points
            results['cif_at_timepoints'][label][et] = {}
            for tp in time_points:
                val, lo, hi = cif_at_time(cif_t, cif_v, cif_lo, cif_hi, tp)
                results['cif_at_timepoints'][label][et][tp] = (val, lo, hi)

    # Cause-specific log-rank test per event type
    for et in event_types:
        g_times = [gdf[time_col].values for gdf in group_dfs]
        g_events = [gdf[event_col].values for gdf in group_dfs]
        stat, pval, df = cause_specific_logrank_test(g_times, g_events, et)
        results['cs_logrank_tests'][et] = (stat, pval, df)

    # Gray's test (subdistribution) per event type — only when ≥2 groups and R
    # with cmprsk is available; otherwise quietly left empty.
    if len(group_dfs) >= 2:
        gt = grays_test(group_dfs, time_col, event_col, group_labels)
        if gt:
            results['grays_tests'] = gt

    results['event_types'] = event_types
    return results


def format_pvalue(p):
    """Format p-value for display."""
    if isinstance(p, str) or np.isnan(p):
        return 'N/A'
    if p < 0.001:
        return '<0.001'
    return f"{p:.3f}"


# ═══════════════════════════════════════════════════════════════════════════════
# Plot Generation
# ═══════════════════════════════════════════════════════════════════════════════

def generate_cif_plot(results, config):
    """Generate publication-ready CIF plot."""
    ps = config['plot_settings']
    time_unit = config['time_unit']
    group_labels = [g['label'] for g in config['grouping']['groups']]
    event_labels = config.get('event_labels', {})
    primary_event = config['primary_event']
    plot_mode = ps['plot_mode']

    colors = ps['colors'] if ps['colors'] else DEFAULT_COLORS[:len(group_labels)]
    while len(colors) < len(group_labels):
        colors.append(DEFAULT_COLORS[len(colors) % len(DEFAULT_COLORS)])

    figsize = ps['figsize']
    fig, ax = plt.subplots(figsize=figsize)

    line_styles = ['-', '--', '-.', ':']

    if plot_mode == 'primary_by_group':
        # Plot CIF of primary event for each group
        for i, label in enumerate(group_labels):
            cif_data = results['cif_data'][label].get(primary_event)
            if cif_data is None:
                continue
            cif_t, cif_v, cif_lo, cif_hi = cif_data

            ax.step(cif_t, cif_v, where='post', color=colors[i],
                    linewidth=1.8, label=label, linestyle='-')

            if ps['confidence_interval']:
                ax.fill_between(cif_t, cif_lo, cif_hi, step='post',
                                alpha=0.15, color=colors[i])

        # Add cause-specific log-rank test p-value
        stat, pval, df = results['cs_logrank_tests'].get(primary_event, (np.nan, np.nan, 0))
        p_text = f"Cause-specific log-rank p = {format_pvalue(pval)}"
        ax.text(0.98, 0.98, p_text, transform=ax.transAxes,
                fontsize=10, ha='right', va='top',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                          edgecolor='gray', alpha=0.8))

        primary_label = event_labels.get(str(primary_event), f"Event {primary_event}")
        ylabel = f'Cumulative Incidence ({primary_label})'

    elif plot_mode == 'all_events':
        # Plot CIF of all event types, grouped by group
        color_idx = 0
        for i, label in enumerate(group_labels):
            for j, et in enumerate(results['event_types']):
                cif_data = results['cif_data'][label].get(et)
                if cif_data is None:
                    continue
                cif_t, cif_v, cif_lo, cif_hi = cif_data

                et_label = event_labels.get(str(et), f"Event {et}")
                line_label = f"{label} — {et_label}"
                ls = line_styles[j % len(line_styles)]

                ax.step(cif_t, cif_v, where='post', color=colors[i],
                        linewidth=1.8, label=line_label, linestyle=ls)

                if ps['confidence_interval']:
                    ax.fill_between(cif_t, cif_lo, cif_hi, step='post',
                                    alpha=0.10, color=colors[i])

        ylabel = 'Cumulative Incidence'

    # Axis formatting
    max_time = max(cif_t[-1] for label in group_labels
                   for et, (cif_t, _, _, _) in results['cif_data'][label].items()
                   if len(cif_t) > 0)

    x_max = ps['x_max'] if ps['x_max'] is not None else max_time
    x_tick_interval = ps['x_tick_interval']
    if x_tick_interval is None:
        if x_max <= 5:
            x_tick_interval = 1
        elif x_max <= 12:
            x_tick_interval = 2
        elif x_max <= 30:
            x_tick_interval = 5
        else:
            x_tick_interval = max(1, int(x_max / 10))

    x_ticks = np.arange(0, x_max + x_tick_interval * 0.01, x_tick_interval)

    ax.set_xlim(0, x_max)
    y_max = ps['y_max']
    if y_max is not None:
        ax.set_ylim(0, y_max)
    else:
        # Auto y_max based on data
        all_max_cif = 0
        for label in group_labels:
            for et in results['event_types']:
                cif_data = results['cif_data'][label].get(et)
                if cif_data:
                    all_max_cif = max(all_max_cif, cif_data[1].max() if len(cif_data[1]) else 0)
        ax.set_ylim(0, min(1.0, all_max_cif * 1.3 + 0.05))

    ax.set_xlabel(f'Time ({time_unit})', fontsize=12, fontweight='bold')
    ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
    ax.set_xticks(x_ticks)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1.0, decimals=0))
    ax.tick_params(axis='both', labelsize=10)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    ax.legend(loc=ps['legend_position'], fontsize=9, framealpha=0.9)

    if config['title']:
        ax.set_title(config['title'], fontsize=14, fontweight='bold', pad=15)

    plt.tight_layout()

    output_base = os.path.splitext(config['output_file'])[0]
    png_path = output_base + '.png'
    fig.savefig(png_path, dpi=ps['dpi'], bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  CIF plot saved: {png_path}")
    return png_path


# ═══════════════════════════════════════════════════════════════════════════════
# Excel Output
# ═══════════════════════════════════════════════════════════════════════════════

DARK_BLUE = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
MEDIUM_BLUE = PatternFill(start_color='2E75B6', end_color='2E75B6', fill_type='solid')
LIGHT_BLUE = PatternFill(start_color='D6E4F0', end_color='D6E4F0', fill_type='solid')
LIGHT_GRAY = PatternFill(start_color='F2F2F2', end_color='F2F2F2', fill_type='solid')
WHITE_FILL = PatternFill(start_color='FFFFFF', end_color='FFFFFF', fill_type='solid')
WHITE_FONT = Font(color='FFFFFF', bold=True, size=12)
HEADER_FONT = Font(color='FFFFFF', bold=True, size=10)
DATA_FONT = Font(size=10)
BOLD_FONT = Font(size=10, bold=True)
THIN_BORDER = Border(
    left=Side(style='thin', color='D9D9D9'),
    right=Side(style='thin', color='D9D9D9'),
    top=Side(style='thin', color='D9D9D9'),
    bottom=Side(style='thin', color='D9D9D9')
)
CENTER_ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT_ALIGN = Alignment(horizontal='left', vertical='center', wrap_text=True)


def write_excel(results, config):
    """Write formatted Excel output."""
    wb = Workbook()
    time_unit = config['time_unit']
    time_points = config['time_points']
    event_labels = config.get('event_labels', {})
    primary_event = config['primary_event']
    group_labels = [g['label'] for g in config['grouping']['groups']]

    # ── Sheet 1: CIF Summary ──
    ws1 = wb.active
    ws1.title = "CIF Summary"

    total_n = sum(s['n'] for s in results['group_summaries'])
    event_types = results['event_types']

    # Columns: Group | N | Event counts per type | CIF at each time point (for primary event)
    n_event_cols = len(event_types)
    n_tp_cols = len(time_points)
    n_cols = 2 + n_event_cols + n_tp_cols

    # Row 1: Title
    ws1.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    cell = ws1.cell(row=1, column=1, value=config['title'] or 'Competing Risk Analysis')
    cell.font = WHITE_FONT
    cell.fill = DARK_BLUE
    cell.alignment = CENTER_ALIGN
    ws1.row_dimensions[1].height = 30

    # Row 2: Subtitle
    subtitle = config['subtitle'] or ''
    subtitle_full = f"{subtitle} (N = {total_n})" if subtitle else f"N = {total_n}"
    ws1.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n_cols)
    cell = ws1.cell(row=2, column=1, value=subtitle_full)
    cell.font = Font(size=10, italic=True)
    cell.fill = LIGHT_BLUE
    cell.alignment = CENTER_ALIGN
    ws1.row_dimensions[2].height = 22

    # Row 3: Headers
    headers = ['Group', 'N']
    for et in event_types:
        et_label = event_labels.get(str(et), f"Event {et}")
        headers.append(f'{et_label}\nn (%)')
    primary_label = event_labels.get(str(primary_event), f"Event {primary_event}")
    for tp in time_points:
        headers.append(f'{tp}-{time_unit[0].upper()} CIF %\n(95% CI)')

    for j, header in enumerate(headers, 1):
        cell = ws1.cell(row=3, column=j, value=header)
        cell.font = HEADER_FONT
        cell.fill = MEDIUM_BLUE
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
    ws1.row_dimensions[3].height = 35

    # Data rows
    for idx, summary in enumerate(results['group_summaries']):
        row = 4 + idx
        fill = LIGHT_GRAY if idx % 2 == 0 else WHITE_FILL
        label = summary['label']

        cell = ws1.cell(row=row, column=1, value=label)
        cell.font = BOLD_FONT
        cell.fill = fill
        cell.alignment = LEFT_ALIGN
        cell.border = THIN_BORDER

        cell = ws1.cell(row=row, column=2, value=summary['n'])
        cell.font = DATA_FONT
        cell.fill = fill
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

        for j, et in enumerate(event_types):
            ec = summary['event_counts'].get(et, {'n': 0})
            pct = ec['n'] / summary['n'] * 100 if summary['n'] > 0 else 0
            text = f"{ec['n']} ({pct:.1f}%)"
            cell = ws1.cell(row=row, column=3 + j, value=text)
            cell.font = DATA_FONT
            cell.fill = fill
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER

        for j, tp in enumerate(time_points):
            cif_data = results['cif_at_timepoints'][label].get(primary_event, {})
            tp_data = cif_data.get(tp, (None, None, None))
            if tp_data[0] is None:
                text = 'N/A'
            else:
                val, lo, hi = tp_data
                text = f"{val*100:.1f}% ({lo*100:.1f}–{hi*100:.1f})"
            cell = ws1.cell(row=row, column=3 + n_event_cols + j, value=text)
            cell.font = DATA_FONT
            cell.fill = fill
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER

    # Footnotes
    footnote_row = 4 + len(results['group_summaries']) + 1
    for et in event_types:
        et_label = event_labels.get(str(et), f"Event {et}")
        stat, pval, df = results['cs_logrank_tests'].get(et, (np.nan, np.nan, 0))
        footnote = f"Cause-specific log-rank test for {et_label}: χ² = {stat:.4f}, p = {format_pvalue(pval)}" if not np.isnan(stat) else f"Cause-specific log-rank test for {et_label}: N/A"
        ws1.merge_cells(start_row=footnote_row, start_column=1, end_row=footnote_row, end_column=n_cols)
        cell = ws1.cell(row=footnote_row, column=1, value=footnote)
        cell.font = Font(size=9, italic=True)
        cell.alignment = LEFT_ALIGN
        footnote_row += 1

        # Gray's test (subdistribution) — shown alongside when R/cmprsk available.
        g_stat, g_pval, _ = results.get('grays_tests', {}).get(et, (np.nan, np.nan, 0))
        if not np.isnan(g_stat):
            g_footnote = (f"Gray's test (subdistribution) for {et_label}: "
                          f"χ² = {g_stat:.4f}, p = {format_pvalue(g_pval)} "
                          f"— compares CIFs directly (vs cause-specific hazards above)")
            ws1.merge_cells(start_row=footnote_row, start_column=1, end_row=footnote_row, end_column=n_cols)
            cell = ws1.cell(row=footnote_row, column=1, value=g_footnote)
            cell.font = Font(size=9, italic=True)
            cell.alignment = LEFT_ALIGN
            footnote_row += 1

    if config['abbreviations']:
        ws1.merge_cells(start_row=footnote_row, start_column=1, end_row=footnote_row, end_column=n_cols)
        cell = ws1.cell(row=footnote_row, column=1, value=config['abbreviations'])
        cell.font = Font(size=9, italic=True)
        cell.alignment = LEFT_ALIGN
        footnote_row += 1

    method_note = "CIF estimated using Aalen-Johansen method. Unlike 1−KM, CIF properly accounts for competing events."
    ws1.merge_cells(start_row=footnote_row, start_column=1, end_row=footnote_row, end_column=n_cols)
    cell = ws1.cell(row=footnote_row, column=1, value=method_note)
    cell.font = Font(size=9, italic=True)
    cell.alignment = LEFT_ALIGN

    # Column widths
    ws1.column_dimensions['A'].width = 20
    ws1.column_dimensions['B'].width = 10
    for j in range(n_event_cols):
        ws1.column_dimensions[get_column_letter(3 + j)].width = 16
    for j in range(n_tp_cols):
        ws1.column_dimensions[get_column_letter(3 + n_event_cols + j)].width = 22

    # ── Sheet 2: Cause-specific log-rank test ──
    ws2 = wb.create_sheet("Cause-Specific Log-Rank")

    ws2.merge_cells('A1:D1')
    cell = ws2.cell(row=1, column=1, value="Cause-Specific Log-Rank Test Results")
    cell.font = WHITE_FONT
    cell.fill = DARK_BLUE
    cell.alignment = CENTER_ALIGN
    ws2.row_dimensions[1].height = 30

    for j, header in enumerate(['Event Type', 'Test Statistic (χ²)', 'df', 'p-value'], 1):
        cell = ws2.cell(row=2, column=j, value=header)
        cell.font = HEADER_FONT
        cell.fill = MEDIUM_BLUE
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    for idx, et in enumerate(event_types):
        row = 3 + idx
        fill = LIGHT_GRAY if idx % 2 == 0 else WHITE_FILL
        et_label = event_labels.get(str(et), f"Event {et}")
        stat, pval, df = results['cs_logrank_tests'].get(et, (np.nan, np.nan, 0))

        cell = ws2.cell(row=row, column=1, value=et_label)
        cell.font = BOLD_FONT
        cell.fill = fill
        cell.alignment = LEFT_ALIGN
        cell.border = THIN_BORDER

        cell = ws2.cell(row=row, column=2, value=f"{stat:.4f}" if not np.isnan(stat) else 'N/A')
        cell.font = DATA_FONT
        cell.fill = fill
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

        cell = ws2.cell(row=row, column=3, value=str(df))
        cell.font = DATA_FONT
        cell.fill = fill
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

        cell = ws2.cell(row=row, column=4, value=format_pvalue(pval))
        cell.font = BOLD_FONT
        cell.fill = fill
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    footnote_row = 3 + len(event_types) + 1
    ws2.merge_cells(start_row=footnote_row, start_column=1, end_row=footnote_row, end_column=4)
    cell = ws2.cell(row=footnote_row, column=1,
                    value=("Cause-specific log-rank test (via lifelines.multivariate_logrank_test): "
                           "compares cause-specific hazards between groups, treating competing events as censored. "
                           "NOT Gray's test (which operates on subdistribution hazards; requires cmprsk via rpy2)."))
    cell.font = Font(size=9, italic=True)
    cell.alignment = LEFT_ALIGN

    ws2.column_dimensions['A'].width = 25
    ws2.column_dimensions['B'].width = 20
    ws2.column_dimensions['C'].width = 10
    ws2.column_dimensions['D'].width = 15

    # Save
    output_path = config['output_file']
    wb.save(output_path)
    print(f"  Excel saved: {output_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_academic_style():
    """academic-style integration (Wave 1). Consumes --style=<journal> from
    sys.argv. No-op when skill not installed or flag absent."""
    from pathlib import Path as _P
    _as = _P.home() / ".claude" / "skills" / "academic-style"
    if not _as.exists():
        return None
    if str(_as) not in sys.path:
        sys.path.insert(0, str(_as))
    try:
        from core.biostats_integration import apply_style_from_argv
    except ImportError:
        return None
    return apply_style_from_argv(sys.argv)


def main():
    _AS_STYLE = _apply_academic_style()
    if _AS_STYLE:
        print(f"  Applied {_AS_STYLE} journal style")

    if len(sys.argv) < 2:
        print("Usage: python competing_risk.py config.json [--check-missing] [--style=<journal>]")
        sys.exit(1)

    config_path = sys.argv[1]
    check_missing_mode = '--check-missing' in sys.argv

    config = load_config(config_path)

    # P-7 audit fix (2026-05-07): Fine-Gray is R-only via cmprsk::crr; this Python
    # skill is cause-specific only. Previously emitted [QC_WARNING] and continued
    # silently producing CIF-only output despite user requesting Fine-Gray — that
    # silent downgrade was MORE dangerous than not supporting it at all.
    # Now: abort with [FATAL] so user knows to use R cmprsk or ma-meta-analysis.
    if config.get('fine_gray'):
        sys.exit(
            "[FATAL] fine_gray=true requested but not implemented in this Python "
            "skill (cause-specific only). For Fine-Gray subdistribution hazard "
            "regression, use R `cmprsk::crr` or the ma-meta-analysis pipeline. "
            "See SKILL.md scope note for details."
        )

    print("Loading data...")
    df = load_data(config)
    print(f"  Data loaded: {len(df)} rows")

    # Split into groups (raw)
    raw_groups = split_groups(df, config)
    group_labels = [g['label'] for g in config['grouping']['groups']]

    if check_missing_mode:
        check_missing(df, raw_groups, config)
        sys.exit(0)

    # Prepare data
    df = prepare_data(df, config)
    print(f"  After preparation: {len(df)} rows")

    # Split prepared data into groups
    group_dfs = split_groups(df, config)
    for gdf, label in zip(group_dfs, group_labels):
        print(f"  {label}: n = {len(gdf)}")

    # Run analysis
    print("\nComputing Cumulative Incidence Functions...")
    results = run_analysis(group_dfs, config)

    # Print cause-specific log-rank test results
    event_labels = config.get('event_labels', {})
    for et in results['event_types']:
        et_label = event_labels.get(str(et), f"Event {et}")
        stat, pval, df_val = results['cs_logrank_tests'].get(et, (np.nan, np.nan, 0))
        print(f"  Cause-specific log-rank ({et_label}): p = {format_pvalue(pval)}")

    # Generate plot
    print("\nGenerating CIF plot...")
    generate_cif_plot(results, config)

    # Write Excel
    print("Writing Excel output...")
    write_excel(results, config)

    # Print summary
    print("\n" + "=" * 60)
    print("COMPETING RISK ANALYSIS COMPLETE")
    print("=" * 60)
    for s in results['group_summaries']:
        event_strs = []
        for et, ec in s['event_counts'].items():
            event_strs.append(f"{ec['label']}={ec['n']}")
        print(f"  {s['label']}: N={s['n']}, {', '.join(event_strs)}")

    print(f"\n  Cause-specific log-rank test results:")
    for et in results['event_types']:
        et_label = event_labels.get(str(et), f"Event {et}")
        stat, pval, _ = results['cs_logrank_tests'].get(et, (np.nan, np.nan, 0))
        print(f"    {et_label}: p = {format_pvalue(pval)}")
    grays = results.get('grays_tests', {})
    if grays:
        print(f"\n  Gray's test (subdistribution) results:")
        for et in results['event_types']:
            et_label = event_labels.get(str(et), f"Event {et}")
            g_stat, g_pval, _ = grays.get(et, (np.nan, np.nan, 0))
            if not np.isnan(g_stat):
                print(f"    {et_label}: p = {format_pvalue(g_pval)}")
    print("=" * 60)

    # ── QC Warnings ──────────────────────────────────────────────────────────
    # P-4 + P-5 batch (2026-05-07): track [QC_BLOCKING] emissions and exit
    # non-zero so pipeline detects failure; surface block-level exception.
    qc_blocking_count = 0

    def _qc_block(msg):
        nonlocal qc_blocking_count
        print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
        qc_blocking_count += 1

    try:
        primary_event = config['primary_event']
        for s in results['group_summaries']:
            # Check 0 primary events in any group
            primary_count = s['event_counts'].get(primary_event, {}).get('n', 0)
            if primary_count == 0:
                _qc_block(f"Group '{s['label']}' has 0 primary events (event={primary_event})")
            if s['n'] < 30:
                print(f"[QC_WARNING] Group '{s['label']}' has n={s['n']} (< 30)", file=sys.stderr)
    except Exception as e:
        # P-5 batch: surface QC exception (was silent except: pass)
        print(f"[QC_WARNING] QC block raised: {type(e).__name__}: {e}", file=sys.stderr)

    if qc_blocking_count > 0:
        sys.exit(2)


if __name__ == '__main__':
    main()
