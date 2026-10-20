#!/usr/bin/env python3
"""
Clustering and repeated measures — variance that is not underestimated
(research-plan pipeline, references/advanced_analyses.md section 4)

Patients from the same hospital, the same physician, or repeated measurements on
the same patient are not independent. Ignoring that makes the standard error too
small, the confidence interval too narrow and the p-value too small — and the
direction of the error is always towards looking more significant than the data
support. This script refits the adjusted model with the dependence accounted for
and, crucially, puts the uncorrected and corrected results side by side.

Usage:
    python robust_variance.py config.json                  # full run
    python robust_variance.py config.json --check-missing  # preview only, no models

Config (mode = "robust"):
    {"mode":"robust","cluster_column":"hospital_id",
     "method":"cluster_robust" | "gee" | "mixed",
     "correlation_structure":"exchangeable",
     "compare_to_naive":true,
     "data_file":"...","filters":[],"derived_variables":[],
     "grouping":{"column":"AF","groups":[...]},
     "analysis_type":"cox",
     "cox_settings":{"time_column":"t","event_column":"e"},
     "logistic_settings":null,
     "sections":[{"header":"...","variables":[...]}],
     "title":"...","subtitle":"...",
     "output_file":".../Robust_primary.xlsx"}

Design notes
------------
* The three methods answer different questions and the Estimand sheet says so:
  cluster-robust keeps the same point estimate and only widens the SE; GEE gives
  a marginal (population-averaged) effect; a mixed model gives a conditional
  (cluster-specific) effect. They are not interchangeable.
* Cox + GEE / mixed is a [QC_BLOCKING], not a silent substitution: neither is a
  survival model. Use cluster-robust SEs (or a shared-frailty model, which this
  script does not implement).
* correlation_structure is always written into the output, including when it came
  from the script default — advanced_analyses.md section 4 forbids using a
  default without saying so.
"""

import sys
import os
import json
import math
import operator

import numpy as np
import pandas as pd

from scipy import stats as sps

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


_QC_MESSAGES = []

MIN_CLUSTERS = 30                 # advanced_analyses.md section 4
MAX_SINGLE_CLUSTER_SHARE = 0.20
DIVERGENCE_ABS_COEF = 20.0


def qc(kind, message):
    """QC line on stderr, flush-left, one per line."""
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

VALID_METHODS = ('cluster_robust', 'gee', 'mixed')
VALID_STRUCTURES = {
    'exchangeable': 'Exchangeable',
    'independence': 'Independence',
    'independent': 'Independence',
    'ar1': 'Autoregressive',
    'ar(1)': 'Autoregressive',
    'autoregressive': 'Autoregressive',
    'unstructured': 'Unstructured',
}

DEFAULT_STRUCTURE = 'exchangeable'


def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    config.setdefault('mode', 'robust')
    config.setdefault('filters', [])
    config.setdefault('derived_variables', [])
    config.setdefault('sections', [])
    config.setdefault('title', '')
    config.setdefault('subtitle', '')
    config.setdefault('cox_settings', None)
    config.setdefault('logistic_settings', None)
    config.setdefault('analysis_type', 'cox')
    config.setdefault('method', 'cluster_robust')
    config.setdefault('compare_to_naive', True)

    # Remember whether the correlation structure was actually chosen by a human.
    config['_structure_from_config'] = bool(config.get('correlation_structure'))
    config.setdefault('correlation_structure', DEFAULT_STRUCTURE)

    if config['mode'] != 'robust':
        sys.exit(f"[FATAL] Unknown mode: {config['mode']!r} (expected 'robust')")
    if config['analysis_type'] not in ('cox', 'logistic'):
        sys.exit(f"[FATAL] Unknown analysis_type: {config['analysis_type']!r} "
                 f"(expected 'cox' or 'logistic')")
    if config['method'] not in VALID_METHODS:
        sys.exit(f"[FATAL] Unknown method: {config['method']!r} "
                 f"(expected one of {VALID_METHODS})")
    if str(config['correlation_structure']).lower() not in VALID_STRUCTURES:
        sys.exit(f"[FATAL] Unknown correlation_structure: "
                 f"{config['correlation_structure']!r} "
                 f"(expected one of {sorted(set(VALID_STRUCTURES))})")
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
    s = df[col]
    if var_type == 'categorical':
        return s.where(s.notna() & (s.astype(str).str.strip() != ''), np.nan)
    return pd.to_numeric(s, errors='coerce')


def collect_variables(config):
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
    """Reference level + dummy encoding, lifted verbatim from
    univariate_forest.py so the behaviour matches the rest of the pipeline."""
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


def build_design(df, config, variables):
    """(design_df, model_cols, label_map, missing_cols) — complete case."""
    grp = grouping_column(config)
    cluster_col = config['cluster_column']
    out_cols = [c for c in outcome_columns(config) if c]

    model_vars = list(variables)
    if grp and grp not in [v['column'] for v in model_vars]:
        model_vars = [{'column': grp, 'type': 'binary', 'label': grp,
                       'scale': None, 'reference_level': None,
                       'section': 'Exposure'}] + model_vars

    needed = [v['column'] for v in model_vars] + out_cols + [cluster_col]
    # The within-cluster time axis is not a model term, but AR(1) needs it to be
    # present in the analysis frame — and it has to survive the same dropna, or
    # the time vector and the design matrix would end up different lengths.
    time_col = config.get('within_cluster_time_column')
    if time_col:
        needed.append(time_col)
    needed = list(dict.fromkeys(needed))
    missing_cols = [c for c in needed if c not in df.columns]
    if missing_cols:
        return None, None, None, missing_cols

    d = df[needed].copy()
    for v in model_vars:
        d[v['column']] = normalize_series(d, v['column'], v['type'])
    for c in out_cols:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d[cluster_col] = d[cluster_col].where(
        d[cluster_col].notna() & (d[cluster_col].astype(str).str.strip() != ''), np.nan)

    d = d.dropna(subset=needed).reset_index(drop=True)

    model_cols, label_map = [], {}
    for v in model_vars:
        col, vtype = v['column'], v['type']
        if vtype == 'categorical':
            d, dummies = _prepare_categorical(d, col, vtype, v['reference_level'],
                                              context_label='(robust variance model)')
            for dc in dummies:
                label_map[dc] = f"{v['label']}: {dc[len(col) + 1:]}"
            model_cols += dummies
        else:
            if v['scale']:
                d[col] = d[col] / v['scale']
                label_map[col] = f"{v['label']} (per {v['scale']})"
            else:
                label_map[col] = v['label']
            model_cols.append(col)

    keep = []
    for c in model_cols:
        if d[c].nunique(dropna=True) < 2:
            qc_warning(f"dropped covariate '{c}' (zero variance in the complete-case rows)")
        else:
            keep.append(c)
    return d, keep, label_map, []


