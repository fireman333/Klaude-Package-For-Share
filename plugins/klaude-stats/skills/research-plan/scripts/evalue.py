#!/usr/bin/env python3
"""E-value — how strong an unmeasured confounder would have to be.

Spec: references/advanced_analyses.md section 1 (VanderWeele & Ding 2017).

Usage:
    python evalue.py config.json                  # full analysis
    python evalue.py config.json --check-missing  # preview only

An E-value is not a test. It does not say whether unmeasured confounding
exists; it says how strong it would have to be, on the risk-ratio scale and
associated with BOTH exposure and outcome, to explain the observed effect away.
A large E-value therefore means "this finding is not fragile", never "there is
no confounding".
"""

import json
import math
import os
import re
import sys

import numpy as np
import pandas as pd


RARE_OUTCOME_THRESHOLD = 0.15   # VanderWeele: below this, OR/HR approximate RR

_QC = []


def qc(kind, message):
    line = f"[QC_{kind}] {message}"
    _QC.append(line)
    print(line, file=sys.stderr)


def qc_warning(m):
    qc('WARNING', m)


def qc_blocking(m):
    qc('BLOCKING', m)


# ═══════════════════════════════════════════════════════════════════════════════
# The arithmetic
# ═══════════════════════════════════════════════════════════════════════════════

def evalue_from_rr(rr):
    """E-value for a risk ratio. Symmetric about the null: RR and 1/RR agree."""
    if rr is None or not np.isfinite(rr) or rr <= 0:
        return None
    if rr < 1:
        rr = 1.0 / rr
    return rr + math.sqrt(rr * (rr - 1.0))


def evalue_for_ci(lo, hi):
    """E-value for the confidence limit closest to the null.

    A CI that already crosses 1 gets an E-value of 1: no confounding at all is
    needed to be compatible with the null, which is the honest reading.
    """
    if lo is None or hi is None or not np.isfinite(lo) or not np.isfinite(hi):
        return None, None
    if lo <= 1.0 <= hi:
        return 1.0, 'CI crosses the null'
    limit = lo if lo > 1.0 else hi           # the limit nearer to 1
    return evalue_from_rr(limit), f'limit = {limit:.3f}'


def to_risk_ratio(effect, measure, prevalence):
    """Convert HR or OR to the risk-ratio scale. Returns (rr, how).

    Feeding an OR or HR straight into the E-value formula overstates it whenever
    the outcome is common, which is exactly when people reach for these
    measures, so the conversion is not optional.
    """
    if effect is None or not np.isfinite(effect) or effect <= 0:
        return None, 'not convertible'
    rare = prevalence is not None and prevalence < RARE_OUTCOME_THRESHOLD

    if measure == 'RR':
        return effect, 'already a risk ratio'
    if measure == 'OR':
        if rare:
            return effect, f'rare outcome ({prevalence:.1%}) — OR approximates RR'
        return math.sqrt(effect), f'common outcome ({prevalence:.1%}) — RR = sqrt(OR)'
    # HR
    if rare:
        return effect, f'rare outcome ({prevalence:.1%}) — HR approximates RR'
    # VanderWeele's approximation for a hazard ratio with a common outcome
    num = 1.0 - math.pow(0.5, math.sqrt(effect))
    den = 1.0 - math.pow(0.5, math.sqrt(1.0 / effect))
    if den == 0:
        return None, 'conversion undefined'
    return num / den, f'common outcome ({prevalence:.1%}) — HR converted (VanderWeele 2017)'


# ═══════════════════════════════════════════════════════════════════════════════
# Input
# ═══════════════════════════════════════════════════════════════════════════════

OPS = {'==': lambda s, v: s == v, '!=': lambda s, v: s != v,
       '>': lambda s, v: s > v, '>=': lambda s, v: s >= v,
       '<': lambda s, v: s < v, '<=': lambda s, v: s <= v}

# "1.48 (1.35–1.63)" — en-dash is what the other skills emit; accept a hyphen too.
_EFFECT_RE = re.compile(r'([\d.]+)\s*\(\s*([\d.]+)\s*[–\-]\s*([\d.]+)\s*\)')


