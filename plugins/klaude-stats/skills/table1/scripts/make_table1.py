#!/usr/bin/env python3
"""
Table 1 Generator — Parameterized script for medical research baseline characteristics tables.
Accepts a JSON config file and produces formatted Excel + CSV output.

Usage:
    python make_table1.py config.json                  # Generate Table 1
    python make_table1.py config.json --check-missing  # Missing data report only
"""

import sys
import json
import os
import operator
import pandas as pd
import numpy as np
from scipy.stats import mannwhitneyu, ttest_ind, chi2_contingency, fisher_exact, shapiro
# table1-B-3: removed global `warnings.filterwarnings('ignore')` — scipy/pandas/openpyxl
# warnings can flag invalid tests, deprecated APIs, or data import issues. If a specific
# noisy warning needs suppression, scope it locally with `warnings.catch_warnings`.


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════

def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    # Defaults
    config.setdefault('filters', [])
    config.setdefault('derived_variables', [])
    config.setdefault('subtitle', '')
    config.setdefault('abbreviations', '')
    # Default = available-case (per-variable): each variable's n/mean/% is computed
    # on its own non-missing values, the standard convention for a baseline Table 1.
    # Set explicitly to 'listwise' for global complete-case deletion across all table
    # variables (shrinks N and can bias the table; opt-in only).
    config.setdefault('missing_data_handling', 'available')
    config.setdefault('normality_alpha', 0.05)
    config.setdefault('normality_method', 'skew')  # 'skew' (default) or 'shapiro'
    return config


# ═══════════════════════════════════════════════════════════════════════════════
# Data Loading & Preprocessing
# ═══════════════════════════════════════════════════════════════════════════════

# table1-R2-1: split equality vs numeric ops. Equality (==, !=) must compare on
# original dtype, otherwise string filters like sex == "F" silently coerce to NaN
# and drop every row.
EQ_OPS = {'==': operator.eq, '!=': operator.ne}
NUMERIC_OPS = {'>': operator.gt, '>=': operator.ge, '<': operator.lt, '<=': operator.le}
OPS = {**EQ_OPS, **NUMERIC_OPS}

def load_data(config):
    path = config['data_file']
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.xlsx', '.xls'):
        # table1-R2-2: refuse to silently pick first sheet from multi-sheet workbook.
        # Require explicit `config['sheet_name']` when the workbook has > 1 sheet.
        sheet_name = config.get('sheet_name')
        if sheet_name is None:
            try:
                xl = pd.ExcelFile(path)
            except Exception as e:
                sys.exit(f"[FATAL] Could not open Excel file '{path}': {e}")
            if len(xl.sheet_names) > 1:
                sys.exit(
                    f"[FATAL] Excel file '{path}' has {len(xl.sheet_names)} sheets: "
                    f"{xl.sheet_names}. Specify config['sheet_name'] to choose one."
                )
            sheet_name = xl.sheet_names[0]
        df = pd.read_excel(path, sheet_name=sheet_name)
        print(f"[INFO] Loaded sheet '{sheet_name}' from '{path}'", file=sys.stderr)
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
            # table1-R2-1: keep original dtype for equality so string filters work
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
            # Build a local namespace with dependency columns
            local_ns = {}
            for dep in dv.get('dependencies', []):
                local_ns[dep] = pd.to_numeric(df[dep], errors='coerce')
            local_ns['np'] = np
            df[dv['name']] = eval(dv['expression'], {"__builtins__": {}}, local_ns)

    return df


def split_groups(df, config):
    gc = config['grouping']
    col = gc['column']
    groups = gc['groups']

    # table1-R1-1: refuse >= 3 groups loudly. Previously truncated to first 2 silently.
    # For multi-group analyses, use ANOVA / Kruskal-Wallis tools instead.
    if len(groups) != 2:
        sys.exit(
            f"[FATAL] table1 supports 2-group comparisons only. Got {len(groups)} groups "
            f"in config['grouping']['groups']. For >= 3 groups, use ANOVA / "
            f"Kruskal-Wallis tools."
        )

    g1_val = groups[0]['value']
    g2_val = groups[1]['value']

    # table1-B-1: dtype-aware comparison. Coerce to numeric only when BOTH configured
    # group values are numeric. String group labels (e.g. "control"/"treatment") would
    # otherwise be silently wiped to NaN, producing two empty groups that the script
    # then runs analyses on.
    if isinstance(g1_val, (int, float)) and isinstance(g2_val, (int, float)):
        col_vals = pd.to_numeric(df[col], errors='coerce')
    else:
        col_vals = df[col]

    grp1 = df[col_vals == g1_val]
    grp2 = df[col_vals == g2_val]

    if len(grp1) == 0 or len(grp2) == 0:
        sys.exit(
            f"[FATAL] split_groups produced empty group(s): "
            f"{groups[0]['label']} n={len(grp1)}, {groups[1]['label']} n={len(grp2)}. "
            f"Check column '{col}' values vs configured group values "
            f"({g1_val!r}, {g2_val!r})."
        )

    return grp1, grp2


