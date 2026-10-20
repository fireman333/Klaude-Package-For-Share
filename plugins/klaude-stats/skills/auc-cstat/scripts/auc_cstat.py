#!/usr/bin/env python3
"""
AUC / C-Statistics Discrimination Analysis
Evaluates discriminative performance (AUC or C-index) of individual variables,
with optional comparison against a baseline clinical model.

Usage:
    python auc_cstat.py config.json                  # Full analysis
    python auc_cstat.py config.json --check-missing  # Missing data report only
"""

import sys
import json
import os
import operator
import pandas as pd
import numpy as np
# P-3 batch (2026-05-07 partitioned-flame audit): removed `import warnings;
# warnings.filterwarnings('ignore')` — global suppression hid statsmodels /
# lifelines / scipy convergence and bootstrap-failure warnings during
# discrimination modelling (silent error pattern).
# 

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

    # Clinical model defaults
    cm = config.get('clinical_model', {})
    cm.setdefault('enabled', False)
    cm.setdefault('variables', [])
    config['clinical_model'] = cm

    # Bootstrap defaults (for cox)
    bs = config.get('bootstrap', {})
    bs.setdefault('n_iterations', 1000)
    bs.setdefault('random_seed', 42)
    config['bootstrap'] = bs

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


def get_outcome_cols(config):
    """Return list of outcome-related columns."""
    if config['analysis_type'] == 'cox':
        cs = config['cox_settings']
        return [cs['time_column'], cs['event_column']]
    else:
        return [config['logistic_settings']['outcome_column']]


def get_clinical_cols(config):
    """Return list of clinical model column names."""
    cm = config['clinical_model']
    if not cm['enabled']:
        return []
    return [v['column'] for v in cm['variables']]


def get_clinical_scales(config):
    """Return dict of column -> scale for clinical model variables."""
    cm = config['clinical_model']
    if not cm['enabled']:
        return {}
    return {v['column']: v.get('scale', None) for v in cm['variables']}


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
    # Include outcome columns
    for c in get_outcome_cols(config):
        if c in df.columns and c not in cols:
            cols.append(c)
    # Include clinical model columns
    for c in get_clinical_cols(config):
        if c in df.columns and c not in cols:
            cols.append(c)
    for col in cols:
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

def check_missing(df, config):
    """Print a missing data report."""
    outcome_cols = get_outcome_cols(config)
    clinical_cols = get_clinical_cols(config)
    n_total = len(df)

    lines = []
    lines.append("=" * 80)
    lines.append("MISSING DATA REPORT")
    lines.append("=" * 80)
    lines.append(f"Total sample size: {n_total}")
    lines.append("")
    lines.append(f"{'Variable':<40} {'Missing':>12} {'%':>8}")
    lines.append("-" * 80)

    any_missing = False

    # Outcome/time columns
    lines.append("\nOutcome Variables:")
    for col_name in outcome_cols:
        if col_name in df.columns:
            n_miss = pd.to_numeric(df[col_name], errors='coerce').isna().sum()
            pct = n_miss / n_total * 100 if n_total > 0 else 0
            if n_miss > 0:
                any_missing = True
            lines.append(f"  {col_name:<38} {n_miss:>6}/{n_total:<5} ({pct:>5.1f}%)")
        else:
            lines.append(f"  {col_name:<38} {'COLUMN NOT FOUND':>20}")
            any_missing = True

    # Clinical model variables
    if clinical_cols:
        lines.append("\nClinical Model Variables:")
        for var in config['clinical_model']['variables']:
            col = var['column']
            label = var['label']
            display = f"{label} [{col}]"
            if col in df.columns:
                n_miss = pd.to_numeric(df[col], errors='coerce').isna().sum()
                pct = n_miss / n_total * 100 if n_total > 0 else 0
                if n_miss > 0:
                    any_missing = True
                lines.append(f"  {display:<38} {n_miss:>6}/{n_total:<5} ({pct:>5.1f}%)")
            else:
                lines.append(f"  {display:<38} {'COLUMN NOT FOUND':>20}")
                any_missing = True

    # Evaluation variables
    for section in config['sections']:
        lines.append(f"\n{section['header']}:")
        for var in section['variables']:
            col = var['column']
            label = var['label']
            display = f"{label} [{col}]"
            if col in df.columns:
                n_miss = pd.to_numeric(df[col], errors='coerce').isna().sum()
                pct = n_miss / n_total * 100 if n_total > 0 else 0
                if n_miss > 0:
                    any_missing = True
                lines.append(f"  {display:<38} {n_miss:>6}/{n_total:<5} ({pct:>5.1f}%)")
            else:
                lines.append(f"  {display:<38} {'COLUMN NOT FOUND':>20}")
                any_missing = True

    # Listwise effective sample size
    if config['missing_data_handling'] == 'listwise':
        all_cols = list(set(outcome_cols + clinical_cols +
                           [v['column'] for s in config['sections'] for v in s['variables']]))
        existing_cols = [c for c in all_cols if c in df.columns]
        temp = df[existing_cols].copy()
        for c in existing_cols:
            temp[c] = pd.to_numeric(temp[c], errors='coerce')
        n_complete = temp.dropna().shape[0]
        lines.append(f"\nEffective sample size (listwise deletion): {n_complete} / {n_total}")

    lines.append("")
    lines.append("=" * 80)
    if not any_missing:
        lines.append("No missing values detected across all variables.")
    else:
        handling = config['missing_data_handling']
        lines.append(f"Missing values detected. Current handling: {handling} deletion.")
    lines.append("=" * 80)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Statistical Functions — AUC (Logistic)
