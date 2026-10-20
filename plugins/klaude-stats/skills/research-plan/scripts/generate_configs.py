#!/usr/bin/env python3
"""Generate sub-skill JSON configs from a research_plan.json."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
from datetime import datetime


def _normalize_outcome_type(t):
    """Normalize outcome type to canonical form.

    Canonical values: "time_to_event", "competing_risk", "binary".
    Accepted aliases (mapped to canonical):
      - "time-to-event" → "time_to_event"
      - "competing-risk" → "competing_risk"
    Hyphen aliases exist because plan_template.md older tables used hyphen
    form; users copying that style would otherwise silently mis-route to
    logistic regression on `==` exact-string match.

    Raises ValueError on unknown values rather than falling through.
    """
    if t in ("time_to_event", "time-to-event"):
        return "time_to_event"
    if t in ("competing_risk", "competing-risk"):
        return "competing_risk"
    if t == "binary":
        return "binary"
    raise ValueError(
        f"Unknown outcome type: {t!r}. Expected one of: "
        f"'time_to_event' / 'time-to-event' / 'competing_risk' / "
        f"'competing-risk' / 'binary'."
    )


# Outcome types that have time + event columns (Cox / cause-specific routing).
# Generic regression / PSM / AUC code should route both to the cox branch;
# competing-risk-specific Fine-Gray subdistribution analysis lives only in
# gen_competing_risk. Other generators emit a stderr WARN if they receive a
# competing_risk primary, since cause-specific Cox treats the competing event
# as censoring (suboptimal for competing-risk causal inference).
_TIME_TO_EVENT_TYPES = ("time_to_event", "competing_risk")

# Plan schema generation. Bumped when this generator starts reading fields an
# older plan cannot have. Absent == "written before 2026-08-11"; such a plan is
# still generated from (every new field is optional with a stated default), it
# just does not get the opt-in behaviours that would restructure its pipeline.
# `--migrate` is what raises it, and it is the only place plan fields are added.
PLAN_SCHEMA_VERSION = 2

# Methodological substitutions this generator makes on the user's behalf.
# A stderr line disappears with the terminal scrollback, but these decisions
# belong in the SAP, the decision log and the manuscript's limitations — so they
# are also persisted into configs/manifest.json under "methodological_warnings".
METHOD_WARNINGS = []

# Step whose generator is currently running, so a warning raised inside a
# generator can say which step it belongs to. Without it a selective re-run
# (`--only`) cannot tell which of the previous run's warnings it has just
# superseded and which it must carry forward — see merge_method_warnings().
_CURRENT_STEP_ID = None

# Set while a hypothetical pipeline is projected onto a COPY of the plan (the
# "here is what --migrate would add" preview). Those warnings describe a run
# that is not happening; printing them beside the real ones would report a
# substitution that was never made.
_SUPPRESS_WARN = False


def _abort(message, code=1):
    """Stop the run, in a way BOTH kinds of consumer can see.

    Two prefixes for one condition was a real defect, not untidiness. Callers of
    these scripts split into two families: some read exit codes, some scan
    stderr for `[QC_*]` findings and count them. A line prefixed only `[FATAL]`
    is invisible to the second family — precheck_configs hit exactly this, where
    its `[FATAL]` line was dropped by a caller collecting QC lines and the run
    was logged as `exit 1 — 0 blocking / 0 warning`: confidently silent. And a
    grep for either prefix alone misses half this file's terminating paths.

    Every abort therefore carries BOTH markers. What is deliberately NOT changed
    is the exit code: in this file `sys.exit("<string>")` means exit 1 ("the
    plan is not usable"), and 2 is reserved for "a step names a skill with no
    generator". precheck_configs uses the opposite convention (2 = cannot run);
    three downstream files depend on the current behaviour of each, so the
    prefixes are unified and the codes are left alone.
    """
    text = f"[QC_BLOCKING] [FATAL] {message}"
    if code == 1:
        sys.exit(text)                 # prints to stderr, exits 1
    print(text, file=sys.stderr)
    sys.exit(code)


def _method_warn(kind, message):
    """Record a methodological substitution and echo it to stderr."""
    if _SUPPRESS_WARN:
        return
    METHOD_WARNINGS.append({"kind": kind, "message": message,
                            "step_id": _CURRENT_STEP_ID})
    print(f"  [METHOD_WARNING] {message}", file=sys.stderr)


def _warn_competing_risk_in_generic(skill, primary_type):
    """Record the cause-specific-Cox substitution for a competing_risk primary.

    Applies to psm / auc / univariate-forest / multivariate-interaction. Not
    blocking — cause-specific Cox may be the deliberate choice when the question
    is etiologic rather than absolute-risk — but it must be a *recorded* choice.
    """
    if primary_type == "competing_risk":
        _method_warn(
            "competing_risk_routed_to_cause_specific",
            f"{skill}: primary outcome type='competing_risk' is routed via "
            f"cause-specific Cox (the competing event is treated as censoring). "
            f"This estimates an etiologic hazard, not absolute risk. For "
            f"subdistribution (Fine-Gray) hazards use the competing-risk skill "
            f"directly. Record this choice in decision_log.md and state it in "
            f"the manuscript's statistical methods.",
        )


# The only flag names this generator understands. Anything else in a bare list
# is refused rather than ignored: a substring match over free text read
# "no_time_varying_detected" as a detected time-varying exposure, and read
# {"competing_risk": {"detected": false}} the same way — the negation was never
# looked at. A gate that fires on a report saying the opposite trains whoever
# reads it to fill in an override reflexively, which is worse than no gate.
_CANONICAL_FLAGS = {
    "competing_risk": "competing_risk",
    "competing_risks": "competing_risk",
    "left_truncation": "left_truncation",
    "delayed_entry": "left_truncation",
    "time_varying": "time_varying",
    "time_varying_exposure": "time_varying",
    "time_dependent_exposure": "time_varying",
    "clustering": "clustering",
    "cluster": "clustering",
    # Known checks this generator does NOT gate on. Named so they are quietly
    # accepted instead of being reported as unrecognised.
    "informative_censoring": "informative_censoring",
    "proportional_hazards": "proportional_hazards",
    "ph_violation": "proportional_hazards",
    "non_proportional_hazards": "proportional_hazards",
}


def _canonical_flag(name):
    """Map one flag name onto its canonical form, or None when unrecognised."""
    key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    key = key.removeprefix("checks.").removeprefix("check_")
    return _CANONICAL_FLAGS.get(key)


def _normalize_diagnostic_flags(plan):
    """`diagnostics.flags_detected` as {canonical_flag: {detected, risk}}.

    Three shapes have been written into plans over time and all three are read,
    but each one is read for its VALUE rather than for the presence of a key:

      ["clustering"]                       -> detected, no risk grade
      {"clustering": true/false}           -> the boolean is obeyed
      {"clustering": {"detected": false}}  -> the boolean is obeyed

    Raises ValueError on anything it cannot read — an unrecognised flag name, a
    detected value that is not a boolean, a list entry that is not a known flag.
    Guessing here means guessing about competing risks and delayed entry.
    """
    diag = plan.get("diagnostics") or {}
    flags = diag.get("flags_detected")
    out, problems = {}, []
    if flags is None:
        return out
    if isinstance(flags, dict):
        items = list(flags.items())
    elif isinstance(flags, (list, tuple)):
        # A bare list carries no negations, so every entry means "detected".
        # That is exactly why an unknown entry cannot be shrugged off: a report
        # whose wording happens to include a flag name would be read as the
        # finding itself.
        items = [(f, True) for f in flags]
    else:
        raise ValueError(
            f"diagnostics.flags_detected must be a list of flag names or a "
            f"{{flag: …}} object; got {type(flags).__name__}.")
    for raw_key, val in items:
        canon = _canonical_flag(raw_key)
        if canon is None:
            problems.append(
                f"unrecognised flag {raw_key!r} (known: "
                f"{', '.join(sorted(set(_CANONICAL_FLAGS.values())))})")
            continue
        risk = None
        if isinstance(val, dict):
            detected = val.get("detected")
            risk = val.get("risk")
            risk = str(risk).strip().lower() if risk is not None else None
        else:
            detected = val
        if not isinstance(detected, bool):
            problems.append(
                f"flag {raw_key!r}: 'detected' must be true or false, got "
                f"{detected!r}. A missing or non-boolean value used to be read as "
                f"'detected'.")
            continue
        entry = out.setdefault(canon, {"detected": False, "risk": None})
        # Several aliases of one flag: detected wins, and so does the graded risk.
        entry["detected"] = entry["detected"] or detected
        if risk is not None:
            entry["risk"] = risk
    if problems:
        raise ValueError("; ".join(problems))
    return out


def _diagnostics_flagged(plan, needle):
    """True when the diagnostics recorded `needle` as DETECTED.

    `needle` is a canonical flag name. Kept as a helper because gen_missing_data
    also asks about clustering (protocol §6 grades single-level imputation by
    the provenance of that finding).
    """
    diag = plan.get("diagnostics") or {}
    if str(diag.get("mode", "")).strip().lower() == "off":
        return False
    try:
        flags = _normalize_diagnostic_flags(plan)
    except ValueError:
        # Unreadable flags are refused by _validate_diagnostics_honored with a
        # message; this helper must not answer "no clustering" on the way there.
        return False
    return bool(flags.get(needle, {}).get("detected"))


def _diagnostics_flag_risk(plan, needle):
    """The risk grade attached to a detected flag, or None when ungraded."""
    try:
        return _normalize_diagnostic_flags(plan).get(needle, {}).get("risk")
    except ValueError:
        return None


def _diagnostics_declared(plan):
    """True when the plan carries a diagnostics block at all.

    A plan written before Step 3.5 existed has no block. That is a different
    fact from "Step 3.5 ran and found nothing", and the two must not produce the
    same behaviour: the first needs the diagnostics run (or an explicit
    override), the second is a clean bill of health.
    """
    return isinstance(plan.get("diagnostics"), dict) and bool(plan["diagnostics"])


# `diagnostics.mode` is a closed set. It used to be "anything that is not 'off'
# counts as ran", which let `{"mode": "not_run", "flags_detected": []}` — a
# literal statement that nothing has been run — satisfy the gate that exists to
# require the run. Aliases are accepted because Step 3.5 has written "on"; a
# value outside this table is refused.
_DIAG_MODES = {
    "completed": "completed", "on": "completed", "done": "completed",
    "ran": "completed", "complete": "completed",
    "off": "off", "not_applicable": "off", "n/a": "off",
}


def _diagnostics_mode(plan):
    """Canonical diagnostics.mode. Raises ValueError on an unknown value."""
    raw = (plan.get("diagnostics") or {}).get("mode")
    if raw is None:
        return None
    mode = _DIAG_MODES.get(str(raw).strip().lower())
    if mode is None:
        raise ValueError(
            f"diagnostics.mode = {raw!r} is not a value this generator accepts. "
            f"Use \"completed\" (Step 3.5 ran; the block must then carry "
            f"report_path and completed_at) or \"off\" (it does not apply; the "
            f"block must then carry an override_reason with a decision_log.md ID). "
            f"Values like 'not_run' or 'pending' describe the absence of a run and "
            f"cannot stand in for one.")
    return mode


def _data_fingerprint(path):
    """sha256 (16 hex) of the dataset, or None when it cannot be read.

    Used to tell "the diagnostics ran on this data" from "the diagnostics ran on
    something, and the data has been rebuilt since".
    """
    try:
        h = hashlib.sha256()
        with open(os.path.expanduser(path), "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:16]
    except OSError as exc:
        print(f"  [WARN] could not fingerprint the dataset ({path}): {exc}",
              file=sys.stderr)
        return None


# --- schema v2 fields -------------------------------------------------------
# Every field below is optional. Two locations are accepted for each:
#   canonical  — inside `study` (what Step 3 writes for a NEW plan)
#   alias      — a top-level key of the same name
# The alias exists for one concrete reason: reviewer_challenge.plan_fingerprint()
# hashes `study` (and eight sibling blocks) but NOT unknown top-level keys, so
# `--migrate` can add these to a live project without invalidating a
# reviewer challenge that cost ten Opus agents and three hours. Which of them
# *should* invalidate a challenge is a judgement recorded in the sync notes, not
# something this file can decide on its own.
def _schema_field(plan, key):
    """Resolve a schema-v2 field from study.<key>, else the top-level alias."""
    val = (plan.get("study") or {}).get(key)
    if val is None:
        val = plan.get(key)
    return val


def _estimand_type(plan):
    """Normalised causal-vs-associational estimand, or None when unstated.

    Legacy plans carry `estimand` / `study.estimand` as a *dict* describing the
    PICO in prose (population / exposure / summary_measure). That is not this
    field and is deliberately not read as one: guessing "causal" from the
    presence of prose is exactly the silent mis-routing _normalize_outcome_type
    exists to prevent. Only an explicit string counts.
    """
    raw = _schema_field(plan, "estimand_type")
    if raw is None:
        legacy = _schema_field(plan, "estimand")
        raw = legacy if isinstance(legacy, str) else None
    if raw is None:
        return None
    s = str(raw).strip().lower().replace("-", "_")
    if s in ("causal", "causal_effect"):
        return "causal"
    if s in ("associational", "association", "descriptive", "etiologic_association"):
        return "associational"
    if s in ("unspecified", "unknown", ""):
        return None
    raise ValueError(
        f"Unknown estimand_type: {raw!r}. Expected 'causal' or 'associational' "
        f"(or omit the field, which means 'unspecified')."
    )


def _normalize_model_purpose(raw):
    """'prediction' / 'etiologic' / None (unstated). Raises on anything else."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("prediction", "predictive", "prognostic_model"):
        return "prediction"
    if s in ("etiologic", "aetiologic", "association", "associational", "descriptive"):
        return "etiologic"
    if s in ("unspecified", "unknown", ""):
        return None
    raise ValueError(
        f"Unknown model_purpose: {raw!r}. Expected 'prediction' or 'etiologic'."
    )


def _model_purpose(plan, step=None):
    """Purpose of the model THIS STEP fits — not of the study as a whole.

    A study is rarely one thing: an etiologic primary analysis can carry a
    prognostic sub-model, and one study-level field would then either block the
    legitimate calibration or license calibration for every association model in
    the plan. Resolution order, narrowest first:

        step.model_purpose                        (this model)
        advanced_analyses.calibration.study_purpose  (this analysis, pre-existing)
        study.model_purpose / top-level              (the study's default)

    None means unstated, which is never upgraded to a guess.
    """
    if step:
        purpose = _normalize_model_purpose(step.get("model_purpose"))
        if purpose:
            return purpose
    purpose = _normalize_model_purpose(
        ((plan.get("advanced_analyses") or {}).get("calibration") or {}).get(
            "study_purpose"))
    if purpose:
        return purpose
    return _normalize_model_purpose(_schema_field(plan, "model_purpose"))


def _pipeline_profile(plan):
    """'explore' or 'submit'. Default 'submit' — i.e. the behaviour a plan
    written before this field existed already had."""
    raw = _schema_field(plan, "pipeline_profile")
    if raw is None:
        return "submit"
    s = str(raw).strip().lower()
    if s in ("explore", "exploration", "exploratory"):
        return "explore"
    if s in ("submit", "submission", "confirmatory"):
        return "submit"
    raise ValueError(
        f"Unknown pipeline_profile: {raw!r}. Expected 'explore' or 'submit'."
    )


def _covariate_rationale(plan, cov):
    """Why this covariate is in the adjustment set, or None.

    covariates[].selection_rationale is canonical; the top-level
    `covariate_provenance` map (column -> rationale) is the fingerprint-neutral
    alias `--migrate` writes into. A plan-wide `covariates_selection_rule`
    counts as a rationale for covariates that do not state their own, because
    "all of them, by this stated rule" is a real pre-specification.
    """
    own = cov.get("selection_rationale")
    if own:
        return str(own)
    block = plan.get("covariate_provenance") or {}
    if isinstance(block, dict) and block.get(cov.get("column")):
        return str(block[cov["column"]])
    rule = plan.get("covariates_selection_rule")
    if rule:
        return f"(plan-level rule) {rule}"
    return None


def _outcome_intent(plan, outcome, is_primary):
    """(hypothesis_family, analysis_intent) for one outcome.

    The PRIMARY outcome's default is a definition, not a guess — being the
    primary endpoint is what confirmatory means. A secondary's is neither:
    "everything in outcomes.secondary is exploratory" is a filing convention, and
    a pre-specified co-primary endpoint listed there would be demoted by it
    without anyone being told. So an unstated secondary intent is 'unknown', and
    _record_multiplicity keeps asking. Multiplicity is then *reported* per family
    — no blanket FDR, which would shrink a pre-specified primary.
    """
    block = plan.get("multiplicity") or {}
    per_outcome = (block.get("outcomes") or {}).get(outcome.get("id")) or {}
    family = (outcome.get("hypothesis_family") or per_outcome.get("hypothesis_family")
              or ("primary" if is_primary else None))
    intent = (outcome.get("analysis_intent") or per_outcome.get("analysis_intent")
              or ("confirmatory" if is_primary else "unknown"))
    intent = str(intent).strip().lower()
    if intent not in ("confirmatory", "exploratory", "unknown"):
        raise ValueError(
            f"outcome '{outcome.get('id')}': unknown analysis_intent {intent!r}. "
            f"Expected 'confirmatory', 'exploratory' or 'unknown'."
        )
    return str(family) if family else "unassigned", intent


def get_outcome(plan, outcome_id):
    """Return the outcome dict by id (checks primary first, then secondary)."""
    primary = plan["outcomes"]["primary"]
    if primary["id"] == outcome_id:
        return primary
    for sec in plan["outcomes"].get("secondary", []):
        if sec["id"] == outcome_id:
            return sec
    raise ValueError(f"Outcome '{outcome_id}' not found in research plan")


def build_sections(covariates):
    """Group covariates into a sections array for table1/univariate/multivariate configs."""
    variables = []
    for cov in covariates:
        var = {"column": cov["column"], "type": cov["type"]}
        if cov["type"] == "continuous":
            if "scale" in cov and cov["scale"]:
                default_label = "per " + str(cov["scale"])
                var["label"] = cov["name"] + " (" + cov.get("scale_label", default_label) + ")"
                var["scale"] = cov["scale"]
                var["scale_label"] = cov.get("scale_label", f"per {cov['scale']}")
            else:
                var["label"] = cov["name"]
            if cov.get("center") is not None:
                var["center"] = cov["center"]
        elif cov["type"] == "binary":
            var["label"] = f"{cov['name']}, n (%)"
        elif cov["type"] == "ordinal":
            var["label"] = cov["name"]
            if "label_map" in cov:
                var["label_map"] = cov["label_map"]
        else:
            var["label"] = cov["name"]
        if cov.get("reference") is not None:
            var["reference_level"] = cov["reference"]
        variables.append(var)
    return [{"header": "Demographics & Comorbidities", "variables": variables}]


def build_table1_sections(covariates):
    """Build sections for table1 — same as build_sections but label format differs slightly."""
    variables = []
    for cov in covariates:
        var = {"column": cov["column"], "type": cov["type"]}
        if cov["type"] == "continuous":
            var["label"] = f"{cov['name']}"
            if "scale_label" in cov:
                var["label"] += f" ({cov['scale_label']})"
        elif cov["type"] == "binary":
            var["label"] = f"{cov['name']}, n (%)"
        elif cov["type"] == "ordinal":
            var["label"] = cov["name"]
            if "label_map" in cov:
                var["label_map"] = cov["label_map"]
        else:
            var["label"] = cov["name"]
        if cov.get("reference") is not None:
            var["reference_level"] = cov["reference"]
        variables.append(var)
    return [{"header": "Demographics & Comorbidities", "variables": variables}]


def shared_fields(plan):
    """Return fields shared by most configs."""
    return {
        "data_file": plan["study"]["data_file"],
        "filters": plan["population"].get("filters", []),
        "derived_variables": plan.get("derived_variables", []),
    }


def gen_flowchart(plan, step):
    config = shared_fields(plan)
    config["initial_label"] = plan["study"].get("title", "Total patients in registry")
    config["exclusion_steps"] = plan["population"].get("exclusion_steps", [])
    config["final_label"] = "Final study cohort"
    if "grouping" in plan:
        config["group_split"] = {
            "column": plan["grouping"]["column"],
            "groups": plan["grouping"]["groups"],
        }
    config["plot_settings"] = {
        "figsize": [10, 14],
        "dpi": 300,
        "main_box_width": 0.50,
        "main_box_color": "#D6E4F0",
        "exclude_box_color": "#FADBD8",
        "final_box_color": "#D5F5E3",
        "group_box_color": "#D6E4F0",
        "font_size": 10,
        "title_font_size": 11,
        "arrow_color": "#333333",
        "border_color": "#2C3E50",
    }
    config["output_file"] = _output_path(plan, step, "Flowchart")
    return config


def gen_table1(plan, step):
    config = shared_fields(plan)
    config["grouping"] = plan["grouping"]
    config["title"] = "Table 1. Baseline Characteristics"
    config["subtitle"] = plan["study"].get("title", "")
    config["sections"] = build_table1_sections(plan["covariates"])
    config["output_file"] = _output_path(plan, step, "Table1")
    config["abbreviations"] = plan.get("abbreviations", "")
    # Available-case (per-variable) is the standard convention for a baseline table;
    # opt into global complete-case via plan["table1"]["missing_data_handling"].
    t1_opts = plan.get("table1", {})
    config["missing_data_handling"] = t1_opts.get("missing_data_handling", "available")
    config["normality_alpha"] = t1_opts.get("normality_alpha", 0.05)
    config["normality_method"] = t1_opts.get("normality_method", "skew")
    return config


# What an undeclared time scale actually costs, per analysis route. Graded on
# purpose: one shared sentence would either overstate the Cox case or understate
# the AUC one, and a warning that overstates gets discounted the next time it
# appears — which is how the one that does not overstate gets ignored too.
_TIME_SCALE_CONSEQUENCE = {
    "kaplan-meier": (
        "Getting this wrong shifts every survival estimate — the curve, the median, "
        "survival at t — by a constant factor, without any error being raised."),
    "competing-risk": (
        "Getting this wrong shifts every cumulative-incidence estimate and every "
        "time point it is read at by a constant factor, without any error being "
        "raised."),
    # Cox partial likelihood uses only the ORDER of the event times, so a constant
    # rescaling leaves the hazard ratio untouched. Saying "your HRs are wrong"
    # here would be false.
    "univariate-forest": (
        "The hazard ratios themselves are unaffected — Cox's partial likelihood "
        "uses only the ordering of the event times, which a constant factor does "
        "not change. What is affected is every TIME-VALUED figure this step and "
        "its neighbours report: median follow-up, any landmark or split point, and "
        "the axis of any plot. Those come out in the raw column's units, whatever "
        "the manuscript says they are in."),
    "psm-matching": (
        "The matched hazard ratios themselves are unaffected — Cox's partial "
        "likelihood uses only the ordering of the event times. What is affected is "
        "every TIME-VALUED figure: median follow-up in each arm, any landmark or "
        "split point, and the axis of any plot. Those come out in the raw column's "
        "units, whatever the manuscript says they are in."),
    # The two remedy routes that consume a time VALUE the author supplies, so a
    # wrong scale silently moves the thing being asked for.
    "ph-rmst": (
        "This one changes the result. tau is consumed in the declared unit, so a "
        "wrong or assumed unit integrates the survival curve to a DIFFERENT horizon "
        "than the one reported — 'RMST at 5 years' computed at 5 days, or at 1826 "
        "years (where it is just the mean follow-up) — and reports it under the "
        "intended label. Declare time_unit and time_scale before reading this step."),
    "ph-time-varying": (
        "This one changes the result. The time windows are consumed in the declared "
        "unit, so a wrong or assumed unit puts every cut point somewhere else on the "
        "follow-up axis: 'the first year' becomes the first day, and the "
        "period-specific hazard ratios are for windows nobody chose. The hazard "
        "ratios themselves are not scale-invariant here, unlike an ordinary Cox "
        "model, because the windows define which events go in which coefficient."),
    # The one route where the number itself changes.
    "auc-cstat": (
        "This one does change the result. A time-dependent AUC or C-index AT t "
        "consumes t in the declared unit, so if the unit is wrong or assumed wrong "
        "the step computes discrimination at a DIFFERENT time point than the one "
        "reported — 'AUC at 1 year' computed at 1 day, or at 365 years — and "
        "reports it under the intended label with no error raised. Declare "
        "time_unit and time_scale before reading this step's output."),
}


def resolve_time_scale(outcome, skill="kaplan-meier"):
    """Resolve the divisor that converts the RAW time column into ``time_unit``.

    A wrong scale silently corrupts time-valued output, so this never guesses
    365.25 blindly:
      - if ``time_scale`` is given explicitly in the plan, use it verbatim;
      - otherwise assume the raw column is in DAYS (registry norm) and derive the
        scale from ``time_unit`` (years->365.25, months->30.4375, days->1), and
        emit a warning so a user whose raw data is NOT in days can override.

    `skill` selects what the warning says the consequence IS. Until 2026-08-12
    only the KM and competing-risk generators called this at all, so a plan that
    declared no time unit was warned on the KM route and passed in silence on
    every Cox route — the same undeclared field, reported or not depending on
    which analysis happened to be in the pipeline.
    """
    if outcome.get("time_scale") is not None:
        return outcome["time_scale"]
    unit = outcome.get("time_unit", "years")
    scale = {"years": 365.25, "months": 30.4375, "days": 1.0}.get(unit, 365.25)
    consequence = _TIME_SCALE_CONSEQUENCE.get(
        skill, _TIME_SCALE_CONSEQUENCE["kaplan-meier"])
    _method_warn(
        "time_scale_assumed",
        f"{skill}, outcome '{outcome.get('id', '?')}': time_scale not specified; "
        f"assuming raw '{outcome.get('time_column', 'time')}' is in DAYS and "
        f"converting to {unit} (scale={scale}). If the raw column is already in "
        f"{unit}, set \"time_scale\": 1 for this outcome in research_plan.json. "
        f"{consequence}",
    )
    return scale


def _carry_time_scale(config, outcome, skill):
    """Give a time-to-event config its time unit, or leave a logistic one alone.

    Only time-to-event outcomes: a logistic route has no time axis, so the
    fields would be inert and the warning would be about nothing.
    """
    if _normalize_outcome_type(outcome["type"]) not in _TIME_TO_EVENT_TYPES:
        return
    config["time_unit"] = outcome.get("time_unit", "years")
    config["time_scale"] = resolve_time_scale(outcome, skill)


def gen_kaplan_meier(plan, step):
    outcome = get_outcome(plan, step["outcome"])
    config = shared_fields(plan)
    config["grouping"] = plan["grouping"]
    config["time_column"] = outcome["time_column"]
    config["event_column"] = outcome["event_column"]
    config["time_unit"] = outcome.get("time_unit", "years")
    config["time_scale"] = resolve_time_scale(outcome, "kaplan-meier")
    config["time_points"] = outcome.get("time_points", [1, 3, 5])
    config["plot_settings"] = {
        "confidence_interval": True,
        "censor_marks": True,
        "colors": ["#E74C3C", "#3498DB"],
        "x_max": None,
        "x_tick_interval": None,
        "y_min": 0.0,
        "number_at_risk": True,
        "risk_table_times": None,
        "legend_position": "best",
        "figsize": [8, 6],
        "dpi": 300,
    }
    config["title"] = f"Kaplan-Meier: {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = os.path.join(plan["output_dir"], f"KM_{outcome['id']}.xlsx")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["missing_data_handling"] = "listwise"
    return config


def gen_competing_risk(plan, step):
    outcome = get_outcome(plan, step["outcome"])
    config = shared_fields(plan)
    config["grouping"] = plan["grouping"]
    config["time_column"] = outcome["time_column"]
    config["event_column"] = outcome.get("competing_event_column", outcome["event_column"])
    config["event_labels"] = outcome.get("competing_event_labels", {"1": outcome["name"], "2": "Other"})
    config["primary_event"] = 1
    config["time_unit"] = outcome.get("time_unit", "years")
    config["time_scale"] = resolve_time_scale(outcome, "competing-risk")
    config["time_points"] = outcome.get("time_points", [1, 3, 5])
    config["plot_settings"] = {
        "confidence_interval": True,
        "colors": None,
        "x_max": None,
        "x_tick_interval": None,
        "y_max": None,
        "figsize": [8, 6],
        "dpi": 300,
        "legend_position": "upper left",
        "plot_mode": "primary_by_group",
    }
    config["fine_gray"] = None
    config["title"] = f"Competing Risk: {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = os.path.join(plan["output_dir"], f"CR_{outcome['id']}.xlsx")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["missing_data_handling"] = "listwise"
    return config


def gen_univariate_forest(plan, step):
    outcome = get_outcome(plan, step["outcome"])
    config = shared_fields(plan)
    config["grouping"] = plan["grouping"]
    _ot = _normalize_outcome_type(outcome["type"])
    _warn_competing_risk_in_generic("univariate-forest", _ot)
    if _ot in _TIME_TO_EVENT_TYPES:
        config["analysis_type"] = "cox"
        config["cox_settings"] = {
            "time_column": outcome["time_column"],
            "event_column": outcome["event_column"],
        }
        config["logistic_settings"] = None
    else:
        config["analysis_type"] = "logistic"
        config["logistic_settings"] = {"outcome_column": outcome["event_column"]}
        config["cox_settings"] = None
    _carry_time_scale(config, outcome, "univariate-forest")
    config["sections"] = build_sections(plan["covariates"])
    config["title"] = f"Univariate Regression: {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = os.path.join(plan["output_dir"], f"Uni_{outcome['id']}.xlsx")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["missing_data_handling"] = "listwise"
    config["forest_plot"] = {
        "format": "png",
        "dpi": 300,
        "truncation_method": "auto",
        "truncation_range": None,
    }
    return config


# What multivariate_interaction.PH_REMEDIES accepts. Kept as a literal rather
# than imported: that script pulls in lifelines and statsmodels, and this
# generator must run on a machine that only has the plan.
_PH_REMEDIES = ("stratify", "time_varying", "rmst", "disclose")

# Remedy -> the step that performs it. One table, so adding a fourth remedy means
# adding one row rather than editing a generator, a registry, an output-stem map
# and an auto-add branch that each know part of the same fact.
#
# `hints` mirrors ph_remedy_gate.REMEDY_STEP_HINTS. The two copies serve different
# jobs — that one RECOGNISES a hand-built step as evidence, this one avoids adding
# a second step next to one the user already built — but they have to agree, or a
# hand-built step this table does not recognise gets a generated twin and the gate
# is handed two answers about one violation. test_pipeline_contract.py pins them
# equal, the same way it pins _PH_REMEDIES to multivariate_interaction's copy.
_REMEDY_STEPS = {
    "stratify": {
        "skill": "ph-stratified", "id": "ph_stratified_{oid}",
        "stem": "Stratified_{oid}",
        "hints": ("stratif",),
        "why": ("a stratified Cox as its own table, leaving the multivariate "
                "workbook unremediated and internally consistent"),
    },
    "time_varying": {
        "skill": "ph-time-varying", "id": "ph_time_varying_{oid}",
        "stem": "TimeVarying_{oid}",
        "hints": ("time_varying", "timevarying", "extcox", "extended_cox", "tvc"),
        "why": ("a Cox model whose coefficient for the violating covariate is "
                "allowed to differ between pre-specified time windows"),
    },
    "rmst": {
        "skill": "ph-rmst", "id": "ph_rmst_{oid}",
        "stem": "RMST_{oid}",
        "hints": ("rmst",),
        "why": ("restricted mean survival time up to tau, a summary that assumes "
                "no proportionality anywhere"),
    },
}


def _carry_ph_remedy(plan, outcome, config):
    """Carry outcomes[].ph_violation_remedy into the model's config.

    multivariate_interaction.py blocks (exit 2) when the Schoenfeld test finds a
    violation and no remedy was pre-specified — the whole point being that the
    remedy is declared BEFORE the test result is known. Until now nothing moved
    the declaration from research_plan.json into the generated config, so the
    only way to set it inside a pipeline was to hand-edit the config after the
    run had already blocked: exactly the after-the-fact route the gate exists to
    prevent. multivariate-interaction/SKILL.md:270 described this wiring as
    existing; `grep ph_violation_remedy generate_configs.py` returned nothing.

    Read from `outcomes[]`, never from the plan's top level, and that placement
    is the enforcement rather than a stylistic choice.
    reviewer_challenge.plan_fingerprint() hashes `outcomes`; it does not hash
    unknown top-level keys. A remedy declared at the top level could therefore
    be added AFTER seeing the Schoenfeld p-value without invalidating the
    challenge that had already passed — the declaration would be
    indistinguishable from a pre-specification, which is the only thing this
    gate checks. In `outcomes[]` the same edit moves the fingerprint (measured:
    33695bb3116d2343 -> 24b2cabc1059aef9) and the challenge has to be re-run.

    Absent means absent: nothing is written, so a violation stays blocking.
    """
    remedy = outcome.get("ph_violation_remedy")
    decision_id = outcome.get("ph_disclose_decision_id")
    if remedy is None:
        if decision_id:
            _method_warn(
                "ph_disclose_decision_id_without_remedy",
                f"outcome '{outcome.get('id')}' declares ph_disclose_decision_id="
                f"{decision_id!r} but no ph_violation_remedy, so nothing is carried into "
                f"the model config and a proportional-hazards violation will still block. "
                f"The decision ID only means something alongside "
                f"\"ph_violation_remedy\": \"disclose\".")
        return
    if remedy not in _PH_REMEDIES:
        raise ValueError(
            f"outcome '{outcome.get('id')}': ph_violation_remedy={remedy!r} is not one of "
            f"{list(_PH_REMEDIES)}. Refused here rather than passed through: a typo that "
            f"reaches the config reads as a pre-specification that was made, and the "
            f"analysis step would block on it much later with the plan looking correct.")
    config["ph_violation_remedy"] = remedy
    if decision_id:
        config["ph_disclose_decision_id"] = decision_id


def gen_multivariate_interaction(plan, step):
    outcome = get_outcome(plan, step["outcome"])
    config = shared_fields(plan)
    config["grouping"] = plan["grouping"]
    _ot = _normalize_outcome_type(outcome["type"])
    _warn_competing_risk_in_generic("multivariate-interaction", _ot)
    if _ot in _TIME_TO_EVENT_TYPES:
        config["analysis_type"] = "cox"
        config["cox_settings"] = {
            "time_column": outcome["time_column"],
            "event_column": outcome["event_column"],
        }
        config["logistic_settings"] = None
    else:
        config["analysis_type"] = "logistic"
        config["logistic_settings"] = {"outcome_column": outcome["event_column"]}
        config["cox_settings"] = None
    config["sections"] = build_sections(plan["covariates"])
    config["interaction_variables"] = "all"
    _carry_ph_remedy(plan, outcome, config)
    config["title"] = f"Multivariate Regression: {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = os.path.join(plan["output_dir"], f"Multi_{outcome['id']}.xlsx")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["missing_data_handling"] = "listwise"
    return config


def _ph_source_step(plan, outcome_id):
    """The multivariate step whose PH violation a remedy step is answering."""
    for s in (plan.get("pipeline") or []):
        if (s.get("skill") == "multivariate-interaction"
                and s.get("outcome") == outcome_id
                and s.get("status") != "skipped"):
            return s
    return None


def gen_ph_stratified(plan, step):
    """The `stratify` remedy as an executable step — see scripts/ph_stratified.py.

    Until now `ph_violation_remedy: "stratify"` was a declaration with no program
    behind it: no generator shipped, so the remedy had to be a hand-built step,
    and the artifact gate could only ask whether *a file* existed. This generator
    is the other half — the declaration now schedules an analysis.

    Two things it deliberately does NOT do:

      * It does not touch the multivariate step's workbook. Passing `strata=`
        inside multivariate_interaction.py would leave Sheet 1 without an HR for
        the stratified variable while Sheet 2's interaction models stayed
        unstratified — one workbook, two fitting assumptions, nothing in the
        layout saying so (2026-08-12 adjudication, dispute 5). The remedy is a
        third table with an explicit cross-reference instead.
      * It does not pick the stratification variables here. `"auto"` defers to the
        PH test artifact at run time, because which covariate broke
        proportionality is a property of the data and is not knowable when
        configs are generated. What *is* pre-specified — and what
        `outcomes[].ph_violation_remedy` records — is the decision to stratify.
        `outcomes[].ph_strata_variables` overrides when the author wants to name
        them in advance; both routes are recorded in the evidence sidecar so a
        reader can tell them apart.

    There is no `manuscript-results` extractor for this table yet, so a plan with
    this step reports it as unextractable. That is accurate rather than tidy: how
    the remedied estimate is cited alongside the unremediated main table is an
    open question, and silencing the warning would be answering it by default.
    """
    outcome = get_outcome(plan, step["outcome"])
    declared = outcome.get("ph_violation_remedy")
    if declared != "stratify":
        raise ValueError(
            f"step '{step.get('id')}' is a stratify-remedy step for outcome "
            f"'{outcome['id']}', but that outcome declares "
            f"ph_violation_remedy={declared!r}. The remedy that runs and the remedy "
            f"that was pre-specified have to be the same one — otherwise the "
            f"artifact gate would see evidence for a remedy nobody declared.")

    config = shared_fields(plan)
    config["mode"] = "ph_stratified"
    config["remedy"] = "stratify"
    config["outcome_id"] = outcome["id"]
    config["grouping"] = plan["grouping"]
    ot = _survival_or_binary(config, outcome)
    if ot not in _TIME_TO_EVENT_TYPES:
        raise ValueError(
            f"outcome '{outcome['id']}' is type {ot!r}: there is no "
            f"proportional-hazards assumption outside a survival model, so a "
            f"'stratify' remedy has nothing to fix. Remove the remedy or the step.")
    # No _carry_time_scale here, unlike the other Cox routes: this step reports
    # hazard ratios and event counts and nothing time-valued, so the fields would
    # be inert and the "time_scale not specified" warning would be describing a
    # consequence this step does not have. A warning that overstates is how the
    # ones that do not overstate get discounted.
    config["sections"] = build_sections(plan["covariates"])

    src_step = _ph_source_step(plan, outcome["id"])
    if src_step is None:
        raise ValueError(
            f"outcome '{outcome['id']}' declares a 'stratify' remedy but the pipeline "
            f"has no active multivariate-interaction step for it. The remedy answers a "
            f"violation found by that step; without it there is no PH test artifact to "
            f"read and nothing to remedy.")
    source_table = _manuscript_source_path(plan, src_step)
    config["source_table"] = source_table
    # multivariate_interaction.py writes `<workbook stem>_ph_test.json` beside the
    # workbook. Derived from the source step's own resolved path rather than
    # rebuilt from the outcome id, so the two cannot drift apart.
    config["ph_test_file"] = (f"{os.path.splitext(source_table)[0]}_ph_test.json"
                              if source_table else None)

    strata = outcome.get("ph_strata_variables")
    config["strata_variables"] = list(strata) if strata else "auto"

    config["title"] = f"Stratified Cox (PH remedy): {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = _output_path(plan, step, f"Stratified_{outcome['id']}")
    config["evidence_file"] = f"{os.path.splitext(config['output_file'])[0]}_remedy.json"
    config["abbreviations"] = plan.get("abbreviations", "")
    config["missing_data_handling"] = "listwise"
    return config


def _ph_remedy_common(plan, step, remedy, mode, stem):
    """The half of a remedy config that is the same for all three.

    Every remedy step answers one multivariate step's PH test, names the workbook
    it is the remedy for, and carries the same binding between its own output and
    its evidence sidecar. Writing that once is what stops the three from drifting
    into three slightly different ideas of where the PH artifact lives.
    """
    outcome = get_outcome(plan, step["outcome"])
    declared = outcome.get("ph_violation_remedy")
    if declared != remedy:
        raise ValueError(
            f"step '{step.get('id')}' is a {remedy!r}-remedy step for outcome "
            f"'{outcome['id']}', but that outcome declares "
            f"ph_violation_remedy={declared!r}. The remedy that runs and the remedy "
            f"that was pre-specified have to be the same one — otherwise the "
            f"artifact gate would see evidence for a remedy nobody declared.")

    config = shared_fields(plan)
    config["mode"] = mode
    config["remedy"] = remedy
    config["outcome_id"] = outcome["id"]
    config["grouping"] = plan["grouping"]
    ot = _survival_or_binary(config, outcome)
    if ot not in _TIME_TO_EVENT_TYPES:
        raise ValueError(
            f"outcome '{outcome['id']}' is type {ot!r}: there is no "
            f"proportional-hazards assumption outside a survival model, so a "
            f"{remedy!r} remedy has nothing to fix. Remove the remedy or the step.")

    src_step = _ph_source_step(plan, outcome["id"])
    if src_step is None:
        raise ValueError(
            f"outcome '{outcome['id']}' declares a {remedy!r} remedy but the pipeline "
            f"has no active multivariate-interaction step for it. The remedy answers a "
            f"violation found by that step; without it there is no PH test artifact to "
            f"read and nothing to remedy.")
    source_table = _manuscript_source_path(plan, src_step)
    config["source_table"] = source_table
    # multivariate_interaction.py writes `<workbook stem>_ph_test.json` beside the
    # workbook. Derived from the source step's own resolved path rather than
    # rebuilt from the outcome id, so the two cannot drift apart.
    config["ph_test_file"] = (f"{os.path.splitext(source_table)[0]}_ph_test.json"
                              if source_table else None)

    config["subtitle"] = plan["study"].get("title", "")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["output_file"] = _output_path(plan, step, stem.format(oid=outcome["id"]))
    config["evidence_file"] = f"{os.path.splitext(config['output_file'])[0]}_remedy.json"
    return config, outcome


def gen_ph_rmst(plan, step):
    """The `rmst` remedy as an executable step — see scripts/ph_rmst.py.

    tau is the only thing this remedy has to defend, so the generator's real work
    is carrying its provenance. `outcomes[].rmst_tau` (a number) and
    `outcomes[].rmst_tau_rule` (a named rule) both sit inside the plan
    fingerprint; neither declared leaves `tau_source: "default_rule"`, which the
    script still runs on — so the author sees the numbers and the exact fix —
    and which the manuscript gate then blocks. Warning here rather than raising
    for the same reason: a door with no exit is worse than a signposted one.
    """
    config, outcome = _ph_remedy_common(plan, step, "rmst", "ph_rmst", "RMST_{oid}")
    tau = outcome.get("rmst_tau")
    tau_rule = outcome.get("rmst_tau_rule")
    if tau is not None:
        config["tau"], config["tau_rule"], config["tau_source"] = tau, None, "plan_value"
    elif tau_rule:
        config["tau"], config["tau_rule"], config["tau_source"] = None, tau_rule, "plan_rule"
    else:
        config["tau"], config["tau_rule"] = None, "min_of_arm_max_followup"
        config["tau_source"] = "default_rule"
        _method_warn(
            "rmst_tau_not_prespecified",
            f"outcome '{outcome['id']}': ph_violation_remedy='rmst' but neither "
            f"rmst_tau nor rmst_tau_rule is declared in outcomes[]. The step will run "
            f"with the default rule (min_of_arm_max_followup) so you can see the "
            f"numbers, but tau will sit OUTSIDE the plan fingerprint — which means it "
            f"cannot be shown to have been chosen before the result, and choosing tau "
            f"after seeing the comparison is the entire p-hacking surface of RMST. The "
            f"manuscript gate blocks until one of the two fields is set.")
    _carry_time_scale(config, outcome, "ph-rmst")
    config["title"] = f"Restricted mean survival time (PH remedy): {outcome['name']}"
    return config


def gen_ph_time_varying(plan, step):
    """The `time_varying` remedy as an executable step — see ph_time_varying.py.

    Cut points carry the same burden tau does in gen_ph_rmst, and for the same
    reason: windows chosen after seeing where the effect changes are a subgroup
    search along the time axis. `outcomes[].tv_cut_points` is inside the
    fingerprint; undeclared runs on the median event time and is blocked at the
    manuscript gate.
    """
    config, outcome = _ph_remedy_common(plan, step, "time_varying",
                                        "ph_time_varying", "TimeVarying_{oid}")
    config["sections"] = build_sections(plan["covariates"])
    tv = outcome.get("time_varying_variables")
    config["time_varying_variables"] = list(tv) if tv else "auto"
    cuts = outcome.get("tv_cut_points")
    if cuts:
        config["cut_points"], config["cut_points_source"] = list(cuts), "plan"
    else:
        config["cut_points"], config["cut_points_source"] = None, "default_rule"
        _method_warn(
            "tv_cut_points_not_prespecified",
            f"outcome '{outcome['id']}': ph_violation_remedy='time_varying' but "
            f"outcomes[].tv_cut_points is not declared. The step will run with a "
            f"single cut at the median event time so you can see the numbers, but the "
            f"windows will sit OUTSIDE the plan fingerprint and cannot be shown to "
            f"predate the result. The manuscript gate blocks until tv_cut_points is "
            f"set.")
    _carry_time_scale(config, outcome, "ph-time-varying")
    config["title"] = f"Time-varying Cox (PH remedy): {outcome['name']}"
    config["missing_data_handling"] = "listwise"
    return config


def gen_psm(plan, step):
    config = shared_fields(plan)
    config["grouping"] = plan["grouping"]
    config["matching"] = {
        "caliper": {"enabled": True, "width": 0.20},
        "ratio": 1,
    }
    # Build matching variables from covariates (only continuous and binary)
    match_vars = []
    for cov in plan["covariates"]:
        if cov["type"] in ("continuous", "binary"):
            var = {"column": cov["column"], "type": cov["type"]}
            if cov["type"] == "continuous":
                var["label"] = cov["name"]
            else:
                var["label"] = cov["name"]
            match_vars.append(var)
    config["matching_variables"] = [{"header": "Matching Variables", "variables": match_vars}]

    # Determine analysis type from primary outcome
    primary = plan["outcomes"]["primary"]
    _primary_ot = _normalize_outcome_type(primary["type"])
    _warn_competing_risk_in_generic("psm-matching", _primary_ot)
    if _primary_ot in _TIME_TO_EVENT_TYPES:
        config["analysis_type"] = "cox"
        outcomes_list = []
        # Add primary
        outcomes_list.append({
            "label": primary["name"],
            "event_column": primary["event_column"],
            "time_column": primary["time_column"],
        })
        # Add secondaries
        for sec in plan["outcomes"].get("secondary", []):
            if _normalize_outcome_type(sec["type"]) in _TIME_TO_EVENT_TYPES:
                outcomes_list.append({
                    "label": sec["name"],
                    "event_column": sec["event_column"],
                    "time_column": sec["time_column"],
                })
            else:
                outcomes_list.append({
                    "label": sec["name"],
                    "outcome_column": sec["event_column"],
                })
    else:
        config["analysis_type"] = "logistic"
        outcomes_list = []
        outcomes_list.append({
            "label": primary["name"],
            "outcome_column": primary["event_column"],
        })
        for sec in plan["outcomes"].get("secondary", []):
            outcomes_list.append({
                "label": sec["name"],
                "outcome_column": sec["event_column"],
            })
    config["outcomes"] = outcomes_list
    _carry_time_scale(config, primary, "psm-matching")
    config["title"] = "Propensity Score Matched Analysis"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = _output_path(plan, step, "PSM")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["missing_data_handling"] = "listwise"
    return config


def _auc_clinical_model(plan, auc_settings):
    """(clinical_model block, the covariates left to evaluate against it).

    Incremental value asks whether a candidate variable adds discrimination to a
    model that already exists, so the base model is a DECLARATION, not a
    convenience: which variables count as "already known" decides the delta, and
    picking that set after seeing which choice flatters the candidate is the
    entire p-hacking surface of the question. It is read from
    `analyses.auc.clinical_model_columns`, which lives inside `analyses` and is
    therefore already inside the plan fingerprint — the same protection tau and
    the time-varying cut points get from living in `outcomes[]`.

    Columns, not variable specs. Labels, types, scales and reference levels
    already exist once in `covariates`; a second copy of them here would be a
    second definition of the same fact, free to drift from the one the rest of
    the pipeline models.

    The evaluated set is every OTHER covariate. auc_cstat fits
    `clinical_cols + [col]` for the full model, so a candidate that is also in
    the base would be entered twice and its delta would be zero by construction.
    """
    covariates = plan.get("covariates") or []
    declared = auc_settings.get("clinical_model_columns")
    if not declared:
        return {"enabled": False}, covariates
    if not isinstance(declared, list) or any(not isinstance(c, str) for c in declared):
        _abort(f"analyses.auc.clinical_model_columns must be a list of covariate "
               f"column names, got {declared!r}")
    repeated = sorted({c for c in declared if declared.count(c) > 1})
    if repeated:
        _abort(f"analyses.auc.clinical_model_columns repeats {repeated}; a column "
               f"entered twice would be fitted twice")
    by_column = {c["column"]: c for c in covariates}
    unknown = [c for c in declared if c not in by_column]
    if unknown:
        _abort(f"analyses.auc.clinical_model_columns names {unknown}, which "
               f"plan.covariates does not model. The base model has to be drawn "
               f"from the covariates the study declares; available columns are "
               f"{sorted(by_column)}")
    evaluated = [c for c in covariates if c["column"] not in set(declared)]
    if not evaluated:
        _abort("analyses.auc.clinical_model_columns names every covariate, so no "
               "variable is left whose incremental value could be measured. Remove "
               "the candidate marker from the base model")
    return ({"enabled": True,
             "variables": build_sections([by_column[c] for c in declared])[0]["variables"]},
            evaluated)


def gen_auc(plan, step):
    config = shared_fields(plan)
    primary = plan["outcomes"]["primary"]
    _primary_ot = _normalize_outcome_type(primary["type"])
    _warn_competing_risk_in_generic("auc-cstat", _primary_ot)
    if _primary_ot in _TIME_TO_EVENT_TYPES:
        config["analysis_type"] = "cox"
        config["cox_settings"] = {
            "time_column": primary["time_column"],
            "event_column": primary["event_column"],
        }
        config["logistic_settings"] = None
    else:
        config["analysis_type"] = "logistic"
        config["logistic_settings"] = {"outcome_column": primary["event_column"]}
        config["cox_settings"] = None
    _carry_time_scale(config, primary, "auc-cstat")
    _auc = (plan.get("analyses") or {}).get("auc", {}) or {}
    config["clinical_model"], _evaluated = _auc_clinical_model(plan, _auc)
    config["sections"] = build_sections(_evaluated)
    # Overridable. 2000 resamples was hard-coded with nothing in the plan schema
    # to change it, and it is enough to hit the runner's 600s step timeout on a
    # few hundred rows — the step then fails on wall-clock rather than on
    # anything statistical, with no lever to pull. The default stays 2000
    # (percentile CIs on a C-statistic want the resamples); a project that is
    # timing out can turn it down deliberately and say so.
    config["bootstrap"] = {
        "n_iterations": int(_auc.get("bootstrap_n", 2000)),
        "random_seed": int(_auc.get("seed", 42)),
    }
    if config["clinical_model"]["enabled"] and config["analysis_type"] == "cox":
        # The paired comparison refits BOTH nested models on every resample, so
        # the wall clock is not the same run with an extra column: it is roughly
        # three C-index fits per candidate per resample. Said here, with the
        # lever named, because the failure it causes downstream is a 600s step
        # timeout, which reads as a broken step rather than as a cost.
        _method_warn(
            "auc_incremental_value_bootstrap_cost",
            f"incremental value is enabled for {len(_evaluated)} candidate "
            f"variable(s) against a {len(config['clinical_model']['variables'])}-"
            f"variable base model, and the paired bootstrap refits both nested "
            f"models {config['bootstrap']['n_iterations']} times per candidate. "
            f"If this step hits the 600s timeout, lower analyses.auc.bootstrap_n "
            f"deliberately rather than reading the timeout as a failed analysis")
    config["title"] = "Discrimination Analysis"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = _output_path(plan, step, "AUC")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["missing_data_handling"] = "listwise"
    return config


def _missing_data_opts(plan):
    """Return the plan's ``missing_data`` block (empty dict when absent).

    Every field in the block is optional — a plan written before the missing-data
    steps existed still generates valid configs, it just gets the defaults.
    """
    return plan.get("missing_data") or {}


def gen_missingness(plan, step):
    """Config for the missing-data ASSESSMENT step (Foundation group, always runs).

    Assessment is unconditional: "this dataset has no missing-data problem" is
    itself a claim that needs evidence, not an impression
    (references/missing_data_protocol.md §1). The script produces per-variable and
    per-group missing rates, the missingness pattern, the listwise-deletion cost,
    MCAR-testable associations, auxiliary-variable candidates, and a verdict.
    The verdict only *suggests*; it never rewrites the pipeline (§2, §7).
    """
    md = _missing_data_opts(plan)
    config = {"mode": "assessment"}
    config.update(shared_fields(plan))
    config["grouping"] = plan["grouping"]
    config["analysis_variables"] = [
        {"column": cov["column"], "type": cov["type"], "label": cov["name"]}
        for cov in plan["covariates"]
    ]
    outcomes = [plan["outcomes"]["primary"]] + list(plan["outcomes"].get("secondary", []))
    config["outcomes"] = [
        {
            "id": o["id"],
            "type": _normalize_outcome_type(o["type"]),
            "time_column": o.get("time_column"),
            "event_column": o["event_column"],
        }
        for o in outcomes
    ]
    # Auxiliary candidates the user already knows about; the script may add more
    # from the data (variables correlated with both the incomplete variable and
    # its missingness indicator — protocol §3 item 5).
    config["candidate_auxiliary"] = md.get("auxiliary_variables", [])
    # Verdict cut-points from protocol §2: <5% → complete_case_ok,
    # 5–40% → mi_recommended, >40% → mi_with_caution.
    config["thresholds"] = {"low": 5, "high": 40}
    config["output_file"] = _output_path(plan, step, "Missingness")
    config["plot_file"] = _output_path(plan, step, "Missingness", "_pattern.png")
    return config


def gen_missing_data_mi(plan, step):
    """Config for the multiple-imputation + pooled-analysis step (per outcome).

    Mirrors gen_multivariate_interaction's cox/logistic routing so the MI model is
    the *same* model as the complete-case one — that is what makes the CC_vs_MI
    sheet a like-for-like comparison (protocol §5).

    ``mi_settings.m = null`` means "let the script apply protocol §4.4"
    (m = max(20, ceil(largest missing %)), capped at 100). It is not "use mice's
    default of 5".
    """
    outcome = get_outcome(plan, step["outcome"])
    md = _missing_data_opts(plan)
    config = {"mode": "imputation"}
    config.update(shared_fields(plan))
    config["grouping"] = plan["grouping"]

    _ot = _normalize_outcome_type(outcome["type"])
    if _ot == "competing_risk":
        # Protocol §6: MI for competing risks needs a separate Nelson-Aalen
        # cumulative hazard per event type; one na_cumhaz is not enough. The
        # config is still written on purpose — missing_data.py raises the single
        # authoritative [QC_BLOCKING] at run time, so the refusal lives in one
        # place instead of being split between generator and script.
        _method_warn(
            "mi_competing_risk_unsupported",
            f"missing-data (MI) for outcome '{outcome['id']}': type="
            f"'competing_risk' is NOT supported by the imputation step "
            f"(missing_data_protocol.md §6 — each event type needs its own "
            f"Nelson-Aalen cumulative hazard). The config is generated so the "
            f"script emits the [QC_BLOCKING] itself; this step WILL fail. Either "
            f"drop the mi_{outcome['id']} step, or re-specify the outcome as a "
            f"cause-specific single endpoint, and record the choice in "
            f"decision_log.md.",
        )

    if _ot in _TIME_TO_EVENT_TYPES:
        config["analysis_type"] = "cox"
        config["cox_settings"] = {
            "time_column": outcome["time_column"],
            "event_column": outcome["event_column"],
        }
        config["logistic_settings"] = None
    else:
        config["analysis_type"] = "logistic"
        config["logistic_settings"] = {"outcome_column": outcome["event_column"]}
        config["cox_settings"] = None

    config["sections"] = build_sections(plan["covariates"])
    config["auxiliary_variables"] = md.get("auxiliary_variables", [])
    config["mi_settings"] = {
        "m": md.get("m"),
        "seed": md.get("seed", 42),
        "maxit": md.get("maxit", 20),
        "method_overrides": md.get("method_overrides", {}),
    }
    # Carry the Step 3.5 clustering finding through to the script. It cannot read
    # research_plan.json itself, and the protocol grades this by provenance: a
    # column-name guess is a warning, a diagnostics-confirmed cluster is blocking,
    # because single-level imputation then understates the variance for certain.
    config["cluster_confirmed"] = _diagnostics_flagged(plan, "clustering")
    # missing_data.py labels the outcome descriptor from this; without it every
    # step falls back to "primary" and a secondary-outcome MI reports itself as
    # the primary one in the Imputation_model sheet.
    config["outcome_id"] = outcome["id"]
    config["title"] = f"Multiple Imputation: {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["output_file"] = os.path.join(plan["output_dir"], f"MI_{outcome['id']}.xlsx")
    config["diagnostics_plot"] = os.path.join(
        plan["output_dir"], f"MI_{outcome['id']}_diagnostics.png"
    )
    return config


def gen_missing_data(plan, step):
    """Dispatch the shared ``missing-data`` skill to assessment vs imputation.

    Both pipeline steps carry ``skill == "missing-data"`` (they share one script),
    so the generator table cannot key on the skill name alone. The discriminator is
    the presence of an ``outcome`` field — the same rule
    ``run_pipeline.group_steps_by_analysis_group()`` uses to send `missingness` to
    the Foundation group and `mi_{outcome_id}` to its outcome group. Keep the two
    in sync.
    """
    if step.get("outcome"):
        return gen_missing_data_mi(plan, step)
    return gen_missingness(plan, step)


# Steps that produce no workbook a Results section quotes from, and whose
# absence from manuscript-results is therefore a design decision rather than an
# oversight. Before 2026-08-11 `flowchart` and the missingness ASSESSMENT fell
# through to steps_missing_from_manuscript_extraction, so that warning fired on
# essentially every run with the same two permanent entries — and the entries
# that mattered (an analysis with genuinely no extractor) were read as more of
# the same noise. Flowchart numbers reach the manuscript through the STROBE
# checklist and the figure itself; the assessment's numbers are a decision
# record, not a result.
_NOT_EXTRACTED = ("flowchart", "reviewer-challenge", "missing-data")

# How each generator names its workbook. This mirrors the `output_file` each
# gen_* sets and exists because gen_manuscript has to name those files without
# re-running the generators. A step that states its own `output_file` always
# wins; an unknown skill returns None and is reported as unextractable rather
# than pointed at a path that does not exist.
_OUTPUT_STEM = {
    "flowchart": lambda plan, s: "Flowchart",
    "table1": lambda plan, s: "Table1",
    "kaplan-meier": lambda plan, s: f"KM_{s.get('outcome')}",
    "competing-risk": lambda plan, s: f"CR_{s.get('outcome')}",
    "univariate-forest": lambda plan, s: f"Uni_{s.get('outcome')}",
    "multivariate-interaction": lambda plan, s: f"Multi_{s.get('outcome')}",
    "ph-stratified": lambda plan, s: f"Stratified_{s.get('outcome')}",
    "ph-rmst": lambda plan, s: f"RMST_{s.get('outcome')}",
    "ph-time-varying": lambda plan, s: f"TimeVarying_{s.get('outcome')}",
    "psm-matching": lambda plan, s: "PSM",
    "auc-cstat": lambda plan, s: "AUC",
    "missing-data": lambda plan, s: (f"MI_{s['outcome']}" if s.get("outcome")
                                     else "Missingness"),
    "nonlinearity": lambda plan, s: f"RCS_{s.get('outcome')}",
    "robust-variance": lambda plan, s: f"Robust_{s.get('outcome')}",
    "calibration": lambda plan, s: f"Calibration_{s.get('outcome')}",
    "weighting": lambda plan, s: f"Weighting_{s.get('outcome')}",
    "immortal-time": lambda plan, s: (
        ("Landmark" if _adv(plan, "immortal_time").get("mode", "landmark") == "landmark"
         else "ExtendedCox") + f"_{s.get('outcome')}"),
    "evalue": lambda plan, s: f"E_value_{s.get('outcome')}",
    "strobe": lambda plan, s: "STROBE_checklist",
}


def _output_stem(plan, step, base):
    """The filename stem for one step, disambiguated when two steps collide.

    `gen_psm` wrote "PSM.xlsx" unconditionally, so a plan with a primary and a
    sensitivity PSM step had both writing the same workbook. The overwrite was
    the visible half; the worse half was that every post-stage check resolved
    BOTH steps to the same artifact, so the second one was never actually
    examined — its outputs, its numbers, its group direction and its sidecar
    were all read off the first one's file. One sidecar appearing to "cover two
    steps" was this, not a sidecar problem.

    Back-compatible on purpose: with a single step of that kind the stem is
    unchanged ("PSM", "Table1", "AUC"), so existing projects' manifests, decision
    logs and on-disk artifacts still line up. The suffix appears only where the
    collision is real — and a plan with two colliding steps has no working
    behaviour to preserve, since today it silently analyses one of them twice.

    An explicit `step["output_file"]` always wins: that is the escape hatch for
    naming the files yourself, and it is honoured by both the generators and the
    manuscript path resolver, which is what stops those two from disagreeing.
    """
    declared = step.get("output_file")
    if declared:
        return str(declared)[:-5] if str(declared).lower().endswith(".xlsx") \
            else str(declared)
    peers = 0
    for other in (plan.get("pipeline") or []):
        if other.get("id") == step.get("id"):
            continue
        stem = _OUTPUT_STEM.get(other.get("skill"))
        if stem is None or other.get("output_file"):
            continue
        try:
            if stem(plan, other) == base:
                peers += 1
        except Exception:                      # a malformed peer is not this step's problem
            continue
    return base if peers == 0 else f"{base}_{step.get('id')}"


def _output_path(plan, step, base, ext=".xlsx"):
    """Absolute path for a step's own output, collision-disambiguated."""
    return os.path.join(plan["output_dir"], f"{_output_stem(plan, step, base)}{ext}")


def _manuscript_source_path(plan, step):
    """Absolute path of the workbook `step` writes, or None if it cannot be known.

    `step["output_file"]` used to fall back to the step **id**
    (`km_primary.xlsx`), a file no generator ever writes — the manuscript config
    then listed a path that is simply not on disk, and the extractor reported it
    as a missing file rather than as a wrong guess.

    Goes through the same _output_stem() the generators use, so a disambiguated
    workbook is looked for under the name it was actually written to.
    """
    stem = _OUTPUT_STEM.get(step.get("skill"))
    if stem is None and not step.get("output_file"):
        return None
    base = stem(plan, step) if stem else ""
    return _output_path(plan, step, base)


def gen_manuscript(plan, step):
    # An explicit manuscript.analysis_files list wins over everything derived
    # below: once a project's main model has moved to a re-fit workbook, the
    # derived list is the wrong one and hand-patching the generated config lasts
    # only until the next regeneration.
    override = (plan.get("manuscript") or {}).get("analysis_files")
    # Build analysis_files from completed pipeline steps
    type_map = {
        "table1": "table1",
        "kaplan-meier": "kaplan_meier",
        "competing-risk": "competing_risk",
        "univariate-forest": "univariate",
        "multivariate-interaction": "multivariate",
        "psm-matching": "psm",
        "auc-cstat": "auc",
        "weighting": "weighting",
        # advanced_analyses.md's seven gaps — extract_data.py extractors added
        # 2026-08-11. "strobe" and "immortal-time"/"evalue"/etc. are step
        # *skills*, matching the pipeline step dict's "skill" field.
        "nonlinearity": "nonlinearity",
        "robust-variance": "robust-variance",
        "calibration": "calibration",
        "immortal-time": "immortal-time",
        "evalue": "evalue",
        "strobe": "strobe",
    }
    analysis_files = []
    unextractable = []
    by_design = []
    for p in plan["pipeline"]:
        if p["id"] == step["id"] or p.get("status") == "skipped":
            continue
        skill = p["skill"]
        # missing-data is one skill with two step shapes (missing_data_protocol.md
        # §1 / generate_configs.gen_missing_data's own docstring): a step with an
        # "outcome" is the per-outcome MI + pooled-analysis run
        # (MI_{outcome}.xlsx, extractable), a step without one is the
        # unconditional missingness ASSESSMENT (Missingness.xlsx). The assessment
        # is deliberately left out of type_map, not because it could not be
        # parsed but because its numbers (per-variable missing %, the MCAR
        # tests, the verdict) describe a decision about which analysis to run,
        # not a result to report in the same voice as a Table/Figure — the MI
        # step's own CC_vs_MI sheet already carries the comparison a Results
        # section needs. It is listed in _NOT_EXTRACTED below rather than left to
        # fall through, because a warning that fires on every single run stops
        # being read.
        if skill == "missing-data" and p.get("outcome"):
            file_type = "missing-data"
        elif skill in type_map:
            file_type = type_map[skill]
        else:
            file_type = None
        if file_type:
            xlsx_path = _manuscript_source_path(plan, p)
            if xlsx_path is None:
                unextractable.append(p["id"])
                continue
            analysis_files.append({
                "type": file_type,
                "path": xlsx_path,
            })
        elif skill in _NOT_EXTRACTED:
            by_design.append(p["id"])
        else:
            unextractable.append(p["id"])

    # Steps with no extractor in manuscript-results never reach the Results
    # draft even though the analysis ran and the workbook is on disk — the risk
    # is precisely that nobody notices they are missing from the write-up, which
    # is the "ran it, did not report it" failure this domain treats as its
    # worst. Record it rather than letting it pass in silence. As of 2026-08-11
    # this is normally just the missingness assessment step (see above) plus
    # whatever the plan does not otherwise route through a known skill.
    if by_design:
        # Stated, but not as a methodological warning. These are the same two or
        # three ids on every run of every project; filed as warnings they trained
        # the reader to skim the list, which is where a genuinely unextracted
        # analysis would then be missed.
        print(f"  Not extracted by design (read the workbooks directly when writing): "
              f"{', '.join(by_design)}")
    if unextractable:
        _method_warn(
            "steps_missing_from_manuscript_extraction",
            f"{len(unextractable)} completed step(s) have no extractor in "
            f"manuscript-results and will NOT appear in the Results draft: "
            f"{', '.join(unextractable)}. Read those workbooks directly when writing the "
            f"manuscript, and state in decision_log.md which of them the paper reports.")

    if override:
        _method_warn(
            "manuscript_analysis_files_overridden",
            f"manuscript.analysis_files is set in the plan, so the Results draft reads "
            f"{len(override)} file(s) named there instead of the "
            f"{len(analysis_files)} derived from the pipeline steps. This is the "
            f"supported way to point the write-up at a re-fitted model, but it means the "
            f"pipeline can no longer tell you when a step's workbook is left out — list "
            f"the reason and the permanent decision ID in decision_log.md.")
        for f in override:
            if not f.get("type") or not f.get("path"):
                raise ValueError(
                    f"manuscript.analysis_files entry {f!r} needs both a 'type' (an "
                    f"extractor name from manuscript-results, e.g. 'multivariate') and a "
                    f"'path' (absolute, or relative to output_dir). Refusing rather than "
                    f"defaulting: a half-specified override silently drops a workbook "
                    f"from the Results draft.")
        analysis_files = [
            {"type": f["type"], "path": _resolve_output_path(plan, f["path"], "")}
            for f in override
        ]

    groups = plan["grouping"]["groups"]
    config = {
        "analysis_files": analysis_files,
        "study_design": plan["study"]["design"],
        "primary_outcome": plan["outcomes"]["primary"].get("description", plan["outcomes"]["primary"]["name"]),
        "secondary_outcomes": [
            sec.get("description", sec["name"])
            for sec in plan["outcomes"].get("secondary", [])
        ],
        "group_description": {
            "group1": f"patients with {groups[0]['label']}",
            "group2": f"patients without {groups[0]['label']}",
            "short1": groups[0]["label"],
            "short2": groups[1]["label"] if len(groups) > 1 else f"Non-{groups[0]['label']}",
        },
        "table_figure_map": {},
        "language": "english",
        "output_file": _output_path(plan, step, "Results_Section", ".docx"),
    }

    # Convert table_figure_mapping (step_id -> label) to type-based keys
    tfm = plan.get("table_figure_mapping", {})
    for step_id, label in tfm.items():
        for p in plan["pipeline"]:
            if p["id"] == step_id and p["skill"] in type_map:
                config["table_figure_map"][type_map[p["skill"]]] = label
                break

    return config


def _adv(plan, key):
    """Settings for one advanced analysis. See references/advanced_analyses.md."""
    return (plan.get("advanced_analyses") or {}).get(key) or {}


def _resolve_output_path(plan, override, default_name):
    """An explicit path from the plan, else <output_dir>/<default_name>.

    A relative override is taken relative to output_dir, so a plan can say
    "Multi_primary_T5.xlsx" without hard-coding an absolute path that breaks the
    moment the project directory moves.
    """
    if not override:
        return os.path.join(plan["output_dir"], default_name)
    if os.path.isabs(override):
        return override
    return os.path.join(plan["output_dir"], override)


def _survival_or_binary(config, outcome):
    """Fill analysis_type + cox/logistic settings the same way every other
    generator does, so a new step cannot drift from the established routing."""
    ot = _normalize_outcome_type(outcome["type"])
    if ot in _TIME_TO_EVENT_TYPES:
        config["analysis_type"] = "cox"
        config["cox_settings"] = {"time_column": outcome["time_column"],
                                  "event_column": outcome["event_column"]}
        config["logistic_settings"] = None
    else:
        config["analysis_type"] = "logistic"
        config["logistic_settings"] = {"outcome_column": outcome["event_column"]}
        config["cox_settings"] = None
    return ot


def gen_nonlinearity(plan, step):
    """RCS — advanced_analyses.md section 3."""
    outcome = get_outcome(plan, step["outcome"])
    s = _adv(plan, "nonlinearity")
    config = shared_fields(plan)
    config["mode"] = "rcs"
    config["grouping"] = plan["grouping"]
    _survival_or_binary(config, outcome)
    config["sections"] = build_sections(plan["covariates"])
    # Default to every continuous covariate: the whole point is that "linear
    # unless someone remembered to ask" is the failure mode.
    config["spline_variables"] = s.get("variables") or [
        c["column"] for c in plan["covariates"] if c.get("type") == "continuous"]
    config["spline_settings"] = {"knots": s.get("knots", 4),
                                 "knot_percentiles": s.get("knot_percentiles"),
                                 "reference": s.get("reference")}
    config["title"] = f"Non-linearity (RCS): {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = os.path.join(plan["output_dir"], f"RCS_{outcome['id']}.xlsx")
    config["plot_file"] = os.path.join(plan["output_dir"], f"RCS_{outcome['id']}.png")
    return config


# The variance methods this pipeline can actually fit. A POSITIVE list, because
# the negative one let everything through: only `mixed` was rejected, so
# "cluster_robsut" / "GEE" / "sandwich" reached the config unchallenged. That is
# not a cosmetic typo — the clustering gate in _validate_diagnostics_honored
# only asks whether a `robust-variance` step exists, so a misspelt method
# satisfied the gate while the step it points at fits nothing recognisable.
# _remedy_coverage now treats an unrecognised method as inert for the same reason.
_ROBUST_METHODS = ("cluster_robust", "gee")


def _robust_method(raw):
    """Validate advanced_analyses.robust_variance.method. Raises on anything else.

    `mixed` keeps its own message: it was withdrawn for a measured statistical
    reason, and "not in the list" would not tell anyone why the method their
    protocol names has disappeared.
    """
    method = str(raw).strip().lower()
    if method in _ROBUST_METHODS or method == "mixed":
        return method
    raise ValueError(
        f"advanced_analyses.robust_variance.method={raw!r} is not a method this "
        f"pipeline fits. Use one of: {', '.join(_ROBUST_METHODS)} "
        f"('cluster_robust' corrects the variance for clustering; 'gee' is for "
        f"repeated measures and needs a correlation_structure). Refused rather than "
        f"passed through: the clustering gate only checks that a robust-variance step "
        f"EXISTS, so a misspelt method would satisfy that gate while the step fits "
        f"nothing — the exposure SE would stay uncorrected with a step in the pipeline "
        f"appearing to have corrected it.")


def gen_robust_variance(plan, step):
    """Cluster-robust / GEE / mixed — advanced_analyses.md section 4."""
    outcome = get_outcome(plan, step["outcome"])
    s = _adv(plan, "robust_variance")
    config = shared_fields(plan)
    config["mode"] = "robust"
    config["grouping"] = plan["grouping"]
    _survival_or_binary(config, outcome)
    config["sections"] = build_sections(plan["covariates"])
    cluster = s.get("cluster_column") or plan.get("study", {}).get("cluster_column")
    if not cluster:
        _method_warn(
            "robust_variance_without_cluster_column",
            "robust-variance step was generated without a cluster_column. Set "
            "advanced_analyses.robust_variance.cluster_column (or study.cluster_column); "
            "the step will block rather than guess which column identifies the cluster.")
    config["cluster_column"] = cluster
    config["method"] = _robust_method(s.get("method", "cluster_robust"))
    if config["method"] == "mixed":
        # Withdrawn 2026-08-11. Measured on data with a real centre effect: the
        # variational approximation widened the exposure SE by 4.8% where the
        # cluster-robust sandwich widened it by 148% — a 30-fold difference on
        # the same clustering, and always in the direction that makes the result
        # look more significant than it is. A method its own reference manual
        # tells you not to use for the primary analysis does not belong in the
        # menu: warning it and generating the config anyway meant whoever picked
        # it still got the number. The ability to handle clustering is NOT
        # removed — 'cluster_robust' and 'gee' both stay.
        raise ValueError(
            "robust-variance method='mixed' is no longer accepted. statsmodels' "
            "variational-Bayes GLMM understated the exposure SE by roughly 30-fold "
            "relative to the cluster-robust sandwich on test data with a real centre "
            "effect (references/advanced_analyses.md section 4), and the error runs in "
            "the direction that inflates significance. Use method='cluster_robust' "
            "(correct the variance) or method='gee' (repeated measures, state the "
            "correlation structure). If a genuine random-effect variance estimate is "
            "the point, fit it in R with lme4::glmer and bring the result in as an "
            "external analysis — do not route it through this step.")
    config["correlation_structure"] = s.get("correlation_structure", "exchangeable")
    # AR(1) is defined by the time gap between observations inside a cluster. With
    # no time column statsmodels uses row order instead, which quietly models a
    # correlation the data may not have — so the step refuses rather than guesses.
    config["within_cluster_time_column"] = s.get("within_cluster_time_column")
    if (str(config["correlation_structure"]).lower() in ("ar1", "ar(1)", "autoregressive")
            and not config["within_cluster_time_column"]):
        _method_warn(
            "gee_ar1_without_time_column",
            "robust-variance requests an autoregressive correlation structure without "
            "advanced_analyses.robust_variance.within_cluster_time_column. AR(1) needs "
            "a real time or visit axis; the step will block rather than let row order "
            "stand in for it. Either supply the column, or use 'exchangeable', which "
            "assumes no ordering.")
    config["compare_to_naive"] = s.get("compare_to_naive", True)
    config["title"] = f"Cluster-robust variance: {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = os.path.join(plan["output_dir"], f"Robust_{outcome['id']}.xlsx")
    return config


def gen_calibration(plan, step):
    """Calibration + Brier + optimism correction — advanced_analyses.md section 5."""
    outcome = get_outcome(plan, step["outcome"])
    s = _adv(plan, "calibration")
    # advanced_analyses.md section 5: this whole set is for PREDICTION-model
    # studies. Reporting calibration for an etiologic association invites the
    # reader to treat an association model as a clinical prediction tool. The
    # rule was written down but nothing enforced it, and "declared in prose,
    # unenforced in code" is the failure mode this pipeline keeps fixing
    # elsewhere (see _validate_manuscript_is_gated). It refuses rather than
    # warns: a warning does not stop the plot being generated and pasted in.
    purpose = _model_purpose(plan, step)
    if purpose != "prediction":
        raise ValueError(
            f"calibration step '{step.get('id')}' needs the model it calibrates to be "
            f"declared a prediction model; got "
            f"{purpose if purpose else 'no value (nothing declares a purpose)'}. "
            f"Calibration, Brier score and optimism-corrected internal validation "
            f"describe how well a model predicts absolute risk — they answer nothing "
            f"about an exposure-outcome association (references/advanced_analyses.md "
            f"section 5). Declare it on the STEP if only this model is prognostic — "
            f"{{\"id\": \"{step.get('id')}\", …, \"model_purpose\": \"prediction\"}} — "
            f"which is how a study with an etiologic primary analysis and one prognostic "
            f"sub-model says so; or on study.model_purpose if the whole paper is a "
            f"prediction study; or drop this step. Reporting a C-index for an etiologic "
            f"study is fine, it just must not be called model performance.")
    config = shared_fields(plan)
    config["mode"] = "calibration"
    # No grouping: a prediction model is fitted on the whole cohort, not compared
    # between two arms. Passing it would imply a split that never happens.
    _survival_or_binary(config, outcome)
    config["sections"] = build_sections(plan["covariates"])
    config["eval_times"] = s.get("eval_times", [])
    # 500 by default (2026-08-11); 200 is the protocol floor and a fast mode,
    # which calibration.py labels as such in the provenance sheet.
    config["bootstrap_n"] = s.get("bootstrap_n", 500)
    config["seed"] = s.get("seed", 42)
    config["n_bins"] = s.get("n_bins", 10)
    config["min_bootstrap_success_frac"] = s.get("min_bootstrap_success_frac", 0.5)
    # Externally supplied predictions (validating someone else's model rather
    # than refitting). None means "fit the model here".
    config["predicted_column"] = s.get("predicted_column")
    # Etiologic by default: most studies in this pipeline ask whether X is
    # associated with Y, and reporting calibration for those invites the reader
    # to treat an association model as a prediction tool.
    config["study_purpose"] = s.get("study_purpose", "etiologic")
    config["title"] = f"Calibration & internal validation: {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["output_file"] = os.path.join(plan["output_dir"],
                                         f"Calibration_{outcome['id']}.xlsx")
    config["plot_file"] = os.path.join(plan["output_dir"],
                                       f"Calibration_{outcome['id']}.png")
    return config


