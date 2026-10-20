#!/usr/bin/env python3
"""
Restricted mean survival time — the executable half of `ph_violation_remedy = "rmst"`
(research-plan pipeline; 2026-08-12 adjudication dispute 5, remedy generators)

Why this exists
---------------
When proportional hazards fails, a single hazard ratio is an average of a ratio
that was changing — it answers a question nobody asked. RMST answers a different
one that survives the failure: *how much event-free time, on average, does each
arm accumulate over the first tau of follow-up?* No proportionality is assumed
anywhere in that quantity, which is why it is a remedy rather than a workaround.

Like the other remedies this is its own step and its own table. It does not touch
the multivariate workbook — see ph_stratified.py's header for why that separation
is deliberate rather than lazy.

THE ONLY THING THAT HAS TO BE DEFENDED HERE IS tau
--------------------------------------------------
RMST is a summary over [0, tau], and the answer moves with tau. Choosing tau
after seeing which value makes the comparison look best is the whole
p-hacking surface of this method — everything else about RMST is robust.

So tau must come from the plan, and from `outcomes[]` specifically, which is
what puts it inside `reviewer_challenge.plan_fingerprint()`. Two accepted forms,
and the sidecar records which one was used:

  * `outcomes[<id>].rmst_tau` — a number, fixed in advance.
  * `outcomes[<id>].rmst_tau_rule` — a NAMED rule evaluated against the data
    (currently `min_of_arm_max_followup`, the conventional choice). A rule is
    still a pre-specification: it is decided before the data are seen and it has
    exactly one value once they are.

Neither declared is not fatal here — the analysis still runs, so the author can
see the numbers and the exact fix — but the sidecar records
`tau_source: "default_rule"` and the manuscript gate blocks on it. A tau that was
never written into the plan is indistinguishable from one chosen after the fact,
and that is the single claim this remedy has to make.

WHAT THIS DOES NOT DO: adjust for covariates
--------------------------------------------
The RMST difference computed here is UNADJUSTED — Kaplan-Meier per arm, then the
difference of the two restricted means. The model it is a remedy for was
adjusted, so this is a genuine change of estimand, not just of scale, and it is
labelled that way everywhere it appears: in the workbook footnote, in the
sidecar (`adjusted: false`), and as a QC warning on every run.

An adjusted RMST needs either IPTW weights or pseudo-observation regression.
Neither is implemented here, and implementing one hastily underneath a published
estimate is worse than saying plainly that this one is unadjusted. If confounding
is doing real work in your model, `stratify` or `time_varying` keep the
adjustment; this remedy trades it for freedom from proportionality.

Usage:
    python ph_rmst.py config.json                  # full run
    python ph_rmst.py config.json --check-missing  # preview only, no models

Config (mode = "ph_rmst"):
    {"mode":"ph_rmst","remedy":"rmst","outcome_id":"primary",
     "data_file":"...","filters":[],"derived_variables":[],
     "grouping":{"column":"AF","groups":[{"value":0,"label":"No AF"},
                                          {"value":1,"label":"AF"}]},
     "analysis_type":"cox",
     "cox_settings":{"time_column":"t","event_column":"e"},
     "tau":null, "tau_rule":"min_of_arm_max_followup", "tau_source":"default_rule",
     "ph_test_file":".../Multi_primary_ph_test.json",
     "source_table":".../Multi_primary.xlsx",
     "title":"...","subtitle":"...","abbreviations":"...",
     "output_file":".../RMST_primary.xlsx",
     "evidence_file":".../RMST_primary_remedy.json"}
"""

import hashlib
import json
import operator
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from lifelines import KaplanMeierFitter
from lifelines.utils import restricted_mean_survival_time

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

EVIDENCE_SCHEMA = "ph_remedy_evidence/1"
REMEDY = "rmst"

# Named tau rules. A rule name is a pre-specification; a bare number computed at
# run time is not. Kept as a registry with one entry rather than inlined, so
# adding a second rule cannot mean adding a second place that evaluates them.
TAU_RULES = {}


def _rule(name):
    def deco(fn):
        TAU_RULES[name] = fn
        return fn
    return deco