# ═══════════════════════════════════════════════════════════════════════════════
# Missing Data Analysis
# ═══════════════════════════════════════════════════════════════════════════════

def check_missing(df, grp1, grp2, config):
    g1_label = config['grouping']['groups'][0]['label']
    g2_label = config['grouping']['groups'][1]['label']

    header = f"{'Variable':<40} {'Total N':>8} {'Miss':>6} {'Miss%':>7} {'  ' + g1_label + ' Miss':>12} {'  ' + g2_label + ' Miss':>12}"
    sep = '-' * len(header)
    lines = [header, sep]

    all_cols = []
    for section in config['sections']:
        for var in section['variables']:
            all_cols.append((var['label'], var['column'], section['header']))

    has_missing = False
    current_section = None
    for label, col, section_header in all_cols:
        if section_header != current_section:
            current_section = section_header
            lines.append(f"\n  [{section_header}]")

        total_n = len(df)
        total_miss = pd.to_numeric(df[col], errors='coerce').isna().sum() if col in df.columns else total_n
        total_pct = total_miss / total_n * 100 if total_n > 0 else 0

        g1_n = len(grp1)
        g1_miss = pd.to_numeric(grp1[col], errors='coerce').isna().sum() if col in grp1.columns else g1_n
        g1_str = f"{g1_miss}/{g1_n} ({g1_miss/g1_n*100:.1f}%)" if g1_n > 0 else "N/A"

        g2_n = len(grp2)
        g2_miss = pd.to_numeric(grp2[col], errors='coerce').isna().sum() if col in grp2.columns else g2_n
        g2_str = f"{g2_miss}/{g2_n} ({g2_miss/g2_n*100:.1f}%)" if g2_n > 0 else "N/A"

        if total_miss > 0:
            has_missing = True
            marker = " ⚠"
        else:
            marker = ""

        lines.append(f"  {label:<38} {total_n:>8} {total_miss:>6} {total_pct:>6.1f}% {g1_str:>12} {g2_str:>12}{marker}")

    lines.append(sep)
    if not has_missing:
        lines.append("\n✓ All variables have zero missing values.")
    else:
        lines.append(f"\n⚠ Some variables have missing data (marked with ⚠).")
        lines.append(f"  Current handling mode: {config['missing_data_handling']}")

    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Statistical Functions
# ═══════════════════════════════════════════════════════════════════════════════

def _coerce_numeric_with_warning(series, col_name, var_type):
    """Coerce a Series to numeric with errors='coerce', emit warning if non-numeric values are lost.

    table1-R2-3: standardize coercion reporting across continuous/binary/ordinal/categorical
    stats so date strings, mixed dtype, or mislabeled categories don't silently become missing.
    """
    coerced = pd.to_numeric(series, errors='coerce')
    n_lost = int(series.notna().sum() - coerced.notna().sum())
    if n_lost > 0:
        unique_lost = sorted([str(v) for v in series[series.notna() & coerced.isna()].unique()])[:5]
        print(f"[WARNING] {var_type} variable '{col_name}': {n_lost} non-numeric value(s) "
              f"coerced to NaN. Examples: {unique_lost}", file=sys.stderr)
    return coerced


def test_normality(x, method='skew', alpha=0.05):
    """
    Normality check.

    method='skew'    : |skewness| < 1 (default; robust for n > 100 where
                       Shapiro-Wilk over-rejects).
    method='shapiro' : Shapiro-Wilk test; normal iff p >= alpha.
                       alpha is read from config['normality_alpha'] (default 0.05).
    """
    x = x.dropna()
    if len(x) < 8:
        return False
    if method == 'shapiro':
        if len(x) > 5000:
            x = x.sample(5000, random_state=0)
        try:
            _, p = shapiro(x)
        except Exception:
            return abs(x.skew()) < 1.0
        return p >= alpha
    return abs(x.skew()) < 1.0


def _pval_str(p):
    if p is None or pd.isna(p):
        return "N/A"
    if p < 0.001:
        return "<0.001*"
    elif p < 0.05:
        return f"{p:.3f}*"
    else:
        return f"{p:.3f}"


# table1-A-3: SMD (standardized mean difference) helpers.
# Continuous: |mean1 - mean2| / pooled_sd (Cohen's d denominator using (var1+var2)/2).
# Binary: Cohen's h (arcsin transformation) — standard for PSM and Table 1 reporting.
# Ordinal/categorical: not reported here (per-level Cohen's h would be misleading);
# em-dash is used for those rows.
def _smd_continuous(x1, x2):
    if len(x1) < 2 or len(x2) < 2:
        return float('nan')
    pooled_sd = float(np.sqrt((x1.var(ddof=1) + x2.var(ddof=1)) / 2))
    if pooled_sd == 0 or np.isnan(pooled_sd):
        return float('nan')
    return float(abs(x1.mean() - x2.mean()) / pooled_sd)


