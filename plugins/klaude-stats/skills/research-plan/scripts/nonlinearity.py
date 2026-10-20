#!/usr/bin/env python3
"""
Restricted Cubic Splines — non-linearity of continuous covariates
(research-plan pipeline, references/advanced_analyses.md section 3)

The pipeline's `covariates[].scale` only divides; that silently assumes the
log-hazard / log-odds is linear in the covariate. Age, eGFR, BMI and blood
pressure almost never are. This script refits every requested continuous
covariate as a restricted cubic spline **inside the adjusted model**, tests
whether the non-linear terms are jointly zero, and writes out the curve so a
reader can redraw it.

Usage:
    python nonlinearity.py config.json                  # full run
    python nonlinearity.py config.json --check-missing  # preview only, no models

Config (mode = "rcs"):
    {"mode":"rcs","data_file":"...","filters":[],"derived_variables":[],
     "grouping":{"column":"AF","groups":[{"value":1,"label":"AF"},
                                         {"value":0,"label":"No AF"}]},
     "analysis_type":"cox",
     "cox_settings":{"time_column":"t","event_column":"e"},
     "logistic_settings":null,
     "sections":[{"header":"...","variables":[{"column":"age","type":"continuous",
                                               "label":"Age"}]}],
     "spline_variables":["age","egfr"],
     "spline_settings":{"knots":4,"knot_percentiles":null,"reference":null},
     "title":"...","subtitle":"...",
     "output_file":".../RCS_primary.xlsx","plot_file":".../RCS_primary.png"}

Design notes
------------
* One model per spline variable: that variable is expanded into an RCS basis,
  every other covariate (and the grouping column) enters exactly as the main
  model has it. The curve is therefore an adjusted association, not a marginal
  one.
* Three nested fits per variable — full spline / linear-only / variable dropped
  — all on the identical complete-case rows, so the two likelihood-ratio tests
  are legitimate.
* Nothing is silently substituted. A variable that cannot support a spline is a
  [QC_BLOCKING] and the run exits 3 without writing an Excel file; it does not
  quietly fall back to a linear term.
"""

import sys
import os
import json
import math
import operator

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from scipy import stats as sps

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# QC messages are collected so the closing summary mirrors what the runner
# scraped off stderr.
_QC_MESSAGES = []


def qc(kind, message):
    """Emit a QC line on stderr with the prefix run_pipeline.py greps for.

    Written flush-left with no leading whitespace: the runner strips nothing and
    matches on the line start.
    """
    line = f"[QC_{kind}] {message}"
    _QC_MESSAGES.append(line)
    print(line, file=sys.stderr)


def qc_warning(message):
    qc('WARNING', message)


def qc_blocking(message):
    qc('BLOCKING', message)


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

# Harrell (Regression Modeling Strategies, 2nd ed., table 2.3) knot percentiles.
HARRELL_PERCENTILES = {
    3: [10.0, 50.0, 90.0],
    4: [5.0, 35.0, 65.0, 95.0],
    5: [5.0, 27.5, 50.0, 72.5, 95.0],
    6: [5.0, 23.0, 41.0, 59.0, 77.0, 95.0],
    7: [2.5, 18.33, 34.17, 50.0, 65.83, 81.67, 97.5],
}

MIN_EVENTS_PER_SPLINE_PARAM = 10
SMALL_N_KNOT_DOWNGRADE = 100      # n < 100 -> 3 knots (advanced_analyses.md s3)
MAX_SAFE_KNOTS = 5                # above this the tails go confidently wrong; see the
                                  # knots sweep recorded in advanced_analyses.md s3
DIVERGENCE_ABS_COEF = 20.0        # |beta| beyond this is separation, not a fit


def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    config.setdefault('mode', 'rcs')
    config.setdefault('filters', [])
    config.setdefault('derived_variables', [])
    config.setdefault('sections', [])
    config.setdefault('spline_variables', [])
    config.setdefault('title', '')
    config.setdefault('subtitle', '')
    config.setdefault('cox_settings', None)
    config.setdefault('logistic_settings', None)
    config.setdefault('analysis_type', 'cox')

    ss = config.setdefault('spline_settings', {})
    ss.setdefault('knots', 4)
    ss.setdefault('knot_percentiles', None)
    ss.setdefault('reference', None)
    ss.setdefault('grid_points', 100)

    if config['mode'] != 'rcs':
        sys.exit(f"[FATAL] Unknown mode: {config['mode']!r} (expected 'rcs')")
    if config['analysis_type'] not in ('cox', 'logistic'):
        sys.exit(f"[FATAL] Unknown analysis_type: {config['analysis_type']!r} "
                 f"(expected 'cox' or 'logistic')")
    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Data loading (identical semantics to missing_data.py / univariate_forest.py)
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
    elif ext == '.tsv':
        df = pd.read_csv(path, sep='\t')
    elif ext == '.sas7bdat':
        df = pd.read_sas(path)
    elif ext == '.dta':
        df = pd.read_stata(path)
    else:
        df = pd.read_csv(path)

    for f in config['filters']:
        col, op, val = f['column'], f['operator'], f['value']
        if op in OPS:
            df = df[OPS[op](pd.to_numeric(df[col], errors='coerce'), val)]
        elif op == 'in':
            df = df[df[col].isin(val)]
        elif op == 'not_in':
            df = df[~df[col].isin(val)]

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

    return df.reset_index(drop=True)


def normalize_series(df, col, var_type):
    """Blank-aware NA handling: categoricals keep their labels, everything else
    is coerced to numeric."""
    s = df[col]
    if var_type == 'categorical':
        return s.where(s.notna() & (s.astype(str).str.strip() != ''), np.nan)
    return pd.to_numeric(s, errors='coerce')


def collect_variables(config):
    """[{column, type, label, scale, reference_level, section}] from sections."""
    out = []
    for section in config['sections']:
        for v in section['variables']:
            out.append({
                'column': v['column'],
                'type': v.get('type', 'continuous'),
                'label': v.get('label', v['column']),
                'scale': v.get('scale'),
                'reference_level': v.get('reference_level'),
                'section': section.get('header', ''),
            })
    return out


def outcome_columns(config):
    if config['analysis_type'] == 'cox':
        cs = config['cox_settings'] or {}
        return [cs.get('time_column'), cs.get('event_column')]
    ls = config['logistic_settings'] or {}
    return [ls.get('outcome_column')]