@_rule("min_of_arm_max_followup")
def _min_of_arm_max_followup(d, time_col, event_col, group_col):
    """The conventional choice: min over arms of the largest observed time.

    Beyond this point one arm has nobody left, so the survival curve there is an
    extrapolation and the integral would be comparing a real curve against a flat
    line. Taking the minimum keeps both arms inside their own data.
    """
    per_arm = d.groupby(group_col)[time_col].max()
    if per_arm.empty:
        return None, "no arms in the analysis rows"
    return float(per_arm.min()), None


_QC_MESSAGES = []


def qc(kind, message):
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

def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    config.setdefault('mode', 'ph_rmst')
    config.setdefault('remedy', REMEDY)
    config.setdefault('filters', [])
    config.setdefault('derived_variables', [])
    config.setdefault('sections', [])
    config.setdefault('title', '')
    config.setdefault('subtitle', '')
    config.setdefault('abbreviations', '')
    config.setdefault('analysis_type', 'cox')
    config.setdefault('cox_settings', None)
    config.setdefault('tau', None)
    config.setdefault('tau_rule', None)
    config.setdefault('tau_source', 'default_rule')
    config.setdefault('ph_test_file', None)
    config.setdefault('source_table', None)

    if config['mode'] != 'ph_rmst':
        sys.exit(f"[FATAL] Unknown mode: {config['mode']!r} (expected 'ph_rmst')")
    if config['remedy'] != REMEDY:
        sys.exit(f"[FATAL] This script implements ph_violation_remedy = {REMEDY!r}, "
                 f"but the config says {config['remedy']!r}.")
    if config['analysis_type'] != 'cox':
        sys.exit(f"[FATAL] analysis_type={config['analysis_type']!r}: restricted mean "
                 f"SURVIVAL time needs a survival outcome. A logistic step has no "
                 f"proportional-hazards assumption and needs no remedy.")
    if config['tau_rule'] and config['tau_rule'] not in TAU_RULES:
        sys.exit(f"[FATAL] Unknown tau_rule {config['tau_rule']!r} "
                 f"(known rules: {sorted(TAU_RULES)}). Refused rather than replaced "
                 f"with a default: a misspelled rule name that silently became "
                 f"something else would read as a pre-specification that was honoured.")
    if not config.get('output_file'):
        sys.exit("[FATAL] config has no output_file; the gate matches the evidence "
                 "sidecar to the workbook by name, so the workbook must be named.")
    config.setdefault('evidence_file',
                      f"{os.path.splitext(config['output_file'])[0]}_remedy.json")
    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Data loading (identical semantics to ph_stratified.py / robust_variance.py)
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


def read_ph_test(config):
    path = config.get('ph_test_file')
    if not path:
        return None, None, "config has no ph_test_file"
    if not os.path.exists(path):
        return None, path, f"not found: {path}"
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f), path, None
    except Exception as exc:
        return None, path, f"{type(exc).__name__}: {exc}"


def analysis_frame(df, config):
    """(frame, error). Complete cases on the three columns RMST actually uses."""
    cs = config['cox_settings'] or {}
    time_col, event_col = cs.get('time_column'), cs.get('event_column')
    group_col = (config.get('grouping') or {}).get('column')
    needed = [c for c in (time_col, event_col, group_col) if c]
    if len(needed) < 3:
        return None, ("config must name a time column, an event column and a "
                      "grouping column")
    missing = [c for c in needed if c not in df.columns]
    if missing:
        return None, f"columns not in the data: {missing}"
    d = df[needed].copy()
    for c in (time_col, event_col):
        d[c] = pd.to_numeric(d[c], errors='coerce')
    # tau is stated in `time_unit`, so the time column has to be in `time_unit`
    # too. Same divide as kaplan_meier.py:213 — this step reports time-valued
    # numbers (tau, RMST, follow-up), so unlike a Cox model, whose partial
    # likelihood only uses the ordering, the scale changes the answer here.
    if config.get('time_scale') is not None:
        d[time_col] = d[time_col] / config['time_scale']
    d = d.dropna(subset=needed).reset_index(drop=True)
    if len(d) < 10:
        return None, f"only {len(d)} complete cases"
    return d, None