def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    config.setdefault('filters', [])
    config.setdefault('derived_variables', [])
    config.setdefault('subtitle', '')
    config.setdefault('estimates', [])
    config.setdefault('reference_confounders', [])
    return config


def load_data(config):
    path = config.get('data_file')
    if not path or not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.xlsx', '.xls'):
        df = pd.read_excel(path)
    elif ext == '.tsv':
        df = pd.read_csv(path, sep='\t')
    else:
        df = pd.read_csv(path)
    for f in config['filters']:
        col, op, val = f['column'], f['operator'], f['value']
        if op in ('==', '!='):
            df = df[OPS[op](df[col], val)]
        elif op in OPS:
            df = df[OPS[op](pd.to_numeric(df[col], errors='coerce'), val)]
        elif op == 'in':
            df = df[df[col].isin(val)]
        elif op == 'not_in':
            df = df[~df[col].isin(val)]
    return df


def outcome_prevalence(config, df):
    """Proportion with the event. Decides which RR approximation applies."""
    if df is None:
        return None
    col = None
    if config.get('analysis_type') == 'cox':
        col = (config.get('cox_settings') or {}).get('event_column')
    else:
        col = (config.get('logistic_settings') or {}).get('outcome_column')
    if not col or col not in df.columns:
        return None
    s = pd.to_numeric(df[col], errors='coerce').dropna()
    if s.empty:
        return None
    return float((s > 0).mean())


def parse_source_estimates(config, preview=False):
    """Read effect estimates out of an upstream skill's Excel output.

    Numbers come from a generated file rather than being retyped into this
    config — delivery_discipline.md rule 1. If the sheet cannot be parsed the
    step blocks rather than silently producing an empty table.

    In preview the upstream regression legitimately may not have run yet — the
    whole plan can be previewed before anything executes — so a missing source
    is a warning there and a blocker only on the real run.
    """
    src = config.get('source_file')
    if not src:
        return []
    if not os.path.exists(src):
        (qc_warning if preview else qc_blocking)(
            f"source_file not found: {src}."
            + (" It is produced by the upstream regression step, which has not run yet;"
               " that is expected during preview." if preview
               else " Run the upstream regression step first."))
        return []
    sheet = config.get('source_sheet')
    try:
        raw = pd.read_excel(src, sheet_name=sheet or 0, header=None)
    except Exception as exc:
        qc_blocking(f"could not read {src}: {exc}")
        return []

    est = []
    for _, row in raw.iterrows():
        cells = [str(c) for c in row.tolist() if pd.notna(c)]
        if not cells:
            continue
        label = cells[0].strip()
        for c in cells[1:]:
            m = _EFFECT_RE.search(c)
            if not m:
                continue
            eff, lo, hi = (float(x) for x in m.groups())
            if not label or label.lower().startswith(('variable', 'nan')):
                break
            est.append({'label': label, 'effect': eff, 'ci_lower': lo, 'ci_upper': hi})
            break
    if not est:
        qc_blocking(f"no 'x.xx (lo–hi)' effect estimates found in {os.path.basename(src)}"
                    f"{f' sheet {sheet!r}' if sheet else ''}. Check source_sheet.")
    return est


def collect_estimates(config, preview=False):
    """Explicit estimates win; otherwise parse the upstream output."""
    if config.get('estimates'):
        return list(config['estimates']), 'config.estimates'
    return parse_source_estimates(config, preview), config.get('source_file', '')


# ═══════════════════════════════════════════════════════════════════════════════
# Output
# ═══════════════════════════════════════════════════════════════════════════════