def _smd_binary(r1, n1, r2, n2):
    if n1 == 0 or n2 == 0:
        return float('nan')
    p1 = r1 / n1
    p2 = r2 / n2
    # Cohen's h
    return float(2 * abs(np.arcsin(np.sqrt(p1)) - np.arcsin(np.sqrt(p2))))


def _smd_str(s):
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return "–"
    return f"{s:.2f}"


def continuous_stat(col, grp1, grp2, all_data, config=None):
    """Analyze a continuous variable: returns (total_str, g1_str, g2_str, p_str, method, smd_str).

    table1-A-3: now also computes SMD = |mean1 - mean2| / pooled_sd.
    table1-R2-3: uses _coerce_numeric_with_warning so non-numeric values are surfaced.
    """
    x  = _coerce_numeric_with_warning(all_data[col], col, "Continuous").dropna()
    x1 = _coerce_numeric_with_warning(grp1[col],     col, "Continuous").dropna()
    x2 = _coerce_numeric_with_warning(grp2[col],     col, "Continuous").dropna()

    if len(x1) < 2 or len(x2) < 2:
        return f"n={len(x)}", f"n={len(x1)}", f"n={len(x2)}", "N/A", "–", "–"

    cfg = config or {}
    # table1-A-1: per-group normality. Pooled normality could mask one skewed group;
    # both groups must pass for parametric. Either fails -> Mann-Whitney.
    normality_kwargs = dict(
        method=cfg.get('normality_method', 'skew'),
        alpha=cfg.get('normality_alpha', 0.05),
    )
    normal = test_normality(x1, **normality_kwargs) and test_normality(x2, **normality_kwargs)

    smd_str = _smd_str(_smd_continuous(x1, x2))

    if normal:
        m,  s  = x.mean(),  x.std()
        m1, s1 = x1.mean(), x1.std()
        m2, s2 = x2.mean(), x2.std()
        _, p = ttest_ind(x1, x2, equal_var=False)
        method = "t-test"
        fmt = lambda mu, sd: f"{mu:.1f} \u00b1 {sd:.1f}"
        return fmt(m, s), fmt(m1, s1), fmt(m2, s2), _pval_str(p), method, smd_str
    else:
        med,  q1,  q3  = x.median(),  x.quantile(0.25),  x.quantile(0.75)
        med1, q11, q31 = x1.median(), x1.quantile(0.25), x1.quantile(0.75)
        med2, q12, q32 = x2.median(), x2.quantile(0.25), x2.quantile(0.75)
        _, p = mannwhitneyu(x1, x2, alternative='two-sided')
        method = "Mann-Whitney"
        fmt = lambda m, a, b: f"{m:.1f} [{a:.1f}\u2013{b:.1f}]"
        return fmt(med, q1, q3), fmt(med1, q11, q31), fmt(med2, q12, q32), _pval_str(p), method, smd_str


