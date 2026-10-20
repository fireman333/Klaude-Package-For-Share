#!/usr/bin/env python3
"""
Multivariate Analysis + Interaction Analysis
Performs multivariate Cox (HR) or logistic (OR) regression on the overall population,
then fits a single interaction model (grp x covariate) and derives subgroup HR/OR and p-interaction
for every covariate using the delta method (Var = V_gg + x^2*V_ii + 2x*V_gi).

Usage:
    python multivariate_interaction.py config.json                  # Full analysis
    python multivariate_interaction.py config.json --check-missing  # Missing data report only
"""

import sys
import json
import os
import operator
import pandas as pd
import numpy as np
from scipy import stats
# P-3 batch (2026-05-07 partitioned-flame audit): removed `import warnings;
# warnings.filterwarnings('ignore')` — global suppression hid lifelines / scipy /
# statsmodels convergence and ill-conditioned-covariance warnings (silent error
# pattern).

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
    config.setdefault('title', '')
    config.setdefault('subtitle', '')
    config.setdefault('abbreviations', '')
    config.setdefault('missing_data_handling', 'listwise')
    config.setdefault('interaction_variables', 'all')
    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Data Loading & Preprocessing
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


def get_all_var_columns(config):
    """Get all variable column names from config."""
    cols = []
    for section in config['sections']:
        for var in section['variables']:
            cols.append(var['column'])
    return cols


def get_outcome_columns(config):
    """Get outcome/time columns based on analysis type."""
    if config['analysis_type'] == 'cox':
        cs = config['cox_settings']
        return [cs['time_column'], cs['event_column']]
    else:
        return [config['logistic_settings']['outcome_column']]


def prepare_analysis_df(df, config):
    """Prepare dataframe for analysis: convert to numeric and handle missing data."""
    var_cols = get_all_var_columns(config)
    outcome_cols = get_outcome_columns(config)
    all_cols = var_cols + outcome_cols

    # Also include the grouping column
    grp_col = config['grouping']['column']
    if grp_col not in all_cols:
        all_cols.append(grp_col)

    df_work = df.copy()
    for col in all_cols:
        if col in df_work.columns:
            df_work[col] = pd.to_numeric(df_work[col], errors='coerce')

    if config['missing_data_handling'] == 'listwise':
        existing_cols = [c for c in all_cols if c in df_work.columns]
        df_work = df_work.dropna(subset=existing_cols)

    return df_work


# ═══════════════════════════════════════════════════════════════════════════════
# Missing Data Check
# ═══════════════════════════════════════════════════════════════════════════════

def check_missing(df, grp1, grp2, config):
    """Print a missing data report for all 3 populations + effective N after listwise deletion."""
    g1_label = config['grouping']['groups'][0]['label']
    g2_label = config['grouping']['groups'][1]['label']

    outcome_cols = get_outcome_columns(config)
    var_cols = get_all_var_columns(config)
    grp_col = config['grouping']['column']
    all_cols = var_cols + outcome_cols
    if grp_col not in all_cols:
        all_cols.append(grp_col)

    lines = []
    lines.append("=" * 100)
    lines.append("MISSING DATA REPORT")
    lines.append("=" * 100)
    lines.append(f"{'Variable':<35} {'Overall':>20} {g1_label:>20} {g2_label:>20}")
    lines.append("-" * 100)

    any_missing = False

    # Check outcome/time columns first
    for col_name in outcome_cols:
        row = f"  {col_name:<33}"
        for pop_name, pop_df in [("Overall", df), (g1_label, grp1), (g2_label, grp2)]:
            if col_name in pop_df.columns:
                n_miss = pd.to_numeric(pop_df[col_name], errors='coerce').isna().sum()
                n_total = len(pop_df)
                pct = n_miss / n_total * 100 if n_total > 0 else 0
                if n_miss > 0:
                    any_missing = True
                row += f" {n_miss:>6}/{n_total:<6} ({pct:>5.1f}%)"
            else:
                row += f" {'COLUMN NOT FOUND':>20}"
                any_missing = True
        lines.append(row)

    # Check grouping variable
    row = f"  {grp_col:<33}"
    for pop_name, pop_df in [("Overall", df), (g1_label, grp1), (g2_label, grp2)]:
        if grp_col in pop_df.columns:
            n_miss = pd.to_numeric(pop_df[grp_col], errors='coerce').isna().sum()
            n_total = len(pop_df)
            pct = n_miss / n_total * 100 if n_total > 0 else 0
            if n_miss > 0:
                any_missing = True
            row += f" {n_miss:>6}/{n_total:<6} ({pct:>5.1f}%)"
        else:
            row += f" {'COLUMN NOT FOUND':>20}"
    lines.append(row)

    lines.append("-" * 100)

    # Check analysis variables by section
    for section in config['sections']:
        lines.append(f"\n{section['header']}")
        for var in section['variables']:
            col = var['column']
            label = var['label']
            row = f"  {label:<33}"
            for pop_name, pop_df in [("Overall", df), (g1_label, grp1), (g2_label, grp2)]:
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

    # Report effective N after listwise deletion
    lines.append("")
    lines.append("-" * 100)
    lines.append("EFFECTIVE SAMPLE SIZE (after listwise deletion of all analysis variables):")

    existing_cols = [c for c in all_cols if c in df.columns]
    df_numeric = df.copy()
    for c in existing_cols:
        df_numeric[c] = pd.to_numeric(df_numeric[c], errors='coerce')
    df_complete = df_numeric.dropna(subset=existing_cols)

    grp_col_numeric = pd.to_numeric(df_complete[grp_col], errors='coerce')
    g1_val = config['grouping']['groups'][0]['value']
    g2_val = config['grouping']['groups'][1]['value']
    g1_complete = df_complete[grp_col_numeric == g1_val]
    g2_complete = df_complete[grp_col_numeric == g2_val]

    lines.append(f"  Overall:    {len(df_complete):>6} (original: {len(df)})")
    lines.append(f"  {g1_label:10s}:  {len(g1_complete):>6} (original: {len(grp1)})")
    lines.append(f"  {g2_label:10s}:  {len(g2_complete):>6} (original: {len(grp2)})")

    if config['analysis_type'] == 'cox':
        event_col = config['cox_settings']['event_column']
        for lbl, sub_df in [("Overall", df_complete), (g1_label, g1_complete), (g2_label, g2_complete)]:
            ev = int(pd.to_numeric(sub_df[event_col], errors='coerce').sum())
            lines.append(f"  {lbl} events: {ev}")

    lines.append("")
    lines.append("=" * 100)
    if not any_missing:
        lines.append("No missing values detected across all variables and populations.")
    else:
        lines.append("Missing values detected. Default handling: listwise deletion.")
    lines.append("=" * 100)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Multivariate Regression
# ═══════════════════════════════════════════════════════════════════════════════

def cox_multivariate(var_cols, time_col, event_col, data):
    """
    Fit multivariate Cox model with all covariates.
    Returns (results, n, n_events, fit) where `results` is a dict of
    {column: (coef, HR, CI_lower, CI_upper, p)} or None on failure, and `fit` is
    {'model': CoxPHFitter, 'data': DataFrame, 'var_cols': [...]} or None.
    `fit` is what the proportional-hazards diagnostics (ph_assumption_test) consume;
    without it the fitted model would be discarded and PH could not be tested.
    """
    from lifelines import CoxPHFitter

    cols_needed = var_cols + [time_col, event_col]
    d = data[cols_needed].dropna().copy()

    if len(d) < 10 or d[event_col].sum() < 5:
        return None, len(d), int(d[event_col].sum()) if len(d) > 0 else 0, None

    # Check for zero variance
    for col in var_cols:
        if d[col].nunique() < 2:
            d = d.drop(columns=[col])
            var_cols = [c for c in var_cols if c != col]
            print(f"  [Warning] Dropped {col} due to zero variance")

    if not var_cols:
        return None, len(d), int(d[event_col].sum()), None

    try:
        cph = CoxPHFitter()
        cph.fit(d, duration_col=time_col, event_col=event_col)
        s = cph.summary
        results = {}
        for col in var_cols:
            if col in s.index:
                results[col] = {
                    'coef': float(s.loc[col, 'coef']),
                    'effect': float(np.exp(s.loc[col, 'coef'])),
                    'ci_lower': float(np.exp(s.loc[col, 'coef lower 95%'])),
                    'ci_upper': float(np.exp(s.loc[col, 'coef upper 95%'])),
                    'p': float(s.loc[col, 'p']),
                }
        fit = {'model': cph, 'data': d, 'var_cols': list(var_cols)}
        return results, len(d), int(d[event_col].sum()), fit
    except Exception as e:
        print(f"  [Cox Multivariate] Error: {e}")
        return None, len(d), int(d[event_col].sum()) if len(d) > 0 else 0, None


def logistic_multivariate(var_cols, outcome_col, data):
    """
    Fit multivariate logistic regression with all covariates.
    Returns dict of {column: (coef, OR, CI_lower, CI_upper, p)} or None on failure.
    """
    import statsmodels.api as sm

    cols_needed = var_cols + [outcome_col]
    d = data[cols_needed].dropna().copy()

    if len(d) < 10 or d[outcome_col].sum() < 5:
        return None, len(d), int(d[outcome_col].sum()) if len(d) > 0 else 0

    # Check for zero variance
    for col in var_cols:
        if d[col].nunique() < 2:
            d = d.drop(columns=[col])
            var_cols = [c for c in var_cols if c != col]
            print(f"  [Warning] Dropped {col} due to zero variance")

    if not var_cols:
        return None, len(d), int(d[outcome_col].sum())

    try:
        X = sm.add_constant(d[var_cols])
        model = sm.Logit(d[outcome_col], X).fit(disp=0, method='bfgs', maxiter=200)
        results = {}
        ci = model.conf_int()
        for col in var_cols:
            if col in model.params.index:
                results[col] = {
                    'coef': float(model.params[col]),
                    'effect': float(np.exp(model.params[col])),
                    'ci_lower': float(np.exp(ci.loc[col, 0])),
                    'ci_upper': float(np.exp(ci.loc[col, 1])),
                    'p': float(model.pvalues[col]),
                }
        return results, len(d), int(d[outcome_col].sum())
    except Exception as e:
        print(f"  [Logistic Multivariate] Error: {e}")
        return None, len(d), int(d[outcome_col].sum()) if len(d) > 0 else 0