def grouping_column(config):
    gc = config.get('grouping')
    return gc.get('column') if gc else None


# ═══════════════════════════════════════════════════════════════════════════════
# Model matrix
# ═══════════════════════════════════════════════════════════════════════════════

def _prepare_categorical(d, col, var_type, reference_level, context_label=""):
    """Set the reference level and dummy-encode (drop_first=True).

    Lifted verbatim from univariate_forest.py so the reference-level behaviour is
    identical across the pipeline. Continuous covariates pass through untouched.
    """
    if var_type != 'categorical':
        return d, [col]

    non_na = d[col].dropna()
    unique_vals = sorted(non_na.unique().tolist(), key=lambda x: str(x))
    if len(unique_vals) < 2:
        return d, [col]

    if reference_level is None:
        first_cat = unique_vals[0]
        qc_warning(f"{col}: no reference_level specified, using alphabetical first "
                   f"({first_cat}). This may not match research_plan.")
        ref = first_cat
    else:
        ref = reference_level
        if ref not in unique_vals:
            qc_warning(f"{col}: reference_level '{ref}' not present in data "
                       f"{context_label}; falling back to alphabetical first "
                       f"({unique_vals[0]}).")
            ref = unique_vals[0]

    ordered = [ref] + [c for c in unique_vals if c != ref]
    d = d.copy()
    d[col] = pd.Categorical(d[col], categories=ordered)
    d = pd.get_dummies(d, columns=[col], prefix=col, drop_first=True, dtype=float)
    dummy_cols = [f"{col}_{c}" for c in ordered[1:]]
    dummy_cols = [c for c in dummy_cols if c in d.columns]
    return d, dummy_cols


def build_design(df, config, variables, spline_col):
    """Complete-case design matrix for one spline variable's model.

    Returns (design_df, adjust_cols, label_map). `design_df` carries the outcome
    columns plus every adjustment covariate but NOT the spline basis: the basis
    is added per-model so that the full / linear / dropped fits share rows.
    """
    grp = grouping_column(config)
    out_cols = [c for c in outcome_columns(config) if c]

    model_vars = [v for v in variables if v['column'] != spline_col]
    if grp and grp not in [v['column'] for v in model_vars]:
        model_vars = [{'column': grp, 'type': 'binary', 'label': grp,
                       'scale': None, 'reference_level': None,
                       'section': 'Exposure'}] + model_vars

    needed = [spline_col] + [v['column'] for v in model_vars] + out_cols
    needed = [c for c in dict.fromkeys(needed)]
    missing_cols = [c for c in needed if c not in df.columns]
    if missing_cols:
        return None, None, None, missing_cols

    d = df[needed].copy()
    for v in model_vars:
        d[v['column']] = normalize_series(d, v['column'], v['type'])
    d[spline_col] = pd.to_numeric(d[spline_col], errors='coerce')
    for c in out_cols:
        d[c] = pd.to_numeric(d[c], errors='coerce')

    d = d.dropna(subset=needed).reset_index(drop=True)

    adjust_cols, label_map = [], {}
    for v in model_vars:
        col, vtype = v['column'], v['type']
        if vtype == 'categorical':
            d, dummies = _prepare_categorical(d, col, vtype, v['reference_level'],
                                              context_label=f"(spline model for {spline_col})")
            for dc in dummies:
                label_map[dc] = f"{v['label']}: {dc[len(col) + 1:]}"
            adjust_cols += dummies
        else:
            if v['scale']:
                d[col] = d[col] / v['scale']
                label_map[col] = f"{v['label']} (per {v['scale']})"
            else:
                label_map[col] = v['label']
            adjust_cols.append(col)

    # Zero-variance covariates cannot be estimated; drop them loudly.
    keep = []
    for c in adjust_cols:
        if d[c].nunique(dropna=True) < 2:
            qc_warning(f"{spline_col} model: dropped adjustment covariate '{c}' "
                       f"(zero variance in the complete-case rows)")
        else:
            keep.append(c)
    return d, keep, label_map, []


# ═══════════════════════════════════════════════════════════════════════════════
# Restricted cubic spline basis (Harrell / rms parameterisation)
# ═══════════════════════════════════════════════════════════════════════════════

def rcs_basis(x, knots):
    """Restricted cubic spline basis, k knots -> k-1 columns.

    Column 0 is x itself; columns 1..k-2 are the non-linear terms. The
    parameterisation is Harrell's (rms::rcspline.eval), i.e. the function is
    forced to be linear before the first and after the last knot, and the
    non-linear terms are scaled by (t_k - t_1)^2 for numerical conditioning.
    """
    x = np.asarray(x, dtype=float)
    t = np.asarray(knots, dtype=float)
    k = len(t)
    if k < 3:
        raise ValueError("restricted cubic splines need at least 3 knots")
    denom = (t[-1] - t[0]) ** 2

    def cube_plus(u):
        return np.where(u > 0, u ** 3, 0.0)

    cols = [x]
    span = t[k - 1] - t[k - 2]
    for j in range(k - 2):
        term = (cube_plus(x - t[j])
                - cube_plus(x - t[k - 2]) * (t[k - 1] - t[j]) / span
                + cube_plus(x - t[k - 1]) * (t[k - 2] - t[j]) / span)
        cols.append(term / denom)
    return np.column_stack(cols)


def choose_knots(values, n_knots, percentiles):
    """(knot_values, percentiles_used). Percentiles come from the config when
    given, otherwise from Harrell's table for that number of knots."""
    if percentiles:
        pcts = [float(p) for p in percentiles]
    else:
        pcts = HARRELL_PERCENTILES[n_knots]
    knots = [float(np.percentile(values, p)) for p in pcts]
    return knots, pcts


# ═══════════════════════════════════════════════════════════════════════════════
# Model fitting
# ═══════════════════════════════════════════════════════════════════════════════

class FitFailure(Exception):
    pass