# ═══════════════════════════════════════════════════════════════════════════════
# tau
# ═══════════════════════════════════════════════════════════════════════════════

TAU_SOURCES = ('plan_value', 'plan_rule', 'default_rule')


def tau_source_of(config):
    """Where tau came from — read, never re-derived.

    The generator is the only thing that can know whether the plan declared tau,
    so it writes `tau_source` into the config and this script reports it. An
    earlier version inferred it instead ("there is a tau_rule in the config, so
    it must have come from the plan") and got it exactly backwards: the generator
    ALSO writes the default rule's name into the config, so an undeclared tau was
    reported as pre-specified and the gate passed it — the one thing this remedy
    has to defend, defeated by deriving the same fact in two places.

    Absence is not a pre-specification. A config with no provenance claim gets
    `plan_value` only when it names a tau outright, and `default_rule` otherwise.
    """
    declared = config.get('tau_source')
    if declared in TAU_SOURCES:
        return declared
    if declared is not None:
        qc_warning(f"tau_source={declared!r} is not one of {TAU_SOURCES}; treating it "
                   f"as 'default_rule', because an unrecognised provenance claim is "
                   f"not evidence of pre-specification.")
        return 'default_rule'
    return 'plan_value' if config.get('tau') is not None else 'default_rule'


def resolve_tau(config, d):
    """(tau, source, rule_name, error).

    A literal tau wins over a rule; the source itself comes from `tau_source_of`.
    """
    cs = config['cox_settings']
    time_col, event_col = cs['time_column'], cs['event_column']
    group_col = config['grouping']['column']
    source = tau_source_of(config)

    if config.get('tau') is not None:
        try:
            tau = float(config['tau'])
        except (TypeError, ValueError):
            return None, source, None, f"tau={config['tau']!r} is not a number"
        if tau <= 0:
            return None, source, None, f"tau={tau} is not positive"
        return tau, source, None, None

    rule = config.get('tau_rule') or 'min_of_arm_max_followup'
    fn = TAU_RULES[rule]
    tau, err = fn(d, time_col, event_col, group_col)
    if err or tau is None or tau <= 0:
        return None, source, rule, err or f"rule {rule!r} produced tau={tau!r}"
    return float(tau), source, rule, None


# ═══════════════════════════════════════════════════════════════════════════════
# RMST
# ═══════════════════════════════════════════════════════════════════════════════

def _step_integral(times, surv, lo, hi):
    """Area under a right-continuous step function between lo and hi.

    The Kaplan-Meier curve holds the value `surv[j]` over `[times[j],
    times[j+1])`, so the integral is a sum of rectangles clipped to the window.
    Trapezoids would be wrong here — the curve does not interpolate between
    event times, it stays flat and then drops.
    """
    total = 0.0
    n = len(times)
    for j in range(n):
        left = times[j]
        right = times[j + 1] if j + 1 < n else hi
        a, b = max(left, lo), min(right, hi)
        if b > a:
            total += surv[j] * (b - a)
    return float(total)


def rmst_point_and_se(kmf, tau):
    """(rmst, se, error) for one arm.

    lifelines' `restricted_mean_survival_time(..., return_variance=True)` returns
    `E[min(T,tau)^2] - E[min(T,tau)]^2` — the spread of restricted survival time
    ACROSS INDIVIDUALS, not the sampling variance of the estimate. Using its
    square root as a standard error inflates it by roughly sqrt(n) and turns
    every comparison non-significant; measured on a 1500-patient fixture it gave
    SE = 2.06 for an RMST of 1.45 over tau = 4, i.e. a standard error larger than
    the entire integration window.

    So the variance here is the standard Kaplan-Meier one (Klein & Moeschberger):

        Var = sum over event times t_i <= tau of
              [ integral of S from t_i to tau ]^2 * d_i / (n_i * (n_i - d_i))

    The point estimate is computed from the same step integral and then checked
    against lifelines' value, which is the cross-check that keeps this
    hand-written integral honest without giving the two of them separate
    authority over the number.
    """
    sf = kmf.survival_function_
    times = np.asarray(sf.index.values, dtype=float)
    surv = np.asarray(sf.iloc[:, 0].values, dtype=float)
    rmst = _step_integral(times, surv, 0.0, tau)

    try:
        reference = float(restricted_mean_survival_time(kmf, t=tau))
    except Exception as exc:
        return None, None, f"lifelines RMST cross-check failed: {type(exc).__name__}: {exc}"
    if not np.isclose(rmst, reference, rtol=1e-6, atol=1e-9):
        return None, None, (f"the step integral ({rmst:.6f}) disagrees with lifelines' "
                            f"RMST ({reference:.6f}); refusing to report either")

    et = kmf.event_table
    var = 0.0
    for t_i, row in et.iterrows():
        if t_i > tau or t_i <= 0:
            continue
        d_i = float(row.get('observed', 0) or 0)
        n_i = float(row.get('at_risk', 0) or 0)
        if d_i <= 0 or n_i <= d_i:
            continue
        a_i = _step_integral(times, surv, float(t_i), tau)
        var += (a_i ** 2) * d_i / (n_i * (n_i - d_i))
    return float(rmst), (float(np.sqrt(var)) if var >= 0 else None), None