def run_multivariate(df_clean, config):
    """Run multivariate analysis on the overall population.

    The grouping column is included as a main effect so its adjusted HR/OR
    is reported alongside the covariates (previously omitted -> main effect
    was absorbed into the baseline hazard / intercept).
    """
    analysis_type = config['analysis_type']
    grp_col = config['grouping']['column']

    # Collect all variable columns with scaling applied
    var_cols = []
    scale_map = {}
    for section in config['sections']:
        for var in section['variables']:
            col = var['column']
            var_cols.append(col)
            scale = var.get('scale')
            if scale:
                scale_map[col] = scale

    # Ensure grouping column is in the model (main effect of treatment/exposure)
    if grp_col not in var_cols:
        var_cols = [grp_col] + var_cols

    # Apply scaling
    df_work = df_clean.copy()
    for col, scale in scale_map.items():
        if col in df_work.columns:
            df_work[col] = df_work[col] / scale

    if analysis_type == 'cox':
        cs = config['cox_settings']
        results, n, n_events, fit = cox_multivariate(var_cols, cs['time_column'], cs['event_column'], df_work)
    else:
        results, n, n_events = logistic_multivariate(var_cols, config['logistic_settings']['outcome_column'], df_work)
        fit = None  # PH diagnostics are Cox-only

    return results, n, n_events, fit


# ═══════════════════════════════════════════════════════════════════════════════
# Proportional Hazards Assumption (Schoenfeld residuals)
# ═══════════════════════════════════════════════════════════════════════════════

# Two thresholds, because "when do we block" and "when do we stop claiming the
# assumption held" are different questions (2026-08-12 adjudication, dispute 4).
#
# PH_ALPHA (0.01) = automatic hard gate. Deliberately not 0.05: at n≈6000 a
#   clinically trivial 7% early departure trips a 0.05 gate 4 times in 15 runs and a
#   0.01 gate once — a gate that fires on trivia only teaches people to override it.
# PH_ALPHA_REVIEW (0.05) = far edge of the borderline band. At n≈500 a real and
#   clinically major early-only effect (HR 0.5 -> 1.0) lands in 0.01–0.05 in 9 of 40
#   simulations. Those runs must not be blocked (precision is poor at that n) but
#   they must never be described as "no violation" either. The band produces a
#   warning that has to reach methodological_warnings plus an effect-size readout.
PH_ALPHA = 0.01
PH_ALPHA_REVIEW = 0.05

# The gate is decided on ONE pre-specified transform. The review band looks at both,
# because a departure invisible on one time scale can be plain on the other — but
# feeding the minimum p over transforms into the gate would inflate its false
# positives, which is the thing PH_ALPHA exists to prevent.
PH_GATE_TRANSFORM = 'rank'
PH_REVIEW_TRANSFORMS = ('rank', 'km')

# Remedies the author may pre-specify in the plan as `ph_violation_remedy`.
# Pre-specification is the point: "we detected a violation" is not a response to a
# reviewer, "we pre-declared what we would do" is.
#
# NOTE: none of these is performed by THIS script — a remedy runs as its own step,
# against its own table, so that this workbook stays internally consistent (Sheet 1
# and Sheet 2 fitted under the same assumptions) instead of carrying a stratified
# Sheet 1 next to an unstratified Sheet 2. See the 2026-08-12 adjudication, dispute 5.
#
# All three gained shipped generators on 2026-08-12 (`ph-stratified` /
# `ph-time-varying` / `ph-rmst`, via generate_configs._REMEDY_STEPS), so declaring
# one now schedules the analysis and the artifact gate verifies its evidence
# sidecar. PH_REMEDIES_NEEDING_OWN_STEP is therefore empty — kept rather than
# deleted because the sentence it drives ("no generator ships for this, build the
# step yourself") is the right thing to say the next time a remedy is added to the
# vocabulary before its generator exists, and rebuilding that path under pressure
# is how someone ends up at a door with no exit.
PH_REMEDIES = ('stratify', 'time_varying', 'rmst', 'disclose')
PH_REMEDIES_NEEDING_OWN_STEP = ()

# Three outcomes of asking for a PH test, kept distinct on purpose. Collapsing
# "could not be computed" into the same value as "does not apply" is the silent-
# swallow pattern: a Cox model whose Schoenfeld residuals blew up would read as
# "nothing to report" and sail through the gate. NOT_COMPUTED is blocking.
PH_COMPUTED = 'computed'
PH_NOT_COMPUTED = 'not_computed'
PH_NOT_APPLICABLE = 'not_applicable'


def _ph_statistics(cph, model_df, time_transform):
    """
    Schoenfeld statistics for ONE time transform.

    Variable-level statistics reproduce lifelines' `proportional_hazard_test`
    (T_j = (sum_i xx_i r*_ij)^2 / (d * se_j^2 * sum_i xx_i^2), 1 df).
    The global statistic is the corresponding quadratic form over all covariates
    (chi-square with p df), which lifelines does not expose but R's cox.zph does:
        Q = w' V^-1 w / (d * sum_i xx_i^2),  w = sum_i xx_i r*_i
    where r* are the scaled Schoenfeld residuals (r* = d * V * s), V the covariance
    matrix of the coefficients and d the number of events. Computing both from the
    same residual matrix keeps the global test and the per-variable tests coherent.

    Raises on degenerate input; the caller turns that into PH_NOT_COMPUTED.
    """
    from lifelines.statistics import TimeTransformers

    scaled = cph.compute_residuals(model_df, kind='scaled_schoenfeld')
    events = cph.event_observed
    n_deaths = float(events.sum())

    transformer = TimeTransformers().get(time_transform)
    times = transformer(cph.durations, events, cph.weights)[events.values]
    xx = times - times.mean()
    sum_xx2 = float((xx ** 2).sum())
    if sum_xx2 <= 0 or n_deaths <= 0:
        # e.g. every event happens at the same transformed time, so the statistic
        # is 0/0. Degenerate input, not a passing result.
        raise ValueError(
            f'degenerate time transform: sum of squared demeaned {time_transform} '
            f'times = {sum_xx2}, n_events = {n_deaths}. All events may share a '
            f'single event time on this time scale.')

    cols = list(scaled.columns)
    w = (xx.values[:, None] * scaled.values).sum(0)          # length p
    se = cph.standard_errors_.loc[cols].values

    t_var = w ** 2 / (n_deaths * (se ** 2) * sum_xx2)
    p_var = stats.chi2.sf(t_var, 1)

    v = cph.variance_matrix_.loc[cols, cols].values
    v_inv = np.linalg.pinv(v)
    q_global = float(w @ v_inv @ w / (n_deaths * sum_xx2))
    p_global = float(stats.chi2.sf(q_global, len(cols)))

    return {
        'time_transform': time_transform,
        'n_events': int(n_deaths),
        'global': {'chi2': q_global, 'df': len(cols), 'p': p_global},
        'per_variable': {col: {'chi2': float(t_var[j]), 'df': 1, 'p': float(p_var[j])}
                         for j, col in enumerate(cols)},
    }


def _band(p_gate, p_min_across_transforms):
    """(violated, borderline) for one statistic.

    `violated` is decided on the pre-specified gate transform alone. `borderline` is
    the 0.01–0.05 band on the most extreme of the review transforms — a departure
    that only shows up on one time scale still means we may not claim the assumption
    held. The two are mutually exclusive by construction.
    """
    violated = bool(p_gate < PH_ALPHA)
    borderline = bool(not violated and p_min_across_transforms < PH_ALPHA_REVIEW)
    return violated, borderline


def ph_assumption_test(fit, time_transform=PH_GATE_TRANSFORM):
    """
    Global + variable-level Schoenfeld test, evaluated on the gate transform and on
    every review transform.

    Always returns a dict carrying a `status` of PH_COMPUTED / PH_NOT_COMPUTED /
    PH_NOT_APPLICABLE. Never returns None: "we could not test it" is a finding that
    has to reach the gate, not an absence.
    """
    if not fit or fit.get('model') is None:
        # No fitted Cox model to test. The missing model is itself already blocking
        # upstream (convergence check), so this is not a second failure.
        return {'status': PH_NOT_APPLICABLE,
                'time_transform': time_transform,
                'alpha': PH_ALPHA,
                'alpha_review': PH_ALPHA_REVIEW,
                'reason': 'no fitted Cox model (the model failed to converge or was not run)'}

    cph = fit['model']
    model_df = fit['data']

    try:
        gate = _ph_statistics(cph, model_df, time_transform)
    except Exception as e:
        # Surface, never swallow: a PH test that crashed must not read as "PH is fine".
        # The model fitted, so the test was required — returning NOT_COMPUTED makes
        # ph_gate() block instead of shrugging.
        print(f"  [PH test] Error: {type(e).__name__}: {e}")
        return {'status': PH_NOT_COMPUTED,
                'time_transform': time_transform,
                'alpha': PH_ALPHA,
                'alpha_review': PH_ALPHA_REVIEW,
                'reason': f'{type(e).__name__}: {e}'}

    # Review transforms are best-effort: one of them failing must not take down a
    # gate result we already have. Failures are recorded, not swallowed.
    by_transform, transform_errors = {time_transform: gate}, {}
    for tt in PH_REVIEW_TRANSFORMS:
        if tt in by_transform:
            continue
        try:
            by_transform[tt] = _ph_statistics(cph, model_df, tt)
        except Exception as e:
            transform_errors[tt] = f'{type(e).__name__}: {e}'

    def _min_p(getter):
        return min(getter(s) for s in by_transform.values())

    g_violated, g_borderline = _band(gate['global']['p'],
                                     _min_p(lambda s: s['global']['p']))
    per_variable = {}
    for col, r in gate['per_variable'].items():
        p_by_tt = {tt: s['per_variable'][col]['p']
                   for tt, s in by_transform.items() if col in s['per_variable']}
        v, b = _band(r['p'], min(p_by_tt.values()))
        per_variable[col] = {
            'chi2': r['chi2'], 'df': r['df'], 'p': r['p'],
            'p_by_transform': p_by_tt,
            'min_p': min(p_by_tt.values()),
            'violated': v,
            'borderline': b,
        }

    violating = sorted(c for c, r in per_variable.items() if r['violated'])
    borderline_vars = sorted(c for c, r in per_variable.items() if r['borderline'])
    all_min_p = min([_min_p(lambda s: s['global']['p'])]
                    + [r['min_p'] for r in per_variable.values()])

    return {
        'status': PH_COMPUTED,
        'time_transform': time_transform,          # the gate transform
        'gate_transform': time_transform,
        'review_transforms': sorted(by_transform),
        'transform_errors': transform_errors,
        'alpha': PH_ALPHA,
        'alpha_review': PH_ALPHA_REVIEW,
        'n_events': gate['n_events'],
        'global': {
            'chi2': gate['global']['chi2'],
            'df': gate['global']['df'],
            'p': gate['global']['p'],
            'p_by_transform': {tt: s['global']['p'] for tt, s in by_transform.items()},
            'min_p': _min_p(lambda s: s['global']['p']),
            'violated': g_violated,
            'borderline': g_borderline,
        },
        'by_transform': by_transform,
        'per_variable': per_variable,
        'violating_variables': violating,
        'borderline_variables': borderline_vars,
        'min_p': all_min_p,
        'violated': bool(g_violated or violating),
        # Not blocking, but the run may not be described as "assumption held".
        'borderline': bool(not (g_violated or violating) and (g_borderline or borderline_vars)),
    }


