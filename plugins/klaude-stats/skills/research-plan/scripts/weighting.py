#!/usr/bin/env python3
"""
Propensity score weighting — IPTW and overlap weighting (research-plan pipeline)

Implements references/advanced_analyses.md section 6 ("IPTW and overlap weighting —
matching is not the only way to use a propensity score").

    python weighting.py config.json                  # full run
    python weighting.py config.json --check-missing  # preview only, no fitting

Why this script exists
----------------------
psm_matching.py estimates the ATT, and only in the subset that actually found a
match — everyone unmatched is silently deleted from the inference population, and
nothing in that script diagnoses positivity. Weighting keeps every patient and makes
the target population explicit, but it fails in its own characteristic way: a
handful of patients with propensity scores near 0 or 1 receive enormous weights and
end up driving the entire result. Everything in this script is built around making
that failure visible instead of letting it hide inside a confidence interval.

Estimands (they are three different clinical questions, never interchangeable)
-----------------------------------------------------------------------------
    IPTW     -> ATE : effect if the whole study population were treated vs untreated
    matching -> ATT : effect in the patients who actually received treatment
    overlap  -> ATO : effect in the population with genuine clinical equipoise

Choosing between them because one produced a smaller p-value is data dredging. The
choice belongs in the protocol and in decision_log.md.
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

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


_QC_MESSAGES = []


def qc(kind, message):
    line = f"[QC_{kind}] {message}"
    _QC_MESSAGES.append(line)
    print(line, file=sys.stderr)


def qc_warning(message):
    qc('WARNING', message)


def qc_blocking(message):
    qc('BLOCKING', message)


def n_blocking():
    return sum(1 for m in _QC_MESSAGES if m.startswith('[QC_BLOCKING]'))


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULTS = {
    'method': 'iptw',
    'stabilized': True,
    'seed': 42,
    'smd_threshold': 0.1,
    'extreme_weight_threshold': 10.0,
    'max_weight_share_threshold': 0.05,
    'ess_fraction_threshold': 0.5,
    # Screening thresholds, not validity cut-offs. Neither has a consensus value
    # in the literature; both raise a QC warning. The only blocking positivity
    # condition is empty common support. (Changed from blocking on 2026-08-11 —
    # blocking on numbers this arbitrary produced false stops.)
    'overlap_coefficient_threshold': 0.10,
    'nonoverlap_fraction_threshold': 0.20,
}

TRIM_DEFAULT = {'enabled': False, 'percentile': [1, 99]}


def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    config.setdefault('mode', 'weighting')
    if config['mode'] != 'weighting':
        sys.exit(f"[FATAL] Unknown mode: {config['mode']!r} (expected 'weighting')")

    config.setdefault('filters', [])
    config.setdefault('derived_variables', [])
    config.setdefault('title', 'Propensity score weighted analysis')
    config.setdefault('subtitle', '')
    config.setdefault('abbreviations', '')
    config.setdefault('sections', [])

    provenance = {}
    for key, default in DEFAULTS.items():
        provenance[key] = 'config' if key in config else 'default'
        config.setdefault(key, default)

    trim = config.get('trim') or {}
    provenance['trim'] = 'config' if 'trim' in config else 'default'
    for k, v in TRIM_DEFAULT.items():
        trim.setdefault(k, v)
    config['trim'] = trim
    config['_provenance'] = provenance

    if config['method'] not in ('iptw', 'overlap'):
        sys.exit("[FATAL] method must be 'iptw' or 'overlap'")

    at = config.get('analysis_type')
    if at not in ('cox', 'logistic', 'linear'):
        sys.exit("[FATAL] analysis_type must be 'cox', 'logistic' or 'linear'")

    g = config.get('grouping') or {}
    if not g.get('column') or len(g.get('groups') or []) != 2:
        sys.exit("[FATAL] grouping.column and exactly two grouping.groups are required "
                 "(the first group is the treated arm)")

    if at == 'cox':
        cs = config.get('cox_settings') or {}
        if not cs.get('time_column') or not cs.get('event_column'):
            sys.exit("[FATAL] cox_settings.time_column and cox_settings.event_column are required")
    elif at == 'logistic':
        if not (config.get('logistic_settings') or {}).get('outcome_column'):
            sys.exit("[FATAL] logistic_settings.outcome_column is required")
    else:
        ls = config.get('linear_settings') or {}
        if not ls.get('outcome_column'):
            sys.exit("[FATAL] linear_settings.outcome_column is required")

    base = os.path.splitext(os.path.basename(path))[0]
    config.setdefault('output_file', f"{base}_weighting.xlsx")
    config.setdefault('plot_file', f"{base}_ps_overlap.png")
    stem, ext = os.path.splitext(config['plot_file'])
    config.setdefault('love_plot_file', f"{stem}_love{ext or '.png'}")
    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Data loading
# ═══════════════════════════════════════════════════════════════════════════════

EQ_OPS = {'==': operator.eq, '!=': operator.ne}
NUMERIC_OPS = {'>': operator.gt, '>=': operator.ge, '<': operator.lt, '<=': operator.le}


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
        if op in EQ_OPS:
            df = df[EQ_OPS[op](df[col], val)]
        elif op in NUMERIC_OPS:
            df = df[NUMERIC_OPS[op](pd.to_numeric(df[col], errors='coerce'), val)]
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
            ns = {dep: pd.to_numeric(df[dep], errors='coerce')
                  for dep in dv.get('dependencies', [])}
            ns['np'] = np
            df[dv['name']] = eval(dv['expression'], {"__builtins__": {}}, ns)

    return df.reset_index(drop=True)


def ps_variables(config):
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


def build_design(df, ps_vars):
    cols, terms = {}, []
    for v in ps_vars:
        col, vtype = v['column'], v['type']
        if col not in df.columns:
            sys.exit(f"[FATAL] Propensity score variable '{col}' not found in data")
        if vtype == 'categorical':
            s = df[col].astype(str)
            s = s.where(df[col].notna() & (s.str.strip() != ''), np.nan)
            levels = sorted(x for x in s.dropna().unique())
            ref = v.get('reference_level')
            ref = str(ref) if ref is not None else (levels[0] if levels else None)
            for lev in levels:
                if lev == ref:
                    continue
                name = f"x{len(terms)}"
                cols[name] = np.where(s.isna(), np.nan, (s == lev).astype(float))
                terms.append({'safe': name, 'label': f"{v['label']} = {lev}",
                              'column': col, 'type': 'binary', 'section': v['section']})
        else:
            s = pd.to_numeric(df[col], errors='coerce')
            if v.get('scale'):
                s = s / float(v['scale'])
            name = f"x{len(terms)}"
            cols[name] = s.values
            terms.append({'safe': name, 'label': v['label'], 'column': col,
                          'type': 'binary' if vtype == 'binary' else 'continuous',
                          'section': v['section']})
    return pd.DataFrame(cols, index=df.index), terms


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
BOLD_FONT = Font(name='Arial', size=10, bold=True)
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
            cell.font = BOLD_FONT
        cell.border = THIN_BORDER
        cell.alignment = LEFT if c == 1 else CENTER
        if flag:
            cell.fill = FLAG_FILL
        elif alt:
            cell.fill = ALT_FILL
    return r + 1


def write_para(ws, r, ncol, text, bold=False):
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
    cell = ws.cell(row=r, column=1, value=text)
    cell.font = BOLD_FONT if bold else DATA_FONT
    cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True, indent=1)
    ws.row_dimensions[r].height = max(15, 13 * (1 + len(text) // 110 + text.count('\n')))
    return r + 1


def write_footnote(ws, r, ncol, text):
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
    cell = ws.cell(row=r, column=1, value=text)
    cell.font = FOOTNOTE_FONT
    cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)
    ws.row_dimensions[r].height = max(14, 11 * (1 + len(text) // 130 + text.count('\n')))
    return r + 1


def fmt_num(x, nd=3):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "N/A"
    return f"{x:.{nd}f}"


def fmt_p(p):
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "N/A"
    if p < 0.001:
        return "<0.001*"
    if p < 0.05:
        return f"{p:.3f}*"
    return f"{p:.3f}"


def fmt_effect(est, lo, hi, nd=3):
    if est is None or (isinstance(est, float) and math.isnan(est)):
        return "N/A"
    if lo is None or hi is None or any(isinstance(v, float) and math.isnan(v) for v in (lo, hi)):
        return f"{est:.{nd}f}"
    return f"{est:.{nd}f} ({lo:.{nd}f}–{hi:.{nd}f})"


# ═══════════════════════════════════════════════════════════════════════════════
# Propensity scores, weights, diagnostics
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_ps(X, A):
    """Unregularized logistic regression, the standard propensity score model.
    Regularization would shrink coefficients and is not appropriate here: the PS
    model exists to balance covariates, not to predict treatment parsimoniously."""
    import statsmodels.api as sm
    Xc = sm.add_constant(X.values.astype(float), has_constant='add')
    model = sm.Logit(A.astype(float), Xc).fit(disp=0, method='newton', maxiter=500)
    # statsmodels only warns when the optimizer gives up; a divergent propensity
    # score model silently produces scores pinned at 0 and 1, which is exactly the
    # situation the positivity gate exists to catch, so it must not pass quietly.
    if not model.mle_retvals.get('converged', True):
        raise RuntimeError('propensity score model did not converge (this usually means '
                           'treatment is perfectly predicted by the covariates)')
    if not np.all(np.isfinite(np.asarray(model.params, dtype=float))):
        raise RuntimeError('propensity score model produced non-finite coefficients')
    ps = np.clip(np.asarray(model.predict(Xc), dtype=float), 1e-8, 1 - 1e-8)
    return ps, model


def compute_weights(ps, A, method, stabilized):
    """IPTW -> ATE (optionally stabilized); overlap -> ATO."""
    A = np.asarray(A, dtype=float)
    if method == 'overlap':
        # Overlap weights are self-stabilizing by construction: the treated get
        # (1 - e) and the controls get e, so nobody near e = 0 or 1 can dominate.
        return A * (1.0 - ps) + (1.0 - A) * ps
    w = A / ps + (1.0 - A) / (1.0 - ps)
    if stabilized:
        p_treat = float(A.mean())
        w = A * p_treat / ps + (1.0 - A) * (1.0 - p_treat) / (1.0 - ps)
    return w


def effective_sample_size(w):
    w = np.asarray(w, dtype=float)
    s = w.sum()
    ss = (w ** 2).sum()
    return float(s ** 2 / ss) if ss > 0 else 0.0


def overlap_coefficient(ps_t, ps_c, n_bins=50):
    """Integrated minimum of the two densities: 1 = identical distributions,
    0 = no common support at all. The single most informative positivity number."""
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ht, _ = np.histogram(ps_t, bins=edges, density=True)
    hc, _ = np.histogram(ps_c, bins=edges, density=True)
    return float(np.sum(np.minimum(ht, hc)) * (edges[1] - edges[0]))


def ps_distribution_stats(ps, label):
    q = np.percentile(ps, [0, 1, 5, 25, 50, 75, 95, 99, 100])
    return {'label': label, 'n': int(len(ps)), 'mean': float(np.mean(ps)),
            'sd': float(np.std(ps, ddof=1)) if len(ps) > 1 else np.nan,
            'min': float(q[0]), 'p1': float(q[1]), 'p5': float(q[2]),
            'q1': float(q[3]), 'median': float(q[4]), 'q3': float(q[5]),
            'p95': float(q[6]), 'p99': float(q[7]), 'max': float(q[8]),
            'n_lt_001': int((ps < 0.01).sum()), 'n_gt_099': int((ps > 0.99).sum())}


def weighted_mean(v, w):
    v = np.asarray(v, dtype=float)
    w = np.asarray(w, dtype=float)
    m = np.isfinite(v)
    if not m.any() or w[m].sum() == 0:
        return np.nan
    return float(np.sum(v[m] * w[m]) / np.sum(w[m]))


def weighted_var(v, w):
    v = np.asarray(v, dtype=float)
    w = np.asarray(w, dtype=float)
    m = np.isfinite(v)
    if m.sum() < 2 or w[m].sum() == 0:
        return np.nan
    mu = weighted_mean(v, w)
    sw = np.sum(w[m])
    sw2 = np.sum(w[m] ** 2)
    denom = sw - sw2 / sw
    if denom <= 0:
        return np.nan
    return float(np.sum(w[m] * (v[m] - mu) ** 2) / denom)


def smd(v_t, w_t, v_c, w_c, vtype):
    """Standardized mean difference. Austin & Stuart 2015: weighted means with
    weighted variances in the pooled denominator. Reported signed AND absolute;
    the sheets show the absolute value because that is what the 0.1 rule uses."""
    if vtype == 'binary':
        p_t, p_c = weighted_mean(v_t, w_t), weighted_mean(v_c, w_c)
        if not (np.isfinite(p_t) and np.isfinite(p_c)):
            return np.nan
        den = math.sqrt((p_t * (1 - p_t) + p_c * (1 - p_c)) / 2.0)
        return 0.0 if den == 0 else abs(p_t - p_c) / den
    m_t, m_c = weighted_mean(v_t, w_t), weighted_mean(v_c, w_c)
    s_t, s_c = weighted_var(v_t, w_t), weighted_var(v_c, w_c)
    if not (np.isfinite(m_t) and np.isfinite(m_c)):
        return np.nan
    if not np.isfinite(s_t):
        s_t = 0.0
    if not np.isfinite(s_c):
        s_c = 0.0
    den = math.sqrt((s_t + s_c) / 2.0)
    return 0.0 if den == 0 else abs(m_t - m_c) / den


def display_stat(v, w, vtype):
    if vtype == 'binary':
        p = weighted_mean(v, w)
        return "N/A" if not np.isfinite(p) else f"{100.0 * p:.1f}%"
    m, s = weighted_mean(v, w), weighted_var(v, w)
    if not np.isfinite(m):
        return "N/A"
    return f"{m:.2f} ± {math.sqrt(s):.2f}" if np.isfinite(s) and s >= 0 else f"{m:.2f}"


def balance_table(work, terms, A, w, ps_vars_lookup):
    rows = []
    ones = np.ones(len(work))
    t_mask = A == 1
    c_mask = A == 0
    for t in terms:
        v = work[t['safe']].values.astype(float)
        rows.append({
            'label': t['label'], 'section': t['section'], 'type': t['type'],
            'before_t': display_stat(v[t_mask], ones[t_mask], t['type']),
            'before_c': display_stat(v[c_mask], ones[c_mask], t['type']),
            'smd_before': smd(v[t_mask], ones[t_mask], v[c_mask], ones[c_mask], t['type']),
            'after_t': display_stat(v[t_mask], w[t_mask], t['type']),
            'after_c': display_stat(v[c_mask], w[c_mask], t['type']),
            'smd_after': smd(v[t_mask], w[t_mask], v[c_mask], w[c_mask], t['type']),
        })
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# Weighted outcome models (robust / sandwich SE throughout)
# ═══════════════════════════════════════════════════════════════════════════════

def outcome_cox(work, A, w, time_col, event_col, robust=True):
    from lifelines import CoxPHFitter
    d = pd.DataFrame({'A': np.asarray(A, dtype=float),
                      time_col: work[time_col].values.astype(float),
                      event_col: work[event_col].values.astype(float),
                      '_w': np.asarray(w, dtype=float)})
    d = d[d['_w'] > 0]
    cph = CoxPHFitter()
    cph.fit(d, duration_col=time_col, event_col=event_col, weights_col='_w',
            formula='A', robust=robust)
    beta = float(cph.params_['A'])
    se = float(cph.standard_errors_['A'])
    z = beta / se if se > 0 else np.nan
    from scipy import stats as sps
    p = float(2 * sps.norm.sf(abs(z))) if np.isfinite(z) else np.nan
    return {'scale': 'Hazard ratio', 'estimate': math.exp(beta),
            'ci_lo': math.exp(beta - 1.96 * se), 'ci_hi': math.exp(beta + 1.96 * se),
            'log_est': beta, 'se': se, 'p': p, 'null': 1.0,
            'se_type': 'robust (sandwich)' if robust else 'model-based'}


def outcome_logistic(y, A, w):
    import statsmodels.api as sm
    from scipy import stats as sps
    X = sm.add_constant(np.asarray(A, dtype=float).reshape(-1, 1), has_constant='add')
    m = sm.GLM(np.asarray(y, dtype=float), X, family=sm.families.Binomial(),
               freq_weights=np.asarray(w, dtype=float)).fit(cov_type='HC0')
    beta = float(m.params[1])
    se = float(m.bse[1])
    z = beta / se if se > 0 else np.nan
    p = float(2 * sps.norm.sf(abs(z))) if np.isfinite(z) else np.nan
    return {'scale': 'Odds ratio', 'estimate': math.exp(beta),
            'ci_lo': math.exp(beta - 1.96 * se), 'ci_hi': math.exp(beta + 1.96 * se),
            'log_est': beta, 'se': se, 'p': p, 'null': 1.0,
            'se_type': 'robust (HC0 sandwich)'}


def outcome_linear(y, A, w):
    import statsmodels.api as sm
    from scipy import stats as sps
    X = sm.add_constant(np.asarray(A, dtype=float).reshape(-1, 1), has_constant='add')
    m = sm.WLS(np.asarray(y, dtype=float), X,
               weights=np.asarray(w, dtype=float)).fit(cov_type='HC0')
    beta = float(m.params[1])
    se = float(m.bse[1])
    z = beta / se if se > 0 else np.nan
    p = float(2 * sps.norm.sf(abs(z))) if np.isfinite(z) else np.nan
    return {'scale': 'Mean difference', 'estimate': beta,
            'ci_lo': beta - 1.96 * se, 'ci_hi': beta + 1.96 * se,
            'log_est': beta, 'se': se, 'p': p, 'null': 0.0,
            'se_type': 'robust (HC0 sandwich)'}


def fit_outcome(config, work, A, w):
    at = config['analysis_type']
    if at == 'cox':
        cs = config['cox_settings']
        return outcome_cox(work, A, w, cs['time_column'], cs['event_column'])
    if at == 'logistic':
        y = work[config['logistic_settings']['outcome_column']].values.astype(float)
        return outcome_logistic(y, A, w)
    y = work[config['linear_settings']['outcome_column']].values.astype(float)
    return outcome_linear(y, A, w)


def additive_contrast(config, work, A, w):
    """Weighted arm-level summary on the additive scale. For a binary or
    continuous outcome this IS the estimand (risk difference / mean difference)
    and it is what the truth check in validation compares against."""
    at = config['analysis_type']
    if at == 'cox':
        return None
    col = (config['logistic_settings']['outcome_column'] if at == 'logistic'
           else config['linear_settings']['outcome_column'])
    y = work[col].values.astype(float)
    A = np.asarray(A, dtype=float)
    m_t = weighted_mean(y[A == 1], np.asarray(w)[A == 1])
    m_c = weighted_mean(y[A == 0], np.asarray(w)[A == 0])
    return {'treated': m_t, 'control': m_c, 'difference': m_t - m_c,
            'label': 'Weighted risk difference' if at == 'logistic'
                     else 'Weighted mean difference'}


# ═══════════════════════════════════════════════════════════════════════════════
# Analysis driver
# ═══════════════════════════════════════════════════════════════════════════════

ESTIMAND_TEXT = {
    'ate': ("ATE — average treatment effect in the ENTIRE study population. "
            "Clinical question: what would happen to outcomes in this whole population "
            "if everyone received the treatment, compared with nobody receiving it? "
            "It is the right estimand for a policy or guideline decision that will apply "
            "to all comers, and it requires that every patient could plausibly have "
            "received either treatment (positivity)."),
    'ato': ("ATO — average treatment effect in the OVERLAP population. "
            "Clinical question: what would happen in the patients for whom there is "
            "genuine clinical equipoise, i.e. those who could realistically have gone "
            "either way? Patients with a near-certain treatment assignment contribute "
            "almost nothing. This is the right estimand when positivity is shaky, and "
            "it has the practical advantage that no single patient can dominate. Its "
            "cost is that the target population is defined by the data rather than by a "
            "pre-specified clinical group, so it must be described (not just named) when "
            "the results are reported."),
    'att': ("ATT — average treatment effect in the TREATED. Clinical question: for the "
            "patients who actually received the treatment, how did they fare compared "
            "with how they would have fared untreated? This is what propensity score "
            "MATCHING estimates; this script does not estimate it."),
}


def run_analysis(config, df):
    method = config['method']
    stabilized = bool(config['stabilized']) and method == 'iptw'
    at = config['analysis_type']

    g = config['grouping']
    gcol = g['column']
    g_t, g_c = g['groups'][0], g['groups'][1]

    ps_vars = ps_variables(config)
    if not ps_vars:
        sys.exit("[FATAL] sections must define at least one propensity score variable")
    X_all, terms = build_design(df, ps_vars)

    if at == 'cox':
        cs = config['cox_settings']
        outcome_cols = [cs['time_column'], cs['event_column']]
    elif at == 'logistic':
        outcome_cols = [config['logistic_settings']['outcome_column']]
    else:
        outcome_cols = [config['linear_settings']['outcome_column']]

    if gcol not in df.columns:
        sys.exit(f"[FATAL] Grouping column '{gcol}' not found in data")
    gvals = df[gcol]
    if all(isinstance(x.get('value'), (int, float)) and not isinstance(x.get('value'), bool)
           for x in (g_t, g_c)):
        gvals = pd.to_numeric(df[gcol], errors='coerce')
    A_all = pd.Series(np.nan, index=df.index)
    A_all[gvals == g_t['value']] = 1.0
    A_all[gvals == g_c['value']] = 0.0

    work = pd.concat([X_all, df[outcome_cols], A_all.rename('_A')], axis=1)
    for c in outcome_cols:
        work[c] = pd.to_numeric(work[c], errors='coerce')
    n_before = len(work)
    work = work.dropna().reset_index(drop=True)
    n_dropped = n_before - len(work)

    A = work['_A'].values.astype(float)
    n_t, n_c = int((A == 1).sum()), int((A == 0).sum())
    print(f"  {g_t.get('label','Treated')}: n={n_t}   {g_c.get('label','Control')}: n={n_c}")
    if n_dropped:
        print(f"  Listwise deletion removed {n_dropped} row(s) with missing PS/outcome data")

    result = {'method': method, 'stabilized': stabilized, 'analysis_type': at,
              'terms': terms, 'n_total': n_before, 'n_analyzed': len(work),
              'n_dropped': n_dropped, 'n_treated': n_t, 'n_control': n_c,
              'label_t': g_t.get('label', 'Treated'), 'label_c': g_c.get('label', 'Control'),
              'estimand': 'ATO' if method == 'overlap' else 'ATE'}

    if n_t < 10 or n_c < 10:
        qc_blocking(f"Fewer than 10 subjects in an arm after listwise deletion "
                    f"(treated {n_t}, control {n_c}); weighting cannot be estimated")
        return result

    X = work[[t['safe'] for t in terms]]
    try:
        ps, ps_model = estimate_ps(X, A)
    except Exception as e:
        qc_blocking(f"Positivity failure: the propensity score model could not be fitted "
                    f"({type(e).__name__}: {e}); treatment assignment is (near-)perfectly "
                    f"predicted by the covariates, so the groups are not comparable and "
                    f"weighting cannot fix it")
        return result
    work['_ps'] = ps
    result['ps_model'] = [
        {'term': (['(Intercept)'] + [t['label'] for t in terms])[i],
         'beta': float(b), 'se': float(s)}
        for i, (b, s) in enumerate(zip(ps_model.params, ps_model.bse))]

    ps_t, ps_c = ps[A == 1], ps[A == 0]
    result['ps_stats'] = [ps_distribution_stats(ps_t, result['label_t']),
                          ps_distribution_stats(ps_c, result['label_c']),
                          ps_distribution_stats(ps, 'Overall')]

    lo_cs = max(ps_t.min(), ps_c.min())
    hi_cs = min(ps_t.max(), ps_c.max())
    n_outside = int(((ps < lo_cs) | (ps > hi_cs)).sum()) if hi_cs > lo_cs else len(ps)
    ovl = overlap_coefficient(ps_t, ps_c)
    result['positivity'] = {'common_support_lo': float(lo_cs), 'common_support_hi': float(hi_cs),
                            'n_outside_common_support': n_outside,
                            'frac_outside': n_outside / len(ps),
                            'overlap_coefficient': ovl}

    marginal_reasons = []
    # ── Positivity gate. Weighting cannot manufacture comparability. ─────────
    # Only the structural failure blocks: empty common support is a fact, not a
    # judgement call, and no weighting scheme survives it. The two graded
    # thresholds below were blocking until 2026-08-11 and are now warnings —
    # neither 0.10 on the overlap coefficient nor 20% outside common support has
    # a consensus cut-point in the literature, so blocking on them stopped runs
    # that a reviewer would have accepted with the diagnostic reported. Marginal
    # overlap is a limitation to disclose, not a reason to withhold the number.
    # Both are checked independently: a run can breach one, the other, or both,
    # and the analyst needs to see every breach rather than the first one only.
    if hi_cs <= lo_cs:
        qc_blocking("Positivity failure: the two groups' propensity score ranges do not "
                    "overlap at all; there is no common support and weighting cannot fix it")
    else:
        # These two are diagnostics of the data as collected, so they are computed
        # before any trimming and trimming does not clear them: dropping subjects
        # changes the population, it does not create overlap that was not there.
        if ovl < config['overlap_coefficient_threshold']:
            marginal_reasons.append(
                f"overlap coefficient {ovl:.3f} < {config['overlap_coefficient_threshold']:.2f}")
            qc_warning(f"Marginal positivity: propensity score overlap coefficient = {ovl:.3f} "
                       f"(< {config['overlap_coefficient_threshold']:.2f}); treatment assignment "
                       f"is close to deterministic over part of the covariate space. The "
                       f"estimate is reported, but it leans on extrapolation")
        if result['positivity']['frac_outside'] > config['nonoverlap_fraction_threshold']:
            marginal_reasons.append(
                f"{100.0 * result['positivity']['frac_outside']:.1f}% outside common support "
                f"> {100.0 * config['nonoverlap_fraction_threshold']:.0f}%")
            qc_warning(f"Marginal positivity: {n_outside}/{len(ps)} "
                       f"({100.0 * result['positivity']['frac_outside']:.1f}%) of subjects lie "
                       f"outside the region of common support "
                       f"(> {100.0 * config['nonoverlap_fraction_threshold']:.0f}%); those "
                       f"subjects have no counterpart in the other arm")
    result['positivity']['marginal'] = bool(marginal_reasons)
    result['positivity']['marginal_reasons'] = marginal_reasons
    if n_blocking():
        return result

    # ── Weights, untrimmed ───────────────────────────────────────────────────
    w_full = compute_weights(ps, A, method, stabilized)
    result['untrimmed'] = summarize_weighting(config, work, terms, A, ps, w_full, label='untrimmed')

    # ── Trimming ─────────────────────────────────────────────────────────────
    trim = config['trim']
    if trim.get('enabled'):
        p_lo, p_hi = float(trim['percentile'][0]), float(trim['percentile'][1])
        t_lo, t_hi = np.percentile(ps, [p_lo, p_hi])
        keep = (ps >= t_lo) & (ps <= t_hi)
        result['trim'] = {'enabled': True, 'percentile': [p_lo, p_hi],
                          'threshold_lo': float(t_lo), 'threshold_hi': float(t_hi),
                          'n_trimmed': int((~keep).sum()),
                          'n_trimmed_treated': int(((~keep) & (A == 1)).sum()),
                          'n_trimmed_control': int(((~keep) & (A == 0)).sum()),
                          'n_remaining': int(keep.sum())}
        if keep.sum() < 20 or (A[keep] == 1).sum() < 5 or (A[keep] == 0).sum() < 5:
            qc_blocking("Trimming left too few subjects to analyse "
                        f"({int(keep.sum())} remaining); relax the trimming percentiles")
            return result
        work_t = work[keep].reset_index(drop=True)
        A_t = A[keep]
        ps_t2 = ps[keep]
        # Weights are recomputed from the retained subjects (the stabilization
        # numerator changes once the sample changes).
        w_t = compute_weights(ps_t2, A_t, method, stabilized)
        result['primary'] = summarize_weighting(config, work_t, terms, A_t, ps_t2, w_t,
                                                label='trimmed (primary)')
        result['primary_is_trimmed'] = True
    else:
        result['trim'] = {'enabled': False, 'percentile': trim.get('percentile')}
        result['primary'] = result['untrimmed']
        result['primary_is_trimmed'] = False

    # ── ATO companion, when positivity is marginal ──────────────────────────
    # An IPTW estimate under marginal overlap is an ATE that leans on
    # extrapolation into regions where one arm barely exists. The standard
    # response is to report it beside the estimand the data actually support —
    # the overlap-weighted ATO (Li, Morgan & Zaslavsky 2018), which downweights
    # exactly those subjects instead of extrapolating over them.
    #
    # It is computed here, in the same step, from the same propensity model:
    # only the weights change, so the cost is negligible. Requiring a separate
    # pipeline step would have made "do not report this alone" one more rule
    # that a plan could be written around; computing it here makes the companion
    # exist by construction. Trimming is not a substitute — a trimmed ATE is
    # still an ATE, on a population defined by the data rather than by the
    # research question.
    result['ato_companion'] = None
    if result['positivity'].get('marginal') and method != 'overlap':
        try:
            w_ato = compute_weights(ps, A, 'overlap', stabilized)
            result['ato_companion'] = summarize_weighting(
                config, work, terms, A, ps, w_ato, label='ATO companion (overlap weights)')
            qc_warning(
                f"Marginal positivity ({'; '.join(marginal_reasons)}): an overlap-weighted "
                f"(ATO) companion analysis has been computed from the same propensity model "
                f"and written to the output. **Report the two together** — the "
                f"{result['estimand']} estimate answers the question you asked, the ATO "
                f"estimate is the one this data supports without extrapolation. Presenting "
                f"either alone is selective reporting.")
        except Exception as e:
            qc_blocking(
                f"Marginal positivity was detected but the ATO companion analysis could not "
                f"be computed ({type(e).__name__}: {e}). The {result['estimand']} estimate "
                f"must not be reported on its own under marginal overlap; fix this or run "
                f"the weighting step with method='overlap'.")
            return result

    # ── Crude (unweighted) comparison, shown side by side ───────────────────
    try:
        result['crude'] = fit_outcome(config, work, A, np.ones(len(work)))
        result['crude_additive'] = additive_contrast(config, work, A, np.ones(len(work)))
    except Exception as e:
        print(f"  [crude model] {type(e).__name__}: {e}", file=sys.stderr)
        result['crude'] = None
        result['crude_additive'] = None

    # ── QC on the primary weighting ─────────────────────────────────────────
    prim = result['primary']
    ext = config['extreme_weight_threshold']
    if prim['n_weight_gt_threshold'] > 0:
        qc_warning(f"{prim['n_weight_gt_threshold']} subject(s) have a weight > {ext:g} "
                   f"(maximum weight = {prim['max_weight']:.2f}); a small number of patients "
                   f"is carrying a large share of the analysis")
    if prim['max_weight_share'] > config['max_weight_share_threshold']:
        qc_warning(f"The single largest weight is {100.0 * prim['max_weight_share']:.1f}% of the "
                   f"total weight (> {100.0 * config['max_weight_share_threshold']:.0f}%); one "
                   f"individual case is dominating the weighted estimate")
    if prim['ess_fraction'] < config['ess_fraction_threshold']:
        qc_warning(f"Effective sample size = {prim['ess']:.1f} of {prim['n']} "
                   f"({100.0 * prim['ess_fraction']:.1f}% < "
                   f"{100.0 * config['ess_fraction_threshold']:.0f}%, a screening threshold "
                   f"rather than a validity cutoff); the weighted analysis carries much less "
                   f"information than the raw N suggests. Report ESS = {prim['ess']:.1f} "
                   f"alongside N = {prim['n']}, not the percentage alone")
    imbalanced = [b['label'] for b in prim['balance']
                  if np.isfinite(b['smd_after']) and b['smd_after'] > config['smd_threshold']]
    if imbalanced:
        qc_warning(f"{len(imbalanced)} variable(s) still have SMD > {config['smd_threshold']} "
                   f"after weighting: {', '.join(imbalanced)}; the propensity score model "
                   f"needs respecification (interactions, splines) before these results are used")

    return result


def summarize_weighting(config, work, terms, A, ps, w, label):
    n = len(work)
    ext = config['extreme_weight_threshold']
    ess = effective_sample_size(w)
    total_w = float(np.sum(w))
    out = {
        'label': label, 'n': n, 'ps': ps, 'A': A, 'w': w,
        'ess': ess, 'ess_fraction': ess / n if n else 0.0,
        'ess_treated': effective_sample_size(w[A == 1]),
        'ess_control': effective_sample_size(w[A == 0]),
        'mean_weight': float(np.mean(w)), 'sd_weight': float(np.std(w, ddof=1)) if n > 1 else np.nan,
        'min_weight': float(np.min(w)), 'max_weight': float(np.max(w)),
        'p99_weight': float(np.percentile(w, 99)),
        'n_weight_gt_threshold': int((w > ext).sum()),
        'max_weight_share': float(np.max(w) / total_w) if total_w > 0 else np.nan,
        'balance': balance_table(work, terms, A, w, None),
    }
    for arm, mask in (('treated', A == 1), ('control', A == 0)):
        ww = w[mask]
        out[f'weight_{arm}'] = {
            'n': int(mask.sum()), 'mean': float(np.mean(ww)),
            'sd': float(np.std(ww, ddof=1)) if mask.sum() > 1 else np.nan,
            'min': float(np.min(ww)), 'max': float(np.max(ww)),
            'sum': float(np.sum(ww)), 'ess': effective_sample_size(ww)}
    try:
        out['outcome'] = fit_outcome(config, work, A, w)
    except Exception as e:
        print(f"  [weighted outcome model, {label}] {type(e).__name__}: {e}", file=sys.stderr)
        out['outcome'] = None
        qc_blocking(f"Weighted outcome model failed to fit ({label}): {type(e).__name__}: {e}")
    out['additive'] = additive_contrast(config, work, A, w)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# Excel output
# ═══════════════════════════════════════════════════════════════════════════════

def write_excel(config, result):
    wb = Workbook()
    subtitle = config.get('subtitle', '')
    method = result['method']
    estimand = result['estimand']
    prim = result.get('primary')

    # ── Estimand (always the first sheet) ────────────────────────────────────
    ws = wb.active
    ws.title = 'Estimand'
    r = sheet_header(ws, 'Estimand — what this analysis estimates', subtitle,
                     ['Estimand'], [130])
    r = write_para(ws, r, 1,
                   f"Weighting method: {method.upper()}"
                   f"{' (stabilized weights)' if result['stabilized'] else ''}"
                   f"   ->   ESTIMAND = {estimand}", bold=True)
    r = write_para(ws, r, 1, ESTIMAND_TEXT['ato' if estimand == 'ATO' else 'ate'])
    r += 1
    r = write_para(ws, r, 1, "The three estimands are different clinical questions", bold=True)
    for key in ('ate', 'att', 'ato'):
        r = write_para(ws, r, 1, "    " + ESTIMAND_TEXT[key])
    r = write_para(ws, r, 1,
                   "They are not interchangeable and they can legitimately differ in size and "
                   "even in direction when treatment effect varies across patients. Which one "
                   "is being estimated is a protocol decision made before the analysis; "
                   "selecting an estimand after seeing which produced the smaller p-value is "
                   "data dredging and must not be done.")
    r += 1
    r = write_para(ws, r, 1, "Sample", bold=True)
    rows = [
        ('Treated arm', f"{result['label_t']} (n = {result['n_treated']})"),
        ('Control arm', f"{result['label_c']} (n = {result['n_control']})"),
        ('Rows analysed', f"{result['n_analyzed']} of {result['n_total']} "
                          f"({result['n_dropped']} dropped listwise)"),
        ('Propensity score covariates', str(len(result['terms']))),
    ]
    if prim:
        rows += [('Effective sample size after weighting',
                  f"{prim['ess']:.1f} ({100.0 * prim['ess_fraction']:.1f}% of {prim['n']})"),
                 ('Primary analysis set', prim['label'])]
    for k, v in rows:
        r = write_para(ws, r, 1, f"    {k}: {v}")
    r += 1
    r = write_footnote(ws, r, 1,
                       "Wording convention: a confidence interval that includes the null means "
                       "no statistically significant difference was detected in this analysis. "
                       "It does not mean the two groups are equivalent — showing equivalence "
                       "requires a pre-specified non-inferiority or equivalence margin.")

    if not prim:
        _finish(wb, config)
        return config['output_file']

    # ── PS_distribution ──────────────────────────────────────────────────────
    ws = wb.create_sheet('PS_distribution')
    headers = ['Group', 'n', 'Mean', 'SD', 'Min', 'P1', 'P5', 'Q1', 'Median', 'Q3',
               'P95', 'P99', 'Max', 'PS < 0.01', 'PS > 0.99']
    r = sheet_header(ws, 'Propensity score distribution by group', subtitle, headers,
                     [22, 8, 9, 9, 9, 9, 9, 9, 10, 9, 9, 9, 9, 12, 12])
    for i, s in enumerate(result['ps_stats']):
        r = write_row(ws, r, [s['label'], s['n'], fmt_num(s['mean']), fmt_num(s['sd']),
                              fmt_num(s['min']), fmt_num(s['p1']), fmt_num(s['p5']),
                              fmt_num(s['q1']), fmt_num(s['median']), fmt_num(s['q3']),
                              fmt_num(s['p95']), fmt_num(s['p99']), fmt_num(s['max']),
                              s['n_lt_001'], s['n_gt_099']],
                      alt=(i % 2 == 1), bold_cols=(1,))
    r += 1
    pos = result['positivity']
    r = write_row(ws, r, ['Positivity diagnostics', '', '', '', '', '', '', '', '', '',
                          '', '', '', '', ''], bold_cols=(1,))
    diag = [
        ('Region of common support',
         f"[{pos['common_support_lo']:.4f}, {pos['common_support_hi']:.4f}]"),
        ('Subjects outside common support',
         f"{pos['n_outside_common_support']} ({100.0 * pos['frac_outside']:.1f}%)"),
        ('Overlap coefficient', f"{pos['overlap_coefficient']:.3f}"),
        ('Blocking rule', 'empty common support (the two ranges do not intersect)'),
        ('Warning thresholds (screening, not validity cut-offs)',
         f"overlap coefficient < {config['overlap_coefficient_threshold']:.2f}, or "
         f"> {100.0 * config['nonoverlap_fraction_threshold']:.0f}% outside common support"),
    ]
    for i, (k, v) in enumerate(diag):
        r = write_row(ws, r, [k, v] + [''] * 13, alt=(i % 2 == 1))
    r += 1
    r = write_row(ws, r, ['Propensity score model (unregularized logistic regression)']
                  + [''] * 14, bold_cols=(1,))
    r = write_row(ws, r, ['Term', 'beta', 'SE'] + [''] * 12, bold_cols=(1, 2, 3))
    for i, c in enumerate(result['ps_model']):
        r = write_row(ws, r, [c['term'], fmt_num(c['beta'], 4), fmt_num(c['se'], 4)] + [''] * 12,
                      alt=(i % 2 == 1))
    r += 1
    r = write_footnote(ws, r, len(headers),
                       "The overlap coefficient is the integrated minimum of the two groups' "
                       "propensity score densities: 1 means the distributions are identical, 0 "
                       "means no patient in one group has a counterpart in the other. It is the "
                       "first-hand evidence for positivity, and when it is near zero no amount "
                       "of weighting produces a valid comparison — the two groups are simply "
                       "not comparable populations. Patients with a propensity score below 0.01 "
                       "or above 0.99 are the ones who generate extreme weights.")

    # ── Weights ──────────────────────────────────────────────────────────────
    ws = wb.create_sheet('Weights')
    headers = ['Statistic', result['label_t'], result['label_c'], 'Overall', 'Note']
    r = sheet_header(ws, 'Weight distribution and effective sample size', subtitle, headers,
                     [34, 18, 18, 18, 56])
    wt, wc = prim['weight_treated'], prim['weight_control']
    ext = config['extreme_weight_threshold']
    wrows = [
        ('n', wt['n'], wc['n'], prim['n'], 'Subjects contributing to the weighted analysis.'),
        ('Mean weight', fmt_num(wt['mean']), fmt_num(wc['mean']), fmt_num(prim['mean_weight']),
         'Stabilized IPTW weights average about 1; unstabilized ones do not.'),
        ('SD of weight', fmt_num(wt['sd']), fmt_num(wc['sd']), fmt_num(prim['sd_weight']),
         'Large spread is the warning sign, not the mean.'),
        ('Minimum weight', fmt_num(wt['min']), fmt_num(wc['min']), fmt_num(prim['min_weight']), ''),
        ('Maximum weight', fmt_num(wt['max']), fmt_num(wc['max']), fmt_num(prim['max_weight']),
         'The single most important number on this sheet.'),
        ('99th percentile of weight', '', '', fmt_num(prim['p99_weight']), ''),
        (f'Subjects with weight > {ext:g}', '', '', prim['n_weight_gt_threshold'],
         'Each of these patients is standing in for more than ten others.'),
        ('Largest weight as share of total', '', '',
         f"{100.0 * prim['max_weight_share']:.2f}%",
         f"Flagged above {100.0 * config['max_weight_share_threshold']:.0f}%: a single case "
         f"dominating the estimate is the most common way weighting fails."),
        ('Effective sample size (ESS)', fmt_num(wt['ess'], 1), fmt_num(wc['ess'], 1),
         fmt_num(prim['ess'], 1),
         'ESS = (sum of weights)^2 / sum of squared weights.'),
        ('ESS as % of n', '', '', f"{100.0 * prim['ess_fraction']:.1f}%",
         f"Flagged below {100.0 * config['ess_fraction_threshold']:.0f}% — a screening "
         f"threshold for attention, not a validity cutoff: there is no ESS fraction below "
         f"which the estimate becomes invalid. Report the absolute ESS and this percentage "
         f"together. Confidence intervals reflect the ESS, not the raw N; reporting N "
         f"without ESS overstates precision."),
    ]
    for i, row in enumerate(wrows):
        flag = (row[0].startswith('Largest weight')
                and prim['max_weight_share'] > config['max_weight_share_threshold']) or \
               (row[0] == 'ESS as % of n'
                and prim['ess_fraction'] < config['ess_fraction_threshold']) or \
               (row[0].startswith('Subjects with weight') and prim['n_weight_gt_threshold'] > 0)
        r = write_row(ws, r, list(row), alt=(i % 2 == 1), flag=flag, bold_cols=(1,))
    r += 1
    r = write_footnote(ws, r, len(headers),
                       "Overlap weights are bounded between 0 and 1 by construction, so the "
                       "extreme-weight problem cannot arise with method = \"overlap\"; that is "
                       "the main practical reason to prefer it when positivity is marginal. "
                       "For IPTW, an ESS far below N is not a bug — it is the honest cost of "
                       "reweighting a population that does not resemble the target one, and it "
                       "must be reported alongside N.")

    # ── Balance ──────────────────────────────────────────────────────────────
    ws = wb.create_sheet('Balance')
    headers = ['Variable', f"{result['label_t']} (unweighted)", f"{result['label_c']} (unweighted)",
               'SMD before', f"{result['label_t']} (weighted)", f"{result['label_c']} (weighted)",
               'SMD after', 'Balanced?']
    r = sheet_header(ws, 'Covariate balance before and after weighting — every variable',
                     subtitle, headers, [30, 22, 22, 12, 22, 22, 12, 12])
    thr = config['smd_threshold']
    cur_section = None
    i = 0
    for b in prim['balance']:
        if b['section'] and b['section'] != cur_section:
            cur_section = b['section']
            r = write_row(ws, r, [cur_section] + [''] * 7, bold_cols=(1,))
        bad = np.isfinite(b['smd_after']) and b['smd_after'] > thr
        r = write_row(ws, r, [b['label'], b['before_t'], b['before_c'],
                              fmt_num(b['smd_before']), b['after_t'], b['after_c'],
                              fmt_num(b['smd_after']),
                              'no' if bad else 'yes'],
                      alt=(i % 2 == 1), flag=bad, sig_cols=(7,) if bad else ())
        i += 1
    r += 1
    finite_after = [b['smd_after'] for b in prim['balance'] if np.isfinite(b['smd_after'])]
    finite_before = [b['smd_before'] for b in prim['balance'] if np.isfinite(b['smd_before'])]
    r = write_row(ws, r, ['Maximum SMD', '', '', fmt_num(max(finite_before) if finite_before else np.nan),
                          '', '', fmt_num(max(finite_after) if finite_after else np.nan), ''],
                  bold_cols=(1,))
    r = write_row(ws, r, ['Variables with SMD > %.2f' % thr, '', '',
                          sum(1 for v in finite_before if v > thr), '', '',
                          sum(1 for v in finite_after if v > thr), ''], bold_cols=(1,))
    r += 1
    r = write_footnote(ws, r, len(headers),
                       "SMD is reported for every variable individually and never as an average "
                       "— an average hides the one covariate that stayed imbalanced, which is "
                       "exactly the one a reviewer will find. Weighted SMDs use weighted means "
                       "and weighted variances (Austin & Stuart 2015). Balance is judged at "
                       "SMD < 0.1 by convention; it is a diagnostic of the propensity score "
                       "MODEL, not a hypothesis test, so p-values for baseline differences are "
                       "deliberately not reported. Overlap weights balance the covariates in "
                       "the propensity score model exactly, by construction, so SMDs at or near "
                       "zero there are expected and are not evidence that the model is right.")

    # ── Outcome_model ────────────────────────────────────────────────────────
    ws = wb.create_sheet('Outcome_model')
    headers = ['Analysis', 'Estimand', 'Effect (95% CI)', 'p', 'SE type', 'Note']
    r = sheet_header(ws, 'Weighted outcome model', subtitle, headers, [30, 12, 30, 12, 24, 46])
    crude = result.get('crude')
    i = 0
    if crude:
        r = write_row(ws, r, [
            'Crude (unweighted)', 'none — confounded',
            f"{crude['scale']}: " + fmt_effect(crude['estimate'], crude['ci_lo'], crude['ci_hi']),
            fmt_p(crude['p']), 'model-based',
            'Shown for side-by-side comparison only. Any difference between this row and the '
            'weighted row is the measured contribution of the covariates in the propensity '
            'score model.'], alt=(i % 2 == 1))
        i += 1
    po = prim.get('outcome')
    if po:
        r = write_row(ws, r, [
            f"Weighted ({method.upper()}, {prim['label']})", result['estimand'],
            f"{po['scale']}: " + fmt_effect(po['estimate'], po['ci_lo'], po['ci_hi']),
            fmt_p(po['p']), po['se_type'],
            'Robust (sandwich) standard errors are mandatory: weighting makes the observations '
            'non-independent, and model-based standard errors would be too narrow.'],
            alt=(i % 2 == 1), bold_cols=(1,))
        i += 1
    if result.get('primary_is_trimmed') and result.get('untrimmed', {}).get('outcome'):
        uo = result['untrimmed']['outcome']
        r = write_row(ws, r, [
            f"Weighted ({method.upper()}, untrimmed)", result['estimand'],
            f"{uo['scale']}: " + fmt_effect(uo['estimate'], uo['ci_lo'], uo['ci_hi']),
            fmt_p(uo['p']), uo['se_type'],
            'Same model without trimming; see the Trimming sheet for how much the trimming '
            'moved the estimate.'], alt=(i % 2 == 1))
        i += 1
    ato = result.get('ato_companion')
    if ato and ato.get('outcome'):
        ao = ato['outcome']
        r = write_row(ws, r, [
            'Weighted (overlap weights, ATO companion)', 'ATO',
            f"{ao['scale']}: " + fmt_effect(ao['estimate'], ao['ci_lo'], ao['ci_hi']),
            fmt_p(ao['p']), ao['se_type'],
            'Added automatically because positivity is marginal '
            f"({'; '.join(result['positivity'].get('marginal_reasons') or [])}). Same "
            'propensity model, overlap weights instead of inverse-probability weights, so '
            'it targets the population with genuine clinical equipoise rather than '
            'extrapolating into regions where one arm barely exists. **Report this row and '
            f"the {result['estimand']} row together** — they answer different questions, "
            'and presenting either alone under marginal overlap is selective reporting.'],
            alt=(i % 2 == 1), bold_cols=(1,))
        i += 1
    add = prim.get('additive')
    if add:
        r += 1
        r = write_row(ws, r, ['Additive-scale contrast', '', '', '', '', ''], bold_cols=(1,))
        ca = result.get('crude_additive')
        if ca:
            r = write_row(ws, r, [f"Crude {ca['label'].lower()}", 'none — confounded',
                                  fmt_num(ca['difference'], 4), '', '',
                                  f"{result['label_t']}: {fmt_num(ca['treated'], 4)}   "
                                  f"{result['label_c']}: {fmt_num(ca['control'], 4)}"])
        r = write_row(ws, r, [add['label'], result['estimand'], fmt_num(add['difference'], 4),
                              '', '',
                              f"{result['label_t']}: {fmt_num(add['treated'], 4)}   "
                              f"{result['label_c']}: {fmt_num(add['control'], 4)}"],
                      alt=True, bold_cols=(1,))
    r += 1
    r = write_footnote(ws, r, len(headers),
                       "The weighted model contains the treatment indicator only: covariate "
                       "adjustment is done by the weights, not by the outcome model. The "
                       "estimand named in the second column is the one defined on the Estimand "
                       "sheet — it is a property of the weighting scheme, not of the outcome "
                       "model, and it does not change because the outcome is binary rather than "
                       "time-to-event. Where a confidence interval includes the null, the "
                       "correct wording is that no statistically significant difference was "
                       "detected, not that the treatments are equivalent.")

    # ── Trimming (only when trimming was applied) ────────────────────────────
    if result['trim'].get('enabled'):
        t = result['trim']
        ws = wb.create_sheet('Trimming')
        headers = ['Item', 'Value', 'Note']
        r = sheet_header(ws, 'Propensity score trimming', subtitle, headers, [40, 30, 66])
        trows = [
            ('Trimming rule', f"keep propensity scores between the "
                              f"{t['percentile'][0]:g}th and {t['percentile'][1]:g}th percentile "
                              f"of the pooled distribution",
             'Set in config.trim. The percentiles are a methodological choice and belong in '
             'decision_log.md.'),
            ('Lower / upper threshold',
             f"{t['threshold_lo']:.4f} / {t['threshold_hi']:.4f}",
             'Absolute propensity score cut-points implied by those percentiles.'),
            ('Subjects trimmed',
             f"{t['n_trimmed']} ({t['n_trimmed_treated']} {result['label_t']}, "
             f"{t['n_trimmed_control']} {result['label_c']})",
             'These patients are excluded from the primary weighted analysis. They are not a '
             'random subset — they are the ones whose treatment was most predictable — so '
             'trimming changes the population the estimate refers to.'),
            ('Subjects remaining', str(t['n_remaining']), ''),
        ]
        for i, row in enumerate(trows):
            r = write_row(ws, r, list(row), alt=(i % 2 == 1), bold_cols=(1,))
        r += 1
        r = write_row(ws, r, ['Effect of trimming on the result', '', ''], bold_cols=(1,))
        r = write_row(ws, r, ['Analysis set', 'Effect (95% CI)', 'ESS (% of n)'],
                      bold_cols=(1, 2, 3))
        for key, tag in (('untrimmed', 'Untrimmed'), ('primary', 'Trimmed (primary)')):
            blk = result.get(key)
            if not blk or not blk.get('outcome'):
                continue
            o = blk['outcome']
            r = write_row(ws, r, [tag,
                                  f"{o['scale']}: " + fmt_effect(o['estimate'], o['ci_lo'], o['ci_hi']),
                                  f"{blk['ess']:.1f} ({100.0 * blk['ess_fraction']:.1f}%)"],
                          alt=(key == 'primary'))
        u, p_ = result.get('untrimmed'), result.get('primary')
        if u and p_ and u.get('outcome') and p_.get('outcome'):
            d_abs = p_['outcome']['estimate'] - u['outcome']['estimate']
            denom = abs(u['outcome']['estimate'])
            d_rel = 100.0 * d_abs / denom if denom > 0 else np.nan
            r = write_row(ws, r, ['Change in the point estimate',
                                  f"{d_abs:+.4f} ({d_rel:+.1f}%)", ''], bold_cols=(1,))
        r += 1
        r = write_footnote(ws, r, len(headers),
                           "Trimming is a trade-off, not a fix: it removes the patients "
                           "generating extreme weights and therefore stabilises the estimate, "
                           "but it also redefines the population the estimate applies to, and "
                           "that redefinition is data-driven. Report the trimmed and untrimmed "
                           "results together, as above. A large difference between them is a "
                           "finding about how much the result depends on a few unusual "
                           "patients; it is not a reason to report only the more convenient of "
                           "the two.")

    # ── Method ───────────────────────────────────────────────────────────────
    ws = wb.create_sheet('Method')
    headers = ['Setting', 'Value', 'Source', 'Why it matters']
    r = sheet_header(ws, 'Methodological choices and defaults', subtitle, headers,
                     [34, 30, 16, 64])
    prov = config['_provenance']
    at = result['analysis_type']
    meta = [
        ('Weighting method', method, prov.get('method', 'default'),
         'iptw -> ATE; overlap -> ATO. Determines the estimand and therefore the clinical '
         'question being answered.'),
        ('Stabilized weights',
         str(result['stabilized']) + ('' if method == 'iptw' else ' (not applicable to overlap weights)'),
         prov.get('stabilized', 'default'),
         'Unstabilized IPTW weights have extreme variance and inflate confidence intervals. '
         'Overlap weights are bounded by construction and need no stabilization.'),
        ('Propensity score model', 'unregularized logistic regression, main effects only',
         'fixed', 'The PS model exists to balance covariates. If any covariate remains '
                  'imbalanced (see Balance), respecify it with interactions or splines rather '
                  'than accepting the imbalance.'),
        ('Trimming',
         (f"enabled, percentiles {config['trim']['percentile']}" if config['trim']['enabled']
          else f"disabled (default percentiles would be {TRIM_DEFAULT['percentile']})"),
         prov.get('trim', 'default'),
         'Off by default so that no patient is removed without an explicit decision.'),
        ('Outcome model',
         {'cox': 'weighted Cox proportional hazards, treatment only',
          'logistic': 'weighted logistic regression, treatment only',
          'linear': 'weighted linear regression, treatment only'}[at],
         'config', 'Adjustment is carried by the weights, not by covariates in the outcome '
                   'model.'),
        ('Standard errors', 'robust / sandwich', 'fixed',
         'Mandatory after weighting: weights break the independence assumption and '
         'model-based standard errors are anticonservative.'),
        ('Balance threshold', f"SMD < {config['smd_threshold']}",
         prov.get('smd_threshold', 'default'),
         'Conventional cut-off, applied per variable rather than on average.'),
        ('Extreme weight threshold', f"weight > {config['extreme_weight_threshold']:g}",
         prov.get('extreme_weight_threshold', 'default'), 'Triggers a QC warning.'),
        ('Single-case dominance threshold',
         f"largest weight > {100.0 * config['max_weight_share_threshold']:.0f}% of total weight",
         prov.get('max_weight_share_threshold', 'default'), 'Triggers a QC warning.'),
        ('ESS threshold', f"ESS < {100.0 * config['ess_fraction_threshold']:.0f}% of n",
         prov.get('ess_fraction_threshold', 'default'),
         'Triggers a QC warning. A screening threshold, not a validity cutoff — report the '
         'absolute ESS alongside the fraction and let the reader judge the precision.'),
        ('Positivity blocking rule', 'empty common support (no overlap at all)', 'fixed',
         'The only structural positivity failure: with no shared propensity score range '
         'there is nothing to weight towards and the run is stopped rather than producing '
         'a number.'),
        ('Positivity warning thresholds',
         f"overlap coefficient < {config['overlap_coefficient_threshold']:.2f}, or > "
         f"{100.0 * config['nonoverlap_fraction_threshold']:.0f}% outside common support",
         prov.get('overlap_coefficient_threshold', 'default'),
         'Screening thresholds, not validity cut-offs — neither has a consensus value in '
         'the literature, so neither blocks. Breaching one adds the ATO companion row '
         'above instead: getting these numbers wrong then costs one extra analysis, not a '
         'stopped study, and no marginal-overlap estimate is ever reported on its own. '
         'Computed before trimming; trimming does not clear them.'),
        ('Missing data', 'listwise deletion on PS covariates and outcome', 'fixed',
         f"{result['n_dropped']} row(s) dropped. Run the multiple-imputation step first if "
         f"this is more than a few percent."),
        ('Random seed', str(config['seed']), prov.get('seed', 'default'),
         'Kept for reproducibility; the current weighting path is deterministic.'),
    ]
    for i, (k, v, src, why) in enumerate(meta):
        r = write_row(ws, r, [k, v, src, why], alt=(i % 2 == 1))
    r += 1
    if _QC_MESSAGES:
        r = write_row(ws, r, ['QC messages raised by this run', '', '', ''], bold_cols=(1,))
        for i, m in enumerate(_QC_MESSAGES):
            r = write_row(ws, r, ['', m, '', ''], alt=(i % 2 == 1),
                          flag=m.startswith('[QC_BLOCKING]'))
    r += 1
    r = write_footnote(ws, r, len(headers),
                       "Every row above is a methodological choice that belongs in "
                       "decision_log.md with a permanent ID. \"default\" in the Source column "
                       "means this script chose it, not the analyst.")

    _finish(wb, config)
    return config['output_file']


def _finish(wb, config):
    out = config['output_file']
    os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
    wb.save(out)
    print(f"  Excel written: {out}")


# ═══════════════════════════════════════════════════════════════════════════════
# Plots
# ═══════════════════════════════════════════════════════════════════════════════

def write_ps_plot(config, result):
    prim = result.get('primary')
    if not prim:
        return None
    ps = prim['ps']
    A = prim['A']
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))

    ax = axes[0]
    bins = np.linspace(0, 1, 41)
    ax.hist(ps[A == 1], bins=bins, alpha=0.55, color='#C00000',
            label=f"{result['label_t']} (n={int((A==1).sum())})", density=True)
    ax.hist(ps[A == 0], bins=bins, alpha=0.55, color='#2E5FA3',
            label=f"{result['label_c']} (n={int((A==0).sum())})", density=True)
    pos = result['positivity']
    ax.axvline(pos['common_support_lo'], color='#555555', linestyle=':', linewidth=1)
    ax.axvline(pos['common_support_hi'], color='#555555', linestyle=':', linewidth=1)
    if result['trim'].get('enabled'):
        ax.axvline(result['trim']['threshold_lo'], color='#1E8449', linestyle='--', linewidth=1.2)
        ax.axvline(result['trim']['threshold_hi'], color='#1E8449', linestyle='--', linewidth=1.2,
                   label='Trimming thresholds')
    ax.set_xlabel('Propensity score')
    ax.set_ylabel('Density')
    ax.set_title(f"Propensity score overlap\noverlap coefficient = "
                 f"{pos['overlap_coefficient']:.3f}", fontsize=10, fontweight='bold')
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.2, linewidth=0.5)

    ax = axes[1]
    w = prim['w']
    ax.hist(w[A == 1], bins=30, alpha=0.55, color='#C00000', label=result['label_t'])
    ax.hist(w[A == 0], bins=30, alpha=0.55, color='#2E5FA3', label=result['label_c'])
    ax.axvline(config['extreme_weight_threshold'], color='#555555', linestyle='--',
               linewidth=1, label=f"weight = {config['extreme_weight_threshold']:g}")
    ax.set_xlabel('Weight')
    ax.set_ylabel('Number of subjects')
    ax.set_title(f"Weight distribution\nESS = {prim['ess']:.1f} "
                 f"({100.0 * prim['ess_fraction']:.1f}% of {prim['n']})",
                 fontsize=10, fontweight='bold')
    ax.legend(fontsize=8, frameon=False)
    ax.grid(alpha=0.2, linewidth=0.5)

    fig.suptitle(f"{config.get('title','')} — {result['method'].upper()} "
                 f"(estimand: {result['estimand']})", fontsize=12, fontweight='bold')
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    out = config['plot_file']
    os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
    fig.savefig(out, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"  Plot written: {out}")
    return out


def write_love_plot(config, result):
    prim = result.get('primary')
    if not prim:
        return None
    bal = prim['balance']
    labels = [b['label'] for b in bal]
    before = [b['smd_before'] if np.isfinite(b['smd_before']) else 0.0 for b in bal]
    after = [b['smd_after'] if np.isfinite(b['smd_after']) else 0.0 for b in bal]
    order = np.argsort(before)
    labels = [labels[i] for i in order]
    before = [before[i] for i in order]
    after = [after[i] for i in order]
    y = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(8.4, max(3.2, 0.34 * len(labels) + 2.0)))
    for i in range(len(labels)):
        ax.plot([before[i], after[i]], [y[i], y[i]], color='#BBBBBB', linewidth=1, zorder=1)
    ax.scatter(before, y, color='#C00000', marker='o', s=55, label='Before weighting', zorder=3)
    ax.scatter(after, y, color='#2E5FA3', marker='s', s=55, label='After weighting', zorder=3)
    thr = config['smd_threshold']
    ax.axvline(thr, color='#555555', linestyle='--', linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel('Absolute standardized mean difference')
    ax.set_xlim(left=0, right=max(max(before + after), thr * 1.5) * 1.15 + 0.02)
    ax.set_title(f"Covariate balance — {result['method'].upper()} "
                 f"(estimand: {result['estimand']})\ndashed line = SMD {thr}",
                 fontsize=11, fontweight='bold')
    ax.legend(fontsize=9, frameon=False, loc='lower right')
    ax.grid(axis='x', alpha=0.25, linewidth=0.5)
    fig.tight_layout()
    out = config['love_plot_file']
    os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
    fig.savefig(out, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"  Love plot written: {out}")
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# --check-missing preview (never fits anything)
# ═══════════════════════════════════════════════════════════════════════════════

def preview(config, df):
    at = config['analysis_type']
    print("=" * 96)
    print("WEIGHTING PREVIEW (--check-missing)")
    print("=" * 96)
    print(f"Data file : {config['data_file']}")
    print(f"Rows after filters/derived variables : {len(df)}")
    print(f"method : {config['method']}   stabilized : {config['stabilized']}   "
          f"analysis_type : {at}")
    print(f"Target estimand : {'ATO' if config['method'] == 'overlap' else 'ATE'}")
    print("-" * 96)

    g = config['grouping']
    rows = [('[treatment]', g['column'], 'binary')]
    for v in ps_variables(config):
        rows.append((v['label'], v['column'], v['type']))
    if at == 'cox':
        cs = config['cox_settings']
        rows.append(('[outcome] time', cs['time_column'], 'continuous'))
        rows.append(('[outcome] event', cs['event_column'], 'binary'))
    elif at == 'logistic':
        rows.append(('[outcome]', config['logistic_settings']['outcome_column'], 'binary'))
    else:
        rows.append(('[outcome]', config['linear_settings']['outcome_column'], 'continuous'))

    print(f"{'Variable':<30} {'Column':<24} {'Type':<14} {'Missing':>16}")
    print("-" * 96)
    present = []
    for label, col, vtype in rows:
        if col not in df.columns:
            print(f"{label:<30} {col:<24} {vtype:<14} {'COLUMN NOT FOUND':>16}")
            continue
        s = (df[col] if vtype == 'categorical' else pd.to_numeric(df[col], errors='coerce'))
        nm = int(s.isna().sum())
        pct = 100.0 * nm / len(df) if len(df) else 0.0
        present.append(col)
        print(f"{label:<30} {col:<24} {vtype:<14} {nm:>5}/{len(df):<5} ({pct:>4.1f}%)")

    if present:
        sub = df[present].apply(lambda c: pd.to_numeric(c, errors='coerce')
                                if c.dtype != object else c)
        n_complete = int(sub.notna().all(axis=1).sum())
        print("-" * 96)
        print(f"Complete cases across all model variables : {n_complete}/{len(df)} "
              f"({100.0 * n_complete / len(df):.1f}%)")

    if g['column'] in df.columns:
        gv = pd.to_numeric(df[g['column']], errors='coerce')
        for grp in g['groups']:
            print(f"  {grp.get('label', grp['value'])}: n = {int((gv == grp['value']).sum())}")

    print("-" * 96)
    tr = config['trim']
    print(f"Trimming : {'enabled, percentiles ' + str(tr['percentile']) if tr['enabled'] else 'disabled'} "
          f"({config['_provenance'].get('trim', 'default')})")
    print(f"Balance threshold : SMD < {config['smd_threshold']}")
    print(f"ESS warning threshold : < {100.0 * config['ess_fraction_threshold']:.0f}% of n")
    print(f"Positivity blocking : empty common support only")
    print(f"Positivity warning  : overlap coefficient < "
          f"{config['overlap_coefficient_threshold']:.2f} or > "
          f"{100.0 * config['nonoverlap_fraction_threshold']:.0f}% outside common support "
          f"(screening thresholds, no consensus cut-point)")
    print("=" * 96)
    print("[preview] No propensity score model was fitted (--check-missing). "
          "No Excel or PNG was written.")
    print("=" * 96)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python weighting.py config.json [--check-missing]")
        sys.exit(1)

    config = load_config(sys.argv[1])
    check_only = '--check-missing' in sys.argv

    df = load_data(config)
    print(f"Mode: weighting ({config['method']}, {config['analysis_type']})")
    print(f"Data loaded: n={len(df)}")

    if check_only:
        preview(config, df)
        sys.exit(0)

    result = run_analysis(config, df)

    write_excel(config, result)
    if n_blocking() == 0:
        write_ps_plot(config, result)
        write_love_plot(config, result)
    else:
        print("  Plots skipped: a blocking QC condition was raised")

    print("\nDone!")
    nb = n_blocking()
    nw = len(_QC_MESSAGES) - nb
    if _QC_MESSAGES:
        print(f"  QC: {nb} blocking, {nw} warning(s) written to stderr")
    sys.exit(3 if nb else 0)


if __name__ == '__main__':
    main()