def rmst_by_arm(d, config, tau):
    """{label: {...}} plus the arm order, or (None, reason)."""
    cs = config['cox_settings']
    time_col, event_col = cs['time_column'], cs['event_column']
    grouping = config['grouping']
    group_col = grouping['column']

    arms = []
    for g in grouping['groups']:
        sub = d[d[group_col] == g['value']]
        n = int(len(sub))
        n_events = int(sub[event_col].sum()) if n else 0
        if n < 10 or n_events < 5:
            return None, (f"arm {g.get('label', g['value'])!r}: n={n}, events="
                          f"{n_events} — too few to estimate a survival curve")
        kmf = KaplanMeierFitter().fit(sub[time_col], sub[event_col])
        est, se, err = rmst_point_and_se(kmf, tau)
        if err:
            return None, f"RMST failed for arm {g.get('label')!r}: {err}"
        arms.append({
            'label': str(g.get('label', g['value'])),
            'value': g['value'],
            'n': n,
            'n_events': n_events,
            'max_followup': float(sub[time_col].max()),
            'rmst': est,
            'se': se,
        })
    return arms, None


def rmst_contrast(arms, tau):
    """Difference and ratio of the two restricted means, with a 95% CI on the
    difference. Two arms only: a 'difference' needs exactly two things."""
    if len(arms) != 2:
        return None, f"{len(arms)} arms declared; an RMST difference needs exactly two"
    a, b = arms[0], arms[1]
    diff = b['rmst'] - a['rmst']
    if a['se'] is None or b['se'] is None:
        return {'reference': a['label'], 'comparator': b['label'],
                'difference': diff, 'ci': None, 'p': None,
                'ratio': (b['rmst'] / a['rmst']) if a['rmst'] else None,
                'se_available': False}, None
    se = float(np.sqrt(a['se'] ** 2 + b['se'] ** 2))
    lo, hi = diff - 1.96 * se, diff + 1.96 * se
    z = diff / se if se > 0 else None
    from scipy import stats as sps
    p = float(2 * sps.norm.sf(abs(z))) if z is not None else None
    return {'reference': a['label'], 'comparator': b['label'],
            'difference': float(diff), 'se': se, 'ci': [float(lo), float(hi)],
            'z': float(z) if z is not None else None, 'p': p,
            'ratio': (float(b['rmst'] / a['rmst']) if a['rmst'] else None),
            'se_available': True}, None


# ═══════════════════════════════════════════════════════════════════════════════
# Excel
# ═══════════════════════════════════════════════════════════════════════════════

