#!/usr/bin/env python3
"""Aggregate reviewer-challenge domain reports into one gated verdict.

Rubric and agent instructions: references/reviewer_challenge.md

Usage
  # 1. list the domains to farm out (one fresh-context agent each)
  python3 reviewer_challenge.py domains

  # 2. aggregate the per-domain JSON reports the agents produced
  python3 reviewer_challenge.py aggregate \
      --plan <OUTPUT_DIR>/research_plan.json \
      --reports <r1.json> <r2.json> ... \
      --out <OUTPUT_DIR>/reviewer_challenge_v1.json

  # 3. gate: the pipeline step form. Reads a step config like every other
  #    script in the pipeline, so run_pipeline.py can block the manuscript on it.
  python3 reviewer_challenge.py <step_config.json> [--check-missing]

  # 4. why did the fingerprint move? (the gate blocks on it; this says what changed)
  python3 reviewer_challenge.py explain-fingerprint --plan <plan.json> [--against <other.json>]

  # 5. explore -> submit promotion gate
  python3 reviewer_challenge.py promotion-diff --explore <explore_plan.json> \
      --submit <submit_plan.json> --decision-id <ID> --decision-log <decision_log.md> \
      --after-seeing-outcomes yes|no

Exit codes
  0  no fatal comment — manuscript step may proceed
  1  at least one fatal comment, or a domain is missing / malformed (aggregate)
  2  could not run (bad arguments, unreadable plan)
  3  gate blocked (the pipeline's blocking convention)

The coverage check is the point of this script as much as the verdict is. A
challenge that ran three of ten domains and found nothing is not a pass, and
without an explicit check that is exactly what it looks like.

Why a gate step exists at all: until 2026-08-11 nothing stopped the manuscript
step from running with no challenge on disk. The rule was written down and the
runner could not enforce it, so "the challenge was skipped" and "the challenge
passed" looked identical from the outside — the same shape of failure the
coverage check inside `aggregate` was built to prevent.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

# Keep in sync with the rubric table in references/reviewer_challenge.md.
DOMAINS = [
    ("estimand_target_trial", "Estimand 與 target trial 對位"),
    ("selection_immortal_time", "Selection bias / immortal time"),
    ("confounding", "Confounding（含 mediator / collider / E-value）"),
    ("missing_data", "缺失資料與其假設"),
    ("model_specification", "模型設定（EPV / 線性 / PH / 交互作用）"),
    ("competing_risk_estimand", "Competing risk 的 estimand"),
    ("propensity_score", "Propensity score（positivity / balance）"),
    ("multiplicity_selective_reporting", "多重比較與選擇性呈現"),
    ("sensitivity_robustness", "Sensitivity / robustness"),
    ("reporting_strobe", "報告完整性（STROBE）"),
]
DOMAIN_KEYS = [d[0] for d in DOMAINS]
DOMAIN_LABEL = dict(DOMAINS)

VERDICTS = ("pass", "concern", "fatal")
SEVERITIES = ("major", "minor")
STATUSES = ("open", "fixed", "wontfix")


def _fail(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def load_report(path):
    """Read one domain report, returning (report, list_of_problems)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            rep = json.load(f)
    except Exception as exc:
        return None, [f"{os.path.basename(path)}: unreadable ({exc})"]
    return rep, validate_report(rep, os.path.basename(path))


def validate_report(rep, label):
    """Schema and self-consistency checks for one domain report.

    Split out from load_report so the gate can re-run it against the reports
    embedded in an aggregate. Trusting the aggregate's stored `schema_problems`
    would mean a hand-edited file could declare itself clean — the reports are
    the evidence, the summary is only a convenience.
    """
    problems = []
    domain = rep.get("domain")
    if domain not in DOMAIN_KEYS:
        problems.append(
            f"{label}: domain {domain!r} is not one of the ten rubric domains"
        )
    if rep.get("verdict") not in VERDICTS:
        problems.append(
            f"{domain}: verdict {rep.get('verdict')!r} must be one of {VERDICTS}"
        )

    for i, c in enumerate(rep.get("comments", [])):
        where = f"{domain}[{c.get('id', i)}]"
        if c.get("verdict") not in VERDICTS:
            problems.append(f"{where}: comment verdict {c.get('verdict')!r} invalid")
        if c.get("severity") not in SEVERITIES:
            problems.append(f"{where}: severity {c.get('severity')!r} invalid")
        if not str(c.get("comment", "")).strip():
            problems.append(f"{where}: empty comment text")
        if not str(c.get("remedy", "")).strip():
            problems.append(f"{where}: no remedy — an objection with no proposed "
                            f"action is not actionable")
        c.setdefault("status", "open")
        if c["status"] not in STATUSES:
            problems.append(f"{where}: status {c['status']!r} invalid")
        # Closing a fatal as `wontfix` is the only way past the gate, so it has to
        # cost something. Without this, "wontfix" is a free pass typed into a JSON
        # file; the decision_log id is what makes the override answerable in a
        # rebuttal letter (delivery_discipline.md rule 2).
        if c.get("verdict") == "fatal" and c.get("status") == "wontfix" \
                and not str(c.get("decision_log_id", "")).strip():
            problems.append(
                f"{where}: a fatal closed as 'wontfix' needs a 'decision_log_id' "
                f"pointing at the decision_log.md row that carries the reason. "
                f"An override with no permanent ID is indistinguishable from "
                f"deleting the finding")
        # Evidence is what separates a finding from an impression. A fatal with
        # no evidence pointer is demoted rather than dropped, so the reviewer's
        # instinct survives but cannot silently block the pipeline.
        #
        # The demotion must also be a schema problem, which is what makes it not
        # silent. Until 2026-08-11 it was only recorded in the JSON, so omitting
        # `evidence` was an undocumented third way past the gate — the docs say a
        # fatal has exactly two exits (fix it, or wontfix with a decision-log id),
        # and a reviewer agent that simply forgot the field quietly opened a
        # third. Blocking here forces the choice to be made deliberately: supply
        # the pointer, or downgrade the comment on purpose.
        if not str(c.get("evidence", "")).strip():
            c["evidence"] = "[unverified]"
            if c.get("verdict") == "fatal":
                c["verdict"] = "concern"
                c["demoted_from_fatal"] = "no evidence pointer supplied"
                problems.append(
                    f"{where}: a fatal with no 'evidence' pointer. It has been demoted "
                    f"to concern and cannot block on its own — supply the pointer "
                    f"(file:sheet:cell or log:line) if the objection is real, or set "
                    f"the verdict to concern deliberately")

    # A domain claiming `pass` must still say what it looked at.
    if rep.get("verdict") == "pass" and not str(rep.get("checked", "")).strip():
        problems.append(
            f"{domain}: verdict=pass but 'checked' is empty — a pass has to state "
            f"what was examined, otherwise it is indistinguishable from a skip"
        )

    # The gate counts comments, not domain verdicts. Without this check a report
    # that declares verdict="fatal" and lists no comments sails straight through
    # as a pass — the most dangerous possible direction for the failure to go.
    comments = rep.get("comments", [])
    open_fatal = [c for c in comments
                  if c.get("verdict") == "fatal" and c.get("status") == "open"]
    open_concern = [c for c in comments
                    if c.get("verdict") == "concern" and c.get("status") == "open"]
    if rep.get("verdict") == "fatal" and not open_fatal:
        problems.append(
            f"{domain}: verdict=fatal but no open fatal comment carries it. State the "
            f"objection as a comment with evidence, or set the domain verdict to match "
            f"what was actually found — an unsupported domain verdict is not a finding"
        )
    if rep.get("verdict") == "concern" and not (open_fatal or open_concern):
        problems.append(
            f"{domain}: verdict=concern but no open concern or fatal comment carries it"
        )
    if rep.get("verdict") == "pass" and (open_fatal or open_concern):
        problems.append(
            f"{domain}: verdict=pass while {len(open_fatal) + len(open_concern)} "
            f"comment(s) are still open — resolve them or raise the domain verdict"
        )
    return problems