def ph_split_hr(fit, exposure_col, split_time=None):
    """
    Landmark-style early/late hazard ratios for the exposure, as an EFFECT SIZE to
    put next to the p-value.

    A Schoenfeld p answers "is there evidence of non-proportionality", never "how
    much". In the borderline band that is exactly the wrong question to stop on, so
    the reviewer gets two numbers instead: the exposure HR before and after a split
    of follow-up. The late model is refitted on subjects still at risk at the split
    with the clock reset (a landmark analysis), so no left-truncation handling is
    needed and the two estimates are independent.

    The split point is data-driven (median event time), so this is a DIAGNOSTIC. It
    must not be reported in a manuscript as a pre-specified subgroup effect.
    """
    from lifelines import CoxPHFitter

    if not fit or fit.get('model') is None or not exposure_col:
        return None
    cph = fit['model']
    d = fit['data']
    time_col, event_col = cph.duration_col, cph.event_col
    if exposure_col not in d.columns:
        return None

    try:
        ev_times = d.loc[d[event_col] == 1, time_col]
        if len(ev_times) < 10:
            return {'available': False,
                    'reason': f'only {len(ev_times)} events; split HR would be noise'}
        cut = float(split_time) if split_time is not None else float(ev_times.median())

        out = {'available': True, 'variable': exposure_col, 'split_time': cut,
               'method': 'landmark split at median event time (data-driven cut point; '
                         'diagnostic only, not a pre-specified subgroup effect)'}

        # Early period: censor everything at the cut.
        early = d.copy()
        early[event_col] = np.where(early[time_col] <= cut, early[event_col], 0)
        early[time_col] = np.minimum(early[time_col], cut)
        # Late period: survivors past the cut, clock reset.
        late = d[d[time_col] > cut].copy()
        late[time_col] = late[time_col] - cut

        for label, frame in (('early', early), ('late', late)):
            n_ev = int(frame[event_col].sum())
            if len(frame) < 10 or n_ev < 5:
                out[f'hr_{label}'] = None
                out[f'hr_{label}_reason'] = f'n={len(frame)}, events={n_ev}: too few to fit'
                continue
            try:
                sub = CoxPHFitter().fit(frame, duration_col=time_col, event_col=event_col)
                s = sub.summary
                out[f'hr_{label}'] = float(np.exp(s.loc[exposure_col, 'coef']))
                out[f'hr_{label}_ci'] = [float(np.exp(s.loc[exposure_col, 'coef lower 95%'])),
                                         float(np.exp(s.loc[exposure_col, 'coef upper 95%']))]
                out[f'hr_{label}_p'] = float(s.loc[exposure_col, 'p'])
                out[f'n_events_{label}'] = n_ev
            except Exception as e:
                out[f'hr_{label}'] = None
                out[f'hr_{label}_reason'] = f'{type(e).__name__}: {e}'
        return out
    except Exception as e:
        print(f"  [PH split HR] Error: {type(e).__name__}: {e}")
        return {'available': False, 'reason': f'{type(e).__name__}: {e}'}