HEADER_FONT = Font(bold=True, size=11, color="FFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="4472C4")
TITLE_FONT = Font(bold=True, size=14)
SUB_FONT = Font(italic=True, size=10, color="555555")
DATA_FONT = Font(size=10)
SIG_FONT = Font(size=10, bold=True)
CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
THIN = Border(*(Side(style="thin", color="BFBFBF"),) * 4)


def fmt_p(p):
    if p is None:
        return "—"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def write_excel(config, arms, contrast, tau, tau_source, tau_rule, unit, ph_art):
    wb = Workbook()
    ws = wb.active
    ws.title = "RMST"
    for c, w in zip(range(1, 6), [26, 12, 12, 22, 20]):
        ws.column_dimensions[get_column_letter(c)].width = w

    r = 1
    ws.cell(row=r, column=1,
            value=config.get('title') or "Restricted mean survival time").font = TITLE_FONT
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    r += 1
    if config.get('subtitle'):
        ws.cell(row=r, column=1, value=config['subtitle']).font = SUB_FONT
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        r += 1
    ws.cell(row=r, column=1,
            value=f"tau = {tau:.4g} {unit} ({tau_source}"
                  f"{', rule ' + tau_rule if tau_rule else ''})").font = SUB_FONT
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
    r += 2

    for c, h in enumerate(["Arm", "n", "Events", f"RMST ({unit})",
                           f"Max follow-up ({unit})"], 1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font, cell.fill, cell.alignment, cell.border = HEADER_FONT, HEADER_FILL, CENTER, THIN
    r += 1
    for a in arms:
        vals = [a['label'], a['n'], a['n_events'],
                f"{a['rmst']:.3f}" + (f" (SE {a['se']:.3f})" if a['se'] is not None else ""),
                f"{a['max_followup']:.3f}"]
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=i, value=v)
            cell.font = DATA_FONT
            cell.alignment = LEFT if i == 1 else CENTER
            cell.border = THIN
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="Contrast").font = TITLE_FONT
    r += 1
    if contrast:
        ci = (f" (95% CI {contrast['ci'][0]:.3f} to {contrast['ci'][1]:.3f})"
              if contrast.get('ci') else "")
        cell = ws.cell(row=r, column=1,
                       value=f"{contrast['comparator']} minus {contrast['reference']}: "
                             f"{contrast['difference']:+.3f} {unit}{ci}; "
                             f"p = {fmt_p(contrast.get('p'))}")
        cell.font = SIG_FONT if (contrast.get('p') is not None
                                 and contrast['p'] < 0.05) else DATA_FONT
        cell.alignment = LEFT
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        r += 1

    r += 1
    footnotes = [
        f"Restricted mean survival time is the area under the Kaplan-Meier curve from "
        f"0 to tau = {tau:.4g} {unit}: the average event-free time accumulated over "
        f"that window. It makes no proportional-hazards assumption, which is why it is "
        f"reported here.",
        "⚠ This comparison is UNADJUSTED — Kaplan-Meier per arm, with no covariates. "
        "The model it remedies was adjusted, so this is a change of estimand and not "
        "only of scale. An adjusted RMST requires IPTW weighting or pseudo-observation "
        "regression, neither of which is computed here; if confounding is doing real "
        "work in your model, prefer ph_violation_remedy = 'stratify' or 'time_varying', "
        "which keep the adjustment.",
    ]
    if tau_source == 'default_rule':
        footnotes.append(
            f"⚠ tau was NOT declared in research_plan.json. It came from this script's "
            f"default rule ({tau_rule}), so it is not covered by the plan fingerprint "
            f"and cannot be shown to have been chosen before the results were seen — "
            f"which is the one claim this analysis has to make. Set "
            f"outcomes[<id>].rmst_tau or .rmst_tau_rule; the manuscript gate blocks "
            f"until you do.")
    elif tau_source == 'plan_rule':
        footnotes.append(
            f"tau was set by the pre-declared rule '{tau_rule}' in research_plan.json "
            f"(outcomes[<id>].rmst_tau_rule), evaluated against this cohort.")
    else:
        footnotes.append("tau was fixed in advance in research_plan.json "
                         "(outcomes[<id>].rmst_tau).")
    if config.get('source_table'):
        footnotes.append(
            f"This table is the pre-specified remedy for the proportional-hazards "
            f"violation reported in {os.path.basename(config['source_table'])}"
            + (f" (violating covariates: "
               f"{', '.join(ph_art.get('violating_variables') or []) or 'global only'})"
               if ph_art else "")
            + ". That workbook's hazard ratios are averaged over a ratio that was "
              "changing and must not be presented as the primary estimate.")
    if config.get('abbreviations'):
        footnotes.append(f"Abbreviations: {config['abbreviations']}")
    for note in footnotes:
        cell = ws.cell(row=r, column=1, value=note)
        cell.font, cell.alignment = SUB_FONT, LEFT
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=5)
        r += 1

    out = config['output_file']
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    wb.save(out)
    return [ws.title]