# ═══════════════════════════════════════════════════════════════════════════════
# Cluster description
# ═══════════════════════════════════════════════════════════════════════════════

def cluster_summary(d, cluster_col, config):
    sizes = d.groupby(cluster_col, dropna=False).size().sort_values(ascending=False)
    n_obs = int(len(d))
    n_clusters = int(len(sizes))

    events = None
    if config['analysis_type'] == 'cox':
        ev_col = config['cox_settings']['event_column']
    else:
        ev_col = config['logistic_settings']['outcome_column']
    if ev_col in d.columns:
        events = d.groupby(cluster_col, dropna=False)[ev_col].sum()

    summ = {
        'n_obs': n_obs,
        'n_clusters': n_clusters,
        'sizes': sizes,
        'events': events,
        'event_column': ev_col,
        'mean_size': float(sizes.mean()) if n_clusters else float('nan'),
        'median_size': float(sizes.median()) if n_clusters else float('nan'),
        'min_size': int(sizes.min()) if n_clusters else 0,
        'max_size': int(sizes.max()) if n_clusters else 0,
        'q1_size': float(sizes.quantile(0.25)) if n_clusters else float('nan'),
        'q3_size': float(sizes.quantile(0.75)) if n_clusters else float('nan'),
        'n_singleton': int((sizes == 1).sum()),
        'largest_share': float(sizes.max() / n_obs) if n_obs else float('nan'),
        'largest_label': str(sizes.index[0]) if n_clusters else 'N/A',
        'clusters_zero_events': (int((events == 0).sum()) if events is not None else None),
    }
    return summ


# ═══════════════════════════════════════════════════════════════════════════════
# Model fitting
# ═══════════════════════════════════════════════════════════════════════════════

class FitFailure(Exception):
    pass


def _sanity_check(params, names):
    vals = np.asarray([params[n] for n in names], dtype=float)
    if not np.all(np.isfinite(vals)):
        raise FitFailure("model produced non-finite coefficients")
    if vals.size and np.max(np.abs(vals)) > DIVERGENCE_ABS_COEF:
        raise FitFailure(f"coefficients diverged (max |beta| = {np.max(np.abs(vals)):.1f}); "
                         f"this is separation or collinearity, not a converged fit")


def _terms(names, coefs, ses):
    out = {}
    for n in names:
        b, se = float(coefs[n]), float(ses[n])
        if not np.isfinite(se) or se <= 0:
            raise FitFailure(f"term '{n}' has a non-positive or non-finite standard error "
                             f"({se}); the variance estimate did not converge")
        z = b / se
        out[n] = {
            'coef': b, 'se': se,
            'effect': math.exp(b),
            'ci_lower': math.exp(b - 1.96 * se),
            'ci_upper': math.exp(b + 1.96 * se),
            'p': float(2 * sps.norm.sf(abs(z))),
        }
    return out


def fit_cox(d, model_cols, config, cluster_col=None):
    from lifelines import CoxPHFitter
    cs = config['cox_settings']
    t, e = cs['time_column'], cs['event_column']

    cols = list(dict.fromkeys(list(model_cols) + [t, e]))
    dd = d[cols].astype(float).copy()
    kwargs = {}
    if cluster_col is not None:
        dd['_cluster_'] = pd.factorize(d[cluster_col])[0]
        kwargs = {'cluster_col': '_cluster_', 'robust': True}

    try:
        cph = CoxPHFitter()
        cph.fit(dd, duration_col=t, event_col=e, **kwargs)
    except Exception as ex:
        raise FitFailure(f"Cox model did not converge: {type(ex).__name__}: {ex}")

    _sanity_check(cph.params_, list(model_cols))
    ses = cph.standard_errors_
    return {
        'terms': _terms(list(model_cols), cph.params_, ses),
        'n': int(len(dd)), 'n_events': int(dd[e].sum()),
        'loglik': float(cph.log_likelihood_),
        'extra': {},
    }


def fit_logit_plain(d, model_cols, config, cluster_codes=None):
    import statsmodels.api as sm
    y = d[config['logistic_settings']['outcome_column']].astype(float)
    X = sm.add_constant(d[list(model_cols)].astype(float), has_constant='add')
    kwargs = {}
    if cluster_codes is not None:
        kwargs = {'cov_type': 'cluster', 'cov_kwds': {'groups': np.asarray(cluster_codes)}}
    try:
        res = sm.Logit(y, X).fit(disp=0, method='bfgs', maxiter=400, **kwargs)
    except Exception as ex:
        raise FitFailure(f"logistic model did not converge: {type(ex).__name__}: {ex}")
    if not res.mle_retvals.get('converged', True):
        raise FitFailure("logistic model did not converge (statsmodels reported "
                         "converged = False)")
    _sanity_check(res.params, list(model_cols))
    return {
        'terms': _terms(list(model_cols), res.params, res.bse),
        'n': int(len(y)), 'n_events': int(y.sum()),
        'loglik': float(res.llf),
        'extra': {},
    }