def fit_cox(d, model_cols, time_col, event_col):
    """Returns (loglik, params Series, covariance DataFrame, n, n_events)."""
    from lifelines import CoxPHFitter

    cols = list(dict.fromkeys(list(model_cols) + [time_col, event_col]))
    dd = d[cols].astype(float)
    try:
        cph = CoxPHFitter()
        cph.fit(dd, duration_col=time_col, event_col=event_col)
    except Exception as e:
        raise FitFailure(f"Cox model did not converge: {type(e).__name__}: {e}")

    params = cph.params_
    if not np.all(np.isfinite(params.values)):
        raise FitFailure("Cox model produced non-finite coefficients")
    if np.max(np.abs(params.values)) > DIVERGENCE_ABS_COEF:
        raise FitFailure(
            f"Cox coefficients diverged (max |beta| = {np.max(np.abs(params.values)):.1f}); "
            f"this is separation or collinearity, not a converged fit")
    cov = pd.DataFrame(cph.variance_matrix_, index=params.index, columns=params.index)
    return (float(cph.log_likelihood_), params, cov,
            int(len(dd)), int(dd[event_col].sum()))


def fit_logit(d, model_cols, outcome_col):
    """Returns (loglik, params Series, covariance DataFrame, n, n_events)."""
    import statsmodels.api as sm

    y = d[outcome_col].astype(float)
    X = sm.add_constant(d[list(model_cols)].astype(float), has_constant='add')
    try:
        res = sm.Logit(y, X).fit(disp=0, method='bfgs', maxiter=300)
    except Exception as e:
        raise FitFailure(f"Logistic model did not converge: {type(e).__name__}: {e}")

    if not res.mle_retvals.get('converged', True):
        raise FitFailure("Logistic model did not converge (statsmodels reported "
                         "converged = False)")
    params = res.params
    if not np.all(np.isfinite(params.values)):
        raise FitFailure("Logistic model produced non-finite coefficients")
    if np.max(np.abs(params.drop(index=['const'], errors='ignore').values)) > DIVERGENCE_ABS_COEF:
        raise FitFailure(
            f"Logistic coefficients diverged (max |beta| = "
            f"{np.max(np.abs(params.drop(index=['const'], errors='ignore').values)):.1f}); "
            f"this is quasi-complete separation, not a converged fit")
    cov = pd.DataFrame(res.cov_params(), index=params.index, columns=params.index)
    return float(res.llf), params, cov, int(len(y)), int(y.sum())


def fit_model(config, d, model_cols):
    if config['analysis_type'] == 'cox':
        cs = config['cox_settings']
        return fit_cox(d, model_cols, cs['time_column'], cs['event_column'])
    ls = config['logistic_settings']
    return fit_logit(d, model_cols, ls['outcome_column'])


# ═══════════════════════════════════════════════════════════════════════════════
# Per-variable RCS analysis
# ═══════════════════════════════════════════════════════════════════════════════

def validate_spline_variable(df, config, variables, col):
    """(ok, n_knots, message). Everything that makes a spline impossible is a
    blocking condition, checked before a single model is fitted."""
    ss = config['spline_settings']
    declared = {v['column']: v for v in variables}

    if col not in df.columns:
        return False, None, f"spline variable '{col}' does not exist in the data file"

    if col in declared and declared[col]['type'] != 'continuous':
        return False, None, (f"spline variable '{col}' is declared as "
                             f"type = '{declared[col]['type']}' in the config sections; "
                             f"restricted cubic splines apply to continuous variables only")

    s = pd.to_numeric(df[col], errors='coerce')
    n_obs = int(s.notna().sum())
    if n_obs == 0:
        return False, None, (f"spline variable '{col}' has no numeric values "
                             f"(it is not a continuous variable)")

    n_unique = int(s.dropna().nunique())
    n_knots = int(ss['knots'])
    if ss['knot_percentiles']:
        n_knots = len(ss['knot_percentiles'])
    elif n_obs < SMALL_N_KNOT_DOWNGRADE and n_knots > 3:
        n_knots = 3
    if n_knots < 3:
        return False, None, (f"spline settings request {n_knots} knots for '{col}'; "
                             f"restricted cubic splines need at least 3")
    if n_knots not in HARRELL_PERCENTILES and not ss['knot_percentiles']:
        return False, None, (f"no default knot percentiles for {n_knots} knots "
                             f"(supported: {sorted(HARRELL_PERCENTILES)}); supply "
                             f"spline_settings.knot_percentiles explicitly")
    if n_knots > MAX_SAFE_KNOTS:
        qc_warning(
            f"'{col}': {n_knots} knots requested. Measured on a known quadratic "
            f"(n=8000, 6929 events, 2026-08-11): 4 knots recovered the curve to a mean "
            f"absolute error of 0.03 in log-HR, while 7 knots was off by ~1.3 in both "
            f"tails WITH A SMALL STANDARD ERROR — confidently wrong, not merely "
            f"uncertain. More knots is not a route to a better fit here. If you raise "
            f"this, inspect the tails of the curve against the data before reporting.")

    if n_unique < 6:
        return False, None, (f"spline variable '{col}' has only {n_unique} distinct "
                             f"values — too few to place {n_knots} knots; this looks "
                             f"categorical or ordinal, not continuous")
    knots, _ = choose_knots(s.dropna().values, n_knots, ss['knot_percentiles'])
    if len(set(np.round(knots, 10))) < n_knots:
        return False, None, (f"spline variable '{col}' has a distribution too "
                             f"concentrated to place {n_knots} distinct knots "
                             f"(knot values collapse to {sorted(set(np.round(knots, 4)))})")
    return True, n_knots, ''