def gen_weighting(plan, step):
    """IPTW / overlap weighting — advanced_analyses.md section 6."""
    outcome = get_outcome(plan, step["outcome"])
    s = _adv(plan, "weighting")
    config = shared_fields(plan)
    config["mode"] = "weighting"
    config["grouping"] = plan["grouping"]
    _survival_or_binary(config, outcome)
    config["sections"] = build_sections(plan["covariates"])
    config["method"] = s.get("method", "iptw")
    config["stabilized"] = s.get("stabilized", True)
    config["trim"] = s.get("trim", {"enabled": False, "percentile": [1, 99]})
    config["seed"] = s.get("seed", 42)
    # Thresholds are surfaced in the plan rather than left inside the script:
    # they decide what gets flagged, so they have to be visible, auditable and
    # changeable in one place (delivery_discipline rule 2). The two positivity
    # ones have no consensus cut-point in the literature and therefore only warn;
    # the sole blocking positivity condition is empty common support, which is
    # structural rather than a chosen number.
    for key, default in (("smd_threshold", 0.1),
                         ("ess_fraction_threshold", 0.5),
                         ("extreme_weight_threshold", 10.0),
                         ("max_weight_share_threshold", 0.05),
                         ("overlap_coefficient_threshold", 0.10),
                         ("nonoverlap_fraction_threshold", 0.20)):
        config[key] = s.get(key, default)
    config["title"] = f"{config['method'].upper()} weighting: {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["abbreviations"] = plan.get("abbreviations", "")
    config["output_file"] = os.path.join(plan["output_dir"],
                                         f"Weighting_{outcome['id']}.xlsx")
    config["plot_file"] = os.path.join(plan["output_dir"],
                                       f"Weighting_{outcome['id']}.png")
    config["love_plot_file"] = os.path.join(plan["output_dir"],
                                            f"Weighting_{outcome['id']}_loveplot.png")
    return config


