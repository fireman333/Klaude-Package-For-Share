#!/usr/bin/env python3
"""
Univariate Analysis + Forest Plot Generator
Performs univariate Cox (HR) or logistic (OR) regression across 3 populations
(Overall, Group X, Group Non-X) and generates formatted Excel + forest plot.

Usage:
    python univariate_forest.py config.json                  # Full analysis
    python univariate_forest.py config.json --check-missing  # Missing data report only
"""

import sys
import json
import os
import operator
import math
import pandas as pd
import numpy as np
# P-3 batch (2026-05-07 partitioned-flame audit): removed `import warnings;
# warnings.filterwarnings('ignore')` — global suppression hid lifelines / scipy /
# statsmodels convergence and perfect-separation warnings (silent error pattern).
# 

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    config.setdefault('filters', [])
    config.setdefault('derived_variables', [])
    # NOTE: do NOT seed 'title' here (same convention as table1's load_config). Seeding
    # it with '' makes every downstream `config.get('title', <fallback>)` dead code —
    # the key exists, so the fallback never fires and the Excel/forest-plot title
    # renders blank instead of the intended default.
    config.setdefault('subtitle', '')
    config.setdefault('abbreviations', '')
    config.setdefault('missing_data_handling', 'listwise')
    config.setdefault('forest_plot', {})
    fp = config['forest_plot']
    fp.setdefault('format', 'png')
    fp.setdefault('dpi', 300)
    fp.setdefault('truncation_method', 'auto')
    fp.setdefault('truncation_range', None)
    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Data Loading & Preprocessing (reused from table1)
# ═══════════════════════════════════════════════════════════════════════════════

OPS = {
    '==': operator.eq, '!=': operator.ne,
    '>': operator.gt, '>=': operator.ge,
    '<': operator.lt, '<=': operator.le,
}

def load_data(config):
    path = config['data_file']
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.xlsx', '.xls'):
        df = pd.read_excel(path)
    elif ext in ('.csv',):
        df = pd.read_csv(path)
    elif ext in ('.tsv',):
        df = pd.read_csv(path, sep='\t')
    elif ext in ('.sas7bdat',):
        df = pd.read_sas(path)
    elif ext in ('.dta',):
        df = pd.read_stata(path)
    else:
        df = pd.read_csv(path)

    # Apply filters
    for f in config['filters']:
        col, op, val = f['column'], f['operator'], f['value']
        if op in OPS:
            df = df[OPS[op](pd.to_numeric(df[col], errors='coerce'), val)]
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


def split_groups(df, config):
    """P-1 batch (2026-05-07): dtype-aware comparison + abort on empty group.

    Previously force-coerced grouping column to numeric, which silently wiped
    string-coded groups to NaN and continued with empty groups.
    """
    gc = config['grouping']
    col = gc['column']
    g1_val = gc['groups'][0]['value']
    g2_val = gc['groups'][1]['value']

    if isinstance(g1_val, (int, float)) and isinstance(g2_val, (int, float)):
        col_vals = pd.to_numeric(df[col], errors='coerce')
    else:
        col_vals = df[col]

    grp1 = df[col_vals == g1_val]
    grp2 = df[col_vals == g2_val]

    if len(grp1) == 0 or len(grp2) == 0:
        sys.exit(
            f"[FATAL] split_groups produced empty group(s): "
            f"{gc['groups'][0]['label']} n={len(grp1)}, "
            f"{gc['groups'][1]['label']} n={len(grp2)}. "
            f"Check column '{col}' values vs configured group values "
            f"({g1_val!r}, {g2_val!r})."
        )
    return grp1, grp2


# ═══════════════════════════════════════════════════════════════════════════════
# Listwise Deletion
# ═══════════════════════════════════════════════════════════════════════════════

def apply_listwise_deletion(df, config):
    """Drop rows with any missing value across all analyzed variables."""
    cols = []
    for section in config['sections']:
        for var in section['variables']:
            if var['column'] in df.columns:
                cols.append(var['column'])
    # Include outcome/time/event columns
    if config['analysis_type'] == 'cox':
        cs = config['cox_settings']
        for c in [cs['time_column'], cs['event_column']]:
            if c in df.columns and c not in cols:
                cols.append(c)
    else:
        c = config['logistic_settings']['outcome_column']
        if c in df.columns and c not in cols:
            cols.append(c)
    # Include group column
    gc = config['grouping']['column']
    if gc in df.columns and gc not in cols:
        cols.append(gc)
    # Build set of categorical columns so we don't force them to numeric
    categorical_cols = set()
    for section in config['sections']:
        for var in section['variables']:
            if var.get('type') == 'categorical':
                categorical_cols.add(var['column'])
    for col in cols:
        if col in categorical_cols:
            # Treat blanks as NA but preserve labels
            df[col] = df[col].where(df[col].notna() & (df[col].astype(str).str.strip() != ''), np.nan)
        else:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    before = len(df)
    df = df.dropna(subset=cols)
    after = len(df)
    if before != after:
        print(f"Listwise deletion: {before} -> {after} rows ({before - after} removed)")
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# Missing Data Check
# ═══════════════════════════════════════════════════════════════════════════════