def analyse_variable(config, df, variables, col, n_knots):
    """Fit the three nested models and build the curve. Raises FitFailure."""
    ss = config['spline_settings']
    label = next((v['label'] for v in variables if v['column'] == col), col)

    d, adjust_cols, label_map, missing_cols = build_design(df, config, variables, col)
    if missing_cols:
        raise FitFailure(f"columns not found in the data: {', '.join(missing_cols)}")
    if len(d) == 0:
        raise FitFailure(f"no complete cases remain for the '{col}' spline model")

    x = d[col].astype(float).values
    knots, pcts = choose_knots(x, n_knots, ss['knot_percentiles'])
    basis = rcs_basis(x, knots)
    basis_cols = [f"{col}__rcs{i + 1}" for i in range(basis.shape[1])]
    for i, bc in enumerate(basis_cols):
        d[bc] = basis[:, i]

    ref = ss['reference']
    ref_source = 'config spline_settings.reference'
    if ref is None:
        ref = float(np.median(x))
        ref_source = 'median of the analysed (complete-case) values — script default'
    ref = float(ref)

    full_cols = basis_cols + list(adjust_cols)
    lin_cols = [basis_cols[0]] + list(adjust_cols)
    drop_cols = list(adjust_cols)

    ll_full, params, cov, n, n_events = fit_model(config, d, full_cols)
    ll_lin, _, _, _, _ = fit_model(config, d, lin_cols)
    if drop_cols:
        ll_drop, _, _, _, _ = fit_model(config, d, drop_cols)
    else:
        ll_drop = None

    df_nonlin = len(basis_cols) - 1
    lr_nonlin = 2.0 * (ll_full - ll_lin)
    lr_nonlin = max(lr_nonlin, 0.0)
    p_nonlin = float(sps.chi2.sf(lr_nonlin, df_nonlin)) if df_nonlin > 0 else float('nan')

    if ll_drop is not None:
        lr_overall = max(2.0 * (ll_full - ll_drop), 0.0)
        p_overall = float(sps.chi2.sf(lr_overall, len(basis_cols)))
    else:
        lr_overall = p_overall = float('nan')

    # Linear-term-only model, reported side by side so the reader can see what
    # the main (linear) analysis would have claimed.
    _, lin_params, lin_cov, _, _ = fit_model(config, d, lin_cols)
    b_lin = float(lin_params[basis_cols[0]])
    se_lin = float(np.sqrt(lin_cov.loc[basis_cols[0], basis_cols[0]]))
    linear_effect = {
        'coef': b_lin, 'se': se_lin,
        'effect': math.exp(b_lin),
        'ci_lower': math.exp(b_lin - 1.96 * se_lin),
        'ci_upper': math.exp(b_lin + 1.96 * se_lin),
        'p': float(2 * sps.norm.sf(abs(b_lin / se_lin))) if se_lin > 0 else float('nan'),
    }

    # ── curve, centred on the reference value ──────────────────────────────
    beta = params[basis_cols].values.astype(float)
    V = cov.loc[basis_cols, basis_cols].values.astype(float)
    lo_x, hi_x = float(np.percentile(x, 1)), float(np.percentile(x, 99))
    n_grid = int(ss.get('grid_points') or 100)
    grid = np.unique(np.concatenate([
        np.linspace(lo_x, hi_x, n_grid), np.array([ref]), np.array(knots)]))
    grid = grid[(grid >= min(lo_x, ref, min(knots))) & (grid <= max(hi_x, ref, max(knots)))]

    B = rcs_basis(grid, knots) - rcs_basis(np.array([ref]), knots)
    log_effect = B @ beta
    var = np.einsum('ij,jk,ik->i', B, V, B)
    var = np.clip(var, 0.0, None)
    se = np.sqrt(var)

    curve = {
        'x': grid,
        'log_effect': log_effect,
        'se': se,
        'effect': np.exp(log_effect),
        'lower': np.exp(log_effect - 1.96 * se),
        'upper': np.exp(log_effect + 1.96 * se),
    }

    n_spline_params = len(basis_cols)
    return {
        'column': col, 'label': label,
        'n': n, 'n_events': n_events,
        'n_knots': n_knots, 'knots': knots, 'knot_percentiles': pcts,
        'knot_source': ('config spline_settings.knot_percentiles'
                        if ss['knot_percentiles'] else
                        f'Harrell default percentiles for {n_knots} knots'),
        'reference': ref, 'reference_source': ref_source,
        'spline_df': n_spline_params, 'nonlinear_df': df_nonlin,
        'lr_nonlinear': lr_nonlin, 'p_nonlinear': p_nonlin,
        'lr_overall': lr_overall, 'p_overall': p_overall,
        'events_per_spline_param': (n_events / n_spline_params) if n_spline_params else float('nan'),
        'linear': linear_effect,
        'curve': curve,
        'x_values': x,
        'adjust_cols': list(adjust_cols),
        'label_map': label_map,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Excel style constants (shared with the other pipeline sub-skills)
# ═══════════════════════════════════════════════════════════════════════════════

DARK_BLUE = "1F3864"
HEADER_BG = "2E5FA3"
ALT_ROW = "F7FAFD"
SIG_COLOR = "C00000"
BORDER_COLOR = "BFBFBF"
FOOTNOTE_COLOR = "595959"
FLAG_BG = "FDEBD0"

THIN_BORDER = Border(
    left=Side(style='thin', color=BORDER_COLOR),
    right=Side(style='thin', color=BORDER_COLOR),
    top=Side(style='thin', color=BORDER_COLOR),
    bottom=Side(style='thin', color=BORDER_COLOR),
)

TITLE_FONT = Font(name='Arial', size=12, bold=True, color="FFFFFF")
SUBTITLE_FONT = Font(name='Arial', size=10, italic=True, color="FFFFFF")
HEADER_FONT = Font(name='Arial', size=10, bold=True, color="FFFFFF")
DATA_FONT = Font(name='Arial', size=10)
SIG_FONT = Font(name='Arial', size=10, bold=True, color=SIG_COLOR)
FOOTNOTE_FONT = Font(name='Arial', size=8, italic=True, color=FOOTNOTE_COLOR)

TITLE_FILL = PatternFill(start_color=DARK_BLUE, end_color=DARK_BLUE, fill_type='solid')
HEADER_FILL = PatternFill(start_color=HEADER_BG, end_color=HEADER_BG, fill_type='solid')
ALT_FILL = PatternFill(start_color=ALT_ROW, end_color=ALT_ROW, fill_type='solid')
FLAG_FILL = PatternFill(start_color=FLAG_BG, end_color=FLAG_BG, fill_type='solid')

CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT = Alignment(horizontal='left', vertical='center', indent=1, wrap_text=True)


def sheet_header(ws, title, subtitle, headers, widths):
    ncol = len(headers)
    for c, w in zip(range(1, ncol + 1), widths):
        ws.column_dimensions[get_column_letter(c)].width = w

    r = 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
    cell = ws.cell(row=r, column=1, value=title)
    cell.font = TITLE_FONT
    cell.alignment = CENTER
    for c in range(1, ncol + 1):
        ws.cell(row=r, column=c).fill = TITLE_FILL
    r += 1

    if subtitle:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
        cell = ws.cell(row=r, column=1, value=subtitle)
        cell.font = SUBTITLE_FONT
        cell.alignment = CENTER
        for c in range(1, ncol + 1):
            ws.cell(row=r, column=c).fill = TITLE_FILL
        r += 1

    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER
    r += 1
    ws.freeze_panes = ws.cell(row=r, column=1)
    return r


def write_row(ws, r, values, alt=False, flag=False, bold_cols=(), sig_cols=()):
    for c, v in enumerate(values, 1):
        cell = ws.cell(row=r, column=c, value=v)
        cell.font = SIG_FONT if c in sig_cols else DATA_FONT
        if c in bold_cols:
            cell.font = Font(name='Arial', size=10, bold=True)
        cell.border = THIN_BORDER
        cell.alignment = LEFT if c == 1 else CENTER
        if flag:
            cell.fill = FLAG_FILL
        elif alt:
            cell.fill = ALT_FILL
    return r + 1


def write_footnote(ws, r, ncol, text):
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
    cell = ws.cell(row=r, column=1, value=text)
    cell.font = FOOTNOTE_FONT
    cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
    ws.row_dimensions[r].height = max(14, 12 * (1 + text.count('\n')))
    return r + 1


def fmt_p(p):
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "N/A"
    if p < 0.001:
        return "<0.001*"
    if p < 0.05:
        return f"{p:.3f}*"
    return f"{p:.3f}"


def fmt_num(x, nd=3):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "N/A"
    return f"{x:.{nd}f}"


def fmt_effect(effect, lo, hi):
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in (effect, lo, hi)):
        return "N/A"
    return f"{effect:.2f} ({lo:.2f}–{hi:.2f})"