# Deterministic producers of domain reports, and the schema each one stamps. A
# domain whose report comes from a script rather than an agent can be checked for
# provenance; the rest are LLM output and carry none.
#
# Domain 10 is the one that matters: strobe_signoff.py feeds `aggregate` directly,
# so a stale `verdict: pass` left on disk from an earlier round is merged in as
# this round's result unless something checks.
DOMAIN_REPORT_SCHEMAS = {
    "reporting_strobe": "strobe_domain_report/1",
}


def provenance_problems(rep, label, plan_fp):
    """Validate where a domain report came from. Returns (problems, warnings).

    Three things, in the order they can mislead you:

      schema            a report written by a different version of the producer is
                        a different shape; say so rather than parse it hopefully
      plan_fingerprint  a report for another plan — or another round of this one —
                        is not this round's result, however clean its verdict
      null fingerprint  the producer writes null plus a reason when it cannot
                        compute one. That is a signal to block on, not to pass on:
                        "could not be verified" is not "verified".

    A report with no provenance at all only warns. Every domain report on disk
    today predates these fields, and a check that turns every project red on
    upgrade is one people learn to route around — the same warn-then-block
    migration C4 / C6 / C7 use.
    """
    problems, warnings = [], []
    domain = rep.get("domain")
    schema = rep.get("schema")
    expected = DOMAIN_REPORT_SCHEMAS.get(domain)

    if schema:
        if expected and str(schema) != expected:
            same_family = str(schema).split("/")[0] == expected.split("/")[0]
            problems.append(
                f"{label}: report schema {schema!r}, but this consumer understands "
                + (f"{expected!r}. The producer changed version; regenerate the report "
                   f"with the current script or update the consumer — do not merge a "
                   f"shape nobody has checked."
                   if same_family else
                   f"{expected!r}. This file is not the kind of report domain "
                   f"{domain!r} expects."))
    elif expected:
        warnings.append(
            f"{label}: no `schema` field. Domain {domain!r} has a deterministic "
            f"producer ({expected}), so a report without provenance cannot be shown "
            f"to be this round's. Re-run biostats-guardian's strobe_signoff.py to "
            f"get one.")

    if "plan_fingerprint" in rep:
        got = rep.get("plan_fingerprint")
        if got is None:
            reason = rep.get("plan_fingerprint_error") or "no reason recorded"
            problems.append(
                f"{label}: plan_fingerprint is null ({reason}). The producer records "
                f"null when it could not establish which plan the report is about, so "
                f"this report cannot be attributed to this analysis. Unverifiable is "
                f"not clean.")
        elif plan_fp and str(got) != str(plan_fp):
            problems.append(
                f"{label}: generated against plan fingerprint {got}, but this plan is "
                f"{plan_fp}. It describes a different analysis — or an earlier round "
                f"of this one — and cannot stand in for a current review.")
    # No warning for a domain with no deterministic producer. Those reports are
    # written by fresh-context agents and never carry provenance, so flagging
    # nine of them on every single run would be noise — and a warning that always
    # fires is a warning nobody reads, which is how the one that matters gets
    # missed. Domain 10's absent provenance is reported above, where it means
    # something.
    return problems, warnings


FINGERPRINT_FIELDS = ("study", "population", "grouping", "outcomes", "covariates",
                      "derived_variables", "analyses", "missing_data",
                      "advanced_analyses")

# Fields added to the plan schema after the original nine. They are read only
# when the plan actually carries them, so introducing one does not change the
# fingerprint of every plan written before it existed — which is the whole point:
# a schema migration must not invalidate a challenge that already ran.
FINGERPRINT_FIELDS_OPTIONAL = ("estimand", "pipeline_profile", "estimand_type")

# Keys removed from the fingerprint material wherever they appear, at any depth.
#
# Only *free text* is excluded, and only because a structured twin of it is
# hashed instead: `selection_rationale` is prose a human writes for a human,
# while `covariates[].selection_basis` is the same decision as an enum, and that
# one is hashed.
#
# This list used to also hold `model_purpose` and `analysis_intent`, on the
# argument that their gating effect would show up in the hashed `pipeline` list.
# That argument was measured and is false: changing model_purpose from etiologic
# to prediction without adding a calibration step leaves the pipeline list
# byte-identical, and a covariate set justified "by DAG, pre-specified" versus
# "kept by univariable p<0.10 screen" is the difference between an adjusted
# estimate and post-selection inference — a different objection, from a different
# domain, behind an identical fingerprint. The exclusion contradicted the rule
# stated in plan_fingerprint() directly below it.
#
# The cost worry that motivated the scrub — a schema addition invalidating a
# ten-agent challenge — is handled by FINGERPRINT_FIELDS_OPTIONAL and by reading
# these fields only where they are actually declared. Adding a field and changing
# a field's value are different events; only the second should invalidate
# anything.
#
# Scrubbing is recursive because this lives nested; a top-level exclusion would
# silently miss `covariates[].selection_rationale`.
FINGERPRINT_EXCLUDE_KEYS = ("selection_rationale",)

# Structured decisions that change what a reviewer should look for. Hashed as
# normalized enum values, so "prediction" vs "predictive" is not a spurious
# invalidation, and only when actually declared.
SELECTION_BASIS_VALUES = ("dag_prespecified", "clinical_prior",
                          "univariable_screen", "data_driven_other")

# Which reviewer domains a decision field bears on. Deliberately over-inclusive:
# a domain listed unnecessarily costs one agent; a domain omitted means a stale
# report gets presented as a current one. `model_purpose` carries estimand as
# well as model specification for exactly that reason.
FIELD_DOMAIN_MAP = {
    "selection_basis": ("confounding",),
    "model_purpose": ("model_specification", "estimand_target_trial"),
    "analysis_intent": ("multiplicity_selective_reporting",),
    # estimand_type decides whether an E-value is a legitimate thing to report at
    # all (it quantifies unmeasured confounding of a causal claim), so it lands on
    # confounding as well as on the estimand itself.
    "estimand_type": ("estimand_target_trial", "confounding"),
}

# Where the decision enums are read from. Removed from the raw material once
# lifted into DECISIONS_KEY, so that changing one shows up as a decision change
# and not as a change to the covariate list or the outcome block.
DECISION_SOURCE_KEYS = ("model_purpose", "study_purpose", "analysis_intent",
                        "selection_basis", "estimand_type")

# analysis_intent values that carry no decision. 'unknown' is what
# generate_configs._outcome_intent returns for an unstated secondary, so writing
# it explicitly says exactly what saying nothing says. Treating it as absent is
# what lets `--migrate` write the placeholder into every outcome for free; the
# alternative charges a full re-challenge for a field that changed from "not
# stated" to "stated as not stated".
#
# It does not open an escape route: going from a declared `confirmatory` to
# `unknown` REMOVES a value that was in the decisions block, which moves the
# fingerprint exactly as any other downgrade would.
INTENT_NULL_VALUES = ("unknown", "unspecified", "")