# ═══════════════════════════════════════════════════════════════════════════════
# Evidence sidecar
# ═══════════════════════════════════════════════════════════════════════════════

def file_sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def write_evidence(config, config_path, payload):
    out = config['output_file']
    payload = dict(payload)
    payload.update({
        'schema': EVIDENCE_SCHEMA,
        'remedy': REMEDY,
        'generated_by': 'research-plan/scripts/ph_rmst.py',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'outcome_id': config.get('outcome_id'),
        'table_basename': os.path.basename(out),
        'table_sha256': file_sha256(out) if os.path.exists(out) else None,
        'config_basename': os.path.basename(config_path),
        'config_sha256': file_sha256(config_path),
        'source_table': (os.path.basename(config['source_table'])
                         if config.get('source_table') else None),
    })
    path = config['evidence_file']
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def _not_computed(config, config_path, reason, **extra):
    payload = {'status': 'not_computed', 'reason': reason}
    payload.update(extra)
    path = write_evidence(config, config_path, payload)
    qc_blocking(f"RMST not computed: {reason}")
    print(f"Evidence written: {path} (status = not_computed)")
    return 2


def _not_applicable(config, config_path, reason, **extra):
    payload = {'status': 'not_applicable', 'reason': reason}
    payload.update(extra)
    path = write_evidence(config, config_path, payload)
    print(f"No proportional-hazards violation to remedy: {reason}")
    print(f"Evidence written: {path} (status = not_applicable)")
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# Preview / run
# ═══════════════════════════════════════════════════════════════════════════════

def preview(config, df):
    print("RMST PREVIEW (--check-missing)  |  mode = ph_rmst")
    d, err = analysis_frame(df, config)
    print(f"  rows loaded    : {len(df)}")
    if err:
        qc_warning(f"analysis frame would fail: {err}")
        return
    tau, source, rule, terr = resolve_tau(config, d)
    print(f"  complete cases : {len(d)}")
    print(f"  tau            : {tau}  [{source}{', ' + rule if rule else ''}]")
    if terr:
        qc_warning(terr)
    if source == 'default_rule':
        qc_warning("tau is not declared in research_plan.json; the manuscript gate "
                   "will block until outcomes[<id>].rmst_tau or .rmst_tau_rule is set.")
    print("[preview] No estimate was computed (--check-missing). No Excel was written.")