def binary_stat(col, grp1, grp2, all_data, event_value=1):
    """Analyze a binary variable: returns (total_str, g1_str, g2_str, p_str, method).

    table1-A-2: event_value defaults to 1 for backward compatibility. Configs should
    declare ``event_value`` per binary variable when encoding differs (2/1, Y/N, 0=event).
    Validates that event_value appears in the data and warns when:
      (a) original column has non-numeric values lost to coercion
      (b) configured event_value not present in the numeric data
      (c) data has more than 2 unique numeric values (not actually binary)
    """
    x  = pd.to_numeric(all_data[col], errors='coerce')
    x1 = pd.to_numeric(grp1[col],     errors='coerce')
    x2 = pd.to_numeric(grp2[col],     errors='coerce')

    # (a) Detect non-numeric values lost to coercion (e.g. 'Y'/'N' string-coded)
    n_lost = int(all_data[col].notna().sum() - x.notna().sum())
    if n_lost > 0:
        unique_orig = sorted([str(v) for v in all_data[col].dropna().unique()])[:5]
        print(f"[WARNING] Binary variable '{col}': {n_lost} non-numeric value(s) "
              f"coerced to NaN. Unique original values: {unique_orig}. Recode the "
              f"column to numeric before analysis (e.g. Y -> 1, N -> 0).",
              file=sys.stderr)

    # (b) and (c) — validate event_value matches numeric data
    non_na_numeric = sorted(x.dropna().unique().tolist())
    if non_na_numeric and event_value not in non_na_numeric:
        print(f"[WARNING] Binary variable '{col}': configured event_value="
              f"{event_value!r} not in numeric data {non_na_numeric[:5]}. "
              f"n (%) will read 0/0. Check event_value config.", file=sys.stderr)
    if len(non_na_numeric) > 2:
        print(f"[WARNING] Binary variable '{col}' has >2 unique numeric values "
              f"{non_na_numeric[:5]}; should be binary.", file=sys.stderr)

    n_t  = x.notna().sum();  r_t  = (x  == event_value).sum()
    n_1  = x1.notna().sum(); r_1  = (x1 == event_value).sum()
    n_2  = x2.notna().sum(); r_2  = (x2 == event_value).sum()

    # table1-A-3: SMD for binary = Cohen's h (arcsin transform)
    smd_str = _smd_str(_smd_binary(int(r_1), int(n_1), int(r_2), int(n_2)))

    ct = np.array([[r_1, n_1 - r_1], [r_2, n_2 - r_2]])

    # Prefer Fisher when any expected cell < 5 (Cochran's rule) or tiny groups.
    # Fall back to observed-cell / group-size heuristics when chi2 can't compute
    # expected counts (e.g. degenerate table with an all-zero row/column).
    use_fisher = False
    try:
        _, _, _, expected = chi2_contingency(ct, correction=False)
        if (expected < 5).any() or n_1 < 30 or n_2 < 30:
            use_fisher = True
    except ValueError:
        use_fisher = True

    if use_fisher:
        _, p = fisher_exact(ct)
        method = "Fisher"
    else:
        _, p, _, _ = chi2_contingency(ct, correction=False)
        method = "Chi-square"

    fmt = lambda r, n: f"{int(r)} ({r/n*100:.1f}%)" if n > 0 else "\u2013"
    return fmt(r_t, n_t), fmt(r_1, n_1), fmt(r_2, n_2), _pval_str(p), method, smd_str


def ordinal_stat(col, grp1, grp2, all_data, label_map=None):
    """Analyze an ordinal variable: returns list of row dicts for each category.

    table1-R2-3: uses _coerce_numeric_with_warning so non-numeric values are surfaced.
    table1-A-3: SMD per-level not standard for ordinal \u2014 em-dash used in row dict.
    """
    x  = _coerce_numeric_with_warning(all_data[col], col, "Ordinal").dropna()
    x1 = _coerce_numeric_with_warning(grp1[col],     col, "Ordinal").dropna()
    x2 = _coerce_numeric_with_warning(grp2[col],     col, "Ordinal").dropna()

    cats = sorted(x.unique())
    rows = []

    if len(x1) >= 2 and len(x2) >= 2:
        _, p = mannwhitneyu(x1, x2, alternative='two-sided')
        p_str = _pval_str(p)
    else:
        p_str = "N/A"

    # Convert label_map keys to float for matching
    float_label_map = {}
    if label_map:
        for k, v in label_map.items():
            try:
                float_label_map[float(k)] = v
            except (ValueError, TypeError):
                float_label_map[k] = v

    for i, cat in enumerate(cats):
        lbl = float_label_map.get(cat, f"  Class {int(cat)}") if float_label_map else f"  Class {int(cat)}"
        if not lbl.startswith("  "):
            lbl = "  " + lbl
        n_t = len(x);  r_t = (x  == cat).sum()
        n_1 = len(x1); r_1 = (x1 == cat).sum()
        n_2 = len(x2); r_2 = (x2 == cat).sum()
        fmt = lambda r, n: f"{int(r)} ({r/n*100:.1f}%)" if n > 0 else "\u2013"
        rows.append({
            'variable': lbl,
            'total':    fmt(r_t, n_t),
            'grp1':     fmt(r_1, n_1),
            'grp2':     fmt(r_2, n_2),
            'p':        p_str if i == 0 else '',
            'method':   'Mann-Whitney' if i == 0 else '',
            'smd':      '–',  # table1-A-3: per-level SMD for ordinal not standard
        })
    return rows