def gen_immortal_time(plan, step):
    """Landmark / extended Cox — advanced_analyses.md section 7."""
    outcome = get_outcome(plan, step["outcome"])
    s = _adv(plan, "immortal_time")
    config = shared_fields(plan)
    mode = s.get("mode", "landmark")
    config["mode"] = mode
    # Say which arm is the exposed one explicitly. The script defaults to
    # groups[0], so a plan that happens to list the reference group first would
    # invert the hazard ratio with nothing in the output to show it happened.
    grouping = dict(plan["grouping"])
    grouping["groups"] = list(plan["grouping"]["groups"])
    exposed = s.get("exposed_value", grouping["groups"][0].get("value"))
    grouping["exposed_value"] = exposed
    if "exposed_value" not in s:
        _method_warn(
            "immortal_time_exposed_arm_assumed",
            f"immortal-time step assumed the exposed arm is "
            f"{grouping['groups'][0].get('label')!r} (grouping.groups[0], value={exposed!r}). "
            f"If the reference group is listed first, the hazard ratio comes out inverted. "
            f"Set advanced_analyses.immortal_time.exposed_value to state it explicitly.")
    config["grouping"] = grouping
    ot = _survival_or_binary(config, outcome)
    if ot not in _TIME_TO_EVENT_TYPES:
        _method_warn(
            "immortal_time_on_binary_outcome",
            f"immortal-time step generated for a non-survival outcome "
            f"({outcome['id']}, type={outcome['type']}). Landmark and extended Cox both "
            f"need time-to-event data; the step will block. Remove it or point it at a "
            f"survival outcome.")
    config["sections"] = build_sections(plan["covariates"])
    config["exposure_time_column"] = s.get("exposure_time_column")
    config["landmark_times"] = s.get("landmark_times", [])
    config["time_unit"] = s.get("time_unit", "days")
    config["late_exposure_handling"] = s.get("late_exposure_handling", "unexposed_at_landmark")
    config["tv_hr_cutpoints"] = s.get("tv_hr_cutpoints")
    # advanced_analyses.md section 7: the landmark times must be pre-specified
    # WITH a reason. Without one there is nothing to stop a later reader — or a
    # later self — from assuming the times were chosen after seeing the results.
    config["landmark_rationale"] = s.get("landmark_rationale", "")
    if mode == "landmark" and not config["landmark_rationale"]:
        _method_warn(
            "landmark_times_without_rationale",
            f"landmark times {config['landmark_times']} were set without a rationale. "
            f"The protocol requires them to be pre-specified and justified, because "
            f"a reader cannot otherwise tell them apart from times chosen after seeing "
            f"the results. Set advanced_analyses.immortal_time.landmark_rationale and "
            f"record it in decision_log.md.")
    config["title"] = (f"{'Landmark' if mode == 'landmark' else 'Extended Cox'}: "
                       f"{outcome['name']}")
    config["subtitle"] = plan["study"].get("title", "")
    stem = "Landmark" if mode == "landmark" else "ExtendedCox"
    config["output_file"] = os.path.join(plan["output_dir"],
                                         f"{stem}_{outcome['id']}.xlsx")
    config["plot_file"] = os.path.join(plan["output_dir"], f"{stem}_{outcome['id']}.png")
    return config