def interpret(e_point, e_ci, refs):
    """One sentence with a scale anchor. A bare number carries no meaning."""
    if e_point is None:
        return 'not evaluable'
    if e_ci is not None and e_ci <= 1.0:
        return ('The CI already includes the null, so no unmeasured confounding is '
                'needed to be compatible with no effect.')
    base = (f'An unmeasured confounder would need to be associated with both exposure '
            f'and outcome by a risk ratio of at least {e_point:.2f} each, above and '
            f'beyond the measured covariates, to explain the point estimate away')
    if e_ci is not None:
        base += f'; {e_ci:.2f} to move the CI to the null'
    if refs:
        strongest = max(refs, key=lambda r: float(r.get('rr', 0) or 0))
        rr = float(strongest.get('rr', 0) or 0)
        rel = 'stronger than' if e_point > rr else 'weaker than'
        base += (f'. That is {rel} the strongest measured confounder here '
                 f'({strongest.get("name", "?")}, RR = {rr:.2f})')
    else:
        base += ('. No measured-confounder benchmark was supplied, so the reader has '
                 'no scale to judge whether that is plausible')
    return base + '.'


def write_excel(rows, config, measure, prevalence, source_desc):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    DARK_BLUE, HEADER_BG = '1F3864', '2E5FA3'
    SECTION_BG, ALT_ROW, BORDER = 'EBF2FA', 'F7FAFD', 'BFBFBF'

    wb = Workbook()
    ws = wb.active
    ws.title = 'E-values'
    thin = Side(style='thin', color=BORDER)
    box = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws['A1'] = config.get('title', 'E-value: sensitivity to unmeasured confounding')
    ws['A1'].font = Font(size=13, bold=True, color=DARK_BLUE)
    ws['A2'] = config.get('subtitle', '')
    ws['A2'].font = Font(size=10, italic=True, color='595959')

    headers = ['Variable', f'Observed {measure} (95% CI)', 'Risk-ratio scale',
               'E-value (point)', 'E-value (CI)', 'Interpretation']
    widths = [30, 24, 18, 16, 14, 96]
    for i, (h, w) in enumerate(zip(headers, widths), start=1):
        c = ws.cell(row=4, column=i, value=h)
        c.font = Font(bold=True, color='FFFFFF')
        c.fill = PatternFill('solid', fgColor=HEADER_BG)
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        c.border = box
        ws.column_dimensions[chr(64 + i)].width = w

    r = 5
    for row in rows:
        vals = [row['label'],
                f"{row['effect']:.2f} ({row['ci_lower']:.2f}–{row['ci_upper']:.2f})",
                f"{row['rr']:.3f}" if row['rr'] else '—',
                f"{row['e_point']:.2f}" if row['e_point'] else '—',
                f"{row['e_ci']:.2f}" if row['e_ci'] else '—',
                row['interpretation']]
        for i, v in enumerate(vals, start=1):
            c = ws.cell(row=r, column=i, value=v)
            c.border = box
            c.alignment = Alignment(vertical='top',
                                    wrap_text=(i == 6),
                                    horizontal='left' if i in (1, 6) else 'center')
            if r % 2 == 0:
                c.fill = PatternFill('solid', fgColor=ALT_ROW)
        r += 1

    r += 1
    ws.cell(row=r, column=1, value='Method').font = Font(bold=True, color=DARK_BLUE)
    ws.cell(row=r, column=1).fill = PatternFill('solid', fgColor=SECTION_BG)
    r += 1
    for label, val in [
        ('Estimand', 'Not a test. The minimum strength of association, on the risk-ratio '
                     'scale, that an unmeasured confounder would need with BOTH exposure '
                     'and outcome to explain the observed effect away.'),
        ('Formula', 'E = RR + sqrt(RR x (RR - 1)); for RR < 1 the reciprocal is used first '
                    '(VanderWeele & Ding, Ann Intern Med 2017).'),
        ('Effect measure', measure),
        ('Outcome prevalence', f'{prevalence:.1%}' if prevalence is not None else
                               'unknown — conversion assumed the rare-outcome case'),
        ('Scale conversion', rows[0]['how'] if rows else '—'),
        ('CI E-value', 'Computed for the confidence limit nearer the null. A CI that '
                       'crosses the null gets E = 1.'),
        ('Estimates read from', source_desc or '—'),
        ('Caution', 'A large E-value means the finding is not fragile. It never means '
                    'unmeasured confounding is absent.'),
    ]:
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        c = ws.cell(row=r, column=2, value=val)
        c.alignment = Alignment(wrap_text=True, vertical='top')
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        r += 1

    out = config['output_file']
    os.makedirs(os.path.dirname(os.path.abspath(out)) or '.', exist_ok=True)
    wb.save(out)
    return ['E-values']