def categorical_stat(col, grp1, grp2, all_data, label_map=None):
    """Analyze a nominal (multi-level) categorical variable: returns list of row dicts.

    table1-R1-2: nominal categorical (race, smoking type, medication class) is NOT
    ordinal. Overall association tested with RxC chi-square (Fisher exact only for
    2x2 sparse cells; RxC sparse falls back to chi-square with method labelled).
    Per-level n (%) shown for each category.
    """
    x_orig  = all_data[col]
    x1_orig = grp1[col]
    x2_orig = grp2[col]

    # Use original dtype (categorical can be string-coded; don't coerce)
    x  = x_orig.dropna()
    x1 = x1_orig.dropna()
    x2 = x2_orig.dropna()

    if len(x) == 0 or len(x1) == 0 or len(x2) == 0:
        # No data — emit single placeholder row
        return [{
            'variable': f"  (no data for {col})",
            'total': "–", 'grp1': "–", 'grp2': "–",
            'p': "N/A", 'method': "–", 'smd': "–",
        }]

    # Sort by string repr for stable ordering (numeric and string mix)
    cats = sorted(x.unique(), key=lambda v: str(v))

    # Build contingency table (rows = categories, cols = groups)
    ct = np.array([[(x1 == cat).sum(), (x2 == cat).sum()] for cat in cats])

    p = float('nan')
    method = "–"
    if ct.size > 0 and ct.sum() > 0:
        try:
            _, _, _, expected = chi2_contingency(ct, correction=False)
            sparse = bool((expected < 5).any())
        except ValueError:
            sparse = True

        if sparse and ct.shape == (2, 2):
            _, p = fisher_exact(ct)
            method = "Fisher"
        elif sparse:
            # RxC sparse: scipy.stats.fisher_exact only supports 2x2.
            # Use chi-square with sparse-cell flag in method label.
            try:
                _, p, _, _ = chi2_contingency(ct, correction=False)
                method = "Chi-square (sparse)"
            except ValueError:
                p = float('nan')
                method = "–"
        else:
            _, p, _, _ = chi2_contingency(ct, correction=False)
            method = "Chi-square"
    p_str = _pval_str(p)

    # Convert label_map keys for matching (str-keyed in JSON)
    str_label_map = {str(k): v for k, v in (label_map or {}).items()}

    rows = []
    for i, cat in enumerate(cats):
        lbl = str_label_map.get(str(cat), f"  {cat}")
        if not str(lbl).startswith("  "):
            lbl = "  " + str(lbl)
        n_t = len(x);  r_t = int((x  == cat).sum())
        n_1 = len(x1); r_1 = int((x1 == cat).sum())
        n_2 = len(x2); r_2 = int((x2 == cat).sum())
        fmt = lambda r, n: f"{int(r)} ({r/n*100:.1f}%)" if n > 0 else "–"
        rows.append({
            'variable': lbl,
            'total':    fmt(r_t, n_t),
            'grp1':     fmt(r_1, n_1),
            'grp2':     fmt(r_2, n_2),
            'p':        p_str if i == 0 else '',
            'method':   method if i == 0 else '',
            'smd':      '–',  # per-level SMD for nominal not standard
        })
    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# Table Row Builder
# ═══════════════════════════════════════════════════════════════════════════════

def build_rows(config, df, grp1, grp2):
    rows = []

    # N row
    rows.append({
        'variable': 'n',
        'total': str(len(df)),
        'grp1': str(len(grp1)),
        'grp2': str(len(grp2)),
        'p': '', 'method': '', 'smd': '',
    })

    for section in config['sections']:
        # Section header
        rows.append({
            'variable': f"\u25ba  {section['header']}",
            'total': '', 'grp1': '', 'grp2': '', 'p': '', 'method': '', 'smd': '',
            'is_header': True,
        })

        for var in section['variables']:
            col = var['column']
            label = var['label']
            vtype = var['type']

            if col not in df.columns:
                rows.append({
                    'variable': label,
                    'total': 'COLUMN NOT FOUND',
                    'grp1': '', 'grp2': '', 'p': '', 'method': '', 'smd': '',
                })
                continue

            if vtype == 'continuous':
                t, g1, g2, p, meth, smd = continuous_stat(col, grp1, grp2, df, config)
                rows.append({
                    'variable': label, 'total': t,
                    'grp1': g1, 'grp2': g2, 'p': p, 'method': meth, 'smd': smd,
                })
            elif vtype == 'binary':
                # table1-A-2: pass per-variable event_value (default 1 for backcompat)
                event_value = var.get('event_value', 1)
                t, g1, g2, p, meth, smd = binary_stat(col, grp1, grp2, df, event_value)
                rows.append({
                    'variable': label, 'total': t,
                    'grp1': g1, 'grp2': g2, 'p': p, 'method': meth, 'smd': smd,
                })
            elif vtype == 'ordinal':
                label_map = var.get('label_map', None)
                ord_rows = ordinal_stat(col, grp1, grp2, df, label_map)
                for r in ord_rows:
                    rows.append(r)
            elif vtype == 'categorical':
                # table1-R1-2: nominal categorical (race / smoking type / medication class)
                # \u2014 RxC chi-square / Fisher fallback, per-level rendering
                label_map = var.get('label_map', None)
                cat_rows = categorical_stat(col, grp1, grp2, df, label_map)
                for r in cat_rows:
                    rows.append(r)

    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# Excel Output
# ═══════════════════════════════════════════════════════════════════════════════