def gen_evalue(plan, step):
    """E-value — advanced_analyses.md section 1.

    Reads its estimates out of the multivariate output rather than having them
    retyped into a config: delivery_discipline.md rule 1, numbers come from a
    generated file.
    """
    outcome = get_outcome(plan, step["outcome"])
    s = _adv(plan, "evalue")
    # advanced_analyses.md section 1 converts HR/OR to a RISK RATIO before
    # applying VanderWeele & Ding's formula. A competing-risk outcome is routed
    # through cause-specific Cox everywhere in this pipeline (SKILL.md Step 4),
    # so the estimate on offer is an etiologic *hazard* with the competing event
    # censored — feeding it through the HR->RR approximation yields a number
    # that corresponds to no risk contrast at all. Hard block, not a warning:
    # the output is a single headline number that reads as if it were valid.
    if _normalize_outcome_type(outcome["type"]) == "competing_risk":
        raise ValueError(
            f"E-value step '{step.get('id')}' points at outcome '{outcome['id']}', whose "
            f"type is 'competing_risk'. Every regression route in this pipeline handles a "
            f"competing-risk outcome with cause-specific Cox, so Multi_{outcome['id']}.xlsx "
            f"holds a cause-specific hazard ratio. The E-value formula "
            f"(references/advanced_analyses.md section 1) needs an effect on the RISK "
            f"RATIO scale; the HR->RR approximation assumes an HR that corresponds to a "
            f"real risk contrast, which a cause-specific HR under competing events does "
            f"not. The resulting E-value would quantify the sensitivity of nothing. "
            f"Remove this step, or re-specify the outcome as a cause-specific single "
            f"endpoint and say in the manuscript that the E-value refers to that "
            f"etiologic contrast.")
    # Not blocking, unlike the above: an E-value on an associational estimate is
    # not arithmetically wrong, it just answers a question nobody asked, since
    # "how strong must unmeasured confounding be to explain this away" presumes
    # a causal reading. The reviewer's correction: do not switch this on
    # for every observational study.
    _estimand = _estimand_type(plan)
    if _estimand != "causal":
        _method_warn(
            "evalue_without_declared_causal_estimand",
            f"E-value step '{step.get('id')}' is generated while the plan's estimand is "
            f"{_estimand or 'unstated'}. The E-value quantifies how strong unmeasured "
            f"confounding would have to be to explain away a CAUSAL effect; on an "
            f"explicitly associational estimate it has no target to be sensitive about. "
            f"Set \"estimand_type\": \"causal\" in the plan's study block if the paper "
            f"does make a causal claim (and defend that in the discussion), or drop the "
            f"step. This generator never adds an E-value step on its own for exactly "
            f"this reason.")
    config = shared_fields(plan)
    config["mode"] = "evalue"
    _survival_or_binary(config, outcome)
    # Overridable. The default assumes the E-value reads the multivariate step's
    # own workbook, which is true until a project's main model moves (a re-fit
    # under a different specification writes Multi_{id}_T5.xlsx, say). Before
    # this, the only way to point it elsewhere was to hand-patch the generated
    # config — which the next `generate_configs.py` run silently overwrote.
    config["source_file"] = _resolve_output_path(
        plan, s.get("source_file"), f"Multi_{outcome['id']}.xlsx")
    config["source_sheet"] = s.get("source_sheet", "Multivariate Analysis")
    config["reference_confounders"] = s.get("reference_confounders", [])
    if not config["reference_confounders"]:
        _method_warn(
            "evalue_without_benchmark",
            "E-value step has no reference_confounders. The number will be reported "
            "without a scale anchor, so no reader can judge whether that confounder "
            "strength is plausible. Add one or two known strong measured confounders "
            "with their risk ratios to advanced_analyses.evalue.reference_confounders.")
    config["title"] = f"E-value: {outcome['name']}"
    config["subtitle"] = plan["study"].get("title", "")
    config["output_file"] = os.path.join(plan["output_dir"], f"E_value_{outcome['id']}.xlsx")
    return config