# ═══════════════════════════════════════════════════════════════════════════════

def _placement_values(y_true, y_score):
    """Compute DeLong placement values."""
    pos_scores = y_score[y_true == 1]
    neg_scores = y_score[y_true == 0]

    # V10: for each positive, proportion of negatives scored below
    V10 = np.array([np.mean(neg_scores < s) + 0.5 * np.mean(neg_scores == s)
                    for s in pos_scores])
    # V01: for each negative, proportion of positives scored above
    V01 = np.array([np.mean(pos_scores > s) + 0.5 * np.mean(pos_scores == s)
                    for s in neg_scores])
    return V10, V01


def auc_ci_delong(y_true, y_score, alpha=0.05):
    """Compute AUC with 95% CI using DeLong's variance estimate."""
    from sklearn.metrics import roc_auc_score
    import scipy.stats

    y_true = np.asarray(y_true, dtype=int)
    y_score = np.asarray(y_score, dtype=float)

    auc = roc_auc_score(y_true, y_score)
    n1 = np.sum(y_true == 1)
    n0 = np.sum(y_true == 0)

    if n1 == 0 or n0 == 0:
        return auc, np.nan, np.nan

    V10, V01 = _placement_values(y_true, y_score)
    var_auc = np.var(V10, ddof=1) / n1 + np.var(V01, ddof=1) / n0

    z_crit = scipy.stats.norm.ppf(1 - alpha / 2)
    se = np.sqrt(max(var_auc, 0))
    ci_lower = max(0, auc - z_crit * se)
    ci_upper = min(1, auc + z_crit * se)
    return auc, ci_lower, ci_upper


def delong_test(y_true, y_score_base, y_score_full):
    """
    Compare two correlated AUCs using DeLong's method.
    Returns: (delta_auc, p_value)
    """
    import scipy.stats

    y_true = np.asarray(y_true, dtype=int)
    y_score_base = np.asarray(y_score_base, dtype=float)
    y_score_full = np.asarray(y_score_full, dtype=float)

    n1 = np.sum(y_true == 1)
    n0 = np.sum(y_true == 0)

    if n1 == 0 or n0 == 0:
        return 0.0, 1.0

    V10_base, V01_base = _placement_values(y_true, y_score_base)
    V10_full, V01_full = _placement_values(y_true, y_score_full)

    auc_base = np.mean(V10_base)
    auc_full = np.mean(V10_full)
    delta = auc_full - auc_base

    # Covariance matrix
    S10 = np.cov(np.vstack([V10_base, V10_full]))
    S01 = np.cov(np.vstack([V01_base, V01_full]))

    # Handle scalar case (single positive or negative)
    if S10.ndim == 0:
        S10 = np.array([[S10, S10], [S10, S10]])
    if S01.ndim == 0:
        S01 = np.array([[S01, S01], [S01, S01]])

    S = S10 / n0 + S01 / n1
    var_delta = S[0, 0] + S[1, 1] - 2 * S[0, 1]

    if var_delta <= 0:
        return delta, 1.0

    z = delta / np.sqrt(var_delta)
    p = 2 * (1 - scipy.stats.norm.cdf(abs(z)))
    return delta, p