def fit_gee(d, model_cols, config, cluster_codes):
    import statsmodels.api as sm
    from statsmodels.genmod import cov_struct as cs_mod

    struct_name = VALID_STRUCTURES[str(config['correlation_structure']).lower()]
    cov_struct = getattr(cs_mod, struct_name)()

    # Autoregressive correlation is defined by the distance between observations
    # in TIME. statsmodels reads that from the `time` argument; without it the row
    # order within each cluster stands in for the time axis, so AR(1) on unordered
    # rows silently models a correlation the data does not have.
    time_arg = None
    if struct_name == 'Autoregressive':
        tcol = config.get('within_cluster_time_column')
        if not tcol:
            raise FitFailure(
                "correlation_structure is autoregressive but no "
                "'within_cluster_time_column' was supplied. AR(1) is defined by the "
                "time gap between observations within a cluster; with no time "
                "variable statsmodels falls back to row order. Supply the time or "
                "visit column, or use 'exchangeable' (assumes no ordering) or "
                "'independence'.")
        if tcol not in d.columns:
            raise FitFailure(f"within_cluster_time_column '{tcol}' is not in the data")
        tvals = pd.to_numeric(d[tcol], errors='coerce')
        if tvals.isna().any():
            raise FitFailure(
                f"within_cluster_time_column '{tcol}' has non-numeric or missing "
                f"values; AR(1) needs a complete numeric time axis")
        time_arg = tvals.to_numpy().reshape(-1, 1)

    y = d[config['logistic_settings']['outcome_column']].astype(float)
    X = sm.add_constant(d[list(model_cols)].astype(float), has_constant='add')
    try:
        res = sm.GEE(y, X, groups=np.asarray(cluster_codes),
                     time=time_arg,
                     family=sm.families.Binomial(),
                     cov_struct=cov_struct).fit(maxiter=200)
    except Exception as ex:
        raise FitFailure(f"GEE did not converge: {type(ex).__name__}: {ex}")
    if not getattr(res, 'converged', True):
        raise FitFailure("GEE did not converge (statsmodels reported converged = False)")
    _sanity_check(res.params, list(model_cols))

    dep = None
    try:
        dep = res.cov_struct.dep_params
        dep = float(np.ravel(np.asarray(dep, dtype=float))[0])
    except Exception:
        dep = None
    return {
        'terms': _terms(list(model_cols), res.params, res.bse),
        'n': int(len(y)), 'n_events': int(y.sum()),
        'loglik': float('nan'),
        'extra': {
            'correlation_structure': struct_name,
            'estimated_within_cluster_correlation': dep,
            'cov_struct_summary': str(res.cov_struct.summary()),
            'scale': float(getattr(res, 'scale', float('nan'))),
        },
    }