def gen_strobe(plan, step):
    """STROBE checklist — advanced_analyses.md section 2."""
    out = plan["output_dir"]
    return {
        "mode": "strobe",
        "plan_path": plan.get("_plan_path") or os.path.join(out, "research_plan.json"),
        "output_dir": out,
        "output_file": _output_path(plan, step, "STROBE_checklist"),
        "md_file": _output_path(plan, step, "STROBE_checklist", ".md"),
    }


def gen_reviewer_challenge(plan, step):
    """Reviewer-challenge gate — references/reviewer_challenge.md.

    Runs no analysis. It reads the aggregate the ten domain agents produced and
    decides whether the manuscript may be written. The version is baked into the
    filename so a challenge against an earlier version of the plan cannot be
    mistaken for a current one.
    """
    out = plan["output_dir"]
    version = plan.get("version", 1)
    s = _adv(plan, "reviewer_challenge")
    return {
        "mode": "reviewer-challenge",
        "plan_path": plan.get("_plan_path") or os.path.join(out, "research_plan.json"),
        "output_dir": out,
        # `or`, not a .get default: plan_template.md documents this key as
        # `null`, and an explicit null is a present key, so .get would hand the
        # gate None and it would exit 2 on every run. Copying the documented
        # template must not be the thing that breaks the gate.
        "aggregate_file": (s.get("aggregate_file")
                           or os.path.join(out, f"reviewer_challenge_v{version}.json")),
    }


GENERATORS = {
    "flowchart": gen_flowchart,
    "table1": gen_table1,
    # One skill, two step shapes — gen_missing_data() routes on step["outcome"].
    "missing-data": gen_missing_data,
    # references/advanced_analyses.md — the seven gaps an adversarial audit
    # called out as the ones a reviewer would reject the paper over.
    "nonlinearity": gen_nonlinearity,
    "robust-variance": gen_robust_variance,
    "calibration": gen_calibration,
    "weighting": gen_weighting,
    "immortal-time": gen_immortal_time,
    "evalue": gen_evalue,
    "strobe": gen_strobe,
    "reviewer-challenge": gen_reviewer_challenge,
    "kaplan-meier": gen_kaplan_meier,
    "competing-risk": gen_competing_risk,
    "univariate-forest": gen_univariate_forest,
    "multivariate-interaction": gen_multivariate_interaction,
    # The executable half of ph_violation_remedy — a declared remedy that runs.
    # One entry per row of _REMEDY_STEPS.
    "ph-stratified": gen_ph_stratified,
    "ph-rmst": gen_ph_rmst,
    "ph-time-varying": gen_ph_time_varying,
    "psm-matching": gen_psm,
    "auc-cstat": gen_auc,
    "manuscript-results": gen_manuscript,
}


