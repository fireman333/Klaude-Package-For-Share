#!/usr/bin/env python3
"""Deterministic pre-flight / post-flight checks for a research_plan.json pipeline.

Why this exists
---------------
The guardian fan-out spent one LLM subagent per pipeline step re-deriving facts
that are set operations and arithmetic: does this column exist, is this event
column binary, is the reference level actually present, how many events per
fitted parameter. Those checks never need judgement, and a subagent that has to
read a 143-line checklist to perform `set(a) - set(b)` is the most expensive way
possible to compute a set difference.

This script performs them once. It replaces:

  COL-001  column existence            (config columns vs df.columns)
  COL-002  dtype alignment             (event binary / time numeric / cardinality)
  COL-003  role sanity + reference level present
  COL-005  post-filter n + missingness thresholds
  RES-001  numeric plausibility of reported estimates
  RES-002  analysis N vs flowchart final N
  RES-005  duplicate subject ids in any subject-level output
  RES-006  events per fitted parameter (EPV) — spline-aware
  RES-008  KM / CIF range, monotonicity, median-NR reason, CIF + survival <= 1
  RES-012  figure files present and not blank (file-level heuristic, not visual)
  RES-013  Table 1 internal consistency: column Ns, p-column presence, percentages
  RES-014  cross-language refit in R, escalating to an agent only on disagreement
  PSM direction anchor  (group label order + reciprocal-effect signature)
  success_criteria      (the mini-DSL in plan_template.md, actually evaluated)
  Stage Reflector rules (checkpoint_protocol.md), with the n-vs-events bug fixed

Two stages
----------
  --stage pre   runs before run_pipeline.py: everything computable from the plan,
                the generated configs and the dataset alone.
  --stage post  runs after run_pipeline.py: adds the checks that need outputs.
                It re-runs the pre checks too, because a config can be hand-edited
                between the two.

Output contract
---------------
Blocking and warning lines go to stderr with the same prefixes run_pipeline.py's
`extract_qc_warnings()` already collects:

    [QC_BLOCKING] COL-001 uni_primary: config column 'event_dth' not in dataset
    [QC_WARNING]  RES-006 multi_primary: EPV 7.3 below 10

A machine-readable copy is written to <output_dir>/precheck_report.json.

Exit codes (same convention as assets/check_freshness.py)
    0  every enabled check passed (warnings may still have been emitted)
    1  at least one blocking problem
    2  cannot run (missing plan / dataset / unreadable config)
"""
from __future__ import annotations

import argparse
import ast
import glob
import hashlib
import json
import math
import operator
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

def _cannot_run(message):
    """Report a condition that stops the check from running at all, and exit 2.

    Two things this must get right, both learned the hard way:

    - the exit code is 2, not 1. `sys.exit("some string")` prints the string and
      exits **1**, which callers read as "ran, found blocking problems" and then
      handle by counting `[QC_*]` lines. A bare `[FATAL]` line is not one of
      those, so the only line explaining the failure was dropped and the run was
      logged as `exit 1 — 0 blocking / 0 warning`. Confidently saying nothing is
      exactly the failure mode this module exists to remove.
    - the message carries the `[QC_BLOCKING]` prefix, so a caller that scans for
      findings rather than exit codes still sees it. Not being able to run is a
      blocking condition; it should look like one in both consumption styles.
    """
    print(f"[QC_BLOCKING] {message}", file=sys.stderr)
    sys.exit(2)


try:
    import pandas as pd
except ImportError:  # pragma: no cover - environment problem, must be loud
    _cannot_run("precheck_configs.py needs pandas: python3 -m pip install pandas")


# ─────────────────────────────────────────────────────────────────────────────
# Issue collection
# ─────────────────────────────────────────────────────────────────────────────

BLOCK = "block"
WARN = "warn"
INFO = "info"
UNKNOWN = "uncertain"

_SEVERITY_PREFIX = {
    BLOCK: "[QC_BLOCKING]",
    WARN: "[QC_WARNING]",
    UNKNOWN: "[QC_WARNING]",
    INFO: "[QC_INFO]",
}


class Report:
    """Collects issues, echoes them to stderr, serialises to JSON.

    Nothing here swallows anything: every issue is printed as it is added, so a
    crash later in the run still leaves the findings on the terminal.
    """

    def __init__(self, quiet=False):
        self.issues = []
        self.quiet = quiet
        self.counters = {"checks_run": 0, "checks_skipped": 0}
        self.skips = []

    def add(self, severity, check_id, step_id, message, evidence=None):
        issue = {
            "check_id": check_id,
            "severity": severity,
            "step_id": step_id,
            "message": message,
            "evidence": evidence or {},
        }
        self.issues.append(issue)
        if not self.quiet or severity in (BLOCK, WARN, UNKNOWN):
            prefix = _SEVERITY_PREFIX[severity]
            where = f" {step_id}" if step_id else ""
            print(f"{prefix} {check_id}{where}: {message}", file=sys.stderr)
        return issue

    def block(self, check_id, step_id, message, evidence=None):
        return self.add(BLOCK, check_id, step_id, message, evidence)

    def warn(self, check_id, step_id, message, evidence=None):
        return self.add(WARN, check_id, step_id, message, evidence)

    def unknown(self, check_id, step_id, message, evidence=None):
        return self.add(UNKNOWN, check_id, step_id, message, evidence)

    def info(self, check_id, step_id, message, evidence=None):
        return self.add(INFO, check_id, step_id, message, evidence)

    def ran(self, n=1):
        self.counters["checks_run"] += n

    def skipped(self, check_id, reason):
        """A check that could not run. Recorded, never silently dropped."""
        self.counters["checks_skipped"] += 1
        self.skips.append({"check_id": check_id, "reason": reason})
        print(f"  [SKIP] {check_id}: {reason}", file=sys.stderr)

    @property
    def n_blocking(self):
        return sum(1 for i in self.issues if i["severity"] == BLOCK)

    @property
    def n_warning(self):
        return sum(1 for i in self.issues if i["severity"] in (WARN, UNKNOWN))


# ─────────────────────────────────────────────────────────────────────────────
# success_criteria mini-DSL evaluator  (RES-004)
# ─────────────────────────────────────────────────────────────────────────────
#
# plan_template.md:236-265 defines checks as machine-readable expressions:
#     {"check": "events_per_group >= 1", "severity": "blocking"}
#     {"check": "model_converged == true", "severity": "blocking"}
#     {"check": "ci_width < 100",         "severity": "warning"}
# Until now nothing parsed them; an LLM read them off the page. This evaluator
# is deliberately not eval()/exec(): the grammar is one comparison, the operator
# table is a fixed whitelist and every literal goes through ast.literal_eval.

_COMPARATORS = {
    ">=": operator.ge,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    "<": operator.lt,
}

_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_COMPARISON_RE = re.compile(rf"^\s*({_IDENT})\s*(>=|<=|==|!=|>|<)\s*(.+?)\s*$")
_BARE_RE = re.compile(rf"^\s*({_IDENT})\s*$")

# Evaluation outcomes.
EVAL_PASS = "pass"
EVAL_FAIL = "fail"
EVAL_UNKNOWN = "unknown"      # metric not available in this stage
EVAL_UNPARSABLE = "unparsable"


def _parse_literal(token):
    """Parse the right-hand side of a criterion.

    Returns (kind, value) where kind is 'literal' or 'name'. Raises ValueError
    when the token is neither a Python literal nor a bare identifier — an
    unparsable criterion is reported, never treated as a pass.
    """
    low = token.strip().lower()
    if low in ("true", "false"):
        return "literal", (low == "true")
    if low in ("null", "none"):
        return "literal", None
    try:
        return "literal", ast.literal_eval(token)
    except (ValueError, SyntaxError):
        pass
    if _BARE_RE.match(token):
        return "name", token.strip()
    raise ValueError(f"cannot parse right-hand side {token!r}")


def evaluate_criterion(expr, metrics):
    """Evaluate one success_criteria `check` string against a metrics dict.

    Returns (outcome, detail). `metrics` maps metric name -> value; a missing or
    None value yields EVAL_UNKNOWN so the caller can say "not evaluated" rather
    than quietly passing.
    """
    if not isinstance(expr, str) or not expr.strip():
        return EVAL_UNPARSABLE, "empty criterion"

    bare = _BARE_RE.match(expr)
    if bare:
        name = bare.group(1)
        if name not in metrics or metrics[name] is None:
            return EVAL_UNKNOWN, f"{name} unavailable"
        value = metrics[name]
        return (EVAL_PASS if bool(value) else EVAL_FAIL), f"{name}={value!r}"

    m = _COMPARISON_RE.match(expr)
    if not m:
        return EVAL_UNPARSABLE, f"not a single comparison: {expr!r}"
    lhs_name, op_token, rhs_token = m.group(1), m.group(2), m.group(3)

    # Validity is established before availability. Checking the left-hand metric
    # first let a malformed criterion be reported as "metric unavailable" — a
    # temporary, stage-dependent excuse — when it is in fact permanently
    # unevaluable. `smd_max < 0.1 and matched_pairs >= 50` matched the comparison
    # pattern with a right-hand side of `0.1 and matched_pairs >= 50`, and said
    # "smd_max unavailable".
    try:
        kind, rhs = _parse_literal(rhs_token)
    except ValueError as exc:
        return EVAL_UNPARSABLE, str(exc)

    if lhs_name not in metrics or metrics[lhs_name] is None:
        return EVAL_UNKNOWN, f"{lhs_name} unavailable"
    lhs = metrics[lhs_name]

    if kind == "name":
        if rhs not in metrics or metrics[rhs] is None:
            return EVAL_UNKNOWN, f"{rhs} unavailable"
        rhs = metrics[rhs]

    func = _COMPARATORS[op_token]
    try:
        ok = bool(func(lhs, rhs))
    except TypeError as exc:
        return EVAL_UNPARSABLE, f"{lhs!r} {op_token} {rhs!r}: {exc}"
    return (EVAL_PASS if ok else EVAL_FAIL), f"{lhs_name}={lhs!r} {op_token} {rhs!r}"


# ─────────────────────────────────────────────────────────────────────────────
# Plan / config / data loading
# ─────────────────────────────────────────────────────────────────────────────

_TIME_TO_EVENT_TYPES = ("time_to_event", "time-to-event", "competing_risk", "competing-risk")


def _norm_outcome_type(t):
    if t in ("time_to_event", "time-to-event"):
        return "time_to_event"
    if t in ("competing_risk", "competing-risk"):
        return "competing_risk"
    if t == "binary":
        return "binary"
    raise ValueError(f"Unknown outcome type: {t!r}")


def load_json(path, what):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        _cannot_run(f"{what} not found: {path}")
    except json.JSONDecodeError as exc:
        _cannot_run(f"{what} is not valid JSON ({path}): {exc}")