def run(config, config_path, df):
    ph_art, ph_path, ph_err = read_ph_test(config)
    if ph_err:
        qc_warning(f"PH test artifact: {ph_err}")

    ph_status = (ph_art or {}).get('status')
    if ph_art and ph_status == 'computed' and not ph_art.get('violated'):
        return _not_applicable(
            config, config_path,
            f"the proportional-hazards assumption was not violated in "
            f"{os.path.basename(ph_path)}, so there is nothing for the declared "
            f"'rmst' remedy to remedy",
            source_ph_test=os.path.basename(ph_path),
            source_ph_test_sha256=file_sha256(ph_path),
            ph_violating_variables=list(ph_art.get('violating_variables') or []))
    if ph_art and ph_status not in (None, 'computed'):
        return _not_computed(
            config, config_path,
            f"the upstream PH test is status={ph_status!r} "
            f"({ph_art.get('reason') or 'no reason given'}), so whether the assumption "
            f"is violated is unknown. An unknown violation is not an absent one.",
            source_ph_test=os.path.basename(ph_path) if ph_path else None)

    d, err = analysis_frame(df, config)
    if err:
        return _not_computed(config, config_path, err)

    tau, tau_source, tau_rule, terr = resolve_tau(config, d)
    if terr:
        return _not_computed(config, config_path, f"tau could not be resolved: {terr}",
                             tau_source=tau_source, tau_rule=tau_rule)

    arms, aerr = rmst_by_arm(d, config, tau)
    if aerr:
        return _not_computed(config, config_path, aerr, tau=tau,
                             tau_source=tau_source, tau_rule=tau_rule)
    contrast, cerr = rmst_contrast(arms, tau)
    if cerr:
        return _not_computed(config, config_path, cerr, tau=tau,
                             tau_source=tau_source, tau_rule=tau_rule)

    unit = config.get('time_unit') or 'time units'
    max_followup = {a['label']: a['max_followup'] for a in arms}
    tau_within = tau <= min(max_followup.values())

    # ── warnings, none of them fatal: each has an answer that is the author's ──
    qc_warning("the RMST difference reported here is UNADJUSTED (Kaplan-Meier per "
               "arm, no covariates). The model it remedies was adjusted, so this is a "
               "change of estimand; say so wherever it is reported.")
    if tau_source == 'default_rule':
        qc_warning(f"tau ({tau:.4g}) came from this script's default rule "
                   f"({tau_rule}), not from research_plan.json, so it is outside the "
                   f"plan fingerprint and cannot be shown to predate the result. Set "
                   f"outcomes[<id>].rmst_tau or .rmst_tau_rule — the manuscript gate "
                   f"blocks until you do.")
    if not tau_within:
        qc_warning(f"tau = {tau:.4g} is beyond the largest observed follow-up in at "
                   f"least one arm ({max_followup}). Past that point the curve is a "
                   f"flat extrapolation and the area under it is not data.")

    sheets = write_excel(config, arms, contrast, tau, tau_source, tau_rule, unit, ph_art)
    evidence_path = write_evidence(config, config_path, {
        'status': 'computed',
        'method': 'restricted mean survival time from Kaplan-Meier per arm '
                  '(lifelines restricted_mean_survival_time), unadjusted',
        'adjusted': False,
        'tau': tau,
        'tau_source': tau_source,
        'tau_rule': tau_rule,
        'tau_within_followup': bool(tau_within),
        'max_followup_by_arm': max_followup,
        'time_unit': unit,
        'arms': arms,
        'contrast': contrast,
        'n': int(len(d)),
        'n_events': int(d[config['cox_settings']['event_column']].sum()),
        'ph_violating_variables': list((ph_art or {}).get('violating_variables') or []),
        'source_ph_test': os.path.basename(ph_path) if ph_path else None,
        'source_ph_test_sha256': file_sha256(ph_path) if ph_path else None,
        'exposure_variable': config['grouping']['column'],
    })

    print(f"\ntau = {tau:.4g} {unit}  [{tau_source}"
          f"{', ' + tau_rule if tau_rule else ''}]")
    for a in arms:
        print(f"  {a['label']:<24} RMST {a['rmst']:.3f}  (n={a['n']}, events={a['n_events']})")
    if contrast:
        ci = (f"  95% CI {contrast['ci'][0]:.3f} to {contrast['ci'][1]:.3f}"
              if contrast.get('ci') else "")
        print(f"  difference             {contrast['difference']:+.3f}{ci}  "
              f"p = {fmt_p(contrast.get('p'))}")
    print(f"\nExcel written    : {config['output_file']}")
    print(f"  Sheets         : {', '.join(sheets)}")
    print(f"Evidence written : {evidence_path}")
    return 0


def main():
    if len(sys.argv) < 2:
        print("Usage: python ph_rmst.py config.json [--check-missing]")
        sys.exit(1)

    config_path = sys.argv[1]
    check_only = '--check-missing' in sys.argv

    config = load_config(config_path)
    df = load_data(config)

    print(f"Mode: {config['mode']}  (remedy = {config['remedy']})")
    print(f"Data loaded: n={len(df)}")

    if check_only:
        preview(config, df)
        sys.exit(0)

    rc = run(config, config_path, df)

    print("\nDone!")
    if _QC_MESSAGES:
        n_block = sum(1 for m in _QC_MESSAGES if m.startswith('[QC_BLOCKING]'))
        n_warn = len(_QC_MESSAGES) - n_block
        print(f"  QC: {n_block} blocking, {n_warn} warning(s) written to stderr")
    sys.exit(rc)


if __name__ == '__main__':
    main()