def write_manifest(config_dir, generated_configs, plan=None, warnings=None):
    """Write a manifest of all generated configs."""
    warnings = list(METHOD_WARNINGS) if warnings is None else list(warnings)
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "configs": generated_configs,
        "methodological_warnings": warnings,
    }
    if plan is not None:
        # The reviewer-challenge agents read this file; the multiplicity ledger
        # and the covariate provenance are exactly the two things domains 3 and 9
        # otherwise have to infer from prose.
        manifest["plan_schema_version"] = plan.get("plan_schema_version")
        manifest["pipeline_profile"] = _pipeline_profile(plan)
        manifest["estimand_type"] = _estimand_type(plan)
        manifest["model_purpose"] = _model_purpose(plan)
        manifest["multiplicity"] = plan.get("_multiplicity_summary", {})
        manifest["covariate_provenance"] = {
            c.get("column"): _covariate_rationale(plan, c)
            for c in (plan.get("covariates") or [])
        }
        if _pipeline_profile(plan) == "explore":
            # generate_configs cannot set run_pipeline's guardian mode; record
            # the intent where the runner and the user can both see it.
            manifest["guardian_mode_recommended"] = "off"
    manifest_path = os.path.join(config_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  Manifest: {manifest_path}")
    if warnings:
        print(f"\n  ⚠ {len(warnings)} methodological substitution(s) recorded in the manifest.")
        print("    These change what the numbers mean. Present them to the user and")
        print("    log them in decision_log.md before running the pipeline.")


def load_existing_manifest(config_dir):
    """Load an existing manifest.json if present, returning its configs list."""
    manifest_path = os.path.join(config_dir, "manifest.json")
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        return manifest.get("configs", [])
    return []


def validate_plan(plan, plan_path):
    """Fail fast with a human-readable message when a required field is missing,
    instead of a raw KeyError deep inside a generator."""
    problems = []
    if "output_dir" not in plan:
        problems.append('"output_dir" (absolute path for generated configs/outputs)')
    if "study" not in plan or "data_file" not in plan.get("study", {}):
        problems.append('"study.data_file" (absolute path to the dataset)')
    if "grouping" not in plan:
        problems.append('"grouping" {column, groups[]}')
    if "pipeline" not in plan or not isinstance(plan.get("pipeline"), list):
        problems.append('"pipeline" (list of analysis steps)')
    if problems:
        _abort(
            f"research_plan.json ({plan_path}) is missing required field(s):\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\nSee references/plan_template.md for the expected schema."
        )

    # Duplicate ids silently collapse: topo_sort and run_pipeline both key steps
    # by id, so the last declaration wins and every earlier step with that id
    # disappears from the run while still satisfying any depends_on that names
    # it. A gate declared as `g` and then shadowed by a later `g` validates
    # cleanly and never executes.
    ids = [s.get("id") for s in plan["pipeline"]]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        _abort(
            f"research_plan.json ({plan_path}) has duplicate pipeline step id(s): "
            f"{', '.join(str(d) for d in dupes)}.\n"
            f"        Step ids key the dependency graph; a duplicate shadows the earlier "
            f"step, which then never runs while still appearing to satisfy depends_on."
        )

    _validate_schema_fields(plan, plan_path)
    _apply_pipeline_resolution(plan)
    _validate_diagnostics_honored(plan, plan_path)
    _validate_manuscript_is_gated(plan, plan_path)
    _validate_missingness_runs(plan, plan_path)
    _warn_mi_primary_with_psm(plan)
    _record_multiplicity(plan)
    _warn_covariates_without_rationale(plan)
    _warn_disambiguated_outputs(plan)


def _warn_disambiguated_outputs(plan):
    """Say when a step's workbook name changed because another step collided.

    The rename is the right outcome — two steps writing one file meant the
    second was never independently checked — but it moves an artifact a project
    may already reference by name, so it is never silent.
    """
    renamed = []
    for step in (plan.get("pipeline") or []):
        stem = _OUTPUT_STEM.get(step.get("skill"))
        if stem is None or step.get("output_file"):
            continue
        try:
            base = stem(plan, step)
        except Exception:
            continue
        resolved = _output_stem(plan, step, base)
        if resolved != base:
            renamed.append(f"{step.get('id')}: {base}.xlsx -> {resolved}.xlsx")
    if not renamed:
        return
    _method_warn(
        "output_file_disambiguated",
        f"{len(renamed)} step(s) share a skill whose output name is fixed, so their "
        f"workbooks were given distinct names: {'; '.join(renamed)}. Previously both "
        f"wrote the same file — the second overwrote the first, and every post-run check "
        f"(outputs exist, numeric plausibility, PSM direction, sidecar match) resolved "
        f"both steps to the FIRST step's artifact, so the second was never examined. If "
        f"anything already refers to the old filename, update it, or set "
        f"\"output_file\" on each step to name them yourself.")


def _project_pipeline_changes(plan):
    """(changes, projected_plan) — what _plan_pipeline_changes WOULD do.

    Computed on a throwaway copy, so the plan itself is untouched, and with
    warnings suppressed: this is a preview, and a preview that files
    methodological warnings is indistinguishable from the run having happened.
    The copy is returned so the caller can fingerprint the projected result.
    """
    global _SUPPRESS_WARN
    probe = json.loads(json.dumps({k: v for k, v in plan.items()
                                   if not k.startswith("_")}))
    _SUPPRESS_WARN = True
    try:
        return _plan_pipeline_changes(probe), probe
    except Exception as exc:
        print(f"  [WARN] could not project the pipeline changes: {exc}",
              file=sys.stderr)
        return [], probe
    finally:
        _SUPPRESS_WARN = False


def _apply_pipeline_resolution(plan):
    """Apply the profile and the automatic diagnostic steps — when allowed to.

    Three brakes, all deliberate:
      - `--only` (selective regeneration) never restructures the pipeline;
      - a plan that has not been through `--migrate` (no plan_schema_version) is
        only TOLD what would change, because adding a step changes the
        reviewer-challenge fingerprint and a live project must get to decide
        when to pay for that;
      - `"auto_steps_enabled": false` declines permanently.
    """
    plan["_pipeline_changes"] = []
    if plan.get("_only_mode"):
        return
    if plan.get("auto_steps_enabled") is False:
        return
    declared = plan.get("plan_schema_version")
    # `< PLAN_SCHEMA_VERSION` rather than `!=`: a plan written by a NEWER
    # generator is not an old plan, and treating it as one would silently
    # disable the automatic steps it was written to rely on. That case is
    # refused outright in _validate_schema_fields.
    proposed_only = not isinstance(declared, int) or declared < PLAN_SCHEMA_VERSION
    if proposed_only:
        # Work on a copy so the run itself is unaffected, then report.
        pending, _ = _project_pipeline_changes(plan)
        if pending:
            print(f"\n  ℹ This plan predates plan_schema_version "
                  f"{PLAN_SCHEMA_VERSION}, so the pipeline was left exactly as written.")
            print("    Running `generate_configs.py <plan> --migrate` would then add:")
            for kind, name, why in pending:
                print(f"      {kind:<6s} {name}: {why}")
            print("    (adding a step changes the reviewer-challenge fingerprint; "
                  "--migrate reports the cost first.)")
        return
    plan["_pipeline_changes"] = _plan_pipeline_changes(plan)


def _validate_schema_fields(plan, plan_path):
    """Reject a *typo* in one of the schema-v2 enums; never reject its absence.

    Every one of these fields is optional and has a documented default (see the
    resolvers above), because two live projects predate them. What is not
    tolerated is a value nobody reads: `"pipeline_profile": "exploratory-ish"`
    would otherwise fall through to the "submit" default and generate a full
    submission pipeline for someone who asked for the opposite.
    """
    declared = plan.get("plan_schema_version")
    if isinstance(declared, int) and declared > PLAN_SCHEMA_VERSION:
        _abort(
            f"research_plan.json ({plan_path}) declares plan_schema_version "
            f"{declared}, but this\n"
            f"        generator understands {PLAN_SCHEMA_VERSION}. Fields a newer version "
            f"added would be ignored\n"
            f"        rather than applied — including, potentially, gates. Update the "
            f"research-plan skill;\n"
            f"        do NOT lower the number to make this message go away."
        )
    problems = []
    for resolver, label in ((_estimand_type, "estimand_type"),
                            (_model_purpose, "model_purpose"),
                            (_pipeline_profile, "pipeline_profile")):
        try:
            resolver(plan)
        except ValueError as exc:
            problems.append(str(exc))
    try:
        _diagnostics_mode(plan)
        _normalize_diagnostic_flags(plan)
    except ValueError as exc:
        problems.append(str(exc))
    outcomes = [(plan["outcomes"]["primary"], True)] if plan.get("outcomes") else []
    outcomes += [(o, False) for o in (plan.get("outcomes") or {}).get("secondary", [])]
    for outcome, is_primary in outcomes:
        try:
            _outcome_intent(plan, outcome, is_primary)
        except ValueError as exc:
            problems.append(str(exc))
    if problems:
        _abort(
            f"research_plan.json ({plan_path}) has unreadable schema value(s):\n"
            + "\n".join(f"  - {p}" for p in problems)
            + "\n        These fields are optional; an unrecognised value is not, because "
              "it would\n        silently take the default and do the opposite of what it "
              "says.\n        See references/plan_template.md, or run: "
              "generate_configs.py <plan> --migrate"
        )


# Step 3.5 flag -> (what the pipeline must contain to have honoured it, why).
# The pairing is what turns a detection into a gate: SKILL.md:276-280 detects all
# four at plan time and then only "suggests", so the corresponding fatal arrives
# 60 days later from a reviewer-challenge agent, costing a round of ten agents
# and a full pipeline re-run to learn something a set membership test knew on day
# one.
_DIAGNOSTIC_GATES = (
    ("competing_risk", "competing-risk",
     "A competing event was detected. Kaplan-Meier and cause-specific Cox alone "
     "overstate the cumulative incidence of the event of interest, because subjects "
     "who had the competing event are treated as if they could still have it. Add a "
     "competing-risk step (cumulative incidence + Fine-Gray)."),
    ("left_truncation", None,
     "Delayed entry (left truncation) was detected. No skill in this pipeline handles "
     "it: risk sets that include subjects before they were actually under observation "
     "make the KM and Cox estimates BIASED, not merely incomplete. Recording it as a "
     "limitation would publish a wrong number with a caveat attached. Either restrict "
     "the cohort to a time origin every subject is observed from, or handle the delayed "
     "entry outside this pipeline and bring the result in."),
    ("time_varying", "immortal-time",
     "A time-varying exposure was detected at medium/high risk. Classifying subjects by "
     "something that happens after time zero gives the exposed arm a guaranteed "
     "event-free interval (immortal time), which looks like protection and is not. Add a "
     "landmark or extended-Cox step (skill 'immortal-time'), or re-define the exposure "
     "at baseline."),
    ("clustering", "robust-variance",
     "Clustering was detected. Ignoring it makes standard errors too small, confidence "
     "intervals too narrow and p-values too small — the error always runs in the "
     "direction that makes the finding look stronger. Add a robust-variance step "
     "(cluster-robust SE, or GEE for repeated measures)."),
)


def _has_survival_work(plan):
    """True when a step in this plan actually fits a time-to-event model.

    Same skip condition SKILL.md Step 3.5 states ("no survival steps in
    pipeline"), and deliberately not "the plan declares a time-to-event
    outcome": a plan that declares one but models nothing has nothing for the
    diagnostics to be about, and blocking it would be a false positive on the
    plan's own terms. Steps without an `outcome` key (psm / auc) read the
    primary outcome, matching what their generators do.
    """
    primary = (plan.get("outcomes") or {}).get("primary") or {}
    for step in (plan.get("pipeline") or []):
        if step.get("skill") not in _MODELLING_SKILLS:
            continue
        oid = step.get("outcome")
        try:
            outcome = get_outcome(plan, oid) if oid else primary
            if _normalize_outcome_type(outcome.get("type")) in _TIME_TO_EVENT_TYPES:
                return True
        except (ValueError, KeyError):
            # An unresolvable outcome is a different problem, reported elsewhere.
            continue
    return False


# A decision-log ID: a letter-led token with at least one hyphen-joined part
# (D-017, RP-2026-04, D3-R3-02) or a #-prefixed number. Deliberately narrow:
# the point is that the string names a RECORD, which can then be looked up.
_DECISION_ID_RE = re.compile(r"\b(?:#\d+|[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)\b")


def _override_key(name):
    """Canonical key for a diagnostics.overrides entry.

    The same names flags_detected uses, plus `diagnostics_off`, which is not a
    finding but a statement that nothing was looked for. Keeping the two
    namespaces separate here is deliberate: `_canonical_flag` alone rejected
    "diagnostics_off", which made `mode: "off"` a documented setting that no
    plan could ever satisfy — the gate fired, and the "current problem" line it
    printed was empty, so there was nothing to act on either.
    """
    key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    if key in ("diagnostics_off", "diagnostics", "off"):
        return "diagnostics_off"
    return _canonical_flag(name)


def _decision_log_path(plan):
    """Where the decision log lives (plan-declared, else beside the outputs)."""
    declared = plan.get("decision_log")
    if declared:
        return os.path.expanduser(declared)
    return os.path.join(plan.get("output_dir", ""), "decision_log.md")


def _decision_log_entry(plan, decision_id):
    """The decision_log.md text for `decision_id`, or None if it is not there.

    "Not there" covers both a missing file and an ID nobody wrote up. Both mean
    the same thing for an override: there is nothing to read, so the override
    documents nothing.
    """
    path = _decision_log_path(plan)
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    lines = text.splitlines()
    hits = [i for i, ln in enumerate(lines) if decision_id in ln]
    if not hits:
        return None
    # The entry is the line that names it plus everything up to the next
    # heading — enough to check what the decision is actually about.
    start = hits[0]
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].lstrip().startswith("#") or _DECISION_ID_RE.search(lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


# What an override for each flag has to be seen to be about. Checked against the
# decision-log entry text so that an ID pointing at an unrelated decision (or at
# a decision about a different outcome) does not release the gate.
#
# This is the ONE place in this file that matches on prose, and it is not a
# cross-script contract: decision_log.md is written by a person, in whatever
# words they choose, and there is no structured field to read instead — checking
# that their justification is about this finding is inherently a text question.
# Do not take it as a pattern to copy. Matching another SCRIPT's human-readable
# output is a different thing and has failed here three times (the "? levels"
# label below, the [FATAL] prefix, line-number references); those all had a
# structured field available and should have used it. When the producer has a
# field, read the field.
_FLAG_KEYWORDS = {
    # Not a flag — the pseudo-key for "the diagnostics were not run at all".
    # It lives here rather than in _CANONICAL_FLAGS so that it can be named in
    # diagnostics.overrides without also becoming something flags_detected
    # would accept as a finding.
    "diagnostics_off": ("diagnostic", "survival-diagnostics", "not applicable",
                        "no time-to-event", "診斷", "不適用"),
    "competing_risk": ("competing risk", "competing event", "competing-risk",
                       "fine-gray", "fine gray", "競爭"),
    "left_truncation": ("left truncation", "left-truncation", "delayed entry",
                        "delayed-entry", "左截斷", "延遲進入"),
    "time_varying": ("time-varying", "time varying", "immortal time",
                     "immortal-time", "landmark", "時間相依", "不死時間"),
    "clustering": ("cluster", "clustering", "random effect", "gee",
                   "群集", "叢集"),
}


def _diagnostic_override(plan, flag, affected_outcomes):
    """(ok, detail) for one flag's structured override.

    Returns (False, why-it-does-not-count) or (True, a description that names
    the decision). What changed on 2026-08-12: a bare
    `override_reason: "N/A"` used to release ALL FOUR gates at once, with
    nothing checked. An override is a methodological decision about what the
    published numbers mean, so it now has to name a record that exists, is about
    this finding, and covers the outcomes the finding applies to:

        "diagnostics": {
          "overrides": {
            "clustering": {"decision_id": "D-017",
                           "reason": "single centre; the cluster is the study",
                           "outcomes": ["primary", "secondary_1"]}
          }
        }
    """
    diag = plan.get("diagnostics") or {}
    overrides = diag.get("overrides")
    if not isinstance(overrides, dict) or not overrides:
        legacy = diag.get("override_reason")
        if legacy:
            return False, (
                "diagnostics.override_reason is a free-text field that used to release "
                "every gate at once; it no longer releases any. Move it to "
                "diagnostics.overrides.<flag> = {\"decision_id\": …, \"reason\": …, "
                "\"outcomes\": [...]}")
        return False, None
    entry = None
    for key, val in overrides.items():
        if _override_key(key) == flag:
            entry = val
            break
    if entry is None:
        return False, None
    if not isinstance(entry, dict):
        return False, (f"diagnostics.overrides.{flag} must be an object with "
                       f"decision_id / reason / outcomes, not {type(entry).__name__}")
    decision_id = str(entry.get("decision_id") or "").strip()
    if not decision_id:
        return False, f"diagnostics.overrides.{flag} has no decision_id"
    if not _DECISION_ID_RE.fullmatch(decision_id):
        return False, (f"decision_id {decision_id!r} does not look like a permanent "
                       f"record ID (expected e.g. D-017, RP-2026-04, #42)")
    if not str(entry.get("reason") or "").strip():
        return False, f"diagnostics.overrides.{flag} has no reason"
    logged = _decision_log_entry(plan, decision_id)
    if logged is None:
        return False, (f"{decision_id} is not in {_decision_log_path(plan)}. An "
                       f"override whose reasoning cannot be read is the same as "
                       f"deleting the finding")
    low = logged.lower()
    if not any(k in low for k in _FLAG_KEYWORDS.get(flag, ())):
        return False, (f"{decision_id} exists but its entry does not mention {flag} — "
                       f"an ID pointing at some other decision does not document this "
                       f"one")
    covered = entry.get("outcomes")
    if covered is None:
        return False, (f"diagnostics.overrides.{flag} does not say which outcomes it "
                       f"covers. It has to name them: {sorted(affected_outcomes)}")
    missing = sorted(set(affected_outcomes) - set(covered))
    if missing:
        return False, (f"{decision_id} covers {sorted(set(covered))} but the finding "
                       f"applies to {sorted(affected_outcomes)}; not covered: {missing}")
    return True, f"{decision_id}: {entry['reason']}"


# The steps whose estimates a Step 3.5 finding would corrupt — i.e. the models a
# remedy has to actually cover. `psm-matching` / `auc-cstat` carry no `outcome`
# key and read the primary outcome, matching their generators.
_PRIMARY_MODEL_SKILLS = ("kaplan-meier", "competing-risk", "univariate-forest",
                         "multivariate-interaction", "psm-matching", "auc-cstat",
                         "nonlinearity", "weighting", "calibration")


def _modelled_outcomes(plan, time_to_event_only=False):
    """{outcome_id: outcome} for every outcome a primary model is fitted on."""
    primary = (plan.get("outcomes") or {}).get("primary") or {}
    found = {}
    for step in (plan.get("pipeline") or []):
        if step.get("skill") not in _PRIMARY_MODEL_SKILLS:
            continue
        if step.get("status") == "skipped":
            continue
        oid = step.get("outcome") or primary.get("id")
        try:
            outcome = get_outcome(plan, oid)
        except (ValueError, KeyError):
            continue
        if time_to_event_only:
            try:
                if _normalize_outcome_type(outcome.get("type")) not in _TIME_TO_EVENT_TYPES:
                    continue
            except ValueError:
                continue
        found[oid] = outcome
    return found


def _remedy_coverage(plan, remedy_skill, needed_outcomes):
    """(uncovered_outcome_ids, inert_step_ids) for one remedy skill.

    "There is a robust-variance step somewhere in the pipeline" was accepted as
    proof that clustering had been handled — even when that step pointed at a
    secondary outcome while the primary Cox model, the one in the abstract, still
    ignored it. Coverage is therefore per outcome, and a step whose own config
    would refuse to run (a cluster-robust step with no cluster column; a landmark
    step with no exposure time column) does not count as covering anything.
    """
    primary_id = ((plan.get("outcomes") or {}).get("primary") or {}).get("id")
    covered, inert = set(), []
    for step in (plan.get("pipeline") or []):
        if step.get("skill") != remedy_skill or step.get("status") == "skipped":
            continue
        oid = step.get("outcome") or primary_id
        if remedy_skill == "robust-variance":
            s = _adv(plan, "robust_variance")
            if not (s.get("cluster_column")
                    or (plan.get("study") or {}).get("cluster_column")):
                inert.append(f"{step.get('id')} (no cluster_column: the step blocks "
                             f"rather than guessing which column is the cluster)")
                continue
            method = str(s.get("method", "cluster_robust")).strip().lower()
            if method not in _ROBUST_METHODS:
                # A misspelt method is how this gate was bypassed: the step
                # exists, so "clustering is handled" looked true, while the
                # method it names fits nothing. `mixed` lands here too — it is
                # spelled correctly and still does not correct the variance.
                inert.append(f"{step.get('id')} (method={s.get('method')!r} is not one "
                             f"of {', '.join(_ROBUST_METHODS)}, so this step does not "
                             f"correct the variance for clustering)")
                continue
        if remedy_skill == "immortal-time":
            s = _adv(plan, "immortal_time")
            if not s.get("exposure_time_column"):
                inert.append(f"{step.get('id')} (no exposure_time_column: nothing "
                             f"defines when exposure starts, so no immortal time can "
                             f"be removed)")
                continue
            if s.get("mode", "landmark") == "landmark" and not s.get("landmark_times"):
                inert.append(f"{step.get('id')} (no landmark_times)")
                continue
        covered.add(oid)
    return sorted(set(needed_outcomes) - covered), inert


def _diagnostics_off_accepted(plan):
    """(ok, detail) for `diagnostics.mode: "off"`. `detail` is never empty.

    Two routes, and the weaker one is deliberate. Waiving a DETECTED finding and
    declaring the check inapplicable are not the same act: the first publishes a
    number already known to be biased, the second says "we did not look", which
    is a limitation. So mode='off' accepts a substantive free-text reason —
    while always recording it as a methodological warning that reaches the
    manifest and the reviewer-challenge agents — and a decision-log record is
    offered as the stronger form rather than demanded.

    "Substantive" rules out the pattern this whole area exists to stop: a token
    like "N/A" that satisfies a truthiness test and tells nobody anything.
    """
    diag = plan.get("diagnostics") or {}
    ok, detail = _diagnostic_override(plan, "diagnostics_off",
                                      sorted(_modelled_outcomes(plan)))
    if ok:
        return True, detail
    structured_problem = detail          # None unless an overrides entry was tried
    for key in ("reason", "override_reason", "note"):
        raw = diag.get(key)
        if not isinstance(raw, str):
            continue
        reason = raw.strip()
        if len(reason) < 10:
            return False, (f"diagnostics.{key} = {raw!r} is too short to be a reason. "
                           f"A token like 'N/A' passes a truthiness check and tells the "
                           f"next reader nothing")
        return True, f"declared not applicable: {reason}"
    if structured_problem:
        return False, structured_problem
    return False, ("the diagnostics block gives no reason: it has no `reason` string "
                   "and no `overrides.diagnostics_off` entry")


def _validate_diagnostics_honored(plan, plan_path):
    """Step 3.5's findings are gates, not suggestions (review section C, P1-1).

    Three outcomes, deliberately distinguishable:
      - no survival work at all                  -> nothing to check
      - survival work but no diagnostics block   -> blocking, and the message says
                                                    which of the two fixes applies
      - flag detected and unhandled              -> FATAL, overridable on the record
    """
    if not _has_survival_work(plan):
        return
    diag = plan.get("diagnostics") or {}

    if not _diagnostics_declared(plan):
        _abort(
            f"research_plan.json ({plan_path}) has time-to-event analyses "
            f"but no `diagnostics` block.\n"
            f"        This is NOT the same as 'the diagnostics found nothing' — nothing "
            f"has been run,\n"
            f"        so competing risks, delayed entry, time-varying exposure and "
            f"clustering are all\n"
            f"        unknown rather than absent. Do one of:\n"
            f"          1. Run SKILL.md Step 3.5 (survival-diagnostics) and let it write "
            f"diagnostics.flags_detected; or\n"
            f"          2. If it genuinely does not apply, state that: "
            f"\"diagnostics\": {{\"mode\": \"off\",\n"
            f"             \"override_reason\": \"<why, with a decision_log.md ID>\"}}; or\n"
            f"          3. For a plan written before this field existed, run:  "
            f"generate_configs.py {plan_path} --migrate\n"
            f"             (it adds the field set with conservative defaults and tells "
            f"you what it changed)."
        )

    try:
        mode = _diagnostics_mode(plan)
        flags = _normalize_diagnostic_flags(plan)
    except ValueError as exc:
        _abort(f"research_plan.json ({plan_path}) diagnostics block: {exc}")

    if mode == "off":
        ok, detail = _diagnostics_off_accepted(plan)
        if not ok:
            affected = sorted(_modelled_outcomes(plan))
            _abort(
                f"research_plan.json ({plan_path}) sets diagnostics.mode='off' on "
                f"a plan that\n"
                f"        fits survival models, without saying why.\n"
                f"        Problem: {detail}\n"
                f"        Either state the reason in the block:\n"
                f"          \"diagnostics\": {{\"mode\": \"off\", \"reason\": \"<why the "
                f"survival diagnostics do not\n"
                f"              apply to this design>\"}}\n"
                f"        or, better, point at the decision that was taken:\n"
                f"          \"diagnostics\": {{\"mode\": \"off\", \"overrides\": "
                f"{{\"diagnostics_off\":\n"
                f"              {{\"decision_id\": \"D-nnn\", \"reason\": \"…\", "
                f"\"outcomes\": {affected}}}}}}}\n"
                f"        with D-nnn written up in {_decision_log_path(plan)}. Either way "
                f"the choice is\n"
                f"        recorded in the manifest and belongs in the limitations."
            )
        _method_warn(
            "diagnostics_turned_off",
            f"survival diagnostics are switched off on a plan that fits survival models "
            f"({detail}). Competing risks, delayed entry, time-varying exposure and "
            f"clustering are therefore UNKNOWN for this analysis rather than absent — "
            f"that is a limitation to state in the manuscript, not a clean bill of "
            f"health.")
        return

    if mode is None or diag.get("flags_detected") is None:
        _abort(
            f"research_plan.json ({plan_path}) has a diagnostics block that "
            f"records no run:\n"
            f"        mode={diag.get('mode')!r}, flags_detected="
            f"{diag.get('flags_detected')!r}.\n"
            f"        Step 3.5 has not written its findings back (SKILL.md Step 3.5 item "
            f"3). Re-run it, or\n"
            f"        set mode='off' with a diagnostics.overrides entry saying why it does "
            f"not apply."
        )

    _validate_diagnostics_provenance(plan, plan_path)

    problems = []
    for flag, remedy, why in _DIAGNOSTIC_GATES:
        if not flags.get(flag, {}).get("detected"):
            continue
        if flag == "time_varying":
            # No grade recorded is treated as triggering. The alternative reads
            # silence as 'low', which is how a detected-but-ungraded flag would
            # slip through; the override path is the way out, and it leaves a
            # record.
            if flags[flag].get("risk") in ("low", "none"):
                continue
        # Which models the finding would corrupt. Competing risks only bear on
        # time-to-event outcomes; the other three bear on every fitted model.
        affected = _modelled_outcomes(plan, time_to_event_only=(flag == "competing_risk"))
        if not affected:
            continue
        uncovered, inert = ([], []) if remedy is None else _remedy_coverage(
            plan, remedy, affected)
        if remedy is not None and not uncovered and not inert:
            continue
        ok, detail = _diagnostic_override(plan, flag, sorted(affected))
        if ok:
            _method_warn(
                f"diagnostic_gate_overridden_{flag}",
                f"Step 3.5 detected '{flag}' and the pipeline does not handle it for "
                f"{sorted(affected)}; the gate was released by {detail}. {why} State it in "
                f"the manuscript's limitations — it is a decision about what the numbers "
                f"mean, not a configuration detail.")
            continue
        lines = [f"  - {flag}: {why}"]
        if remedy is None:
            lines.append("      Fix: there is no in-pipeline remedy (see above).")
        else:
            if uncovered:
                lines.append(f"      Not covered by any '{remedy}' step: {uncovered}. A "
                             f"remedy for one outcome does not fix the model reported for "
                             f"another.")
            for bad in inert:
                lines.append(f"      Present but inert: {bad}")
        if detail:
            lines.append(f"      Override rejected: {detail}")
        problems.append("\n".join(lines))

    if problems:
        _abort(
            f"research_plan.json ({plan_path}): Step 3.5 detected "
            f"{len(problems)} condition(s) the\n"
            f"        pipeline does not handle. These are plan-time facts, so they are "
            f"refused now rather\n"
            f"        than surfaced by a reviewer-challenge agent after everything has "
            f"run:\n"
            + "\n".join(problems)
            + "\n        To proceed anyway, add a per-flag record — one gate, one "
              "decision, one ID:\n"
              "          \"diagnostics\": {\"overrides\": {\"<flag>\": {\"decision_id\": "
              "\"D-nnn\",\n"
              "              \"reason\": \"…\", \"outcomes\": [\"primary\", …]}}}\n"
              "        D-nnn has to exist in decision_log.md and its entry has to be "
              "about this finding."
        )


def _validate_diagnostics_provenance(plan, plan_path):
    """`mode: "completed"` has to be attributable to an actual run.

    Writing `{"mode": "completed", "flags_detected": []}` by hand is a clean bill
    of health nobody issued, and it is the cheapest way to get past every gate
    above. So the claim carries evidence: the report the run produced, when it
    ran, and — where it can be checked — which dataset it ran on.
    """
    diag = plan["diagnostics"]
    report = diag.get("report_path")
    if not report:
        _abort(
            f"research_plan.json ({plan_path}) says diagnostics.mode='completed' "
            f"but does not\n"
            f"        say where the report is. SKILL.md Step 3.5 writes "
            f"diagnostics.report_path\n"
            f"        (<OUTPUT_DIR>/diagnostics/diagnostic_report.json). Without it, "
            f"'completed' is an\n"
            f"        assertion with nothing behind it."
        )
    report = os.path.expanduser(report)
    if not os.path.isabs(report):
        report = os.path.join(plan.get("output_dir", ""), report)
    if not os.path.exists(report):
        _abort(
            f"research_plan.json ({plan_path}): diagnostics.report_path points at\n"
            f"        {report}\n"
            f"        which is not on disk. Either the diagnostics have not been run, or "
            f"the report was\n"
            f"        deleted — in both cases the findings in this plan cannot be checked "
            f"against anything."
        )
    completed_at = diag.get("completed_at")
    if not completed_at:
        _abort(
            f"research_plan.json ({plan_path}): diagnostics.mode='completed' "
            f"without\n"
            f"        completed_at. A run with no timestamp cannot be told apart from one "
            f"that predates\n"
            f"        the current dataset. Add \"completed_at\": \"<ISO timestamp>\"."
        )
    try:
        ran_at = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
    except ValueError:
        _abort(
            f"research_plan.json ({plan_path}): diagnostics.completed_at="
            f"{completed_at!r} is not an ISO timestamp."
        )

    data_file = os.path.expanduser((plan.get("study") or {}).get("data_file", ""))
    if not os.path.exists(data_file):
        _method_warn(
            "diagnostics_data_not_verifiable",
            f"the dataset ({data_file}) is not readable from here, so it cannot be "
            f"confirmed that the survival diagnostics ran on the data this pipeline is "
            f"about to analyse. Re-check before the manuscript step.")
        return
    # Timestamps first: this catches the common case (data rebuilt after the
    # diagnostics ran) with no cooperation needed from the R driver.
    data_mtime = datetime.fromtimestamp(os.path.getmtime(data_file))
    if ran_at.tzinfo is not None:
        ran_at = ran_at.replace(tzinfo=None)
    if data_mtime > ran_at:
        _abort(
            f"research_plan.json ({plan_path}): the dataset was modified "
            f"({data_mtime.isoformat(timespec='seconds')}) AFTER\n"
            f"        the survival diagnostics ran "
            f"({ran_at.isoformat(timespec='seconds')}). The recorded flags describe "
            f"an\n"
            f"        earlier version of the data. Re-run SKILL.md Step 3.5."
        )
    declared_fp = diag.get("data_fingerprint")
    actual_fp = _data_fingerprint(data_file)
    if declared_fp and actual_fp and declared_fp != actual_fp:
        _abort(
            f"research_plan.json ({plan_path}): diagnostics.data_fingerprint="
            f"{declared_fp}\n"
            f"        but {data_file} hashes to {actual_fp}. The diagnostics ran on a "
            f"different dataset\n"
            f"        than the one this pipeline analyses. Re-run SKILL.md Step 3.5."
        )
    if not declared_fp:
        if plan.get("plan_schema_version", 0) >= PLAN_SCHEMA_VERSION:
            _abort(
                f"research_plan.json ({plan_path}): diagnostics.mode='completed' "
                f"without a\n"
                f"        data_fingerprint. The timestamp check passed, but a timestamp "
                f"cannot tell a\n"
                f"        re-saved file from a rebuilt one. Add "
                f"\"data_fingerprint\": \"{actual_fp}\"\n"
                f"        to the diagnostics block if the current dataset is what Step 3.5 "
                f"ran on;\n"
                f"        `--migrate` fills it in for you after checking the report is "
                f"older than nothing else."
            )
        _method_warn(
            "diagnostics_without_data_fingerprint",
            f"the diagnostics block has no data_fingerprint, so only its timestamp ties it "
            f"to the current dataset. Add \"data_fingerprint\": \"{actual_fp}\" (or run "
            f"--migrate) so a rebuilt dataset cannot pass as the one that was checked.")


def _record_multiplicity(plan):
    """Count the tests by family and intent so the manifest can carry it.

    No global FDR: correcting a pre-specified primary endpoint alongside every
    exploratory analysis demotes it. What a reader needs instead is the count —
    how many confirmatory tests are in the primary family, and how many
    exploratory analyses exist at all — printed in the table footnotes.
    """
    outcomes = [(plan["outcomes"]["primary"], True)] if plan.get("outcomes") else []
    outcomes += [(o, False) for o in (plan.get("outcomes") or {}).get("secondary", [])]
    summary = {}
    for outcome, is_primary in outcomes:
        family, intent = _outcome_intent(plan, outcome, is_primary)
        bucket = summary.setdefault(
            family, {"confirmatory": [], "exploratory": [], "unknown": []})
        bucket[intent].append(outcome.get("id"))
    plan["_multiplicity_summary"] = summary
    unknown = sorted(oid for v in summary.values() for oid in v["unknown"])
    if unknown:
        _method_warn(
            "analysis_intent_unconfirmed",
            f"{len(unknown)} outcome(s) have analysis_intent='unknown': "
            f"{', '.join(str(o) for o in unknown)}. Nothing here guesses: an outcome "
            f"sitting in outcomes.secondary can be a pre-specified co-primary endpoint, "
            f"and labelling it exploratory would quietly demote it. Set "
            f"analysis_intent to 'confirmatory' or 'exploratory' per outcome (and a "
            f"hypothesis_family), then say so in the statistical methods.")
    confirmatory = sum(len(v["confirmatory"]) for v in summary.values())
    if confirmatory > 1:
        _method_warn(
            "multiple_confirmatory_outcomes",
            f"{confirmatory} outcomes are marked analysis_intent='confirmatory' across "
            f"{len(summary)} hypothesis family/families. Family-wise error is not "
            f"controlled anywhere in this pipeline, so either designate one primary "
            f"endpoint and mark the rest 'exploratory', or state the correction used in "
            f"the statistical methods. Do not apply a blanket FDR across all of them: "
            f"that would also shrink the pre-specified primary result.")


def _warn_covariates_without_rationale(plan):
    """Domain 3 of the reviewer challenge opens by asking why each covariate is
    in the model. Nothing in the schema could answer it before 2026-08-11."""
    missing = [c.get("column") for c in (plan.get("covariates") or [])
               if not _covariate_rationale(plan, c)]
    if not missing:
        return
    _method_warn(
        "covariates_without_selection_rationale",
        f"{len(missing)} covariate(s) have no selection_rationale: "
        f"{', '.join(str(m) for m in missing[:8])}"
        f"{'…' if len(missing) > 8 else ''}. Record for each whether it entered on "
        f"clinical/DAG grounds specified before looking at the data, or by a "
        f"variable-by-variable screen (which invalidates the p-values that follow). Put "
        f"it in covariates[].selection_rationale, or in the plan-level "
        f"covariate_provenance map, or state one covariates_selection_rule covering all "
        f"of them.")


# Steps whose N depends on which rows are complete, and which therefore cannot be
# read without knowing what was dropped.
_MODELLING_SKILLS = ("kaplan-meier", "competing-risk", "univariate-forest",
                     "multivariate-interaction", "ph-stratified", "ph-rmst",
                     "ph-time-varying", "psm-matching", "auc-cstat", "nonlinearity",
                     "robust-variance", "calibration", "weighting", "immortal-time")


def _validate_missingness_runs(plan, plan_path):
    """The missing-data assessment is not optional once anything is modelled.

    missing_data_protocol.md §1: the assessment always runs, because "this
    dataset has no missingness problem" is itself a claim that needs evidence.
    Until 2026-08-11 that rule lived only in SKILL.md, so it held exactly as long
    as whoever wrote the plan remembered it — a hand-edited plan could drop the
    step and nothing would say a word, while every downstream model silently ran
    listwise.
    """
    pipeline = plan.get("pipeline") or []
    modelling = [s["id"] for s in pipeline if s.get("skill") in _MODELLING_SKILLS]
    if not modelling:
        return
    has_assessment = any(s.get("skill") == "missing-data" and not s.get("outcome")
                         for s in pipeline)
    if not has_assessment:
        _abort(
            f"research_plan.json ({plan_path}) fits models "
            f"({', '.join(modelling[:4])}{'…' if len(modelling) > 4 else ''}) but has no\n"
            f"        missing-data assessment step. Every one of those models drops "
            f"incomplete rows;\n"
            f"        how many, and whether that is related to the outcome, is not "
            f"optional information\n"
            f"        (references/missing_data_protocol.md §1).\n"
            f"        Add:  {{\"id\": \"missingness\", \"skill\": \"missing-data\", "
            f"\"depends_on\": []}}"
        )


def _warn_mi_primary_with_psm(plan):
    """MI as the declared primary analysis while PSM also runs is not a pairing
    the pipeline can reconcile: the PSM step stays complete-case
    (missing_data_protocol.md §6), so it is not a same-estimand sensitivity
    analysis for an MI primary — different estimand, different subset. The
    imputation step already warns the two are not directly comparable; recording
    it as a methodological substitution here too, because under
    `primary_analysis: "mi"` it changes what the paper's main number means.
    run_pipeline additionally forces a MANDATORY checkpoint on the MI outcome
    groups so a human sees the comparison before it is signed off.
    """
    md = plan.get("missing_data") or {}
    if md.get("primary_analysis") != "mi":
        return
    has_psm = ((plan.get("analyses") or {}).get("psm_enabled")
               or any(s.get("skill") == "psm-matching" for s in (plan.get("pipeline") or [])))
    if not has_psm:
        return
    _method_warn(
        "psm_complete_case_under_mi_primary",
        "missing_data.primary_analysis is 'mi' while a PSM step is also enabled. The PSM "
        "analysis stays complete-case, so it estimates a different quantity on a different "
        "subset and cannot be presented as a sensitivity analysis of the MI primary. State "
        "in the manuscript which analysis is primary and why the two Ns differ, and log the "
        "choice in decision_log.md with a permanent ID.")


def _transitive_deps(pipeline, step_id, _seen=None):
    """Every step id reachable through depends_on from step_id."""
    by_id = {s["id"]: s for s in pipeline}
    seen = set() if _seen is None else _seen
    for dep in (by_id.get(step_id, {}).get("depends_on") or []):
        if dep in seen:
            continue
        seen.add(dep)
        _transitive_deps(pipeline, dep, seen)
    return seen


def _validate_manuscript_is_gated(plan, plan_path):
    """The manuscript step must sit behind the reviewer-challenge gate.

    Before 2026-08-11 this rule lived only in SKILL.md Step 6.7, which meant it
    held exactly as long as the agent following the workflow remembered it. A
    rule the runner cannot enforce is a suggestion; wiring it into depends_on is
    what makes "the challenge was skipped" impossible to confuse with "the
    challenge passed".
    """
    pipeline = plan.get("pipeline") or []
    # A step parked by pipeline_profile="explore" is not going to be written, so
    # requiring a gate in front of it would block an exploratory run over a
    # manuscript nobody is producing.
    manuscript = [s for s in pipeline if s.get("skill") == "manuscript-results"
                  and s.get("status") != "skipped"]
    if not manuscript:
        return
    gates = {s["id"] for s in pipeline if s.get("skill") == "reviewer-challenge"}
    if not gates:
        _abort(
            f"research_plan.json ({plan_path}) has a manuscript-results step but no\n"
            f"        reviewer-challenge step. The manuscript may not be written before the\n"
            f"        ten-domain challenge has run (references/reviewer_challenge.md).\n"
            f"        Add:  {{\"id\": \"reviewer_challenge\", \"skill\": \"reviewer-challenge\",\n"
            f"               \"depends_on\": [<the analysis steps it reviews>]}}\n"
            f"        and list it in the manuscript step's depends_on."
        )
    ungated = [s["id"] for s in manuscript
               if not (gates & _transitive_deps(pipeline, s["id"]))]
    if ungated:
        _abort(
            f"research_plan.json ({plan_path}): manuscript step(s) "
            f"{', '.join(ungated)} do not\n"
            f"        depend on the reviewer-challenge gate ({', '.join(sorted(gates))}).\n"
            f"        A gate the pipeline can route around is not a gate — add it to\n"
            f"        depends_on."
        )


# Steps that only exist to produce a submission. In `explore` they are parked
# (status "skipped" — a state pipeline_state_machine.md already defines and
# run_pipeline.should_run already honours) rather than deleted, so switching the
# profile back to "submit" restores them without re-authoring anything.
_SUBMIT_ONLY_SKILLS = ("manuscript-results", "reviewer-challenge", "strobe")


def _precheck_module():
    """precheck_configs, imported by path. Raises if it cannot be loaded.

    Imported rather than mirrored. There were briefly two parameter counts in
    this codebase — this file charged 1 for a categorical with no label_map,
    precheck_configs charged (L-1) — and the looser one sat in front of the
    decision about whether to add a spline, which is to say the overfitting
    guard had a back door that issued splines. A second copy of a definition
    does not stay in step with the first; the same conclusion reviewer_challenge
    reached when it started importing _normalize_model_purpose from here instead
    of keeping its own table.
    """
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "precheck_configs.py")
    spec = importlib.util.spec_from_file_location("_precheck_configs", path)
    if spec is None:
        raise ImportError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _prospective_param_budget(plan, outcome_id, spline_columns, knots):
    """(total, unpriced_terms, provenance) if every continuous covariate were splined.

    Delegates the arithmetic to precheck_configs.parameter_budget(), the single
    definition of the EPV denominator, by handing it a COPY of the plan whose
    nonlinearity block names the splines being considered. df and configs are
    None on purpose: at plan time there is no dataframe, and the configs on disk
    belong to a previous run — parameter_budget's documented fallback is the
    plan-level count with `provenance["source"] == "plan"`, which is what this
    decision should be made on.

    `total` is a LOWER BOUND: a categorical whose levels nothing declares is
    priced at its floor of 1. So the events-per-parameter figure derived from it
    is an UPPER bound, and `unpriced_terms` is what says whether that distinction
    matters here. Each entry is {"column", "reason", "floor"}, optionally with a
    "ceiling"/"max_levels" when something does bound the term.

    Re-pricing those terms is deliberately NOT done here. A number called "the
    parameters this model fits" stops being that the moment each caller is free
    to re-price its items — which is the two-parameter-counts failure one level
    up, with the disagreement moved from between two functions to between one
    function and its callers.
    """
    probe = json.loads(json.dumps({k: v for k, v in plan.items()
                                   if not k.startswith("_")}))
    adv = probe.setdefault("advanced_analyses", {}).setdefault("nonlinearity", {})
    adv["enabled"] = True                      # _spline_variables returns nothing otherwise
    adv["variables"] = list(spline_columns)
    adv["knots"] = int(knots)
    total, breakdown, provenance = _precheck_module().parameter_budget(
        probe, df=None, configs=None, outcome_id=outcome_id)
    if "unpriced_terms" in provenance:
        unpriced = list(provenance.get("unpriced_terms") or [])
    else:
        # TRANSITIONAL (remove once every precheck_configs in use ships
        # `unpriced_terms`): reconstruct the signal from the STRUCTURED flag the
        # producer sets on each breakdown entry, `is_floor` — the same boolean
        # that decides whether it appends to unpriced_terms in the first place.
        #
        # The first version of this shim matched the human-readable type label
        # against "? levels". The producer writes "(levels unknown)", so it
        # never matched: the fallback silently found nothing unpriced and the
        # auto-RCS gate then treated a lower bound as an exact count and granted
        # a spline on a budget that might not exist. Reading `.get(..., [])` was
        # rejected for exactly that fail-open behaviour, and then the
        # replacement failed open too, because a display string was used as the
        # contract. Formatting is not an interface; a field is.
        unpriced = [{"column": b.get("term"), "floor": b.get("params", 1),
                     "reason": b.get("unpriced_reason")
                     or "priced at its floor by parameter_budget (is_floor)"}
                    for b in breakdown if b.get("is_floor")]
        if unpriced:
            _method_warn(
                "parameter_budget_missing_unpriced_terms",
                f"precheck_configs.parameter_budget() did not return `unpriced_terms`, so "
                f"the unpriced terms were reconstructed from the `is_floor` flag on its "
                f"breakdown entries: "
                f"{', '.join(str(u['column']) for u in unpriced)}. That reconstruction is "
                f"a temporary shim for an older precheck_configs; the two scripts should "
                f"be updated together.")
    return total, unpriced, provenance