def check_missing(df, grp_x, grp_nonx, config):
    """Print a missing data report for all 3 populations."""
    grp_x_label = config['grouping']['groups'][0]['label']
    grp_nonx_label = config['grouping']['groups'][1]['label']
    analysis_type = config['analysis_type']

    # Collect relevant columns
    extra_cols = []
    if analysis_type == 'cox':
        cs = config['cox_settings']
        extra_cols = [cs['time_column'], cs['event_column']]
    else:
        extra_cols = [config['logistic_settings']['outcome_column']]

    lines = []
    lines.append("=" * 100)
    lines.append("MISSING DATA REPORT")
    lines.append("=" * 100)
    lines.append(f"{'Variable':<35} {'Overall':>20} {grp_x_label:>20} {grp_nonx_label:>20}")
    lines.append("-" * 100)

    # Check outcome/time columns first
    for col_name in extra_cols:
        row = f"  {col_name:<33}"
        for pop_name, pop_df in [("Overall", df), (grp_x_label, grp_x), (grp_nonx_label, grp_nonx)]:
            if col_name in pop_df.columns:
                n_miss = pd.to_numeric(pop_df[col_name], errors='coerce').isna().sum()
                n_total = len(pop_df)
                pct = n_miss / n_total * 100 if n_total > 0 else 0
                row += f" {n_miss:>6}/{n_total:<6} ({pct:>5.1f}%)"
            else:
                row += f" {'COLUMN NOT FOUND':>20}"
        lines.append(row)

    lines.append("-" * 100)

    any_missing = False
    for section in config['sections']:
        lines.append(f"\n{section['header']}")
        for var in section['variables']:
            col = var['column']
            label = var['label']
            row = f"  {label:<33}"
            for pop_name, pop_df in [("Overall", df), (grp_x_label, grp_x), (grp_nonx_label, grp_nonx)]:
                if col in pop_df.columns:
                    n_miss = pd.to_numeric(pop_df[col], errors='coerce').isna().sum()
                    n_total = len(pop_df)
                    pct = n_miss / n_total * 100 if n_total > 0 else 0
                    if n_miss > 0:
                        any_missing = True
                    row += f" {n_miss:>6}/{n_total:<6} ({pct:>5.1f}%)"
                else:
                    row += f" {'COLUMN NOT FOUND':>20}"
                    any_missing = True
            lines.append(row)

    lines.append("")
    lines.append("=" * 100)
    if not any_missing:
        lines.append("No missing values detected across all variables and populations.")
    else:
        lines.append("Missing values detected. Default handling: listwise deletion (complete-case).")
    lines.append("=" * 100)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Regression Functions
# ═══════════════════════════════════════════════════════════════════════════════

def _prepare_categorical(d, col, var_type, reference_level, context_label=""):
    """
    For categorical covariates: set reference level and dummy-encode (drop_first=True).
    Returns: (dataframe_with_dummies, list_of_dummy_columns)
    For continuous covariates: returns (dataframe, [col]) unchanged.
    """
    if var_type != 'categorical':
        return d, [col]

    # Warn if reference_level missing
    non_na = d[col].dropna()
    unique_vals = sorted(non_na.unique().tolist(), key=lambda x: str(x))
    if len(unique_vals) < 2:
        return d, [col]

    if reference_level is None:
        first_cat = unique_vals[0]
        print(
            f"[QC_WARNING] {col}: no reference_level specified, using alphabetical first "
            f"({first_cat}). This may not match research_plan.",
            file=sys.stderr,
        )
        ref = first_cat
    else:
        ref = reference_level
        if ref not in unique_vals:
            print(
                f"[QC_WARNING] {col}: reference_level '{ref}' not present in data "
                f"{context_label}; falling back to alphabetical first ({unique_vals[0]}).",
                file=sys.stderr,
            )
            ref = unique_vals[0]

    ordered = [ref] + [c for c in unique_vals if c != ref]
    d = d.copy()
    d[col] = pd.Categorical(d[col], categories=ordered)
    d = pd.get_dummies(d, columns=[col], prefix=col, drop_first=True, dtype=float)
    dummy_cols = [f"{col}_{c}" for c in ordered[1:]]
    dummy_cols = [c for c in dummy_cols if c in d.columns]
    return d, dummy_cols


def cox_univariate(col, time_col, event_col, data, scale=None,
                   var_type='continuous', reference_level=None,
                   cluster_col=None):
    """
    Fit univariate Cox model.
    Returns: (n, n_events, HR, CI_lower, CI_upper, p_value, schoenfeld_p) or None
    For categorical variables with >2 levels, returns stats for the first non-reference
    dummy (overall model p reported via schoenfeld/effect of the leading contrast);
    multi-level categoricals are best reported via table1 — this keeps the forest
    plot row informative but QC_WARNINGs the user.

    P-7 audit fix (2026-05-07): cluster_col support. When provided, fit uses
    `robust=True, cluster_col=cluster_col` for cluster-robust standard errors
    (multi-center / family / repeated-measure data per survival-diagnostics
    routing). NULL = standard fit unchanged.
    """
    from lifelines import CoxPHFitter
    from lifelines.statistics import proportional_hazard_test

    cols_to_keep = [col, time_col, event_col]
    if cluster_col:
        cols_to_keep.append(cluster_col)
    raw = data[cols_to_keep].copy()
    raw[time_col] = pd.to_numeric(raw[time_col], errors='coerce')
    raw[event_col] = pd.to_numeric(raw[event_col], errors='coerce')
    if var_type != 'categorical':
        raw[col] = pd.to_numeric(raw[col], errors='coerce')
    d = raw.dropna(subset=[col, time_col, event_col])

    if len(d) < 10 or d[event_col].sum() < 5:
        return None
    if scale and var_type != 'categorical':
        d = d.copy()
        d[col] = d[col] / scale

    # Prepare covariate (categorical dummy or continuous)
    d, fit_cols = _prepare_categorical(d, col, var_type, reference_level,
                                        context_label=f"(n={len(d)})")
    if not fit_cols:
        return None
    # Check for zero variance on leading column
    if d[fit_cols[0]].nunique() < 2:
        return None
    if var_type == 'categorical' and len(fit_cols) > 1:
        print(
            f"[QC_WARNING] {col}: multi-level categorical with {len(fit_cols) + 1} levels; "
            f"forest row reports first contrast vs reference. Consider reporting all "
            f"contrasts in table1.",
            file=sys.stderr,
        )
    try:
        cph = CoxPHFitter()
        # P-7 fix: include cluster_col in fit_df when provided
        keep = fit_cols + [time_col, event_col]
        if cluster_col and cluster_col in d.columns:
            keep = keep + [cluster_col]
        fit_df = d[keep]
        if cluster_col and cluster_col in fit_df.columns:
            cph.fit(fit_df, duration_col=time_col, event_col=event_col,
                    robust=True, cluster_col=cluster_col)
        else:
            cph.fit(fit_df, duration_col=time_col, event_col=event_col)
        s = cph.summary
        lead = fit_cols[0]
        hr = float(np.exp(s.loc[lead, 'coef']))
        ci_l = float(np.exp(s.loc[lead, 'coef lower 95%']))
        ci_u = float(np.exp(s.loc[lead, 'coef upper 95%']))
        p = float(s.loc[lead, 'p'])
        n_events = int(d[event_col].sum())

        # Schoenfeld PH test
        ph_p = None
        try:
            ph_result = proportional_hazard_test(cph, fit_df, time_transform='rank')
            pv = ph_result.p_value
            if hasattr(pv, '__len__'):
                ph_p = float(min(pv))  # worst-case across dummies
            else:
                ph_p = float(pv)
            if ph_p < 0.05:
                print(
                    f"[QC_WARNING] PH violated for {col}: Schoenfeld p={ph_p:.3f}",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"  [Cox] Schoenfeld test failed for {col}: {e}")

        return (len(d), n_events, hr, ci_l, ci_u, p, ph_p)
    except Exception as e:
        print(f"  [Cox] Error for {col}: {e}")
        return None