def plot_ph_diagnostics(fit, ph_result, out_path, time_transform='rank'):
    """
    Scaled Schoenfeld residuals vs transformed time, one panel per covariate,
    with a least-squares trend line. A flat line is consistent with proportional
    hazards; a systematic slope is the visual counterpart of a small p-value.
    Returns the written path, or None if plotting is unavailable.
    """
    if not fit or not ph_result or ph_result.get('status') != PH_COMPUTED:
        return None
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from lifelines.statistics import TimeTransformers

        cph = fit['model']
        scaled = cph.compute_residuals(fit['data'], kind='scaled_schoenfeld')
        events = cph.event_observed
        transformer = TimeTransformers().get(time_transform)
        times = transformer(cph.durations, events, cph.weights)[events.values]

        cols = list(scaled.columns)
        ncol = min(3, len(cols))
        nrow = int(np.ceil(len(cols) / ncol))
        fig, axes = plt.subplots(nrow, ncol, figsize=(4.2 * ncol, 3.2 * nrow), squeeze=False)

        for idx, col in enumerate(cols):
            ax = axes[idx // ncol][idx % ncol]
            y = scaled[col].values
            ax.scatter(times, y, s=8, alpha=0.4, color='#4C72B0')
            if len(times) > 2:
                slope, intercept = np.polyfit(times, y, 1)
                xs = np.linspace(float(np.min(times)), float(np.max(times)), 50)
                ax.plot(xs, slope * xs + intercept, color='#C44E52', lw=1.5)
            ax.axhline(0, color='grey', lw=0.8, ls='--')
            pv = ph_result['per_variable'].get(col, {})
            p = pv.get('p')
            flag = ' *' if pv.get('violated') else (' [borderline]' if pv.get('borderline') else '')
            ax.set_title(f"{col}  (Schoenfeld p={p:.3f}{flag})" if p is not None else col, fontsize=9)
            ax.set_xlabel(f"{time_transform}-transformed time", fontsize=8)
            ax.set_ylabel("scaled Schoenfeld residual", fontsize=8)
            ax.tick_params(labelsize=7)

        for idx in range(len(cols), nrow * ncol):
            axes[idx // ncol][idx % ncol].axis('off')

        g = ph_result['global']
        band = ''
        if ph_result.get('borderline'):
            band = (f"  |  BORDERLINE: min p across "
                    f"{'/'.join(ph_result.get('review_transforms', []))} = "
                    f"{ph_result.get('min_p', float('nan')):.3f} "
                    f"(in {PH_ALPHA}–{PH_ALPHA_REVIEW})")
        fig.suptitle(
            f"Proportional hazards diagnostics — global chi2={g['chi2']:.2f}, "
            f"df={g['df']}, p={g['p']:.4f} (gate p<{PH_ALPHA}, {time_transform} transform){band}",
            fontsize=10,
        )
        fig.tight_layout(rect=(0, 0, 1, 0.96))
        fig.savefig(out_path, dpi=300)
        plt.close(fig)
        return out_path
    except Exception as e:
        print(f"  [PH plot] Error: {type(e).__name__}: {e}")
        return None


def ph_gate(ph_result, config):
    """
    Decide what the PH result means for the pipeline.

    Returns (blocking_messages, warning_messages). Two rules:

    1. The test was required but could not be produced (status NOT_COMPUTED) →
       BLOCKING. An un-computable PH test is not a passing PH test, and nothing
       downstream is guaranteed to notice the missing artifact (`quick` profile
       has no Results Auditor).
    2. A detected violation with no pre-specified `ph_violation_remedy` is BLOCKING
       — per research-plan P2-3, "we detected it" is not a response. A pre-specified
       remedy downgrades it to a warning, because the author declared the handling
       before seeing the result.
    """
    blocking, warnings_ = [], []
    if not ph_result:
        # Should not happen: ph_assumption_test always returns a status dict. If a
        # caller passed None for a Cox model, fail closed rather than fall through.
        blocking.append(
            "Proportional hazards result is missing entirely for a Cox model — "
            "treating as not tested. This is a wiring bug; do not override."
        )
        return blocking, warnings_

    status = ph_result.get('status')
    if status == PH_NOT_COMPUTED:
        blocking.append(
            f"Proportional hazards test could not be computed for a fitted Cox model: "
            f"{ph_result.get('reason', 'no reason recorded')}. An un-computable PH test "
            f"is not a passing PH test — fix the input (check for degenerate event "
            f"times, collinearity, or zero-variance covariates) or move this outcome to "
            f"an analysis that does not assume proportional hazards."
        )
        return blocking, warnings_
    if status == PH_NOT_APPLICABLE:
        warnings_.append(
            f"Proportional hazards not tested: {ph_result.get('reason', 'not applicable')}."
        )
        return blocking, warnings_

    remedy = config.get('ph_violation_remedy')
    if remedy is not None and remedy not in PH_REMEDIES:
        blocking.append(
            f"ph_violation_remedy='{remedy}' is not one of {list(PH_REMEDIES)}"
        )
        remedy = None

    if not ph_result['violated']:
        # Borderline band: not blocking (precision is poor here), but it must not be
        # silent either. run_pipeline's extract_qc_warnings() picks this up into
        # step.qc_warnings[] -> manifest.methodological_warnings, which is what puts
        # it in front of reviewer-challenge domain 5. The TTM lesson was an empty
        # methodological_warnings list, so silence here is the failure mode.
        if ph_result.get('borderline'):
            where = ', '.join(ph_result.get('borderline_variables') or []) or 'global test'
            split = ph_result.get('effect_size') or {}
            eff = ''
            if split.get('available') and split.get('hr_early') and split.get('hr_late'):
                eff = (f" Early/late split for {split['variable']} at t={split['split_time']:.3g}: "
                       f"HR {split['hr_early']:.2f} -> {split['hr_late']:.2f} "
                       f"(data-driven cut, diagnostic only).")
            warnings_.append(
                f"PH borderline (min p={ph_result.get('min_p', float('nan')):.3f} across "
                f"{'/'.join(ph_result.get('review_transforms', []))} transforms, in "
                f"{PH_ALPHA}-{PH_ALPHA_REVIEW}; {where}); not blocking, but must appear in "
                f"methodological_warnings and be reviewed against the *_ph_diagnostics.png "
                f"plot. Do NOT describe this model as satisfying proportional hazards.{eff}"
            )
        return blocking, warnings_

    g = ph_result['global']
    detail = (f"global chi2={g['chi2']:.2f} (df={g['df']}, p={g['p']:.4g}); "
              f"violating covariates: {', '.join(ph_result['violating_variables']) or 'none individually'}")

    if remedy is None:
        blocking.append(
            f"Proportional hazards assumption violated at p<{PH_ALPHA} and no "
            f"`ph_violation_remedy` was declared in the plan — {detail}. Set "
            f"ph_violation_remedy to one of {list(PH_REMEDIES)} in research_plan.json "
            f"and re-run; detection alone is not a remedy."
        )
    elif remedy == 'disclose':
        warnings_.append(
            f"PH violated ({detail}); declared remedy='disclose' — the adjusted HRs are "
            f"averaged over follow-up and this must be stated in Limitations against a "
            f"decision-log ID (`ph_disclose_decision_id`); the manuscript-stage artifact "
            f"gate blocks if that ID is missing."
        )
    else:
        need_step = (' There is no shipped step generator for this remedy — it has to '
                     'be a hand-built step.') \
            if remedy in PH_REMEDIES_NEEDING_OWN_STEP else \
            (f" In a /research-plan pipeline the '{remedy}' step is added for you "
             f"(generate_configs._REMEDY_STEPS) and writes its own table; this "
             f"workbook is deliberately left unremediated so its two sheets stay "
             f"fitted under the same assumptions.")
        warnings_.append(
            f"PH violated ({detail}); declared remedy='{remedy}' is NOT executed by this "
            f"skill — the Sheet 1 HRs are unremediated and must not be presented as the "
            f"primary estimate until the '{remedy}' analysis has been run as its own step. "
            f"The manuscript-stage artifact gate blocks if that step's output does not "
            f"exist.{need_step}"
        )
    return blocking, warnings_


# ═══════════════════════════════════════════════════════════════════════════════
# Interaction Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def _delta_subgroup_hr(params, cov, grp_term, int_term, x, z=1.96):
    """
    Delta-method subgroup HR/OR at subgroup_var = x from a single interaction model.

    log(effect | subgroup_var = x) = beta_grp + beta_int * x
    Var(log effect) = Var(beta_grp) + x^2 * Var(beta_int) + 2x * Cov(beta_grp, beta_int)

    Returns (effect, ci_lower, ci_upper, p_wald).
    """
    from scipy.stats import norm

    beta_grp = float(params[grp_term])
    beta_int = float(params[int_term])
    var_grp = float(cov.loc[grp_term, grp_term])
    var_int = float(cov.loc[int_term, int_term])
    cov_gi = float(cov.loc[grp_term, int_term])

    log_eff = beta_grp + beta_int * x
    var_log = var_grp + (x ** 2) * var_int + 2.0 * x * cov_gi
    if var_log <= 0 or not np.isfinite(var_log):
        return None, None, None, None
    se = float(np.sqrt(var_log))
    eff = float(np.exp(log_eff))
    ci_low = float(np.exp(log_eff - z * se))
    ci_high = float(np.exp(log_eff + z * se))
    # Wald p-value for H0: log_eff = 0 (subgroup effect = 1)
    p = float(2.0 * (1.0 - norm.cdf(abs(log_eff / se))))
    return eff, ci_low, ci_high, p


def _fit_cox_interaction_model(df, var_cols, grp_col, target_col, int_term_name,
                               time_col, event_col):
    """Fit Cox model with grp + target + grp:target (interaction) + other covariates."""
    from lifelines import CoxPHFitter

    cols_needed = list(set(var_cols + [grp_col, target_col, int_term_name,
                                       time_col, event_col]))
    cols_needed = [c for c in cols_needed if c in df.columns]
    d = df[cols_needed].dropna().copy()

    if len(d) < 10 or d[event_col].sum() < 5:
        return None, d

    model_cols = [c for c in cols_needed if c not in (time_col, event_col)]
    # Drop zero-variance non-interaction columns; fail if interaction itself is degenerate
    for c in list(model_cols):
        if d[c].nunique() < 2:
            if c == int_term_name or c == grp_col or c == target_col:
                return None, d
            d = d.drop(columns=[c])
            model_cols = [x for x in model_cols if x != c]

    try:
        cph = CoxPHFitter()
        cph.fit(d, duration_col=time_col, event_col=event_col)
        return cph, d
    except Exception as e:
        print(f"  [Cox Interaction Model] Error fitting {target_col}: {e}")
        return None, d


def _fit_logit_interaction_model(df, var_cols, grp_col, target_col, int_term_name,
                                 outcome_col):
    """Fit logistic model with grp + target + grp:target + other covariates."""
    import statsmodels.api as sm

    cols_needed = list(set(var_cols + [grp_col, target_col, int_term_name,
                                       outcome_col]))
    cols_needed = [c for c in cols_needed if c in df.columns]
    d = df[cols_needed].dropna().copy()

    if len(d) < 10 or d[outcome_col].sum() < 5:
        return None, d

    model_cols = [c for c in cols_needed if c != outcome_col]
    for c in list(model_cols):
        if d[c].nunique() < 2:
            if c == int_term_name or c == grp_col or c == target_col:
                return None, d
            d = d.drop(columns=[c])
            model_cols = [x for x in model_cols if x != c]

    try:
        X = sm.add_constant(d[model_cols])
        model = sm.Logit(d[outcome_col], X).fit(disp=0, method='bfgs', maxiter=200)
        return model, d
    except Exception as e:
        print(f"  [Logit Interaction Model] Error fitting {target_col}: {e}")
        return None, d


def run_interaction(df_clean, grp1, grp2, config):
    """
    Run interaction analysis using a SINGLE interaction model per covariate
    and compute subgroup-specific HR/OR via delta-method contrast from that
    model's coefficient covariance matrix.

    For each test variable X:
      formula = grp + X + grp:X + (other covariates)
      fit once on df_clean; then for each subgroup level of X:
          log HR(x) = beta_grp + beta_int * x
          Var(log HR(x)) = V_gg + x^2 * V_ii + 2x * V_gi
      p-interaction = Wald p of beta_int.

    Continuous X: reported at x = 0 and x = 1 SD (post-centering) — i.e. the
    group effect at the mean of X and at mean + 1 SD of X. Centering is
    mean-centering (can be disabled per-variable via 'center': false).

    Categorical X: expanded via pd.get_dummies with the user-specified
    reference_level dropped. Each non-reference dummy yields its own row.
    """
    analysis_type = config['analysis_type']
    grp_col = config['grouping']['column']

    # Determine which variables to test for interaction
    interaction_vars = config.get('interaction_variables', 'all')

    # Collect all variable info
    all_vars = []
    scale_map = {}
    for section in config['sections']:
        for var in section['variables']:
            all_vars.append({
                'label': var['label'],
                'column': var['column'],
                'type': var.get('type', 'binary'),
                'section': section['header'],
                'scale': var.get('scale'),
                'scale_label': var.get('scale_label', ''),
                'center': var.get('center', True),
                'reference_level': var.get('reference_level', None),
            })
            if var.get('scale'):
                scale_map[var['column']] = var['scale']

    # Filter to interaction variables
    if interaction_vars == 'all':
        test_vars = all_vars
    else:
        test_vars = [v for v in all_vars if v['column'] in interaction_vars]

    # Apply scaling on the overall df (single model fit only uses df_clean)
    df_scaled = df_clean.copy()
    grp1_scaled = grp1.copy()
    grp2_scaled = grp2.copy()
    for col, scale in scale_map.items():
        for d in [df_scaled, grp1_scaled, grp2_scaled]:
            if col in d.columns:
                d[col] = d[col] / scale

    # Mean-center continuous test variables (so grp main effect is interpretable
    # at the mean of X). Original scaled column is overwritten; centering is
    # applied identically across subgroup dataframes for consistency.
    for v in test_vars:
        if v['type'] == 'continuous' and v.get('center', True):
            col = v['column']
            if col in df_scaled.columns:
                mu = df_scaled[col].mean()
                df_scaled[col] = df_scaled[col] - mu
                if col in grp1_scaled.columns:
                    grp1_scaled[col] = grp1_scaled[col] - mu
                if col in grp2_scaled.columns:
                    grp2_scaled[col] = grp2_scaled[col] - mu

    # Other adjustment covariates = all all_vars EXCEPT the current test variable
    # (rebuilt per iteration below). We exclude grp_col since it's added explicitly.
    all_test_cols = [v['column'] for v in all_vars]

    # Outcome columns
    if analysis_type == 'cox':
        cs = config['cox_settings']
        time_col = cs['time_column']
        event_col = cs['event_column']
    else:
        outcome_col = config['logistic_settings']['outcome_column']

    interaction_results = []
    failed = []

    # Determine subgroup sizes once (used for display; per-subgroup refit is gone)
    for tv in test_vars:
        target_col = tv['column']
        label = tv['label']
        var_type = tv['type']
        print(f"  Interaction: {label}...")

        # Skip self as grouping column
        if target_col == grp_col:
            continue

        # Categorical handling: expand dummies with user-specified reference
        if var_type == 'categorical':
            ref_level = tv.get('reference_level')
            if ref_level is None:
                print(f"  [Warning] Categorical variable '{target_col}' has no "
                      f"reference_level specified; using pandas default (first level).",
                      file=sys.stderr)

            # Build model dataframe with dummies for target_col
            df_model = df_scaled.copy()
            # Cast to categorical with ref first so get_dummies(drop_first=True) drops ref
            levels = list(pd.Categorical(df_model[target_col].dropna()).categories)
            if ref_level is not None and ref_level in levels:
                ordered = [ref_level] + [lv for lv in levels if lv != ref_level]
                df_model[target_col] = pd.Categorical(df_model[target_col],
                                                      categories=ordered, ordered=False)
            dummies = pd.get_dummies(df_model[target_col], prefix=target_col,
                                     drop_first=True).astype(float)
            if dummies.shape[1] == 0:
                failed.append(f"{label} (no non-reference levels)")
                continue

            # Other adjustment covariates = all_test_cols minus target_col
            other_cols = [c for c in all_test_cols if c != target_col]

            # One row per non-reference dummy
            for dummy_name in dummies.columns:
                d_fit = df_model.copy()
                d_fit[dummy_name] = dummies[dummy_name].values
                int_name = f'_int_{grp_col}_{dummy_name}'
                d_fit[int_name] = d_fit[grp_col] * d_fit[dummy_name]

                model_vars = other_cols + [dummy_name]

                level_label = dummy_name.replace(f"{target_col}_", "")
                row_label = f"{label}: {level_label}"
                result = {
                    'label': row_label,
                    'column': dummy_name,
                    'section': tv['section'],
                    'scale_label': tv.get('scale_label', ''),
                }

                if analysis_type == 'cox':
                    model, d_used = _fit_cox_interaction_model(
                        d_fit, model_vars, grp_col, dummy_name, int_name,
                        time_col, event_col)
                    if model is None:
                        result.update({
                            'g1_n': len(d_used), 'g1_events': 0,
                            'g2_n': 0, 'g2_events': 0,
                            'g1_effect': None, 'g1_ci_lower': None,
                            'g1_ci_upper': None, 'g1_p': None,
                            'g2_effect': None, 'g2_ci_lower': None,
                            'g2_ci_upper': None, 'g2_p': None,
                            'p_interaction': None,
                        })
                        failed.append(row_label)
                        interaction_results.append(result)
                        continue
                    params = model.params_
                    covm = model.variance_matrix_
                    p_int = float(model.summary.loc[int_name, 'p']) if int_name in model.summary.index else None
                    # N/events per subgroup stratum in the fitted dataset
                    g1_mask = d_used[grp_col] == config['grouping']['groups'][0]['value']
                    g2_mask = d_used[grp_col] == config['grouping']['groups'][1]['value']
                    n_g1 = int(g1_mask.sum())
                    n_g2 = int(g2_mask.sum())
                    ev_g1 = int(d_used.loc[g1_mask, event_col].sum())
                    ev_g2 = int(d_used.loc[g2_mask, event_col].sum())
                else:
                    model, d_used = _fit_logit_interaction_model(
                        d_fit, model_vars, grp_col, dummy_name, int_name, outcome_col)
                    if model is None:
                        result.update({
                            'g1_n': len(d_used), 'g1_events': 0,
                            'g2_n': 0, 'g2_events': 0,
                            'g1_effect': None, 'g1_ci_lower': None,
                            'g1_ci_upper': None, 'g1_p': None,
                            'g2_effect': None, 'g2_ci_lower': None,
                            'g2_ci_upper': None, 'g2_p': None,
                            'p_interaction': None,
                        })
                        failed.append(row_label)
                        interaction_results.append(result)
                        continue
                    params = model.params
                    covm = model.cov_params()
                    p_int = float(model.pvalues[int_name]) if int_name in model.pvalues.index else None
                    g1_mask = d_used[grp_col] == config['grouping']['groups'][0]['value']
                    g2_mask = d_used[grp_col] == config['grouping']['groups'][1]['value']
                    n_g1 = int(g1_mask.sum())
                    n_g2 = int(g2_mask.sum())
                    ev_g1 = int(d_used.loc[g1_mask, outcome_col].sum())
                    ev_g2 = int(d_used.loc[g2_mask, outcome_col].sum())

                # Group effect within each level of this categorical dummy
                # (delta method): g1 column = reference level (dummy=0),
                # g2 column = this non-reference level (dummy=1). N(events) are the
                # covariate-subgroup counts, not the grouping arms.
                _oc = event_col if analysis_type == 'cox' else outcome_col
                s0 = d_used[dummy_name] == 0
                s1 = d_used[dummy_name] == 1
                eff1, ci1l, ci1u, p1 = _delta_subgroup_hr(
                    params, covm, grp_col, int_name, x=1.0)
                eff0, ci0l, ci0u, p0 = _delta_subgroup_hr(
                    params, covm, grp_col, int_name, x=0.0)

                result.update({
                    'g1_sub': 'reference', 'g2_sub': level_label,
                    'g1_n': int(s0.sum()), 'g1_events': int(d_used.loc[s0, _oc].sum()),
                    'g2_n': int(s1.sum()), 'g2_events': int(d_used.loc[s1, _oc].sum()),
                    # g1 column = subgroup with dummy=0 (reference level of this categorical)
                    'g1_effect': eff0, 'g1_ci_lower': ci0l,
                    'g1_ci_upper': ci0u, 'g1_p': p0,
                    # g2 column = subgroup with dummy=1 (non-reference level)
                    'g2_effect': eff1, 'g2_ci_lower': ci1l,
                    'g2_ci_upper': ci1u, 'g2_p': p1,
                    'p_interaction': p_int,
                })
                interaction_results.append(result)

            continue  # next test variable

        # Binary / continuous handling: single dummy column = target_col itself
        int_name = f'_int_{grp_col}_{target_col}'
        d_fit = df_scaled.copy()
        d_fit[int_name] = d_fit[grp_col] * d_fit[target_col]

        other_cols = [c for c in all_test_cols if c != target_col]
        model_vars = other_cols + [target_col]

        result = {
            'label': label,
            'column': target_col,
            'section': tv['section'],
            'scale_label': tv.get('scale_label', ''),
        }

        if analysis_type == 'cox':
            model, d_used = _fit_cox_interaction_model(
                d_fit, model_vars, grp_col, target_col, int_name,
                time_col, event_col)
            if model is None:
                result.update({
                    'g1_n': len(d_used), 'g1_events': 0,
                    'g2_n': 0, 'g2_events': 0,
                    'g1_effect': None, 'g1_ci_lower': None,
                    'g1_ci_upper': None, 'g1_p': None,
                    'g2_effect': None, 'g2_ci_lower': None,
                    'g2_ci_upper': None, 'g2_p': None,
                    'p_interaction': None,
                })
                failed.append(label)
                interaction_results.append(result)
                continue
            params = model.params_
            covm = model.variance_matrix_
            p_int = float(model.summary.loc[int_name, 'p']) if int_name in model.summary.index else None
            g1_mask = d_used[grp_col] == config['grouping']['groups'][0]['value']
            g2_mask = d_used[grp_col] == config['grouping']['groups'][1]['value']
            n_g1 = int(g1_mask.sum())
            n_g2 = int(g2_mask.sum())
            ev_g1 = int(d_used.loc[g1_mask, event_col].sum())
            ev_g2 = int(d_used.loc[g2_mask, event_col].sum())
        else:
            model, d_used = _fit_logit_interaction_model(
                d_fit, model_vars, grp_col, target_col, int_name, outcome_col)
            if model is None:
                result.update({
                    'g1_n': len(d_used), 'g1_events': 0,
                    'g2_n': 0, 'g2_events': 0,
                    'g1_effect': None, 'g1_ci_lower': None,
                    'g1_ci_upper': None, 'g1_p': None,
                    'g2_effect': None, 'g2_ci_lower': None,
                    'g2_ci_upper': None, 'g2_p': None,
                    'p_interaction': None,
                })
                failed.append(label)
                interaction_results.append(result)
                continue
            params = model.params
            covm = model.cov_params()
            p_int = float(model.pvalues[int_name]) if int_name in model.pvalues.index else None
            g1_mask = d_used[grp_col] == config['grouping']['groups'][0]['value']
            g2_mask = d_used[grp_col] == config['grouping']['groups'][1]['value']
            n_g1 = int(g1_mask.sum())
            n_g2 = int(g2_mask.sum())
            ev_g1 = int(d_used.loc[g1_mask, outcome_col].sum())
            ev_g2 = int(d_used.loc[g2_mask, outcome_col].sum())

        # Outcome column actually used downstream (cox -> event, logit -> outcome).
        _oc = event_col if analysis_type == 'cox' else outcome_col

        if var_type == 'binary':
            # Binary X: group effect within the X=0 and X=1 subgroups (delta method).
            # The two columns are the COVARIATE's subgroups, so N(events) are the
            # covariate-subgroup counts — NOT the grouping arms.
            s0 = d_used[target_col] == 0
            s1 = d_used[target_col] == 1
            eff0, ci0l, ci0u, p0 = _delta_subgroup_hr(params, covm, grp_col, int_name, x=0.0)
            eff1, ci1l, ci1u, p1 = _delta_subgroup_hr(params, covm, grp_col, int_name, x=1.0)
            result.update({
                'g1_sub': f"{label} = 0", 'g2_sub': f"{label} = 1",
                'g1_n': int(s0.sum()), 'g1_events': int(d_used.loc[s0, _oc].sum()),
                'g2_n': int(s1.sum()), 'g2_events': int(d_used.loc[s1, _oc].sum()),
                'g1_effect': eff0, 'g1_ci_lower': ci0l,
                'g1_ci_upper': ci0u, 'g1_p': p0,
                'g2_effect': eff1, 'g2_ci_lower': ci1l,
                'g2_ci_upper': ci1u, 'g2_p': p1,
                'p_interaction': p_int,
            })
        else:
            # Continuous X: group effect at the mean (x=0 after centering) and at
            # mean + 1 SD. These are evaluation points, not discrete subgroups, so
            # there is no per-subgroup N(events).
            sd = float(d_used[target_col].std()) if target_col in d_used.columns else 1.0
            eff_mean, ci_ml, ci_mu, p_mean = _delta_subgroup_hr(
                params, covm, grp_col, int_name, x=0.0)
            eff_sd, ci_sl, ci_su, p_sd = _delta_subgroup_hr(
                params, covm, grp_col, int_name, x=sd)
            result.update({
                'g1_sub': 'at mean', 'g2_sub': 'at mean + 1 SD',
                'g1_n': None, 'g1_events': None,
                'g2_n': None, 'g2_events': None,
                'g1_effect': eff_mean, 'g1_ci_lower': ci_ml,
                'g1_ci_upper': ci_mu, 'g1_p': p_mean,
                'g2_effect': eff_sd, 'g2_ci_lower': ci_sl,
                'g2_ci_upper': ci_su, 'g2_p': p_sd,
                'p_interaction': p_int,
            })
        interaction_results.append(result)

    return interaction_results, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Formatting Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_p(p):
    """Format p-value."""
    if p is None:
        return "N/A"
    if p < 0.001:
        return "<0.001*"
    elif p < 0.05:
        return f"{p:.3f}*"
    else:
        return f"{p:.3f}"


def fmt_effect(effect, ci_l, ci_u):
    """Format HR/OR with 95% CI."""
    if effect is None:
        return "N/A"
    return f"{effect:.2f} ({ci_l:.2f}\u2013{ci_u:.2f})"


def fmt_n_events(n, events):
    """Format N (events)."""
    if n is None:
        return "N/A"
    return f"{n} ({events})"


def fmt_coef(coef):
    """Format coefficient."""
    if coef is None:
        return "N/A"
    return f"{coef:.4f}"


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
GRP1_HEADER = "1A5276"
GRP2_HEADER = "1E8449"
GRP1_BG = "EBF5FB"
GRP1_ALT = "D6EAF8"
GRP2_BG = "EAFAF1"
GRP2_ALT = "D5F5E3"

THIN_BORDER = Border(
    left=Side(style='thin', color=BORDER_COLOR),
    right=Side(style='thin', color=BORDER_COLOR),
    top=Side(style='thin', color=BORDER_COLOR),
    bottom=Side(style='thin', color=BORDER_COLOR),
)


def write_excel(mv_results, mv_n, mv_events, interaction_results, config, df_clean, ph_result=None):
    """Write formatted Excel output with 2 sheets."""
    analysis_type = config['analysis_type']
    effect_label = "HR" if analysis_type == 'cox' else "OR"
    g1_label = config['grouping']['groups'][0]['label']
    g2_label = config['grouping']['groups'][1]['label']
    output_path = config['output_file']
    abbreviations = config.get('abbreviations', '')

    # Common styles
    title_font = Font(name='Arial', size=12, bold=True, color="FFFFFF")
    title_fill = PatternFill(start_color=DARK_BLUE, end_color=DARK_BLUE, fill_type='solid')
    subtitle_font = Font(name='Arial', size=10, italic=True, color="FFFFFF")

    header_font = Font(name='Arial', size=10, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color=HEADER_BG, end_color=HEADER_BG, fill_type='solid')
    g1_header_fill = PatternFill(start_color=GRP1_HEADER, end_color=GRP1_HEADER, fill_type='solid')
    g2_header_fill = PatternFill(start_color=GRP2_HEADER, end_color=GRP2_HEADER, fill_type='solid')

    section_font = Font(name='Arial', size=10, bold=True, color=DARK_BLUE)
    section_fill = PatternFill(start_color=SECTION_BG, end_color=SECTION_BG, fill_type='solid')

    data_font = Font(name='Arial', size=10)
    alt_fill = PatternFill(start_color=ALT_ROW, end_color=ALT_ROW, fill_type='solid')
    no_fill = PatternFill(fill_type=None)

    sig_font = Font(name='Arial', size=10, bold=True, color=SIG_COLOR)
    footnote_font = Font(name='Arial', size=8, italic=True, color=FOOTNOTE_COLOR)

    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    left = Alignment(horizontal='left', vertical='center', indent=1)

    wb = Workbook()

    # ── Sheet 1: Multivariate Analysis ──────────────────────────────────────
    ws1 = wb.active
    ws1.title = "Multivariate Analysis"

    # Column widths: Variable | Coefficient | Adj HR/OR (95% CI) | p-value
    total_cols_s1 = 4
    for c, w in zip(range(1, total_cols_s1 + 1), [32, 14, 26, 12]):
        ws1.column_dimensions[get_column_letter(c)].width = w

    row_idx = 1

    # Title
    ws1.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s1)
    cell = ws1.cell(row=row_idx, column=1, value=config.get('title', f'Multivariate {effect_label} Analysis'))
    cell.font = title_font; cell.fill = title_fill; cell.alignment = center
    for c in range(1, total_cols_s1 + 1):
        ws1.cell(row=row_idx, column=c).fill = title_fill
    row_idx += 1

    # Subtitle
    if analysis_type == 'cox':
        sub_text = f"n = {mv_n}, events = {mv_events}"
    else:
        sub_text = f"n = {mv_n}, events = {mv_events}"
    subtitle = config.get('subtitle', '')
    if subtitle:
        sub_text = f"{subtitle}  |  {sub_text}"
    ws1.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s1)
    cell = ws1.cell(row=row_idx, column=1, value=sub_text)
    cell.font = subtitle_font; cell.fill = title_fill; cell.alignment = center
    for c in range(1, total_cols_s1 + 1):
        ws1.cell(row=row_idx, column=c).fill = title_fill
    row_idx += 1

    # Headers
    headers_s1 = ["Variable", "Coefficient", f"Adjusted {effect_label} (95% CI)", "p-value"]
    for c, h in enumerate(headers_s1, 1):
        cell = ws1.cell(row=row_idx, column=c, value=h)
        cell.font = header_font; cell.fill = header_fill; cell.alignment = center; cell.border = THIN_BORDER
    row_idx += 1
    ws1.freeze_panes = ws1.cell(row=row_idx, column=1)

    # Data rows
    current_section = None
    data_row_idx = 0

    # Write grp_col (exposure main effect) first, as its own "Exposure" section.
    # run_multivariate injects grp_col into the model but it is not in config['sections'].
    grp_col = config['grouping']['column']
    if mv_results and grp_col in mv_results:
        current_section = "Exposure"
        ws1.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s1)
        cell = ws1.cell(row=row_idx, column=1, value=current_section)
        cell.font = section_font; cell.fill = section_fill; cell.alignment = left
        for c in range(1, total_cols_s1 + 1):
            ws1.cell(row=row_idx, column=c).fill = section_fill
            ws1.cell(row=row_idx, column=c).border = THIN_BORDER
        row_idx += 1

        r = mv_results[grp_col]
        is_sig = r['p'] < 0.05
        font = sig_font if is_sig else data_font
        exp_label = f"{g2_label} vs {g1_label}"
        cell = ws1.cell(row=row_idx, column=1, value=exp_label)
        cell.font = data_font; cell.fill = no_fill; cell.alignment = left; cell.border = THIN_BORDER
        cell = ws1.cell(row=row_idx, column=2, value=fmt_coef(r['coef']))
        cell.font = font; cell.fill = no_fill; cell.alignment = center; cell.border = THIN_BORDER
        cell = ws1.cell(row=row_idx, column=3, value=fmt_effect(r['effect'], r['ci_lower'], r['ci_upper']))
        cell.font = font; cell.fill = no_fill; cell.alignment = center; cell.border = THIN_BORDER
        cell = ws1.cell(row=row_idx, column=4, value=fmt_p(r['p']))
        cell.font = font; cell.fill = no_fill; cell.alignment = center; cell.border = THIN_BORDER
        row_idx += 1
        data_row_idx = 0

    for section in config['sections']:
        for var in section['variables']:
            # Section header
            if section['header'] != current_section:
                current_section = section['header']
                ws1.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s1)
                cell = ws1.cell(row=row_idx, column=1, value=current_section)
                cell.font = section_font; cell.fill = section_fill; cell.alignment = left
                for c in range(1, total_cols_s1 + 1):
                    ws1.cell(row=row_idx, column=c).fill = section_fill
                    ws1.cell(row=row_idx, column=c).border = THIN_BORDER
                row_idx += 1
                data_row_idx = 0

            row_fill = alt_fill if data_row_idx % 2 == 1 else no_fill
            col_name = var['column']

            # Variable label
            display_label = var['label']
            cell = ws1.cell(row=row_idx, column=1, value=display_label)
            cell.font = data_font; cell.fill = row_fill; cell.alignment = left; cell.border = THIN_BORDER

            if mv_results and col_name in mv_results:
                r = mv_results[col_name]
                is_sig = r['p'] < 0.05
                font = sig_font if is_sig else data_font

                # Coefficient
                cell = ws1.cell(row=row_idx, column=2, value=fmt_coef(r['coef']))
                cell.font = font; cell.fill = row_fill; cell.alignment = center; cell.border = THIN_BORDER

                # HR/OR (95% CI)
                cell = ws1.cell(row=row_idx, column=3, value=fmt_effect(r['effect'], r['ci_lower'], r['ci_upper']))
                cell.font = font; cell.fill = row_fill; cell.alignment = center; cell.border = THIN_BORDER

                # p-value
                cell = ws1.cell(row=row_idx, column=4, value=fmt_p(r['p']))
                cell.font = font; cell.fill = row_fill; cell.alignment = center; cell.border = THIN_BORDER
            else:
                for c in range(2, total_cols_s1 + 1):
                    cell = ws1.cell(row=row_idx, column=c, value="N/A")
                    cell.font = data_font; cell.fill = row_fill; cell.alignment = center; cell.border = THIN_BORDER

            row_idx += 1
            data_row_idx += 1

    # Footnotes
    row_idx += 1
    if abbreviations:
        ws1.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s1)
        cell = ws1.cell(row=row_idx, column=1, value=abbreviations)
        cell.font = footnote_font; cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws1.row_dimensions[row_idx].height = 30
        row_idx += 1

    note = (f"* p < 0.05  |  {effect_label} = {'hazard ratio' if analysis_type == 'cox' else 'odds ratio'}; "
            f"CI = confidence interval  |  "
            f"All variables entered simultaneously in a single {'Cox proportional hazards' if analysis_type == 'cox' else 'logistic regression'} model")
    ws1.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s1)
    cell = ws1.cell(row=row_idx, column=1, value=note)
    cell.font = footnote_font; cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    ws1.row_dimensions[row_idx].height = 30

    # PH footnote: the reviewer question is "was PH tested, and what was done about
    # a violation" — both halves have to travel with the table itself.
    if ph_result:
        row_idx += 1
        if ph_result.get('status') == PH_COMPUTED:
            g = ph_result['global']
            bad = ph_result['violating_variables']
            # Wording rule (2026-08-12 adjudication, dispute 4): a p in 0.01-0.05 is
            # a test that did not clear OUR threshold, not evidence the assumption
            # held. The old sentence "No individual covariate violated the
            # assumption" put a reassurance next to a real p=0.034 departure, which
            # is the statistical-significance wording failure in reverse.
            if bad:
                verdict = f"Covariates with evidence against proportionality: {', '.join(bad)}. "
            else:
                verdict = (f"No covariate crossed alpha = {ph_result['alpha']}; minimum "
                           f"Schoenfeld p = {ph_result.get('min_p', float('nan')):.3f}")
                if ph_result.get('borderline'):
                    verdict += (f" (borderline {ph_result['alpha']}-{ph_result['alpha_review']}, "
                                f"see diagnostics plot; the assumption is NOT established). ")
                else:
                    verdict += ". "
            if ph_result['violated'] and config.get('ph_violation_remedy'):
                # "Declared", not "pre-specified": this script cannot see history and
                # must not vouch for a chronology it has no way to verify.
                remedy_txt = (f"Declared remedy: {config.get('ph_violation_remedy')} "
                              f"(provenance: research_plan.json; see decision log).")
            elif ph_result['violated']:
                remedy_txt = "No remedy declared."
            else:
                remedy_txt = ""
            split = ph_result.get('effect_size') or {}
            eff_txt = ""
            if split.get('available') and split.get('hr_early') and split.get('hr_late'):
                eff_txt = (f" Diagnostic early/late split for {split['variable']} at "
                           f"t = {split['split_time']:.3g}: HR {split['hr_early']:.2f} vs "
                           f"{split['hr_late']:.2f} (data-driven cut point; diagnostic only, "
                           f"not a pre-specified subgroup effect).")
            ph_note = (
                f"Proportional hazards (scaled Schoenfeld residuals, gate on "
                f"{ph_result['time_transform']} transform, reviewed on "
                f"{'/'.join(ph_result.get('review_transforms', []))}): global chi2 = "
                f"{g['chi2']:.2f}, df = {g['df']}, p = {g['p']:.4f}; gate alpha = "
                f"{ph_result['alpha']}, review band up to {ph_result['alpha_review']}. "
                + verdict + remedy_txt + eff_txt
            )
        else:
            # Never let a failed test read as a silent pass on the table itself.
            ph_note = (
                f"Proportional hazards: NOT TESTED ({ph_result.get('status')}) — "
                f"{ph_result.get('reason', 'no reason recorded')}. The hazard ratios above "
                f"have not been checked against the proportional hazards assumption."
            )
        ws1.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s1)
        cell = ws1.cell(row=row_idx, column=1, value=ph_note)
        cell.font = footnote_font
        cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws1.row_dimensions[row_idx].height = 30

    # ── Sheet 2: Interaction Analysis ───────────────────────────────────────
    ws2 = wb.create_sheet("Interaction Analysis")

    # Columns: Variable | G1: N(ev) | G1: HR/OR(CI) | G1: p | G2: N(ev) | G2: HR/OR(CI) | G2: p | p-interaction
    total_cols_s2 = 8
    for c, w in zip(range(1, total_cols_s2 + 1), [32, 14, 26, 10, 14, 26, 10, 14]):
        ws2.column_dimensions[get_column_letter(c)].width = w

    row_idx = 1

    # Title
    ws2.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s2)
    cell = ws2.cell(row=row_idx, column=1, value=f"Interaction Analysis \u2014 Subgroup Adjusted {effect_label} (delta method)")
    cell.font = title_font; cell.fill = title_fill; cell.alignment = center
    for c in range(1, total_cols_s2 + 1):
        ws2.cell(row=row_idx, column=c).fill = title_fill
    row_idx += 1

    # Subtitle with per-group info
    if analysis_type == 'cox':
        event_col = config['cox_settings']['event_column']
    else:
        event_col = config['logistic_settings']['outcome_column']
    sub_text_parts = []
    subtitle_base = config.get('subtitle', '')
    if subtitle_base:
        sub_text_parts.append(subtitle_base)
    sub_text_parts.append(f"Each cell = {g1_label} vs {g2_label} {effect_label} within a covariate subgroup (delta method, single {config['grouping']['column']} × covariate interaction model). Columns are the covariate's subgroup levels — see the subgroup tag in each cell.")
    ws2.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s2)
    cell = ws2.cell(row=row_idx, column=1, value="  |  ".join(sub_text_parts))
    cell.font = subtitle_font; cell.fill = title_fill; cell.alignment = center
    for c in range(1, total_cols_s2 + 1):
        ws2.cell(row=row_idx, column=c).fill = title_fill
    row_idx += 1

    # Row 3: Group headers (merged)
    ws2.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx + 1, end_column=1)  # Variable
    cell = ws2.cell(row=row_idx, column=1, value="Variable")
    cell.font = header_font; cell.fill = header_fill; cell.alignment = center; cell.border = THIN_BORDER

    # Group 1 header
    ws2.merge_cells(start_row=row_idx, start_column=2, end_row=row_idx, end_column=4)
    cell = ws2.cell(row=row_idx, column=2, value="Subgroup 1")
    cell.font = header_font; cell.fill = g1_header_fill; cell.alignment = center
    for c in range(2, 5):
        ws2.cell(row=row_idx, column=c).fill = g1_header_fill; ws2.cell(row=row_idx, column=c).border = THIN_BORDER

    # Group 2 header
    ws2.merge_cells(start_row=row_idx, start_column=5, end_row=row_idx, end_column=7)
    cell = ws2.cell(row=row_idx, column=5, value="Subgroup 2")
    cell.font = header_font; cell.fill = g2_header_fill; cell.alignment = center
    for c in range(5, 8):
        ws2.cell(row=row_idx, column=c).fill = g2_header_fill; ws2.cell(row=row_idx, column=c).border = THIN_BORDER

    # p-interaction header
    ws2.merge_cells(start_row=row_idx, start_column=8, end_row=row_idx + 1, end_column=8)
    cell = ws2.cell(row=row_idx, column=8, value="p-interaction")
    cell.font = header_font; cell.fill = header_fill; cell.alignment = center; cell.border = THIN_BORDER

    row_idx += 1

    # Row 4: Sub-headers
    sub_headers = ["Subgroup [N (events)]", f"Adj. {effect_label} (95% CI)", "p-value"]
    for i, start_col in enumerate([2, 5]):
        fill = g1_header_fill if start_col == 2 else g2_header_fill
        for j, sh in enumerate(sub_headers):
            col = start_col + j
            cell = ws2.cell(row=row_idx, column=col, value=sh)
            cell.font = header_font; cell.fill = fill; cell.alignment = center; cell.border = THIN_BORDER

    # Variable and p-interaction cells in row 4 (already merged)
    ws2.cell(row=row_idx, column=1).fill = header_fill; ws2.cell(row=row_idx, column=1).border = THIN_BORDER
    ws2.cell(row=row_idx, column=8).fill = header_fill; ws2.cell(row=row_idx, column=8).border = THIN_BORDER

    row_idx += 1
    ws2.freeze_panes = ws2.cell(row=row_idx, column=1)

    # Data rows
    current_section = None
    data_row_idx = 0

    for result in interaction_results:
        # Section header
        if result['section'] != current_section:
            current_section = result['section']
            ws2.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s2)
            cell = ws2.cell(row=row_idx, column=1, value=current_section)
            cell.font = section_font; cell.fill = section_fill; cell.alignment = left
            for c in range(1, total_cols_s2 + 1):
                ws2.cell(row=row_idx, column=c).fill = section_fill
                ws2.cell(row=row_idx, column=c).border = THIN_BORDER
            row_idx += 1
            data_row_idx = 0

        row_fill = alt_fill if data_row_idx % 2 == 1 else no_fill

        # Variable label
        cell = ws2.cell(row=row_idx, column=1, value=result['label'])
        cell.font = data_font; cell.fill = row_fill; cell.alignment = left; cell.border = THIN_BORDER

        # Group 1 results
        for grp_key, col_offset in [('g1', 2), ('g2', 5)]:
            sub_lbl = result.get(f'{grp_key}_sub')
            _n = result.get(f'{grp_key}_n')
            if _n is None:
                # continuous covariate: evaluation point, no discrete subgroup N
                n_ev_str = sub_lbl or '—'
            else:
                base = fmt_n_events(_n, result.get(f'{grp_key}_events'))
                n_ev_str = f"{sub_lbl}: {base}" if sub_lbl else base
            effect_str = fmt_effect(result.get(f'{grp_key}_effect'),
                                    result.get(f'{grp_key}_ci_lower'),
                                    result.get(f'{grp_key}_ci_upper'))
            p_str = fmt_p(result.get(f'{grp_key}_p'))
            p_val = result.get(f'{grp_key}_p')

            cell = ws2.cell(row=row_idx, column=col_offset, value=n_ev_str)
            cell.font = data_font; cell.fill = row_fill; cell.alignment = center; cell.border = THIN_BORDER

            cell = ws2.cell(row=row_idx, column=col_offset + 1, value=effect_str)
            cell.font = data_font; cell.fill = row_fill; cell.alignment = center; cell.border = THIN_BORDER

            cell = ws2.cell(row=row_idx, column=col_offset + 2, value=p_str)
            if p_val is not None and p_val < 0.05:
                cell.font = sig_font
            else:
                cell.font = data_font
            cell.fill = row_fill; cell.alignment = center; cell.border = THIN_BORDER

        # p-interaction
        p_int = result.get('p_interaction')
        p_int_str = fmt_p(p_int)
        cell = ws2.cell(row=row_idx, column=8, value=p_int_str)
        if p_int is not None and p_int < 0.05:
            cell.font = sig_font
        else:
            cell.font = data_font
        cell.fill = row_fill; cell.alignment = center; cell.border = THIN_BORDER

        row_idx += 1
        data_row_idx += 1

    # Footnotes
    row_idx += 1
    if abbreviations:
        ws2.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s2)
        cell = ws2.cell(row=row_idx, column=1, value=abbreviations)
        cell.font = footnote_font; cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
        ws2.row_dimensions[row_idx].height = 30
        row_idx += 1

    note = (f"* p < 0.05  |  {effect_label} = {'hazard ratio' if analysis_type == 'cox' else 'odds ratio'}; "
            f"CI = confidence interval  |  "
            f"Each cell reports the {g1_label} vs {g2_label} {effect_label} estimated WITHIN that covariate subgroup; "
            f"the two columns are the covariate's subgroup levels (binary: =0 / =1; categorical: reference / level; "
            f"continuous: at mean / at mean + 1 SD), NOT the {g1_label}/{g2_label} arms. "
            f"Derived via delta method from a single {'Cox proportional hazards' if analysis_type == 'cox' else 'logistic regression'} model: log {effect_label}(x) = \u03b2_grp + \u03b2_int \u00b7 x, Var = V_gg + x\u00b2\u00b7V_ii + 2x\u00b7V_gi  |  "
            f"p-interaction = Wald test on the {config['grouping']['column']} \u00d7 covariate product term")
    ws2.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=total_cols_s2)
    cell = ws2.cell(row=row_idx, column=1, value=note)
    cell.font = footnote_font; cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    ws2.row_dimensions[row_idx].height = 30

    # Save
    wb.save(output_path)
    print(f"\nSaved: {output_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_academic_style():
    """academic-style integration (Wave 3, Excel-only). Consumes --style=<journal>
    from sys.argv. No-op when skill not installed or flag absent."""
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
        print(f"  Applied {_AS_STYLE} journal style (Excel formatting hints)")

    if len(sys.argv) < 2:
        print("Usage: python multivariate_interaction.py config.json [--check-missing] [--style=<journal>]")
        sys.exit(1)

    config_path = sys.argv[1]
    check_missing_only = '--check-missing' in sys.argv

    config = load_config(config_path)
    df = load_data(config)
    grp1, grp2 = split_groups(df, config)

    g1_label = config['grouping']['groups'][0]['label']
    g2_label = config['grouping']['groups'][1]['label']

    print(f"Data loaded: n={len(df)}")
    print(f"  {g1_label}: n={len(grp1)}")
    print(f"  {g2_label}: n={len(grp2)}")

    if check_missing_only:
        report = check_missing(df, grp1, grp2, config)
        print(report)
        sys.exit(0)

    # Prepare data (listwise deletion)
    df_clean = prepare_analysis_df(df, config)
    grp1_clean, grp2_clean = split_groups(df_clean, config)

    print(f"\nAfter {config['missing_data_handling']} deletion:")
    print(f"  Overall: n={len(df_clean)}")
    print(f"  {g1_label}: n={len(grp1_clean)}")
    print(f"  {g2_label}: n={len(grp2_clean)}")

    # Sheet 1: Multivariate analysis (overall)
    print("\n=== Multivariate Analysis (Overall) ===")
    mv_results, mv_n, mv_events, mv_fit = run_multivariate(df_clean, config)
    if mv_results:
        n_sig = sum(1 for r in mv_results.values() if r['p'] < 0.05)
        print(f"  Completed: {len(mv_results)} variables, {n_sig} significant (p<0.05)")
    else:
        print("  Multivariate model failed to converge")

    # Time-scale declaration (Cox only). `kaplan-meier` and `competing-risk` receive
    # `time_scale` / `time_unit` in their configs and warn when the plan declared
    # neither; the Cox route was never given either field, so the same undeclared
    # time unit was flagged on one route and silent on the other.
    if config['analysis_type'] == 'cox':
        _cs = config.get('cox_settings') or {}
        _scale = _cs.get('time_scale', config.get('time_scale'))
        _unit = _cs.get('time_unit', config.get('time_unit'))
        _tcol = _cs.get('time_column', 'time')
        if _scale is None and _unit is None:
            print(f"[QC_WARNING] time_scale_assumed: neither `time_scale` nor "
                  f"`time_unit` is declared for '{_tcol}', so this run cannot state "
                  f"what one unit of follow-up means. The adjusted HRs are unaffected "
                  f"— Cox uses only the ordering of event times, so a constant "
                  f"rescaling cannot change them — but every time-denominated number "
                  f"reported here is in raw column units, including the PH early/late "
                  f"split point. Declare `time_unit` (and `time_scale` if the raw "
                  f"column is not in days) for this outcome in research_plan.json.",
                  file=sys.stderr)
        elif _unit is not None and _scale is None:
            print(f"[QC_WARNING] time_scale_assumed: `time_unit`='{_unit}' is declared "
                  f"for '{_tcol}' but `time_scale` is not, so the raw column is taken "
                  f"as already being in {_unit}. If it is in days, set \"time_scale\" "
                  f"for this outcome.", file=sys.stderr)

    # Proportional hazards diagnostics (Cox only). `ph_result` stays None only for
    # logistic models, where there is no PH assumption at all; every Cox run gets a
    # status dict, including the failure cases, so the gate below always sees them.
    ph_result = None
    if config['analysis_type'] == 'cox':
        print("\n=== Proportional Hazards (Schoenfeld) ===")
        ph_result = ph_assumption_test(mv_fit)
        if ph_result['status'] == PH_COMPUTED:
            # Effect size next to the p-value: in the borderline band the p alone is
            # the wrong thing to decide on, and the reviewer needs a magnitude.
            ph_result['effect_size'] = ph_split_hr(
                mv_fit, (config.get('grouping') or {}).get('column'))
        out_base = os.path.splitext(config['output_file'])[0]
        ph_json = f"{out_base}_ph_test.json"
        # Written for every status: an artifact recording "could not be computed"
        # is what lets the downstream auditor tell that apart from "never ran".
        with open(ph_json, 'w', encoding='utf-8') as f:
            json.dump(ph_result, f, indent=2)

        if ph_result['status'] == PH_COMPUTED:
            g = ph_result['global']
            print(f"  Global: chi2={g['chi2']:.2f}, df={g['df']}, p={g['p']:.4g} "
                  f"(gate p<{PH_ALPHA} on {ph_result['gate_transform']}; "
                  f"review band up to {PH_ALPHA_REVIEW} over "
                  f"{'/'.join(ph_result['review_transforms'])})")
            for col, r in ph_result['per_variable'].items():
                mark = ('  <-- violated' if r['violated']
                        else ('  <-- borderline' if r['borderline'] else ''))
                print(f"    {col}: chi2={r['chi2']:.2f}, p={r['p']:.4g} "
                      f"(min over transforms {r['min_p']:.4g}){mark}")
            es = ph_result.get('effect_size') or {}
            if es.get('available') and es.get('hr_early') and es.get('hr_late'):
                print(f"  Early/late split HR for {es['variable']} at t={es['split_time']:.3g}: "
                      f"{es['hr_early']:.2f} -> {es['hr_late']:.2f} (diagnostic only)")
            if ph_result.get('transform_errors'):
                for tt, err in ph_result['transform_errors'].items():
                    print(f"  [PH review transform '{tt}' unavailable] {err}")
            print(f"  PH test detail: {ph_json}")
            ph_png = plot_ph_diagnostics(mv_fit, ph_result, f"{out_base}_ph_diagnostics.png")
            if ph_png:
                print(f"  PH diagnostic plot: {ph_png}")
        else:
            print(f"  status={ph_result['status']}: {ph_result.get('reason', '')}")
            print(f"  PH test detail: {ph_json}")

    # Sheet 2: Interaction analysis
    print("\n=== Interaction Analysis ===")
    interaction_results, interaction_failed = run_interaction(df_clean, grp1_clean, grp2_clean, config)
    n_sig_int = sum(1 for r in interaction_results if r.get('p_interaction') is not None and r['p_interaction'] < 0.05)
    print(f"  Completed: {len(interaction_results)} variables, {n_sig_int} significant interactions (p<0.05)")
    if interaction_failed:
        print(f"  Failed: {', '.join(interaction_failed)}")

    # Write Excel
    print("\n=== Writing Excel ===")
    write_excel(mv_results, mv_n, mv_events, interaction_results, config, df_clean, ph_result)

    print("\nDone!")
    print(f"  Output: {config['output_file']}")
    print(f"  Sheet 1: Multivariate Analysis (n={mv_n}, events={mv_events})")
    print(f"  Sheet 2: Interaction Analysis ({len(interaction_results)} variables, {n_sig_int} significant interactions)")

    # ── QC Warnings ──────────────────────────────────────────────────────────
    # Track blocking emissions and sys.exit(2) at the end so the pipeline sees a
    # non-zero exit when [QC_BLOCKING] is raised. Previously [QC_BLOCKING] was
    # emitted but exit was always 0, making the pipeline think the step succeeded
    # with warnings only.
    #
    # NOTE (intentional difference from table1): table1 runs its blocking check in
    # `pre_write_validation()` BEFORE write_excel/write_csv, so a blocking failure
    # leaves no artifact on disk. This script validates AFTER writing the Excel —
    # the QC checks depend on the fitted model/interaction results, so the file is
    # already written when we discover the problem. Consequence: on exit 2 an Excel
    # file DOES exist on disk; downstream consumers must key off the exit code, not
    # file presence. Kept as-is deliberately; do not reorder the flow for this.
    qc_blocking_count = 0

    def _qc_block(msg):
        nonlocal qc_blocking_count
        print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
        qc_blocking_count += 1

    try:
        analysis_type = config['analysis_type']
        effect_label = "HR" if analysis_type == 'cox' else "OR"

        # Check group sizes
        for lbl, n in [(g1_label, len(grp1_clean)), (g2_label, len(grp2_clean))]:
            if n < 30:
                print(f"[QC_WARNING] Group '{lbl}' has n={n} (< 30)", file=sys.stderr)

        # Check 0 events
        if analysis_type == 'cox':
            event_col_name = config['cox_settings']['event_column']
            for lbl, sub_df in [(g1_label, grp1_clean), (g2_label, grp2_clean)]:
                ev = pd.to_numeric(sub_df[event_col_name], errors='coerce').sum()
                if ev == 0:
                    _qc_block(f"Group '{lbl}' has 0 events")
        else:
            outcome_col_name = config['logistic_settings']['outcome_column']
            for lbl, sub_df in [(g1_label, grp1_clean), (g2_label, grp2_clean)]:
                ev = pd.to_numeric(sub_df[outcome_col_name], errors='coerce').sum()
                if ev == 0:
                    _qc_block(f"Group '{lbl}' has 0 events")

        # Check model convergence
        if mv_results is None:
            _qc_block("Multivariate model did not converge")

        # Proportional hazards gate (Cox only). ph_gate itself decides what each
        # status means; do not pre-filter here or the failure cases go quiet again.
        if analysis_type == 'cox':
            ph_blocking, ph_warnings = ph_gate(ph_result, config)
            for msg in ph_warnings:
                print(f"[QC_WARNING] {msg}", file=sys.stderr)
            for msg in ph_blocking:
                _qc_block(msg)

        # Check for extreme HR/OR values in multivariate results
        if mv_results:
            for col_name, r in mv_results.items():
                eff = r.get('effect')
                if eff is not None:
                    if np.isinf(eff) or np.isnan(eff) or eff <= 0:
                        _qc_block(f"Variable '{col_name}': {effect_label}={eff} is Inf/NaN/<=0")
                    elif eff > 10:
                        print(f"[QC_WARNING] Variable '{col_name}': {effect_label}={eff:.2f} > 10", file=sys.stderr)
                ci_l = r.get('ci_lower')
                ci_u = r.get('ci_upper')
                if ci_l is not None and ci_u is not None:
                    ci_width = ci_u - ci_l
                    if ci_width > 100:
                        print(f"[QC_WARNING] Variable '{col_name}': CI width={ci_width:.1f} > 100", file=sys.stderr)

        # Check interaction results for extreme values
        for ir in interaction_results:
            for grp_key in ['g1', 'g2']:
                eff = ir.get(f'{grp_key}_effect')
                if eff is not None:
                    if np.isinf(eff) or np.isnan(eff) or eff <= 0:
                        _qc_block(f"Interaction '{ir['label']}' ({grp_key}): {effect_label}={eff} is Inf/NaN/<=0")
                    elif eff > 10:
                        print(f"[QC_WARNING] Interaction '{ir['label']}' ({grp_key}): {effect_label}={eff:.2f} > 10", file=sys.stderr)
                ci_l = ir.get(f'{grp_key}_ci_lower')
                ci_u = ir.get(f'{grp_key}_ci_upper')
                if ci_l is not None and ci_u is not None:
                    ci_width = ci_u - ci_l
                    if ci_width > 100:
                        print(f"[QC_WARNING] Interaction '{ir['label']}' ({grp_key}): CI width={ci_width:.1f} > 100", file=sys.stderr)
    except Exception as e:
        # Surface the QC failure instead of silently swallowing it: a QC block that
        # itself crashes must not look like a clean run to the pipeline.
        print(f"[QC_WARNING] QC block raised: {type(e).__name__}: {e}", file=sys.stderr)

    if qc_blocking_count > 0:
        sys.exit(2)


if __name__ == '__main__':
    main()