def _describe_unpriced(term):
    """One unpriced term as 'column (reason)' for a message."""
    col = term.get("column", "?")
    reason = term.get("reason")
    return f"{col} ({reason})" if reason else str(col)


def _worst_case_params(total, unpriced):
    """Largest parameter count consistent with the unpriced terms, or None.

    None means unbounded — nothing declares a ceiling for at least one term, so
    no finite worst case exists and sufficiency cannot be demonstrated. Charging
    an invented ceiling (this file briefly assumed ten levels) is the same
    mistake as re-pricing: a number nobody derived, doing the work of a fact.

    A term may carry `ceiling` / `max_levels` when something does bound it; the
    extra cost over its floor is then (ceiling - 1) - floor.
    """
    extra = 0
    for term in unpriced:
        ceiling = term.get("ceiling") or term.get("max_levels")
        if not ceiling:
            return None
        extra += max(0, (int(ceiling) - 1) - int(term.get("floor", 1)))
    return total + extra


def _declared_events(outcome):
    """Total events for this outcome across the fitted analysis set, or None.

    Total, not the smallest exposure group's: every textbook definition of EPV
    (Peduzzi 1996, Concato 1995, Riley 2019) counts the outcome events in the
    model's fitted sample. Using the smaller arm systematically blocks
    imbalanced cohorts that have plenty of events overall — and a blocking gate
    with a high false-positive rate teaches people to override it, after which
    the true positives are overridden too. The sparse-arm problem is real but is
    a different check (sparse-data bias in the exposure coefficient), and it
    lives in precheck_configs, not here.
    """
    for key in ("n_events", "events", "event_count", "total_events"):
        val = outcome.get(key)
        if isinstance(val, (int, float)) and val > 0:
            return int(val)
    return None


def _plan_pipeline_changes(plan):
    """Work out the effective pipeline; return a list of (kind, id, why) changes.

    Two directions, both from review section C:
      - pipeline_profile parks (explore) or restores (submit) the
        submission-only steps. BOTH directions, because a one-way park is worse
        than no profile at all: an explore run left `manuscript` and
        `reviewer_challenge` marked skipped, switching back to submit did not
        clear them, and the paper was then written with no challenge behind it —
        the exact hole `_validate_manuscript_is_gated` exists to close.
      - a functional-form DIAGNOSTIC is added for every outcome that fits a
        multivariable model over at least one continuous covariate, because
        "linear unless somebody remembered to ask" is the default that killed a
        primary result 60 days late. It is a diagnostic only: it does NOT
        replace the linear term in the main model, which stays a pre-specified
        decision for decision_log.md. This runs in BOTH profiles — exploration
        is when you most want to know the shape is not linear.
      - a STROBE checklist is added when a manuscript is being written, since it
        is a pure script whose cost is seconds.
    """
    pipeline = plan.get("pipeline") or []
    by_skill = {}
    for s in pipeline:
        by_skill.setdefault(s.get("skill"), []).append(s)
    changes = []
    profile = _pipeline_profile(plan)

    for s in pipeline:
        if s.get("skill") not in _SUBMIT_ONLY_SKILLS:
            continue
        if profile == "explore":
            if s.get("status") != "skipped":
                s["status"] = "skipped"
                # The marker is what makes the park reversible without guessing.
                # A step the researcher skipped by hand carries no skip_reason
                # and is left alone in both directions.
                s["skip_reason"] = "profile"
                changes.append(("park", s["id"],
                                f"pipeline_profile='explore' — {s['skill']} is a "
                                f"submission step; set the profile to 'submit' to "
                                f"restore it"))
        elif s.get("status") == "skipped" and s.get("skip_reason") == "profile":
            s["status"] = "pending"
            s.pop("skip_reason", None)
            changes.append(("unpark", s["id"],
                            f"pipeline_profile='submit' — {s['skill']} was parked by an "
                            f"earlier explore run and is restored, so the submission "
                            f"gates apply again"))

    existing_ids = {s.get("id") for s in pipeline}
    continuous = [c for c in (plan.get("covariates") or [])
                  if c.get("type") == "continuous"]
    spline_cols = [c.get("column") for c in continuous]
    knots = _adv(plan, "nonlinearity").get("knots", 4)
    already_rcs = {s.get("outcome") for s in by_skill.get("nonlinearity", [])}
    for s in list(by_skill.get("multivariate-interaction", [])):
        oid = s.get("outcome")
        if not continuous or oid in already_rcs or f"rcs_{oid}" in existing_ids:
            continue
        outcome = get_outcome(plan, oid)
        events = _declared_events(outcome)
        try:
            n_params, unpriced, _prov = _prospective_param_budget(
                plan, oid, spline_cols, knots)
        except Exception as exc:
            # Fail closed. The alternative is a local re-implementation of the
            # denominator, and a second copy of that definition is what put a
            # back door in the overfitting guard in the first place.
            _method_warn(
                "rcs_diagnostic_skipped_no_parameter_budget",
                f"outcome '{oid}': the non-linearity diagnostic was NOT added because the "
                f"parameter budget could not be computed ({exc}). "
                f"precheck_configs.parameter_budget() is the single definition of the EPV "
                f"denominator and this file will not approximate it. Fix that import and "
                f"re-run, or add the rcs_{oid} step by hand once you have checked the "
                f"events per parameter yourself.")
            continue
        # `n_params` is a lower bound while anything is unpriced, so the
        # events-per-parameter figure below it is an UPPER bound. Clearing a
        # floor on an upper bound proves nothing, which is why an unpriced term
        # withholds the diagnostic unless something bounds it from above.
        worst_case = _worst_case_params(n_params, unpriced)
        if unpriced and worst_case is None:
            listed = "; ".join(_describe_unpriced(u) for u in unpriced)
            ratio = (f"the {events / n_params:.1f} events per parameter it implies is an "
                     f"UPPER bound" if events else
                     "the plan states no event count either, so neither side of the ratio "
                     "is known")
            _method_warn(
                "rcs_diagnostic_skipped_unpriced_terms",
                f"outcome '{oid}': the non-linearity diagnostic was NOT added. "
                f"precheck_configs.parameter_budget() reported {len(unpriced)} unpriced "
                f"term(s) — {listed} — so its total of {n_params} is a LOWER bound and "
                f"{ratio}. Clearing a floor on an upper bound proves nothing, and nothing "
                f"here re-prices those terms: the budget is parameter_budget's to state. "
                f"Declare label_map (or levels) for them, or let precheck_configs count "
                f"them from the data, and the diagnostic is added on the next run.")
            continue
        budget = worst_case if worst_case is not None else n_params
        if events is not None and events < 10 * budget:
            _method_warn(
                "rcs_diagnostic_skipped_low_epv",
                f"outcome '{oid}': the non-linearity diagnostic was NOT added. With "
                f"{events} events (total, across the fitted analysis set) and {budget} "
                f"fitted parameters once every continuous covariate is splined, that is "
                f"{events / budget:.1f} events per parameter, below the floor of 10 "
                f"(references/advanced_analyses.md section 3). A spline fitted there "
                f"overfits confidently. Report the linear form and say in the limitations "
                f"that non-linearity could not be assessed — or spline a single "
                f"pre-specified variable, which is a much smaller parameter budget.")
            continue
        if unpriced:
            _method_warn(
                "rcs_diagnostic_unpriced_but_bounded",
                f"outcome '{oid}': {len(unpriced)} term(s) came back unpriced from "
                f"parameter_budget, but each declares a ceiling, so the worst case "
                f"({budget} parameters rather than the lower bound of {n_params}) still "
                f"clears the floor and the diagnostic was added. Declaring label_map (or "
                f"levels) removes the range.")
        if events is None:
            _method_warn(
                "rcs_diagnostic_epv_unverified",
                f"outcome '{oid}': the non-linearity diagnostic was added without an "
                f"events-per-parameter check, because the plan does not state an event "
                f"count for this outcome (set outcomes.*.n_events to the TOTAL events in "
                f"the fitted analysis set, or let precheck_configs.py compute it from the "
                f"data). If events / {budget} parameters falls below 10, read the RCS "
                f"curve as exploratory only.")
        pipeline.append({
            "id": f"rcs_{oid}", "skill": "nonlinearity", "outcome": oid,
            "status": "pending", "depends_on": [s["id"]],
            "output_file": f"RCS_{oid}",
        })
        changes.append(("add", f"rcs_{oid}",
                        "functional-form diagnostic for the continuous covariates "
                        "(p-nonlinear + curve + data density). It does NOT change the "
                        "main model; swapping the linear term for a spline stays a "
                        "pre-specified decision"))

    # A pre-declared PH remedy schedules the analysis that performs it.
    #
    # This is what closes the loop the artifact gate was left holding. The plan
    # declares the remedy BEFORE the Schoenfeld test runs — that is the whole
    # point of pre-specification — but until these steps existed, "declared" and
    # "performed" were separated by the user remembering to hand-build one, and
    # the gate could only ask whether some file was there. Adding the step here
    # means the declaration is the thing that runs.
    #
    # Added unconditionally, not "if PH is violated": at config-generation time
    # nobody knows yet. A step that finds no violation writes an evidence sidecar
    # with status `not_applicable` and exits 0 — the third state, kept distinct
    # from "could not compute" on purpose.
    for s in list(pipeline):
        if s.get("skill") != "multivariate-interaction" or s.get("status") == "skipped":
            continue
        oid = s.get("outcome")
        if not oid:
            continue
        try:
            oc = get_outcome(plan, oid)
        except ValueError:                     # a malformed plan is validated elsewhere
            continue
        spec = _REMEDY_STEPS.get(oc.get("ph_violation_remedy"))
        if spec is None:                       # `disclose`, or nothing declared
            continue
        # Someone may already have hand-built one — the route that was the only
        # option before these generators existed. Two steps computing the same
        # remedy would hand the gate two answers about one violation.
        if any(o.get("skill") == spec["skill"]
               or (any(h in str(o.get("id", "")).lower() for h in spec["hints"])
                   and o.get("outcome") in (oid, None))
               for o in pipeline):
            continue
        new_id = spec["id"].format(oid=oid)
        if new_id in existing_ids:
            continue
        pipeline.append({
            "id": new_id, "skill": spec["skill"], "outcome": oid,
            "status": "pending", "depends_on": [s["id"]],
            "output_file": spec["stem"].format(oid=oid),
        })
        existing_ids.add(new_id)
        changes.append(("add", new_id,
                        f"outcome '{oid}' pre-declared ph_violation_remedy="
                        f"'{oc['ph_violation_remedy']}'; this step performs it — "
                        f"{spec['why']}, leaving {s['id']}'s workbook unremediated and "
                        f"internally consistent. If the assumption turns out not to be "
                        f"violated the step records `not_applicable` and changes "
                        f"nothing"))

    # STROBE is a submission artefact, so it is added only when a manuscript is
    # actually going to be written — which in `explore` is never, since the
    # manuscript step is parked above.
    has_manuscript = any(s.get("status") != "skipped"
                         for s in by_skill.get("manuscript-results", []))
    if has_manuscript and not by_skill.get("strobe") and "strobe" not in existing_ids:
        pipeline.append({"id": "strobe", "skill": "strobe", "status": "pending",
                         "depends_on": [], "output_file": "STROBE_checklist"})
        changes.append(("add", "strobe",
                        "reporting checklist required before submission; a pure script "
                        "with no data cost, previously off by default"))
    return changes