# ═══════════════════════════════════════════════════════════════════════════════
# Excel output
# ═══════════════════════════════════════════════════════════════════════════════

def write_excel(config, results, n_total):
    wb = Workbook()
    is_cox = config['analysis_type'] == 'cox'
    eff_name = 'HR' if is_cox else 'OR'
    title = config.get('title') or 'Restricted cubic spline (non-linearity) analysis'
    subtitle = config.get('subtitle') or f'N = {n_total}'

    # ── 1. Estimand (first sheet: what is actually being estimated) ─────────
    ws = wb.active
    ws.title = 'Estimand'
    r = sheet_header(ws, title, subtitle, ['Item', 'Statement'], [34, 120])
    grp = grouping_column(config)
    outcome_txt = (f"time to {config['cox_settings']['event_column']} "
                   f"(follow-up column {config['cox_settings']['time_column']})"
                   if is_cox else
                   f"binary {config['logistic_settings']['outcome_column']}")
    rows = [
        ('Analysis', 'Restricted cubic spline (RCS) of one continuous covariate at a time, '
                     'inside the adjusted outcome model.'),
        ('Model', 'Cox proportional hazards' if is_cox else 'Logistic regression'),
        ('Outcome', outcome_txt),
        ('Exposure / grouping variable', grp or '(none declared)'),
        ('Estimand',
         f"The adjusted conditional association between the covariate and the outcome: "
         f"{eff_name}(x) = the {'hazard' if is_cox else 'odds'} at covariate value x divided by the "
         f"{'hazard' if is_cox else 'odds'} at the reference value, holding every other covariate in "
         f"the model fixed. It is a covariate-conditional contrast, NOT a marginal or population-level "
         f"effect, and NOT a causal effect unless the covariate set happens to be a sufficient "
         f"adjustment set for that covariate."),
        ('What p-nonlinear tests',
         "H0: the adjusted log-"
         + ('hazard' if is_cox else 'odds')
         + " is a straight line in this covariate, i.e. the non-linear spline terms are jointly zero. "
           "It is a likelihood-ratio test of the full spline model against the linear-term-only model "
           "fitted on identical rows."),
        ('What this does NOT estimate',
         "It does not estimate the effect of changing the covariate, does not adjust for the other "
         "spline variables' own non-linearity (each variable gets its own model), and does not replace "
         "the main analysis. Which specification is primary is a pre-specified decision that belongs in "
         "decision_log.md with a permanent ID."),
        ('Comparison with the main analysis',
         f"The Nonlinearity_tests sheet reports the linear-term {eff_name} per 1 unit from the same "
         f"adjusted model next to the spline result, so the reader can see exactly what the linear "
         f"specification would have claimed."),
    ]
    for i, (k, v) in enumerate(rows):
        r = write_row(ws, r, [k, v], alt=(i % 2 == 1), bold_cols=(1,))

    # ── 2. Nonlinearity_tests ──────────────────────────────────────────────
    ws = wb.create_sheet('Nonlinearity_tests')
    headers = ['Variable', 'Column', 'N', 'Events', 'Knots (k)', 'Knot percentiles',
               'Knot values', 'Reference value', 'Spline df', 'Non-linear df',
               'LR chi-square (non-linearity)', 'p-nonlinear',
               'Events per spline parameter', f'Linear-term {eff_name} per 1 unit (95% CI)',
               'Linear-term p', 'LR chi-square (overall)', 'p-overall', 'Flags']
    widths = [24, 16, 8, 9, 9, 22, 30, 14, 10, 12, 16, 12, 16, 26, 12, 16, 12, 46]
    r = sheet_header(ws, 'Non-linearity likelihood-ratio tests', subtitle, headers, widths)
    for i, res in enumerate(results):
        flags = []
        if res['events_per_spline_param'] < MIN_EVENTS_PER_SPLINE_PARAM:
            flags.append(f"< {MIN_EVENTS_PER_SPLINE_PARAM} events per spline parameter "
                         f"(overfitting risk)")
        if not math.isnan(res['p_nonlinear']) and res['p_nonlinear'] >= 0.05:
            flags.append("no statistically significant departure from linearity detected "
                         "(this is NOT evidence that linearity is correct)")
        vals = [res['label'], res['column'], res['n'], res['n_events'], res['n_knots'],
                ', '.join(f"{p:g}" for p in res['knot_percentiles']),
                ', '.join(f"{k:.4g}" for k in res['knots']),
                f"{res['reference']:.4g}",
                res['spline_df'], res['nonlinear_df'],
                fmt_num(res['lr_nonlinear'], 2), fmt_p(res['p_nonlinear']),
                fmt_num(res['events_per_spline_param'], 1),
                fmt_effect(res['linear']['effect'], res['linear']['ci_lower'],
                           res['linear']['ci_upper']),
                fmt_p(res['linear']['p']),
                fmt_num(res['lr_overall'], 2), fmt_p(res['p_overall']),
                ' | '.join(flags) if flags else '']
        sig = (12,) if (not math.isnan(res['p_nonlinear']) and res['p_nonlinear'] < 0.05) else ()
        r = write_row(ws, r, vals, alt=(i % 2 == 1), sig_cols=sig, flag=bool(flags))
    r += 1
    r = write_footnote(
        ws, r, len(headers),
        "p-nonlinear is a likelihood-ratio test of the full restricted cubic spline against the "
        "linear-term-only model, fitted on identical complete-case rows with the same adjustment set; "
        f"df = k - 2. p-overall tests the whole spline block (df = k - 1) against dropping the variable. "
        "READING RULE (advanced_analyses.md section 3): p-nonlinear >= 0.05 does NOT mean linearity is "
        "correct — it means this sample size did not detect a departure from it. To argue that a linear "
        "term is adequate you must also look at the shape of the fitted curve and the width of its "
        "confidence band in Spline_estimates / the PNG. When there are fewer than "
        f"{MIN_EVENTS_PER_SPLINE_PARAM} events per spline parameter the spline is prone to overfitting "
        "and a linear term with an explicit limitation is the safer report. "
        "All defaults used here (number of knots, knot percentiles, reference value) are methodological "
        "choices that must be registered in decision_log.md with a permanent ID.")

    # ── 3. Spline_estimates ────────────────────────────────────────────────
    ws = wb.create_sheet('Spline_estimates')
    headers = ['Variable', 'Column', 'x', f'{eff_name} vs reference', 'CI lower', 'CI upper',
               f'log {eff_name}', f'SE(log {eff_name})', 'At a knot?', 'Reference point?']
    r = sheet_header(ws, f'Fitted spline curve ({eff_name} relative to the reference value)',
                     subtitle, headers, [24, 16, 12, 16, 12, 12, 14, 14, 11, 14])
    for res in results:
        c = res['curve']
        knot_set = {round(k, 10) for k in res['knots']}
        for i in range(len(c['x'])):
            xv = float(c['x'][i])
            is_knot = round(xv, 10) in knot_set
            is_ref = abs(xv - res['reference']) < 1e-12
            r = write_row(ws, r, [res['label'], res['column'], round(xv, 6),
                                  round(float(c['effect'][i]), 6),
                                  round(float(c['lower'][i]), 6),
                                  round(float(c['upper'][i]), 6),
                                  round(float(c['log_effect'][i]), 6),
                                  round(float(c['se'][i]), 6),
                                  'yes' if is_knot else '',
                                  'yes' if is_ref else ''],
                          alt=(i % 2 == 1), flag=is_ref)
    r += 1
    r = write_footnote(
        ws, r, len(headers),
        f"Every row is one point on the fitted curve, so the figure can be redrawn from this sheet "
        f"alone. {eff_name} at x is exp(b'(basis(x) - basis(reference))) from the adjusted spline model; "
        f"the confidence band is the delta-method standard error of that same contrast, which is why it "
        f"is exactly zero-width at the reference value. The grid spans the 1st to 99th percentile of the "
        f"analysed values plus the knot positions and the reference value; it is deliberately NOT "
        f"extended to the extremes, where a spline is extrapolating.")

    # ── 4. Method ──────────────────────────────────────────────────────────
    ws = wb.create_sheet('Method')
    r = sheet_header(ws, 'Method and methodological defaults', subtitle,
                     ['Item', 'Value / statement'], [40, 118])
    ss = config['spline_settings']
    meth_rows = [
        ('Spline family',
         "Restricted cubic spline (natural spline), Harrell parameterisation as in "
         "rms::rcspline.eval: linear beyond the outermost knots, non-linear terms scaled by "
         "(last knot - first knot)^2. k knots produce k-1 model terms."),
        ('Number of knots',
         f"{ss['knots']} requested in the config"
         + (f"; automatically reduced to 3 for any variable analysed on fewer than "
            f"{SMALL_N_KNOT_DOWNGRADE} observations (advanced_analyses.md section 3)"
            if not ss['knot_percentiles'] else
            "; overridden by an explicit knot_percentiles list")),
        ('Knot placement',
         'Explicit percentiles from the config: '
         + ', '.join(f"{p:g}" for p in ss['knot_percentiles'])
         if ss['knot_percentiles'] else
         "Harrell's recommended percentiles (Regression Modeling Strategies): "
         + '; '.join(f"{k} knots -> " + ', '.join(f"{p:g}" for p in v)
                     for k, v in sorted(HARRELL_PERCENTILES.items()) if k <= 5)
         + ". Percentiles are taken within each variable's own complete-case values, so different "
           "variables can have different knot values."),
        ('Reference value',
         ("Explicit value from spline_settings.reference: " + f"{ss['reference']}")
         if ss['reference'] is not None else
         "Not specified in the config; the median of each variable's analysed values was used. "
         "The SHAPE of the curve does not depend on this choice, but every single reported "
         f"{eff_name} does — it is always '{eff_name} relative to the reference'. The value used for "
         "each variable is printed in Nonlinearity_tests and marked in Spline_estimates."),
        ('Adjustment set',
         "Every covariate in the config sections plus the grouping/exposure column enters each model. "
         "The spline variable itself is replaced by its basis; the other covariates keep the same "
         "specification (and the same `scale` divisor) as the main analysis. Each spline variable is "
         "analysed in its own model — the other continuous covariates are NOT simultaneously splined."),
        ('Missing data',
         "Complete-case (listwise deletion) within each variable's model, so N can differ between "
         "variables. This mirrors the main pipeline's behaviour; see the Missingness / MI steps if "
         "that matters."),
        ('Non-linearity test',
         "Likelihood-ratio test, full spline model vs linear-term-only model on identical rows, "
         "df = k - 2. Reported as p-nonlinear."),
        ('Overall test',
         "Likelihood-ratio test, full spline model vs the model with the variable removed, "
         "df = k - 1. Reported as p-overall."),
        ('Confidence band',
         "Pointwise 95% delta-method interval on the log scale, exponentiated. It is pointwise, not "
         "simultaneous: do not read 'the whole curve lies inside this band with 95% confidence'."),
        ('Overfitting guard',
         f"Events per spline parameter is reported for every variable. Below "
         f"{MIN_EVENTS_PER_SPLINE_PARAM} the spline is flagged and a linear term with an explicit "
         f"limitation is the recommended report."),
        ('Reading rule',
         "p-nonlinear >= 0.05 does not establish linearity — it only means no departure was detected "
         "at this sample size. Judge the curve and its band as well."),
        ('Software',
         f"Python {sys.version.split()[0]}, "
         + ("lifelines CoxPHFitter" if is_cox else "statsmodels Logit")
         + ", spline basis implemented in this script."),
        ('Registration requirement',
         "Number of knots, knot percentiles and the reference value are methodological choices, not "
         "neutral defaults. Copy them into decision_log.md with a permanent ID before the results are "
         "used in a manuscript."),
    ]
    for i, (k, v) in enumerate(meth_rows):
        r = write_row(ws, r, [k, v], alt=(i % 2 == 1), bold_cols=(1,))

    out = config['output_file']
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    wb.save(out)
    return [w.title for w in wb.worksheets]