def fit_mixed_binomial(d, model_cols, config, cluster_codes):
    """Random-intercept logistic model via variational Bayes.

    statsmodels' MixedLM is a linear model and cannot take a binary outcome, so
    the binary path uses BinomialBayesMixedGLM.fit_vb(). The price is that the
    intervals are variational-Bayes posterior intervals, not likelihood
    intervals, and VB is known to understate posterior spread. That is written
    into the Method sheet and raised as a QC warning.

    The optimiser is run with the fixed-effects design centred and scaled
    (scale_fe=True) and a raised iteration cap: with the raw design the VB
    objective overflows and stops early, which produces posterior SDs an order
    of magnitude too small. A run that still fails to converge is a
    [QC_BLOCKING], not a result.
    """
    import warnings as _warnings
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

    y = d[config['logistic_settings']['outcome_column']].astype(float)
    dat = pd.DataFrame({'_y_': y.values})
    safe_names = {}
    for i, c in enumerate(model_cols):
        safe = f"x{i + 1}"
        safe_names[safe] = c
        dat[safe] = d[c].astype(float).values
    dat['_cl_'] = np.asarray(cluster_codes)

    formula = '_y_ ~ ' + (' + '.join(safe_names) if safe_names else '1')
    vc_formulas = {'cluster': '0 + C(_cl_)'}
    try:
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter('always')
            mod = BinomialBayesMixedGLM.from_formula(formula, vc_formulas, dat)
            res = mod.fit_vb(minim_opts={'maxiter': 5000}, scale_fe=True, verbose=False)
        msgs = [str(c.message) for c in caught]
    except Exception as ex:
        raise FitFailure(f"random-intercept (mixed) model failed: {type(ex).__name__}: {ex}")

    if any('did not converge' in m for m in msgs):
        raise FitFailure("the variational-Bayes optimiser for the random-intercept model did not "
                         "converge (statsmodels: 'VB fitting did not converge'); the posterior "
                         "standard deviations from a stopped optimiser are not usable")

    names = list(mod.exog_names)
    means = pd.Series(np.asarray(res.fe_mean, dtype=float), index=names)
    sds = pd.Series(np.asarray(res.fe_sd, dtype=float), index=names)
    inv = {v: k for k, v in safe_names.items()}
    means = means.rename(index={safe: real for safe, real in safe_names.items()})
    sds = sds.rename(index={safe: real for safe, real in safe_names.items()})

    _sanity_check(means, list(model_cols))

    try:
        vc_sd = float(np.exp(np.asarray(res.vcp_mean, dtype=float)[0]))
    except Exception:
        vc_sd = float('nan')
    icc = (vc_sd ** 2) / (vc_sd ** 2 + (math.pi ** 2) / 3.0) if np.isfinite(vc_sd) else float('nan')

    return {
        'terms': _terms(list(model_cols), means, sds),
        'n': int(len(y)), 'n_events': int(y.sum()),
        'loglik': float('nan'),
        'extra': {
            'random_effect_sd': vc_sd,
            'icc_latent_scale': icc,
            'engine': 'statsmodels BinomialBayesMixedGLM.fit_vb (variational Bayes, random '
                      'intercept per cluster; fixed-effects design centred and scaled, '
                      'optimiser cap 5000 iterations, non-convergence treated as blocking)',
        },
        'unused_inv': inv,
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

METHOD_ESTIMAND = {
    'cluster_robust': (
        "Cluster-robust (sandwich) variance. The POINT ESTIMATE is identical to the uncorrected "
        "model — only the standard error changes. The estimand is therefore exactly the same "
        "conditional effect as the main analysis; what changes is how honestly its uncertainty is "
        "reported."),
    'gee': (
        "Generalised estimating equations. The estimand is MARGINAL (population-averaged): the "
        "contrast in the average outcome risk across the whole population if everyone were exposed "
        "versus unexposed, given the covariates. It is not the same quantity as a mixed model's."),
    'mixed': (
        "Random-intercept (mixed) model. The estimand is CONDITIONAL (cluster-specific): the effect "
        "within a given hospital / physician / patient, holding that cluster's random intercept "
        "fixed. Conditional odds ratios are systematically further from 1 than marginal ones, so "
        "they must not be compared numerically with the GEE or naive estimates as if they were the "
        "same number."),
}


def write_excel(config, summ, robust_fit, naive_fit, label_map, model_cols):
    wb = Workbook()
    is_cox = config['analysis_type'] == 'cox'
    eff_name = 'HR' if is_cox else 'OR'
    method = config['method']
    struct = str(config['correlation_structure'])
    title = config.get('title') or 'Cluster-adjusted variance analysis'
    subtitle = config.get('subtitle') or (f"N = {summ['n_obs']} in {summ['n_clusters']} clusters "
                                          f"({config['cluster_column']})")

    def term_label(t):
        return label_map.get(t, t)

    # ── 1. Estimand ────────────────────────────────────────────────────────
    ws = wb.active
    ws.title = 'Estimand'
    r = sheet_header(ws, title, subtitle, ['Item', 'Statement'], [34, 120])
    outcome_txt = (f"time to {config['cox_settings']['event_column']} "
                   f"(follow-up column {config['cox_settings']['time_column']})"
                   if is_cox else
                   f"binary {config['logistic_settings']['outcome_column']}")
    grp = grouping_column(config)
    rows = [
        ('Analysis', f"Adjusted outcome model refitted so that non-independence within "
                     f"'{config['cluster_column']}' is accounted for."),
        ('Model', 'Cox proportional hazards' if is_cox else 'Logistic regression'),
        ('Outcome', outcome_txt),
        ('Exposure / grouping variable', grp or '(none declared)'),
        ('Clustering unit', f"{config['cluster_column']} — {summ['n_clusters']} clusters over "
                            f"{summ['n_obs']} observations"),
        ('Method used', method),
        ('Estimand', METHOD_ESTIMAND[method]),
        ('Correlation structure',
         f"{struct}"
         + ("  (taken from the config)" if config['_structure_from_config']
            else f"  (NOT specified in the config; the script default '{DEFAULT_STRUCTURE}' was "
                 f"applied and must be registered in decision_log.md)")
         + ("  — used by the GEE working correlation matrix."
            if method == 'gee' else
            "  — recorded for the record; this method does not use a working correlation matrix.")),
        ('Why this step exists',
         "Observations inside the same cluster are correlated. An uncorrected model treats them as "
         "independent, which makes the standard error too small, the confidence interval too narrow "
         "and the p-value too small. The direction of that error is always towards making the result "
         "look more significant than the data support."),
        ('How to read Naive_vs_Robust',
         "SE ratio > 1 means the uncorrected model was understating uncertainty by that factor; "
         "CI width ratio > 1 means the corrected interval is that many times wider. A ratio near 1.0 "
         "means this clustering variable carries little information — which is itself a reportable "
         "finding, not a reason to drop the correction."),
        ('What this does NOT do',
         "It does not change which model is the primary analysis, does not fix confounding by cluster "
         "(add the cluster as a covariate or use a mixed model for that), and does not rescue a study "
         "with too few clusters — see the Method sheet."),
    ]
    for i, (k, v) in enumerate(rows):
        r = write_row(ws, r, [k, v], alt=(i % 2 == 1), bold_cols=(1,))

    # ── 2. Adjusted_robust ─────────────────────────────────────────────────
    ws = wb.create_sheet('Adjusted_robust')
    headers = ['Variable', 'Model term', 'Coefficient (log scale)', 'Standard error',
               f'{eff_name} (95% CI)', 'p-value']
    r = sheet_header(ws, f'Adjusted model with {method} variance', subtitle, headers,
                     [34, 26, 20, 16, 24, 12])
    for i, t in enumerate(model_cols):
        est = robust_fit['terms'][t]
        r = write_row(ws, r, [term_label(t), t, fmt_num(est['coef'], 4), fmt_num(est['se'], 4),
                              fmt_effect(est['effect'], est['ci_lower'], est['ci_upper']),
                              fmt_p(est['p'])],
                      alt=(i % 2 == 1),
                      sig_cols=(6,) if est['p'] < 0.05 else ())
    r += 1
    extra = robust_fit.get('extra') or {}
    for k, v in extra.items():
        if k == 'cov_struct_summary':
            continue
        r = write_row(ws, r, [f"[{k}]", '', '', '', str(v), ''], bold_cols=(1,))
    r += 1
    r = write_footnote(
        ws, r, len(headers),
        f"n = {robust_fit['n']} observations, {robust_fit['n_events']} events, "
        f"{summ['n_clusters']} clusters. Complete-case: a row is dropped if any model covariate, the "
        f"outcome or the cluster identifier is missing. "
        + METHOD_ESTIMAND[method]
        + " Confidence intervals are Wald intervals on the log scale, exponentiated.")

    # ── 3. Naive_vs_Robust ─────────────────────────────────────────────────
    ws = wb.create_sheet('Naive_vs_Robust')
    headers = ['Variable', 'Model term',
               'Naive coef', 'Naive SE', f'Naive {eff_name} (95% CI)', 'Naive p',
               f'{method} coef', f'{method} SE', f'{method} {eff_name} (95% CI)',
               f'{method} p',
               'SE ratio (corrected / naive)', 'CI width ratio (corrected / naive)',
               'Crosses the null differently?']
    widths = [30, 22, 12, 12, 22, 11, 12, 12, 22, 11, 18, 20, 22]
    r = sheet_header(ws, 'Uncorrected versus cluster-adjusted, side by side', subtitle,
                     headers, widths)
    if naive_fit is None:
        r = write_row(ws, r, ['compare_to_naive was set to false in the config, so the '
                              'side-by-side comparison was not produced',
                              '', '', '', '', '', '', '', '', '', '', '', ''],
                      bold_cols=(1,))
    else:
        for i, t in enumerate(model_cols):
            nv = naive_fit['terms'][t]
            rb = robust_fit['terms'][t]
            se_ratio = rb['se'] / nv['se'] if nv['se'] else float('nan')
            w_naive = math.log(nv['ci_upper']) - math.log(nv['ci_lower'])
            w_rob = math.log(rb['ci_upper']) - math.log(rb['ci_lower'])
            ci_ratio = w_rob / w_naive if w_naive else float('nan')
            flips = ((nv['p'] < 0.05) != (rb['p'] < 0.05))
            r = write_row(ws, r, [
                term_label(t), t,
                fmt_num(nv['coef'], 4), fmt_num(nv['se'], 4),
                fmt_effect(nv['effect'], nv['ci_lower'], nv['ci_upper']), fmt_p(nv['p']),
                fmt_num(rb['coef'], 4), fmt_num(rb['se'], 4),
                fmt_effect(rb['effect'], rb['ci_lower'], rb['ci_upper']), fmt_p(rb['p']),
                fmt_num(se_ratio, 3), fmt_num(ci_ratio, 3),
                'YES — significance changes' if flips else 'no'],
                alt=(i % 2 == 1), flag=flips)
    r += 1
    same_point = (method == 'cluster_robust')
    r = write_footnote(
        ws, r, len(headers),
        ("Both columns come from the same model fitted on the same rows; only the variance "
         "estimator differs, so the coefficients are identical by construction and every difference "
         "you see is in the standard error. "
         if same_point else
         "The two columns come from DIFFERENT estimators, so the coefficients themselves differ and "
         "the SE ratio mixes a variance correction with a change of estimand — read it together with "
         "the Estimand sheet before quoting it. ")
        + "An SE ratio above 1 is the quantity that answers the reviewer's question: it is the factor "
          "by which ignoring the clustering was understating uncertainty. A ratio BELOW 1 is not an "
          "error and does not mean the correction failed: for a covariate that varies within clusters "
          "the corrected variance can legitimately be smaller than the model-based one, and a GEE with "
          "a well-chosen working correlation is a genuinely more efficient estimator than the "
          "independence-weighted fit. Expect the largest inflation on covariates that are shared "
          "within a cluster (centre-level exposures) and little change on individual-level ones. "
          "Where the last column says "
          "the significance changes, the uncorrected result was resting on the independence "
          "assumption. Where a result is no longer below 0.05, the correct wording is "
          "'no statistically significant difference was detected', not 'there is no association'.")

    # ── 4. Cluster_summary ─────────────────────────────────────────────────
    ws = wb.create_sheet('Cluster_summary')
    headers = ['Item', 'Value']
    r = sheet_header(ws, f"Cluster structure of '{config['cluster_column']}'", subtitle,
                     headers, [42, 60])
    items = [
        ('Observations analysed', summ['n_obs']),
        ('Number of clusters', summ['n_clusters']),
        ('Mean cluster size', fmt_num(summ['mean_size'], 2)),
        ('Median cluster size (IQR)',
         f"{summ['median_size']:.1f} ({summ['q1_size']:.1f}–{summ['q3_size']:.1f})"),
        ('Smallest cluster', summ['min_size']),
        ('Largest cluster', f"{summ['max_size']}  (cluster {summ['largest_label']})"),
        ('Largest cluster as % of the sample', f"{100 * summ['largest_share']:.1f}%"),
        ('Clusters of size 1', summ['n_singleton']),
        (f"Clusters with zero events ({summ['event_column']})",
         summ['clusters_zero_events'] if summ['clusters_zero_events'] is not None else 'N/A'),
    ]
    ex = robust_fit.get('extra') or {}
    if ex.get('estimated_within_cluster_correlation') is not None:
        items.append(('Estimated within-cluster correlation (GEE working structure)',
                      fmt_num(ex['estimated_within_cluster_correlation'], 4)))
    if ex.get('random_effect_sd') is not None:
        items.append(('Random-intercept SD (log-odds scale)', fmt_num(ex['random_effect_sd'], 4)))
        items.append(('Implied ICC on the latent scale', fmt_num(ex.get('icc_latent_scale'), 4)))
    for i, (k, v) in enumerate(items):
        flag = (k == 'Number of clusters' and summ['n_clusters'] < MIN_CLUSTERS) or \
               (k == 'Largest cluster as % of the sample'
                and summ['largest_share'] > MAX_SINGLE_CLUSTER_SHARE)
        r = write_row(ws, r, [k, v], alt=(i % 2 == 1), bold_cols=(1,), flag=flag)

    r += 1
    r = write_row(ws, r, ['Cluster size distribution', ''], bold_cols=(1,))
    sizes = summ['sizes']
    show = sizes if len(sizes) <= 40 else sizes.head(20)
    ev = summ['events']
    r2_headers_written = False
    for i, (cl, sz) in enumerate(show.items()):
        if not r2_headers_written:
            r = write_row(ws, r, ['Cluster', 'n  (% of sample)  |  events'], bold_cols=(1, 2))
            r2_headers_written = True
        n_ev = int(ev.loc[cl]) if ev is not None and cl in ev.index else 'N/A'
        r = write_row(ws, r, [str(cl), f"{int(sz)}  ({100 * sz / summ['n_obs']:.1f}%)  |  {n_ev}"],
                      alt=(i % 2 == 1),
                      flag=(sz / summ['n_obs'] > MAX_SINGLE_CLUSTER_SHARE))
    if len(sizes) > 40:
        r = write_row(ws, r, [f'... {len(sizes) - 20} smaller clusters not listed',
                              f"sizes {int(sizes.min())}–{int(sizes.iloc[19])}"])
    r += 1
    r = write_footnote(
        ws, r, len(headers),
        f"Cluster-robust standard errors are asymptotic in the NUMBER OF CLUSTERS, not the number of "
        f"patients. Below roughly {MIN_CLUSTERS} clusters the sandwich estimator is itself biased "
        f"downwards (advanced_analyses.md section 4), so a 'corrected' SE can still be too small; the "
        f"usual remedies are a wild cluster bootstrap or a mixed model. A single cluster holding more "
        f"than {100 * MAX_SINGLE_CLUSTER_SHARE:.0f}% of the sample means the result is substantially "
        f"one centre's result and should be checked with a leave-one-cluster-out sensitivity analysis. "
        f"Clusters with zero events contribute nothing to a Cox partial likelihood.")

    # ── 5. Method ──────────────────────────────────────────────────────────
    ws = wb.create_sheet('Method')
    r = sheet_header(ws, 'Method and methodological defaults', subtitle,
                     ['Item', 'Value / statement'], [40, 118])
    engine = {
        'cluster_robust': ("lifelines CoxPHFitter(cluster_col=..., robust=True)" if is_cox
                           else "statsmodels Logit with cov_type='cluster'"),
        'gee': "statsmodels GEE, Binomial family",
        'mixed': (robust_fit.get('extra') or {}).get('engine', 'statsmodels mixed model'),
    }[method]
    meth_rows = [
        ('Clustering variable', f"{config['cluster_column']} ({summ['n_clusters']} clusters)"),
        ('Method', f"{method} — {METHOD_ESTIMAND[method]}"),
        ('Engine', engine),
        ('Correlation structure',
         f"{struct}. "
         + ("Chosen in the config." if config['_structure_from_config']
            else f"NOT chosen in the config — the script default '{DEFAULT_STRUCTURE}' was applied. "
                 f"advanced_analyses.md section 4 requires the structure to be stated rather than "
                 f"left as an unmentioned default, which is why it is written here and flagged as a "
                 f"QC warning.")
         + (" GEE working correlation only; the sandwich variance is robust to it being wrong, but "
            "the efficiency of the estimator is not."
            if method == 'gee' else
            " Recorded for completeness; this method does not fit a working correlation matrix.")),
        ('Comparator (naive) model',
         "Same covariates, same rows, no clustering correction: "
         + ("lifelines CoxPHFitter with default (model-based) variance"
            if is_cox else "statsmodels Logit with default (model-based) variance")
         + ("." if config['compare_to_naive'] else
            " — NOT RUN, because compare_to_naive was set to false in the config.")),
        ('Adjustment set',
         "Every covariate in the config sections plus the grouping/exposure column, with the same "
         "`scale` divisors and categorical reference levels as the main analysis."),
        ('Missing data',
         "Complete-case: a row is dropped if any covariate, the outcome, or the cluster identifier is "
         "missing. N will therefore not necessarily match other pipeline steps."),
        ('Minimum number of clusters',
         f"{MIN_CLUSTERS}. Below this the cluster-robust sandwich SE is itself downward biased; the "
         f"output flags it and the recommended alternatives are a wild cluster bootstrap or a mixed "
         f"model. This threshold is a convention, not a law — record whichever you use in "
         f"decision_log.md."),
        ('Dominant-cluster threshold',
         f"{100 * MAX_SINGLE_CLUSTER_SHARE:.0f}% of the sample in one cluster triggers a warning."),
        ('Confidence intervals',
         "Wald intervals on the log scale using the method's own standard error, exponentiated."
         + (" For the mixed model these are variational-Bayes posterior intervals, which are known to "
            "be too narrow; treat them as approximate and do not present them as likelihood-based "
            "confidence intervals." if method == 'mixed' else "")),
        ('Not implemented here',
         "Wild cluster bootstrap, shared-frailty Cox, three-level (patient within physician within "
         "hospital) nesting, and AR(1) structures on irregular time grids. If the design needs one of "
         "these, this script is not sufficient and the limitation should be stated explicitly."),
        ('Software', f"Python {sys.version.split()[0]}, "
                     f"pandas {pd.__version__}, numpy {np.__version__}"),
        ('Registration requirement',
         "The clustering variable, the method, the correlation structure and the choice of primary "
         "versus sensitivity analysis are methodological decisions. Copy them into decision_log.md "
         "with a permanent ID before these numbers are used in a manuscript."),
    ]
    if (robust_fit.get('extra') or {}).get('cov_struct_summary'):
        meth_rows.append(('GEE dependence summary',
                          robust_fit['extra']['cov_struct_summary']))
    for i, (k, v) in enumerate(meth_rows):
        r = write_row(ws, r, [k, v], alt=(i % 2 == 1), bold_cols=(1,))

    out = config['output_file']
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    wb.save(out)
    return [w.title for w in wb.worksheets]


# ═══════════════════════════════════════════════════════════════════════════════
# Preview (--check-missing): never fits a model
# ═══════════════════════════════════════════════════════════════════════════════

def preview(config, df, variables):
    print("=" * 96)
    print("ROBUST VARIANCE PREVIEW (--check-missing)  |  mode = robust")
    print("=" * 96)
    print(f"Data file : {config['data_file']}")
    print(f"Rows after filters/derived variables : {len(df)}")
    print(f"Analysis type : {config['analysis_type']}   method : {config['method']}")
    print(f"Correlation structure : {config['correlation_structure']}"
          + ("  (from config)" if config['_structure_from_config']
             else "  (SCRIPT DEFAULT — must be registered in decision_log.md)"))
    print("-" * 96)

    grp = grouping_column(config)
    rows = list(variables)
    if grp and grp not in [v['column'] for v in rows]:
        rows = [{'column': grp, 'type': 'binary', 'label': f'[group] {grp}'}] + rows
    for c in outcome_columns(config):
        if c:
            rows.append({'column': c, 'type': 'continuous', 'label': f'[outcome] {c}'})
    rows.append({'column': config['cluster_column'], 'type': 'categorical',
                 'label': f"[cluster] {config['cluster_column']}"})

    print(f"{'Variable':<28} {'Column':<20} {'Type':<12} {'Missing':>16}")
    print("-" * 96)
    for v in rows:
        col = v['column']
        if col not in df.columns:
            print(f"{v['label']:<28} {col:<20} {v.get('type', ''):<12} {'COLUMN NOT FOUND':>16}")
            continue
        s = normalize_series(df, col, v.get('type', 'continuous'))
        nm = int(s.isna().sum())
        pct = 100.0 * nm / len(df) if len(df) else 0.0
        print(f"{v['label']:<28} {col:<20} {v.get('type', ''):<12} "
              f"{nm:>6}/{len(df):<5} ({pct:>4.1f}%)")

    print("-" * 96)
    cc = config['cluster_column']
    if cc in df.columns:
        sizes = df.groupby(cc, dropna=True).size().sort_values(ascending=False)
        n_cl, n_obs = len(sizes), int(df[cc].notna().sum())
        print(f"Clusters : {n_cl} over {n_obs} non-missing rows "
              f"(sizes {int(sizes.min())}–{int(sizes.max())}, "
              f"median {sizes.median():.1f})")
        if n_cl < MIN_CLUSTERS:
            print(f"  NOTE: fewer than {MIN_CLUSTERS} clusters — the real run will warn that the "
                  f"cluster-robust SE is itself downward biased.")
        if n_cl == n_obs:
            print("  NOTE: every observation is its own cluster — the real run will block.")
        if n_cl <= 1:
            print("  NOTE: one cluster or none — the real run will block.")
    else:
        print(f"Clusters : cluster_column '{cc}' NOT FOUND — the real run will block.")
        qc_warning(f"--check-missing preview: cluster_column '{cc}' is not in the data; "
                   f"the real run will exit 3")

    print("=" * 96)
    print("[preview] No model was fitted (--check-missing). No Excel was written.")
    print("=" * 96)


# ═══════════════════════════════════════════════════════════════════════════════
# Driver
# ═══════════════════════════════════════════════════════════════════════════════

def run(config, df, variables):
    cluster_col = config.get('cluster_column')
    method = config['method']
    is_cox = config['analysis_type'] == 'cox'

    if not cluster_col:
        qc_blocking("cluster_column is not set: there is no clustering variable to correct for")
        return 3
    if cluster_col not in df.columns:
        qc_blocking(f"cluster_column '{cluster_col}' does not exist in the data file")
        return 3

    out_cols = [c for c in outcome_columns(config) if c]
    missing_out = [c for c in out_cols if c not in df.columns]
    if missing_out:
        qc_blocking(f"outcome column(s) not found in the data: {', '.join(missing_out)}")
        return 3

    if is_cox and method in ('gee', 'mixed'):
        qc_blocking(
            f"method = '{method}' was requested with analysis_type = 'cox'. Neither GEE nor a "
            f"statsmodels mixed model is a survival model, so this cannot be fitted and will not be "
            f"silently substituted. For clustered time-to-event data use method = 'cluster_robust' "
            f"(advanced_analyses.md section 4), or a shared-frailty Cox model, which this script "
            f"does not implement.")
        return 3

    d, model_cols, label_map, missing_cols = build_design(df, config, variables)
    if missing_cols:
        qc_blocking(f"model columns not found in the data: {', '.join(missing_cols)}")
        return 3
    if not model_cols:
        qc_blocking("no usable covariate remains after dropping zero-variance columns")
        return 3
    if len(d) == 0:
        qc_blocking("no complete cases remain after listwise deletion")
        return 3

    summ = cluster_summary(d, cluster_col, config)
    print(f"\nComplete cases : n = {summ['n_obs']}, clusters = {summ['n_clusters']}, "
          f"sizes {summ['min_size']}–{summ['max_size']} (median {summ['median_size']:.1f})")

    # ── blocking cluster-structure checks ──────────────────────────────────
    if summ['n_clusters'] <= 1:
        qc_blocking(f"cluster_column '{cluster_col}' has only {summ['n_clusters']} distinct "
                    f"value(s) in the analysed rows: there is no between-cluster variation to "
                    f"correct for, and a cluster-robust variance is not defined")
        return 3
    if summ['n_clusters'] == summ['n_obs']:
        qc_blocking(f"cluster_column '{cluster_col}' takes a different value for every one of the "
                    f"{summ['n_obs']} analysed observations: every observation is its own cluster, "
                    f"which is the same as assuming independence. Either this is the wrong column, "
                    f"or the data are not clustered and this step should not be run.")
        return 3

    # ── warnings ───────────────────────────────────────────────────────────
    if summ['n_clusters'] < MIN_CLUSTERS:
        qc_warning(
            f"only {summ['n_clusters']} clusters (< {MIN_CLUSTERS}): cluster-robust standard errors "
            f"are asymptotic in the number of clusters and are themselves biased downwards at this "
            f"count (advanced_analyses.md section 4). The corrected SE reported here is still likely "
            f"to be too small. Consider a wild cluster bootstrap or a mixed model, and state the "
            f"limitation.")
    if summ['largest_share'] > MAX_SINGLE_CLUSTER_SHARE:
        qc_warning(
            f"cluster '{summ['largest_label']}' holds {summ['max_size']}/{summ['n_obs']} "
            f"({100 * summ['largest_share']:.1f}%) of the analysed sample, above the "
            f"{100 * MAX_SINGLE_CLUSTER_SHARE:.0f}% threshold: the pooled result is substantially "
            f"this one cluster's result. Run a leave-one-cluster-out sensitivity analysis before "
            f"presenting it as a multi-centre finding.")
    if not config['_structure_from_config']:
        qc_warning(
            f"correlation_structure was not specified in the config; the script default "
            f"'{DEFAULT_STRUCTURE}' was applied and written into the output. "
            f"advanced_analyses.md section 4 forbids using a default correlation structure without "
            f"stating it — register it in decision_log.md with a permanent ID.")
    if method == 'mixed':
        qc_warning(
            "method = 'mixed' uses statsmodels BinomialBayesMixedGLM with variational Bayes: the "
            "intervals are approximate posterior intervals and VB is known to understate spread. The "
            "effect is also cluster-conditional, not marginal, so it is not numerically comparable "
            "with the naive or GEE estimates.")

    codes = pd.factorize(d[cluster_col])[0]

    # ── fits ───────────────────────────────────────────────────────────────
    try:
        if method == 'cluster_robust':
            robust_fit = (fit_cox(d, model_cols, config, cluster_col=cluster_col) if is_cox
                          else fit_logit_plain(d, model_cols, config, cluster_codes=codes))
        elif method == 'gee':
            robust_fit = fit_gee(d, model_cols, config, codes)
        else:
            robust_fit = fit_mixed_binomial(d, model_cols, config, codes)
    except FitFailure as e:
        qc_blocking(f"{method} model failed: {e}")
        return 3
    except Exception as e:
        qc_blocking(f"{method} model failed ({type(e).__name__}: {e})")
        return 3

    naive_fit = None
    if config['compare_to_naive']:
        try:
            naive_fit = (fit_cox(d, model_cols, config) if is_cox
                         else fit_logit_plain(d, model_cols, config))
        except FitFailure as e:
            qc_blocking(f"uncorrected comparator model failed: {e}")
            return 3
        except Exception as e:
            qc_blocking(f"uncorrected comparator model failed ({type(e).__name__}: {e})")
            return 3
    else:
        qc_warning("compare_to_naive is false: the Naive_vs_Robust sheet is the single most useful "
                   "output of this step for a reviewer, and it was disabled.")

    # A variational-Bayes mixed model that barely widens anything, in a design
    # with few clusters, is almost certainly understating the uncertainty rather
    # than discovering that the clustering does not matter.
    if method == 'mixed' and naive_fit is not None:
        ratios = [robust_fit['terms'][t]['se'] / naive_fit['terms'][t]['se']
                  for t in model_cols if naive_fit['terms'][t]['se'] > 0]
        if ratios and max(ratios) < 1.05 and summ['n_clusters'] < MIN_CLUSTERS:
            qc_warning(
                f"the random-intercept model widened no standard error by more than "
                f"{100 * (max(ratios) - 1):.1f}% even though there are only "
                f"{summ['n_clusters']} clusters. Variational Bayes is known to understate "
                f"posterior spread, so read this as a limitation of the fitting method rather "
                f"than as evidence that the clustering is unimportant — cross-check with "
                f"method = 'cluster_robust' before reporting.")

    # ── console report ─────────────────────────────────────────────────────
    print(f"\n{'Term':<26} {'naive SE':>10} {f'{method} SE':>18} {'SE ratio':>10} "
          f"{'naive p':>10} {'robust p':>10}")
    print("-" * 92)
    for t in model_cols:
        rb = robust_fit['terms'][t]
        if naive_fit:
            nv = naive_fit['terms'][t]
            print(f"{t:<26} {nv['se']:>10.4f} {rb['se']:>18.4f} "
                  f"{rb['se'] / nv['se']:>10.3f} {nv['p']:>10.4f} {rb['p']:>10.4f}")
        else:
            print(f"{t:<26} {'—':>10} {rb['se']:>18.4f} {'—':>10} {'—':>10} {rb['p']:>10.4f}")

    sheets = write_excel(config, summ, robust_fit, naive_fit, label_map, model_cols)
    print(f"\nExcel written : {config['output_file']}")
    print(f"  Sheets: {', '.join(sheets)}")
    return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python robust_variance.py config.json [--check-missing]")
        sys.exit(1)

    config_path = sys.argv[1]
    check_only = '--check-missing' in sys.argv

    config = load_config(config_path)
    df = load_data(config)
    variables = collect_variables(config)

    print(f"Mode: {config['mode']}  ({config['analysis_type']}, method = {config['method']})")
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