def _normalizers():
    """generate_configs' enum normalizers — the single definition of each.

    Imported lazily and never mirrored locally: two copies of an enum table is
    how `time-to-event` and `time_to_event` come to mean different things in one
    repository. Failure raises rather than falling back, because a fingerprint
    computed with a different normalizer than everyone else's is worse than an
    error that says so.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from generate_configs import _estimand_type, _normalize_model_purpose
    except Exception as exc:
        raise RuntimeError(
            f"cannot load the enum normalizers from generate_configs.py ({exc}). The "
            f"fingerprint depends on them; refusing to compute one with a second, "
            f"possibly divergent, copy.") from exc
    return _normalize_model_purpose, _estimand_type


def _declared_estimand_type(plan):
    """'causal' | 'associational' | None, normalized.

    Whether the study claims a causal effect decides whether an E-value means
    anything, and it is the first thing a target-trial reviewer checks.
    generate_configs._estimand_type resolves study.estimand_type then the
    top-level alias, and deliberately refuses to infer the value from the legacy
    prose `estimand` dict — inferring it is the silent mis-routing that whole
    normalizer exists to prevent.
    """
    _, estimand_type = _normalizers()
    return estimand_type(plan)


def _declared_model_purpose(plan):
    """The model purpose the plan states, normalized, or None.

    Resolution order mirrors generate_configs._model_purpose (narrowest first)
    minus the defaults: unstated stays unstated, so a plan written before the
    field existed keeps its fingerprint.
    """
    norm, _ = _normalizers()
    for raw in (((plan.get("advanced_analyses") or {}).get("calibration") or {})
                .get("study_purpose"),
                (plan.get("study") or {}).get("model_purpose"),
                plan.get("model_purpose")):
        if raw is not None:
            value = norm(raw)
            if value:
                return value
    return None


def _declared_analysis_intents(plan):
    """{outcome_id: intent} for outcomes that state one. Defaults are not read.

    _outcome_intent() defaults a primary to 'confirmatory'; hashing that default
    would move the fingerprint of every plan ever written — the schema migration
    this design is careful not to charge anyone for.
    """
    out = {}
    outcomes = plan.get("outcomes") or {}
    per_outcome = (plan.get("multiplicity") or {}).get("outcomes") or {}
    candidates = ([outcomes["primary"]] if outcomes.get("primary") else []) \
        + list(outcomes.get("secondary") or [])
    for oc in candidates:
        if not isinstance(oc, dict):
            continue
        oid = str(oc.get("id"))
        raw = oc.get("analysis_intent") or (per_outcome.get(oid) or {}).get("analysis_intent")
        if raw and str(raw).strip().lower() not in INTENT_NULL_VALUES:
            out[oid] = str(raw).strip().lower()
    return out


def _declared_selection_basis(plan):
    """{covariate column: basis} for covariates that state one."""
    out = {}
    for cov in plan.get("covariates") or []:
        if isinstance(cov, dict) and cov.get("selection_basis"):
            out[str(cov.get("column") or cov.get("name"))] = \
                str(cov["selection_basis"]).strip().lower()
    return out


def declared_decisions(plan):
    """The structured decision enums this plan declares, normalized.

    Held in their own block of the fingerprint material, and stripped from the
    fields they were read from, so a diff can tell "the covariate set changed"
    from "the same covariates are now justified differently". The first needs all
    ten domains re-challenged; the second needs one.
    """
    decisions = {}
    estimand_type = _declared_estimand_type(plan)
    if estimand_type:
        decisions["estimand_type"] = estimand_type
    purpose = _declared_model_purpose(plan)
    if purpose:
        decisions["model_purpose"] = purpose
    intents = _declared_analysis_intents(plan)
    if intents:
        decisions["analysis_intent"] = intents
    basis = _declared_selection_basis(plan)
    if basis:
        decisions["selection_basis"] = basis
    return decisions


def _scrub(node, exclude):
    """Recursively drop `exclude` keys from dicts/lists. Returns a new structure."""
    if isinstance(node, dict):
        return {k: _scrub(v, exclude) for k, v in node.items() if k not in exclude}
    if isinstance(node, list):
        return [_scrub(v, exclude) for v in node]
    return node


DECISIONS_KEY = "_decisions"


def fingerprint_material(plan):
    """The exact structure that gets hashed. Exposed so it can be diffed."""
    material = {k: plan.get(k) for k in FINGERPRINT_FIELDS}
    for k in FINGERPRINT_FIELDS_OPTIONAL:
        if k in plan:
            material[k] = plan.get(k)
    material["pipeline"] = [
        {"id": s.get("id"), "skill": s.get("skill"), "outcome": s.get("outcome"),
         "depends_on": sorted(s.get("depends_on") or [])}
        for s in sorted(plan.get("pipeline") or [], key=lambda s: str(s.get("id")))
    ]
    decisions = declared_decisions(plan)
    # Lifted out of the fields they were read from and hashed once, here. Left in
    # place as well they would be hashed twice, and — worse — a decision change
    # would be indistinguishable from a covariate or outcome change in the diff,
    # which is exactly what the domain-scoped re-run has to tell apart.
    material = _scrub(material, FINGERPRINT_EXCLUDE_KEYS + DECISION_SOURCE_KEYS)
    if decisions:
        material[DECISIONS_KEY] = decisions
    return material


def plan_fingerprint(plan):
    """Hash of everything about the plan that changes what a challenge should find.

    The version number alone is not enough: an analysis can be edited — a
    covariate added, an outcome redefined, an advanced analysis switched on —
    without anyone bumping `version`, and the stale challenge would then pass the
    gate while describing a study that no longer exists. Execution state
    (statuses, timestamps, runtimes, checkpoints) is excluded on purpose, so
    simply re-running the pipeline does not invalidate a challenge.

    The same test decides everything else: a field belongs in the fingerprint if
    changing it changes what a reviewer should look for. Documentation fields do
    not (see FINGERPRINT_EXCLUDE_KEYS), and fields that did not exist when a plan
    was written do not appear at all (FINGERPRINT_FIELDS_OPTIONAL) — otherwise
    every schema addition silently invalidates every challenge on disk.

    When a fingerprint changes and you cannot see why:
        python3 reviewer_challenge.py explain-fingerprint --plan A [--against B]
    """
    blob = json.dumps(fingerprint_material(plan), sort_keys=True,
                      ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def rerun_scope(plan_a, plan_b):
    """Which domains a change invalidates. Returns a dict.

    The staleness gate is all-or-nothing by construction: one fingerprint, one
    verdict, ten agents. That is right for the question it answers ("was this
    analysis reviewed?") and far too blunt for the question a user actually has
    ("what do I have to run again?"). This narrows the second question without
    weakening the first — the fingerprint still moves, the challenge is still
    stale, but the stale part can be named.

    Only changes confined to FIELD_DOMAIN_MAP fields can be scoped. Anything else
    — a covariate added, an outcome redefined, a filter changed — reverts to all
    ten, because the map is about decisions *about* the analysis, not about the
    analysis itself. Reusing old reports is otherwise a way to paste a current
    stamp onto a review of a different study.
    """
    diffs = fingerprint_field_diff(plan_a, plan_b)
    changed = {d["field"] for d in diffs}
    other = sorted(changed - {DECISIONS_KEY})

    decision_fields = []
    if DECISIONS_KEY in changed:
        da = declared_decisions(plan_a)
        db = declared_decisions(plan_b)
        decision_fields = sorted(
            k for k in set(da) | set(db) if _canon(da.get(k)) != _canon(db.get(k)))

    if not changed:
        return {"mode": "none", "domains": [], "decision_fields": [],
                "other_fields": [], "reason": "the fingerprint material is identical"}
    if other:
        return {"mode": "full", "domains": list(DOMAIN_KEYS),
                "decision_fields": decision_fields, "other_fields": other,
                "reason": f"fields outside the decision map changed "
                          f"({', '.join(other)}); the analysis itself is different, "
                          f"not just how it is justified"}
    unmapped = [f for f in decision_fields if f not in FIELD_DOMAIN_MAP]
    if unmapped:
        return {"mode": "full", "domains": list(DOMAIN_KEYS),
                "decision_fields": decision_fields, "other_fields": [],
                "reason": f"decision field(s) with no domain mapping changed "
                          f"({', '.join(unmapped)}) — an unmapped field is treated as "
                          f"affecting everything"}
    domains, seen = [], set()
    for f in decision_fields:
        for d in FIELD_DOMAIN_MAP[f]:
            if d not in seen:
                seen.add(d)
                domains.append(d)
    return {"mode": "partial", "domains": domains,
            "decision_fields": decision_fields, "other_fields": [],
            "reason": f"only declared decisions changed ({', '.join(decision_fields)})"}


def scope_against_challenge(plan, agg):
    """Scope a re-run using a stored challenge, without the plan it reviewed.

    The realistic situation: the gate blocks, the plan that was challenged is
    gone or has been edited in place, and the only artefact left is the aggregate.
    Challenges written before `fingerprint_parts` existed cannot be scoped at all
    — that is reported as such rather than guessed at, because guessing here
    means carrying over a report that no longer applies.
    """
    parts = agg.get("fingerprint_parts")
    if not parts:
        return {"mode": "full", "domains": list(DOMAIN_KEYS), "decision_fields": [],
                "other_fields": [],
                "reason": "this challenge predates per-field digests, so what changed "
                          "cannot be established from it. Scoping needs the plan that "
                          "was challenged (a research_plan_v{N}.json backup, or git "
                          "history); without it the safe answer is all ten"}
    now = {k: hashlib.sha256(_canon(v).encode("utf-8")).hexdigest()[:16]
           for k, v in fingerprint_material(plan).items()}
    changed = sorted({k for k in set(parts) | set(now) if parts.get(k) != now.get(k)})
    other = [k for k in changed if k != DECISIONS_KEY]
    if not changed:
        return {"mode": "none", "domains": [], "decision_fields": [],
                "other_fields": [], "reason": "the challenge covers this plan exactly"}
    if other:
        return {"mode": "full", "domains": list(DOMAIN_KEYS), "decision_fields": [],
                "other_fields": other,
                "reason": f"fields outside the decision map changed "
                          f"({', '.join(other)})"}
    was = agg.get("declared_decisions") or {}
    is_ = declared_decisions(plan)
    fields = sorted(k for k in set(was) | set(is_)
                    if _canon(was.get(k)) != _canon(is_.get(k)))
    unmapped = [f for f in fields if f not in FIELD_DOMAIN_MAP]
    if unmapped or not fields:
        return {"mode": "full", "domains": list(DOMAIN_KEYS), "decision_fields": fields,
                "other_fields": [],
                "reason": "the decision block moved but cannot be attributed to mapped "
                          "fields"}
    domains, seen = [], set()
    for f in fields:
        for d in FIELD_DOMAIN_MAP[f]:
            if d not in seen:
                seen.add(d)
                domains.append(d)
    return {"mode": "partial", "domains": domains, "decision_fields": fields,
            "other_fields": [], "reason": f"only declared decisions changed "
                                          f"({', '.join(fields)})"}


def cmd_rerun_scope(args):
    """Which domains have to be re-challenged, against a plan or a stored challenge."""
    plan = _load_plan(args.plan, "")
    print(f"Plan        : {os.path.abspath(args.plan)}")
    print(f"Fingerprint : {plan_fingerprint(plan)}")
    if args.against:
        other = _load_plan(args.against, "comparison")
        print(f"Against plan: {os.path.abspath(args.against)}  {plan_fingerprint(other)}")
        scope = rerun_scope(other, plan)
    else:
        agg, err = None, None
        try:
            with open(args.challenge, "r", encoding="utf-8") as f:
                agg = json.load(f)
        except Exception as exc:
            err = str(exc)
        if agg is None:
            _fail(f"cannot read challenge {args.challenge}: {err}")
        print(f"Challenge   : {os.path.abspath(args.challenge)}  "
              f"v{agg.get('version')}  {agg.get('plan_fingerprint')}")
        scope = scope_against_challenge(plan, agg)
    print_rerun_scope(scope)
    return 0 if scope["mode"] in ("none", "partial") else 1


def print_rerun_scope(scope, header="Domain-scoped re-run"):
    """Render a scope, including what may be carried over and what that costs."""
    print(f"\n{header}")
    print(f"  verdict : {scope['mode']} — {scope['reason']}")
    if scope["mode"] == "none":
        print("  action  : nothing to re-run.")
        return
    print(f"  re-run  : {len(scope['domains'])}/{len(DOMAIN_KEYS)} domain(s)")
    for d in scope["domains"]:
        print(f"              - {d:<34s} {DOMAIN_LABEL.get(d, '')}")
    carried = [d for d in DOMAIN_KEYS if d not in scope["domains"]]
    if carried:
        print(f"  carry over: {len(carried)} existing report(s) — "
              f"{', '.join(carried)}")
        print("  Re-run the listed domains as fresh-context agents, then re-run "
              "`aggregate` over the new reports PLUS the carried-over report files. "
              "aggregate recomputes the fingerprint against the current plan, so the "
              "result is stamped for this analysis.")
        print("  Record in decision_log.md which domains were carried over and why — "
              "a carried-over report is a claim that nothing in it was affected.")


def describe_change(va, vb, indent="      "):
    """Lines locating a difference *inside* a field, not just naming the field.

    `covariates` differing is not usable information — the whole list prints
    identically for the first 200 characters and the reader is back to re-running
    the challenge to find out what moved. Which covariate, or which sub-key, is.
    """
    lines = []
    if isinstance(va, dict) and isinstance(vb, dict):
        only_a = sorted(set(va) - set(vb))
        only_b = sorted(set(vb) - set(va))
        changed = sorted(k for k in set(va) & set(vb) if _canon(va[k]) != _canon(vb[k]))
        if only_a:
            lines.append(f"{indent}removed key(s): {', '.join(only_a)}")
        if only_b:
            lines.append(f"{indent}added key(s)  : {', '.join(only_b)}")
        for k in changed:
            lines.append(f"{indent}changed `{k}`:")
            lines.append(f"{indent}    A: {_canon(va[k])[:150]}")
            lines.append(f"{indent}    B: {_canon(vb[k])[:150]}")
        return lines
    if isinstance(va, list) and isinstance(vb, list):
        ca, cb = [_canon(x) for x in va], [_canon(x) for x in vb]
        removed = [x for x in ca if x not in cb]
        added = [x for x in cb if x not in ca]
        lines.append(f"{indent}{len(va)} entr(ies) -> {len(vb)}")
        for x in removed[:6]:
            lines.append(f"{indent}  - {x[:150]}")
        for x in added[:6]:
            lines.append(f"{indent}  + {x[:150]}")
        if len(removed) > 6 or len(added) > 6:
            lines.append(f"{indent}  … {len(removed)} removed / {len(added)} added in total")
        return lines
    lines.append(f"{indent}A: {_canon(va)[:200]}")
    lines.append(f"{indent}B: {_canon(vb)[:200]}")
    return lines


def fingerprint_field_diff(plan_a, plan_b):
    """Which fingerprint fields differ between two plans. Returns a list of dicts.

    This is the part that was missing: when the gate says "the plan has changed",
    the only recourse was to re-run a three-hour challenge, because nothing could
    say *what* changed.
    """
    ma, mb = fingerprint_material(plan_a), fingerprint_material(plan_b)
    out = []
    for key in sorted(set(ma) | set(mb)):
        va, vb = ma.get(key), mb.get(key)
        if _canon(va) == _canon(vb):
            continue
        out.append({"field": key, "in_a": va, "in_b": vb,
                    "only_in": "a" if key not in mb else ("b" if key not in ma else None)})
    return out


def build(plan_path, report_paths):
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except Exception as exc:
        _fail(f"cannot read plan {plan_path}: {exc}")

    plan_fp = plan_fingerprint(plan)
    reports, problems, prov_warnings = [], [], []
    for p in report_paths:
        rep, probs = load_report(p)
        problems.extend(probs)
        if rep:
            # Where did this report come from? A deterministic producer writes its
            # result to a fixed path, so the previous round's file is sitting
            # exactly where this round's belongs — and a `verdict: pass` reads the
            # same either way.
            pp, pw = provenance_problems(
                rep, str(rep.get("domain") or os.path.basename(p)), plan_fp)
            problems.extend(pp)
            prov_warnings.extend(pw)
            reports.append(rep)

    seen = {r.get("domain") for r in reports}
    missing = [d for d in DOMAIN_KEYS if d not in seen]
    duplicates = sorted({d for d in seen if [r.get("domain") for r in reports].count(d) > 1})

    fatal = [(r["domain"], c) for r in reports for c in r.get("comments", [])
             if c.get("verdict") == "fatal" and c.get("status") == "open"]
    concern = [(r["domain"], c) for r in reports for c in r.get("comments", [])
               if c.get("verdict") == "concern" and c.get("status") == "open"]

    out = {
        "version": plan.get("version", 1),
        "plan_fingerprint": plan_fp,
        # Per-key digests of the fingerprint material. The aggregate stores only a
        # single hash, so when a later plan fails the gate there is no way to work
        # out *what* moved without still having the plan that was challenged —
        # which is how a scoped re-run becomes impossible and everyone re-runs ten
        # agents. These make the comparison possible from the challenge alone.
        "fingerprint_parts": {k: hashlib.sha256(
            _canon(v).encode("utf-8")).hexdigest()[:16]
            for k, v in fingerprint_material(plan).items()},
        "declared_decisions": declared_decisions(plan),
        "generated_at": datetime.now().isoformat(),
        "plan": os.path.abspath(plan_path),
        "domains_expected": DOMAIN_KEYS,
        "domains_reported": sorted(seen),
        "domains_missing": missing,
        "domains_duplicated": duplicates,
        "schema_problems": problems,
        # Non-blocking: reports written before provenance fields existed cannot
        # prove they belong to this round, and saying so is more useful than
        # failing every project that has one.
        "provenance_warnings": prov_warnings,
        "counts": {
            "fatal_open": len(fatal),
            "concern_open": len(concern),
            "comments_total": sum(len(r.get("comments", [])) for r in reports),
        },
        "reports": reports,
    }
    return out, missing, problems, fatal, concern, prov_warnings


def write_markdown(out, path):
    L = []
    L.append(f"# Reviewer Challenge — v{out['version']}\n")
    L.append(f"_產生於 {out['generated_at']}；rubric 見 "
             f"`references/reviewer_challenge.md`_\n")
    c = out["counts"]
    L.append(f"**未結案 fatal：{c['fatal_open']}　未結案 concern：{c['concern_open']}　"
             f"意見總數：{c['comments_total']}**\n")

    if out["domains_missing"]:
        L.append("## ⛔ 涵蓋範圍不足\n")
        L.append("下列 domain 沒有回報，這份挑戰**不算跑完**：\n")
        for d in out["domains_missing"]:
            L.append(f"- `{d}` — {DOMAIN_LABEL[d]}")
        L.append("")

    if out["schema_problems"]:
        L.append("## ⚠ 報告格式問題\n")
        for p in out["schema_problems"]:
            L.append(f"- {p}")
        L.append("")

    for rep in sorted(out["reports"], key=lambda r: DOMAIN_KEYS.index(r["domain"])
                      if r.get("domain") in DOMAIN_KEYS else 99):
        icon = {"pass": "✓", "concern": "⚠", "fatal": "⛔"}.get(rep.get("verdict"), "?")
        L.append(f"## {icon} {DOMAIN_LABEL.get(rep.get('domain'), rep.get('domain'))}"
                 f" — `{rep.get('verdict')}`\n")
        if rep.get("checked"):
            L.append(f"_查了：{rep['checked']}_\n")
        for cm in rep.get("comments", []):
            L.append(f"### {cm.get('id', '?')} · {cm.get('severity')} · "
                     f"`{cm.get('verdict')}` · {cm.get('status')}")
            L.append(f"{cm.get('comment', '')}\n")
            L.append(f"- **證據**：{cm.get('evidence')}")
            L.append(f"- **建議**：{cm.get('remedy', '')}")
            if cm.get("demoted_from_fatal"):
                L.append(f"- _由 fatal 降級：{cm['demoted_from_fatal']}_")
            L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def cmd_domains(_args):
    print("Reviewer challenge rubric — one fresh-context agent per domain, "
          "no cross-talk:\n")
    for i, (key, label) in enumerate(DOMAINS, 1):
        print(f"  {i:>2}. {key:<34s} {label}")
    print("\n每隻 agent 的 prompt 必須含 references/reviewer_challenge.md §3 的反奉承條款。")
    return 0


def _load_plan(path, label):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        _fail(f"cannot read {label} plan {path}: {exc}")


def cmd_explain_fingerprint(args):
    """Show what the fingerprint is computed from, and what makes two differ."""
    plan = _load_plan(args.plan, "")
    material = fingerprint_material(plan)
    print(f"Plan        : {os.path.abspath(args.plan)}")
    print(f"Fingerprint : {plan_fingerprint(plan)}")
    print(f"\nHashed keys ({len(material)}):")
    for key in sorted(material):
        blob = _canon(material[key])
        present = "" if key in plan or key == "pipeline" else "   (absent in plan → null)"
        print(f"  {key:<20s} {len(blob):>7d} chars{present}")
    print("\nDeliberately NOT hashed:")
    print("  execution state      status / timestamps / runtimes / checkpoints")
    print(f"  documentation fields {', '.join(FINGERPRINT_EXCLUDE_KEYS)} "
          f"(removed at every depth)")
    print(f"  fields absent from this plan: "
          f"{', '.join(k for k in FINGERPRINT_FIELDS_OPTIONAL if k not in plan) or '(none)'}")

    decisions = declared_decisions(plan)
    print("\nDeclared decisions (hashed as normalized enums):")
    if decisions:
        for k, v in sorted(decisions.items()):
            print(f"  {k:<20s} {_canon(v)[:120]}")
            print(f"  {'':<20s} → domain(s): {', '.join(FIELD_DOMAIN_MAP.get(k, ('?',)))}")
    else:
        print("  (none declared — these are read only where stated, so this plan's "
              "fingerprint is unaffected by the decision fields)")
        print(f"  Declaring any of {', '.join(sorted(FIELD_DOMAIN_MAP))} WILL move the "
              f"fingerprint and invalidate an existing challenge. That is intended: "
              f"stating how covariates were selected, or that the model is predictive, "
              f"changes what a reviewer should look for. Use the domain-scoped re-run "
              f"below rather than re-running all ten.")

    if not args.against:
        return 0
    other = _load_plan(args.against, "comparison")
    print(f"\nAgainst     : {os.path.abspath(args.against)}")
    print(f"Fingerprint : {plan_fingerprint(other)}")
    diffs = fingerprint_field_diff(plan, other)
    if not diffs:
        print("\n  ✓ identical fingerprint material — any difference between these two "
              "plans is in fields the fingerprint ignores by design.")
        return 0
    print(f"\n  {len(diffs)} field(s) differ — this is why the fingerprint moved:")
    for d in diffs:
        note = f" (only in plan {d['only_in'].upper()})" if d["only_in"] else ""
        print(f"    • {d['field']}{note}")
        for line in describe_change(d["in_a"], d["in_b"], indent="        "):
            print(line)
    print_rerun_scope(rerun_scope(plan, other))
    return 0


# Fields whose change means the submitted analysis is not the one that was
# explored. Named in 02-stats-harness-review.md C-附 §2.
PROMOTION_CRITICAL = ("population", "grouping", "outcomes", "covariates",
                      "derived_variables", "analyses", "missing_data",
                      "advanced_analyses", "estimand", "pipeline", "study")


def find_decision_row(log_path, decision_id):
    """Locate a decision_log.md row by exact cell match. Returns (cells, error).

    Substring search over the whole file was the hole: `D-1` matches inside
    `D-14`, inside a date, inside prose. A decision log is a markdown table, so
    the ID is a cell — matching the cell means the reference resolves to exactly
    one row, or to nothing.
    """
    try:
        text = open(log_path, "r", encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return None, f"cannot read {log_path}: {exc}"
    wanted = decision_id.strip()
    hits = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if any(c == wanted for c in cells):
            hits.append(cells)
    if not hits:
        return None, (f"no row in {os.path.basename(log_path)} has {wanted!r} as a cell. "
                      f"An ID that resolves to nothing is the same as no record.")
    if len(hits) > 1:
        return None, (f"{len(hits)} rows in {os.path.basename(log_path)} carry the id "
                      f"{wanted!r}. A permanent ID has to identify one decision.")
    return hits[0], None


def verify_decision_row(cells, explore_fp, submit_fp):
    """The row must carry the reconciliation, not just the id. Returns problems[]."""
    problems = []
    joined = " | ".join(cells)
    for label, fp in (("explore", explore_fp), ("submit", submit_fp)):
        if fp not in joined:
            problems.append(
                f"the decision row does not carry the {label} fingerprint {fp}. Without "
                f"both, nothing ties that row to this promotion rather than another one.")
    if not [c for c in cells if len(c) >= 20 and not c.replace("-", "").isalnum()]:
        problems.append(
            "the decision row has no cell long enough to be a reason. It has to say why "
            "the analysis changed, in terms a rebuttal letter could quote.")
    return problems


def suggest_decision_row(decision_id, explore_fp, submit_fp, fields, after):
    """A row the user can paste, so the requirement is answerable rather than a puzzle."""
    return (f"| {decision_id} | active | promotion explore→submit | "
            f"changed: {', '.join(fields)} | explore {explore_fp} → submit {submit_fp} | "
            f"decided after seeing outcomes: {after or '<yes|no>'} | "
            f"<why the analysis changed> |")


def cmd_promotion_diff(args):
    """Gate the explore -> submit promotion on a recorded, dated decision.

    Dropping the manuscript step keeps an exploratory run from being typeset as a
    paper. It does nothing about the actual risk, which is the exploration's
    selection bias riding into the submitted version: a covariate that survived
    because the p-value moved, a cohort filter written in passing. Those show up
    here as a changed fingerprint field, and the only answer that means anything
    is a decision-log row that says what changed and whether it was decided after
    someone had seen the outcome.
    """
    explore = _load_plan(args.explore, "explore")
    submit = _load_plan(args.submit, "submit")
    diffs = fingerprint_field_diff(explore, submit)
    critical = [d for d in diffs if d["field"] in PROMOTION_CRITICAL]

    print(f"  explore : {os.path.abspath(args.explore)}  {plan_fingerprint(explore)}")
    print(f"  submit  : {os.path.abspath(args.submit)}  {plan_fingerprint(submit)}")
    print(f"  fields changed: {len(diffs)}  (analysis-defining: {len(critical)})")

    for d in diffs:
        flag = "⛔" if d["field"] in PROMOTION_CRITICAL else "·"
        print(f"\n  {flag} {d['field']}")
        for line in describe_change(d["in_a"], d["in_b"]):
            print(line)

    explore_fp, submit_fp = plan_fingerprint(explore), plan_fingerprint(submit)
    blocked = []
    row_verified = False

    if critical:
        if not args.decision_id:
            blocked.append(
                f"{len(critical)} analysis-defining field(s) changed between explore and "
                f"submit. Open a new row in decision_log.md and pass its permanent ID as "
                f"--decision-id.")
        if args.after_seeing_outcomes is None:
            blocked.append(
                "--after-seeing-outcomes yes|no is required. Whether the change was made "
                "before or after someone saw the outcome is the difference between a "
                "pre-specified analysis and a post-hoc one, and cannot be inferred later.")
        # --decision-log is mandatory once anything analysis-defining moved.
        # Omitting it used to skip the whole verification block, so
        # `--decision-id anything --after-seeing-outcomes no` was a free pass —
        # the cheapest possible way past the one gate that exists here.
        if not args.decision_log:
            blocked.append(
                "--decision-log is required when analysis-defining fields changed. The "
                "ID has to be resolved against a real row; taking the caller's word for "
                "it is the same as not asking.")
        elif args.decision_id:
            cells, err = find_decision_row(args.decision_log, args.decision_id)
            if err:
                blocked.append(err)
            else:
                row_problems = verify_decision_row(cells, explore_fp, submit_fp)
                blocked.extend(row_problems)
                row_verified = not row_problems

    record = {
        "generated_at": datetime.now().isoformat(),
        "explore_plan": os.path.abspath(args.explore),
        "submit_plan": os.path.abspath(args.submit),
        "explore_fingerprint": explore_fp,
        "submit_fingerprint": submit_fp,
        "changed_fields": [d["field"] for d in diffs],
        "analysis_defining_changes": [d["field"] for d in critical],
        "decision_log_id": args.decision_id,
        "decision_log": os.path.abspath(args.decision_log) if args.decision_log else None,
        "decision_log_verified": row_verified,
        "decided_after_seeing_outcomes": args.after_seeing_outcomes,
    }
    # Only write a record that would pass. A file on disk saying "promotion
    # reviewed" is what run_pipeline reads; writing one for a failed check would
    # hand the gate its own bypass.
    if args.out and not blocked:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        print(f"\n  Written: {args.out}")
    elif args.out:
        print(f"\n  Not written: {args.out} — the checks below did not pass, and a "
              f"promotion record on disk is what the manuscript gate reads.")

    if not critical:
        print("\n  ✓ The submitted analysis is the one that was explored. No new "
              "decision-log row is required by this check.")
        return 0

    if blocked:
        print()
        for b in blocked:
            print(f"  ⛔ {b}")
        print("\n  A row that would satisfy this check:")
        print("    " + suggest_decision_row(
            args.decision_id or "<ID>", explore_fp, submit_fp,
            [d["field"] for d in critical], args.after_seeing_outcomes))
        return 1

    if args.after_seeing_outcomes == "yes":
        print(f"\n  ⚠ Recorded as decided AFTER seeing outcome data under "
              f"{args.decision_id}. The submitted analysis is exploratory on these "
              f"fields; say so in the manuscript rather than presenting it as "
              f"pre-specified. Anchoring on results already seen cannot be undone by "
              f"re-running anything.")
    else:
        print(f"\n  ✓ Change recorded under {args.decision_id}, decided before outcomes "
              f"were seen.")
    return 0


def cmd_aggregate(args):
    out, missing, problems, fatal, concern, prov_warnings = build(args.plan, args.reports)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    md_path = os.path.splitext(args.out)[0] + ".md"
    write_markdown(out, md_path)

    print(f"  JSON: {args.out}")
    print(f"  MD:   {md_path}")
    print(f"  Domains reported: {len(out['domains_reported'])}/{len(DOMAIN_KEYS)}")

    blocked = False
    if prov_warnings:
        print(f"\n  ⚠ 出處無法驗證（{len(prov_warnings)}）—— 不擋，但這些 report "
              f"無法證明是本輪產生的：")
        for w in prov_warnings[:10]:
            print(f"     - {w}")
    if missing:
        print(f"\n  ⛔ 未涵蓋的 domain（{len(missing)}）：{', '.join(missing)}")
        print(f"     少跑 domain 不等於通過。補跑之後重新彙整。")
        blocked = True
    if out["domains_duplicated"]:
        print(f"\n  ⚠ 重複回報的 domain：{', '.join(out['domains_duplicated'])}")
    if problems:
        print(f"\n  ⚠ 報告格式問題（{len(problems)}）：")
        for p in problems[:10]:
            print(f"     - {p}")
        blocked = True
    if fatal:
        print(f"\n  ⛔ 未結案 fatal（{len(fatal)}）—— manuscript 步驟擋住：")
        for dom, c in fatal:
            print(f"     [{c.get('id')}] {dom}: {c.get('comment', '')[:110]}")
        print(f"\n     要繼續必須修正，或由使用者明示 override 並寫進 decision_log.md")
        print(f"     成為有永久 ID 的決策列（理由要寫得足以在 rebuttal letter 引用）。")
        blocked = True
    if concern and not blocked:
        print(f"\n  ⚠ 未結案 concern（{len(concern)}）—— 不擋，但每一條都要有去處："
              f"進 limitations、進 sensitivity 清單、或標 wontfix + 理由。")
    if not blocked and not concern:
        print(f"\n  ✓ 十個 domain 全數通過。查過的範圍：")
        for rep in out["reports"]:
            print(f"     - {DOMAIN_LABEL.get(rep['domain'], rep['domain'])}")

    return 1 if blocked else 0


# ── Gate: the pipeline-step form ──────────────────────────────────────────────

def _blocking(msg):
    print(f"[QC_BLOCKING] {msg}", file=sys.stderr)


def _warning(msg):
    print(f"[QC_WARNING] {msg}", file=sys.stderr)


def cmd_gate(config_path, check_only=False):
    """Verify a reviewer challenge exists, is complete, is current, and is clean.

    This step runs no analysis. It reads what the challenge already produced and
    decides whether the manuscript may be written — the checks are deliberately
    the ones a human cannot wave through by asserting the work was done:
    the aggregate file is on disk, it belongs to this version of the plan, all
    ten domains reported, no report is malformed, and no fatal comment is open.

    A fatal that the analyst has genuinely decided not to act on is closed by
    setting that comment's `status` to `wontfix` in the aggregate JSON, with the
    reason recorded in decision_log.md under a permanent ID. That is the override
    path, and it leaves a trace; there is no flag that simply skips the gate.
    """
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as exc:
        _fail(f"cannot read step config {config_path}: {exc}")

    if config.get("mode") != "reviewer-challenge":
        _fail(f"mode {config.get('mode')!r} is not 'reviewer-challenge'")

    plan_path = config.get("plan_path")
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
    except Exception as exc:
        _fail(f"cannot read plan {plan_path}: {exc}")

    version = plan.get("version", 1)
    agg_path = config.get("aggregate_file")
    if not agg_path:
        _fail("step config has no 'aggregate_file'")

    if check_only:
        print("=" * 78)
        print("REVIEWER CHALLENGE GATE (--check-missing)")
        print("=" * 78)
        print(f"  Plan version   : {version}")
        print(f"  Aggregate file : {agg_path}")
        present = ("yes" if os.path.exists(agg_path)
                   else "NO — the gate will block until the challenge has been run")
        print(f"  Present        : {present}")
        print(f"  Plan fingerprint: {plan_fingerprint(plan)}")
        print(f"  Will check     : file present · version and fingerprint match the "
              f"plan · all {len(DOMAIN_KEYS)} domains reported ·")
        print(f"                   every report re-validated · no open fatal comment ·")
        print(f"                   any wontfix fatal names a real decision_log.md row")
        print("=" * 78)
        return 0

    if not os.path.exists(agg_path):
        _blocking(
            f"No reviewer challenge on disk ({agg_path}). The manuscript step is "
            f"blocked until one has been run: `python3 reviewer_challenge.py domains` "
            f"to list the ten domains, one fresh-context agent each, then "
            f"`reviewer_challenge.py aggregate` to merge the reports. A challenge that "
            f"was never run and a challenge that found nothing are not the same thing.")
        return 3

    try:
        with open(agg_path, "r", encoding="utf-8") as f:
            agg = json.load(f)
    except Exception as exc:
        _blocking(f"reviewer challenge {agg_path} is unreadable ({exc})")
        return 3

    # Recompute the summary from `reports` instead of trusting it. The summary
    # fields are a convenience for readers; they are also the one place where a
    # hand-edit — or an aggregate written by an older version of this script —
    # could turn an open fatal into a pass without touching the finding itself.
    # Disagreement is treated as tampering rather than reconciled silently.
    reports = agg.get("reports") or []
    seen_domains = [r.get("domain") for r in reports]
    recomputed_missing = [d for d in DOMAIN_KEYS if d not in seen_domains]
    # Re-run the per-report schema checks rather than trusting the stored
    # `schema_problems`. Ten reports that each say verdict=pass with an empty
    # `checked` are a skipped challenge wearing a pass; the stored summary would
    # happily call that clean.
    # Needed by the per-report provenance check below as well as by the aggregate
    # comparison further down, so it is computed once, here.
    want_fp = plan_fingerprint(plan)
    recomputed_problems, recomputed_prov_warnings = [], []
    for i, rep in enumerate(reports):
        label = str(rep.get("domain") or f"report[{i}]")
        recomputed_problems += validate_report(rep, label)
        # Provenance is re-derived here for the same reason the counts are: the
        # aggregate's stored verdict about its own reports is a convenience, and
        # the gate is the place that must not take it on trust. `want_fp` is this
        # plan's fingerprint, so a report generated against an older plan is
        # caught even when the aggregate as a whole still matches.
        pp, pw = provenance_problems(rep, label, want_fp)
        recomputed_problems += pp
        recomputed_prov_warnings += pw
    recomputed_fatals = [(r.get("domain"), c) for r in reports
                         for c in (r.get("comments") or [])
                         if c.get("verdict") == "fatal" and c.get("status") == "open"]

    blocked = False
    stated_missing = agg.get("domains_missing") or []
    stated_fatal = int((agg.get("counts") or {}).get("fatal_open", 0))
    if sorted(stated_missing) != sorted(recomputed_missing) or \
            stated_fatal != len(recomputed_fatals):
        _blocking(
            f"The reviewer challenge summary does not match its own reports: it states "
            f"{len(stated_missing)} missing domain(s) and {stated_fatal} open fatal(s), but "
            f"the reports contain {len(recomputed_missing)} and {len(recomputed_fatals)}. "
            f"Re-run `reviewer_challenge.py aggregate` rather than editing the summary — "
            f"a verdict that disagrees with its evidence is not a verdict.")
        blocked = True

    agg_version = agg.get("version")
    if agg_version != version:
        _blocking(
            f"The reviewer challenge on disk is for plan version {agg_version!r}, but the "
            f"plan is now version {version!r}. A challenge against an earlier version of "
            f"the analysis does not cover what changed; re-run it and re-aggregate.")
        blocked = True

    # The version number is a human-maintained field and is routinely not bumped
    # for an edit that changes the analysis. The fingerprint catches that case.
    # (want_fp computed above, where the per-report provenance check needs it.)
    got_fp = agg.get("plan_fingerprint")
    if not got_fp:
        _blocking(
            "The reviewer challenge carries no plan fingerprint, so there is no way to "
            "tell which analysis it reviewed. Re-run `reviewer_challenge.py aggregate` "
            "against the current plan.")
        blocked = True
    elif got_fp != want_fp:
        _blocking(
            f"The plan has changed since the reviewer challenge was run (fingerprint "
            f"{got_fp} vs {want_fp}) even though the version number did not. Covariates, "
            f"outcomes, the population or an enabled analysis differ from what was "
            f"reviewed; re-run the challenge and re-aggregate.")
        blocked = True

    if recomputed_missing:
        _blocking(f"{len(recomputed_missing)} of {len(DOMAIN_KEYS)} rubric domains never "
                  f"reported: {', '.join(recomputed_missing)}. Partial coverage is not a pass.")
        blocked = True

    # Union of what the aggregate recorded and what re-validation finds. Trusting
    # only the stored list lets a hand-edited file declare itself clean; trusting
    # only the recomputation throws away problems the aggregator saw but the gate
    # cannot see any more, such as a report file that was unreadable at merge time.
    all_problems = list(dict.fromkeys(
        (agg.get("schema_problems") or []) + recomputed_problems))
    if all_problems:
        _blocking(f"{len(all_problems)} malformed domain report(s); the challenge "
                  f"cannot be read as a verdict. First: {all_problems[0]}")
        for p in all_problems[1:6]:
            print(f"    {p}", file=sys.stderr)
        blocked = True

    counts = agg.get("counts") or {}
    fatal_open = len(recomputed_fatals)
    if fatal_open:
        fatals = recomputed_fatals
        _blocking(f"{fatal_open} open fatal comment(s) — the manuscript may not be written "
                  f"until each is fixed, or closed as `wontfix` with the reason in "
                  f"decision_log.md under a permanent ID.")
        for dom, c in fatals[:10]:
            print(f"    [{c.get('id')}] {dom}: {str(c.get('comment', ''))[:110]}",
                  file=sys.stderr)
        blocked = True

    # A `wontfix` fatal is the one way past this gate, and the commit that added
    # it claimed the decision-log id "leaves a trace". It only does if something
    # reads the log: until this check existed, any non-empty string unlocked the
    # override and the referenced row did not have to exist.
    overrides = [(r.get("domain"), c) for r in reports
                 for c in (r.get("comments") or [])
                 if c.get("verdict") == "fatal" and c.get("status") == "wontfix"]
    if overrides:
        out_dir = config.get("output_dir") or os.path.dirname(os.path.abspath(plan_path))
        log_path = None
        for cand in ("decision_log.md", "report/decision_log.md",
                     "analysis/report/decision_log.md"):
            p = os.path.join(out_dir, cand)
            if os.path.exists(p):
                log_path = p
                break
        if not log_path:
            _blocking(
                f"{len(overrides)} fatal comment(s) are closed as `wontfix`, but there is "
                f"no decision_log.md under {out_dir}. An override with nowhere to read the "
                f"reason is the same as deleting the finding.")
            blocked = True
        else:
            log_text = open(log_path, "r", encoding="utf-8", errors="replace").read()
            for dom, c in overrides:
                ref = str(c.get("decision_log_id", "")).strip()
                if ref and ref not in log_text:
                    _blocking(
                        f"[{c.get('id')}] {dom}: decision_log_id {ref!r} does not appear in "
                        f"{os.path.relpath(log_path, out_dir)}. The override must point at a "
                        f"row that actually exists and states the reason.")
                    blocked = True

    for w in recomputed_prov_warnings[:10]:
        _warning(w)

    dup = sorted({d for d in seen_domains if d and seen_domains.count(d) > 1})
    if dup:
        _warning(f"domain(s) reported more than once: {', '.join(dup)}")

    concern_open = sum(1 for r in reports for c in (r.get("comments") or [])
                       if c.get("verdict") == "concern" and c.get("status") == "open")
    if concern_open and not blocked:
        _warning(f"{concern_open} open concern(s) — not blocking, but each needs a "
                 f"destination: limitations, the sensitivity list, or `wontfix` + reason.")

    print(f"  Challenge : {agg_path}")
    print(f"  Version   : {agg_version} (plan {version})")
    print(f"  Domains   : {len(agg.get('domains_reported') or [])}/{len(DOMAIN_KEYS)}")
    print(f"  Comments  : {counts.get('comments_total', 0)} "
          f"({fatal_open} open fatal, {concern_open} open concern)")
    if blocked:
        print("\n  ⛔ Gate blocked. The manuscript step will not run.")
        return 3
    print("\nDone!")
    print("  ✓ Gate passed — ten domains reported, no open fatal, challenge matches "
          "this plan version.")
    return 0


SUBCOMMANDS = ("domains", "aggregate", "explain-fingerprint", "promotion-diff",
               "rerun-scope")


def main():
    # The pipeline runner invokes every step as `script.py <config.json>
    # [--check-missing]`, which argparse subcommands cannot express. Anything that
    # is not a known subcommand is therefore a step config, and runs the gate.
    if len(sys.argv) > 1 and sys.argv[1] not in SUBCOMMANDS and not sys.argv[1].startswith("-"):
        sys.exit(cmd_gate(sys.argv[1], check_only="--check-missing" in sys.argv[2:]))

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("domains", help="list the ten rubric domains")

    agg = sub.add_parser("aggregate", help="merge domain reports into a gated verdict")
    agg.add_argument("--plan", required=True)
    agg.add_argument("--reports", nargs="+", required=True)
    agg.add_argument("--out", required=True)

    exp = sub.add_parser("explain-fingerprint",
                         help="show what the fingerprint hashes, and why two plans differ")
    exp.add_argument("--plan", required=True)
    exp.add_argument("--against", help="second plan to diff against")

    pro = sub.add_parser("promotion-diff",
                         help="gate the explore -> submit promotion on a recorded decision")
    pro.add_argument("--explore", required=True)
    pro.add_argument("--submit", required=True)
    pro.add_argument("--decision-id", help="permanent decision_log.md ID for this promotion")
    pro.add_argument("--decision-log", help="path to decision_log.md (the ID is looked up in it)")
    pro.add_argument("--after-seeing-outcomes", choices=("yes", "no"),
                     help="was the change decided after outcome data had been seen")
    pro.add_argument("--out", help="write the promotion record to this JSON path")

    rs = sub.add_parser("rerun-scope",
                        help="which domains a plan change invalidates (a stale "
                             "challenge does not always mean all ten)")
    rs.add_argument("--plan", required=True, help="the current plan")
    rs.add_argument("--challenge", help="an existing reviewer_challenge_vN.json")
    rs.add_argument("--against", help="the plan that was challenged, if you still have it")

    args = ap.parse_args()
    if args.cmd == "domains":
        sys.exit(cmd_domains(args))
    if args.cmd == "rerun-scope":
        if not (args.challenge or args.against):
            _fail("rerun-scope needs --challenge or --against")
        sys.exit(cmd_rerun_scope(args))
    if args.cmd == "explain-fingerprint":
        sys.exit(cmd_explain_fingerprint(args))
    if args.cmd == "promotion-diff":
        sys.exit(cmd_promotion_diff(args))
    sys.exit(cmd_aggregate(args))


if __name__ == "__main__":
    main()