# ═══════════════════════════════════════════════════════════════════════════════
# Plot
# ═══════════════════════════════════════════════════════════════════════════════

def plot_results(config, results):
    path = config.get('plot_file')
    if not path or not results:
        return None
    is_cox = config['analysis_type'] == 'cox'
    eff_name = 'HR' if is_cox else 'OR'

    n = len(results)
    ncols = 1 if n == 1 else 2
    nrows = int(math.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(6.6 * ncols, 4.6 * nrows),
                             squeeze=False)

    for idx, res in enumerate(results):
        ax = axes[idx // ncols][idx % ncols]
        c = res['curve']
        x, eff, lo, hi = c['x'], c['effect'], c['lower'], c['upper']

        # distribution behind the curve
        ax2 = ax.twinx()
        ax2.hist(res['x_values'], bins=40, color='#BDC9DB', alpha=0.55, zorder=0)
        ax2.set_ylabel('Count', fontsize=8, color='#7F8C99')
        ax2.tick_params(axis='y', labelsize=7, colors='#7F8C99')
        ax2.set_ylim(0, ax2.get_ylim()[1] * 3.0)   # keep the histogram low
        ax2.set_zorder(0)
        ax.set_zorder(1)
        ax.patch.set_visible(False)

        ax.fill_between(x, lo, hi, color='#2E5FA3', alpha=0.20, lw=0, zorder=2)
        ax.plot(x, eff, color='#1F3864', lw=2.0, zorder=3)
        ax.axhline(1.0, color='#666666', ls='-', lw=0.8, zorder=1)
        ax.axvline(res['reference'], color='#C0392B', ls='-', lw=1.2, zorder=3)
        for k in res['knots']:
            ax.axvline(k, color='#E67E22', ls='--', lw=0.9, alpha=0.9, zorder=2)

        # rug of the observed values
        y0 = min(np.min(lo), 1.0)
        ax.plot(res['x_values'],
                np.full(len(res['x_values']), y0),
                '|', color='#34495E', alpha=0.15, markersize=4, zorder=2)

        ax.set_yscale('log')
        ax.set_xlabel(res['label'], fontsize=10)
        ax.set_ylabel(f'Adjusted {eff_name} (95% CI)', fontsize=10)
        ax.set_title(
            f"{res['label']}  |  p-nonlinear = {fmt_p(res['p_nonlinear'])}\n"
            f"reference = {res['reference']:.4g}, {res['n_knots']} knots, "
            f"{res['n_events']} events ({res['events_per_spline_param']:.1f} per spline parameter)",
            fontsize=9.5, fontweight='bold')
        ax.grid(alpha=0.18, which='both')
        ax.legend(handles=[
            Line2D([0], [0], color='#1F3864', lw=2, label=f'Adjusted {eff_name}'),
            Line2D([0], [0], color='#2E5FA3', lw=6, alpha=0.3, label='95% CI'),
            Line2D([0], [0], color='#C0392B', lw=1.2,
                   label=f"Reference ({res['reference']:.4g})"),
            Line2D([0], [0], color='#E67E22', lw=1, ls='--', label='Knots'),
            Line2D([0], [0], color='#BDC9DB', lw=6, label='Distribution'),
        ], fontsize=7.5, loc='best', framealpha=0.9)

    for j in range(n, nrows * ncols):
        axes[j // ncols][j % ncols].axis('off')

    fig.suptitle(config.get('title') or 'Restricted cubic spline analysis',
                 fontsize=12, fontweight='bold')
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches='tight')
    plt.close(fig)
    return path


# ═══════════════════════════════════════════════════════════════════════════════
# Preview (--check-missing): never fits a model
# ═══════════════════════════════════════════════════════════════════════════════

def preview(config, df, variables):
    print("=" * 96)
    print("RCS PREVIEW (--check-missing)  |  mode = rcs")
    print("=" * 96)
    print(f"Data file : {config['data_file']}")
    print(f"Rows after filters/derived variables : {len(df)}")
    print(f"Analysis type : {config['analysis_type']}")
    print("-" * 96)

    grp = grouping_column(config)
    rows = list(variables)
    if grp and grp not in [v['column'] for v in rows]:
        rows = [{'column': grp, 'type': 'binary', 'label': f'[group] {grp}'}] + rows
    for c in outcome_columns(config):
        if c:
            rows.append({'column': c, 'type': 'continuous', 'label': f'[outcome] {c}'})

    print(f"{'Variable':<28} {'Column':<20} {'Type':<12} {'Missing':>16}  Role")
    print("-" * 96)
    spline_set = set(config['spline_variables'])
    for v in rows:
        col = v['column']
        role = 'SPLINE' if col in spline_set else ''
        if col not in df.columns:
            print(f"{v['label']:<28} {col:<20} {v.get('type', ''):<12} "
                  f"{'COLUMN NOT FOUND':>16}  {role}")
            continue
        s = normalize_series(df, col, v.get('type', 'continuous'))
        nm = int(s.isna().sum())
        pct = 100.0 * nm / len(df) if len(df) else 0.0
        print(f"{v['label']:<28} {col:<20} {v.get('type', ''):<12} "
              f"{nm:>6}/{len(df):<5} ({pct:>4.1f}%)  {role}")

    print("-" * 96)
    ss = config['spline_settings']
    print(f"Knots requested : {ss['knots']}   "
          f"knot_percentiles : {ss['knot_percentiles'] or '(Harrell default)'}   "
          f"reference : {ss['reference'] if ss['reference'] is not None else '(median)'}")
    print("Planned knot placement per spline variable:")
    for col in config['spline_variables']:
        ok, n_knots, msg = validate_spline_variable(df, config, variables, col)
        if not ok:
            print(f"  {col:<20} CANNOT SPLINE -- {msg}")
            qc_warning(f"--check-missing preview: '{col}' would block the real run ({msg})")
            continue
        s = pd.to_numeric(df[col], errors='coerce').dropna()
        knots, pcts = choose_knots(s.values, n_knots, ss['knot_percentiles'])
        ref = ss['reference'] if ss['reference'] is not None else float(np.median(s.values))
        print(f"  {col:<20} k = {n_knots}  percentiles = "
              f"{', '.join(f'{p:g}' for p in pcts)}  ->  knots = "
              f"{', '.join(f'{k:.4g}' for k in knots)}   reference = {ref:.4g}")

    print("=" * 96)
    print("[preview] No model was fitted (--check-missing). No Excel or PNG was written.")
    print("=" * 96)


# ═══════════════════════════════════════════════════════════════════════════════
# Driver
# ═══════════════════════════════════════════════════════════════════════════════

def run(config, df, variables):
    spline_vars = list(config['spline_variables'])
    if not spline_vars:
        qc_blocking("spline_variables is empty: there is nothing to fit a spline to")
        return 3

    # outcome columns must exist before anything else
    out_cols = [c for c in outcome_columns(config) if c]
    missing_out = [c for c in out_cols if c not in df.columns]
    if missing_out:
        qc_blocking(f"outcome column(s) not found in the data: {', '.join(missing_out)}")
        return 3

    # ── validation pass: any failure blocks the whole run ───────────────────
    plan, blocked = [], False
    for col in spline_vars:
        ok, n_knots, msg = validate_spline_variable(df, config, variables, col)
        if not ok:
            qc_blocking(msg)
            blocked = True
        else:
            plan.append((col, n_knots))
    if blocked:
        qc_blocking("no output was written because at least one requested spline variable "
                    "cannot be analysed; fix the config or the data and re-run")
        return 3

    # ── fitting pass ───────────────────────────────────────────────────────
    results = []
    for col, n_knots in plan:
        print(f"\n[RCS] {col}  (k = {n_knots})")
        try:
            res = analyse_variable(config, df, variables, col, n_knots)
        except FitFailure as e:
            qc_blocking(f"{col}: {e}")
            blocked = True
            continue
        except Exception as e:               # anything unexpected is still blocking
            qc_blocking(f"{col}: model fitting failed ({type(e).__name__}: {e})")
            blocked = True
            continue
        results.append(res)
        print(f"       n = {res['n']}, events = {res['n_events']}, "
              f"knots = {', '.join(f'{k:.4g}' for k in res['knots'])}, "
              f"reference = {res['reference']:.4g}")
        print(f"       LR chi2 (non-linearity) = {res['lr_nonlinear']:.2f} "
              f"on {res['nonlinear_df']} df, p-nonlinear = {fmt_p(res['p_nonlinear'])}")

        if res['events_per_spline_param'] < MIN_EVENTS_PER_SPLINE_PARAM:
            qc_warning(
                f"{col}: only {res['events_per_spline_param']:.1f} events per spline parameter "
                f"({res['n_events']} events / {res['spline_df']} spline terms), below the "
                f"{MIN_EVENTS_PER_SPLINE_PARAM} threshold in advanced_analyses.md section 3 — the "
                f"spline is at risk of overfitting; consider reporting a linear term and stating "
                f"the limitation explicitly")
        if not math.isnan(res['p_nonlinear']) and res['p_nonlinear'] >= 0.05:
            qc_warning(
                f"{col}: p-nonlinear = {res['p_nonlinear']:.3f} (>= 0.05). This does NOT mean the "
                f"linear specification is correct — it means this sample size did not detect a "
                f"departure from linearity. Before reporting a linear term, inspect the fitted curve "
                f"and the width of its confidence band in Spline_estimates / the PNG.")

    if blocked:
        qc_blocking("no output was written because at least one spline model failed to fit")
        return 3

    if not config['spline_settings']['knot_percentiles']:
        qc_warning("knot_percentiles was not specified: Harrell's default percentiles were used. "
                   "This is a methodological choice and must be registered in decision_log.md "
                   "with a permanent ID.")
    if config['spline_settings']['reference'] is None:
        qc_warning("spline_settings.reference was not specified: each variable's median was used as "
                   "the reference value. Every reported HR/OR is relative to it, so it must be "
                   "registered in decision_log.md and stated in the manuscript.")

    sheets = write_excel(config, results, len(df))
    print(f"\nExcel written : {config['output_file']}")
    print(f"  Sheets: {', '.join(sheets)}")
    png = plot_results(config, results)
    if png:
        print(f"Plot written  : {png}")
    return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python nonlinearity.py config.json [--check-missing]")
        sys.exit(1)

    config_path = sys.argv[1]
    check_only = '--check-missing' in sys.argv

    config = load_config(config_path)
    df = load_data(config)
    variables = collect_variables(config)

    print(f"Mode: {config['mode']}  ({config['analysis_type']})")
    print(f"Data loaded: n={len(df)}")

    if check_only:
        preview(config, df, variables)
        sys.exit(0)

    rc = run(config, df, variables)

    print("\nDone!")
    if _QC_MESSAGES:
        n_block = sum(1 for m in _QC_MESSAGES if m.startswith('[QC_BLOCKING]'))
        n_warn = len(_QC_MESSAGES) - n_block
        print(f"  QC: {n_block} blocking, {n_warn} warning(s) written to stderr")
    sys.exit(rc)


if __name__ == '__main__':
    main()