def fit_logistic_auc(X_cols, outcome_col, data):
    """
    Fit logistic regression and return AUC with CI.
    Returns: (n, n_events, auc, ci_lower, ci_upper, y_pred) or None
    """
    import statsmodels.api as sm

    d = data[X_cols + [outcome_col]].dropna().copy()
    for c in X_cols + [outcome_col]:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna()

    n = len(d)
    n_events = int(d[outcome_col].sum())

    if n < 10 or n_events < 5:
        return None

    # Check zero variance
    for c in X_cols:
        if d[c].nunique() < 2:
            return None

    try:
        X = sm.add_constant(d[X_cols])
        model = sm.Logit(d[outcome_col], X).fit(disp=0, method='bfgs', maxiter=200)
        y_pred = model.predict(X).values
        auc, ci_l, ci_u = auc_ci_delong(d[outcome_col].values, y_pred)
        return (n, n_events, auc, ci_l, ci_u, y_pred)
    except Exception as e:
        print(f"  [Logistic] Error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Statistical Functions — C-index (Cox)
# ═══════════════════════════════════════════════════════════════════════════════

def fit_cox_cindex(X_cols, time_col, event_col, data, n_boot=1000, seed=42):
    """
    Fit Cox PH and return C-index with bootstrap CI.
    Returns: (n, n_events, c_index, ci_lower, ci_upper) or None
    """
    from lifelines import CoxPHFitter

    d = data[X_cols + [time_col, event_col]].dropna().copy()
    for c in X_cols + [time_col, event_col]:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna()

    n = len(d)
    n_events = int(d[event_col].sum())

    if n < 10 or n_events < 5:
        return None

    for c in X_cols:
        if d[c].nunique() < 2:
            return None

    try:
        cph = CoxPHFitter()
        formula = ' + '.join(X_cols)
        cph.fit(d, duration_col=time_col, event_col=event_col, formula=formula)
        c_index = cph.concordance_index_

        # Bootstrap CI — with-replacement resampling of n indices per iteration.
        # Uses a single np.random.Generator seeded from config seed; advancing the
        # generator across iterations avoids the frac=1 / permutation-only pitfall
        # that artificially narrowed CIs.
        rng = np.random.default_rng(seed)
        boot_ci = []
        for _ in range(n_boot):
            idx = rng.integers(0, n, size=n)
            # reset_index is mandatory: lifelines concordance_index_ mis-aligns
            # rows when the DataFrame index has duplicates (as happens after
            # with-replacement iloc resampling), collapsing c-index toward 0.5
            # and producing CIs that do not contain the point estimate.
            boot_df = d.iloc[idx].reset_index(drop=True)
            try:
                cph_b = CoxPHFitter()
                cph_b.fit(boot_df, duration_col=time_col, event_col=event_col, formula=formula)
                boot_ci.append(cph_b.concordance_index_)
            except:
                continue

        if len(boot_ci) > 10:
            ci_l = float(np.percentile(boot_ci, 2.5))
            ci_u = float(np.percentile(boot_ci, 97.5))
        else:
            ci_l = np.nan
            ci_u = np.nan

        return (n, n_events, c_index, ci_l, ci_u)
    except Exception as e:
        print(f"  [Cox] Error: {e}")
        return None


def bootstrap_compare_cindex(X_cols_base, X_cols_full, time_col, event_col, data,
                             n_boot=1000, seed=42):
    """
    Paired bootstrap comparison of C-indices between two nested Cox models.
    Returns: (delta_c, ci_lower, ci_upper, p_value) or None
    """
    from lifelines import CoxPHFitter

    all_cols = list(set(X_cols_base + X_cols_full + [time_col, event_col]))
    d = data[all_cols].dropna().copy()
    for c in all_cols:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna()

    n = len(d)
    if n < 10:
        return None

    formula_base = ' + '.join(X_cols_base)
    formula_full = ' + '.join(X_cols_full)

    try:
        cph_base = CoxPHFitter()
        cph_base.fit(d, duration_col=time_col, event_col=event_col, formula=formula_base)
        c_base = cph_base.concordance_index_

        cph_full = CoxPHFitter()
        cph_full.fit(d, duration_col=time_col, event_col=event_col, formula=formula_full)
        c_full = cph_full.concordance_index_

        delta_observed = c_full - c_base
    except Exception as e:
        print(f"  [Cox compare] Error on point estimate: {e}")
        return None

    # Paired bootstrap: resample n indices with replacement and refit BOTH models
    # on the same bootstrap sample. Single Generator, advanced each iteration.
    rng = np.random.default_rng(seed)
    deltas = []

    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_df = d.iloc[idx].reset_index(drop=True)
        try:
            cph_b = CoxPHFitter()
            cph_b.fit(boot_df, duration_col=time_col, event_col=event_col, formula=formula_base)

            cph_f = CoxPHFitter()
            cph_f.fit(boot_df, duration_col=time_col, event_col=event_col, formula=formula_full)

            deltas.append(cph_f.concordance_index_ - cph_b.concordance_index_)
        except:
            continue

        if (i + 1) % 200 == 0:
            print(f"    Bootstrap progress: {i + 1}/{n_boot}")

    if len(deltas) < 10:
        return delta_observed, np.nan, np.nan, np.nan

    deltas = np.array(deltas)
    ci_l = float(np.percentile(deltas, 2.5))
    ci_u = float(np.percentile(deltas, 97.5))

    # Two-sided p-value from bootstrap
    p_value = 2 * min(np.mean(deltas <= 0), np.mean(deltas >= 0))
    p_value = min(p_value, 1.0)

    return delta_observed, ci_l, ci_u, p_value


# ═══════════════════════════════════════════════════════════════════════════════
# Run Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def prepare_var_data(df, var_col, var_scale, clinical_vars, clinical_scales, config):
    """
    Prepare data for one evaluation variable: apply scaling, drop NAs.
    Returns a DataFrame with scaled columns ready for modeling.
    """
    outcome_cols = get_outcome_cols(config)
    clinical_col_names = [v['column'] for v in clinical_vars]
    all_needed = [var_col] + clinical_col_names + outcome_cols

    # Get unique columns (avoid duplicates)
    all_needed = list(dict.fromkeys(all_needed))

    d = df[all_needed].copy()
    for c in all_needed:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.dropna()

    # Apply scaling
    if var_scale:
        d[var_col] = d[var_col] / var_scale
    for c_col, c_scale in clinical_scales.items():
        if c_scale and c_col in d.columns:
            d[c_col] = d[c_col] / c_scale

    return d


def run_analysis(config, df):
    """Run AUC/C-index analysis for all evaluation variables."""
    analysis_type = config['analysis_type']
    cm = config['clinical_model']
    clinical_enabled = cm['enabled'] and len(cm['variables']) > 0
    clinical_vars = cm['variables'] if clinical_enabled else []
    clinical_col_names = [v['column'] for v in clinical_vars]
    clinical_scales = get_clinical_scales(config)
    n_boot = config['bootstrap']['n_iterations']
    seed = config['bootstrap']['random_seed']

    if analysis_type == 'cox':
        cs = config['cox_settings']
        time_col = cs['time_column']
        event_col = cs['event_column']
    else:
        outcome_col = config['logistic_settings']['outcome_column']

    results = []
    failed = []

    for section in config['sections']:
        for var in section['variables']:
            col = var['column']
            label = var['label']
            scale = var.get('scale', None)
            print(f"  Processing: {label} ...")

            row = {
                'label': label,
                'column': col,
                'section': section['header'],
            }

            # Prepare data with scaling
            d = prepare_var_data(df, col, scale, clinical_vars, clinical_scales, config)

            if analysis_type == 'logistic':
                # --- AUC analysis ---
                # 1. Variable alone
                res_var = fit_logistic_auc([col], outcome_col, d)
                if res_var is not None:
                    n, n_ev, auc, ci_l, ci_u, y_pred_var = res_var
                    row['n'] = n
                    row['events'] = n_ev
                    row['var_auc'] = auc
                    row['var_ci_l'] = ci_l
                    row['var_ci_u'] = ci_u
                else:
                    row['n'] = len(d) if len(d) > 0 else None
                    row['events'] = int(pd.to_numeric(d.get(outcome_col, pd.Series()), errors='coerce').sum()) if len(d) > 0 else None
                    row['var_auc'] = None
                    row['var_ci_l'] = None
                    row['var_ci_u'] = None
                    failed.append(label)

                # 2-3. Clinical model (if enabled)
                if clinical_enabled and res_var is not None:
                    res_cm = fit_logistic_auc(clinical_col_names, outcome_col, d)
                    res_full = fit_logistic_auc(clinical_col_names + [col], outcome_col, d)

                    if res_cm is not None and res_full is not None:
                        _, _, auc_cm, ci_l_cm, ci_u_cm, y_pred_cm = res_cm
                        _, _, auc_full, ci_l_full, ci_u_full, y_pred_full = res_full
                        row['cm_auc'] = auc_cm
                        row['cm_ci_l'] = ci_l_cm
                        row['cm_ci_u'] = ci_u_cm
                        row['full_auc'] = auc_full
                        row['full_ci_l'] = ci_l_full
                        row['full_ci_u'] = ci_u_full

                        # DeLong comparison
                        delta, p = delong_test(d[outcome_col].values, y_pred_cm, y_pred_full)
                        row['delta'] = delta
                        row['delta_p'] = p
                    else:
                        row['cm_auc'] = None
                        row['full_auc'] = None
                        row['delta'] = None
                        row['delta_p'] = None

            else:
                # --- C-index analysis ---
                # 1. Variable alone
                res_var = fit_cox_cindex([col], time_col, event_col, d, n_boot, seed)
                if res_var is not None:
                    n, n_ev, c_idx, ci_l, ci_u = res_var
                    row['n'] = n
                    row['events'] = n_ev
                    row['var_auc'] = c_idx
                    row['var_ci_l'] = ci_l
                    row['var_ci_u'] = ci_u
                else:
                    row['n'] = len(d) if len(d) > 0 else None
                    row['events'] = int(pd.to_numeric(d.get(event_col, pd.Series()), errors='coerce').sum()) if len(d) > 0 else None
                    row['var_auc'] = None
                    row['var_ci_l'] = None
                    row['var_ci_u'] = None
                    failed.append(label)

                # 2-3. Clinical model (if enabled)
                if clinical_enabled and res_var is not None:
                    res_cm = fit_cox_cindex(clinical_col_names, time_col, event_col, d, n_boot, seed)

                    if res_cm is not None:
                        _, _, c_idx_cm, ci_l_cm, ci_u_cm = res_cm
                        row['cm_auc'] = c_idx_cm
                        row['cm_ci_l'] = ci_l_cm
                        row['cm_ci_u'] = ci_u_cm

                        # Compare clinical model vs clinical model + variable
                        cmp = bootstrap_compare_cindex(
                            clinical_col_names, clinical_col_names + [col],
                            time_col, event_col, d, n_boot, seed
                        )
                        if cmp is not None:
                            delta, delta_ci_l, delta_ci_u, p = cmp
                            # Get full model C-index (reuse from comparison)
                            res_full = fit_cox_cindex(
                                clinical_col_names + [col], time_col, event_col, d, n_boot, seed
                            )
                            if res_full is not None:
                                row['full_auc'] = res_full[2]
                                row['full_ci_l'] = res_full[3]
                                row['full_ci_u'] = res_full[4]
                            else:
                                row['full_auc'] = None
                            row['delta'] = delta
                            row['delta_ci_l'] = delta_ci_l
                            row['delta_ci_u'] = delta_ci_u
                            row['delta_p'] = p
                        else:
                            row['cm_auc'] = None
                            row['full_auc'] = None
                            row['delta'] = None
                            row['delta_p'] = None
                    else:
                        row['cm_auc'] = None
                        row['full_auc'] = None
                        row['delta'] = None
                        row['delta_p'] = None

            results.append(row)
            print(f"  {label}: done")

    return results, failed


# ═══════════════════════════════════════════════════════════════════════════════
# Formatting Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def fmt_p(p):
    """Format p-value."""
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "\u2013"
    if p < 0.001:
        return "<0.001*"
    elif p < 0.05:
        return f"{p:.3f}*"
    else:
        return f"{p:.3f}"


def fmt_auc(auc, ci_l, ci_u):
    """Format AUC/C-index with 95% CI."""
    if auc is None or (isinstance(auc, float) and np.isnan(auc)):
        return "\u2013"
    if ci_l is not None and ci_u is not None and not np.isnan(ci_l) and not np.isnan(ci_u):
        return f"{auc:.3f} ({ci_l:.3f}\u2013{ci_u:.3f})"
    return f"{auc:.3f}"


def fmt_delta(delta, ci_l=None, ci_u=None):
    """Format delta AUC/C-index."""
    if delta is None or (isinstance(delta, float) and np.isnan(delta)):
        return "\u2013"
    sign = "+" if delta >= 0 else ""
    if ci_l is not None and ci_u is not None and not np.isnan(ci_l) and not np.isnan(ci_u):
        return f"{sign}{delta:.3f} ({ci_l:.3f}\u2013{ci_u:.3f})"
    return f"{sign}{delta:.3f}"


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


def write_excel(results, config, df):
    """Write formatted Excel discrimination table."""
    analysis_type = config['analysis_type']
    cm = config['clinical_model']
    clinical_enabled = cm['enabled'] and len(cm['variables']) > 0
    metric_label = "C-index" if analysis_type == 'cox' else "AUC"
    output_path = config['output_file']

    # Compute overall sample info
    n_total = len(df)
    if analysis_type == 'cox':
        cs = config['cox_settings']
        n_events = int(pd.to_numeric(df[cs['event_column']], errors='coerce').sum())
        sample_info = f"n={n_total}, events={n_events}"
    else:
        oc = config['logistic_settings']['outcome_column']
        n_events = int(pd.to_numeric(df[oc], errors='coerce').sum())
        sample_info = f"n={n_total}, events={n_events}"

    # Determine columns
    if clinical_enabled:
        headers = [
            "Variable", "N", "Events",
            f"{metric_label}\n(variable alone)\n[95% CI]",
            f"{metric_label}\n(clinical model)\n[95% CI]",
            f"{metric_label}\n(clinical model\n+ variable)\n[95% CI]",
            f"Delta {metric_label}\n[95% CI]",
            "p-value"
        ]
        n_cols = 8
        col_widths = {1: 30, 2: 10, 3: 10, 4: 26, 5: 26, 6: 28, 7: 26, 8: 12}
    else:
        headers = [
            "Variable", "N", "Events",
            f"{metric_label} [95% CI]"
        ]
        n_cols = 4
        col_widths = {1: 30, 2: 10, 3: 10, 4: 26}

    wb = Workbook()
    ws = wb.active
    ws.title = f"{metric_label} Analysis"

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

    # Column widths
    for c, w in col_widths.items():
        ws.column_dimensions[get_column_letter(c)].width = w

    row_idx = 1

    # Row 1: Title
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=n_cols)
    cell = ws.cell(row=row_idx, column=1,
                   value=config.get('title', f'{metric_label} Discrimination Analysis'))
    cell.font = title_font
    cell.fill = title_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    for c in range(1, n_cols + 1):
        ws.cell(row=row_idx, column=c).fill = title_fill
    row_idx += 1

    # Row 2: Subtitle
    subtitle = config.get('subtitle', '')
    if subtitle:
        subtitle_text = f"{subtitle} ({sample_info})"
    else:
        subtitle_text = sample_info
    ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=n_cols)
    cell = ws.cell(row=row_idx, column=1, value=subtitle_text)
    cell.font = subtitle_font
    cell.fill = title_fill
    cell.alignment = Alignment(horizontal='center', vertical='center')
    for c in range(1, n_cols + 1):
        ws.cell(row=row_idx, column=c).fill = title_fill
    row_idx += 1

    # Row 3: Column headers
    for i, h in enumerate(headers, 1):
        cell = ws.cell(row=row_idx, column=i, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = THIN_BORDER
    ws.row_dimensions[row_idx].height = 50
    row_idx += 1

    ws.freeze_panes = ws.cell(row=row_idx, column=1)

    # Data rows
    current_section = None
    data_row_idx = 0

    for result in results:
        # Section header
        if result['section'] != current_section:
            current_section = result['section']
            ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=n_cols)
            cell = ws.cell(row=row_idx, column=1, value=current_section)
            cell.font = section_font
            cell.fill = section_fill
            cell.alignment = Alignment(horizontal='left', vertical='center')
            for c in range(1, n_cols + 1):
                ws.cell(row=row_idx, column=c).fill = section_fill
                ws.cell(row=row_idx, column=c).border = THIN_BORDER
            row_idx += 1
            data_row_idx = 0

        # Alternating row color
        row_fill = alt_fill if data_row_idx % 2 == 1 else no_fill

        # Column A: Variable
        ws.cell(row=row_idx, column=1, value=result['label']).font = data_font
        ws.cell(row=row_idx, column=1).fill = row_fill
        ws.cell(row=row_idx, column=1).alignment = Alignment(horizontal='left', vertical='center', indent=1)

        # Column B: N
        n_val = result.get('n')
        ws.cell(row=row_idx, column=2, value=n_val if n_val is not None else "\u2013").font = data_font

        # Column C: Events
        ev_val = result.get('events')
        ws.cell(row=row_idx, column=3, value=ev_val if ev_val is not None else "\u2013").font = data_font

        # Column D: AUC/C-index (variable alone)
        ws.cell(row=row_idx, column=4,
                value=fmt_auc(result.get('var_auc'), result.get('var_ci_l'), result.get('var_ci_u'))
                ).font = data_font

        if clinical_enabled:
            # Column E: AUC/C-index (clinical model)
            ws.cell(row=row_idx, column=5,
                    value=fmt_auc(result.get('cm_auc'), result.get('cm_ci_l'), result.get('cm_ci_u'))
                    ).font = data_font

            # Column F: AUC/C-index (clinical model + variable)
            ws.cell(row=row_idx, column=6,
                    value=fmt_auc(result.get('full_auc'), result.get('full_ci_l'), result.get('full_ci_u'))
                    ).font = data_font

            # Column G: Delta
            ws.cell(row=row_idx, column=7,
                    value=fmt_delta(result.get('delta'),
                                    result.get('delta_ci_l'),
                                    result.get('delta_ci_u'))
                    ).font = data_font

            # Column H: p-value
            p_val = result.get('delta_p')
            p_str = fmt_p(p_val)
            p_cell = ws.cell(row=row_idx, column=8, value=p_str)
            if p_val is not None and not (isinstance(p_val, float) and np.isnan(p_val)) and p_val < 0.05:
                p_cell.font = sig_font
            else:
                p_cell.font = data_font

        # Apply fill, alignment, border to all columns
        for c in range(1, n_cols + 1):
            ws.cell(row=row_idx, column=c).fill = row_fill
            if c > 1:
                ws.cell(row=row_idx, column=c).alignment = Alignment(horizontal='center', vertical='center')
            ws.cell(row=row_idx, column=c).border = THIN_BORDER

        row_idx += 1
        data_row_idx += 1

    # Footnotes
    row_idx += 1
    footnotes = []

    # Abbreviations
    if config.get('abbreviations'):
        footnotes.append(config['abbreviations'])

    # Clinical model composition
    if clinical_enabled:
        cm_labels = [v['label'] for v in cm['variables']]
        footnotes.append(f"Clinical model includes: {', '.join(cm_labels)}")

    # Statistical method note
    if clinical_enabled:
        if analysis_type == 'logistic':
            footnotes.append(f"Delta {metric_label} p-value computed via DeLong test.")
        else:
            n_boot = config['bootstrap']['n_iterations']
            footnotes.append(f"Delta {metric_label} p-value computed via paired bootstrap ({n_boot} iterations).")

    footnotes.append("* p < 0.05")

    for fn in footnotes:
        ws.merge_cells(start_row=row_idx, start_column=1, end_row=row_idx, end_column=n_cols)
        cell = ws.cell(row=row_idx, column=1, value=fn)
        cell.font = footnote_font
        cell.alignment = Alignment(horizontal='left', vertical='center')
        row_idx += 1

    # Save
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    wb.save(output_path)
    print(f"\nExcel saved: {output_path}")

    # Also save CSV
    csv_path = os.path.splitext(output_path)[0] + '.csv'
    rows_csv = []
    for r in results:
        csv_row = {
            'Variable': r['label'],
            'N': r.get('n', ''),
            'Events': r.get('events', ''),
            f'{metric_label} (variable alone)': fmt_auc(r.get('var_auc'), r.get('var_ci_l'), r.get('var_ci_u')),
        }
        if clinical_enabled:
            csv_row[f'{metric_label} (clinical model)'] = fmt_auc(r.get('cm_auc'), r.get('cm_ci_l'), r.get('cm_ci_u'))
            csv_row[f'{metric_label} (clinical model + variable)'] = fmt_auc(r.get('full_auc'), r.get('full_ci_l'), r.get('full_ci_u'))
            csv_row[f'Delta {metric_label}'] = fmt_delta(r.get('delta'), r.get('delta_ci_l'), r.get('delta_ci_u'))
            csv_row['p-value'] = fmt_p(r.get('delta_p'))
        rows_csv.append(csv_row)
    pd.DataFrame(rows_csv).to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"CSV saved: {csv_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_academic_style():
    """academic-style integration (Wave 3, Excel + ROC). Consumes --style=<journal>
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
        print(f"  Applied {_AS_STYLE} journal style")

    if len(sys.argv) < 2:
        print("Usage: python auc_cstat.py config.json [--check-missing] [--style=<journal>]")
        sys.exit(1)

    config_path = sys.argv[1]
    check_only = '--check-missing' in sys.argv

    config = load_config(config_path)
    print(f"Loading data: {config['data_file']}")
    df = load_data(config)
    print(f"Data loaded: {df.shape[0]} rows, {df.shape[1]} columns")

    if check_only:
        report = check_missing(df, config)
        print(report)
        return

    print(f"\nRunning {config['analysis_type'].upper()} discrimination analysis...")
    print(f"Metric: {'C-index' if config['analysis_type'] == 'cox' else 'AUC'}")
    if config['clinical_model']['enabled']:
        print(f"Clinical model: {len(config['clinical_model']['variables'])} variables")
    print(f"Evaluation variables: {sum(len(s['variables']) for s in config['sections'])}")
    print(f"Missing data handling: {config['missing_data_handling']}")
    if config['analysis_type'] == 'cox':
        print(f"Bootstrap iterations: {config['bootstrap']['n_iterations']}")
    print()

    # Apply listwise deletion if configured
    if config['missing_data_handling'] == 'listwise':
        df = apply_listwise_deletion(df, config)
        print(f"After listwise deletion: n={len(df)}")
        print()

    results, failed = run_analysis(config, df)

    # Summary
    metric_label = "C-index" if config['analysis_type'] == 'cox' else "AUC"
    print(f"\n{'='*60}")
    print("ANALYSIS SUMMARY")
    print(f"{'='*60}")

    # Find best variable
    valid_results = [r for r in results if r.get('var_auc') is not None]
    if valid_results:
        best = max(valid_results, key=lambda r: r['var_auc'])
        print(f"Best single variable: {best['label']} ({metric_label}={best['var_auc']:.3f})")

    if config['clinical_model']['enabled']:
        cm_vals = [r.get('cm_auc') for r in results if r.get('cm_auc') is not None]
        if cm_vals:
            print(f"Clinical model {metric_label}: {cm_vals[0]:.3f}")

        n_sig = sum(1 for r in results
                    if r.get('delta_p') is not None
                    and not (isinstance(r['delta_p'], float) and np.isnan(r['delta_p']))
                    and r['delta_p'] < 0.05)
        print(f"Variables with significant incremental value (p<0.05): {n_sig}")

    if failed:
        print(f"Failed/skipped variables: {', '.join(failed)}")

    print(f"{'='*60}")

    # Write Excel
    write_excel(results, config, df)

    # ── QC Warnings ──────────────────────────────────────────────────────────
    # P-4 batch (2026-05-07 partitioned-flame audit): track blocking emissions and
    # sys.exit(2) at the end so the pipeline sees a non-zero exit when [QC_BLOCKING]
    # is raised. Previously [QC_BLOCKING] was emitted but exit was always 0.
    qc_blocking_count = 0

    def _qc_block(msg):
        nonlocal qc_blocking_count
        print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
        qc_blocking_count += 1

    try:
        analysis_type = config['analysis_type']

        # Check events < 5
        if analysis_type == 'cox':
            cs = config['cox_settings']
            total_events = int(pd.to_numeric(df[cs['event_column']], errors='coerce').sum())
        else:
            oc = config['logistic_settings']['outcome_column']
            total_events = int(pd.to_numeric(df[oc], errors='coerce').sum())
        if total_events < 5:
            _qc_block(f"Total events = {total_events} (< 5)")

        # Check model convergence (indicated by all variables in 'failed')
        if failed and len(failed) == sum(len(s['variables']) for s in config['sections']):
            _qc_block("Model did not converge for any variable")

        # Check any group n < 30 (overall sample)
        if len(df) < 30:
            print(f"[QC_WARNING] Overall sample has n={len(df)} (< 30)", file=sys.stderr)
    except Exception as e:
        # P-5 territory partial: surface the QC failure rather than silent swallow
        print(f"[QC_WARNING] QC block raised: {type(e).__name__}: {e}", file=sys.stderr)

    if qc_blocking_count > 0:
        sys.exit(2)


if __name__ == '__main__':
    main()