def write_excel(rows, config, n_total, n_grp1, n_grp2):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    g1_label = config['grouping']['groups'][0]['label']
    g2_label = config['grouping']['groups'][1]['label']

    wb = Workbook()
    ws = wb.active
    ws.title = "Table 1"

    # Colour palette
    DARK_BLUE  = "1F3864"
    HEADER_BG  = "2E5FA3"
    SECTION_BG = "EBF2FA"
    ALT_ROW    = "F7FAFD"
    WHITE      = "FFFFFF"
    SIG_COLOR  = "C00000"

    thin  = Side(style='thin', color="BFBFBF")
    thick = Side(style='medium', color="2E5FA3")

    def thin_border():
        return Border(left=thin, right=thin, top=thin, bottom=thin)

    # Column widths — table1-A-3: added SMD column (7 cols total)
    col_widths = [40, 20, 20, 20, 10, 12, 14]
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # Row 1: Title
    ws.row_dimensions[1].height = 30
    ws.merge_cells("A1:G1")
    title_cell = ws["A1"]
    title_cell.value = config.get('title', 'Table 1. Baseline Characteristics')
    title_cell.font = Font(name="Arial", bold=True, size=13, color=WHITE)
    title_cell.fill = PatternFill("solid", fgColor=DARK_BLUE)
    title_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Row 2: Subtitle
    ws.row_dimensions[2].height = 18
    ws.merge_cells("A2:G2")
    sub_cell = ws["A2"]
    sub_cell.value = config.get('subtitle', '')
    sub_cell.font = Font(name="Arial", italic=True, size=10, color="4472C4")
    sub_cell.fill = PatternFill("solid", fgColor="EEF2FA")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")

    # Row 3: Column headers — table1-A-3: SMD between groups and p-value
    ws.row_dimensions[3].height = 36
    headers = [
        "Variable",
        f"Total\n(n={n_total})",
        f"{g1_label}\n(n={n_grp1})",
        f"{g2_label}\n(n={n_grp2})",
        "SMD",
        "p-value",
        "Method",
    ]
    for col_idx, hdr in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col_idx, value=hdr)
        cell.font = Font(name="Arial", bold=True, size=10, color=WHITE)
        cell.fill = PatternFill("solid", fgColor=HEADER_BG)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border()

    # Data rows
    excel_row = 4
    alt = False

    for row in rows:
        is_header = bool(row.get('is_header', False))
        ws.row_dimensions[excel_row].height = 18 if is_header else 16

        if is_header:
            ws.merge_cells(f"A{excel_row}:G{excel_row}")
            cell = ws.cell(row=excel_row, column=1, value=row['variable'])
            cell.font = Font(name="Arial", bold=True, size=10, color=DARK_BLUE)
            cell.fill = PatternFill("solid", fgColor=SECTION_BG)
            cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
            cell.border = Border(left=thick, right=thin, top=thick, bottom=thin)
            alt = False
        else:
            bg = ALT_ROW if alt else WHITE
            # table1-A-3: column order Variable / Total / G1 / G2 / SMD / p-value / Method
            values = [row['variable'], row['total'], row['grp1'], row['grp2'],
                      row.get('smd', '–'), row['p'], row['method']]
            for col_idx, val in enumerate(values, 1):
                cell = ws.cell(row=excel_row, column=col_idx, value=val)
                cell.font = Font(name="Arial", size=9.5)
                cell.fill = PatternFill("solid", fgColor=bg)
                cell.border = thin_border()
                if col_idx == 1:
                    cell.alignment = Alignment(horizontal="left", vertical="center", indent=1)
                else:
                    cell.alignment = Alignment(horizontal="center", vertical="center")

                # Highlight significant p-values (now in column 6)
                if col_idx == 6 and isinstance(val, str) and '*' in val:
                    cell.font = Font(name="Arial", size=9.5, bold=True, color=SIG_COLOR)

            alt = not alt

        excel_row += 1

    # Footnotes — A-3 SMD added 7th column, merge spans A:G
    excel_row += 1
    ws.row_dimensions[excel_row].height = 20
    ws.merge_cells(f"A{excel_row}:G{excel_row}")
    fn = ws.cell(row=excel_row, column=1)
    # table1-A-4: explicit "descriptive, not adjusted" disclaimer per medical journal convention
    # for Table 1; A-3 SMD column added (no significance test on SMD itself)
    fn.value = (
        "* p < 0.05 (statistically significant)  |  "
        "Continuous variables: Mean \u00b1 SD (normal distribution) or Median [IQR] (skewed)  |  "
        "Categorical variables: n (%)  |  "
        "SMD = standardized mean difference (Cohen's d for continuous, Cohen's h for binary)  |  "
        "Tests: Welch's t-test, Mann-Whitney U, Chi-square (incl. RxC), or Fisher's Exact as appropriate  |  "
        "p-values are descriptive (not adjusted for multiple comparisons)"
    )
    fn.font = Font(name="Arial", size=8, italic=True, color="595959")
    fn.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    if config.get('abbreviations'):
        excel_row += 1
        ws.row_dimensions[excel_row].height = 30
        ws.merge_cells(f"A{excel_row}:G{excel_row}")
        fn2 = ws.cell(row=excel_row, column=1)
        fn2.value = f"Abbreviations: {config['abbreviations']}"
        fn2.font = Font(name="Arial", size=8, italic=True, color="595959")
        fn2.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)

    # Freeze panes
    ws.freeze_panes = "A4"
    ws.print_title_rows = "1:3"

    # Save
    out_path = config['output_file']
    wb.save(out_path)
    return out_path