def _plan_fingerprint(plan):
    """reviewer_challenge.plan_fingerprint() for this plan, or None.

    Imported from the sibling script rather than reimplemented: a second copy of
    the hash would drift, and a drifted fingerprint reported to the user is
    worse than none.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "reviewer_challenge.py")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_rc_fingerprint", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        material = {k: v for k, v in plan.items() if not k.startswith("_")}
        return mod.plan_fingerprint(material)
    except Exception as exc:                      # surfaced, never swallowed
        print(f"  [WARN] could not compute the reviewer-challenge fingerprint "
              f"({path}): {exc}. Check by hand whether the challenge is still valid.",
              file=sys.stderr)
        return None


def _challenge_domain_count(plan):
    """How many domains the existing challenge covered, for the cost warning."""
    out = plan.get("output_dir") or ""
    agg = os.path.join(out, f"reviewer_challenge_v{plan.get('version', 1)}.json")
    if os.path.exists(agg):
        try:
            with open(agg, "r", encoding="utf-8") as f:
                data = json.load(f)
            reports = data.get("domains") or data.get("reports") or []
            if reports:
                return len(reports)
        except Exception as exc:
            print(f"  [WARN] could not read {agg}: {exc}", file=sys.stderr)
    return 10


def _warn_fingerprint_change(plan, before, after):
    """Say — before the user pays for it — that a challenge has been invalidated."""
    if not before or not after or before == after:
        return
    n = _challenge_domain_count(plan)
    print(f"\n  ⚠ REVIEWER CHALLENGE INVALIDATED: plan fingerprint {before} → {after}")
    print("    reviewer_challenge.py gates the manuscript on this hash, so the existing")
    print(f"    challenge no longer counts as covering this plan: {n} domain(s) have to be")
    print("    re-run before the manuscript step will pass. That is the expensive part of")
    print("    this change — the analyses themselves are unaffected.", file=sys.stdout)


class PlanChangedOnDisk(Exception):
    """The file moved under us between reading it and writing it back."""


def _disk_hash(path):
    """sha256 of the file's bytes — the compare half of compare-and-swap."""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _write_plan_body(plan, plan_path, expected_hash):
    """Backup + compare-and-swap + atomic replace. THE LOCK MUST BE HELD.

    Split out from _backup_and_write_plan because flock is per open file
    description, not per process: a caller that already held the lock and then
    called a helper that opened the lock file again waited forever for itself.
    """
    if expected_hash is not None and _disk_hash(plan_path) != expected_hash:
        raise PlanChangedOnDisk(plan_path)
    stamp = datetime.now().strftime("%Y-%m-%d")
    backup = f"{plan_path}.bak-{stamp}"
    if os.path.exists(backup):
        backup = f"{plan_path}.bak-{datetime.now().strftime('%Y-%m-%dT%H%M%S')}"
    with open(plan_path, "r", encoding="utf-8") as f:
        original = f.read()
    with open(backup, "w", encoding="utf-8") as f:
        f.write(original)
    tmp_path = plan_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in plan.items() if not k.startswith("_")},
                  f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, plan_path)
    return backup


def _backup_and_write_plan(plan, plan_path, expected_hash=None):
    """Copy the plan aside, then write it back. Returns the backup path.

    `_`-prefixed keys are this run's scratch space (`_plan_path`,
    `_pipeline_changes`, `_multiplicity_summary`) and are never written.

    Uses the same flock + atomic-replace protocol as run_pipeline.save_plan(),
    plus a compare-and-swap: `expected_hash` is what the file hashed to when
    this process read it, re-checked INSIDE the lock. Without that check the
    lock only guaranteed the write was not torn — the runner could still record
    a step status (or a researcher could edit a covariate) between our read and
    our write, and writing our older snapshot back would silently revert it. The
    backup would then hold the NEWER content, so the loss would be invisible in
    the live file and recoverable only by someone who thought to diff the backup.

    Acquires the lock itself, so it must NOT be called with the lock already
    held — see _write_plan_body, which is the entry point for callers that do.
    """
    with open(plan_path + ".lock", "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            return _write_plan_body(plan, plan_path, expected_hash)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _persist_plan(plan, plan_path, changes, before_fp, expected_hash=None):
    """Write back a pipeline the generator restructured, with an itemised report.

    Nothing here is silent: the backup path, every parked or added step, and the
    fingerprint consequence are all printed. The write is what makes the change
    real — run_pipeline.py reads research_plan.json, not this manifest, so an
    auto-added diagnostic that lived only in the configs directory would never
    be executed and a parked step would run with no config to run from.
    """
    if not changes:
        return
    try:
        backup = _backup_and_write_plan(plan, plan_path, expected_hash)
    except PlanChangedOnDisk:
        detail = "\n".join(f"          {kind:<6s} {name}: {why}"
                           for kind, name, why in changes)
        _abort(
            f"{plan_path} changed on disk while the configs were being generated.\n"
            f"        The pipeline changes below were NOT written, because writing them "
            f"would have\n"
            f"        reverted whatever the other writer (run_pipeline recording a "
            f"status, or a person\n"
            f"        editing the plan) just saved:\n{detail}\n"
            f"        Re-run generate_configs.py once the other writer has finished.",
            code=2)
    print(f"\n  [PLAN UPDATED] {plan_path}")
    print(f"    backup: {backup}")
    for kind, name, why in changes:
        print(f"    {kind:<6s} {name}: {why}")
    _warn_fingerprint_change(plan, before_fp, _plan_fingerprint(plan))


def migrate_plan(plan_path):
    """Bring a pre-2026-08-11 plan up to PLAN_SCHEMA_VERSION without changing
    what any analysis does.

    Where each field is written matters as much as its value, because
    reviewer_challenge.plan_fingerprint() gates the manuscript on a hash of the
    plan. Its contract as of 2026-08-11:
      - the nine analysis blocks + the pipeline shape are hashed;
      - FINGERPRINT_FIELDS_OPTIONAL ("estimand", "pipeline_profile") are hashed
        *when present*, so writing one where the default already applied would
        invalidate a challenge over a no-op;
      - FINGERPRINT_EXCLUDE_KEYS ("selection_rationale", "model_purpose",
        "analysis_intent") are scrubbed at any depth, so those are always safe.
    So: this function writes only fields that cannot change the hash, and for
    the two that can it writes NOTHING when the value would equal the default —
    absent and "the default" are the same state, and one of these migrations
    must not cost ten fresh-context agents and three hours.

    The read and the write are both inside the file lock. They used to be
    separated by the whole transform, so anything the runner or a researcher
    wrote in between was overwritten by the snapshot this function had loaded
    minutes earlier — and since the backup captured the NEWER file, the live plan
    silently went backwards while the evidence of it sat in a .bak nobody reads.
    """
    with open(plan_path + ".lock", "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            return _migrate_locked(plan_path)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _migrate_locked(plan_path):
    """migrate_plan's body, executed while holding the plan's lock."""
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    before = _plan_fingerprint(plan)
    added = []
    notes = []

    on_disk = plan.get("plan_schema_version")
    if isinstance(on_disk, int) and on_disk > PLAN_SCHEMA_VERSION:
        _abort(
            f"{plan_path} declares plan_schema_version {on_disk}, but this "
            f"generator only\n"
            f"        understands {PLAN_SCHEMA_VERSION}. Migrating would DOWNGRADE the "
            f"field and hide whatever\n"
            f"        a newer version added, so it refuses. Update the research-plan "
            f"skill instead."
        )
    if not isinstance(on_disk, int) or on_disk < PLAN_SCHEMA_VERSION:
        plan["plan_schema_version"] = PLAN_SCHEMA_VERSION
        added.append(("plan_schema_version", PLAN_SCHEMA_VERSION,
                      "marks the plan as readable by this generator; also switches on "
                      "the automatic diagnostic steps described below"))
    if _schema_field(plan, "pipeline_profile") is None:
        notes.append(
            "pipeline_profile — NOT written. Absent already means 'submit', and the key "
            "is hashed into the reviewer-challenge fingerprint, so writing the default "
            "would invalidate a completed challenge for no behavioural change. Add "
            "\"pipeline_profile\": \"explore\" by hand when you want the manuscript / "
            "reviewer-challenge / STROBE steps parked — that IS a real change and should "
            "invalidate.")
    if _model_purpose(plan) is None:
        has_calibration = any(s.get("skill") == "calibration"
                              for s in (plan.get("pipeline") or []))
        notes.append(
            "model_purpose — NOT written. Defaulting an undeclared study to 'etiologic' "
            "would have broken exactly the plans that need the field most: an existing "
            "prognostic-model study whose calibration step predates the field would "
            "start failing on the next run, and a mixed study (etiologic primary, one "
            "prognostic sub-model) cannot be described by a single study-level value at "
            "all. Declare it where the model is: on the calibration STEP "
            "(\"model_purpose\": \"prediction\") for one prognostic sub-model, or on "
            "study.model_purpose if the whole paper is a prediction study."
            + (f" This plan HAS {sum(1 for s in plan.get('pipeline') or [] if s.get('skill') == 'calibration')} "
               f"calibration step(s), which will refuse to run until one of those says "
               f"'prediction'." if has_calibration else ""))
    if _estimand_type(plan) is None:
        notes.append(
            "estimand_type — NOT written. 'unspecified' is what absence already means "
            "(no E-value step is ever added automatically), and any plan-level estimand "
            "key is hashed. Set \"estimand_type\": \"causal\" by hand if the paper makes "
            "a causal claim; that changes what a reviewer should look for, so the "
            "resulting invalidation is the correct one.")
    covs = plan.get("covariates") or []
    if covs and not plan.get("covariate_provenance"):
        undocumented = [c.get("column") for c in covs
                        if not _covariate_rationale(plan, c)]
        if undocumented:
            plan["covariate_provenance"] = {c: None for c in undocumented}
            added.append(("covariate_provenance", f"{len(undocumented)} empty entries",
                          "why each covariate is in the adjustment set — reviewer "
                          "challenge domain 3's first question. Left null on purpose: "
                          "this is not something a migration can invent. Kept out of "
                          "covariates[] so filling it in does not invalidate a challenge"))
    outcomes_block = plan.get("outcomes")
    if not isinstance(outcomes_block, dict):
        # A design-stage plan can carry `outcomes` as a bare list (or nothing).
        # It is not a pipeline plan yet, so there is no primary/secondary split
        # to record — say so instead of raising an AttributeError over it.
        notes.append(
            f"multiplicity — NOT written. outcomes is "
            f"{type(outcomes_block).__name__}, not the "
            f"{{\"primary\": …, \"secondary\": […]}} object a pipeline plan uses, so this "
            f"plan has no primary/secondary split to label yet. Re-run --migrate once "
            f"Step 3 has turned it into a pipeline plan.")
    elif plan.get("multiplicity") is None:
        secondary = [o.get("id") for o in outcomes_block.get("secondary", [])]
        notes.append(
            "multiplicity — NOT written. Two reasons. Filling it in from position in "
            "the file ('anything under outcomes.secondary is exploratory') is a "
            "convention, not a fact: a pre-specified co-primary endpoint often sits in "
            "that list, and labelling it exploratory would demote it silently while the "
            "reviewer challenge still read as valid. And writing the placeholder "
            "'unknown' is not free either — reviewer_challenge hashes analysis_intent as "
            "a structured decision, so the placeholder would invalidate a completed "
            "challenge while adding no information. Set analysis_intent to "
            "'confirmatory' or 'exploratory' per outcome yourself"
            + (f" (undeclared: {', '.join(str(s) for s in secondary)})" if secondary
               else "")
            + "; every run records an analysis_intent_unconfirmed warning until you do.")

    if not added:
        print(f"  Nothing to migrate: {plan_path} already carries every schema-v"
              f"{PLAN_SCHEMA_VERSION} field.")
        for note in notes:
            print(f"    · {note}")
        return

    # The lock is already held by migrate_plan (read -> transform -> write is
    # one critical section), so this writes directly rather than re-acquiring it.
    backup = _write_plan_body(plan, plan_path, expected_hash=None)
    payload = {k: v for k, v in plan.items() if not k.startswith("_")}

    print(f"\n  [MIGRATED] {plan_path}  →  plan_schema_version {PLAN_SCHEMA_VERSION}")
    print(f"    backup: {backup}")
    for field, value, why in added:
        print(f"    + {field} = {value!r}")
        print(f"        {why}")
    for note in notes:
        print(f"    · {note}")

    after = _plan_fingerprint(plan)
    if before and after and before == after:
        print(f"\n    reviewer-challenge fingerprint unchanged ({after}) — nothing above "
              f"is hashed by\n    reviewer_challenge.plan_fingerprint(). An existing "
              f"challenge stays valid; no domain\n    needs re-running for this "
              f"migration.")
    else:
        _warn_fingerprint_change(plan, before, after)

    # The next ordinary run is what restructures the pipeline, and that DOES
    # change the fingerprint. Say so now, while there is still a choice.
    pending, projected = _project_pipeline_changes(payload)
    if pending:
        print(f"\n    The NEXT `generate_configs.py {os.path.basename(plan_path)}` run "
              f"will also change the pipeline:")
        for kind, name, why in pending:
            print(f"      {kind:<6s} {name}: {why}")
        _warn_fingerprint_change(projected, after, _plan_fingerprint(projected))
        print("    To decline, set \"auto_steps_enabled\": false at the top level of the "
              "plan.")


def merge_method_warnings(config_dir, regenerated_ids):
    """Carry forward the previous run's warnings that this run did not revisit.

    write_manifest used to store only the warnings raised by the CURRENT call,
    while the `configs` list was merged with the old manifest. After a selective
    `--only` re-run the manifest therefore described every step but carried the
    methodological warnings of only the handful just regenerated — and the
    reviewer-challenge agent, whose brief is to read manifest.json, saw the rest
    as never having existed. Warnings attributed to a step this run regenerated
    are dropped (they have just been re-raised, or fixed); plan-level warnings
    (step_id=None) are re-raised on every call by validate_plan, so they are
    dropped too.
    """
    manifest_path = os.path.join(config_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return list(METHOD_WARNINGS)
    with open(manifest_path, "r", encoding="utf-8") as f:
        previous = json.load(f).get("methodological_warnings", [])
    def keep(w):
        if "step_id" not in w:
            # Written by a build before warnings carried attribution. It cannot
            # be matched to a step, and dropping it would lose the very
            # information this function exists to preserve, so keep it and let
            # the de-duplication below handle the overlap.
            return True
        return bool(w["step_id"]) and w["step_id"] not in regenerated_ids

    fresh = {(w.get("kind"), w.get("message")) for w in METHOD_WARNINGS}
    carried = [w for w in previous
               if keep(w) and (w.get("kind"), w.get("message")) not in fresh]
    return carried + list(METHOD_WARNINGS)


def generate_all(plan_path, only=None):
    with open(plan_path, "r", encoding="utf-8") as f:
        plan = json.load(f)
    # What the file looked like when we read it. _persist_plan compares this
    # inside the lock before writing, so a status the runner recorded while the
    # configs were being generated is never reverted by our older snapshot.
    disk_hash_at_load = _disk_hash(plan_path)

    # Steps that read the plan back (strobe, the reviewer-challenge gate) used to
    # assume it lives at <output_dir>/research_plan.json. It usually does, but
    # nothing enforces it, and when it does not those steps fail with a
    # file-not-found rather than doing their job. Record where it actually came
    # from and let the generators prefer that.
    plan["_plan_path"] = os.path.abspath(plan_path)
    # Selective regeneration must not restructure the pipeline; see
    # _apply_pipeline_resolution.
    plan["_only_mode"] = only is not None
    fingerprint_before = _plan_fingerprint(plan)

    validate_plan(plan, plan_path)
    output_dir = plan["output_dir"]
    configs_dir = os.path.join(output_dir, "configs")
    logs_dir = os.path.join(output_dir, "logs")
    os.makedirs(configs_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)

    # Validate --only step IDs if provided
    all_step_ids = {step["id"] for step in plan["pipeline"]}
    if only is not None:
        invalid = [sid for sid in only if sid not in all_step_ids]
        if invalid:
            print(f"  ERROR: Unknown step IDs: {', '.join(invalid)}")
            print(f"  Available step IDs: {', '.join(sorted(all_step_ids))}")
            sys.exit(1)

    generated = []
    generated_configs = []
    generator_failures = 0  # TP-2 audit fix (rp-B-01): track for non-zero exit
    global _CURRENT_STEP_ID
    for step in plan["pipeline"]:
        skill = step["skill"]
        step_id = step["id"]

        # Skip steps not in --only list (when filtering)
        if only is not None and step_id not in only:
            continue

        # A step parked by pipeline_profile="explore" gets no config on purpose:
        # run_pipeline.should_run() does not run a "skipped" step, so generating
        # one would only leave a file claiming an analysis is configured to run.
        if step.get("status") == "skipped":
            print(f"  parked ({_pipeline_profile(plan)}): {step_id} — no config generated")
            continue

        generator = GENERATORS.get(skill)
        if generator is None:
            print(f"  WARNING: No config generator for skill '{skill}', skipping {step_id}")
            generator_failures += 1
            continue
        try:
            _CURRENT_STEP_ID = step_id
            config = generator(plan, step)
        except Exception as e:
            # TP-2 audit fix (2026-05-08, rp-B-01): config gen exception
            # previously caught + printed + continued; script exited 0 with
            # missing configs → run_pipeline.py crashed later in pipeline.
            # Now: track failure count + sys.exit(2) at end if any.
            print(f"  [QC_BLOCKING] ERROR generating config for {step_id}: {e}",
                  file=sys.stderr)
            generator_failures += 1
            continue
        finally:
            _CURRENT_STEP_ID = None

        config_path = os.path.join(configs_dir, f"{step_id}_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        now_iso = datetime.now().isoformat()
        generated.append((step_id, skill, config_path))
        generated_configs.append({
            "step_id": step_id,
            "skill": skill,
            "config_path": config_path,
            "generated_at": now_iso,
        })

    regenerated_ids = {entry["step_id"] for entry in generated_configs}
    warnings = list(METHOD_WARNINGS)
    # When --only is used, merge with existing manifest entries (replacing updated ones)
    if only is not None:
        existing = load_existing_manifest(configs_dir)
        # Keep existing entries that were not regenerated
        merged = [e for e in existing if e["step_id"] not in regenerated_ids]
        merged.extend(generated_configs)
        generated_configs = merged
        # …and do the same for the warnings, which used to be overwritten with
        # only this call's, silently emptying the manifest of everything the
        # untouched steps had reported (flow review gap #15).
        warnings = merge_method_warnings(configs_dir, regenerated_ids)

    # Write manifest
    write_manifest(configs_dir, generated_configs, plan, warnings)

    # Persist the restructured pipeline. Deliberately after generation: a plan
    # is only rewritten once the configs it describes exist.
    _persist_plan(plan, plan_path, plan.get("_pipeline_changes"), fingerprint_before,
                  expected_hash=disk_hash_at_load)

    # Print summary
    print(f"\nGenerated {len(generated)} configs in {configs_dir}/:")
    for step_id, skill, path in generated:
        filename = os.path.basename(path)
        print(f"  {filename:<40s} → {skill}")

    # TP-2 audit fix (rp-B-01): surface generator failure count and exit
    # non-zero so downstream pipeline doesn't see "success" with missing configs.
    if generator_failures > 0:
        _abort(f"{generator_failures} config generator failure(s) — pipeline cannot "
               f"proceed with incomplete configs (each is reported above with a "
               f"[QC_BLOCKING] line naming its step)", code=2)

    print()
    return generated


def main():
    parser = argparse.ArgumentParser(
        description="Generate sub-skill JSON configs from a research_plan.json."
    )
    parser.add_argument("plan", help="Path to research_plan.json")
    parser.add_argument(
        "--only",
        help="Comma-separated list of step IDs to regenerate (e.g., --only table1,uni_primary)",
    )
    parser.add_argument(
        "--migrate", action="store_true",
        help=(f"Add the plan_schema_version-{PLAN_SCHEMA_VERSION} fields a plan written "
              f"before 2026-08-11 lacks, using conservative defaults that change no "
              f"analysis. Backs the plan up first and prints every field it adds, why, "
              f"and whether the reviewer-challenge fingerprint changes."),
    )
    args = parser.parse_args()

    if not os.path.exists(args.plan):
        print(f"Error: File not found: {args.plan}")
        sys.exit(1)

    if args.migrate:
        if args.only:
            sys.exit("--migrate rewrites the plan and --only regenerates configs; "
                     "run them separately.")
        migrate_plan(args.plan)
        return

    only = None
    if args.only:
        only = [s.strip() for s in args.only.split(",") if s.strip()]

    generate_all(args.plan, only=only)


if __name__ == "__main__":
    main()