def load_dataframe(path):
    """Read the analysis dataset. Extension-driven, same rules as the sub-skills."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if ext == ".tsv":
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def all_outcomes(plan):
    outcomes = plan.get("outcomes") or {}
    result = []
    if outcomes.get("primary"):
        result.append(outcomes["primary"])
    result.extend(outcomes.get("secondary") or [])
    return result


def derived_variable_names(plan):
    """Names produced at runtime by the sub-skills, so absent from the raw file."""
    return {d.get("name") for d in (plan.get("derived_variables") or []) if d.get("name")}


def apply_population(df, plan, report):
    """Apply population.filters[] then population.exclusion_steps[].

    Returns (filtered_df, ok). Filter failures are reported, not swallowed: an
    unapplied filter means every downstream n is wrong and saying so matters
    more than producing a number.
    """
    pop = plan.get("population") or {}
    out = df
    ok = True

    ops = {
        "==": lambda s, v: s == v,
        "!=": lambda s, v: s != v,
        ">": lambda s, v: s > v,
        ">=": lambda s, v: s >= v,
        "<": lambda s, v: s < v,
        "<=": lambda s, v: s <= v,
        "in": lambda s, v: s.isin(v if isinstance(v, (list, tuple)) else [v]),
        "not_in": lambda s, v: ~s.isin(v if isinstance(v, (list, tuple)) else [v]),
    }

    for f in pop.get("filters") or []:
        col, op, val = f.get("column"), f.get("operator"), f.get("value")
        if col not in out.columns:
            report.block("COL-001", None,
                         f"population filter references missing column {col!r}",
                         {"filter": f})
            ok = False
            continue
        if op not in ops:
            report.block("COL-001", None,
                         f"population filter uses unsupported operator {op!r}",
                         {"filter": f})
            ok = False
            continue
        try:
            out = out[ops[op](out[col], val)]
        except Exception as exc:  # surfaced, never silent
            report.block("COL-005", None,
                         f"population filter {col!r} {op} {val!r} raised {type(exc).__name__}: {exc}",
                         {"filter": f})
            ok = False

    for step in pop.get("exclusion_steps") or []:
        expr = step.get("keep_condition") or step.get("condition")
        if not expr:
            report.block("COL-005", None,
                         f"exclusion step {step.get('description')!r} declares neither "
                         f"`condition` nor `keep_condition`; the rows it is supposed to "
                         f"remove would stay in the cohort",
                         {"step": step})
            ok = False
            continue
        keep = "keep_condition" in step and step.get("keep_condition")
        try:
            selected = out.query(expr)
        except Exception as exc:
            # An exclusion that does not apply is not a smaller inconvenience
            # than a wrong one: the patients it was meant to remove stay in, and
            # every N, missingness rate and EPV computed afterwards describes a
            # cohort nobody planned.
            report.block("COL-005", None,
                         f"exclusion step {step.get('description')!r} could not be applied "
                         f"({type(exc).__name__}: {exc}); the rows it should have removed "
                         f"are still in the cohort",
                         {"expression": expr})
            ok = False
            continue
        out = selected if keep else out.drop(selected.index)

    return out, ok


# ─────────────────────────────────────────────────────────────────────────────
# Parameter budget (EPV denominator) — spline aware
# ─────────────────────────────────────────────────────────────────────────────

def _spline_variables(plan):
    adv = (plan.get("advanced_analyses") or {}).get("nonlinearity") or {}
    if not adv.get("enabled"):
        return {}, 0
    knots = int(adv.get("knots") or 4)
    knot_percentiles = adv.get("knot_percentiles")
    if isinstance(knot_percentiles, (list, tuple)) and knot_percentiles:
        knots = len(knot_percentiles)
    # A restricted cubic spline on k knots contributes k-1 parameters
    # (the linear term plus k-2 spline basis terms).
    return {v for v in (adv.get("variables") or [])}, max(knots - 1, 1)


UNPRICED_CATEGORICAL = "categorical with undeclared levels"


def _term_cost(col, ctype, df, spline_vars, spline_params, label_map=None):
    """Parameters one model term costs.

    Returns (cost, kind, unpriced_reason). `unpriced_reason` is None when the
    cost is exact, and a string when `cost` is only a FLOOR — which happens for
    a categorical whose level count cannot be established (no `label_map`, and
    no dataframe column to count from). Such a term costs L-1 parameters for
    some unknown L >= 2, so 1 is a lower bound, not an estimate.

    The floor is returned rather than a worst case on purpose. Callers price the
    unknown themselves, because they are not exposed to it symmetrically: the
    EPV gate blocks and so must not over-charge, while the auto-RCS gate grants
    a spline and so must not under-charge. Burying a worst case here would make
    the blocking gate over-conservative everywhere — which is the defect this
    module just finished removing from the EPV numerator.
    """
    if col in spline_vars:
        return spline_params, f"rcs({spline_params + 1} knots)", None
    if ctype == "continuous":
        return 1, "continuous", None
    if ctype == "binary":
        return 1, "binary", None
    levels = None
    if label_map:
        levels = len(label_map)
    elif df is not None and col in df.columns:
        levels = int(df[col].dropna().nunique())
    if levels is None:
        return 1, f"{ctype or 'categorical'}(levels unknown)", UNPRICED_CATEGORICAL
    return max(levels - 1, 1), f"{ctype or 'categorical'}({levels} levels)", None


def _adjusted_model_config(configs, outcome_id):
    """The generated config for the fully adjusted model of one outcome.

    That is the model the EPV gate is about. Univariate configs fit one term at
    a time and carry the same `sections`, so they are not a substitute.
    """
    if not configs:
        return None, None
    preferred = [("multivariate-interaction", f"multi_{outcome_id}")]
    for _skill, step_id in preferred:
        if step_id in configs:
            return step_id, configs[step_id]
    for step_id, cfg in configs.items():
        if step_id.startswith("multi_") and cfg.get("sections"):
            return step_id, cfg
    return None, None


def parameter_budget(plan, df=None, configs=None, outcome_id=None):
    """Parameters the fully adjusted model fits — the EPV denominator.

    Returns (total, breakdown, provenance).

    **`total` is a LOWER BOUND, not an exact count.** Every term whose cost could
    not be established exactly is charged its floor and listed in
    `provenance["unpriced_terms"]` as
    `{"column": ..., "reason": ..., "floor": ...}`. When that list is non-empty
    the true parameter count is >= `total`, and therefore **any EPV computed as
    events / total is an UPPER BOUND** — the real EPV can only be lower. Callers
    must read `unpriced_terms` and decide what that means for them; the two
    existing callers are not exposed symmetrically:

      - the EPV gate blocks, so an upper bound already below the threshold is
        conclusive (block), while an upper bound above it is not (warn);
      - the auto-RCS gate grants degrees of freedom, so it must not spend a
        budget that may not exist (withhold the spline unless the worst case
        still clears).

    Pricing the unknown here, in one direction, would silently impose one of
    those postures on both.

    This is a *parameter* count, not a variable count: an RCS on k knots costs
    k-1 and a categorical with L levels costs L-1. Counting variables is how a
    15-parameter model gets recorded as 8.

    The count is taken from the generated config when one is available, because
    that is the object the sub-skill actually fits: a hand-edited config, or an
    interaction term, changes the real degrees of freedom while `plan.covariates`
    stays put. When no config can be read the plan-level count is used and the
    provenance says so — an approximate denominator is worth more than a refusal
    to compute one, so this never blocks by itself.
    """
    spline_vars, spline_params = _spline_variables(plan)

    def count_from_variables(variables, grouping):
        breakdown, unpriced, total = [], [], 0
        n_groups = len(((grouping or {}).get("groups")) or [])
        if n_groups >= 2:
            cost = n_groups - 1
            total += cost
            breakdown.append({"term": (grouping or {}).get("column"), "role": "exposure",
                              "type": "categorical", "params": cost})
        for var in variables:
            col = var.get("column")
            cost, kind, unpriced_reason = _term_cost(
                col, var.get("type"), df, spline_vars, spline_params, var.get("label_map"))
            total += cost
            entry = {"term": col, "role": "covariate", "type": kind, "params": cost}
            if unpriced_reason:
                entry["is_floor"] = True
                unpriced.append({"column": col, "reason": unpriced_reason, "floor": cost})
            breakdown.append(entry)
        return total, breakdown, unpriced

    plan_total, plan_breakdown, plan_unpriced = count_from_variables(
        [{"column": c.get("column"), "type": c.get("type"), "label_map": c.get("label_map")}
         for c in plan.get("covariates") or []],
        plan.get("grouping"))

    step_id, config = _adjusted_model_config(configs, outcome_id)
    if not config or not config.get("sections"):
        return plan_total, plan_breakdown, {
            "source": "plan",
            "step_id": step_id,
            "plan_total": plan_total,
            "unpriced_terms": plan_unpriced,
            "note": ("counted from plan.covariates; no adjusted-model config was "
                     "available, so hand-edited terms and interactions are not included"),
        }

    variables = [v for section in config["sections"] for v in (section.get("variables") or [])]
    total, breakdown, unpriced = count_from_variables(
        variables, config.get("grouping") or plan.get("grouping"))

    # An interaction model is a separate fit per variable, so the binding
    # constraint is the main model plus the most expensive single interaction.
    note = None
    if config.get("interaction_variables"):
        wanted = config["interaction_variables"]
        candidates = variables if wanted == "all" else [
            v for v in variables if v.get("column") in (wanted or [])]
        n_groups = len(((config.get("grouping") or plan.get("grouping") or {})
                        .get("groups")) or [])
        worst, worst_col, worst_unpriced = 0, None, None
        for var in candidates:
            cost, _kind, unpriced_reason = _term_cost(
                var.get("column"), var.get("type"), df, spline_vars, spline_params,
                var.get("label_map"))
            df_cost = cost * max(n_groups - 1, 1)
            if df_cost > worst:
                worst, worst_col, worst_unpriced = df_cost, var.get("column"), unpriced_reason
        if worst:
            total += worst
            entry = {"term": f"{worst_col} x exposure", "role": "interaction",
                     "type": "interaction", "params": worst}
            if worst_unpriced:
                entry["is_floor"] = True
                unpriced.append({"column": f"{worst_col} x exposure",
                                 "reason": worst_unpriced, "floor": worst})
            breakdown.append(entry)
            note = (f"includes the most expensive single interaction term "
                    f"({worst_col} x exposure, {worst} df); interaction models are "
                    f"fitted one at a time")

    return total, breakdown, {
        "source": "config",
        "step_id": step_id,
        "plan_total": plan_total,
        "config_total": total,
        "drift": total - plan_total,
        "unpriced_terms": unpriced,
        "note": note,
    }


def group_masks(df, plan):
    """Yield (label, boolean mask) for every declared analysis group."""
    grouping = plan.get("grouping") or {}
    col = grouping.get("column")
    if not col or col not in df.columns:
        return []
    out = []
    series = df[col]
    numeric = pd.to_numeric(series, errors="coerce")
    for g in grouping.get("groups") or []:
        val = g.get("value")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            mask = numeric == val
        else:
            mask = series.astype(str) == str(val)
        out.append((g.get("label", str(val)), mask))
    return out


def events_by_group(df, plan, outcome):
    """Event counts per analysis group for one outcome. {} when uncomputable."""
    ev_col = outcome.get("event_column")
    if not ev_col or ev_col not in df.columns:
        return {}
    ev = pd.to_numeric(df[ev_col], errors="coerce")
    counts = {}
    for label, mask in group_masks(df, plan):
        counts[label] = int(((ev == 1) & mask).sum())
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# PRE-stage checks
# ─────────────────────────────────────────────────────────────────────────────

_ROLE_COLUMN_KEYS = (
    "time_column", "event_column", "outcome_column", "competing_event_column",
    "cluster_column", "exposure_time_column",
)


def config_columns(config):
    """Every dataset column a generated config references, with its role."""
    found = []

    def add(col, role):
        if isinstance(col, str) and col:
            found.append((col, role))

    for key in _ROLE_COLUMN_KEYS:
        add(config.get(key), key)
    for sub in ("cox_settings", "logistic_settings"):
        block = config.get(sub)
        if isinstance(block, dict):
            for key in _ROLE_COLUMN_KEYS:
                add(block.get(key), f"{sub}.{key}")
    grouping = config.get("grouping")
    if isinstance(grouping, dict):
        add(grouping.get("column"), "grouping.column")
    group_split = config.get("group_split")
    if isinstance(group_split, dict):
        add(group_split.get("column"), "group_split.column")
    for section_key in ("sections", "matching_variables"):
        for section in config.get(section_key) or []:
            for var in (section or {}).get("variables") or []:
                add(var.get("column"), f"{section_key}.variables")
    for oc in config.get("outcomes") or []:
        if isinstance(oc, dict):
            for key in ("event_column", "time_column", "outcome_column"):
                add(oc.get(key), f"outcomes.{key}")
    for f in config.get("filters") or []:
        if isinstance(f, dict):
            add(f.get("column"), "filters.column")
    return found


def check_col001(report, plan, configs, df):
    """COL-001 — every config column exists in the dataset."""
    known = set(df.columns) | derived_variable_names(plan)
    lower = {c.lower(): c for c in df.columns}
    for step_id, config in configs.items():
        for col, role in config_columns(config):
            report.ran()
            if col in known:
                continue
            near = lower.get(col.lower())
            hint = f" (did you mean {near!r}?)" if near else ""
            report.block("COL-001", step_id,
                         f"config column {col!r} ({role}) is not in the dataset{hint}",
                         {"column": col, "role": role})


def check_col002_col003(report, plan, configs, df):
    """COL-002 dtype alignment and COL-003 role sanity / reference levels."""
    derived = derived_variable_names(plan)

    # Outcome columns, from the plan (the configs only carry them indirectly).
    for outcome in all_outcomes(plan):
        oid = outcome.get("id")
        try:
            otype = _norm_outcome_type(outcome.get("type"))
        except ValueError as exc:
            report.block("COL-002", oid, str(exc), {"outcome": oid})
            continue

        ev_col = outcome.get("event_column")
        if ev_col and ev_col in df.columns:
            report.ran()
            values = pd.to_numeric(df[ev_col], errors="coerce").dropna()
            uniq = sorted(set(values.unique().tolist()))
            if not values.dropna().isin({0, 1}).all():
                if otype == "competing_risk" and set(uniq) <= {0, 1, 2}:
                    report.info("COL-002", oid,
                                f"event column {ev_col!r} codes {uniq} — read as competing risk",
                                {"unique": uniq})
                else:
                    report.block("COL-002", oid,
                                 f"event column {ev_col!r} is not binary; unique values {uniq[:10]}",
                                 {"column": ev_col, "unique": uniq[:10]})
        elif ev_col and ev_col not in derived:
            report.block("COL-002", oid, f"event column {ev_col!r} is not in the dataset")

        t_col = outcome.get("time_column")
        if otype in ("time_to_event", "competing_risk"):
            if not t_col:
                report.block("COL-002", oid, f"outcome type {otype} has no time_column")
            elif t_col in df.columns:
                report.ran()
                if not pd.api.types.is_numeric_dtype(df[t_col]):
                    coerced = pd.to_numeric(df[t_col], errors="coerce")
                    if coerced.notna().sum() == 0:
                        report.block("COL-002", oid,
                                     f"time column {t_col!r} is not numeric (dtype {df[t_col].dtype})")
                    else:
                        report.warn("COL-002", oid,
                                    f"time column {t_col!r} has dtype {df[t_col].dtype}; "
                                    f"{int(coerced.isna().sum())} value(s) will not coerce")
                elif (df[t_col].dropna() < 0).any():
                    report.block("COL-002", oid, f"time column {t_col!r} contains negative values")

    # Grouping column cardinality.
    grouping = plan.get("grouping") or {}
    gcol = grouping.get("column")
    if gcol and gcol in df.columns:
        report.ran()
        nu = int(df[gcol].dropna().nunique())
        if nu < 2:
            report.block("COL-002", None, f"grouping column {gcol!r} has {nu} distinct value(s)")
        elif nu > 20:
            report.warn("COL-002", None,
                        f"grouping column {gcol!r} has {nu} distinct values (expected a small set)")
        declared = [g.get("value") for g in grouping.get("groups") or []]
        present = set(pd.to_numeric(df[gcol], errors="coerce").dropna().unique().tolist())
        present |= set(df[gcol].dropna().astype(str).unique().tolist())
        for val in declared:
            if val not in present and str(val) not in present:
                report.block("COL-003", None,
                             f"grouping value {val!r} does not occur in {gcol!r}",
                             {"declared": declared})

    # Covariate role sanity + reference levels.
    for cov in plan.get("covariates") or []:
        col = cov.get("column")
        if not col or col not in df.columns:
            continue
        report.ran()
        series = df[col].dropna()
        nu = int(series.nunique())
        ctype = cov.get("type")
        if ctype == "continuous":
            if not pd.api.types.is_numeric_dtype(df[col]):
                report.block("COL-002", None,
                             f"covariate {col!r} declared continuous but dtype is {df[col].dtype}")
            elif nu <= 5:
                report.warn("COL-003", None,
                            f"covariate {col!r} declared continuous but has only {nu} distinct values")
        elif ctype in ("binary", "ordinal", "categorical"):
            if nu > 20:
                report.warn("COL-003", None,
                            f"covariate {col!r} declared {ctype} but has {nu} distinct values")
            if ctype == "binary" and nu > 2:
                report.block("COL-002", None,
                             f"covariate {col!r} declared binary but has {nu} distinct values")

        ref = cov.get("reference")
        if ref is not None:
            report.ran()
            present = set(series.unique().tolist()) | {str(v) for v in series.unique().tolist()}
            numeric_present = set(pd.to_numeric(series, errors="coerce").dropna().unique().tolist())
            if ref not in present and str(ref) not in present and ref not in numeric_present:
                report.block("COL-003", None,
                             f"reference level {ref!r} for {col!r} does not occur in the data",
                             {"observed": [str(v) for v in list(series.unique())[:10]]})


def check_col005(report, plan, df_raw, df_filtered):
    """COL-005 — post-filter n and missingness thresholds."""
    pop = plan.get("population") or {}
    min_n = pop.get("min_n", 30)
    n = len(df_filtered)
    report.ran()
    if n < min_n:
        report.block("COL-005", None,
                     f"cohort after filters is n={n}, below min_n={min_n} "
                     f"(raw file had {len(df_raw)} rows)")
    else:
        report.info("COL-005", None,
                    f"cohort after filters n={n} of {len(df_raw)} raw rows")

    # Bands are stated as closed intervals rather than as ">N%", because those are
    # not the same claim. The top message used to read "(>50%)" while its
    # condition was `miss >= 0.60`, so a covariate at 55% landed in the 40% band
    # and a reader could conclude, from the absence of any ">50%" line, that 50%
    # had been tested and cleared. It had not been. This check's tiers are
    # 20/40/60 (missing_data_protocol.md:48); the 50% rule lives in the Stage
    # Reflector, where it asks a different question — "should the plan change"
    # rather than "is this worth saying before anything runs". The differing
    # thresholds are deliberate (ibid.:41); a message implying a threshold this
    # check does not have was the defect.
    for cov in plan.get("covariates") or []:
        col = cov.get("column")
        if not col or col not in df_filtered.columns:
            continue
        report.ran()
        miss = float(df_filtered[col].isna().mean())
        if miss < 0.20:
            continue
        if cov.get("allow_high_missing") and miss >= 0.40:
            # Previously this fell through to the 20% branch, so a 65%-missing
            # column with the flag set was announced as "(>20%)".
            report.info("COL-005", None,
                        f"covariate {col!r} is {miss:.1%} missing; allow_high_missing "
                        f"is set for it, so no warning is raised")
            continue
        if miss >= 0.60:
            report.warn("COL-005", None,
                        f"covariate {col!r} is {miss:.1%} missing (>=60%): requires a "
                        f"justified sensitivity analysis, not silent removal")
        elif miss >= 0.40:
            report.warn("COL-005", None,
                        f"covariate {col!r} is {miss:.1%} missing (40-60%): MI remains "
                        f"usable but the imputed values lean heavily on the model; "
                        f"consider removing the variable or sourcing it elsewhere")
        else:
            report.warn("COL-005", None,
                        f"covariate {col!r} is {miss:.1%} missing (20-40%): "
                        f"consider multiple imputation or removal")

    for outcome in all_outcomes(plan):
        for key in ("event_column", "time_column"):
            col = outcome.get(key)
            if not col or col not in df_filtered.columns:
                continue
            report.ran()
            miss = float(df_filtered[col].isna().mean())
            if miss > 0.05:
                report.block("COL-005", outcome.get("id"),
                             f"outcome column {col!r} is {miss:.1%} missing (>5%)")


def _analysis_set_size(df, plan, outcome):
    """Rows in a declared analysis group with an observed outcome value."""
    ev_col = outcome.get("event_column")
    if not ev_col or ev_col not in df.columns:
        return 0
    observed = pd.to_numeric(df[ev_col], errors="coerce").notna()
    in_group = None
    for _label, mask in group_masks(df, plan):
        in_group = mask if in_group is None else (in_group | mask)
    if in_group is None:
        return int(observed.sum())
    return int((observed & in_group).sum())


def check_epv(report, plan, df_filtered, stage, configs=None):
    """RES-006 / EPV — events per fitted parameter, spline aware.

    Numerator: outcome events in the whole fitted analysis set, which is what
    every published EPV rule means (Peduzzi 1996, Concato/Peduzzi 1995,
    Riley 2019); for a logistic outcome it is min(events, non-events). An
    earlier version of this function used the *smallest exposure group's* event
    count, which is not any standard definition and blocks a perfectly
    estimable model whenever the groups are unbalanced: 8 vs 300 events over 2
    parameters scored EPV 4.0 and blocked, while the model's real EPV is 154.

    The intuition behind that mistake was still worth something — with 8 events
    in one arm the *exposure coefficient* really is fragile — but that is
    sparse-data bias (Greenland 2016), not EPV, and it is reported separately
    below as RES-006b so it cannot masquerade as a fatal gate.
    """
    results = {}
    for outcome in all_outcomes(plan):
        oid = outcome.get("id")
        counts = events_by_group(df_filtered, plan, outcome)
        if not counts:
            report.skipped("RES-006", f"outcome {oid}: event column unavailable at stage={stage}")
            continue

        n_params, breakdown, provenance = parameter_budget(
            plan, df_filtered, configs, oid)
        if n_params == 0:
            report.skipped("RES-006",
                           f"outcome {oid}: no covariates or exposure declared; "
                           f"no parameter budget")
            continue
        if provenance["source"] == "plan":
            report.unknown("RES-006", oid,
                           f"the parameter budget was approximated from plan.covariates "
                           f"({n_params} parameters): {provenance['note']}. EPV below is "
                           f"an estimate, not a reading of the fitted model",
                           provenance)
        elif provenance.get("drift"):
            report.warn("RES-006", oid,
                        f"the adjusted-model config fits {provenance['config_total']} "
                        f"parameters but plan.covariates implies "
                        f"{provenance['plan_total']}; the config has been edited or "
                        f"carries interaction terms. EPV uses the config",
                        provenance)

        total_events = sum(counts.values())
        min_events = min(counts.values())
        n_analysis = _analysis_set_size(df_filtered, plan, outcome)
        try:
            otype = _norm_outcome_type(outcome.get("type"))
        except ValueError:
            otype = "time_to_event"

        if otype == "binary" and n_analysis:
            effective = min(total_events, n_analysis - total_events)
            basis = (f"min(events, non-events) = min({total_events}, "
                     f"{n_analysis - total_events})")
        else:
            effective = total_events
            basis = f"{total_events} events in the analysis set"

        report.ran()
        epv = effective / n_params
        # `n_params` is a lower bound whenever terms could not be priced, so this
        # EPV is an UPPER bound: the real one can only be smaller. That asymmetry
        # decides both branches below, and it is stated here rather than absorbed
        # into the denominator because the other consumer of parameter_budget
        # (the auto-RCS gate) needs the opposite posture from the same number.
        unpriced = provenance.get("unpriced_terms") or []
        bound = "upper bound on EPV" if unpriced else "EPV"
        results[oid] = {
            "events_by_group": counts,
            "total_events": total_events,
            "min_group_events": min_events,
            "analysis_set_n": n_analysis,
            "effective_events": effective,
            "numerator_basis": basis,
            "n_fitted_params": n_params,
            "n_fitted_params_is_lower_bound": bool(unpriced),
            "epv": round(epv, 2),
            "epv_is_upper_bound": bool(unpriced),
            "parameter_breakdown": breakdown,
            "parameter_source": provenance,
        }
        evidence = {"events_by_group": counts, "effective_events": effective,
                    "numerator_basis": basis, "n_fitted_params": n_params,
                    "epv": round(epv, 2), "parameter_source": provenance["source"],
                    "unpriced_terms": unpriced}
        unpriced_note = ""
        if unpriced:
            names = ", ".join(u["column"] for u in unpriced)
            unpriced_note = (f" {len(unpriced)} term(s) could not be priced ({names}), "
                             f"so {n_params} parameters is a lower bound and this EPV is "
                             f"an upper bound")
        if epv < 5:
            # Safe in both directions: if even the upper bound is under 5, the
            # true EPV is under 5 too. Unpriced terms can only strengthen this.
            report.block("RES-006", oid,
                         f"{bound} {epv:.1f} ({basis} / {n_params} fitted parameters) is "
                         f"below 5 — the adjusted model is not estimable at this size."
                         f"{unpriced_note}", evidence)
        elif epv < 10:
            report.warn("RES-006", oid,
                        f"{bound} {epv:.1f} ({basis} / {n_params} fitted parameters) is "
                        f"below 10; reduce the parameter budget or pre-specify "
                        f"penalisation. EPV 10 is a floor, not a certificate."
                        f"{unpriced_note}", evidence)
        elif unpriced:
            # The upper bound clears the threshold, which says nothing about the
            # true value. Not knowing whether a gate is passed is not the same as
            # failing it, so this warns rather than blocks.
            report.warn("RES-006", oid,
                        f"upper bound on EPV {epv:.1f} ({effective}/{n_params}) clears "
                        f"10, but the true EPV may be lower and cannot be computed —"
                        f"{unpriced_note}. Declare the levels of those variables "
                        f"(covariates[].label_map) to settle it", evidence)
        else:
            report.info("RES-006", oid,
                        f"EPV {epv:.1f} ({effective}/{n_params}, {basis})", evidence)

        # RES-006b — the sparse-cell problem, under its own name.
        if min_events < 10:
            report.ran()
            report.warn("RES-006b", oid,
                        f"the smallest exposure group has {min_events} event(s) "
                        f"({counts}). Total events are sufficient for the model as a "
                        f"whole (EPV {epv:.1f}), but the *exposure* coefficient is "
                        f"limited by the sparse arm and is prone to sparse-data bias; "
                        f"consider Firth penalisation or a combined endpoint. This is "
                        f"not a blocking condition",
                        {"events_by_group": counts, "min_group_events": min_events})
    return results


def check_stage_reflector(report, plan, df_filtered, epv_results):
    """checkpoint_protocol.md:122-169 rules, implemented for the first time.

    The EPV rule (row 1 of that table) is triggered by EPV, not by `Any group
    n < 30` as written; the original condition and its rule-of-10 formula
    disagreed. Small-sample n is kept as its own, separate observation so the
    fix does not lose information.
    """
    suggestions = []

    sizes = {label: int(mask.sum()) for label, mask in group_masks(df_filtered, plan)}
    if sizes:
        report.ran()
        smallest, largest = min(sizes.values()), max(sizes.values())
        if smallest > 0 and largest / smallest > 5:
            msg = (f"group sizes {sizes} are more imbalanced than 1:5 "
                   f"({largest}/{smallest} = {largest / smallest:.1f}); consider PSM or IPW")
            report.warn("REFLECT-imbalance", None, msg, {"group_sizes": sizes})
            suggestions.append(msg)
        if smallest < 30:
            msg = (f"smallest group n={smallest} (<30). This is a precision observation only; "
                   f"the covariate budget is governed by EPV, see RES-006")
            report.warn("REFLECT-small-n", None, msg, {"group_sizes": sizes})
            suggestions.append(msg)

    for outcome in all_outcomes(plan):
        oid = outcome.get("id")
        counts = events_by_group(df_filtered, plan, outcome)
        if not counts:
            continue
        report.ran()
        if min(counts.values()) < 5:
            msg = (f"outcome {oid!r} has {min(counts.values())} event(s) in the smallest group "
                   f"(<5); consider dropping it or merging into a composite endpoint")
            report.warn("REFLECT-events", oid, msg, {"events_by_group": counts})
            suggestions.append(msg)

    for oid, res in (epv_results or {}).items():
        if res["epv"] < 10:
            max_cov = max(int(res["effective_events"] // 10), 0)
            msg = (f"outcome {oid!r}: EPV {res['epv']} — rule of 10 allows about {max_cov} "
                   f"fitted parameters, the model fits {res['n_fitted_params']}")
            report.warn("REFLECT-epv", oid, msg, res)
            suggestions.append(msg)

    for cov in plan.get("covariates") or []:
        col = cov.get("column")
        if not col or col not in df_filtered.columns:
            continue
        miss = float(df_filtered[col].isna().mean())
        # These used to be appended to `suggestions` only, which reaches
        # precheck_report.json and nothing else. The 50% tier that
        # missing_data_protocol.md defines therefore existed in the program but
        # never appeared on the surface anyone reads — and COL-005's bands stop
        # at 40 and resume at 60, so between those two facts a covariate at 55%
        # produced no line mentioning 50% anywhere. Emitted as warnings now.
        if miss > 0.50:
            report.ran()
            msg = (f"covariate {col!r} is {miss:.1%} missing (>50%): a variable this "
                   f"incomplete needs a stated justification and a sensitivity "
                   f"analysis. Do NOT auto-remove it — valid MI handles this level of "
                   f"missingness when MAR holds (Madley-Dowd 2019); removing it is a "
                   f"decision for the decision log")
            report.warn("REFLECT-missing", None, msg,
                        {"column": col, "missing_fraction": round(miss, 4)})
            suggestions.append(msg)
        elif miss > 0.20:
            msg = (f"covariate {col!r} is {miss:.1%} missing (>20%): remove from the "
                   f"covariates or impute")
            suggestions.append(msg)

    if not suggestions:
        report.info("REFLECT", None, "no adjustments suggested")
    return suggestions


# ─────────────────────────────────────────────────────────────────────────────
# Output parsing helpers (POST stage)
# ─────────────────────────────────────────────────────────────────────────────

_DASHES = "–—−-"
# Numbers as the workbooks actually write them, including the ones a collapsed
# fit produces. `inf` and `nan` have to be *parsed* rather than ignored: a
# regex that only recognises well-behaved decimals turns "the estimate exploded"
# into "there was no estimate here", which is the quietest possible way to pass.
_NUM = r"[-+]?(?:\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|\.\d+(?:[eE][-+]?\d+)?|[Ii]nf(?:inity)?|[Nn]a[Nn]|NA)"
_EFFECT_RE = re.compile(
    rf"^\s*({_NUM})\s*\(\s*({_NUM})\s*[{_DASHES}]\s*({_NUM})\s*\)\s*$"
)
# Anything shaped like "estimate (low–high)" whose parts are not numbers we
# understand. Reported separately so an unrecognised format becomes a blocker
# rather than an absence.
_EFFECT_SHAPE_RE = re.compile(rf"^\s*[-+0-9.iInN][^()]*\(\s*[^()]*[{_DASHES}][^()]*\)\s*$")
_N_EVENTS_RE = re.compile(r"^\s*(\d+)\s*\(\s*(\d+)\s*\)\s*$")
_P_RE = re.compile(r"^\s*([<>≤≥]?)\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?|[Nn]a[Nn])\s*\*?\s*$")

# Column headers that identify an estimate / bound / p-value when a workbook
# splits them across columns instead of formatting one cell.
#
# The header also fixes the SCALE, and the scale decides which plausibility rule
# applies. Treating every estimate column as ratio-scale is what made RES-001
# block correct multivariable tables: those carry a log-scale `Coefficient`
# column beside the formatted HR, and on the log scale a protective covariate is
# negative (blocked as "non-positive") while a near-null one is ~0.002 (blocked
# as "outside [0.01, 100]"). Both are exactly what a correct model produces.
#
#   ratio                 strictly positive; plausible inside [0.01, 100]
#   log                   any sign; plausible inside +/- log(100), i.e. the same
#                         statement about the same quantity, transported to the
#                         scale it is printed on
#   unit_interval         a discrimination metric: inside [0, 1] by definition
#   signed_unit_interval  a DIFFERENCE of two of those: inside [-1, 1], and
#                         negative is an ordinary result, not a defect
#   unknown               the header does not determine a scale, so no bound is
#                         claimed and only the scale-free checks run (finite,
#                         estimate inside its own CI)
_ESTIMATE_HEADER_SCALES = {
    "or": "ratio", "hr": "ratio", "rr": "ratio", "shr": "ratio",
    # Spelled out too, because weighting.py names the scale INSIDE the cell
    # ("Hazard ratio: 1.04 (0.83–1.30)") rather than in the header, and that
    # label is the most explicit scale declaration in the whole workbook.
    # See parse_labelled_effect.
    "hazard ratio": "ratio", "odds ratio": "ratio", "risk ratio": "ratio",
    "rate ratio": "ratio", "subdistribution hazard ratio": "ratio",
    "beta": "log", "coef": "log", "coefficient": "log",
    "estimate": "unknown",
    "c-index": "unit_interval", "c index": "unit_interval", "auc": "unit_interval",
}
_ESTIMATE_HEADERS = tuple(_ESTIMATE_HEADER_SCALES)

# Discrimination columns are never written bare. auc_cstat.py emits
# "C-index\n(variable alone)\n[95% CI]" and "Delta C-index\n[95% CI]", which
# normalise to something no exact key matches, so every one of them used to fall
# through to the formatted-cell default of "ratio" — and a NEGATIVE delta, which
# is what you get whenever adding a variable costs you discrimination, blocked as
# a non-positive ratio. Matched by prefix because the qualifier that follows the
# metric name is free text the producer composes.
#
# Deliberately narrow. Widening this to catch, say, "log HR vs reference" in
# nonlinearity.py's Spline_estimates would be worse than leaving it unmatched:
# that sheet DOES have recognised "CI lower"/"CI upper" columns, and those bounds
# belong to the ratio column beside it, so a newly recognised log column would
# pair with the wrong interval and block on "estimate outside its own CI".
_DELTA_METRIC_PREFIXES = ("delta c-index", "delta c index", "delta auc")
_METRIC_PREFIXES = ("c-index", "c index", "auc")

# The ratio bound expressed on the log scale, so the two rules cannot drift.
_RATIO_LOW, _RATIO_HIGH = 0.01, 100.0
_LOG_BOUND = math.log(_RATIO_HIGH)
_UNIT_LOW, _UNIT_HIGH = 0.0, 1.0


def _implied_ratio(coef):
    """exp(coef) for a message, without overflowing and without lying about sign.

    `math.exp` overflows above ~709. Guarding on abs(coef) reported a large
    NEGATIVE coefficient as implying an infinite ratio, when it implies one
    indistinguishable from zero — the opposite end of the scale, in the one
    sentence the reader has to diagnose the fit from.
    """
    try:
        return f"{math.exp(coef):g}"
    except OverflowError:
        return "a ratio too large to represent"


def estimate_scale(header):
    """The scale a column header declares, or None when it declares no estimate.

    Exact match first, then the discrimination-metric prefixes. Delta is tested
    before the bare metric, because "delta c-index" starts with neither "c-index"
    nor anything else useful — and a difference of two bounded metrics has a
    different range and a different sign convention from the metrics themselves.
    """
    h = _norm_header(header)
    if h in _ESTIMATE_HEADER_SCALES:
        return _ESTIMATE_HEADER_SCALES[h]
    if h.startswith(_DELTA_METRIC_PREFIXES):
        return "signed_unit_interval"
    if h.startswith(_METRIC_PREFIXES):
        return "unit_interval"
    return None
_CI_LOW_HEADERS = ("95% ci lower", "ci lower", "ci_lower", "ci low", "lower", "lcl",
                   "lower 95% ci")
_CI_HIGH_HEADERS = ("95% ci upper", "ci upper", "ci_upper", "ci high", "upper", "ucl",
                    "upper 95% ci")
_P_HEADERS = ("p", "p-value", "p value", "pvalue", "p_value")

# Skills whose workbook is expected to contain at least one effect estimate.
# For these, "parsed nothing" is a parser failure or a broken output, never a
# clean bill of health.
# competing-risk is deliberately absent: its default output is a cumulative
# incidence table, not an effect estimate (`fine_gray` is None unless asked for),
# so "no effect estimate in this workbook" is the expected state, not a defect.
#
# ph-stratified and ph-time-varying belong here even though ph_remedy_gate.py
# also inspects them, because the gate reads the sidecar and never parses the
# workbook, and the sidecar is written from the same fit rather than from the
# sheet. Nothing else reads the numbers in those two tables. Their workbook
# exists only on the path where the model fitted — _not_computed and
# _not_applicable both write the sidecar and return before `wb.save` — so a
# file that holds no readable hazard ratio is a broken table, never an honest
# degraded state.
#
# ph-rmst is deliberately absent for the opposite reason: it reports a
# difference in years as a contrast sentence ("Unexposed minus Exposed: +0.518
# years (95% CI ...)"), which parse_labelled_effect refuses on purpose, so a
# successful rmst run parses zero effects by design. Adding it for symmetry
# would block every one of them.
_ESTIMATE_PRODUCING_SKILLS = ("univariate-forest", "multivariate-interaction",
                              "psm-matching", "auc-cstat",
                              "nonlinearity", "robust-variance", "weighting",
                              "evalue", "immortal-time",
                              "ph-stratified", "ph-time-varying")


def _to_float(token):
    """Parse a workbook number, including Inf / NaN. Raises ValueError otherwise."""
    text = str(token).strip()
    if text.upper() in ("NA", "N/A"):
        return float("nan")
    return float(text)


def _norm_header(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower().rstrip(":")


_LABELLED_EFFECT_RE = re.compile(r"^\s*([^:()]{1,40}?)\s*:\s*(.+)$")


def parse_labelled_effect(cell):
    """'Hazard ratio: 1.04 (0.83–1.30)' -> ('Hazard ratio', (1.04, 0.83, 1.30)).

    weighting.py writes its effect as `f"{scale}: " + fmt_effect(...)`, and
    parse_effect anchors at the start of the cell, so every one of those was
    invisible — which made `weighting` produce zero readable estimates and, being
    in _ESTIMATE_PRODUCING_SKILLS, block on "no effect estimate could be read"
    on every run.

    The label is not noise to be stripped: it is the scale, stated by the
    producer, and the caller resolves it through estimate_scale(). An
    unrecognised label yields scale "unknown" rather than the ratio default,
    because a producer that troubled to name its scale should not then have a
    different one assumed for it.

    Narrow on purpose. The label may not contain a colon or a bracket, and the
    remainder has to be an effect and nothing else — so ph_rmst's contrast
    sentence ("Unexposed minus Exposed: +0.518 years (95% CI 0.370 to 0.665);
    p = <0.001") still does not parse, and should not.
    """
    if cell is None:
        return None
    m = _LABELLED_EFFECT_RE.match(str(cell))
    if not m:
        return None
    eff = parse_effect(m.group(2))
    return (m.group(1), eff) if eff else None


def parse_effect(cell):
    """'3.42 (2.21-5.30)' -> (3.42, 2.21, 5.30); None when the cell is not one.

    Returns non-finite floats as-is so the caller can block on them.
    """
    if cell is None:
        return None
    m = _EFFECT_RE.match(str(cell))
    if not m:
        return None
    try:
        return tuple(_to_float(g) for g in m.groups())
    except ValueError:
        return None


def looks_like_unparsed_effect(cell):
    """True when a cell presents an estimate with an interval we failed to read.

    A percentage with a confidence interval — "60.6% (50.4-69.3)", which is what
    every KM and CIF summary is made of — has the same shape as an effect
    estimate and is not one. Reporting those as unparsable estimates turned a
    correct survival table into eight blocking findings.
    """
    if cell is None:
        return False
    text = str(cell)
    if parse_effect(cell) is not None or parse_n_events(cell) is not None:
        return False
    if "%" in text:
        return False
    return bool(_EFFECT_SHAPE_RE.match(text))


def parse_n_events(cell):
    """'231 (116)' -> (231, 116)."""
    if cell is None:
        return None
    m = _N_EVENTS_RE.match(str(cell))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def parse_p(cell):
    """'<0.001*' -> 0.001; '0.004' -> 0.004; None when not a p-value cell."""
    if cell is None:
        return None
    m = _P_RE.match(str(cell))
    if not m:
        return None
    try:
        return float(m.group(2))
    except ValueError:
        return None


def iter_xlsx_cells(path):
    """Yield (sheet_name, row_idx, col_idx, value) for every non-empty cell."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        for ws in wb.worksheets:
            for r, row in enumerate(ws.iter_rows(values_only=True), start=1):
                for c, value in enumerate(row, start=1):
                    if value is not None and str(value).strip() != "":
                        yield ws.title, r, c, value
    finally:
        wb.close()


def flowchart_final_n(path):
    """Final cohort N, read from the flowchart workbook's structure.

    Returns (n, why_not). Exactly one of the two is None.

    The table `flowchart.py` writes has a header row `Step | Description |
    N Excluded | N Remaining` and a row whose Step cell is `Final`. That grid is
    what gets read. The display banner ("Initial N = 600 -> Final N = 600") is
    only used as a corroborating fallback, because a caption is a rendering
    choice and can be reworded into `Final cohort (n=438)` without anyone
    thinking they changed a data structure.
    """
    if not os.path.exists(path):
        return None, f"{os.path.basename(path)} does not exist"
    rows = {}
    try:
        for sheet, r, c, value in iter_xlsx_cells(path):
            rows.setdefault((sheet, r), {})[c] = value
    except Exception as exc:
        return None, f"cannot read {os.path.basename(path)}: {type(exc).__name__}: {exc}"

    remaining_col = {}
    for (sheet, _r), cells in sorted(rows.items()):
        for c, value in cells.items():
            if _norm_header(value) in ("n remaining", "remaining", "n_remaining"):
                remaining_col[sheet] = c

    for (sheet, _r), cells in sorted(rows.items()):
        first = _norm_header(next((cells[c] for c in sorted(cells)), None))
        if first != "final":
            continue
        col = remaining_col.get(sheet)
        if col is None:
            return None, (f"{os.path.basename(path)} has a 'Final' row but no "
                          f"'N Remaining' column header to read it from")
        raw = cells.get(col)
        try:
            return int(float(str(raw).replace(",", "").strip())), None
        except (TypeError, ValueError):
            return None, (f"{os.path.basename(path)} 'Final' row has a non-numeric "
                          f"N Remaining cell: {raw!r}")

    # Structured read failed. Try the banner, and say so if that is what happened.
    banner = re.compile(r"Final\s*N\s*=\s*([\d,]+)")
    for cells in rows.values():
        for value in cells.values():
            m = banner.search(str(value))
            if m:
                return int(m.group(1).replace(",", "")), None
    return None, (f"{os.path.basename(path)} has no 'Final' row and no "
                  f"'Final N = ...' banner; its structure is not the one this "
                  f"check knows how to read")


def scan_output_numbers(path):
    """Extract estimates, p-values, N/event pairs and parse failures from a workbook.

    Returns (effects, pvals, ns, unparsed). Two cell layouts are read: a single
    formatted cell (`3.42 (2.21-5.30)`) and estimate/CI/p split across columns
    under their own headers. `unparsed` carries cells that present an estimate in
    a shape this function could not read — the caller blocks on those instead of
    treating them as absent.

    Every effect carries a `scale` ("ratio" / "log" / "unknown") taken from its
    column header, because the plausibility bound is only meaningful per scale.
    A formatted cell in a column with no recognised header defaults to "ratio":
    `x (lo-hi)` in these workbooks is a ratio with its CI, and defaulting to
    "unknown" would silently switch off the check that catches HR = 1.2e6.
    """
    rows = {}
    for sheet, r, c, value in iter_xlsx_cells(path):
        rows.setdefault((sheet, r), {})[c] = value

    # Column roles, taken only from rows that carry at least TWO recognised
    # header names. A single match is not a header row: the log-rank sheet is a
    # vertical key/value layout whose first column contains the literal string
    # "p-value", and treating that column as p-value *data* turned every label
    # in it ("Metric", "Degrees of Freedom") into an unparsable estimate.
    roles, scales = {}, {}
    for (sheet, _r), cells in sorted(rows.items()):
        candidates, candidate_scales = {}, {}
        for c, value in cells.items():
            h = _norm_header(value)
            scale = estimate_scale(value)
            if scale is not None:
                candidates[c] = "estimate"
                candidate_scales[c] = scale
            elif h in _CI_LOW_HEADERS:
                candidates[c] = "ci_low"
            elif h in _CI_HIGH_HEADERS:
                candidates[c] = "ci_high"
            elif h in _P_HEADERS:
                candidates[c] = "p"
        if len(candidates) < 2:
            continue
        for c, role in candidates.items():
            roles.setdefault((sheet, c), role)
            if c in candidate_scales:
                scales.setdefault((sheet, c), candidate_scales[c])

    effects, pvals, ns, unparsed = [], [], [], []
    for (sheet, r), cells in sorted(rows.items()):
        packed, packed_scale = {}, "unknown"
        for c, value in cells.items():
            eff = parse_effect(value)
            if eff:
                effects.append({"sheet": sheet, "row": r, "col": c, "source": "formatted",
                                "scale": scales.get((sheet, c), "ratio"),
                                "estimate": eff[0], "ci_low": eff[1], "ci_high": eff[2]})
                continue
            labelled = parse_labelled_effect(value)
            if labelled:
                label, eff = labelled
                effects.append({"sheet": sheet, "row": r, "col": c, "source": "labelled",
                                "label": label,
                                "scale": estimate_scale(label) or "unknown",
                                "estimate": eff[0], "ci_low": eff[1], "ci_high": eff[2]})
                continue
            ne = parse_n_events(value)
            if ne:
                ns.append({"sheet": sheet, "row": r, "n": ne[0], "events": ne[1]})
                continue
            if looks_like_unparsed_effect(value):
                unparsed.append({"sheet": sheet, "row": r, "col": c,
                                 "value": str(value)[:120]})
                continue
            role = roles.get((sheet, c))
            if role is None:
                continue
            try:
                packed[role] = _to_float(str(value).lstrip("<>≤≥").rstrip("*"))
                if role == "estimate":
                    packed_scale = scales.get((sheet, c), "unknown")
            except ValueError:
                # A header cell, or any cell with no digits in it, is prose in a
                # data column — a layout quirk, not a number we failed to read.
                # "Is this a header?" has to be asked through the same resolver
                # that assigned the role: "C-index (variable alone) [95% CI]"
                # carries digits and is not an exact key, so a literal-tuple test
                # reports the header of a column as an unparsable estimate.
                if (any(ch.isdigit() for ch in str(value))
                        and estimate_scale(value) is None
                        and _norm_header(value) not in (_CI_LOW_HEADERS + _CI_HIGH_HEADERS
                                                        + _P_HEADERS)):
                    unparsed.append({"sheet": sheet, "row": r, "col": c,
                                     "value": str(value)[:120], "role": role})
        if "estimate" in packed:
            effects.append({"sheet": sheet, "row": r, "col": None, "source": "columns",
                            "scale": packed_scale,
                            "estimate": packed["estimate"],
                            "ci_low": packed.get("ci_low", float("nan")),
                            "ci_high": packed.get("ci_high", float("nan"))})
        if "p" in packed:
            pvals.append({"sheet": sheet, "row": r, "col": None, "p": packed["p"]})

    # Formatted p-value cells sit under a p header without matching _NUM alone
    # (e.g. "<0.001*"), so sweep them separately.
    for (sheet, r), cells in sorted(rows.items()):
        for c, value in cells.items():
            if roles.get((sheet, c)) != "p":
                continue
            p = parse_p(value)
            if p is not None and not any(x["sheet"] == sheet and x["row"] == r
                                         for x in pvals):
                pvals.append({"sheet": sheet, "row": r, "col": c, "p": p})
    return effects, pvals, ns, unparsed


# ─────────────────────────────────────────────────────────────────────────────
# POST-stage checks
# ─────────────────────────────────────────────────────────────────────────────

_PENALISED_HINT_RE = re.compile(r"firth|penali", re.IGNORECASE)

# Skills whose analysis N is a designed subset of the final cohort, not a
# silent drop: matched pairs, landmark survivors. RES-002 still reports the gap
# for these, but as a warning — blocking them would train people to ignore it.
_EXPECTED_SUBSET_SKILLS = ("psm-matching", "immortal-time", "weighting")


_TABULAR_EXTENSIONS = (".xlsx", ".xls", ".csv")


def declared_output(plan, step, configs=None):
    """The artifact this step says it will produce, as an absolute path or None.

    The generated config carries an absolute `output_file`; the plan step carries
    a bare stem. The config wins, because that is what the sub-skill was actually
    told to write.
    """
    config = (configs or {}).get(step.get("id")) or {}
    declared = config.get("output_file") or step.get("output_file")
    if not declared:
        return None
    if os.path.isabs(declared):
        return declared
    return os.path.join(plan["output_dir"], declared)


def step_output_paths(plan, step, configs=None):
    """Existing artifacts for a step, preferring a workbook over its CSV twin.

    Extension-agnostic: `PSM` may have been written as PSM.xlsx, PSM.csv or both,
    and a check that only looks for one of them reports "nothing to audit" on a
    step that produced output.
    """
    declared = declared_output(plan, step, configs)
    if not declared:
        return []
    candidates = []
    root, ext = os.path.splitext(declared)
    if ext:
        candidates.append(declared)
        candidates.extend(root + e for e in _TABULAR_EXTENSIONS if e != ext.lower())
    else:
        candidates.extend(declared + e for e in _TABULAR_EXTENSIONS)
    seen, found = set(), []
    for path in candidates:
        if path not in seen and os.path.exists(path):
            seen.add(path)
            found.append(path)
    return found


def check_output_artifacts(report, plan, steps, configs):
    """Post stage: every enabled step that declared an output must have produced it.

    A missing artifact used to mean the numeric checks quietly had nothing to
    run on. "The step never produced output" is a worse finding than any of the
    checks it prevented, so it is the one that has to be reported.
    """
    missing = 0
    for step in steps:
        if step.get("status") == "skipped":
            continue
        declared = declared_output(plan, step, configs)
        if not declared:
            continue
        report.ran()
        if step_output_paths(plan, step, configs) or os.path.exists(declared):
            continue
        missing += 1
        report.block("RES-000", step["id"],
                     f"declared output {os.path.basename(declared)} does not exist "
                     f"(step status {step.get('status', 'unknown')!r}); every numeric "
                     f"check for this step had nothing to read",
                     {"declared_output": declared, "status": step.get("status")})
    return missing


def check_res001_res002(report, plan, steps, configs):
    """RES-001 numeric plausibility and RES-002 N alignment with the flowchart."""
    flowchart_steps = [s for s in steps if s.get("skill") == "flowchart"
                       and s.get("status") != "skipped"]
    final_n = None
    if flowchart_steps:
        fpath = (declared_output(plan, flowchart_steps[0], configs)
                 or os.path.join(plan["output_dir"], "Flowchart.xlsx"))
        final_n, why_not = flowchart_final_n(fpath)
        if final_n is None:
            report.block("RES-002", flowchart_steps[0]["id"],
                         f"the flowchart's final N could not be read, so no analysis N "
                         f"can be checked against it: {why_not}",
                         {"flowchart_path": fpath})
    else:
        report.warn("RES-002", None,
                    "the plan has no flowchart step, so there is no final cohort N to "
                    "align the analysis Ns against")

    processed = skipped = 0
    per_step_n = {}
    for step in steps:
        if step.get("status") == "skipped":
            continue
        paths = step_output_paths(plan, step, configs)
        if not paths:
            # Absence is reported by check_output_artifacts; counted here so the
            # processed/skipped/total line stays honest.
            if declared_output(plan, step, configs):
                skipped += 1
            continue
        for path in paths[:1]:
            try:
                effects, pvals, ns, unparsed = scan_output_numbers(path)
            except Exception as exc:
                skipped += 1
                report.block("RES-001", step["id"],
                             f"could not read output {os.path.basename(path)} "
                             f"({type(exc).__name__}: {exc}); its numbers were not checked")
                continue
            processed += 1
            penalised = _penalised_note_present(path)

            for u in unparsed:
                report.ran()
                report.block("RES-001", step["id"],
                             f"cell presents an estimate this check could not parse, so "
                             f"its plausibility was never tested: {u['value']!r} in "
                             f"{os.path.basename(path)}!{u['sheet']} row {u['row']}", u)

            if not effects and step.get("skill") in _ESTIMATE_PRODUCING_SKILLS:
                report.ran()
                report.block("RES-001", step["id"],
                             f"{os.path.basename(path)} is the output of a "
                             f"{step.get('skill')} step but no effect estimate could be "
                             f"read from it; either the run produced none or the layout "
                             f"is one this check does not understand",
                             {"path": path})

            for e in effects:
                report.ran()
                est = e["estimate"]
                scale = e.get("scale", "ratio")
                where = f"in {os.path.basename(path)}!{e['sheet']} row {e['row']}"
                note = " (penalised fit noted in the workbook)" if penalised else ""
                severity = report.warn if penalised else report.block
                if not math.isfinite(est):
                    report.block("RES-001", step["id"],
                                 f"non-finite estimate {est} {where}", e)
                elif scale == "ratio" and est <= 0:
                    report.block("RES-001", step["id"],
                                 f"non-positive estimate {est} {where}; a ratio cannot "
                                 f"be zero or negative", e)
                elif scale == "ratio" and not (_RATIO_LOW <= est <= _RATIO_HIGH):
                    severity("RES-001", step["id"],
                             f"estimate {est:g} outside "
                             f"[{_RATIO_LOW:g}, {_RATIO_HIGH:g}] {where}" + note, e)
                elif scale == "log" and abs(est) > _LOG_BOUND:
                    severity("RES-001", step["id"],
                             f"log-scale coefficient {est:g} {where} implies a ratio of "
                             f"{_implied_ratio(est)}, outside "
                             f"[{_RATIO_LOW:g}, {_RATIO_HIGH:g}]" + note, e)
                elif scale == "unit_interval" and not (_UNIT_LOW <= est <= _UNIT_HIGH):
                    severity("RES-001", step["id"],
                             f"discrimination metric {est:g} outside "
                             f"[{_UNIT_LOW:g}, {_UNIT_HIGH:g}] {where}" + note, e)
                elif scale == "signed_unit_interval" and not (-_UNIT_HIGH <= est <= _UNIT_HIGH):
                    severity("RES-001", step["id"],
                             f"change in a discrimination metric {est:g} outside "
                             f"[{-_UNIT_HIGH:g}, {_UNIT_HIGH:g}] {where}" + note, e)
                lo, hi = e["ci_low"], e["ci_high"]
                # A ratio CI is read on the multiplicative scale; hi/lo on a log
                # scale is a ratio of two additive bounds that may straddle zero,
                # which says nothing about width.
                if scale == "ratio" and lo > 0 and math.isfinite(hi) and hi / lo >= 1e3:
                    report.warn("RES-001", step["id"],
                                f"95% CI spans {hi / lo:.3g}x (>3 orders of magnitude): "
                                f"{est:g} ({lo:g}-{hi:g}) — sparse data", e)
                if math.isfinite(est) and math.isfinite(lo) and math.isfinite(hi) and not lo <= est <= hi:
                    report.block("RES-001", step["id"],
                                 f"point estimate {est:g} lies outside its own CI ({lo:g}, {hi:g})", e)

            for p in pvals:
                report.ran()
                if not (0.0 <= p["p"] <= 1.0):
                    report.block("RES-001", step["id"],
                                 f"p-value {p['p']} outside [0, 1] in "
                                 f"{os.path.basename(path)}!{p['sheet']} row {p['row']}", p)

            if ns:
                observed = max(x["n"] for x in ns)
                per_step_n[step["id"]] = observed
                if final_n:
                    report.ran()
                    drop = (final_n - observed) / final_n
                    documented = (bool(step.get("qc_warnings"))
                                  or step.get("skill") in _EXPECTED_SUBSET_SKILLS)
                    if drop > 0.05 and not documented:
                        report.block("RES-002", step["id"],
                                     f"analysis N {observed} is {drop:.1%} below the flowchart "
                                     f"final N {final_n} and nothing in qc_warnings explains it",
                                     {"analysis_n": observed, "flowchart_final_n": final_n})
                    elif drop > 0.05:
                        why = ("this skill analyses a designed subset"
                               if step.get("skill") in _EXPECTED_SUBSET_SKILLS
                               else "qc_warnings present, check they explain it")
                        report.warn("RES-002", step["id"],
                                    f"analysis N {observed} is {drop:.1%} below the flowchart "
                                    f"final N {final_n}; {why}",
                                    {"analysis_n": observed, "flowchart_final_n": final_n,
                                     "qc_warnings": step.get("qc_warnings")})
                    elif observed > final_n:
                        report.block("RES-002", step["id"],
                                     f"analysis N {observed} exceeds the flowchart final N {final_n}",
                                     {"analysis_n": observed, "flowchart_final_n": final_n})

    print(f"  RES-001/002: processed {processed} / skipped {skipped} / total "
          f"{processed + skipped} output file(s)", file=sys.stderr)
    return per_step_n, final_n


def _penalised_note_present(path):
    try:
        for _sheet, _r, _c, value in iter_xlsx_cells(path):
            if _PENALISED_HINT_RE.search(str(value)):
                return True
    except Exception as exc:
        print(f"  [SKIP] RES-001 penalised-note scan on {path}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
    return False


def _crude_effect(df, plan, outcome):
    """Unadjusted odds ratio for groups[0] vs groups[1] on a binary/event column.

    Used only as a *direction* anchor for the PSM check, so a 2x2 with a
    continuity correction is sufficient and keeps this dependency-free.
    """
    ev_col = outcome.get("event_column")
    if not ev_col or ev_col not in df.columns:
        return None
    masks = group_masks(df, plan)
    if len(masks) < 2:
        return None
    ev = pd.to_numeric(df[ev_col], errors="coerce")
    (_l0, m0), (_l1, m1) = masks[0], masks[1]
    a = float(((ev == 1) & m0).sum()) + 0.5
    b = float(((ev == 0) & m0).sum()) + 0.5
    c = float(((ev == 1) & m1).sum()) + 0.5
    d = float(((ev == 0) & m1).sum()) + 0.5
    if b <= 0 or c <= 0:
        return None
    return (a / b) / (c / d)


def _two_by_two_or(exposed_counts, control_counts):
    """Odds ratio from two (n, events) pairs, with a continuity correction."""
    (n1, e1), (n2, e2) = exposed_counts, control_counts
    a, b = e1 + 0.5, (n1 - e1) + 0.5
    c, d = e2 + 0.5, (n2 - e2) + 0.5
    if b <= 0 or c <= 0 or d <= 0:
        return None
    return (a / b) / (c / d)


def _psm_evidence(path, exposed_label, control_label):
    """Read the direction evidence out of one PSM artifact.

    Returns a dict with:
      order    (index_of_exposed, index_of_control) column positions, or (None, None)
      effect   the first reported OR/HR, or None
      columns  the header cells, for the message
      counts   {"exposed": (n, events), "control": (n, events)} or None

    `counts` is what makes the self-consistency check possible: the same row
    that reports the effect also reports each arm's N and events, so the row can
    be asked whether it agrees with itself. Both file shapes are handled — the
    workbook is what the pipeline always writes.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        table = pd.read_csv(path)
        cols = [str(c) for c in table.columns]
        order = (next((i for i, c in enumerate(cols) if c.startswith(exposed_label)), None),
                 next((i for i, c in enumerate(cols) if c.startswith(control_label)), None))
        effect_col = next((c for c in table.columns if str(c).strip() in ("OR", "HR")), None)
        effect = None
        if effect_col is not None and len(table):
            values = pd.to_numeric(table[effect_col], errors="coerce").dropna()
            effect = float(values.iloc[0]) if len(values) else None

        counts = None
        if len(table):
            row = table.iloc[0]

            def pair(label):
                n_col = next((c for c in table.columns
                              if str(c).strip() == f"{label} N"), None)
                e_col = next((c for c in table.columns
                              if str(c).strip() == f"{label} Events"), None)
                if n_col is None or e_col is None:
                    return None
                try:
                    return int(float(row[n_col])), int(float(row[e_col]))
                except (TypeError, ValueError):
                    return None

            exposed_pair, control_pair = pair(exposed_label), pair(control_label)
            if exposed_pair and control_pair:
                counts = {"exposed": exposed_pair, "control": control_pair}
        return {"order": order, "effect": effect, "columns": cols, "counts": counts}

    rows = {}
    for sheet, r, c, value in iter_xlsx_cells(path):
        rows.setdefault((sheet, r), {})[c] = value

    order, cols, effect, counts = (None, None), [], None, None
    header_key = None
    for key, cells in sorted(rows.items()):
        texts = {c: str(v).replace("\n", " ") for c, v in cells.items()}
        exposed_at = next((c for c in sorted(texts)
                           if texts[c].startswith(exposed_label)), None)
        control_at = next((c for c in sorted(texts)
                           if texts[c].startswith(control_label)), None)
        if exposed_at is not None and control_at is not None:
            order = (exposed_at, control_at)
            cols = [texts[c] for c in sorted(texts)]
            header_key = key
            break

    for key, cells in sorted(rows.items()):
        if header_key and key <= header_key:
            continue
        row_effect = None
        for value in cells.values():
            eff = parse_effect(value)
            if eff:
                row_effect = eff[0]
                break
        if row_effect is None:
            continue
        effect = row_effect
        exposed_at, control_at = order
        if exposed_at is not None and control_at is not None:
            exposed_pair = parse_n_events(cells.get(exposed_at))
            control_pair = parse_n_events(cells.get(control_at))
            if exposed_pair and control_pair:
                counts = {"exposed": exposed_pair, "control": control_pair}
        break

    if effect is None:
        for _key, cells in sorted(rows.items()):
            for value in cells.values():
                eff = parse_effect(value)
                if eff:
                    effect = eff[0]
                    break
            if effect is not None:
                break
    return {"order": order, "effect": effect, "columns": cols, "counts": counts}


def _file_sha256(path):
    """Hex digest of a file, or None when it cannot be read."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _psm_contrast_sidecar(artifact_path):
    """The sidecar belonging to ONE table: `<stem>_contrast.json`, nothing else.

    Returns (payload, path, generic_path). `generic_path` is set when no
    same-stem sidecar exists but a bare PSM_contrast.json does — the caller
    blocks on that rather than using it.

    There used to be a fallback to `<output_dir>/PSM_contrast.json`. With two
    PSM steps, or one left over from an earlier run, that fallback validated the
    primary table against a sidecar belonging to a sensitivity analysis or to
    last week's data — and passed. The whole reason this file exists is to be an
    independent second source for one specific table; a sidecar that might
    describe a different table is not that.
    """
    same_stem = f"{os.path.splitext(artifact_path)[0]}_contrast.json"
    if os.path.exists(same_stem):
        try:
            with open(same_stem, "r", encoding="utf-8") as f:
                return json.load(f), same_stem, None
        except Exception as exc:
            print(f"  [SKIP] PSM-DIR: cannot read {os.path.basename(same_stem)} "
                  f"({type(exc).__name__}: {exc})", file=sys.stderr)
            return None, same_stem, None
    generic = os.path.join(os.path.dirname(artifact_path), "PSM_contrast.json")
    if os.path.exists(generic) and os.path.abspath(generic) != os.path.abspath(same_stem):
        return None, None, generic
    return None, None, None


def check_psm_direction(report, plan, df_filtered, steps=None, configs=None):
    """PSM direction anchor.

    Two independent assertions, because the failure they guard against — the
    reported OR being the reciprocal of the intended contrast — was found five
    separate times by five separate LLM reviewers on one project:

      1. label order: the first group-labelled column in the PSM output must be
         `plan.grouping.groups[0].label`, which is the group psm_matching.py
         treats as exposed.
      2. reciprocal signature: the reported effect must not sit closer to
         1 / crude_effect than to crude_effect. Matching can move an estimate,
         but landing on its reciprocal is a labelling accident, not an ATT.

    Missing or unreadable evidence is a blocker, not a skip. This check exists
    for one specific historical defect; "could not tell" and "no defect" must not
    share an exit code.
    """
    psm_steps = [s for s in (steps or []) if s.get("skill") == "psm-matching"
                 and s.get("status") != "skipped"]
    if not psm_steps:
        report.skipped("PSM-DIR", "the plan has no psm-matching step")
        return

    groups = (plan.get("grouping") or {}).get("groups") or []
    if len(groups) < 2:
        report.block("PSM-DIR", psm_steps[0]["id"],
                     "the plan runs PSM but grouping declares fewer than two groups, "
                     "so the contrast being estimated is undefined")
        return
    exposed_label = str(groups[0].get("label"))
    control_label = str(groups[1].get("label"))

    # Every PSM step, not just the first. A plan with a primary and a
    # sensitivity match had the second one unchecked entirely, which is also how
    # a sidecar belonging to one of them came to be used for the other.
    for step in psm_steps:
        _check_one_psm_step(report, plan, df_filtered, configs, step,
                            groups, exposed_label, control_label)


def _check_one_psm_step(report, plan, df_filtered, configs, step, groups,
                        exposed_label, control_label):
    paths = step_output_paths(plan, step, configs)
    if not paths:
        declared = declared_output(plan, step, configs)
        report.block("PSM-DIR", step["id"],
                     f"no PSM artifact found for the declared output "
                     f"{os.path.basename(declared) if declared else '(none declared)'}; "
                     f"the direction of the reported effect could not be verified",
                     {"declared_output": declared})
        return

    evidence_read, errors = None, []
    for path in paths:
        try:
            evidence_read = _psm_evidence(path, exposed_label, control_label)
        except Exception as exc:
            errors.append(f"{os.path.basename(path)}: {type(exc).__name__}: {exc}")
            continue
        if evidence_read.get("effect") is not None:
            break
    for err in errors:
        report.warn("PSM-DIR", step["id"], f"could not read a PSM artifact ({err})")
    if evidence_read is None:
        report.block("PSM-DIR", step["id"],
                     f"none of the PSM artifacts could be read "
                     f"({', '.join(os.path.basename(p) for p in paths)}); direction "
                     f"was not verified", {"paths": paths, "errors": errors})
        return

    order = evidence_read["order"]
    reported = evidence_read["effect"]
    cols = evidence_read["columns"]
    counts = evidence_read["counts"]

    # ── 1. Column order (blocking) ──────────────────────────────────────────
    # psm_matching.py hardcodes groups[0] as treatment and emits the columns in
    # that order (`g1_label = config['grouping']['groups'][0]['label']`), and its
    # own footnote reads "OR > 1 indicates higher odds in {g1_label}". In this
    # pipeline the column order IS the machine-readable contrast declaration —
    # there is no separate metadata that could disagree with it — so a
    # control-first table did not come from the shipped producer, or the
    # grouping used to produce it does not match the plan. Both are worth stopping for.
    report.ran()
    first_exposed, first_control = order
    if first_exposed is None or first_control is None:
        report.block("PSM-DIR", step["id"],
                     f"the PSM output does not carry the declared group labels "
                     f"({exposed_label!r} / {control_label!r}), so which arm is the "
                     f"exposed one cannot be established from it. Columns seen: {cols}. "
                     f"If this table came from outside the pipeline, re-run the "
                     f"psm-matching step so the contrast is declared",
                     {"columns": cols})
    elif first_exposed > first_control:
        report.block("PSM-DIR", step["id"],
                     f"PSM output puts {control_label!r} before {exposed_label!r}; "
                     f"grouping.groups[0] is the exposed arm, so the reported effect is "
                     f"the reciprocal of the intended contrast",
                     {"columns": cols})

    if reported is None:
        report.block("PSM-DIR", step["id"],
                     f"no effect estimate could be read from "
                     f"{', '.join(os.path.basename(p) for p in paths)}; none of the "
                     f"direction checks could run",
                     {"paths": paths, "errors": errors})
        return

    # ── 2. Row self-consistency (blocking) ──────────────────────────────────
    # The row that reports the effect also reports each arm's N and events, so
    # it can be asked whether it agrees with itself. Same matched cohort, same
    # row, so confounding cannot explain a disagreement — this is the check that
    # replaces the crude-OR anchor as the blocking guard against an inverted
    # contrast, and unlike that anchor it has no confounding failure mode.
    # Non-collapsibility means the conditional (pair-stratified) OR and this
    # pooled 2x2 OR differ in magnitude; they cannot be reciprocals of each other.
    _psm_self_consistency(report, step, plan, counts, reported, exposed_label, paths)

    # ── 3. Producer sidecar (blocking on mismatch, warning when absent) ─────
    _psm_sidecar_check(report, step, plan, counts, paths, groups, configs)

    # ── 4. Crude anchor (warning only) ──────────────────────────────────────
    # Downgraded from blocking on adjudication: with strong confounding, an
    # adjusted estimate landing on the other side of the null is what adjustment
    # is *for*. A crude OR of 2.0 and a correct matched OR of 0.5 is Simpson's
    # paradox, not a labelling accident, and this band cannot tell the two apart.
    # It stays as the only signal that would catch a total inversion — labels,
    # counts and estimate all flipped together — which items 2 and 3 cannot see.
    primary = (plan.get("outcomes") or {}).get("primary")
    crude = _crude_effect(df_filtered, plan, primary or {})
    if not crude or crude <= 0 or reported <= 0:
        report.warn("PSM-DIR", step["id"],
                    f"the crude effect used as a secondary direction anchor could not "
                    f"be computed (reported {reported!r}, crude {crude!r})",
                    {"psm_effect": reported, "crude_effect": crude})
        return

    report.ran()
    lr, lc = math.log(reported), math.log(crude)
    same_dir = abs(lr - lc)
    flipped = abs(lr + lc)
    evidence = {"psm_effect": round(reported, 4), "crude_effect": round(crude, 4),
                "log_gap_same_direction": round(same_dir, 3),
                "log_gap_if_reciprocal": round(flipped, 3)}
    if flipped < same_dir and abs(lc) > math.log(1.5):
        near_reciprocal = " and close to its reciprocal" if flipped < 0.15 else ""
        report.warn("PSM-DIR", step["id"],
                    f"PSM effect {reported:.2f} points the opposite way to the crude "
                    f"effect {crude:.2f}{near_reciprocal}. Strong confounding can do "
                    f"this legitimately — that is what adjustment is for — so this is "
                    f"not on its own evidence of anything. If the reversal was not "
                    f"expected, confirm the exposed arm is {exposed_label!r} against "
                    f"PSM_contrast.json", evidence)
    else:
        report.info("PSM-DIR", step["id"],
                    f"direction anchored: PSM {reported:.2f} vs crude {crude:.2f}",
                    evidence)


def _psm_self_consistency(report, step, plan, counts, reported, exposed_label, paths):
    """Does the reported effect agree in direction with its own row's counts?"""
    if not counts:
        report.warn("PSM-DIR", step["id"],
                    f"the PSM table does not report per-arm N and events, so the row "
                    f"could not be checked against itself; the strongest available "
                    f"direction check did not run "
                    f"({', '.join(os.path.basename(p) for p in paths)})")
        return
    table_or = _two_by_two_or(counts["exposed"], counts["control"])
    if not table_or or table_or <= 0 or reported <= 0:
        report.warn("PSM-DIR", step["id"],
                    f"per-arm counts {counts} do not yield a usable 2x2 odds ratio; "
                    f"row self-consistency was not checked")
        return

    report.ran()
    lr, lt = math.log(reported), math.log(table_or)
    evidence = {"reported_effect": round(reported, 4),
                "counts_implied_or": round(table_or, 4),
                "exposed_n_events": counts["exposed"],
                "control_n_events": counts["control"]}

    primary = (plan.get("outcomes") or {}).get("primary") or {}
    try:
        otype = _norm_outcome_type(primary.get("type"))
    except ValueError:
        otype = "binary"

    if otype == "binary":
        # Magnitudes are comparable enough to use the reciprocal band.
        if abs(lr + lt) < 0.15 and abs(lr - lt) > 0.40:
            report.block("PSM-DIR", step["id"],
                         f"the reported effect {reported:.2f} is the reciprocal of the "
                         f"one implied by its own row's counts ({table_or:.2f}: "
                         f"{exposed_label} {counts['exposed'][1]}/{counts['exposed'][0]} "
                         f"vs control {counts['control'][1]}/{counts['control'][0]}). "
                         f"Same matched cohort, same row — confounding cannot explain "
                         f"this, so the treatment coding used for the estimate is "
                         f"inverted relative to the counts", evidence)
            return
    else:
        # Censoring makes the counts-OR and a hazard ratio incomparable in
        # magnitude, so only strict direction disagreement is actionable, and
        # only when both sides are clearly away from the null.
        if lr * lt < 0 and abs(lr) > math.log(1.5) and abs(lt) > math.log(1.5):
            report.block("PSM-DIR", step["id"],
                         f"the reported effect {reported:.2f} points the opposite way "
                         f"to its own row's counts ({table_or:.2f}: "
                         f"{exposed_label} {counts['exposed'][1]}/{counts['exposed'][0]} "
                         f"vs control {counts['control'][1]}/{counts['control'][0]}). "
                         f"Differential follow-up can move the magnitude but not "
                         f"usually the sign; check the treatment coding", evidence)
            return
    report.info("PSM-DIR", step["id"],
                f"row is self-consistent: reported {reported:.2f} vs counts-implied "
                f"{table_or:.2f}", evidence)


# ─────────────────────────────────────────────────────────────────────────────
# RES-015-det — PH remedy artifact gate (delegated)
# ─────────────────────────────────────────────────────────────────────────────

PH_REMEDY_GATE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "biostats-guardian", "scripts", "ph_remedy_gate.py")


def check_ph_remedy_gate(report, plan, plan_path, steps, output_dir):
    """RES-015-det: delegate to biostats-guardian's ph_remedy_gate.py.

    Invoked rather than reimplemented, on purpose. Two implementations of one
    rule drift, and this project has already paid for that twice: `_param_count`
    and `parameter_budget` disagree on how many parameters a categorical costs
    (with the looser one feeding the auto-RCS decision), and reviewer_challenge
    deliberately imports the enum table rather than mirroring it, on the grounds
    that a result computed from a diverged table is worse than an error. The
    rules this gate encodes — what `*_ph_test.json` statuses mean, that the
    config's remedy beats the plan's when they disagree, that a decision ID
    declared at plan top level is not fingerprinted and so can be edited
    silently — are exactly the kind of domain reasoning a copy would lose first.

    The cross-skill dependency is real but not new: biostats-guardian's
    integration.md already calls this script, so the two are coupled already;
    this makes the coupling mutual rather than introducing it.

    Timing is preserved: the gate is a MANUSCRIPT gate, not a per-step one. It
    runs once, at the post stage, and only when there is a manuscript to protect.
    """
    manuscript = [s for s in steps if s.get("skill") == "manuscript-results"
                  and s.get("status") != "skipped"]
    if not manuscript:
        report.skipped("RES-015-det",
                       "the plan has no manuscript step; the PH remedy gate guards the "
                       "manuscript, so there is nothing for it to guard here")
        return

    # Scope, taken from results-audit.md's producer table rather than invented:
    # `multivariate-interaction` is the only producer that writes *_ph_test.json,
    # so a plan without one has no PH artifacts by design. Running the gate anyway
    # would exit 2 ("no artifacts found") and block a correct univariate-only or
    # logistic-only run for missing a file nothing ever produces.
    cox_multi = []
    for step in steps:
        if step.get("skill") != "multivariate-interaction" or step.get("status") == "skipped":
            continue
        outcome = next((o for o in all_outcomes(plan)
                        if o.get("id") == step.get("outcome")), None)
        try:
            otype = _norm_outcome_type((outcome or {}).get("type"))
        except ValueError:
            otype = None
        if otype in ("time_to_event", "competing_risk"):
            cox_multi.append(step["id"])
    if not cox_multi:
        report.skipped("RES-015-det",
                       "no multivariate-interaction step fits a Cox model in this plan, "
                       "so no proportional-hazards assumption is being made and no "
                       "*_ph_test.json is expected (results-audit.md producer table)")
        return

    if not os.path.exists(PH_REMEDY_GATE):
        report.block("RES-015-det", manuscript[0]["id"],
                     f"the PH remedy gate is not installed at {PH_REMEDY_GATE}, so "
                     f"whether a declared ph_violation_remedy was ever performed is "
                     f"unknown. Not auditing it is not the same as it passing",
                     {"expected_path": PH_REMEDY_GATE, "cox_steps": cox_multi})
        return

    # The gate's report is read from a private temp file, never from a fixed
    # path in the output directory. A fixed path is readable when the child
    # never wrote it — an older gate version, a SIGKILL, a crash before the
    # write — and last week's "passed" report then stands in for an audit that
    # did not happen this time. The stale copy is removed first so that no other
    # reader can make the same mistake.
    stable = os.path.join(output_dir, "guardian", "ph_remedy_gate.json")
    os.makedirs(os.path.dirname(stable), exist_ok=True)
    if os.path.exists(stable):
        try:
            os.remove(stable)
        except OSError as exc:
            report.warn("RES-015-det", manuscript[0]["id"],
                        f"a previous {os.path.basename(stable)} could not be removed "
                        f"({exc}); it may be mistaken for this run's result")

    with tempfile.TemporaryDirectory(prefix="ph_gate_") as tmpdir:
        json_out = os.path.join(tmpdir, "ph_remedy_gate.json")
        argv = [sys.executable, PH_REMEDY_GATE, "--plan", os.path.abspath(plan_path),
                "--output-dir", output_dir, "--json", json_out, "--quiet"]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        except Exception as exc:
            report.block("RES-015-det", manuscript[0]["id"],
                         f"the PH remedy gate could not be run ({type(exc).__name__}: "
                         f"{exc}); PH remedies were not audited",
                         {"argv": argv[1:]})
            return

        report.ran()
        payload, why_not = _validated_gate_payload(
            json_out, proc, os.path.abspath(plan_path), output_dir)
        if payload is None:
            report.block("RES-015-det", manuscript[0]["id"],
                         f"the PH remedy gate did not produce a usable result, so PH "
                         f"remedies were not audited: {why_not}",
                         {"argv": argv[1:], "returncode": proc.returncode,
                          "stderr": (proc.stderr or "")[-2000:]})
            return
        with open(stable, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    findings = payload.get("findings") or []
    for finding in findings:
        emit = report.block if finding.get("severity") == "block" else report.warn
        emit(finding.get("check_id", "RES-015-det"), manuscript[0]["id"],
             finding.get("message", "").strip(), finding.get("evidence") or {})

    if not findings:
        report.info("RES-015-det", manuscript[0]["id"],
                    f"PH remedy gate passed for {', '.join(cox_multi)}",
                    {"json": stable, "artifacts_checked": payload.get("n_ph_artifacts")})


_GATE_REQUIRED_KEYS = ("plan", "output_dir", "n_ph_artifacts", "n_blocking",
                       "n_warning", "findings")


def _validated_gate_payload(json_out, proc, plan_path, output_dir):
    """(payload, None) only when this report provably belongs to this run.

    Returns (None, reason) otherwise, and the caller blocks. Every branch here
    is a way a report can be real JSON and still be about something else: a
    different plan, a different output directory, an older schema, or a run that
    died before it finished deciding.
    """
    if proc.returncode not in (0, 1):
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        signal = f" (killed by signal {-proc.returncode})" if proc.returncode < 0 else ""
        return None, (f"it exited {proc.returncode}{signal}, which is neither pass (0) "
                      f"nor fail (1): {detail[-1] if detail else 'no output'}")
    if not os.path.exists(json_out):
        return None, ("it wrote no JSON report, so there is nothing to read back; the "
                      "run did not reach its own conclusion")
    try:
        with open(json_out, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        return None, f"its JSON report could not be parsed ({type(exc).__name__}: {exc})"
    if not isinstance(payload, dict):
        return None, f"its JSON report is a {type(payload).__name__}, not an object"

    missing = [k for k in _GATE_REQUIRED_KEYS if k not in payload]
    if missing:
        return None, (f"its JSON report is missing {missing}; this is not the schema "
                      f"this check knows how to read, so its verdict cannot be trusted")
    if not isinstance(payload.get("findings"), list):
        return None, "its `findings` is not a list"

    if os.path.abspath(str(payload["plan"])) != plan_path:
        return None, (f"its report is about {payload['plan']!r}, not the plan being "
                      f"checked ({plan_path!r})")
    if os.path.abspath(str(payload["output_dir"])) != os.path.abspath(output_dir):
        return None, (f"its report is about output dir {payload['output_dir']!r}, not "
                      f"{output_dir!r}")

    blocking = [f for f in payload["findings"] if f.get("severity") == "block"]
    if len(blocking) != payload.get("n_blocking"):
        return None, (f"its report counts {payload.get('n_blocking')} blocking finding(s) "
                      f"but lists {len(blocking)}; the file is internally inconsistent")
    if (proc.returncode == 1) != bool(blocking):
        return None, (f"it exited {proc.returncode} while reporting {len(blocking)} "
                      f"blocking finding(s); exit code and report disagree")
    return payload, None


# ─────────────────────────────────────────────────────────────────────────────
# Coverage inventory — the watchdog's C7 input
# ─────────────────────────────────────────────────────────────────────────────

def check_estimate_inventory(report, plan, steps, configs):
    """Produce coverage_diff.json: every estimate executed vs every one reported.

    Run from here because this is the only place that already knows the pipeline
    has finished. `estimate_inventory.py` stays a usable CLI; the computation
    lives in its `build_coverage()` and both entry points call that, so there is
    one implementation rather than a copy that drifts.

    The findings are warnings by design. Which omissions matter is the judgement
    this deliberately leaves to a reader — the script's job is to hand over the
    set difference, so that nobody has to go looking for absences. That is the
    one search where a miss is invisible: a missed omission and a complete
    report produce identical output.
    """
    output_dir = plan["output_dir"]
    try:
        import estimate_inventory
    except ImportError as exc:
        report.block("C7", None,
                     f"estimate_inventory.py could not be imported ({exc}); "
                     f"coverage_diff.json was not produced and the watchdog's C7 has "
                     f"nothing to read")
        return

    # Prefer the manuscript's declared output over a directory sweep: that is the
    # deliverable the coverage question is actually about.
    reported_files = []
    for step in steps:
        if step.get("skill") != "manuscript-results" or step.get("status") == "skipped":
            continue
        declared = declared_output(plan, step, configs)
        if declared and os.path.exists(declared):
            reported_files.append(declared)

    try:
        payload = estimate_inventory.build_coverage(
            output_dir, reported_files or None, quiet=True, plan=plan)
    except ValueError as exc:
        report.block("C7", None,
                     f"the estimate inventory could not be built ({exc}); "
                     f"coverage_diff.json was not produced")
        return
    except Exception as exc:
        report.block("C7", None,
                     f"the estimate inventory failed ({type(exc).__name__}: {exc}); "
                     f"coverage_diff.json was not produced")
        return

    out_path = estimate_inventory.write_coverage(payload, output_dir)
    report.ran()
    counters = payload["counters"]
    status = payload["status"]
    evidence = {"coverage_diff": out_path, "status": status,
                "executed": counters["executed_estimates"],
                "reported": counters["reported_estimates"],
                "omitted": counters["omitted_estimates"],
                "reported_source_files": payload["reported_source_files"]}

    if status != estimate_inventory.STATUS_COMPARED:
        report.warn("C7", None,
                    f"coverage_diff.json written with status={status}: "
                    f"{counters['executed_estimates']} estimate(s) inventoried, but no "
                    f"deliverable could be read, so selective presentation was not "
                    f"assessed. Searched: "
                    f"{payload['reported_source_files'] or 'the default locations'}",
                    evidence)
    elif counters["omitted_estimates"]:
        report.warn("C7", None,
                    f"{counters['omitted_estimates']} of "
                    f"{counters['executed_estimates']} executed estimate(s) do not "
                    f"appear in the deliverable. This is a set difference, not a "
                    f"verdict — the question for a reader is whether the omissions are "
                    f"directionally convenient for the hypothesis. See "
                    f"{os.path.basename(out_path)} :: omitted", evidence)
    else:
        report.info("C7", None,
                    f"every executed estimate ({counters['executed_estimates']}) "
                    f"appears in the deliverable", evidence)


# ─────────────────────────────────────────────────────────────────────────────
# RES-005 / 008 / 012 / 013 / 014 — the Role 3 checks the script layer replaced
# ─────────────────────────────────────────────────────────────────────────────
#
# These five had LLM coverage under the old guardian fan-out and none on the
# default path after it was removed. That is a regression, not a missing
# feature, so the criteria below are transcribed from
# biostats-guardian/references/results-audit.md rather than reinvented.
#
# Every one of them has a "clean input raises nothing" test, because on this
# module a false block has twice been more expensive than the miss it prevented
# (RES-002 firing on PSM's designed subset; the .docx manuscript that could not
# be read reporting every estimate as omitted).

_ID_COLUMN_NAMES = ("subject_id", "patient_id", "record_id", "id", "subjid",
                    "usubjid", "pid", "case_id")

# Stems whose CSVs are summary tables, not subject-level rows.
_NON_SUBJECT_CSV = ("_balance", "_contrast", "coverage_diff", "precheck_report")

_FIGURE_PRODUCING_SKILLS = ("flowchart", "kaplan-meier", "competing-risk",
                            "univariate-forest", "psm-matching", "nonlinearity",
                            "calibration", "weighting")
_MIN_FIGURE_BYTES = 10 * 1024

_PCT_CELL_RE = re.compile(r"^\s*([\d,]+)\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*\)\s*$")
_PCT_WITH_CI_RE = re.compile(
    rf"^\s*(-?\d+(?:\.\d+)?)\s*%\s*\(\s*(-?\d+(?:\.\d+)?)\s*[{_DASHES}]\s*"
    rf"(-?\d+(?:\.\d+)?)\s*\)\s*$")
_TIMEPOINT_HEADER_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-?\s*[A-Za-z]*\s+"
                                  r"(Survival|CIF)\s*%", re.IGNORECASE)
_HEADER_N_RE = re.compile(r"\(\s*n\s*=\s*([\d,]+)\s*\)", re.IGNORECASE)
_R_IDENT_RE = re.compile(r"^[A-Za-z._][A-Za-z0-9._]*$")


def _num(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _sheet_rows(path):
    """{(sheet, row): {col: value}} for one workbook."""
    rows = {}
    for sheet, r, c, value in iter_xlsx_cells(path):
        rows.setdefault((sheet, r), {})[c] = value
    return rows


# ── RES-005 ──────────────────────────────────────────────────────────────────

def check_res005_duplicate_ids(report, plan, steps, configs):
    """RES-005 — a subject-level output must not repeat a subject.

    Conditional by construction ("若輸出含 subject-level CSV"): no shipped skill
    writes one today, and matching is always without replacement. Saying so is
    the point — a precondition that is not met is recorded, not passed over.
    """
    output_dir = plan["output_dir"]
    declared_replacement = any(
        bool((cfg.get("matching") or {}).get("with_replacement")
             or (cfg.get("matching") or {}).get("replacement"))
        for cfg in (configs or {}).values() if isinstance(cfg, dict))

    candidates = []
    for path in sorted(glob.glob(os.path.join(output_dir, "**", "*.csv"), recursive=True)):
        base = os.path.basename(path)
        if any(marker in base for marker in _NON_SUBJECT_CSV):
            continue
        try:
            head = pd.read_csv(path, nrows=0)
        except Exception as exc:
            report.warn("RES-005", None,
                        f"{base} could not be opened to check for duplicate subject ids "
                        f"({type(exc).__name__}: {exc})")
            continue
        id_cols = [c for c in head.columns
                   if str(c).strip().lower().replace(" ", "_") in _ID_COLUMN_NAMES]
        if id_cols:
            candidates.append((path, id_cols[0]))

    if not candidates:
        report.skipped("RES-005",
                       "no subject-level CSV was found in the output directory (no "
                       "shipped skill writes one); there is nothing whose ids could repeat")
        return

    for path, id_col in candidates:
        report.ran()
        try:
            ids = pd.read_csv(path, usecols=[id_col])[id_col]
        except Exception as exc:
            report.block("RES-005", None,
                         f"{os.path.basename(path)} has an id column {id_col!r} that "
                         f"could not be read ({type(exc).__name__}: {exc}); duplicate "
                         f"subjects were not ruled out")
            continue
        dupes = ids[ids.duplicated(keep=False)]
        if dupes.empty:
            report.info("RES-005", None,
                        f"{os.path.basename(path)}: {len(ids)} rows, no repeated "
                        f"{id_col!r}")
        elif declared_replacement:
            report.info("RES-005", None,
                        f"{os.path.basename(path)}: {dupes.nunique()} id(s) repeat, and "
                        f"the config declares matching with replacement")
        else:
            examples = sorted(set(dupes.astype(str)))[:5]
            report.block("RES-005", None,
                         f"{os.path.basename(path)} repeats {dupes.nunique()} value(s) of "
                         f"{id_col!r} across {len(dupes)} rows (e.g. {examples}) and no "
                         f"config declares matching with replacement; the same subject is "
                         f"contributing more than once",
                         {"path": path, "id_column": id_col,
                          "duplicate_ids": examples})


# ── RES-008 ──────────────────────────────────────────────────────────────────

def _curve_table(path):
    """Per-group survival/CIF percentages by time point, from a KM or CR summary.

    Returns {group_label: {"n":, "events_pct":, "median":, "points": {t: pct}},
             ...} plus the kind ("survival" | "cif").
    """
    rows = _sheet_rows(path)
    for (_sheet, _r), cells in sorted(rows.items()):
        labels = {c: str(v) for c, v in cells.items()}
        if not any(labels[c].strip() == "Group" for c in labels):
            continue
        points, kind = {}, None
        median_col = n_col = events_col = None
        for c, text in labels.items():
            flat = text.replace("\n", " ")
            m = _TIMEPOINT_HEADER_RE.match(flat)
            if m:
                points[c] = float(m.group(1))
                kind = m.group(2).lower()
            elif flat.strip() == "N":
                n_col = c
            elif flat.lower().startswith("median"):
                median_col = c
            elif "events" in flat.lower() or flat.lower().startswith(("event", "n (%)")):
                events_col = events_col if events_col is not None else c
        if not points:
            continue
        header_row = _r
        groups = {}
        for (sheet2, r2), data in sorted(rows.items()):
            if sheet2 != _sheet or r2 <= header_row:
                continue
            first = str(data.get(min(data), "")).strip()
            if not first or first.lower().startswith(("log-rank", "cause-specific",
                                                      "gray", "cif estimated",
                                                      "survival estimated")):
                continue
            entry = {"n": _num(data.get(n_col)) if n_col else None,
                     "median": str(data.get(median_col)) if median_col else None,
                     "events_pct": None, "points": {}}
            if events_col is not None:
                m = _PCT_CELL_RE.match(str(data.get(events_col, "")))
                if m:
                    entry["events_pct"] = float(m.group(2))
            for c, t in points.items():
                m = _PCT_WITH_CI_RE.match(str(data.get(c, "")))
                if m:
                    entry["points"][t] = float(m.group(1))
            if entry["points"]:
                groups[first] = entry
        if groups:
            return groups, kind
    return {}, None


def check_res008_curves(report, plan, steps, configs):
    """RES-008 — survival in [0,1] and monotone, CIF + survival <= 1.

    Read from the summary tables the skills actually emit (per-group estimates
    at the declared time points), because that is the only place these numbers
    exist in the deliverable. Rounding to one decimal means comparisons carry a
    0.2 percentage-point tolerance; anything inside that is arithmetic, not a
    finding.
    """
    tol = 0.2
    curves = {}
    for step in steps:
        skill = step.get("skill")
        if skill not in ("kaplan-meier", "competing-risk") or step.get("status") == "skipped":
            continue
        paths = step_output_paths(plan, step, configs)
        if not paths:
            continue
        try:
            groups, kind = _curve_table(paths[0])
        except Exception as exc:
            report.block("RES-008", step["id"],
                         f"the survival table in {os.path.basename(paths[0])} could not "
                         f"be read ({type(exc).__name__}: {exc}); its values were not checked")
            continue
        if not groups:
            report.warn("RES-008", step["id"],
                        f"no per-group estimates could be parsed from "
                        f"{os.path.basename(paths[0])}; monotonicity and range were "
                        f"not checked")
            continue
        curves[(step.get("outcome"), kind)] = (step["id"], groups)

        for label, entry in groups.items():
            report.ran()
            times = sorted(entry["points"])
            for t in times:
                pct = entry["points"][t]
                if not (0.0 - tol <= pct <= 100.0 + tol):
                    report.block("RES-008", step["id"],
                                 f"{kind} at t={t:g} for {label!r} is {pct}%, outside "
                                 f"[0, 100]", {"group": label, "time": t, "percent": pct})
            for earlier, later in zip(times, times[1:]):
                a, b = entry["points"][earlier], entry["points"][later]
                if kind == "survival" and b > a + tol:
                    report.block("RES-008", step["id"],
                                 f"survival for {label!r} rises from {a}% at t={earlier:g} "
                                 f"to {b}% at t={later:g}; a survival curve cannot increase",
                                 {"group": label, "from": [earlier, a], "to": [later, b]})
                if kind == "cif" and b < a - tol:
                    report.block("RES-008", step["id"],
                                 f"cumulative incidence for {label!r} falls from {a}% at "
                                 f"t={earlier:g} to {b}% at t={later:g}; a CIF cannot "
                                 f"decrease",
                                 {"group": label, "from": [earlier, a], "to": [later, b]})
            median = (entry.get("median") or "").strip().upper()
            if kind == "survival" and median in ("NR", "NA", "N/A", "NOT REACHED", "NONE"):
                report.ran()
                pct = entry.get("events_pct")
                if pct is None:
                    report.warn("RES-008", step["id"],
                                f"median survival for {label!r} is {median!r} and the "
                                f"event percentage could not be read, so the stated "
                                f"reason (fewer than 50% had the event) was not verified")
                elif pct >= 50.0:
                    report.block("RES-008", step["id"],
                                 f"median survival for {label!r} is reported as {median!r} "
                                 f"but {pct}% had the event; with more than half the group "
                                 f"having an event the median is reached and must be given",
                                 {"group": label, "events_percent": pct})

    # CIF + survival <= 1 for the same outcome, group and time point.
    for (outcome, kind), (step_id, groups) in curves.items():
        if kind != "cif":
            continue
        partner = curves.get((outcome, "survival"))
        if not partner:
            continue
        km_step, km_groups = partner
        for label, entry in groups.items():
            km_entry = km_groups.get(label)
            if not km_entry:
                continue
            for t, cif in entry["points"].items():
                surv = km_entry["points"].get(t)
                if surv is None:
                    continue
                report.ran()
                if cif + surv > 100.0 + tol:
                    report.block("RES-008", step_id,
                                 f"at t={t:g} for {label!r}, CIF {cif}% + survival "
                                 f"{surv}% = {cif + surv:.1f}%, which exceeds 100%",
                                 {"group": label, "time": t, "cif": cif,
                                  "survival": surv, "km_step": km_step})


# ── RES-012 ──────────────────────────────────────────────────────────────────

def check_res012_figures(report, plan, steps, configs):
    """RES-012 — a figure file that is present but tiny is a failed render.

    The 10 KB floor is a heuristic for blank canvases and aborted renders. It is
    NOT a visual check: a figure can be the right size and still plot the wrong
    variable, and nothing here would notice. The message says so, because a
    reader who believes this verified the picture has been told something false.
    """
    output_dir = plan["output_dir"]
    for step in steps:
        if step.get("status") == "skipped":
            continue
        if step.get("skill") not in _FIGURE_PRODUCING_SKILLS:
            continue
        declared = declared_output(plan, step, configs)
        if not declared:
            continue
        stem = os.path.splitext(os.path.basename(declared))[0]
        figures = sorted(
            p for ext in ("png", "pdf", "svg", "jpg")
            for p in glob.glob(os.path.join(output_dir, "**", f"{stem}*.{ext}"),
                               recursive=True))
        if not figures:
            report.warn("RES-012", step["id"],
                        f"{step.get('skill')} normally writes a figure but no "
                        f"{stem}*.png/pdf is on disk; if the run was expected to "
                        f"produce one it did not")
            continue
        declared_dpi = ((configs or {}).get(step["id"], {}).get("plot_settings")
                        or {}).get("dpi")
        for path in figures:
            report.ran()
            size = os.path.getsize(path)
            if size < _MIN_FIGURE_BYTES:
                report.block("RES-012", step["id"],
                             f"{os.path.basename(path)} is {size} bytes (<10 KB). That "
                             f"size means a blank canvas or an aborted render, not a "
                             f"plot. This is a file-level heuristic only — it does not "
                             f"check what the figure shows",
                             {"path": path, "bytes": size})
                continue
            if declared_dpi and path.lower().endswith((".png", ".jpg")):
                actual = _image_dpi(path)
                if actual and abs(actual - float(declared_dpi)) > 1.0:
                    report.warn("RES-012", step["id"],
                                f"{os.path.basename(path)} is {actual:g} DPI but its "
                                f"config asks for {declared_dpi}; journals reject "
                                f"under-resolution figures at submission",
                                {"path": path, "declared_dpi": declared_dpi,
                                 "actual_dpi": actual})


def _image_dpi(path):
    """Horizontal DPI recorded in the image, or None when it is not stated."""
    try:
        from PIL import Image
    except ImportError:
        print("  [SKIP] RES-012 DPI: pillow is not installed; figure resolution was "
              "not checked (python3 -m pip install pillow)", file=sys.stderr)
        return None
    try:
        with Image.open(path) as img:
            dpi = img.info.get("dpi")
        return float(dpi[0]) if dpi and dpi[0] else None
    except Exception as exc:
        print(f"  [SKIP] RES-012 DPI on {os.path.basename(path)}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return None


# ── RES-013 ──────────────────────────────────────────────────────────────────

def check_res013_table1(report, plan, steps, configs, final_n=None):
    """RES-013 — Table 1 must add up.

    Three properties, all read off the emitted table:
      - the group columns' n must sum to the total column's n;
      - a p-value column must be present exactly when a grouping is declared;
      - every "k (p%)" cell's percentage must match k over its own column's n.

    The third is stated in the criterion as "percentages sum to ~100 within a
    categorical". Checking each cell against its column denominator is the
    stronger form of the same property — it holds for every cell rather than
    only for a complete set of levels, and it needs no guess about which rows
    belong to which variable, which is where a structural reading would start
    inventing false positives.
    """
    for step in steps:
        if step.get("skill") != "table1" or step.get("status") == "skipped":
            continue
        paths = step_output_paths(plan, step, configs)
        if not paths:
            continue
        path = paths[0]
        try:
            rows = _sheet_rows(path)
        except Exception as exc:
            report.block("RES-013", step["id"],
                         f"Table 1 could not be read ({type(exc).__name__}: {exc}); "
                         f"its internal consistency was not checked")
            continue

        header_key = header = None
        for key, cells in sorted(rows.items()):
            if any(str(v).strip() == "Variable" for v in cells.values()):
                header_key, header = key, cells
                break
        if not header:
            report.warn("RES-013", step["id"],
                        f"no 'Variable' header row found in {os.path.basename(path)}; "
                        f"Table 1 consistency was not checked")
            continue

        column_n, total_col, p_col = {}, None, None
        for c, value in header.items():
            flat = str(value).replace("\n", " ")
            m = _HEADER_N_RE.search(flat)
            if m:
                column_n[c] = float(m.group(1).replace(",", ""))
                if flat.strip().lower().startswith("total"):
                    total_col = c
            if flat.strip().lower().startswith(("p-value", "p value")):
                p_col = c

        grouping = ((configs or {}).get(step["id"], {}).get("grouping")
                    or plan.get("grouping") or {})
        has_groups = len(grouping.get("groups") or []) >= 2
        report.ran()
        if has_groups and p_col is None:
            report.block("RES-013", step["id"],
                         f"a grouping is declared ({grouping.get('column')!r}) but "
                         f"Table 1 has no p-value column; the between-group comparison "
                         f"was not reported")
        elif not has_groups and p_col is not None:
            report.block("RES-013", step["id"],
                         "Table 1 carries a p-value column but no grouping is declared; "
                         "there is nothing those p-values compare")

        group_cols = [c for c in column_n if c != total_col]
        if total_col is not None and group_cols:
            report.ran()
            total = column_n[total_col]
            summed = sum(column_n[c] for c in group_cols)
            if abs(summed - total) > 0.5:
                report.block("RES-013", step["id"],
                             f"the group columns hold {summed:g} subjects but the total "
                             f"column says {total:g}; Table 1 does not account for "
                             f"{abs(total - summed):g} of the cohort",
                             {"total": total, "group_total": summed})
            elif final_n and abs(total - final_n) > 0.5:
                report.warn("RES-013", step["id"],
                            f"Table 1 totals {total:g} but the flowchart's final cohort "
                            f"is {final_n}",
                            {"table1_total": total, "flowchart_final_n": final_n})

        # The 'n' row, when present, must agree with the header-declared n.
        for key, cells in sorted(rows.items()):
            if key[1] <= header_key[1] or key[0] != header_key[0]:
                continue
            if str(cells.get(min(cells), "")).strip().lower() != "n":
                continue
            report.ran()
            for c, declared in column_n.items():
                stated = _num(cells.get(c))
                if stated is not None and abs(stated - declared) > 0.5:
                    report.block("RES-013", step["id"],
                                 f"the 'n' row says {stated:g} for the column headed "
                                 f"{str(header[c]).replace(chr(10), ' ')!r}, whose header "
                                 f"declares {declared:g}",
                                 {"row_n": stated, "header_n": declared})
            break

        mismatches = []
        for key, cells in sorted(rows.items()):
            if key[0] != header_key[0] or key[1] <= header_key[1]:
                continue
            label = str(cells.get(min(cells), "")).strip()
            for c, value in cells.items():
                if c not in column_n:
                    continue
                m = _PCT_CELL_RE.match(str(value))
                if not m:
                    continue
                count = float(m.group(1).replace(",", ""))
                stated_pct = float(m.group(2))
                denominator = column_n[c]
                if denominator <= 0:
                    continue
                report.ran()
                expected = 100.0 * count / denominator
                if abs(expected - stated_pct) > 0.15:
                    mismatches.append({
                        "row": label, "cell": str(value),
                        "column_n": denominator, "stated_percent": stated_pct,
                        "implied_percent": round(expected, 2)})
        if mismatches:
            first = mismatches[0]
            report.warn("RES-013", step["id"],
                        f"{len(mismatches)} percentage cell(s) do not match their own "
                        f"column's n — e.g. {first['row']!r} shows {first['cell']!r} but "
                        f"{first['stated_percent']}% of {first['column_n']:g} implies "
                        f"{first['implied_percent']}%. A percentage computed against the "
                        f"wrong denominator is how a subgroup gets reported as the cohort",
                        {"mismatches": mismatches[:10]})


# ── RES-014 ──────────────────────────────────────────────────────────────────
#
# The only external grounding left on the default path. Everything else in this
# module checks the pipeline's output against the pipeline's own inputs; this
# one re-fits the model in a different language, with a different
# implementation, and compares. Li Hung-yi's self-correction trap 2 is the
# argument for keeping it: a tool checking itself corrects errors with errors.
#
# It stays cheap because the deterministic half answers "do the two agree", and
# only a disagreement over threshold is worth an agent — to decide whether it is
# tie-handling, a reference level, or a real coding bug, which are the three
# explanations results-audit.md names and which a numeric comparison cannot
# distinguish.

_CROSS_LANG_SKILLS = ("univariate-forest", "multivariate-interaction")

_R_COX_TEMPLATE = """
d <- read.csv({csv!r}, stringsAsFactors = FALSE)
keep <- c({cols})
d <- d[, keep, drop = FALSE]
d <- d[stats::complete.cases(d), , drop = FALSE]
suppressMessages(library(survival))
fit <- coxph(Surv({time}, {event}) ~ {rhs}, data = d)
s <- summary(fit)
cat("n\\t", s$n, "\\n", sep = "")
cat("events\\t", s$nevent, "\\n", sep = "")
cat("hr\\t", s$conf.int[{target!r}, "exp(coef)"], "\\n", sep = "")
cat("lo\\t", s$conf.int[{target!r}, "lower .95"], "\\n", sep = "")
cat("hi\\t", s$conf.int[{target!r}, "upper .95"], "\\n", sep = "")
cat("p\\t", s$coefficients[{target!r}, "Pr(>|z|)"], "\\n", sep = "")
"""

_R_LOGIT_TEMPLATE = """
d <- read.csv({csv!r}, stringsAsFactors = FALSE)
keep <- c({cols})
d <- d[, keep, drop = FALSE]
d <- d[stats::complete.cases(d), , drop = FALSE]
fit <- glm({event} ~ {rhs}, data = d, family = binomial())
s <- summary(fit)
ci <- suppressMessages(confint.default(fit))
cat("n\\t", nrow(d), "\\n", sep = "")
cat("events\\t", sum(d${event}), "\\n", sep = "")
cat("hr\\t", exp(coef(fit)[{target!r}]), "\\n", sep = "")
cat("lo\\t", exp(ci[{target!r}, 1]), "\\n", sep = "")
cat("hi\\t", exp(ci[{target!r}, 2]), "\\n", sep = "")
cat("p\\t", s$coefficients[{target!r}, "Pr(>|z|)"], "\\n", sep = "")
"""


def _cross_lang_enabled(plan, step, outcome_id):
    """results-audit.md RES-014: quick runs primary only; the flag overrides."""
    guardian = plan.get("guardian") or {}
    flag = guardian.get("cross_lang_check")
    if flag is False:
        return False, "guardian.cross_lang_check is false"
    if flag is True:
        return True, "guardian.cross_lang_check is true"
    mode = str(guardian.get("mode") or "standard").lower()
    if mode == "quick" and outcome_id != "primary":
        return False, "quick mode checks the primary outcome only"
    return True, f"guardian.mode={mode}"


def _python_side(path, covariate_label):
    """The reported HR / CI / N / events for one covariate, from the workbook."""
    for (_sheet, _r), cells in sorted(_sheet_rows(path).items()):
        ordered = [cells[c] for c in sorted(cells)]
        first = str(ordered[0]).strip() if ordered else ""
        if not first.startswith(covariate_label):
            continue
        effect = n_events = None
        for value in ordered:
            if effect is None:
                effect = parse_effect(value)
            if n_events is None:
                n_events = parse_n_events(value)
        if effect:
            return {"hr": effect[0], "lo": effect[1], "hi": effect[2],
                    "n": n_events[0] if n_events else None,
                    "events": n_events[1] if n_events else None}
    return None


def check_res014_cross_language(report, plan, steps, configs):
    """RES-014 — re-fit in R and compare, escalating only on disagreement."""
    rscript = shutil.which("Rscript")
    data_file = (plan.get("study") or {}).get("data_file")

    applicable = [s for s in steps
                  if s.get("skill") in _CROSS_LANG_SKILLS
                  and s.get("status") != "skipped"]
    if not applicable:
        report.skipped("RES-014", "the plan has no regression step to cross-check")
        return
    if not rscript:
        report.skipped("RES-014",
                       "Rscript is not on PATH, so the alternate-language refit did not "
                       "run. This is the only external grounding on the default path; "
                       "without it the pipeline is checking itself. Install R with the "
                       "'survival' package to restore it")
        return

    processed = skipped = 0
    for step in applicable:
        outcome_id = step.get("outcome")
        enabled, why = _cross_lang_enabled(plan, step, outcome_id)
        if not enabled:
            skipped += 1
            report.skipped("RES-014", f"{step['id']}: {why}")
            continue
        config = (configs or {}).get(step["id"]) or {}
        paths = step_output_paths(plan, step, configs)
        if not paths:
            skipped += 1
            report.skipped("RES-014", f"{step['id']}: no output workbook to compare against")
            continue
        outcome = next((o for o in all_outcomes(plan) if o.get("id") == outcome_id), None)
        if not outcome:
            skipped += 1
            report.skipped("RES-014", f"{step['id']}: outcome {outcome_id!r} not in the plan")
            continue

        variables = [v for section in config.get("sections") or []
                     for v in (section.get("variables") or [])]
        # An unscaled covariate maps 1:1 onto an R term and onto a table row.
        # A scaled one reports HR per `scale` units, i.e. HR_R ** scale, which is
        # a correction rather than a comparison; prefer avoiding it.
        target = next((v for v in variables if not v.get("scale")), None)
        scale = 1.0
        if target is None and variables:
            target = variables[0]
            scale = float(target.get("scale") or 1.0)
        if target is None:
            skipped += 1
            report.skipped("RES-014", f"{step['id']}: no covariate to compare")
            continue

        columns = [v.get("column") for v in variables if v.get("column")]
        is_cox = config.get("analysis_type") == "cox"
        settings = config.get("cox_settings") or config.get("logistic_settings") or {}
        time_col = settings.get("time_column")
        event_col = settings.get("event_column") or settings.get("outcome_column")
        needed = [c for c in ([time_col] if is_cox else []) + [event_col] + columns if c]
        bad = [c for c in needed if not _R_IDENT_RE.match(str(c))]
        if bad:
            skipped += 1
            report.skipped("RES-014",
                           f"{step['id']}: column name(s) {bad} are not plain identifiers "
                           f"and were not interpolated into an R script")
            continue

        template = _R_COX_TEMPLATE if is_cox else _R_LOGIT_TEMPLATE
        script = template.format(
            csv=data_file, cols=", ".join(repr(c) for c in needed),
            time=time_col, event=event_col, rhs=" + ".join(columns),
            target=target["column"])
        try:
            proc = subprocess.run([rscript, "--vanilla", "-e", script],
                                  capture_output=True, text=True, timeout=300)
        except Exception as exc:
            skipped += 1
            report.warn("RES-014", step["id"],
                        f"the R refit could not be launched ({type(exc).__name__}: {exc})")
            continue
        if proc.returncode != 0:
            skipped += 1
            report.warn("RES-014", step["id"],
                        f"the R refit exited {proc.returncode} and the comparison did not "
                        f"run: {(proc.stderr or '').strip().splitlines()[-1:] or ['no output']}",
                        {"stderr": proc.stderr[-1500:]})
            continue

        r_side = {}
        for line in proc.stdout.splitlines():
            if "\t" in line:
                key, _, value = line.partition("\t")
                r_side[key.strip()] = _num(value)
        if r_side.get("hr") is None:
            skipped += 1
            report.warn("RES-014", step["id"],
                        f"the R refit produced no hazard ratio for "
                        f"{target['column']!r}; the comparison did not run",
                        {"stdout": proc.stdout[-800:]})
            continue

        py_side = _python_side(paths[0], str(target.get("label") or target["column"]))
        if not py_side:
            skipped += 1
            report.warn("RES-014", step["id"],
                        f"no row for {target.get('label') or target['column']!r} could be "
                        f"read from {os.path.basename(paths[0])}; the R refit ran but had "
                        f"nothing to be compared against")
            continue

        processed += 1
        r_hr = r_side["hr"] ** scale if scale != 1.0 else r_side["hr"]
        rel = abs(r_hr - py_side["hr"]) / abs(r_hr) if r_hr else None
        evidence = {"type": "cross_lang_repro", "step": step["id"],
                    "term": target["column"], "scale_applied": scale,
                    "main_HR_python": py_side["hr"], "alt_HR_R": round(r_hr, 6),
                    "rel_diff_pct": round(rel * 100, 3) if rel is not None else None,
                    "python_n_events": [py_side["n"], py_side["events"]],
                    "R_n_events": [r_side.get("n"), r_side.get("events")],
                    "reproducer": f"Rscript --vanilla -e '<refit of {target['column']}>'"}

        counts_match = True
        for key, py_value in (("n", py_side["n"]), ("events", py_side["events"])):
            r_value = r_side.get(key)
            if py_value is None or r_value is None:
                continue
            if abs(float(py_value) - float(r_value)) > 0.5:
                counts_match = False
        report.ran()

        if not counts_match and (rel or 0) > 0.01:
            report.block("RES-014", step["id"],
                         f"R and Python disagree on both the estimate "
                         f"({r_hr:.4g} vs {py_side['hr']:.4g}, "
                         f"{rel * 100:.2f}%) and the rows they fitted "
                         f"(N/events {r_side.get('n')}/{r_side.get('events')} vs "
                         f"{py_side['n']}/{py_side['events']}); the two are not analysing "
                         f"the same data", evidence)
        elif not counts_match:
            report.warn("RES-014", step["id"],
                        f"the estimates agree but R fitted "
                        f"{r_side.get('n')}/{r_side.get('events')} rows/events against "
                        f"Python's {py_side['n']}/{py_side['events']}; check na.action "
                        f"before reading anything into it", evidence)
        elif rel is not None and rel > 0.05:
            report.block("RES-014", step["id"],
                         f"the R refit gives HR {r_hr:.4g} where the pipeline reports "
                         f"{py_side['hr']:.4g} — a {rel * 100:.1f}% difference on "
                         f"identical rows. Escalate to an adjudicating agent: at this "
                         f"size it is a coding error or a variable-definition mismatch, "
                         f"not tie handling", evidence)
        elif rel is not None and rel > 0.01:
            report.warn("RES-014", step["id"],
                        f"the R refit gives HR {r_hr:.4g} vs the pipeline's "
                        f"{py_side['hr']:.4g} ({rel * 100:.2f}%). Escalate to an agent to "
                        f"say which it is: tied-event handling (Efron vs Breslow) or a "
                        f"categorical reference level pointing the other way. Whichever "
                        f"it is belongs in the methods", evidence)
        else:
            report.info("RES-014", step["id"],
                        f"R and Python agree on {target['column']!r}: HR {r_hr:.4g} vs "
                        f"{py_side['hr']:.4g} ({(rel or 0) * 100:.2f}%), same N and events",
                        evidence)

    print(f"  RES-014: processed {processed} / skipped {skipped} / "
          f"total {processed + skipped} regression step(s)", file=sys.stderr)


def _psm_sidecar_check(report, step, plan, counts, paths, groups, configs=None):
    """Check the producer's own contrast declaration, when it wrote one."""
    artifact = paths[0]
    sidecar, sidecar_path, generic = _psm_contrast_sidecar(artifact)
    if generic:
        report.block("PSM-DIR", step["id"],
                     f"there is no {os.path.basename(os.path.splitext(artifact)[0])}"
                     f"_contrast.json for {os.path.basename(artifact)}, but a generic "
                     f"{os.path.basename(generic)} exists. It is not known to describe "
                     f"this table — with more than one PSM step, or one left from an "
                     f"earlier run, it describes a different analysis — so it is refused "
                     f"rather than used",
                     {"artifact": artifact, "unbound_sidecar": generic})
        return
    if sidecar is None:
        report.warn("PSM-DIR", step["id"],
                    f"no {os.path.basename(os.path.splitext(artifact)[0])}_contrast.json "
                    f"beside {os.path.basename(artifact)}. That sidecar is the producer's "
                    f"own statement of which arm the estimate is about, computed from the "
                    f"dataframe the model was fitted on; without it the contrast can only "
                    f"be inferred from the table layout. Outputs produced before the "
                    f"sidecar existed are accepted for now")
        return

    report.ran()
    # Binding: the sidecar must name this table, hash to this table, and come
    # from the config that produced it. Any one of the three failing means the
    # file is about something else.
    declared_table = sidecar.get("table_basename")
    declared_hash = sidecar.get("table_sha256")
    if declared_table is None and declared_hash is None:
        report.warn("PSM-DIR", step["id"],
                    f"{os.path.basename(sidecar_path)} predates the binding fields "
                    f"(table_basename / table_sha256 / config_sha256), so it cannot be "
                    f"shown to describe {os.path.basename(artifact)}. It was NOT used to "
                    f"verify the contrast; re-run the psm-matching step to regenerate it",
                    {"sidecar": sidecar_path})
        return
    if declared_table and declared_table != os.path.basename(artifact):
        report.block("PSM-DIR", step["id"],
                     f"{os.path.basename(sidecar_path)} says it describes "
                     f"{declared_table!r}, but it sits beside "
                     f"{os.path.basename(artifact)}",
                     {"sidecar": sidecar_path, "declared_table": declared_table})
        return
    actual_hash = _file_sha256(artifact)
    if declared_hash and actual_hash and declared_hash != actual_hash:
        report.block("PSM-DIR", step["id"],
                     f"{os.path.basename(sidecar_path)} was written for a different "
                     f"version of {os.path.basename(artifact)} (sha256 "
                     f"{str(declared_hash)[:12]}… vs {actual_hash[:12]}…). One of the two "
                     f"has been regenerated since; the sidecar does not describe the "
                     f"table on disk",
                     {"sidecar": sidecar_path, "declared_sha256": declared_hash,
                      "actual_sha256": actual_hash})
        return
    declared_config = sidecar.get("config_sha256")
    config_path = None
    for entry_id, cfg in (configs or {}).items():
        if entry_id == step["id"]:
            config_path = (cfg or {}).get("_config_path")
    config_path = config_path or os.path.join(
        plan["output_dir"], "configs", f"{step['id']}_config.json")
    if declared_config and os.path.exists(config_path):
        actual_config = _file_sha256(config_path)
        if actual_config and declared_config != actual_config:
            # Warning, not a block, and deliberately so: the table hash above
            # already proves this sidecar describes this exact workbook, which is
            # the whole independence property. A config that changed afterwards
            # (a regenerated path, a `--only` rerun) does not make the sidecar
            # wrong about the table, and blocking on it would be a false positive
            # with a benign and common cause.
            report.warn("PSM-DIR", step["id"],
                        f"{os.path.basename(sidecar_path)} was produced from a different "
                        f"{os.path.basename(config_path)} (sha256 "
                        f"{str(declared_config)[:12]}… vs {actual_config[:12]}…). The "
                        f"table hash still matches, so the contrast is about this table; "
                        f"the config has been regenerated since the run",
                        {"sidecar": sidecar_path, "config": config_path})
    declared_value = sidecar.get("exposed_value")
    expected_value = groups[0].get("value")
    if declared_value is not None and expected_value is not None:
        same = (declared_value == expected_value
                or str(declared_value) == str(expected_value))
        if not same:
            report.block("PSM-DIR", step["id"],
                         f"{os.path.basename(sidecar_path)} says the estimate is about "
                         f"exposed_value={declared_value!r}, but "
                         f"grouping.groups[0].value is {expected_value!r}. The producer "
                         f"fitted a different contrast from the one the plan declares",
                         {"sidecar": sidecar_path, "declared": declared_value,
                          "expected": expected_value})
            return

    side_counts = sidecar.get("exposed") or {}
    if counts and side_counts.get("n") is not None:
        table_n, table_e = counts["exposed"]
        if (int(side_counts.get("n", -1)) != table_n
                or int(side_counts.get("events", -1)) != table_e):
            report.block("PSM-DIR", step["id"],
                         f"{os.path.basename(sidecar_path)} reports the exposed arm as "
                         f"{side_counts.get('events')}/{side_counts.get('n')} but the "
                         f"table reports {table_e}/{table_n}. The arm the model was "
                         f"fitted on is not the arm the table displays",
                         {"sidecar": sidecar_path, "sidecar_exposed": side_counts,
                          "table_exposed": counts["exposed"]})
            return
    report.info("PSM-DIR", step["id"],
                f"producer sidecar agrees with the table "
                f"({os.path.basename(sidecar_path)})")


# ─────────────────────────────────────────────────────────────────────────────
# success_criteria driver
# ─────────────────────────────────────────────────────────────────────────────

def _max_post_match_smd(output_path):
    """Largest post-matching standardised mean difference, from the balance CSV.

    psm_matching.py writes `<stem>_balance.csv` alongside the workbook with an
    `SMD After` column. Reading it is what turns the documented criterion
    `smd_max < 0.1` from "not evaluated" into an actual assertion.
    """
    stem = os.path.splitext(output_path)[0]
    path = f"{stem}_balance.csv"
    if not os.path.exists(path):
        return None
    try:
        balance = pd.read_csv(path)
    except Exception as exc:
        print(f"  [SKIP] RES-004 smd_max: cannot read {os.path.basename(path)} "
              f"({type(exc).__name__}: {exc})", file=sys.stderr)
        return None
    col = next((c for c in balance.columns if "smd" in str(c).lower()
                and "after" in str(c).lower()), None)
    if col is None:
        print(f"  [SKIP] RES-004 smd_max: {os.path.basename(path)} has no "
              f"'SMD After' column", file=sys.stderr)
        return None
    values = pd.to_numeric(balance[col], errors="coerce").dropna()
    return float(values.max()) if len(values) else None


def build_metrics(plan, step, df_filtered, per_step_n, final_n, epv_results, stage,
                  configs=None):
    """Assemble the metric namespace one step's success_criteria are evaluated in.

    Metrics that this stage genuinely cannot know are left absent, which makes
    the evaluator return 'unknown' — reported as a warning, never as a pass.
    """
    metrics = {}
    outcome_id = step.get("outcome")
    outcome = next((o for o in all_outcomes(plan) if o.get("id") == outcome_id), None)

    metrics["sample_size"] = per_step_n.get(step["id"]) or (final_n if stage == "post" else len(df_filtered))
    if final_n is not None:
        metrics["final_n"] = final_n
    elif stage == "pre":
        metrics["final_n"] = len(df_filtered)

    if outcome is not None:
        counts = events_by_group(df_filtered, plan, outcome)
        if counts:
            metrics["events_per_group"] = min(counts.values())
            metrics["events"] = sum(counts.values())

    sizes = [int(m.sum()) for _label, m in group_masks(df_filtered, plan)]
    if sizes:
        metrics["groups_have_data"] = all(s > 0 for s in sizes)
        metrics["cell_count"] = min(sizes)

    if epv_results and outcome_id in epv_results:
        metrics["epv"] = epv_results[outcome_id]["epv"]

    if stage == "post":
        paths = step_output_paths(plan, step, configs)
        metrics["input_files_exist"] = bool(paths)
        if paths:
            try:
                effects, _pvals, ns, _unparsed = scan_output_numbers(paths[0])
            except Exception as exc:
                # Degrading to empty lists here is what turns "the workbook could
                # not be read" into "no metric was available", which the criteria
                # loop then has to block on. Keep the reason on the terminal so
                # that block is legible.
                print(f"  [SKIP] RES-004 {step['id']}: cannot read output "
                      f"({type(exc).__name__}: {exc})", file=sys.stderr)
                effects, ns = [], []
            # Ratio-scale only: `hr_is_finite` and `ci_width` are statements about
            # the hazard/odds ratio. A log-scale `Coefficient` column reports no
            # CI of its own, so folding it in made ci_high NaN and failed
            # `hr_is_finite == true` on models whose HRs were all finite.
            ratio_effects = [e for e in effects if e.get("scale", "ratio") == "ratio"]
            if ratio_effects:
                metrics["hr_is_finite"] = all(
                    math.isfinite(e["estimate"]) and math.isfinite(e["ci_high"])
                    for e in ratio_effects)
                metrics["ci_width"] = max(e["ci_high"] - e["ci_low"] for e in ratio_effects)
            if ns:
                metrics["matched_pairs"] = min(x["n"] for x in ns)
            smd = _max_post_match_smd(paths[0])
            if smd is not None:
                metrics["smd_max"] = smd
            blocking_qc = [w for w in step.get("qc_warnings") or []
                           if "converg" in w.lower() or "singular" in w.lower()]
            metrics["model_converged"] = not blocking_qc
    return metrics


def check_success_criteria(report, plan, steps, df_filtered, per_step_n, final_n,
                           epv_results, stage, configs=None):
    """RES-004 — evaluate the success_criteria mini-DSL instead of eyeballing it.

    Severity handling, stated once because it is the whole point of the check:

      - an invalid criterion is a plan defect, and is blocking at every stage.
        A criterion nobody can evaluate is worse than no criterion, because it
        looks like a guarantee in the plan and enforces nothing.
      - at the post stage a blocking-severity criterion must come out `pass`.
        Anything else — failed, unevaluable, unparsable — blocks. "The workbook
        was missing so we could not tell whether the model converged" is not a
        reason to continue to the manuscript.
      - at the pre stage a criterion about output that does not exist yet is
        expected to be unevaluable, and is only recorded.
    """
    evaluated = unevaluable = 0
    results = {}
    for step in steps:
        if step.get("status") == "skipped":
            continue
        criteria = step.get("success_criteria") or []
        declares_output = bool(declared_output(plan, step, configs))
        if not criteria:
            if declares_output:
                report.ran()
                report.warn("RES-004", step["id"],
                            "step produces an output but declares no success_criteria, "
                            "so nothing about its result is asserted")
            continue
        if declares_output and not any(
                str(c.get("severity", "")).lower().startswith("block") for c in criteria):
            report.ran()
            report.warn("RES-004", step["id"],
                        f"all {len(criteria)} success criteria are warning-severity; "
                        f"no result from this step can stop the pipeline")

        metrics = build_metrics(plan, step, df_filtered, per_step_n, final_n,
                                epv_results, stage, configs)
        step_results = []
        for crit in criteria:
            expr = crit.get("check")
            severity = (crit.get("severity") or "warning").lower()
            blocking = severity.startswith("block")
            outcome, detail = evaluate_criterion(expr, metrics)
            report.ran()
            step_results.append({"check": expr, "severity": severity,
                                 "outcome": outcome, "detail": detail})
            if outcome == EVAL_PASS:
                evaluated += 1
            elif outcome == EVAL_FAIL:
                evaluated += 1
                msg = f"success criterion failed: {expr} ({detail})"
                emit = report.block if blocking else report.warn
                emit("RES-004", step["id"], msg, {"check": expr, "detail": detail})
            elif outcome == EVAL_UNKNOWN:
                unevaluable += 1
                msg = (f"success criterion not evaluated at stage={stage}: "
                       f"{expr} ({detail})")
                if stage == "post" and blocking:
                    report.block("RES-004", step["id"],
                                 f"{msg} — a blocking criterion that cannot be evaluated "
                                 f"after the run is an unmet criterion, not a passed one",
                                 {"check": expr, "detail": detail})
                elif stage == "pre":
                    report.info("RES-004", step["id"], msg, {"check": expr})
                else:
                    report.unknown("RES-004", step["id"], msg, {"check": expr})
            else:
                unevaluable += 1
                report.block("RES-004", step["id"],
                             f"success criterion is not valid DSL and can never be "
                             f"evaluated: {expr!r} ({detail}). It must be a single "
                             f"comparison, e.g. 'events_per_group >= 5'",
                             {"check": expr, "detail": detail})
        results[step["id"]] = {"metrics": {k: _jsonable(v) for k, v in metrics.items()},
                               "criteria": step_results}
    total = evaluated + unevaluable
    print(f"  RES-004: processed {evaluated} / skipped {unevaluable} / total {total} criteria",
          file=sys.stderr)
    return results


def _jsonable(value):
    if isinstance(value, (bool, int, float, str)) or value is None:
        return value
    return str(value)


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

def enabled_steps(plan):
    """Pipeline steps that are expected to run (and therefore to have a config)."""
    return [s for s in (plan.get("pipeline") or [])
            if s.get("status") != "skipped" and s.get("id")]


def load_configs(plan, report, configs_dir=None):
    """Load every generated config from <configs_dir>/manifest.json.

    The manifest is required evidence, not an optional convenience. Without it
    COL-001/002/003 have nothing to check, and a run that checks nothing has to
    say so as a blocker: "no configs were audited" and "the configs are fine"
    must not produce the same exit code.
    """
    configs_dir = configs_dir or os.path.join(plan["output_dir"], "configs")
    manifest_path = os.path.join(configs_dir, "manifest.json")
    configs = {}
    expected = {s["id"] for s in enabled_steps(plan)}

    if not os.path.exists(manifest_path):
        report.block("COL-001", None,
                     f"no config manifest at {manifest_path}; nothing to audit. "
                     f"Run generate_configs.py before the pre-check",
                     {"manifest_path": manifest_path, "expected_steps": sorted(expected)})
        return configs

    manifest = load_json(manifest_path, "config manifest")
    entries = manifest.get("configs") or []
    if not entries:
        report.block("COL-001", None,
                     f"config manifest {manifest_path} lists zero configs while the plan "
                     f"declares {len(expected)} step(s); the column checks would pass by "
                     f"having nothing to look at",
                     {"expected_steps": sorted(expected)})
        return configs

    loaded = failed = 0
    for entry in entries:
        path = entry.get("config_path")
        try:
            with open(path, "r", encoding="utf-8") as f:
                configs[entry["step_id"]] = json.load(f)
            loaded += 1
        except Exception as exc:
            failed += 1
            report.block("COL-001", entry.get("step_id"),
                         f"config could not be read ({type(exc).__name__}: {exc})",
                         {"path": path})

    missing = sorted(expected - set(configs))
    if missing:
        report.block("COL-001", None,
                     f"{len(missing)} enabled pipeline step(s) have no config in the "
                     f"manifest and were therefore not audited: {', '.join(missing)}. "
                     f"Re-run generate_configs.py",
                     {"missing_steps": missing, "manifest_path": manifest_path})
    extra = sorted(set(configs) - expected)
    if extra:
        report.warn("COL-001", None,
                    f"the manifest carries {len(extra)} config(s) with no matching enabled "
                    f"step: {', '.join(extra)}; they are stale or the plan changed",
                    {"orphan_configs": extra})

    print(f"  configs: processed {loaded} / skipped {failed + len(missing)} / total "
          f"{loaded + failed + len(missing)}", file=sys.stderr)
    return configs


def run(plan_path, stage, report_path=None, quiet=False, configs_dir=None):
    plan = load_json(plan_path, "research_plan.json")
    for key in ("output_dir", "study", "pipeline"):
        if key not in plan:
            _cannot_run(f"research_plan.json is missing {key!r}; cannot pre-check")
    data_file = (plan.get("study") or {}).get("data_file")
    if not data_file or not os.path.exists(data_file):
        _cannot_run(f"dataset not found: {data_file!r} (study.data_file)")

    report = Report(quiet=quiet)
    print(f"precheck_configs.py — stage={stage} plan={plan_path}", file=sys.stderr)

    try:
        df_raw = load_dataframe(data_file)
    except Exception as exc:
        _cannot_run(f"cannot read dataset {data_file}: {type(exc).__name__}: {exc}")

    configs = load_configs(plan, report, configs_dir)
    steps = plan.get("pipeline") or []

    check_col001(report, plan, configs, df_raw)
    check_col002_col003(report, plan, configs, df_raw)

    df_filtered, cohort_ok = apply_population(df_raw, plan, report)
    epv_results, suggestions = None, []
    per_step_n, final_n, criteria_results = {}, None, {}

    if not cohort_ok:
        # Everything below this point describes a cohort. Running those checks on
        # a cohort already known to be wrong produces numbers that read like
        # findings — an n, a missingness rate, an EPV — computed over rows that
        # should not be there. Stop, and name the checks that did not run.
        for check_id in ("COL-005", "RES-006", "REFLECT", "RES-004", "RES-001",
                         "RES-002", "PSM-DIR"):
            report.skipped(check_id, "the cohort could not be constructed as specified; "
                                     "this check would describe the wrong set of rows")
    else:
        check_col005(report, plan, df_raw, df_filtered)
        epv_results = check_epv(report, plan, df_filtered, stage, configs)
        suggestions = check_stage_reflector(report, plan, df_filtered, epv_results)

        if stage == "post":
            check_output_artifacts(report, plan, steps, configs)
            per_step_n, final_n = check_res001_res002(report, plan, steps, configs)
            check_psm_direction(report, plan, df_filtered, steps, configs)
            check_res005_duplicate_ids(report, plan, steps, configs)
            check_res008_curves(report, plan, steps, configs)
            check_res012_figures(report, plan, steps, configs)
            check_res013_table1(report, plan, steps, configs, final_n)
            check_res014_cross_language(report, plan, steps, configs)
            check_ph_remedy_gate(report, plan, plan_path, steps, plan["output_dir"])
            check_estimate_inventory(report, plan, steps, configs)

        criteria_results = check_success_criteria(
            report, plan, steps, df_filtered, per_step_n, final_n, epv_results, stage,
            configs)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "plan_path": os.path.abspath(plan_path),
        "stage": stage,
        "counters": report.counters,
        "n_blocking": report.n_blocking,
        "n_warning": report.n_warning,
        "cohort": {"raw_rows": len(df_raw), "after_population": len(df_filtered),
                   "flowchart_final_n": final_n},
        "epv": epv_results or {},
        "reflector_suggestions": suggestions,
        "success_criteria": criteria_results,
        "skipped_checks": report.skips,
        "issues": report.issues,
    }
    out_path = report_path or os.path.join(plan["output_dir"], "precheck_report.json")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\nprecheck: {report.n_blocking} blocking / {report.n_warning} warning / "
          f"{report.counters['checks_run']} checks run "
          f"({report.counters['checks_skipped']} skipped)", file=sys.stderr)
    print(f"Report written: {out_path}", file=sys.stderr)
    return 1 if report.n_blocking else 0


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic pre-flight / post-flight checks for a research_plan.json "
                    "pipeline (COL-001/002/003/005, RES-001/002/004/006, PSM direction, "
                    "EPV, Stage Reflector).")
    # The plan can be given positionally or as --plan, and the report as --report
    # or --out, because biostats-guardian's integration.md documents the flag
    # form. Two spellings of one argument is a smaller cost than a documented
    # command that does not run.
    parser.add_argument("plan_pos", nargs="?", metavar="PLAN",
                        help="Path to research_plan.json")
    parser.add_argument("--plan", dest="plan_opt", help="Path to research_plan.json")
    parser.add_argument("--stage", choices=("pre", "post"), default="pre",
                        help="pre = before run_pipeline.py (config + data only); "
                             "post = after, adds output-dependent checks")
    parser.add_argument("--configs", dest="configs_dir",
                        help="Directory holding the generated configs and manifest.json "
                             "(default <output_dir>/configs)")
    parser.add_argument("--report", "--out", dest="report",
                        help="Where to write the JSON report "
                             "(default <output_dir>/precheck_report.json)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress [QC_INFO] lines; blocking and warning lines always print")
    args = parser.parse_args()

    plan_path = args.plan_opt or args.plan_pos
    if not plan_path:
        parser.print_usage(sys.stderr)
        _cannot_run("no plan given: pass research_plan.json positionally or with --plan")
    if not os.path.exists(plan_path):
        _cannot_run(f"research_plan.json not found: {plan_path}")
    if args.configs_dir and not os.path.isdir(args.configs_dir):
        _cannot_run(f"--configs is not a directory: {args.configs_dir}")
    return run(plan_path, args.stage, args.report, args.quiet, args.configs_dir)


if __name__ == "__main__":
    sys.exit(main())