# ═══════════════════════════════════════════════════════════════════════════════
# CSV Output
# ═══════════════════════════════════════════════════════════════════════════════

def write_csv(rows, config, n_total, n_grp1, n_grp2):
    g1_label = config['grouping']['groups'][0]['label']
    g2_label = config['grouping']['groups'][1]['label']

    # table1-A-3: CSV column order matches Excel (SMD between groups and p-value)
    csv_rows = []
    for row in rows:
        if row.get('is_header'):
            csv_rows.append({
                'Variable': row['variable'],
                f'Total (n={n_total})': '',
                f'{g1_label} (n={n_grp1})': '',
                f'{g2_label} (n={n_grp2})': '',
                'SMD': '',
                'p-value': '',
                'Method': '',
            })
        else:
            csv_rows.append({
                'Variable': row['variable'],
                f'Total (n={n_total})': row['total'],
                f'{g1_label} (n={n_grp1})': row['grp1'],
                f'{g2_label} (n={n_grp2})': row['grp2'],
                'SMD': row.get('smd', '–'),
                'p-value': row['p'],
                'Method': row['method'],
            })

    csv_df = pd.DataFrame(csv_rows)
    csv_path = os.path.splitext(config['output_file'])[0] + '.csv'
    csv_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    return csv_path


# ═══════════════════════════════════════════════════════════════════════════════
# Listwise Deletion
# ═══════════════════════════════════════════════════════════════════════════════

def apply_listwise_deletion(df, config):
    """Drop rows with any missing value across all analyzed variables.

    table1-B-2: type-aware dropna. Previously force-coerced every analyzed column
    to numeric BEFORE dropna(), which silently turned binary 'Yes'/'No' or ordinal
    'Mild'/'Moderate' rows into NaN -> dropped. Now uses pd.dropna() on original
    dtype, which correctly preserves string-coded binary/ordinal values.
    """
    cols = []
    for section in config['sections']:
        for var in section['variables']:
            if var['column'] in df.columns:
                cols.append(var['column'])
    before = len(df)
    df = df.dropna(subset=cols)
    after = len(df)
    if before != after:
        print(f"Listwise deletion: {before} -> {after} rows ({before - after} removed)",
              file=sys.stderr)
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# Pre-write Validation & Summary (table1-D-3, table1-D-2)
# ═══════════════════════════════════════════════════════════════════════════════

def pre_write_validation(n_grp1, n_grp2, config):
    """table1-D-3: blocking validation BEFORE write_excel/write_csv.

    Currently checks per-group n >= 5 (sample size below this produces unreliable
    estimates). Returns True if any blocking issue found; caller should sys.exit(2)
    without writing artifacts so downstream consumers don't see "successful" output.
    """
    blocking = []
    g1_label = config['grouping']['groups'][0]['label']
    g2_label = config['grouping']['groups'][1]['label']
    if n_grp1 < 5:
        blocking.append(f"[QC_BLOCKING] Group '{g1_label}' has n={n_grp1} (< 5); too small for table1.")
    if n_grp2 < 5:
        blocking.append(f"[QC_BLOCKING] Group '{g2_label}' has n={n_grp2} (< 5); too small for table1.")
    for msg in blocking:
        print(msg, file=sys.stderr)
    return len(blocking) > 0