def logistic_univariate(col, outcome_col, data, scale=None,
                        var_type='continuous', reference_level=None):
    """
    Fit univariate logistic regression.
    Returns: (n, n_events, OR, CI_lower, CI_upper, p_value, schoenfeld_p) or None
    schoenfeld_p is always None for logistic (not applicable); returned for
    uniform tuple shape with cox_univariate.
    """
    import statsmodels.api as sm

    raw = data[[col, outcome_col]].copy()
    raw[outcome_col] = pd.to_numeric(raw[outcome_col], errors='coerce')
    if var_type != 'categorical':
        raw[col] = pd.to_numeric(raw[col], errors='coerce')
    d = raw.dropna(subset=[col, outcome_col])

    if len(d) < 10 or d[outcome_col].sum() < 5:
        return None
    if scale and var_type != 'categorical':
        d = d.copy()
        d[col] = d[col] / scale

    d, fit_cols = _prepare_categorical(d, col, var_type, reference_level,
                                        context_label=f"(n={len(d)})")
    if not fit_cols:
        return None
    if d[fit_cols[0]].nunique() < 2:
        return None
    if var_type == 'categorical' and len(fit_cols) > 1:
        print(
            f"[QC_WARNING] {col}: multi-level categorical with {len(fit_cols) + 1} levels; "
            f"forest row reports first contrast vs reference. Consider reporting all "
            f"contrasts in table1.",
            file=sys.stderr,
        )
    try:
        X = sm.add_constant(d[fit_cols])
        model = sm.Logit(d[outcome_col], X).fit(disp=0, method='bfgs', maxiter=200)
        lead = fit_cols[0]
        coef = model.params[lead]
        ci = model.conf_int().loc[lead]
        or_val = float(np.exp(coef))
        ci_l = float(np.exp(ci[0]))
        ci_u = float(np.exp(ci[1]))
        p = float(model.pvalues[lead])
        n_events = int(d[outcome_col].sum())
        return (len(d), n_events, or_val, ci_l, ci_u, p, None)
    except Exception as e:
        print(f"  [Logistic] Error for {col}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Run Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def run_analysis(config, df, grp_x, grp_nonx):
    """Run univariate analysis for all variables across 3 populations."""
    analysis_type = config['analysis_type']
    grp_x_label = config['grouping']['groups'][0]['label']
    grp_nonx_label = config['grouping']['groups'][1]['label']

    if analysis_type == 'cox':
        cs = config['cox_settings']
        time_col = cs['time_column']
        event_col = cs['event_column']
        # P-7 audit fix (2026-05-07): clustered Cox support. SKILL.md previously
        # promised auto-cluster on detected clustering but code never read this
        # field. Now: if cluster_col is provided, pass to cph.fit(robust=True,
        # cluster_col=cluster_col). survival-diagnostics' diagnostic_report.json
        # populates this field via downstream_integration.md rules.
        cluster_col = cs.get('cluster_col') or cs.get('cluster_column')
        if cluster_col and cluster_col not in df.columns:
            sys.exit(
                f"[FATAL] cluster_col='{cluster_col}' not found in data columns. "
                f"Available: {df.columns.tolist()[:10]}..."
            )
    else:
        outcome_col = config['logistic_settings']['outcome_column']
        cluster_col = None  # logistic regression — clustering not in this path

    populations = [
        ("Overall", df),
        (grp_x_label, grp_x),
        (grp_nonx_label, grp_nonx),
    ]

    results = []
    failed = []

    for section in config['sections']:
        for var in section['variables']:
            col = var['column']
            label = var['label']
            scale = var.get('scale', None)
            scale_label = var.get('scale_label', '')
            var_type = var.get('type', 'continuous')
            reference_level = var.get('reference_level', None)

            row = {
                'label': label,
                'column': col,
                'section': section['header'],
                'scale_label': scale_label,
                'type': var_type,
                'reference_level': reference_level,
            }

            for pop_name, pop_df in populations:
                prefix = pop_name
                if analysis_type == 'cox':
                    res = cox_univariate(col, time_col, event_col, pop_df, scale,
                                         var_type=var_type,
                                         reference_level=reference_level,
                                         cluster_col=cluster_col)  # P-7 audit fix
                else:
                    res = logistic_univariate(col, outcome_col, pop_df, scale,
                                              var_type=var_type,
                                              reference_level=reference_level)

                if res is not None:
                    n, n_ev, effect, ci_l, ci_u, p, ph_p = res
                    row[f'{prefix}_n'] = n
                    row[f'{prefix}_events'] = n_ev
                    row[f'{prefix}_effect'] = effect
                    row[f'{prefix}_ci_lower'] = ci_l
                    row[f'{prefix}_ci_upper'] = ci_u
                    row[f'{prefix}_p'] = p
                    row[f'{prefix}_schoenfeld_p'] = ph_p
                else:
                    row[f'{prefix}_n'] = None
                    row[f'{prefix}_events'] = None
                    row[f'{prefix}_effect'] = None
                    row[f'{prefix}_ci_lower'] = None
                    row[f'{prefix}_ci_upper'] = None
                    row[f'{prefix}_p'] = None
                    row[f'{prefix}_schoenfeld_p'] = None
                    if pop_name == "Overall":
                        failed.append(label)

            results.append(row)
            print(f"  {label}: done")

    return results, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Formatting Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_p(p):
    """Format p-value."""
    if p is None:
        return "–"
    if p < 0.001:
        return "<0.001*"
    elif p < 0.05:
        return f"{p:.3f}*"
    else:
        return f"{p:.3f}"


def fmt_effect(effect, ci_l, ci_u):
    """Format HR/OR with 95% CI."""
    if effect is None:
        return "–"
    return f"{effect:.2f} ({ci_l:.2f}\u2013{ci_u:.2f})"


def fmt_n_events(n, events):
    """Format N (events)."""
    if n is None:
        return "–"
    return f"{n} ({events})"


# ═══════════════════════════════════════════════════════════════════════════════
# Excel Output
# ═══════════════════════════════════════════════════════════════════════════════

# Color constants
DARK_BLUE = "1F3864"
HEADER_BG = "2E5FA3"
SECTION_BG = "EBF2FA"
ALT_ROW = "F7FAFD"
SIG_COLOR = "C00000"
BORDER_COLOR = "BFBFBF"
FOOTNOTE_COLOR = "595959"

THIN_BORDER = Border(
    left=Side(style='thin', color=BORDER_COLOR),
    right=Side(style='thin', color=BORDER_COLOR),
    top=Side(style='thin', color=BORDER_COLOR),
    bottom=Side(style='thin', color=BORDER_COLOR),
)


def write_excel(results, config, df, grp_x, grp_nonx):
    """Write formatted Excel summary table."""
    analysis_type = config['analysis_type']
    effect_label = "HR" if analysis_type == 'cox' else "OR"
    grp_x_label = config['grouping']['groups'][0]['label']
    grp_nonx_label = config['grouping']['groups'][1]['label']
    output_path = config['output_file']

    # Compute population summaries
    pop_info = {}
    for pop_name, pop_df in [("Overall", df), (grp_x_label, grp_x), (grp_nonx_label, grp_nonx)]:
        n = len(pop_df)
        if analysis_type == 'cox':
            cs = config['cox_settings']
            ev = pd.to_numeric(pop_df[cs['event_column']], errors='coerce').sum()
            pop_info[pop_name] = f"{pop_name} (n={n}, events={int(ev)})"
        else:
            oc = config['logistic_settings']['outcome_column']
            ev = pd.to_numeric(pop_df[oc], errors='coerce').sum()
            pop_info[pop_name] = f"{pop_name} (n={n}, events={int(ev)})"

    wb = Workbook()
    ws = wb.active
    ws.title = "Univariate Analysis"

    # Styles
    title_font = Font(name='Arial', size=12, bold=True, color="FFFFFF")
    title_fill = PatternFill(start_color=DARK_BLUE, end_color=DARK_BLUE, fill_type='solid')
    subtitle_font = Font(name='Arial', size=10, color="FFFFFF")

    header_font = Font(name='Arial', size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color=HEADER_BG, end_color=HEADER_BG, fill_type='solid')

    section_font = Font(name='Arial', size=10, bold=True, color=DARK_BLUE)
    section_fill = PatternFill(start_color=SECTION_BG, end_color=SECTION_BG, fill_type='solid')

    data_font = Font(name='Arial', size=10)
    alt_fill = PatternFill(start_color=ALT_ROW, end_color=ALT_ROW, fill_type='solid')
    no_fill = PatternFill(fill_type=None)

    sig_font = Font(name='Arial', size=10, bold=True, color=SIG_COLOR)
    footnote_font = Font(name='Arial', size=8, italic=True, color=FOOTNOTE_COLOR)

    # Column layout: A=Variable, B=Unit
    # C,D,E,F = Overall (N(events), HR/OR(95%CI), p, PH p)
    # G,H,I,J = Group X
    # K,L,M,N = Group Non-X
    # Total columns: 14 (2 + 3 * 4)
    per_pop_cols = 4
    n_pops = 3
    total_cols = 2 + n_pops * per_pop_cols  # 14
    col_widths = {
        1: 30, 2: 14,
        3: 14, 4: 22, 5: 10, 6: 10,
        7: 14, 8: 22, 9: 10, 10: 10,
        11: 14, 12: 22, 13: 10, 14: 10,
    }
    for c, w in col_widths.items():
        ws.column_dimensions[get_column_letter(c)].width = w

    row_idx = 1

    # Row 1: Title
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols)
    cell = ws.cell(row=row_idx, column=1, value=config.get('title', f'Univariate {effect_label} Analysis'))
    cell.font = title_font
    cell.fill = title_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    for c in range(1, total_cols + 1):
        ws.cell(row=row_idx, column=c).fill = title_fill
    row_idx += 1

    # Row 2: Subtitle
    subtitle = config.get('subtitle', '')
    if subtitle:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols)
        cell = ws.cell(row=row_idx, column=1, value=subtitle)
        cell.font = subtitle_font
        cell.fill = PatternFill(start_color=DARK_BLUE, end_color=DARK_BLUE, fill_type='solid')
        cell.alignment = Alignment(horizontal='center', vertical='center')
        for c in range(1, total_cols + 1):
            ws.cell(row=row_idx, column=c).fill = PatternFill(start_color=DARK_BLUE, end_color=DARK_BLUE, fill_type='solid')
        row_idx += 1

    # Row 3: Population group headers (merged)
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx + 1, end_column=1)  # Variable
    ws.merge_cells(start_row=row_idx, start_column=2, end_row=row_idx + 1, end_column=2)  # Unit
    cell = ws.cell(row=row_idx, column=1, value="Variable")
    cell.font = header_font; cell.fill = header_fill; cell.alignment = Alignment(horizontal='center', vertical='center')
    cell = ws.cell(row=row_idx, column=2, value="Unit")
    cell.font = header_font; cell.fill = header_fill; cell.alignment = Alignment(horizontal='center', vertical='center')

    for i, pop_name in enumerate(["Overall", grp_x_label, grp_nonx_label]):
        start_col = 3 + i * per_pop_cols
        ws.merge_cells(start_row=row_idx, start_column=start_col, end_row=row_idx, end_column=start_col + per_pop_cols - 1)
        cell = ws.cell(row=row_idx, column=start_col, value=pop_info[pop_name])
        cell.font = header_font; cell.fill = header_fill; cell.alignment = Alignment(horizontal='center', vertical='center')
        for c in range(start_col, start_col + per_pop_cols):
            ws.cell(row=row_idx, column=c).fill = header_fill

    row_idx += 1

    # Row 4: Sub-headers (Cox only gets PH p; logistic shows '—')
    ph_header = "PH p" if analysis_type == 'cox' else "—"
    sub_headers = ["N (events)", f"{effect_label} (95% CI)", "p-value", ph_header]
    for c in range(1, total_cols + 1):
        ws.cell(row=row_idx, column=c).fill = header_fill
        ws.cell(row=row_idx, column=c).font = header_font
        ws.cell(row=row_idx, column=c).alignment = Alignment(horizontal='center', vertical='center')
        ws.cell(row=row_idx, column=c).border = THIN_BORDER

    for i in range(n_pops):
        for j, sh in enumerate(sub_headers):
            col = 3 + i * per_pop_cols + j
            cell = ws.cell(row=row_idx, column=col, value=sh)
            cell.font = header_font; cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')

    row_idx += 1
    ws.freeze_panes = ws.cell(row=row_idx, column=1)

    # Data rows
    current_section = None
    data_row_idx = 0

    for result in results:
        # Section header
        if result['section'] != current_section:
            current_section = result['section']
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols)
            cell = ws.cell(row=row_idx, column=1, value=current_section)
            cell.font = section_font; cell.fill = section_fill
            cell.alignment = Alignment(horizontal='left', vertical='center')
            for c in range(1, total_cols + 1):
                ws.cell(row=row_idx, column=c).fill = section_fill
                ws.cell(row=row_idx, column=c).border = THIN_BORDER
            row_idx += 1
            data_row_idx = 0

        # Alternating row color
        row_fill = alt_fill if data_row_idx % 2 == 1 else no_fill

        # Variable name and unit
        ws.cell(row=row_idx, column=1, value=result['label']).font = data_font
        ws.cell(row=row_idx, column=1).fill = row_fill
        ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal='left', vertical='center', indent=1)
        ws.cell(row=row_idx, column=2, value=result['scale_label']).font = data_font
        ws.cell(row=row_idx, column=2).fill = row_fill
        ws.cell(row=row_idx, column=2).alignment = Alignment(horizontal='center', vertical='center')

        # Population results
        for i, pop_name in enumerate(["Overall", grp_x_label, grp_nonx_label]):
            prefix = pop_name
            col_start = 3 + i * per_pop_cols

            n_ev_str = fmt_n_events(result.get(f'{prefix}_n'), result.get(f'{prefix}_events'))
            effect_str = fmt_effect(result.get(f'{prefix}_effect'),
                                    result.get(f'{prefix}_ci_lower'),
                                    result.get(f'{prefix}_ci_upper'))
            p_str = fmt_p(result.get(f'{prefix}_p'))
            p_val = result.get(f'{prefix}_p')
            ph_p_val = result.get(f'{prefix}_schoenfeld_p')
            if analysis_type == 'cox':
                ph_str = fmt_p(ph_p_val)
            else:
                ph_str = "—"

            ws.cell(row=row_idx, column=col_start, value=n_ev_str).font = data_font
            ws.cell(row=row_idx, column=col_start + 1, value=effect_str).font = data_font
            p_cell = ws.cell(row=row_idx, column=col_start + 2, value=p_str)
            if p_val is not None and p_val < 0.05:
                p_cell.font = sig_font
            else:
                p_cell.font = data_font
            ph_cell = ws.cell(row=row_idx, column=col_start + 3, value=ph_str)
            if analysis_type == 'cox' and ph_p_val is not None and ph_p_val < 0.05:
                ph_cell.font = sig_font
            else:
                ph_cell.font = data_font

            for c in range(col_start, col_start + per_pop_cols):
                ws.cell(row=row_idx, column=c).fill = row_fill
                ws.cell(row=row_idx, column=c).alignment = Alignment(horizontal='center', vertical='center')
                ws.cell(row=row_idx, column=c).border = THIN_BORDER

        # Apply border and fill to first 2 columns too
        for c in [1, 2]:
            ws.cell(row=row_idx, column=c).border = THIN_BORDER

        row_idx += 1
        data_row_idx += 1

    # Footnotes
    row_idx += 1
    if config.get('abbreviations'):
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols)
        cell = ws.cell(row=row_idx, column=1, value=config['abbreviations'])
        cell.font = footnote_font
        cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws.row_dimensions[row_idx].height = 30
        row_idx += 1

    note = f"* p < 0.05  |  {effect_label} = {'hazard ratio' if analysis_type == 'cox' else 'odds ratio'}; CI = confidence interval"
    if analysis_type == 'cox':
        note += "  |  PH p = Schoenfeld residuals test for proportional hazards assumption (p < 0.05 indicates violation)"
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols)
    cell = ws.cell(row=row_idx, column=1, value=note)
    cell.font = footnote_font
    cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)

    # Print area
    ws.print_title_rows = '1:4'

    wb.save(output_path)
    print(f"Excel saved: {output_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Forest Plot
# ═══════════════════════════════════════════════════════════════════════════════

# Plot colors and markers for 3 populations
POP_STYLES = [
    {'color': '#2E5FA3', 'marker': 'o', 'label_key': 'Overall'},        # Overall: blue circle
    {'color': '#E07B39', 'marker': 's', 'label_key': None},             # Group X: orange square
    {'color': '#5BAA5B', 'marker': '^', 'label_key': None},             # Group Non-X: green triangle
]


def compute_truncation(results, config):
    """Auto-determine x-axis limits for the forest plot."""
    fp = config['forest_plot']
    if fp['truncation_method'] == 'manual' and fp['truncation_range'] is not None:
        return fp['truncation_range'][0], fp['truncation_range'][1]

    grp_x_label = config['grouping']['groups'][0]['label']
    grp_nonx_label = config['grouping']['groups'][1]['label']
    pop_names = ["Overall", grp_x_label, grp_nonx_label]

    all_ci_lower = []
    all_ci_upper = []
    all_effects = []

    for r in results:
        for pop in pop_names:
            ci_l = r.get(f'{pop}_ci_lower')
            ci_u = r.get(f'{pop}_ci_upper')
            eff = r.get(f'{pop}_effect')
            if ci_l is not None and ci_u is not None and eff is not None:
                # Skip extreme values that would distort the plot
                if 0.01 <= eff <= 100 and ci_u / max(ci_l, 0.001) < 1000:
                    all_ci_lower.append(ci_l)
                    all_ci_upper.append(ci_u)
                    all_effects.append(eff)

    if not all_ci_lower:
        return 0.1, 10.0

    # Use percentiles to exclude extreme outliers
    lower_bound = max(0.05, np.percentile(all_ci_lower, 2.5))
    upper_bound = min(50.0, np.percentile(all_ci_upper, 97.5))

    # Round to aesthetically pleasing values
    # Lower: round down
    nice_lowers = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    for nl in nice_lowers:
        if lower_bound <= nl:
            lower_bound = nl
            break
    else:
        lower_bound = round(lower_bound, 1)

    # Upper: round up
    nice_uppers = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 50.0]
    for nu in nice_uppers:
        if upper_bound <= nu:
            upper_bound = nu
            break
    else:
        upper_bound = 50.0

    # Ensure reference line is visible
    lower_bound = min(lower_bound, 0.8)
    upper_bound = max(upper_bound, 1.5)

    return lower_bound, upper_bound