# ═══════════════════════════════════════════════════════════════════════════════

def build_rows(estimates, measure, prevalence, refs):
    rows = []
    for e in estimates:
        eff = e.get('effect')
        lo, hi = e.get('ci_lower'), e.get('ci_upper')
        rr, how = to_risk_ratio(eff, measure, prevalence)
        rr_lo, _ = to_risk_ratio(lo, measure, prevalence)
        rr_hi, _ = to_risk_ratio(hi, measure, prevalence)
        e_point = evalue_from_rr(rr)
        e_ci, _note = evalue_for_ci(rr_lo, rr_hi)
        rows.append({'label': e.get('label', '?'), 'effect': eff,
                     'ci_lower': lo, 'ci_upper': hi, 'rr': rr, 'how': how,
                     'e_point': e_point, 'e_ci': e_ci,
                     'interpretation': interpret(e_point, e_ci, refs)})
    return rows


def main():
    if len(sys.argv) < 2:
        print('Usage: python evalue.py config.json [--check-missing]')
        sys.exit(1)

    config = load_config(sys.argv[1])
    df = load_data(config)
    prevalence = outcome_prevalence(config, df)
    measure = 'HR' if config.get('analysis_type') == 'cox' else 'OR'
    preview = '--check-missing' in sys.argv
    estimates, source_desc = collect_estimates(config, preview)

    if preview:
        print('=' * 78)
        print('E-VALUE PREVIEW (--check-missing)')
        print('=' * 78)
        print(f'  Effect measure      : {measure}')
        print(f'  Outcome prevalence  : '
              f'{f"{prevalence:.1%}" if prevalence is not None else "unknown"}'
              f'{"  (rare -> direct)" if prevalence is not None and prevalence < RARE_OUTCOME_THRESHOLD else "  (common -> converted)"}')
        print(f'  Estimates source    : {source_desc or "(none)"}')
        print(f'  Estimates found     : {len(estimates)}')
        for e in estimates[:12]:
            print(f'      {e.get("label", "?")[:34]:<34s} '
                  f'{e.get("effect")} ({e.get("ci_lower")}–{e.get("ci_upper")})')
        print(f'  Benchmark confounders: {len(config["reference_confounders"])}')
        sys.exit(0)

    if any(q.startswith('[QC_BLOCKING]') for q in _QC):
        sys.exit(2)

    if not estimates:
        qc_blocking('no effect estimates to evaluate')
        sys.exit(2)

    if prevalence is None:
        qc_warning('outcome prevalence unknown (data_file or event column unavailable): '
                   'the rare-outcome approximation was assumed, which OVERSTATES the '
                   'E-value when the outcome is common. Supply data_file to fix this.')
    if not config['reference_confounders']:
        qc_warning('no reference_confounders supplied: the E-value is reported without a '
                   'scale anchor, so nobody can judge whether that strength is plausible. '
                   'Add the associations of one or two known strong measured confounders.')

    rows = build_rows(estimates, measure, prevalence, config['reference_confounders'])
    for r in rows:
        if r['e_ci'] is not None and r['e_ci'] <= 1.0:
            qc_warning(f"{r['label']}: CI crosses the null, so the CI E-value is 1 — this "
                       f"result cannot support a causal claim regardless of the point E-value.")

    sheets = write_excel(rows, config, measure, prevalence, source_desc)
    print(f'  Excel : {config["output_file"]}')
    print(f'  Sheets: {", ".join(sheets)}')
    print(f'  Rows  : {len(rows)}')
    print('\nDone!')
    print(f'  QC: {sum(1 for q in _QC if "BLOCKING" in q)} blocking, '
          f'{sum(1 for q in _QC if "WARNING" in q)} warning(s) written to stderr')


if __name__ == '__main__':
    main()