def write_summary_json(config, n_total, n_grp1, n_grp2, rows, qc_warnings, xlsx_path, csv_path):
    """table1-D-2: machine-readable summary for downstream manuscript-results consumption.

    Stable schema (schema_version 1.0) with sample sizes, significant variable count,
    skipped variables, and collected QC warnings. Path: same base as output_file with
    `_summary.json` suffix.
    """
    sig_count = sum(1 for r in rows if isinstance(r.get('p'), str) and '*' in r.get('p', ''))
    total_vars = sum(1 for r in rows
                     if not r.get('is_header') and r.get('variable') != 'n' and r.get('p'))
    skipped = [r['variable'] for r in rows if r.get('total') == 'COLUMN NOT FOUND']

    summary = {
        "schema_version": "1.0",
        "table1_summary": {
            "n_total": n_total,
            "n_group1": n_grp1,
            "n_group2": n_grp2,
            "group1_label": config['grouping']['groups'][0]['label'],
            "group2_label": config['grouping']['groups'][1]['label'],
            "total_variables_analyzed": total_vars,
            "significant_count": sig_count,
            "skipped_variables": skipped,
            "qc_warnings": qc_warnings,
        },
        "artifacts": {
            "xlsx": xlsx_path,
            "csv": csv_path,
        },
    }
    summary_path = os.path.splitext(config['output_file'])[0] + '_summary.json'
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary_path


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def _apply_academic_style():
    """academic-style integration (Wave 3, Excel-only). Consumes --style=<journal>
    from sys.argv; affects p-value / decimal formatting helpers if the skill
    imports them. No-op when skill not installed or flag absent."""
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
        print("Usage: python make_table1.py config.json [--check-missing] [--style=<journal>]")
        sys.exit(1)

    config = load_config(sys.argv[1])
    df = load_data(config)
    grp1, grp2 = split_groups(df, config)

    g1_label = config['grouping']['groups'][0]['label']
    g2_label = config['grouping']['groups'][1]['label']

    print(f"Data loaded: {len(df)} rows")
    print(f"  {g1_label}: n={len(grp1)}")
    print(f"  {g2_label}: n={len(grp2)}")

    if '--check-missing' in sys.argv:
        report = check_missing(df, grp1, grp2, config)
        print(f"\n{'='*80}")
        print("MISSING DATA REPORT")
        print(f"{'='*80}")
        print(report)
        sys.exit(0)

    # Apply listwise deletion if configured
    if config['missing_data_handling'] == 'listwise':
        df = apply_listwise_deletion(df, config)
        grp1, grp2 = split_groups(df, config)

    # Build table rows
    rows = build_rows(config, df, grp1, grp2)

    n_total = len(df)
    n_grp1 = len(grp1)
    n_grp2 = len(grp2)

    # table1-D-3: blocking validation BEFORE writing artifacts. If any blocking issue
    # surfaces, exit non-zero so pipeline doesn't see a "successful" file on disk.
    if pre_write_validation(n_grp1, n_grp2, config):
        sys.exit(2)

    # Write outputs
    xlsx_path = write_excel(rows, config, n_total, n_grp1, n_grp2)
    csv_path = write_csv(rows, config, n_total, n_grp1, n_grp2)

    # Summary
    sig_count = sum(1 for r in rows if isinstance(r.get('p'), str) and '*' in r.get('p', ''))
    total_vars = sum(1 for r in rows if not r.get('is_header') and r.get('variable') != 'n' and r.get('p'))

    print(f"\nTable 1 generated successfully!")
    print(f"  Total variables analyzed: {total_vars}")
    print(f"  Statistically significant (p<0.05): {sig_count}")
    print(f"  Excel output: {xlsx_path}")
    print(f"  CSV output:   {csv_path}")

    # ── Post-write QC warnings (non-blocking) ────────────────────────────────
    # table1-B-4: removed try/except: pass wrapper. QC checks must run; if a check
    # raises, surface it loudly rather than silently dropping all warnings.
    qc_warnings = []

    def _emit(msg):
        qc_warnings.append(msg)
        print(f"[QC_WARNING] {msg}", file=sys.stderr)

    # Check group sizes (warning, not blocking — blocking is < 5 in pre_write_validation)
    if n_grp1 < 30:
        _emit(f"Group '{g1_label}' has n={n_grp1} (< 30)")
    if n_grp2 < 30:
        _emit(f"Group '{g2_label}' has n={n_grp2} (< 30)")

    # Check for > 20% missing data in any variable
    for section in config['sections']:
        for var in section['variables']:
            col = var['column']
            if col in df.columns:
                n_miss = pd.to_numeric(df[col], errors='coerce').isna().sum()
                miss_pct = n_miss / len(df) * 100 if len(df) > 0 else 0
                if miss_pct > 20:
                    _emit(f"Variable '{var['label']}' has {miss_pct:.1f}% missing data (> 20%)")

    # Check for cell counts < 5 in binary variables
    for section in config['sections']:
        for var in section['variables']:
            col = var['column']
            vtype = var['type']
            if vtype == 'binary' and col in df.columns:
                event_value = var.get('event_value', 1)
                x1 = pd.to_numeric(grp1[col], errors='coerce')
                x2 = pd.to_numeric(grp2[col], errors='coerce')
                cells = [
                    (x1 == event_value).sum(), x1.notna().sum() - (x1 == event_value).sum(),
                    (x2 == event_value).sum(), x2.notna().sum() - (x2 == event_value).sum(),
                ]
                for cell_val in cells:
                    if cell_val < 5:
                        _emit(f"Variable '{var['label']}' has a cell count < 5 (value={int(cell_val)})")
                        break

    # table1-D-2: write machine-readable summary (manuscript-results consumes this)
    summary_path = write_summary_json(
        config, n_total, n_grp1, n_grp2, rows, qc_warnings, xlsx_path, csv_path
    )
    print(f"  Summary JSON: {summary_path}")


if __name__ == '__main__':
    main()