def write_forest_plot(results, config):
    """Generate the forest plot."""
    analysis_type = config['analysis_type']
    effect_label = "HR" if analysis_type == 'cox' else "OR"
    grp_x_label = config['grouping']['groups'][0]['label']
    grp_nonx_label = config['grouping']['groups'][1]['label']
    pop_names = ["Overall", grp_x_label, grp_nonx_label]

    # Compute truncation
    x_lower, x_upper = compute_truncation(results, config)

    # Collect sections for grouping
    sections_order = []
    for section in config['sections']:
        sections_order.append(section['header'])

    # Calculate figure dimensions
    n_vars = len(results)
    n_sections = len(set(r['section'] for r in results))
    # Each variable has 3 sub-rows + spacing
    group_spacing = 0.3
    var_spacing = 1.0
    section_spacing = 0.6

    total_height_units = n_vars * (3 * group_spacing + var_spacing) + n_sections * section_spacing + 2
    fig_height = max(6, total_height_units * 0.28 + 3)
    fig_width = 22

    fig, (ax_labels, ax_plot, ax_text) = plt.subplots(
        1, 3, figsize=(fig_width, fig_height),
        gridspec_kw={'width_ratios': [3.5, 4, 5], 'wspace': 0.02}
    )

    # Configure axes
    ax_labels.set_xlim(0, 1)
    ax_labels.axis('off')

    ax_plot.set_xscale('log')
    ax_plot.set_xlim(x_lower, x_upper)
    ax_plot.axvline(x=1.0, color='gray', linestyle='--', linewidth=0.8, zorder=0)
    ax_plot.set_xlabel(f'{effect_label} (95% CI)', fontsize=10, fontweight='bold')

    ax_text.set_xlim(0, 1)
    ax_text.axis('off')

    # Custom x-axis ticks
    log_lower = math.log10(x_lower)
    log_upper = math.log10(x_upper)
    tick_values = [x_lower]
    # Add some intermediate ticks
    candidate_ticks = [0.1, 0.2, 0.25, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0, 20.0, 30.0, 50.0]
    for ct in candidate_ticks:
        if x_lower < ct < x_upper:
            tick_values.append(ct)
    tick_values.append(x_upper)
    tick_values = sorted(set(tick_values))
    ax_plot.set_xticks(tick_values)
    ax_plot.get_xaxis().set_major_formatter(mticker.FormatStrFormatter('%.2g'))

    # Build y positions from bottom to top
    y_pos = 0
    y_positions = []  # (y_center_for_variable, section_header_y_or_None)
    current_section = None

    # Process in reverse so bottom of plot = first variable
    reversed_results = list(reversed(results))

    y_data = []  # list of dicts with y positions per population for each result

    for result in reversed_results:
        if result['section'] != current_section:
            current_section = result['section']
            y_pos += section_spacing
            y_data.append({'type': 'section', 'label': current_section, 'y': y_pos})
            y_pos += section_spacing

        # 3 sub-rows for each population
        pop_ys = {}
        base_y = y_pos
        for i in range(3):
            pop_ys[pop_names[i]] = base_y + i * group_spacing
        y_data.append({
            'type': 'variable',
            'result': result,
            'pop_ys': pop_ys,
            'y_center': base_y + group_spacing,  # center of 3 rows
        })
        y_pos = base_y + 3 * group_spacing + var_spacing

    y_max = y_pos + 1

    ax_labels.set_ylim(-0.5, y_max)
    ax_plot.set_ylim(-0.5, y_max)
    ax_text.set_ylim(-0.5, y_max)

    # Remove y-axis ticks from plot
    ax_plot.set_yticks([])
    ax_plot.spines['left'].set_visible(False)
    ax_plot.spines['right'].set_visible(False)
    ax_plot.spines['top'].set_visible(False)

    # Plot header row for text columns
    header_y = y_max - 0.3
    # Text column headers
    col_positions = []
    for i, pop in enumerate(pop_names):
        x_start = i * 0.33 + 0.01
        col_positions.append(x_start)
        ax_text.text(x_start, header_y, pop, fontsize=8, fontweight='bold',
                     va='center', ha='left', color='#1F3864')
        # Sub-headers
        ax_text.text(x_start, header_y - 0.6, f'{effect_label} (95% CI)', fontsize=7,
                     va='center', ha='left', color='#555555')
        ax_text.text(x_start + 0.2, header_y - 0.6, 'p', fontsize=7,
                     va='center', ha='left', color='#555555')

    # Draw data
    for item in y_data:
        if item['type'] == 'section':
            # Section header
            ax_labels.text(0.02, item['y'], item['label'], fontsize=10, fontweight='bold',
                          va='center', ha='left', color='#1F3864')
            # Separator line
            ax_plot.axhline(y=item['y'] - section_spacing * 0.5, color='#BFBFBF',
                           linewidth=0.5, linestyle='-', zorder=0)

        elif item['type'] == 'variable':
            result = item['result']
            pop_ys = item['pop_ys']
            y_center = item['y_center']

            # Variable label on left
            ax_labels.text(0.08, y_center, result['label'], fontsize=9,
                          va='center', ha='left', color='#333333')
            if result['scale_label']:
                ax_labels.text(0.08, y_center - 0.25, f"  ({result['scale_label']})",
                              fontsize=7, va='center', ha='left', color='#777777')

            # Plot markers and CIs for each population
            for i, pop in enumerate(pop_names):
                y = pop_ys[pop]
                effect = result.get(f'{pop}_effect')
                ci_l = result.get(f'{pop}_ci_lower')
                ci_u = result.get(f'{pop}_ci_upper')
                p_val = result.get(f'{pop}_p')

                style = POP_STYLES[i]
                color = style['color']
                marker = style['marker']

                if effect is not None and ci_l is not None and ci_u is not None:
                    # Skip extreme values from plot (but they appear in table)
                    if effect < 0.01 or effect > 100 or ci_u / max(ci_l, 0.001) > 1000:
                        # Write "extreme" text
                        ax_text.text(col_positions[i], y,
                                    fmt_effect(effect, ci_l, ci_u), fontsize=7.5,
                                    va='center', ha='left', color='#999999')
                        ax_text.text(col_positions[i] + 0.2, y,
                                    fmt_p(p_val), fontsize=7.5,
                                    va='center', ha='left',
                                    color=SIG_COLOR if (p_val and p_val < 0.05) else '#333333',
                                    fontweight='bold' if (p_val and p_val < 0.05) else 'normal')
                        continue

                    # Clip CI to truncation range
                    plot_ci_l = max(ci_l, x_lower)
                    plot_ci_u = min(ci_u, x_upper)
                    plot_effect = max(min(effect, x_upper), x_lower)

                    # Draw CI line
                    ax_plot.plot([plot_ci_l, plot_ci_u], [y, y],
                               color=color, linewidth=1.5, solid_capstyle='butt', zorder=2)

                    # Draw arrows for truncated CIs
                    if ci_l < x_lower:
                        ax_plot.annotate('', xy=(x_lower, y),
                                        xytext=(x_lower * 1.15, y),
                                        arrowprops=dict(arrowstyle='->', color=color, lw=1.5),
                                        zorder=3)
                    if ci_u > x_upper:
                        ax_plot.annotate('', xy=(x_upper, y),
                                        xytext=(x_upper / 1.15, y),
                                        arrowprops=dict(arrowstyle='->', color=color, lw=1.5),
                                        zorder=3)

                    # Draw point estimate
                    ax_plot.plot(plot_effect, y, marker=marker, color=color,
                               markersize=7, markeredgecolor='white', markeredgewidth=0.5, zorder=5)

                    # Text annotations on right
                    ax_text.text(col_positions[i], y,
                                fmt_effect(effect, ci_l, ci_u), fontsize=7.5,
                                va='center', ha='left', color='#333333')
                    ax_text.text(col_positions[i] + 0.2, y,
                                fmt_p(p_val), fontsize=7.5,
                                va='center', ha='left',
                                color=SIG_COLOR if (p_val and p_val < 0.05) else '#333333',
                                fontweight='bold' if (p_val and p_val < 0.05) else 'normal')

                else:
                    # N/A
                    ax_text.text(col_positions[i], y, "N/A", fontsize=7.5,
                                va='center', ha='left', color='#999999')

    # Legend
    legend_elements = [
        Line2D([0], [0], marker='o', color='#2E5FA3', label='Overall',
               markersize=7, markeredgecolor='white', markeredgewidth=0.5, linewidth=1.5),
        Line2D([0], [0], marker='s', color='#E07B39', label=grp_x_label,
               markersize=7, markeredgecolor='white', markeredgewidth=0.5, linewidth=1.5),
        Line2D([0], [0], marker='^', color='#5BAA5B', label=grp_nonx_label,
               markersize=7, markeredgecolor='white', markeredgewidth=0.5, linewidth=1.5),
    ]
    ax_plot.legend(handles=legend_elements, loc='lower right', fontsize=8,
                  framealpha=0.9, edgecolor='#BFBFBF')

    # Title
    title = config.get('title', f'Univariate {effect_label} Analysis — Forest Plot')
    fig.suptitle(title, fontsize=13, fontweight='bold', color='#1F3864', y=0.98)

    # Save
    output_base = os.path.splitext(config['output_file'])[0]
    fmt = config['forest_plot'].get('format', 'png')
    dpi = config['forest_plot'].get('dpi', 300)
    output_img = f"{output_base}.{fmt}"

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_img, dpi=dpi, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"Forest plot saved: {output_img}")


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
        print("Usage: python univariate_forest.py config.json [--check-missing] [--style=<journal>]")
        sys.exit(1)

    config_path = sys.argv[1]
    check_missing_only = '--check-missing' in sys.argv

    config = load_config(config_path)
    print("Loading data...")
    df = load_data(config)
    grp_x, grp_nonx = split_groups(df, config)

    grp_x_label = config['grouping']['groups'][0]['label']
    grp_nonx_label = config['grouping']['groups'][1]['label']
    print(f"Overall: n={len(df)}")
    print(f"{grp_x_label}: n={len(grp_x)}")
    print(f"{grp_nonx_label}: n={len(grp_nonx)}")

    if check_missing_only:
        report = check_missing(df, grp_x, grp_nonx, config)
        print(report)
        sys.exit(0)

    # Apply listwise deletion if configured
    if config['missing_data_handling'] == 'listwise':
        df = apply_listwise_deletion(df, config)
        grp_x, grp_nonx = split_groups(df, config)
        grp_x_label = config['grouping']['groups'][0]['label']
        grp_nonx_label = config['grouping']['groups'][1]['label']
        print(f"After listwise deletion: Overall n={len(df)}, {grp_x_label} n={len(grp_x)}, {grp_nonx_label} n={len(grp_nonx)}")

    print("\nRunning univariate analysis...")
    results, failed = run_analysis(config, df, grp_x, grp_nonx)

    print("\nGenerating Excel table...")
    write_excel(results, config, df, grp_x, grp_nonx)

    print("\nGenerating forest plot...")
    write_forest_plot(results, config)

    # Summary
    analysis_type = config['analysis_type']
    effect_label = "HR" if analysis_type == 'cox' else "OR"
    pop_names = ["Overall", grp_x_label, grp_nonx_label]

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    for pop in pop_names:
        sig_count = sum(1 for r in results if r.get(f'{pop}_p') is not None and r[f'{pop}_p'] < 0.05)
        total = sum(1 for r in results if r.get(f'{pop}_p') is not None)
        print(f"  {pop}: {sig_count}/{total} variables significant (p < 0.05)")

    if failed:
        print(f"\n  Variables that could not be analyzed (Overall): {', '.join(failed)}")

    print("=" * 60)

    # ── QC Warnings ──────────────────────────────────────────────────────────
    # P-4 batch (2026-05-07 partitioned-flame audit): track blocking emissions and
    # sys.exit(2) at the end so the pipeline sees a non-zero exit when [QC_BLOCKING]
    # is raised. Previously [QC_BLOCKING] was emitted but exit was always 0,
    # making the pipeline think the step succeeded with warnings.
    qc_blocking_count = 0

    def _qc_block(msg):
        nonlocal qc_blocking_count
        print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
        qc_blocking_count += 1

    try:
        # Check group sizes
        for pop_label, pop_n in [("Overall", len(df)), (grp_x_label, len(grp_x)), (grp_nonx_label, len(grp_nonx))]:
            if pop_n < 30:
                print(f"[QC_WARNING] Population '{pop_label}' has n={pop_n} (< 30)", file=sys.stderr)

        # Check 0 events in any group
        if analysis_type == 'cox':
            cs = config['cox_settings']
            for pop_label, pop_df in [("Overall", df), (grp_x_label, grp_x), (grp_nonx_label, grp_nonx)]:
                ev = pd.to_numeric(pop_df[cs['event_column']], errors='coerce').sum()
                if ev == 0:
                    _qc_block(f"Population '{pop_label}' has 0 events")
        else:
            oc = config['logistic_settings']['outcome_column']
            for pop_label, pop_df in [("Overall", df), (grp_x_label, grp_x), (grp_nonx_label, grp_nonx)]:
                ev = pd.to_numeric(pop_df[oc], errors='coerce').sum()
                if ev == 0:
                    _qc_block(f"Population '{pop_label}' has 0 events")

        # Check for convergence failures (indicated by variables in 'failed')
        if failed:
            _qc_block(f"Model did not converge for {len(failed)} variable(s): {', '.join(failed)}")

        # Check for extreme HR/OR values
        for r in results:
            for pop in pop_names:
                effect = r.get(f'{pop}_effect')
                ci_l = r.get(f'{pop}_ci_lower')
                ci_u = r.get(f'{pop}_ci_upper')
                if effect is not None:
                    if np.isinf(effect) or np.isnan(effect) or effect <= 0:
                        _qc_block(f"{r['label']} ({pop}): {effect_label}={effect} is Inf/NaN/<=0")
                    elif effect > 10:
                        print(f"[QC_WARNING] {r['label']} ({pop}): {effect_label}={effect:.2f} > 10", file=sys.stderr)
                    if ci_l is not None and ci_u is not None:
                        ci_width = ci_u - ci_l
                        if ci_width > 100:
                            print(f"[QC_WARNING] {r['label']} ({pop}): CI width={ci_width:.1f} > 100", file=sys.stderr)
    except Exception as e:
        # P-5 territory partial: surface the QC failure rather than silent swallow
        print(f"[QC_WARNING] QC block raised: {type(e).__name__}: {e}", file=sys.stderr)

    if qc_blocking_count > 0:
        sys.exit(2)


if __name__ == '__main__':
    main()
