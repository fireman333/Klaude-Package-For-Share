#!/usr/bin/env python3
"""Execute the analysis pipeline defined in research_plan.json."""

import argparse
import fcntl
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# reviewer_challenge.py sits beside this file and owns plan_fingerprint(). The
# explore ledger stamps every row with the same fingerprint the reviewer gate
# checks, so the ledger and the gate cannot disagree about which version of the
# analysis a row belongs to.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reviewer_challenge import find_decision_row, plan_fingerprint  # noqa: E402


# Skills directory = parent of this skill's folder (sibling skills live beside research-plan)
_SKILLS = str(Path(__file__).resolve().parents[2])

# Map skill names to (script_path, check_flag)
SKILL_SCRIPTS = {
    "flowchart": (_SKILLS + "/flowchart/scripts/flowchart.py", "--preview"),
    "table1": (_SKILLS + "/table1/scripts/make_table1.py", "--check-missing"),
    "kaplan-meier": (_SKILLS + "/kaplan-meier/scripts/kaplan_meier.py", "--check-missing"),
    "competing-risk": (_SKILLS + "/competing-risk/scripts/competing_risk.py", "--check-missing"),
    "univariate-forest": (_SKILLS + "/univariate-forest/scripts/univariate_forest.py", "--check-missing"),
    "multivariate-interaction": (_SKILLS + "/multivariate-interaction/scripts/multivariate_interaction.py", "--check-missing"),
    # The executable halves of ph_violation_remedy. Each depends on the
    # multivariate step for its outcome: they read that step's *_ph_test.json to
    # learn whether — and on what — the assumption failed, so they can only run
    # after it. See generate_configs._REMEDY_STEPS.
    "ph-stratified": (_SKILLS + "/research-plan/scripts/ph_stratified.py", "--check-missing"),
    "ph-rmst": (_SKILLS + "/research-plan/scripts/ph_rmst.py", "--check-missing"),
    "ph-time-varying": (_SKILLS + "/research-plan/scripts/ph_time_varying.py", "--check-missing"),
    "psm-matching": (_SKILLS + "/psm-matching/scripts/psm_matching.py", "--check-missing"),
    "auc-cstat": (_SKILLS + "/auc-cstat/scripts/auc_cstat.py", "--check-missing"),
    # One script, two modes: config["mode"] == "assessment" (step `missingness`)
    # or "imputation" (step `mi_{outcome_id}`). See references/missing_data_protocol.md.
    "missing-data": (_SKILLS + "/research-plan/scripts/missing_data.py", "--check-missing"),
    # references/advanced_analyses.md — the seven gaps an adversarial audit
    # called out as reviewer-rejection material.
    "nonlinearity": (_SKILLS + "/research-plan/scripts/nonlinearity.py", "--check-missing"),
    "robust-variance": (_SKILLS + "/research-plan/scripts/robust_variance.py", "--check-missing"),
    "calibration": (_SKILLS + "/research-plan/scripts/calibration.py", "--check-missing"),
    "weighting": (_SKILLS + "/research-plan/scripts/weighting.py", "--check-missing"),
    "immortal-time": (_SKILLS + "/research-plan/scripts/immortal_time.py", "--check-missing"),
    "evalue": (_SKILLS + "/research-plan/scripts/evalue.py", "--check-missing"),
    "strobe": (_SKILLS + "/research-plan/scripts/strobe.py", "--check-missing"),
    # Runs no analysis: it reads the reviewer challenge already on disk and blocks
    # the manuscript when it is absent, stale, incomplete or carries an open fatal.
    # See references/reviewer_challenge.md.
    "reviewer-challenge": (_SKILLS + "/research-plan/scripts/reviewer_challenge.py",
                           "--check-missing"),
}

# Steps that belong to the supplementary group (run after every outcome group,
# because they read the per-outcome outputs).
SUPPLEMENTARY_SKILLS = ("psm-matching", "auc-cstat", "calibration", "weighting", "evalue")

# manuscript-results is special: two scripts, no check mode
MANUSCRIPT_EXTRACT = _SKILLS + "/manuscript-results/scripts/extract_data.py"

# The staleness watchdog. Read at the pre-manuscript checkpoint so its verdict is
# on the same screen as everything else the user is being asked to sign off.
CHECK_FRESHNESS = _SKILLS + "/research-plan/assets/check_freshness.py"

# The deterministic pre/post-flight checks. Until this call site existed the
# script could only be run by hand, so the whole deterministic layer — column
# existence, dtypes, reference levels, EPV, PSM direction, success criteria —
# was documented as replacing the guardian fan-out while replacing nothing.
PRECHECK = _SKILLS + "/research-plan/scripts/precheck_configs.py"

# The coverage audit behind watchdog check C7. Run here, right after the
# post-flight, so "which estimates were run but never reported" is answered for
# *this* run rather than whenever somebody last remembered to run it by hand — a
# coverage_diff.json left over from a previous run reports on outputs that no
# longer exist, and reports "0 omitted" while doing it.
ESTIMATE_INVENTORY = _SKILLS + "/research-plan/scripts/estimate_inventory.py"

# How long a checker subprocess gets before it counts as unable to run. Generous,
# because scanning many workbooks on a slow filesystem is legitimately slow;
# finite, because a child that never exits used to hang the pipeline with no way
# to report the one thing the contract requires it to report.
CHECKER_TIMEOUT_S = 900

# Run-time QC lines that are methodological findings rather than operational
# noise, and therefore belong in the manifest the reviewer agents read. Matched
# case-insensitively against the text of a [QC_*] line.
#
# Kept to a named list on purpose. Propagating every QC line would bury domain 5's
# actual finding under retry chatter, and each entry here also becomes a
# substitution the pre-manuscript gate demands a decision on — which is right for
# "the PH assumption is borderline" and absurd for "log file rotated".
RUNTIME_METHOD_WARNING_PATTERNS = (
    "ph borderline", "ph assumption", "proportional hazards",
    "competing risk", "immortal time", "positivity", "separation",
    "convergence", "epv",
)

# references/checkpoint_protocol.md:12-31 — adaptive checkpoint depth.
SLIM_AFTER_CONSECUTIVE_CONTINUES = 3
CHECKPOINT_SPOT_CHECK_RATE = 0.25

# Append-only exploration ledger (02-stats-harness-review.md C-附 §1). One row per
# executed step, never rewritten.
EXPLORE_LEDGER_NAME = "explore_ledger.jsonl"
_ledger_lock = threading.Lock()

# The explore -> submit promotion record (C-附 §2), written by
# `reviewer_challenge.py promotion-diff` and read here — a gate nothing calls is
# not a gate, it is a CLI tool with a gate's docstring.
PROMOTION_RECORD_NAME = "promotion_record.json"


def _estimate_scanner():
    """(scan_workbook, estimate_id) from estimate_inventory.py, or (None, reason).

    Both imported, neither reimplemented: the id is the join key between this
    ledger and coverage_diff.json, and a key each side builds for itself is a
    coincidence rather than a contract. The two had in fact already drifted —
    estimate_inventory strips the extension off the workbook name, the copy here
    used the plan's `output_file` verbatim, so a plan declaring "PSM.xlsx" rather
    than "PSM" produced ids that could never join, and a failed join is
    indistinguishable from an estimate that was never run.

    Imported lazily so a missing sibling script degrades to a recorded ledger
    failure rather than stopping the pipeline from starting at all.
    """
    try:
        from estimate_inventory import estimate_id, scan_workbook
        return (scan_workbook, estimate_id), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def step_estimate_inventory(step, output_dir):
    """What this step actually estimated. Returns (inventory, error).

    The ledger exists to answer "which estimates were run"; a null here made
    every row useless for exactly the omission check it was added to feed. Ids
    come from estimate_inventory.estimate_id, so coverage_diff.json joins on them
    with no translation layer and no second definition to drift.

    Note `stem` is only used to locate the workbook. The id is built from the
    resolved path, so a plan writing `output_file: "PSM.xlsx"` yields the same
    id as one writing `"PSM"` — the drift that used to make those two plans
    unjoinable.
    """
    tools, why = _estimate_scanner()
    if tools is None:
        return None, f"estimate_inventory.py unavailable ({why})"
    scan, make_id = tools
    stem = step.get("output_file", step["id"])
    path = os.path.join(output_dir, f"{os.path.splitext(str(stem))[0]}.xlsx")
    if not os.path.exists(path):
        return {"count": 0, "ids": [], "workbook": None,
                "note": "step wrote no workbook"}, None
    try:
        found = scan(path)
    except Exception as exc:
        return None, f"{os.path.basename(path)}: {type(exc).__name__}: {exc}"
    ids = [make_id(r, path, i) for i, r in enumerate(found)]
    return {"count": len(ids), "ids": ids, "workbook": os.path.basename(path),
            "id_source": "estimate_inventory.estimate_id"}, None


def resolve_checkpoint_type(base_type, consecutive_continue_count, rng=None):
    """Pick the checkpoint depth for a group. Returns (type, was_spot_check).

    Implements the table in references/checkpoint_protocol.md:12-31, which until
    now existed only as prose: the runner hard-coded one string per group, so
    `consecutive_continue_count` was never read and SLIM was unreachable.

    MANDATORY never degrades — those are the boundaries where a wrong decision is
    expensive (cohort size, synthesis, manuscript). Everything else drops to SLIM
    once the user has said "continue" three times running, with a ~25% spot check
    back to FULL so that a run of continues does not train the user to stop
    looking.
    """
    if base_type == "MANDATORY":
        return "MANDATORY", False
    if (consecutive_continue_count or 0) < SLIM_AFTER_CONSECUTIVE_CONTINUES:
        return "FULL", False
    if (rng or random).random() < CHECKPOINT_SPOT_CHECK_RATE:
        return "FULL", True
    return "SLIM", False


def file_sha256(path):
    """SHA-256 of a file, or None when it is not readable.

    Unreadable is reported by the caller rather than swallowed — a missing hash
    means the provenance claim cannot be made, which is information.
    """
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        print(f"[QC_WARNING] cannot hash {path}: {exc}", file=sys.stderr)
        return None


def append_explore_ledger(output_dir, row):
    """Append one row to the append-only explore ledger.

    Why this exists: dropping the manuscript step is enough to stop an
    exploratory run being typeset as a paper, and not nearly enough to stop the
    exploration's selection bias riding into the submitted version — a covariate
    kept because the p-value moved, a cohort filter written in passing and never
    revisited. The ledger is the record of what was actually estimated, so the
    promotion diff has something to compare against and omitted estimates can be
    listed rather than forgotten.

    Opened with 'a' and never rewritten. A failure here is surfaced, not
    swallowed: an incomplete ledger that nobody knows is incomplete is worse than
    no ledger.
    """
    path = os.path.join(output_dir, EXPLORE_LEDGER_NAME)
    try:
        with _ledger_lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return True
    except OSError as exc:
        print(f"[QC_WARNING] explore ledger not written ({path}): {exc}", file=sys.stderr)
        return False


def load_plan(plan_path):
    with open(plan_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_plan_shape(plan, plan_path):
    """Refuse an unusable plan with a named reason instead of a raw KeyError.

    Step 0's resume path runs this script *first* and skips generate_configs.py
    entirely, so one design-stage plan produced a clean `[QC_BLOCKING] [FATAL]`
    list of missing fields down one route and a Python stack trace down the
    other. The plan is not broken in that state — `outcomes` still a list, no
    `grouping`, no `pipeline` is what a plan looks like before Step 3 expands it
    — and an intermediate state real users hit deserves an instruction, not a
    traceback.

    Checks only what this script itself dereferences. generate_configs.py owns
    the authoritative schema check, and duplicating its list here would create a
    second definition to drift, so the message points at it instead.

    Exit code 1, matching generate_configs.py's "the plan is not usable".
    Deliberately not 2: in this file 2 already means "the command was invoked
    wrongly" (an unknown --from / --only), and precheck_configs.py's opposite
    convention (2 = cannot run) is documented as intentional. A bad plan is not a
    bad invocation — and inventing a third convention is how the [FATAL]-prefix
    confusion started in the first place. Both markers are emitted for the same
    reason that file gives: callers split into those that read exit codes and
    those that scan stderr for [QC_*] findings.
    """
    problems = []
    if "output_dir" not in plan:
        problems.append('"output_dir" (absolute path holding configs/ and outputs)')
    pipeline = plan.get("pipeline")
    if pipeline is None:
        problems.append('"pipeline" (list of analysis steps) — this plan has not '
                        'been expanded into steps yet')
    elif not isinstance(pipeline, list):
        problems.append(f'"pipeline" must be a list of steps, not '
                        f'{type(pipeline).__name__}')
    else:
        for i, step in enumerate(pipeline):
            if not isinstance(step, dict):
                problems.append(f'pipeline[{i}] must be an object, not '
                                f'{type(step).__name__}')
                continue
            for key in ("id", "skill"):
                if not step.get(key):
                    problems.append(f'pipeline[{i}] has no "{key}"')
    # `outcomes` as a list is the design-stage shape. plan_fingerprint and several
    # readers call .get() on it, which raises AttributeError several frames deep.
    if "outcomes" in plan and not isinstance(plan["outcomes"], dict):
        problems.append(
            f'"outcomes" must be an object keyed by primary/secondary, not '
            f'{type(plan["outcomes"]).__name__} — the design-stage list form has '
            f'not been converted yet')

    if not problems:
        return
    print(f"[QC_BLOCKING] [FATAL] research_plan.json ({plan_path}) cannot be executed:\n"
          + "\n".join(f"  - {p}" for p in problems)
          + "\n\nThis looks like a plan that has not finished Step 3 (expanding the "
            "design into a `pipeline[]`). Next: complete it against "
            "references/plan_template.md, then run\n"
            f"    python3 generate_configs.py {plan_path}\n"
            "which validates the full schema and writes the configs this script runs.",
          file=sys.stderr)
    sys.exit(1)


def save_plan(plan, plan_path):
    """Save plan with atomic write and file lock for concurrent safety."""
    tmp_path = plan_path + ".tmp"
    lock_path = plan_path + ".lock"
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, plan_path)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def topo_sort(pipeline):
    """Topological sort of pipeline steps using Kahn's algorithm."""
    # Build adjacency and in-degree
    steps = {s["id"]: s for s in pipeline}
    in_degree = {s["id"]: 0 for s in pipeline}
    dependents = {s["id"]: [] for s in pipeline}

    for s in pipeline:
        for dep in s.get("depends_on", []):
            if dep in steps:
                in_degree[s["id"]] += 1
                dependents[dep].append(s["id"])

    # BFS
    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    sorted_ids = []
    while queue:
        # Sort for deterministic order
        queue.sort()
        node = queue.pop(0)
        sorted_ids.append(node)
        for dep_id in dependents[node]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(dep_id)

    if len(sorted_ids) != len(pipeline):
        # Cycle detected — just return original order
        return [s["id"] for s in pipeline]
    return sorted_ids


def should_run(step, run_from, run_only, reached_from):
    """Determine if a step should be run.

    Semantics (fixed 2026-08-11 — the previous version re-ran every completed
    step whenever --from was absent, which silently defeated both Step 5
    mid-entry detection and Step F selective re-run):

      --only ID   run exactly that step, nothing else
      --from ID   skip everything ordered before ID regardless of status;
                  from ID onwards run everything, including already-done steps
      neither     run pending / needs_rerun / error / blocked; never touch done
    """
    if run_only:
        return step["id"] == run_only

    # --from: everything ordered before the target is skipped, whatever its status.
    if run_from and not reached_from:
        return False

    status = step.get("status", "pending")
    if status == "done":
        # A completed step is only redone when --from explicitly reaches it.
        return bool(run_from)
    return status in ("pending", "needs_rerun", "error", "blocked")


def run_script(python_exe, script_path, config_path, check_flag=None, log_path=None):
    """Run a Python script and return (success, stdout, stderr, duration)."""
    script_path = os.path.expanduser(script_path)
    if not os.path.exists(script_path):
        return False, "", f"Script not found: {script_path}", 0.0

    cmd = [python_exe, script_path, config_path]
    if check_flag:
        cmd.append(check_flag)

    start = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=600
        )
        duration = time.time() - start
        return result.returncode == 0, result.stdout, result.stderr, duration
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return False, "", "Script timed out after 600 seconds", duration
    except Exception as e:
        duration = time.time() - start
        return False, "", str(e), duration


def append_log(log_path, header, stdout, stderr):
    """Append output to a log file."""
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"{header}\n")
        f.write(f"{'='*60}\n")
        if stdout:
            f.write("STDOUT:\n")
            f.write(stdout)
            f.write("\n")
        if stderr:
            f.write("STDERR:\n")
            f.write(stderr)
            f.write("\n")


# Prefixes that count as QC signal. GUARDIAN_* is written into qc_warnings[] by
# biostats-guardian's `runner.py writeback`; keeping it in the same vocabulary
# means pipeline_status.py classifies guardian blockers as blocking rather than
# silently demoting them to warnings.
QC_WARNING_PREFIXES = ('[QC_WARNING]', '[GUARDIAN_WARNING]')
QC_BLOCKING_PREFIXES = ('[QC_BLOCKING]', '[GUARDIAN_BLOCKING]')


def extract_qc_warnings(stderr):
    """Extract QC warning and blocking lines from stderr."""
    warnings = []
    if stderr:
        for line in stderr.split('\n'):
            line = line.strip()
            if line.startswith(QC_WARNING_PREFIXES + QC_BLOCKING_PREFIXES):
                warnings.append(line)
    return warnings


def _record_qc(step, stderr):
    """Append QC lines from `stderr` onto the step, de-duplicated.

    Returns the step's full qc_warnings list. Called after *every* subprocess
    phase (check, run, retry) so warnings survive a failing step.
    """
    existing = step.setdefault("qc_warnings", [])
    for line in extract_qc_warnings(stderr):
        if line not in existing:
            existing.append(line)
    return existing


def _mi_primary_with_psm(plan):
    """True when MI is the declared primary analysis while PSM is also running.

    Those two do not sit at the same estimand: the PSM step stays complete-case
    (missing_data_protocol.md §6), so it cannot serve as a sensitivity analysis
    for an MI primary — the two answer different questions on different subsets.
    Worth a human looking at before the outcome group is signed off.
    """
    if not plan:
        return False
    md = plan.get("missing_data") or {}
    if md.get("primary_analysis") != "mi":
        return False
    if (plan.get("analyses") or {}).get("psm_enabled"):
        return True
    return any(s.get("skill") == "psm-matching" for s in (plan.get("pipeline") or []))


def group_steps_by_analysis_group(pipeline, sorted_ids, plan=None):
    """Group pipeline steps into analysis groups for execution ordering.

    Groups:
    - foundation: flowchart, table1, missingness (missing-data step with no outcome)
    - outcome_{outcome_id}: km, cr, uni, multi, mi steps sharing the same outcome
    - supplementary: psm-matching, auc-cstat
    - manuscript: manuscript-results

    The `missing-data` skill appears in two places: the assessment step
    (`missingness`, no `outcome` field) belongs to foundation because its verdict
    informs every later model, while `mi_{outcome_id}` carries an `outcome` and
    rides along with that outcome's group. generate_configs.gen_missing_data()
    uses the same discriminator.

    Returns a list of group dicts with group_id, steps, checkpoint_type.
    """
    steps_map = {s["id"]: s for s in pipeline}

    foundation_steps = []
    outcome_groups = {}  # outcome_id -> list of steps
    supplementary_steps = []
    manuscript_steps = []

    for step_id in sorted_ids:
        step = steps_map[step_id]
        skill = step.get("skill", "")

        if skill in ("flowchart", "table1") or (
            skill == "missing-data" and not step.get("outcome")
        ):
            foundation_steps.append(step)
        elif skill in ("manuscript-results", "strobe", "reviewer-challenge"):
            # STROBE reads every artifact, so it belongs in the last group. Give
            # manuscript-results depends_on: ["strobe"] in the plan if the
            # checklist should be settled before the results section is drafted.
            # reviewer-challenge belongs here for the same reason and must be a
            # depends_on of manuscript-results: it is the gate, not a sibling.
            manuscript_steps.append(step)
        elif skill in SUPPLEMENTARY_SKILLS:
            supplementary_steps.append(step)
        else:
            # Outcome-based grouping (km, cr, uni, multi, mi, rcs, robust, landmark)
            outcome_id = step.get("outcome", "unknown")
            if outcome_id not in outcome_groups:
                outcome_groups[outcome_id] = []
            outcome_groups[outcome_id].append(step)

    groups = []

    if foundation_steps:
        groups.append({
            "group_id": "foundation",
            "steps": foundation_steps,
            "checkpoint_type": "MANDATORY",
        })

    # Sort outcome groups deterministically
    mi_vs_psm = _mi_primary_with_psm(plan)
    for outcome_id in sorted(outcome_groups.keys()):
        steps = outcome_groups[outcome_id]
        # An MI step that is the declared primary analysis, alongside a PSM step
        # that is not, is exactly the comparison a reader will make and the
        # pipeline cannot resolve. Force a human look rather than letting the
        # auto-continue counter carry it through.
        checkpoint = "FULL"
        halt = False
        if mi_vs_psm and any(s.get("skill") == "missing-data" and s.get("outcome")
                             for s in steps):
            checkpoint = "MANDATORY"
            halt = True
        g = {
            "group_id": f"outcome_{outcome_id}",
            "steps": steps,
            "checkpoint_type": checkpoint,
        }
        if halt:
            # Stops the run in auto mode too, not just under --hitl.
            g["halt_in_auto"] = True
            g["halt_reason"] = (
                "missing_data.primary_analysis is 'mi' while PSM also runs. The PSM step "
                "stays complete-case, so it is not a same-estimand sensitivity analysis "
                "for the MI primary. Decide which analysis the paper reports as primary, "
                "log it in decision_log.md with a permanent ID, then re-run to continue.")
        groups.append(g)

    if supplementary_steps:
        groups.append({
            "group_id": "supplementary",
            # Synthesis Review. Demoted from MANDATORY to FULL (P2-4): nothing
            # arrives between this checkpoint and the pre-manuscript one that can
            # change a decision, so two unconditional stops bought one decision.
            # As FULL it can degrade to SLIM under a run of continues; the
            # synthesis content itself now rides on the pre-manuscript briefing.
            "checkpoint_type": "FULL",
            # ...which only holds when that briefing is going to happen. A run
            # that produces a PSM or sensitivity comparison and stops there —
            # `--only psm`, or any plan with no manuscript step — has no later
            # gate to inherit, and a PSM pointing the other way to the primary is
            # precisely the thing a human has to see. The runner restores
            # MANDATORY in that case (see `gate_ahead`).
            "synthesis": True,
            "steps": supplementary_steps,
        })

    if manuscript_steps:
        groups.append({
            "group_id": "manuscript",
            "steps": manuscript_steps,
            "checkpoint_type": "MANDATORY",
            # checkpoint_protocol.md determines this one by "Manuscript generation
            # *pending*". The loop only ever checkpointed after a group ran, so the
            # stop landed after the results section had already been extracted —
            # too late to be a decision point. It fires before the group instead.
            "pre_checkpoint": True,
        })

    return groups


def run_precheck(plan_path, output_dir, stage, python_exe=None, skip=False):
    """Run precheck_configs.py. Returns (ok, summary).

    `ok` is False only for a blocking result (exit 1) or an inability to run
    (exit 2). Both stop the pipeline: a deterministic gate that is skipped when
    it cannot run is the "unconfigured is not a pass" mistake the watchdog
    already refuses to make. `--skip-precheck` is the deliberate way out, and it
    says so in the log.
    """
    if skip:
        print(f"  Precheck [{stage}]: SKIPPED by --skip-precheck. The deterministic "
              f"checks did not run; nothing below is evidence that they would pass.")
        return True, "skipped"
    script = os.path.expanduser(PRECHECK)
    if not os.path.exists(script):
        print(f"  ⛔ Precheck [{stage}]: {script} not found.")
        return False, "script missing"
    report_path = os.path.join(output_dir, f"precheck_report_{stage}.json")
    started = time.time()
    try:
        proc = subprocess.run(
            [python_exe or sys.executable, script, plan_path, "--stage", stage,
             "--report", report_path],
            capture_output=True, text=True, timeout=CHECKER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        # The contract says a checker that cannot run reports that it could not
        # run. A child that never exits cannot report anything, so the timeout is
        # what turns a hang into the answer the contract requires.
        msg = (f"precheck_configs.py --stage {stage} did not finish within "
               f"{CHECKER_TIMEOUT_S}s and was killed")
        print(f"  ⛔ Precheck [{stage}]: {msg}")
        print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
        return False, "could not run"
    except OSError as exc:
        # Bad interpreter path, exec failure, out of file descriptors. Previously
        # this left the runner with a raw traceback instead of a gate result.
        msg = f"could not start precheck_configs.py --stage {stage}: {exc}"
        print(f"  ⛔ Precheck [{stage}]: {msg}")
        print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
        return False, "could not run"
    text = (proc.stderr or "") + (proc.stdout or "")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    blocking = [ln for ln in lines if ln.startswith("[QC_BLOCKING]")]
    warnings = [ln for ln in lines if ln.startswith("[QC_WARNING]")]
    # precheck_configs.py reports "cannot run" with `sys.exit("[FATAL] ...")`,
    # which exits 1 rather than the 2 its own docstring promises. Counting only
    # [QC_*] prefixes therefore printed "exit 1 — 0 blocking / 0 warning" and
    # threw away the one line that said what was wrong.
    fatal = [ln for ln in lines if ln.startswith("[FATAL]")]
    print(f"  Precheck [{stage}]: exit {proc.returncode} — "
          f"{len(blocking)} blocking / {len(warnings)} warning"
          f"{f' / {len(fatal)} fatal' if fatal else ''}")
    for ln in blocking[:20] + warnings[:10] + fatal[:5]:
        print(f"    {ln}")
    if proc.returncode == 0:
        # Exit 0 with no report written is "nothing happened" wearing the same
        # face as "everything passed". Require evidence that this invocation
        # actually produced its report.
        try:
            fresh = os.path.getmtime(report_path) >= started - 1
        except OSError:
            fresh = False
        if not fresh:
            msg = (f"precheck_configs.py --stage {stage} exited 0 but did not write "
                   f"{os.path.basename(report_path)} for this run. A pass with no "
                   f"report is indistinguishable from a checker that did nothing.")
            print(f"  ⛔ Precheck [{stage}]: {msg}")
            print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
            return False, "could not run"
        return True, "clean"
    if fatal or proc.returncode == 2:
        return False, "could not run"
    if not blocking:
        # A non-zero exit with nothing named is the failure mode this whole round
        # has been removing: the run stops and the log cannot say why. Surface the
        # raw tail rather than printing a confident zero.
        print(f"    ⛔ precheck exited {proc.returncode} without naming a single "
              f"finding. Raw output follows; treat the exit as blocking.")
        for ln in (lines[-8:] or ["(no output at all)"]):
            print(f"    | {ln}")
        return False, "non-zero with no named finding"
    return False, "blocking"


DECISION_ID_RE = re.compile(r"\A(?:#\d+|[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)\Z")


def _decision_log_for(output_dir):
    for cand in ("decision_log.md", "report/decision_log.md",
                 "analysis/report/decision_log.md"):
        path = os.path.join(output_dir, cand)
        if os.path.exists(path):
            return path
    return os.path.join(output_dir, "decision_log.md")


def run_watchdog(output_dir, python_exe=None):
    """Run check_freshness.py. Returns (returncode, problem_lines, raw_text)."""
    wd = os.path.expanduser(CHECK_FRESHNESS)
    if not os.path.exists(wd):
        return None, [], f"watchdog script not found at {wd}"
    proc = subprocess.run([python_exe or sys.executable, wd, output_dir, "--quiet"],
                          capture_output=True, text=True)
    text = (proc.stdout or "") + (proc.stderr or "")
    problems = [ln.strip().lstrip("•").strip()
                for ln in text.splitlines() if ln.strip().startswith("•")]
    return proc.returncode, problems, text


def watchdog_failure_id(returncode, problems):
    """Content-derived id for *this* watchdog failure, or None when it passes.

    The same device as substitution_id, for the same reason: an override has to
    name what it releases. Derived from the sorted problem list, so fixing one
    check — or a different one starting to fail — produces a different id and the
    old override stops applying on its own. An override that outlives the failure
    it was written for is indistinguishable from having switched the gate off,
    which is what "records an id and never looks at it again" amounted to.
    """
    if returncode == 0:
        return None
    material = json.dumps({"exit": returncode, "problems": sorted(problems)},
                          ensure_ascii=False, sort_keys=True)
    return "WD-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:8]


def watchdog_override_status(plan, output_dir, failure_id):
    """Is the recorded override valid for this failure? Returns (ok, message)."""
    ov = plan.get("watchdog_override") or {}
    if not ov:
        return False, None
    ref = str(ov.get("decision_log_id") or "").strip()
    was = str(ov.get("failure_id") or "").strip()
    if not ref:
        return False, "the recorded watchdog override carries no decision_log_id"
    if was != failure_id:
        return False, (
            f"the recorded override was written for watchdog failure "
            f"{was or '(unrecorded)'}, but the watchdog now fails with {failure_id}. "
            f"What it released has changed; review it and record a new one.")
    row, err = find_decision_row(_decision_log_for(output_dir), ref)
    if err:
        return False, f"{ref}: {err}"
    if failure_id not in " | ".join(row):
        return False, (
            f"{ref} exists but its row does not name {failure_id}, so it does not "
            f"document this failure. An ID pointing at some other decision is not a "
            f"record of this one.")
    return True, f"{ref} ({failure_id}): {ov.get('reason', '')}"


def record_watchdog_override(plan, plan_path, output_dir, decision_id, reason,
                             python_exe=None):
    """Bind an override to the specific watchdog failure it releases.

    Mirrors generate_configs._diagnostic_override, which this had none of: an ID
    that must look like a permanent record, must resolve to a real decision_log.md
    row, and must be about the thing it is releasing. The content-derived failure
    id supplies the last part and adds expiry, which even the diagnostics version
    does not have.
    """
    decision_id = (decision_id or "").strip()
    if not DECISION_ID_RE.match(decision_id):
        return False, (f"{decision_id!r} does not look like a permanent record ID "
                       f"(expected e.g. D-017, RP-2026-04, #42)")
    if not (reason or "").strip():
        return False, ("an override with no reason is the same as switching the check "
                       "off; pass --reason")
    rc, problems, text = run_watchdog(output_dir, python_exe)
    if rc is None:
        return False, text
    if rc == 0:
        return False, ("the watchdog currently passes, so there is nothing to override. "
                       "Overrides bind to a specific failure and cannot be written in "
                       "advance.")
    fid = watchdog_failure_id(rc, problems)
    row, err = find_decision_row(_decision_log_for(output_dir), decision_id)
    if err:
        return False, (
            f"{err}\n    The row has to exist first, and it has to name the failure. "
            f"One that would satisfy this check:\n"
            f"    | {decision_id} | active | watchdog override | {fid} | "
            f"{reason.strip()[:60]} | <what was checked instead> |")
    if fid not in " | ".join(row):
        return False, (
            f"{decision_id} exists but its row does not name {fid}. Add the failure id "
            f"to that row so the override is bound to what it releases.\n"
            f"    current watchdog failure {fid}:\n"
            + "\n".join(f"      • {p[:110]}" for p in problems[:5]))
    plan["watchdog_override"] = {
        "decision_log_id": decision_id,
        "failure_id": fid,
        "reason": reason.strip(),
        "problems": problems,
        "timestamp": datetime.now().isoformat(),
    }
    save_plan(plan, plan_path)
    return True, f"{decision_id} releases watchdog failure {fid}"


def _append_manifest_warning(output_dir, entry, label):
    """Add one entry to manifest.methodological_warnings, de-duplicated by kind."""
    path = os.path.join(output_dir, "configs", "manifest.json")
    manifest, err = _read_json(path)
    if manifest is None:
        print(f"  [QC_WARNING] {label} not recorded: manifest.json {err}", file=sys.stderr)
        return False
    existing = manifest.setdefault("methodological_warnings", [])
    if any(isinstance(w, dict) and w.get("kind") == entry["kind"] for w in existing):
        return True
    existing.append(entry)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"  [QC_WARNING] {label} not recorded: {exc}", file=sys.stderr)
        return False
    print(f"  Recorded {label} in configs/manifest.json "
          f"(the pre-manuscript gate will ask you to accept or reject it)")
    return True


def record_promotion_exemption(plan, output_dir, evidence):
    """Write down that the promotion gate was skipped, and on what basis.

    An exemption applied silently is a gate that quietly does not exist. Written
    into the manifest it becomes a substitution somebody has to accept — which is
    the right shape, because the claim being made is "this study was never
    exploratory", and only the author can confirm that.
    """
    return _append_manifest_warning(output_dir, {
        "kind": "promotion_gate_exempt", "source": "runtime",
        "text": (f"explore→submit promotion gate not applied: {evidence}. Accepting "
                 f"this asserts that no exploratory analysis preceded the submitted "
                 f"one. If exploration happened before the ledger existed, that "
                 f"assertion is false and the promotion has not been reconciled."),
    }, "the promotion-gate exemption")


def record_precheck_skip(plan, output_dir):
    """Write the fact that the deterministic checks were skipped into the manifest.

    Escape hatches have to cost something visible, or they become the default
    route. This one becomes a methodological substitution like any other, which
    means the pre-manuscript gate will ask for an explicit accept/reject on it
    before the manuscript can be written.
    """
    path = os.path.join(output_dir, "configs", "manifest.json")
    manifest, err = _read_json(path)
    if manifest is None:
        print(f"  [QC_WARNING] --skip-precheck not recorded: manifest.json {err}",
              file=sys.stderr)
        return False
    entry = {"kind": "precheck_skipped", "source": "runtime",
             "text": ("precheck_configs.py was skipped with --skip-precheck: the "
                      "deterministic column / dtype / reference-level / EPV / PSM-"
                      "direction / success-criteria checks did not run for this "
                      "pipeline.")}
    existing = manifest.setdefault("methodological_warnings", [])
    if not any(isinstance(w, dict) and w.get("kind") == "precheck_skipped"
               for w in existing):
        existing.append(entry)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
            print("  Recorded --skip-precheck in configs/manifest.json "
                  "(the pre-manuscript gate will ask you to accept or reject it)")
        except OSError as exc:
            print(f"  [QC_WARNING] --skip-precheck not recorded: {exc}", file=sys.stderr)
            return False
    return True


def run_estimate_inventory(output_dir, python_exe=None, skip=False):
    """Regenerate coverage_diff.json for this run. Returns (ok, summary).

    Ordered with the post-flight rather than left to whoever remembers: watchdog
    check C7 reads this file, and a coverage audit from a previous run reports on
    workbooks that no longer exist — while reporting "0 omitted" as it does so.
    C7 checks the file's freshness for the same reason, so the two agree instead
    of one silently standing in for the other.

    A non-zero exit here is not a failure of the pipeline: exit 1 means omissions
    exist, which is a question for the pre-manuscript gate, not an error.
    """
    if skip:
        return True, "skipped"
    script = os.path.expanduser(ESTIMATE_INVENTORY)
    if not os.path.exists(script):
        msg = f"{script} not found — coverage_diff.json cannot be produced"
        print(f"  ⛔ Coverage inventory: {msg}")
        print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
        return False, "script missing"
    try:
        proc = subprocess.run([python_exe or sys.executable, script, output_dir,
                               "--quiet"],
                              capture_output=True, text=True, timeout=CHECKER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        msg = (f"estimate_inventory.py did not finish within {CHECKER_TIMEOUT_S}s "
               f"and was killed; coverage_diff.json is not current")
        print(f"  ⛔ Coverage inventory: {msg}")
        print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
        return False, "could not run"
    except OSError as exc:
        msg = f"could not start estimate_inventory.py: {exc}"
        print(f"  ⛔ Coverage inventory: {msg}")
        print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
        return False, "could not run"
    tail = [ln for ln in (proc.stderr or "").splitlines() if ln.strip()][-3:]
    print(f"  Coverage inventory: exit {proc.returncode} "
          f"({'omissions found' if proc.returncode == 1 else 'no omissions' if proc.returncode == 0 else 'could not run'})")
    for ln in tail:
        print(f"    | {ln}")
    if proc.returncode == 2:
        return False, "could not run"
    return True, "omissions" if proc.returncode == 1 else "clean"


def propagate_runtime_warnings(plan, output_dir):
    """Lift methodological QC lines from the run into configs/manifest.json.

    The manifest is written at plan time by generate_configs.py, so anything only
    discoverable by *running* the analysis — the PH assumption turning out to be
    borderline, for instance — reached `step.qc_warnings[]` and stopped there.
    The reviewer-challenge agents read the manifest, so domain 5 was being asked
    to assess proportional hazards while the evidence that it is borderline sat
    in a file it does not open.

    Merged by text, so re-running does not duplicate them. A regeneration of the
    configs drops them again, which is correct: they describe a particular run,
    and the next run re-emits them.
    """
    path = os.path.join(output_dir, "configs", "manifest.json")
    manifest, err = _read_json(path)
    if manifest is None:
        print(f"  [QC_WARNING] cannot propagate run-time warnings: manifest.json {err}",
              file=sys.stderr)
        return 0
    existing = manifest.setdefault("methodological_warnings", [])
    seen = {w if isinstance(w, str) else json.dumps(w, sort_keys=True, ensure_ascii=False)
            for w in existing}
    added, scanned = 0, 0
    for step in plan.get("pipeline") or []:
        for line in step.get("qc_warnings") or []:
            scanned += 1
            low = line.lower()
            # `[METHOD_WARNING]` is a prefix generate_configs.py already uses. No
            # analysis script emits it at run time today, so this is defensive:
            # the first one that does would otherwise be dropped here silently,
            # and a warning that announces itself as methodological is the last
            # thing that should need to match a keyword list to be believed.
            if (not line.strip().startswith("[METHOD_WARNING]")
                    and not any(p in low for p in RUNTIME_METHOD_WARNING_PATTERNS)):
                continue
            entry = {"kind": "runtime_qc", "source": "runtime",
                     "step": step["id"], "text": line}
            key = json.dumps(entry, sort_keys=True, ensure_ascii=False)
            if key in seen:
                continue
            seen.add(key)
            existing.append(entry)
            added += 1
    if added:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            print(f"  [QC_WARNING] manifest not updated: {exc}", file=sys.stderr)
            return 0
    print(f"  Run-time methodological warnings: scanned {scanned} QC line(s) / "
          f"added {added} to manifest / {len(existing)} total")
    for w in existing[-added:] if added else []:
        print(f"    + [{w['step']}] {w['text'][:100]}")
    return added


def _read_json(path):
    """Read JSON, returning (data, error_string). Never swallows the reason."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, "not on disk"
    except Exception as exc:
        return None, str(exc)


# ── Methodological substitutions: an answer, per item, that survives the run ──

def substitution_id(warning):
    """Stable short id for one manifest warning.

    Derived from content rather than position so that regenerating the configs
    does not renumber decisions already made, and so that *editing* a warning
    invalidates its acceptance — a substitution whose description changed is a
    different substitution.
    """
    text = warning if isinstance(warning, str) else json.dumps(
        warning, sort_keys=True, ensure_ascii=False, default=str)
    return "SUB-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def manifest_warnings(output_dir):
    """[(id, text)] for every methodological substitution. Returns (items, error)."""
    manifest, err = _read_json(os.path.join(output_dir, "configs", "manifest.json"))
    if manifest is None:
        return None, err
    items = []
    for w in manifest.get("methodological_warnings") or []:
        text = w if isinstance(w, str) else json.dumps(w, ensure_ascii=False, default=str)
        items.append((substitution_id(w), text))
    return items, None


def record_substitution_decision(plan, plan_path, sid, decision, reason):
    """Persist one accepted/rejected substitution. Returns (ok, message)."""
    if not reason or not reason.strip():
        return False, (f"{sid}: a reason is required. 'accepted' with no reason is "
                       f"the same as not reading it.")
    book = plan.setdefault("substitution_decisions", {})
    book[sid] = {"decision": decision, "reason": reason.strip(),
                 "timestamp": datetime.now().isoformat()}
    save_plan(plan, plan_path)
    return True, f"{sid} recorded as {decision}"


def unresolved_substitutions(plan, output_dir):
    """Returns (unresolved, rejected, error) for the manifest's substitutions.

    An unanswered substitution blocks. The point of reading the list aloud was
    never the reading — it was that somebody said yes to a specific swap, such as
    a planned Fine-Gray becoming a cause-specific Cox. Re-running the command was
    being recorded as that yes.
    """
    items, err = manifest_warnings(output_dir)
    if items is None:
        return None, None, err
    book = plan.get("substitution_decisions") or {}
    unresolved = [(sid, text) for sid, text in items
                  if (book.get(sid) or {}).get("decision") not in ("accepted", "rejected")]
    rejected = [(sid, text) for sid, text in items
                if (book.get(sid) or {}).get("decision") == "rejected"]
    return unresolved, rejected, None


# ── Config provenance: an output belongs to the config that produced it ───────

def step_config_state(step, output_dir):
    """One of ok / drifted / config_missing / unstamped, for a step's config."""
    cfg = os.path.join(output_dir, "configs", f"{step['id']}_config.json")
    recorded = step.get("config_sha256")
    if not recorded:
        return "unstamped"
    if not os.path.exists(cfg):
        # A recorded hash with no config is strictly worse than never having
        # stamped one: something produced these numbers and the specification is
        # now gone. This used to fall through both branches and report nothing.
        return "config_missing"
    return "ok" if file_sha256(cfg) == recorded else "drifted"


def mark_stale_steps(plan, plan_path, output_dir):
    """Demote steps whose config no longer matches what produced their output.

    Drift used to be reported only by --detect-only, which is the one entry point
    a person runs when they already suspect something. On the normal path the
    stale output was reused and everything downstream inherited it.

    done + drifted      -> needs_rerun   (a legal transition; the runner will redo it)
    done + config gone  -> blocked       (cannot be re-run or verified; needs a human)
    """
    stale, missing, checked = [], [], 0
    for step in plan.get("pipeline") or []:
        if step.get("status") != "done":
            continue
        checked += 1
        state = step_config_state(step, output_dir)
        if state == "drifted":
            step["status"] = "needs_rerun"
            step["stale_reason"] = "config changed since this output was produced"
            stale.append(step["id"])
        elif state == "config_missing":
            step["status"] = "blocked"
            step["blocked_by"] = "(config file deleted)"
            step["error_message"] = (
                "Output exists and was stamped with a config hash, but "
                f"configs/{step['id']}_config.json is gone. The numbers cannot be "
                "reproduced or checked; re-generate the configs or restore the file.")
            missing.append(step["id"])
    if stale or missing:
        save_plan(plan, plan_path)
    print(f"  Config provenance: checked {checked} completed step(s) / "
          f"{len(stale)} stale / {len(missing)} with a missing config")
    for sid in stale:
        print(f"    ↺ {sid}: config changed — marked needs_rerun")
    for sid in missing:
        print(f"    ⛔ {sid}: config file deleted — marked blocked")
    return stale, missing


# ── explore -> submit promotion ──────────────────────────────────────────────

def exploration_evidence(output_dir):
    """Did this project ever explore? Returns (explored, evidence_sentence).

    The promotion gate has to tell "never explored" from "explored and kept no
    record". Only the second is what it exists to catch; charging the first for a
    promotion that never happened is a false block, and false blocks are how a
    check gets routed around.

    The ledger is the evidence. Its absence is treated as "no exploration on
    record" rather than proof of innocence, which is why the exemption is written
    into the manifest for a human to accept rather than applied silently — a
    project that explored before the ledger existed looks exactly like one that
    never explored, and only the author can tell the difference.
    """
    path = os.path.join(output_dir, EXPLORE_LEDGER_NAME)
    if not os.path.exists(path):
        return False, (f"there is no {EXPLORE_LEDGER_NAME} in {output_dir}, so no "
                       f"exploratory run is on record")
    profiles, rows = set(), 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    profiles.add((json.loads(line) or {}).get("pipeline_profile"))
                    rows += 1
                except ValueError:
                    continue
    except OSError as exc:
        return True, f"{EXPLORE_LEDGER_NAME} exists but could not be read ({exc})"
    explore_rows = profiles - {"submit"}
    if not explore_rows:
        return False, (f"{EXPLORE_LEDGER_NAME} holds {rows} row(s), all of them from "
                       f"submit-profile runs — nothing was explored")
    return True, (f"{EXPLORE_LEDGER_NAME} records {rows} step run(s) under "
                  f"profile(s) {sorted(str(p) for p in explore_rows)}")


def verify_promotion_record(plan, output_dir):
    """Check the promotion record covers this plan. Returns (problems, exemption).

    Only meaningful for `pipeline_profile: "submit"`. Without this, the promotion
    diff was a command someone could choose to run: explore, edit the population,
    re-run under the submit profile, write the manuscript, and nothing ever asked
    what changed.

    `exemption` is a sentence when the gate does not apply because nothing was
    ever explored; the caller records it rather than passing silently.
    """
    problems = []
    path = os.path.join(output_dir, PROMOTION_RECORD_NAME)
    rec, err = _read_json(path)
    if rec is None:
        # A study that was `submit` from the first day never had an exploration to
        # be promoted from, and demanding a record of a promotion that did not
        # happen is a false block — which is how people learn to route around the
        # check. The distinction that matters is "never explored" versus "explored
        # and left no record": the second is the entire point of this gate.
        explored, evidence = exploration_evidence(output_dir)
        if not explored:
            return problems, evidence
        problems.append(
            f"No promotion record ({PROMOTION_RECORD_NAME}: {err}), but {evidence}. "
            f"The submitted analysis has to be reconciled against the one that was "
            f"explored: run `reviewer_challenge.py promotion-diff --explore "
            f"<explore plan> --submit <this plan> --out {path} "
            f"--decision-id <ID> --decision-log <decision_log.md> "
            f"--after-seeing-outcomes yes|no`")
        return problems, None

    want = plan_fingerprint(plan)
    if rec.get("submit_fingerprint") != want:
        problems.append(
            f"The promotion record was written for submit fingerprint "
            f"{rec.get('submit_fingerprint')}, but this plan is {want}. The plan "
            f"changed after the promotion was reviewed; re-run promotion-diff.")

    ledger_fp = last_explore_fingerprint(output_dir)
    if ledger_fp and rec.get("explore_fingerprint") != ledger_fp:
        problems.append(
            f"The promotion record compares against explore fingerprint "
            f"{rec.get('explore_fingerprint')}, but the last exploratory run in "
            f"{EXPLORE_LEDGER_NAME} was {ledger_fp}. It is reconciling against the "
            f"wrong exploration.")

    if rec.get("analysis_defining_changes"):
        if not str(rec.get("decision_log_id") or "").strip():
            problems.append(
                f"{len(rec['analysis_defining_changes'])} analysis-defining field(s) "
                f"changed ({', '.join(rec['analysis_defining_changes'])}) with no "
                f"decision_log_id in the promotion record.")
        if rec.get("decided_after_seeing_outcomes") not in ("yes", "no"):
            problems.append(
                "The promotion record does not say whether the changes were decided "
                "after the outcome had been seen. That is the difference between a "
                "pre-specified and a post-hoc analysis.")
        if not rec.get("decision_log_verified"):
            problems.append(
                "The promotion record was not verified against decision_log.md "
                "(decision_log_verified is absent or false). Re-run promotion-diff "
                "with --decision-log so the ID is resolved against a real row.")
    return problems, None


def last_explore_fingerprint(output_dir):
    """The fingerprint of the most recent non-submit run in the ledger."""
    path = os.path.join(output_dir, EXPLORE_LEDGER_NAME)
    if not os.path.exists(path):
        return None
    fp = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("pipeline_profile") != "submit":
                    fp = row.get("plan_fingerprint")
    except OSError as exc:
        print(f"[QC_WARNING] cannot read {path}: {exc}", file=sys.stderr)
    return fp


def print_manuscript_briefing(plan, output_dir, python_exe=None, skip_inventory=False):
    """The pre-manuscript sign-off screen. Returns the list of blockers (P2-4).

    This replaces a second unconditional stop after the supplementary group.
    Merging the two is only safe if the merged screen carries what both carried,
    so it states the synthesis, the reviewer-challenge verdict, the watchdog exit
    code, and — itemised, because a merged screen invites skimming — every
    methodological substitution the config generator made.

    It returns blockers rather than only printing them. A screen that reports a
    failed watchdog and then lets the run continue is a longer way of not having
    a gate, and printing to a log nobody is watching is what "auto mode" means.
    """
    python_exe = python_exe or sys.executable
    blockers = []
    print("\n" + "=" * 70)
    print("PRE-MANUSCRIPT REVIEW — everything below is signed off in one pass")
    print("=" * 70)

    # Refresh the coverage audit BEFORE the watchdog reads it. C7 blocks on an
    # audit older than the outputs it describes, and the gate fires inside the
    # group loop while the end-of-run refresh happens after it — so ordering the
    # refresh only at the end left the gate permanently blocked on a file that
    # nothing had yet had the chance to write.
    run_estimate_inventory(output_dir, python_exe, skip=skip_inventory)

    print("\n[1/6] Synthesis — what will be written up")
    for step in plan.get("pipeline") or []:
        if step.get("skill") in ("manuscript-results",):
            continue
        out = step.get("output_file", step["id"])
        print(f"   {step.get('status', 'pending'):<12s} {step['id']:<24s} {out}.xlsx")

    print("\n[2/6] Reviewer challenge")
    version = plan.get("version", 1)
    agg_path = os.path.join(output_dir, f"reviewer_challenge_v{version}.json")
    agg, err = _read_json(agg_path)
    if agg is None:
        print(f"   ⛔ {os.path.basename(agg_path)}: {err}")
        blockers.append(f"no reviewer challenge on disk ({os.path.basename(agg_path)}: {err})")
    else:
        counts = agg.get("counts") or {}
        print(f"   domains reported : {len(agg.get('domains_reported') or [])}/10")
        print(f"   open fatal       : {counts.get('fatal_open', '?')}")
        print(f"   open concern     : {counts.get('concern_open', '?')}")
        print(f"   plan fingerprint : {agg.get('plan_fingerprint')} "
              f"(plan now: {plan_fingerprint(plan)})")

    print("\n[3/6] Staleness watchdog")
    rc, problems, text = run_watchdog(output_dir, python_exe)
    if rc is None:
        print(f"   ⛔ {text}")
        blockers.append(text)
    else:
        verdict = {0: "pass", 1: "problems found", 2: "unconfigured — NOT a pass"}
        print(f"   exit {rc} — {verdict.get(rc, 'unknown')}")
        for line in text.strip().splitlines()[:12]:
            print(f"   | {line}")
        if rc != 0:
            fid = watchdog_failure_id(rc, problems)
            ok_ov, why = watchdog_override_status(plan, output_dir, fid)
            if ok_ov:
                print(f"   ⚠ released by {why}")
            else:
                blockers.append(
                    f"watchdog exit {rc} (failure {fid}) — fix it, or record a named "
                    f"override: --override-watchdog <decision_log_id> --reason '...'"
                    + (f". Existing override rejected: {why}" if why else ""))

    print("\n[4/6] Methodological substitutions — one decision each")
    unresolved, rejected, err = unresolved_substitutions(plan, output_dir)
    if unresolved is None:
        print(f"   ⛔ configs/manifest.json: {err} — the substitutions cannot be "
              f"listed, so none of them has been confirmed.")
        blockers.append(f"configs/manifest.json unreadable ({err}) — substitutions unknown")
    else:
        items, _ = manifest_warnings(output_dir)
        book = plan.get("substitution_decisions") or {}
        for sid, text in items:
            d = (book.get(sid) or {}).get("decision")
            mark = {"accepted": "[x]", "rejected": "[!]"}.get(d, "[ ]")
            print(f"   {mark} {sid}  {text}")
            if d:
                print(f"          -> {d}: {(book.get(sid) or {}).get('reason', '')}")
        if not items:
            print("   (none recorded)")
        if unresolved:
            blockers.append(
                f"{len(unresolved)} substitution(s) with no recorded decision: "
                f"{', '.join(s for s, _ in unresolved)}. Record each with "
                f"--accept-substitution ID:reason or --reject-substitution ID:reason.")
        if rejected:
            blockers.append(
                f"{len(rejected)} substitution(s) marked rejected "
                f"({', '.join(s for s, _ in rejected)}) — the plan still contains them. "
                f"Change the plan and re-generate the configs.")

    print("\n[5/6] Deterministic post-flight checks")
    pc, pc_err = _read_json(os.path.join(output_dir, "precheck_report_post.json"))
    if pc is None:
        print(f"   ⛔ precheck_report_post.json: {pc_err} — the deterministic checks "
              f"have not been run against these outputs.")
        blockers.append(f"no post-flight precheck report ({pc_err})")
    else:
        print(f"   {pc.get('n_blocking', '?')} blocking / {pc.get('n_warning', '?')} "
              f"warning across {(pc.get('counters') or {}).get('checks_run', '?')} check(s)")
        for issue in (pc.get("issues") or [])[:10]:
            if str(issue.get("severity", "")).lower() in ("blocking", "block"):
                print(f"   ⛔ {issue.get('check', '?')} {issue.get('step', '')}: "
                      f"{str(issue.get('message', ''))[:110]}")
        if pc.get("n_blocking"):
            blockers.append(
                f"{pc['n_blocking']} blocking finding(s) from precheck_configs.py "
                f"--stage post. These are arithmetic and set operations, not opinions.")

    print("\n[6/6] explore -> submit promotion")
    profile = plan.get("pipeline_profile")
    if profile != "submit":
        print(f"   pipeline_profile = {profile!r} — promotion gate not applicable")
    else:
        promo, exemption = verify_promotion_record(plan, output_dir)
        if promo:
            for p in promo:
                print(f"   ⛔ {p}")
            blockers.extend(promo)
        elif exemption:
            print(f"   ○ gate not applicable — {exemption}")
            record_promotion_exemption(plan, output_dir, exemption)
        else:
            rec, _ = _read_json(os.path.join(output_dir, PROMOTION_RECORD_NAME))
            print(f"   ✓ promotion reconciled under {rec.get('decision_log_id')} "
                  f"(decided after seeing outcomes: "
                  f"{rec.get('decided_after_seeing_outcomes')})")

    print("=" * 70)
    if blockers:
        print(f"⛔ {len(blockers)} blocker(s) — the manuscript will not be written:")
        for b in blockers:
            print(f"   • {b}")
        print("=" * 70)
    return blockers


def detect_existing_outputs(plan):
    """Scan output_dir for existing output files. Returns list of step_ids with existing outputs."""
    detected = []
    output_dir = plan["output_dir"]
    for step in plan["pipeline"]:
        output_base = step.get("output_file", step["id"])
        xlsx_path = os.path.join(output_dir, f"{output_base}.xlsx")
        png_path = os.path.join(output_dir, f"{output_base}.png")
        if os.path.exists(xlsx_path) or os.path.exists(png_path):
            detected.append({
                "step_id": step["id"],
                "files": [p for p in [xlsx_path, png_path] if os.path.exists(p)],
                "mtime": os.path.getmtime(xlsx_path) if os.path.exists(xlsx_path) else os.path.getmtime(png_path)
            })
    return detected


def reviewer_gate_satisfied(plan, output_dir, python_exe=None):
    """Run the reviewer-challenge gate for real. Returns (ok, reason).

    Called at the point the manuscript is about to be written, not as a graph
    edge — see the note at the call site for why the edge alone is not enough.
    """
    gates = [s for s in (plan.get("pipeline") or [])
             if s.get("skill") == "reviewer-challenge"]
    if not gates:
        return False, ("The plan has no reviewer-challenge step, so the manuscript is "
                       "not gated. Add one and list it in the manuscript step's "
                       "depends_on (references/reviewer_challenge.md).")
    script_path, _ = SKILL_SCRIPTS["reviewer-challenge"]
    script_path = os.path.expanduser(script_path)
    python_exe = python_exe or sys.executable
    for g in gates:
        cfg = os.path.join(output_dir, "configs", f"{g['id']}_config.json")
        if not os.path.exists(cfg):
            return False, (f"Reviewer-challenge step '{g['id']}' has no generated config "
                           f"({cfg}); run generate_configs.py first.")
        proc = subprocess.run([python_exe, script_path, cfg],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            first = detail[0] if detail else f"exit {proc.returncode}"
            return False, f"Reviewer-challenge gate '{g['id']}' blocked: {first}"
    return True, ""


def run_step(step, plan, plan_path, python_exe):
    """Run a single pipeline step. Returns (success, message)."""
    step_id = step["id"]
    skill = step["skill"]
    output_dir = plan["output_dir"]
    config_path = os.path.join(output_dir, "configs", f"{step_id}_config.json")
    log_path = os.path.join(output_dir, "logs", f"{step_id}.log")

    # Clear previous log
    if os.path.exists(log_path):
        os.remove(log_path)

    # ...and the previous run's QC lines from *this* script. They live in the plan
    # and therefore survive across invocations, while the blocking check below
    # scans the whole accumulated list — so a step that ever emitted
    # [QC_BLOCKING] stayed failed forever, even after the cause was fixed and it
    # re-ran cleanly. That silently broke every re-run path: selective re-runs,
    # retries, and the intended reviewer-challenge cycle of block -> fix -> pass.
    #
    # GUARDIAN_* lines are kept. They are not this script's output: biostats-
    # guardian writes them back into the same list after its own review, and
    # re-running the analysis does not re-run that review. Clearing them would
    # mean `--only <step>` silently washes a guardian block away without anyone
    # looking at the finding again — turning a deliberate hold into something a
    # re-run dissolves.
    step["qc_warnings"] = [w for w in (step.get("qc_warnings") or [])
                           if w.startswith(("[GUARDIAN_WARNING]", "[GUARDIAN_BLOCKING]"))]

    if not os.path.exists(config_path):
        return False, f"Config not found: {config_path}"

    # Which config produced this output. pipeline_state_machine.md promises a
    # warning when "file exists BUT versions don't match", and nothing on disk
    # recorded what an output was produced from, so that warning could never
    # fire. report_detection() compares this against the config on disk.
    step["config_sha256"] = file_sha256(config_path)

    # Timestamp: started
    step["started_at"] = datetime.now().isoformat()

    # Special handling for manuscript-results
    if skill == "manuscript-results":
        # Re-run the reviewer-challenge gate here rather than relying on
        # depends_on. `--only manuscript` skips dependency checking entirely, and
        # a duplicated step id resolves to whichever step was declared last, so a
        # gate that only exists as an edge in the graph can be walked around. The
        # gate is cheap and reads from disk, so checking it at the point of use
        # costs nothing and cannot be routed around.
        ok, why = reviewer_gate_satisfied(plan, output_dir)
        if not ok:
            step["completed_at"] = datetime.now().isoformat()
            print(f"[QC_BLOCKING] {why}", file=sys.stderr)
            return False, why

        script_path = os.path.expanduser(MANUSCRIPT_EXTRACT)
        if not os.path.exists(script_path):
            msg = ("manuscript-results skill not found next to research-plan "
                   "(it ships in the klaude-med plugin). Install it or skip the manuscript step.")
            step["completed_at"] = datetime.now().isoformat()
            print(f"[QC_BLOCKING] {msg}", file=sys.stderr)
            return False, msg
        success, stdout, stderr, duration = run_script(
            python_exe, script_path, config_path, log_path=log_path
        )
        append_log(log_path, "extract_data.py", stdout, stderr)
        step["runtime_seconds"] = round(duration, 1)
        step["completed_at"] = datetime.now().isoformat()
        if not success:
            return False, stderr[-500:] if stderr else "Unknown error"

        # QC warning extraction
        qc_warnings = extract_qc_warnings(stderr)
        if qc_warnings:
            step["qc_warnings"] = qc_warnings
            if any(w.startswith("[QC_BLOCKING]") for w in qc_warnings):
                return False, "Blocking QC check failed"

        return True, "Data extracted. Claude should now write the Results section."

    # Normal skills
    script_info = SKILL_SCRIPTS.get(skill)
    if not script_info:
        return False, f"Unknown skill: {skill}"

    script_path, check_flag = script_info

    # Phase 1: Check missing / preview
    success, stdout, stderr, duration = run_script(
        python_exe, script_path, config_path, check_flag=check_flag
    )
    append_log(log_path, f"{check_flag} (check phase)", stdout, stderr)

    # Record QC lines from the check phase too. They used to be discarded whenever
    # the phase failed, which hid exactly the warnings that explain the failure.
    _record_qc(step, stderr)

    if not success:
        step["completed_at"] = datetime.now().isoformat()
        return False, f"Check phase failed: {(stderr or stdout)[-500:]}"

    # Phase 2: Full run (with retry logic)
    success, stdout, stderr, duration = run_script(
        python_exe, script_path, config_path
    )
    append_log(log_path, "Full run", stdout, stderr)
    step["runtime_seconds"] = round(duration, 1)

    if not success:
        # Retry logic: retry once if not already retried
        if step.get("retry_count", 0) < 1:
            step["retry_count"] = step.get("retry_count", 0) + 1
            append_log(log_path, "Retrying after 2s sleep...", "", "")
            time.sleep(2)
            success, stdout, stderr, duration = run_script(
                python_exe, script_path, config_path
            )
            append_log(log_path, "Full run (retry)", stdout, stderr)
            step["runtime_seconds"] = round(duration, 1)

    # Timestamp: completed
    step["completed_at"] = datetime.now().isoformat()

    qc_warnings = _record_qc(step, stderr)

    if not success:
        return False, (stderr or stdout)[-500:]

    if any(w.startswith(QC_BLOCKING_PREFIXES) for w in qc_warnings):
        return False, "Blocking QC check failed"

    return True, "Success"


SKIPPABLE_FROM = ("pending", "done")


def apply_skips(plan, plan_path, skip_ids):
    """Mark steps `skipped` on an explicit user decision. Returns counts.

    `skipped` was a declared state in references/pipeline_state_machine.md that
    nothing could ever write, so "never ran" and "deliberately not run" were the
    same value on disk — which is exactly the distinction a selective re-run
    needs. Only the two transitions the state machine actually declares are
    honoured (pending -> skipped, done -> skipped); anything else is refused out
    loud rather than forced, because `error`/`blocked` carry a reason that
    overwriting would destroy.

    The runner never decides this by itself. Mid-entry detection deliberately
    does not, either (see report_detection): "the file on disk matches the
    current plan" cannot be established, so asserting it would be the more
    dangerous error.
    """
    steps = {s["id"]: s for s in plan["pipeline"]}
    marked, refused, unknown = [], [], []
    for sid in skip_ids:
        step = steps.get(sid)
        if step is None:
            unknown.append(sid)
            continue
        status = step.get("status", "pending")
        if status not in SKIPPABLE_FROM:
            refused.append((sid, status))
            continue
        step["status"] = "skipped"
        step["skipped_at"] = datetime.now().isoformat()
        marked.append(sid)
    if marked:
        save_plan(plan, plan_path)
    print(f"  --skip: marked {len(marked)} / refused {len(refused)} / "
          f"unknown {len(unknown)} / requested {len(skip_ids)}")
    for sid in marked:
        print(f"    ⊘ {sid} -> skipped")
    for sid, status in refused:
        print(f"    ! {sid} left as '{status}' — only {'/'.join(SKIPPABLE_FROM)} "
              f"may be skipped; resolve it first")
    for sid in unknown:
        print(f"    ? {sid} is not a step in this pipeline")
    return len(marked), len(refused), len(unknown)


def check_feedback_rounds(plan, override=False):
    """Enforce the feedback-round ceiling. Returns (ok, messages).

    SKILL.md:814-822 and feedback_audit_protocol.md describe a round-3 warning
    and a round-4 override, and nothing read either field. Modelled on the one
    limit that was real — max_total_steps — which works because it is read from
    the plan and therefore counts across runs rather than resetting each time.
    """
    rounds = len(plan.get("feedback_rounds") or [])
    limit = int(plan.get("max_feedback_rounds", 3) or 3)
    msgs = []
    if rounds >= limit and not override:
        msgs.append(
            f"  ⚠ Feedback round {rounds + 1} of a {limit}-round limit. Rounds this deep "
            f"usually mean the disagreement is not statistical — a face-to-face with the "
            f"advisor resolves it faster than another re-run.")
    if rounds >= limit + 1 and not override:
        msgs.append(
            f"  ⛔ {rounds} feedback rounds already recorded (limit {limit}). Continuing "
            f"needs an explicit override: re-run with --override-feedback-rounds, or "
            f"raise `max_feedback_rounds` in the plan and say why in decision_log.md.")
        return False, msgs
    if rounds >= limit and override:
        msgs.append(f"  ⚠ Feedback-round limit ({limit}) overridden at round {rounds + 1} "
                    f"by --override-feedback-rounds.")
    return True, msgs


def record_resume_decision(plan):
    """Turn "the user re-ran the command" into the checkpoint decision it is.

    A HITL checkpoint stops the run and exits; the only way past it is the user
    re-running the same command, which *is* the `continue` decision — but
    plan_template.md's `decision` field was never written and
    `consecutive_continue_count` was never incremented, so the adaptive rules in
    checkpoint_protocol.md had no input and could never fire.

    A decision Claude has already recorded (`review` / `modify` / `pause`) is not
    overwritten, and resets the counter — which is what the protocol says those
    answers mean.
    """
    if plan.get("pipeline_state") != "awaiting_review":
        return None
    checkpoints = plan.get("checkpoints") or []
    if not checkpoints:
        return None
    last = checkpoints[-1]
    # A checkpoint that stopped on unmet preconditions was never a question, so
    # re-running is not an answer to it. Counting it as a `continue` would let a
    # user grind a blocked gate into SLIM territory by repeating the command.
    if last.get("blockers"):
        last["decision"] = "blocked"
        return last
    decision = last.get("decision")
    if decision in (None, "", "continue"):
        last["decision"] = "continue"
        plan["consecutive_continue_count"] = int(plan.get("consecutive_continue_count") or 0) + 1
    else:
        plan["consecutive_continue_count"] = 0
    return last


def run_pipeline(plan_path, run_from=None, run_only=None, hitl=False, parallel=True,
                 skip_ids=None, override_feedback_rounds=False, skip_precheck=False):
    plan = load_plan(plan_path)
    validate_plan_shape(plan, plan_path)
    pipeline = plan["pipeline"]
    output_dir = plan["output_dir"]
    python_exe = sys.executable

    ok, msgs = check_feedback_rounds(plan, override=override_feedback_rounds)
    for m in msgs:
        print(m)
    if not ok:
        sys.exit(2)

    if skip_ids:
        apply_skips(plan, plan_path, skip_ids)

    resumed = record_resume_decision(plan)
    if resumed:
        print(f"  Resuming past the '{resumed.get('group_id')}' checkpoint "
              f"(decision recorded: {resumed.get('decision')}; consecutive continues: "
              f"{plan.get('consecutive_continue_count')})")
        save_plan(plan, plan_path)

    # Argument validation first, before anything expensive or anything that
    # writes. A mistyped --from used to exit 2 with a list of the real step ids;
    # once the pre-flight ran ahead of it, the same typo exited 1 with a report
    # about the dataset, and the actual mistake was never mentioned.
    step_ids = [s["id"] for s in pipeline]
    for flag, value in (("--from", run_from), ("--only", run_only)):
        if value and value not in step_ids:
            print(f"ERROR: {flag} '{value}' is not a step in this pipeline.")
            print(f"       Available: {', '.join(sorted(step_ids))}")
            sys.exit(2)

    # One fingerprint for the whole run: it is a property of the plan, not of a
    # step, and recomputing it per step would let a mid-run plan write change it.
    run_fingerprint = plan_fingerprint(plan)

    # Config provenance, on the normal path rather than only under --detect-only.
    # An output produced by a config that has since changed is stale, and the run
    # that reuses it is the one nobody is watching.
    mark_stale_steps(plan, plan_path, output_dir)

    # Deterministic pre-flight, before a single step runs. Everything it checks —
    # a column that is not in the dataset, a reference level that does not occur,
    # EPV below the floor — is cheaper to catch here than after an hour of Cox
    # models built on it.
    ok, why = run_precheck(plan_path, output_dir, "pre", python_exe, skip=skip_precheck)
    if skip_precheck:
        # An escape hatch nobody can see is not auditable. This lands in the same
        # manifest the reviewer agents and the pre-manuscript gate read, so
        # "the deterministic checks were skipped" is a fact about the run rather
        # than a line that scrolled past in a terminal.
        record_precheck_skip(plan, output_dir)
    if not ok:
        plan["pipeline_state"] = "error"
        save_plan(plan, plan_path)
        print("\n  ⛔ Pre-flight checks did not pass. No step was run — fix the above, "
              "or re-run with --skip-precheck if you intend to proceed without them.")
        sys.exit(1)

    # Ensure logs directory exists
    os.makedirs(os.path.join(output_dir, "logs"), exist_ok=True)

    # Detect existing outputs
    existing = detect_existing_outputs(plan)
    if existing:
        print(f"  Detected {len(existing)} existing output(s):")
        for item in existing:
            files_str = ", ".join(os.path.basename(f) for f in item["files"])
            print(f"    {item['step_id']}: {files_str}")
        print()

    # Topological sort
    sorted_ids = topo_sort(pipeline)
    steps_map = {s["id"]: s for s in pipeline}

    # Group steps by analysis group
    groups = group_steps_by_analysis_group(pipeline, sorted_ids, plan)

    # Safety limit tracking.
    # Seeded from the plan so the cap is cumulative across every run (initial +
    # re-runs), which is what SKILL.md Step 6 promises. Previously this was a
    # process-local counter that reset to 0 on each invocation, so the 80-step
    # ceiling could never actually be reached.
    max_total_steps = plan.get("max_total_steps", 80)
    total_steps_executed = plan.get("total_steps_executed", 0) or 0
    counter_lock = threading.Lock()

    # Determine which steps to run.
    # `reached_from` is precomputed per step from the topological order rather than
    # flipped inside the worker: under ThreadPoolExecutor the flip order is
    # nondeterministic, so a shared flag made --from behave differently run to run.
    total = len(sorted_ids)
    results = []
    hitl_paused = False

    if run_from and run_from not in sorted_ids:
        print(f"ERROR: --from '{run_from}' is not a step in this pipeline.")
        print(f"       Available: {', '.join(sorted_ids)}")
        sys.exit(2)
    if run_only and run_only not in sorted_ids:
        print(f"ERROR: --only '{run_only}' is not a step in this pipeline.")
        print(f"       Available: {', '.join(sorted_ids)}")
        sys.exit(2)

    from_position = sorted_ids.index(run_from) if run_from else 0
    step_position = {sid: pos for pos, sid in enumerate(sorted_ids)}

    # Build a step index map for progress display
    step_index = {sid: idx for idx, sid in enumerate(sorted_ids, 1)}

    def _scheduled(group):
        return any(should_run(s, run_from, run_only,
                              step_position.get(s["id"], 0) >= from_position)
                   for s in group["steps"])

    # Is a pre-manuscript MANDATORY actually going to happen on this invocation?
    # If not, any group that produces a synthesis or sensitivity comparison keeps
    # its own MANDATORY rather than inheriting a sign-off that never comes.
    gate_ahead = any(g.get("pre_checkpoint") and _scheduled(g) for g in groups)

    for group in groups:
        group_id = group["group_id"]
        group_steps = group["steps"]
        base_type = group["checkpoint_type"]
        if group.get("synthesis") and not gate_ahead:
            base_type = "MANDATORY"
        # Adaptive depth (checkpoint_protocol.md:12-31). MANDATORY groups are
        # unaffected; FULL groups drop to SLIM once the user has continued three
        # times running, with a spot check back to FULL.
        checkpoint_type, spot_check = resolve_checkpoint_type(
            base_type, plan.get("consecutive_continue_count"))

        # A group whose checkpoint belongs *before* it runs (currently only the
        # manuscript group): brief, then stop, while the decision is still worth
        # anything. Do not stop again on the run that is answering it — a
        # before-group checkpoint that re-arms on resume is an infinite wait, and
        # the resume *is* the answer (record_resume_decision wrote it down).
        # ...and only when the group actually has something scheduled. Otherwise
        # `--only flowchart`, or any run after the manuscript is written, pays for
        # the briefing (and its watchdog subprocess) to ask about work that is not
        # going to happen.
        group_will_run = _scheduled(group)

        if group.get("pre_checkpoint") and group_will_run:
            blockers = print_manuscript_briefing(plan, output_dir, python_exe,
                                                 skip_inventory=skip_precheck)
            already_answered = bool(
                resumed and resumed.get("position") == "before_group"
                and resumed.get("group_id") == group_id)
            # A MANDATORY gate that only fires under --hitl is not a gate; auto
            # mode is exactly the run with nobody watching the log. Blockers stop
            # the run in either mode, and only a clean board can be waved through
            # by a resume.
            must_stop = bool(blockers) or (hitl and not already_answered)
            if must_stop:
                checkpoint = {
                    "group": group_id, "group_id": group_id,
                    "type": checkpoint_type, "checkpoint_type": checkpoint_type,
                    "position": "before_group",
                    "decision": None,
                    "reflection_applied": False,
                    "blockers": blockers,
                    "timestamp": datetime.now().isoformat(),
                    "steps_completed": [],
                }
                plan["last_checkpoint"] = checkpoint
                plan.setdefault("checkpoints", []).append(checkpoint)
                plan["pipeline_state"] = "awaiting_review"
                save_plan(plan, plan_path)
                print(f"\n  >>> CHECKPOINT [{checkpoint_type}] before group '{group_id}' <<<")
                if blockers:
                    # Not a pause the user can answer by repeating the command.
                    print(f"  >>> BLOCKED by {len(blockers)} unmet precondition(s) above. "
                          f"Re-running changes nothing until they are resolved.")
                else:
                    print("  >>> Confirm the blocks above, then re-run the same command "
                          "to write the manuscript.")
                print()
                hitl_paused = True
                break

        # Separate independent and dependent steps within this group
        group_step_ids = {s["id"] for s in group_steps}
        independent_steps = []
        dependent_steps = []

        for step in group_steps:
            # A step is dependent within the group if any of its deps are also in the group
            intra_deps = [d for d in step.get("depends_on", []) if d in group_step_ids]
            if intra_deps:
                dependent_steps.append(step)
            else:
                independent_steps.append(step)

        def _execute_step(step):
            """Execute a single step with all checks. Returns (step_id, success, elapsed, message)."""
            nonlocal total_steps_executed

            step_id = step["id"]
            idx = step_index.get(step_id, "?")

            reached_from = step_position.get(step_id, 0) >= from_position

            if not should_run(step, run_from, run_only, reached_from):
                if step.get("status") == "done":
                    print(f"  [{idx}/{total}] {step_id:<25s} not scheduled (already done)")
                # "not_scheduled" is a message, not a status. It used to read
                # "skipped", which collided with the `skipped` step status that
                # now really exists (see apply_skips) — one word for "not run
                # this invocation" and "deliberately excluded" is how the two
                # stopped being distinguishable in the first place.
                return step_id, None, 0, "not_scheduled"

            # Check dependencies
            if not run_only:
                for dep_id in step.get("depends_on", []):
                    dep = steps_map.get(dep_id)
                    # A step held up by an upstream failure is `blocked`, not `error`:
                    # it never ran, so counting it as a failure inflates error_count and
                    # hides how many analyses actually broke. `blocked` is a declared
                    # state in references/pipeline_state_machine.md.
                    if dep and dep.get("status") in ("error", "blocked"):
                        step["status"] = "blocked"
                        step["blocked_by"] = dep_id
                        step["error_message"] = f"Dependency '{dep_id}' failed ({dep.get('status')})"
                        save_plan(plan, plan_path)
                        print(f"  [{idx}/{total}] {step_id:<25s} BLOCKED (dependency '{dep_id}' failed)")
                        return step_id, False, 0, f"Dependency '{dep_id}' failed"
                    if dep and dep.get("status") not in ("done",):
                        step["status"] = "blocked"
                        step["blocked_by"] = dep_id
                        step["error_message"] = f"Dependency '{dep_id}' not completed (status: {dep.get('status')})"
                        save_plan(plan, plan_path)
                        print(f"  [{idx}/{total}] {step_id:<25s} BLOCKED (dependency '{dep_id}' not done)")
                        return step_id, False, 0, f"Dependency '{dep_id}' not done"

            # Safety limit check
            if total_steps_executed >= max_total_steps:
                print(f"  WARNING: Reached max_total_steps limit ({max_total_steps}). Stopping.")
                return step_id, None, 0, "limit_reached"

            # Run the step
            step["status"] = "running"
            save_plan(plan, plan_path)
            print(f"  [{idx}/{total}] Running {step_id:<25s}", end="", flush=True)

            start = time.time()
            success, message = run_step(step, plan, plan_path, python_exe)
            elapsed = time.time() - start

            with counter_lock:
                total_steps_executed += 1
                plan["total_steps_executed"] = total_steps_executed

            if success:
                step["status"] = "done"
                step.pop("error_message", None)
                print(f" done ({elapsed:.1f}s)")
            else:
                step["status"] = "error"
                step["error_message"] = message
                print(f" ERROR ({elapsed:.1f}s)")

            # Every executed step, whatever it returned. A run that was abandoned
            # is precisely the kind of estimate that otherwise disappears.
            inventory, inv_err = step_estimate_inventory(step, output_dir)
            if inv_err:
                print(f"[QC_WARNING] estimate inventory unavailable for {step_id}: "
                      f"{inv_err}", file=sys.stderr)
            wrote = append_explore_ledger(output_dir, {
                "timestamp": datetime.now().isoformat(),
                "plan_fingerprint": run_fingerprint,
                "pipeline_profile": plan.get("pipeline_profile"),
                "config_sha256": step.get("config_sha256"),
                "step_id": step_id,
                "status": step["status"],
                "estimate_inventory": inventory,
                "estimate_inventory_error": inv_err,
            })
            # In the exploratory profile the ledger *is* the record — there is no
            # manuscript, no challenge and no watchdog behind it. A step whose row
            # was not written has no audit trail at all, so it cannot be reported
            # as done; the caller was previously ignoring the return value.
            if (not wrote or inv_err) and plan.get("pipeline_profile") == "explore":
                step["status"] = "error"
                step["error_message"] = (
                    f"explore ledger incomplete for this step "
                    f"({'write failed' if not wrote else inv_err}). Under "
                    f"pipeline_profile='explore' the ledger is the only record that "
                    f"this estimate was run, so an unrecorded step is not a done step.")
                print(f"[QC_BLOCKING] {step['error_message']}", file=sys.stderr)
                success = False

            save_plan(plan, plan_path)
            return step_id, success, elapsed, message

        # --- Execute independent steps (potentially in parallel) ---
        if parallel and len(independent_steps) > 1:
            print(f"\n  [Group: {group_id}] Running {len(independent_steps)} independent step(s) in parallel...")
            with ThreadPoolExecutor(max_workers=min(4, len(independent_steps))) as executor:
                futures = {
                    executor.submit(_execute_step, step): step
                    for step in independent_steps
                }
                for future in as_completed(futures):
                    step_id, success, elapsed, message = future.result()
                    if success is not None:
                        results.append((step_id, "done" if success else "error", elapsed))
                    if total_steps_executed >= max_total_steps:
                        break
        else:
            if len(group_steps) > 0:
                print(f"\n  [Group: {group_id}]")
            for step in independent_steps:
                step_id, success, elapsed, message = _execute_step(step)
                if success is not None:
                    results.append((step_id, "done" if success else "error", elapsed))
                if message == "limit_reached":
                    break

        # Check safety limit before dependent steps
        if total_steps_executed >= max_total_steps:
            print(f"  WARNING: Reached max_total_steps limit ({max_total_steps}). Stopping.")
            break

        # --- Execute dependent steps sequentially ---
        for step in dependent_steps:
            step_id, success, elapsed, message = _execute_step(step)
            if success is not None:
                results.append((step_id, "done" if success else "error", elapsed))
            if message == "limit_reached":
                break

        # Check safety limit after group
        if total_steps_executed >= max_total_steps:
            print(f"  WARNING: Reached max_total_steps limit ({max_total_steps}). Stopping.")
            break

        # HITL checkpoint.
        # This used to print the banner and then carry straight on to the next group,
        # so "hitl" mode ran the whole pipeline unattended while telling the user it
        # had paused. It now actually stops: state goes to `awaiting_review` and the
        # process returns. Re-running resumes, because completed steps are no longer
        # re-executed (see should_run).
        # A group can also demand a human even in auto mode. That is reserved for
        # conflicts the pipeline cannot resolve on the user's behalf — currently
        # only MI declared primary alongside PSM, where the two analyses answer
        # different questions and only a person can say which one the paper is
        # about. Marking such a group MANDATORY without stopping would have been
        # the same lie the hitl banner used to tell.
        halt_in_auto = bool(group.get("halt_in_auto"))
        if halt_in_auto and not hitl and results:
            print(f"\n  >>> HALT [{checkpoint_type}] after group '{group_id}' <<<")
            print(f"  >>> {group.get('halt_reason', 'a decision is required')}")

        # A group that checkpointed before it ran does not checkpoint again after.
        # Two stops around one group is how the pre-manuscript gate turned into a
        # loop: the post-group stop re-armed the pre-group one on the next resume,
        # and the run could never reach a terminal state.
        if (hitl or halt_in_auto) and results and not group.get("pre_checkpoint"):
            group_step_ids_done = [
                r[0] for r in results if r[1] == "done" and r[0] in group_step_ids
            ]
            # A SLIM checkpoint that stops the run and demands a re-run is not the
            # "one-line progress bar to reduce friction" checkpoint_protocol.md
            # describes — stopping is the whole cost. SLIM therefore reports and
            # carries on, and records its own `continue` decision because nobody
            # was asked. MANDATORY and FULL still stop.
            stops = checkpoint_type != "SLIM" or halt_in_auto
            checkpoint = {
                # plan_template.md:189-197 declares {group, type, decision,
                # reflection_applied, timestamp}; the runner wrote a different set
                # of keys, so `decision` and `reflection_applied` were never
                # written and the audit trail SKILL.md:432 promises was not on
                # disk. Both spellings are written — group_id / checkpoint_type /
                # steps_completed keep existing readers working.
                "group": group_id,
                "group_id": group_id,
                "type": checkpoint_type,
                "checkpoint_type": checkpoint_type,
                "position": "after_group",
                "decision": None if stops else "continue",
                # Set by Claude when a Stage Reflector suggestion is actually
                # applied. The runner cannot know — it does not run the reflector
                # (SKILL.md:402) — so it records `false` rather than nothing,
                # which is the difference between "not applied" and "no record".
                "reflection_applied": False,
                "timestamp": datetime.now().isoformat(),
                "steps_completed": group_step_ids_done,
            }
            if spot_check:
                checkpoint["spot_check"] = True
            plan["last_checkpoint"] = checkpoint
            # Append-only audit trail — references/plan_template.md declares
            # checkpoints[] but nothing ever wrote to it.
            plan.setdefault("checkpoints", []).append(checkpoint)
            if not stops:
                plan["consecutive_continue_count"] = int(
                    plan.get("consecutive_continue_count") or 0) + 1
                save_plan(plan, plan_path)
                print(f"  [✓] {group_id} complete "
                      f"({len(group_step_ids_done)} step(s)) → continuing "
                      f"[SLIM, {plan['consecutive_continue_count']} consecutive continues]")
                continue
            plan["pipeline_state"] = "awaiting_review"
            save_plan(plan, plan_path)
            print(f"\n  >>> CHECKPOINT [{checkpoint_type}"
                  f"{' — random spot check' if spot_check else ''}] "
                  f"after group '{group_id}' <<<")
            print(f"  >>> Completed in this group: {', '.join(group_step_ids_done) or '(none)'}")
            print(f"  >>> Review plan at: {plan_path}")
            print(f"  >>> PAUSED. Re-run the same command to continue "
                  f"(finished steps are not repeated).\n")
            hitl_paused = True
            break

    # Print summary
    print(f"\n{'='*60}")
    print("Pipeline Summary")
    print(f"{'='*60}")
    done_count = sum(1 for _, s, _ in results if s == "done")
    error_count = sum(1 for sid, s, _ in results
                      if s == "error" and steps_map[sid].get("status") == "error")
    blocked_count = sum(1 for sid, s, _ in results
                        if s == "error" and steps_map[sid].get("status") == "blocked")
    total_time = sum(t for _, _, t in results)
    print(f"  Completed: {done_count}  |  Errors: {error_count}  |  "
          f"Blocked: {blocked_count}  |  Total time: {total_time:.1f}s")
    print(f"  Steps executed: {total_steps_executed}  |  Limit: {max_total_steps}")

    if error_count > 0:
        print(f"\nFailed steps:")
        for step_id, status, _ in results:
            if status == "error" and steps_map[step_id].get("status") == "error":
                msg = steps_map[step_id].get("error_message", "Unknown error")
                print(f"  {step_id}: {msg[:100]}")
    if blocked_count > 0:
        print(f"\nBlocked steps (never ran — fix the upstream failure, then re-run):")
        for step_id, status, _ in results:
            if status == "error" and steps_map[step_id].get("status") == "blocked":
                print(f"  {step_id}: blocked by '{steps_map[step_id].get('blocked_by')}'")

    # Lift run-time methodological findings into the manifest the reviewer agents
    # read, before any terminal state is written — a finding that only exists in
    # the plan is a finding domain 5 will never see.
    propagate_runtime_warnings(plan, output_dir)

    # Deterministic post-flight: the checks that need outputs (reported estimates
    # vs the flowchart N, PSM direction, success criteria). Reported, not fatal —
    # the numbers already exist, and the decision about them belongs at the
    # pre-manuscript gate, which reads the same report.
    if not hitl_paused:
        ok_post, _ = run_precheck(plan_path, output_dir, "post", python_exe,
                                  skip=skip_precheck)
        if not ok_post:
            print("  ⛔ Post-flight checks reported blocking problems. The outputs "
                  "exist but should not be written up until these are resolved.")
        # Ordered immediately after: C7 reads what this writes, and the two are
        # one gate rather than two things that happen to have been run.
        run_estimate_inventory(output_dir, python_exe, skip=skip_precheck)

    # Persist a terminal pipeline_state so a resuming session can tell what happened.
    # `awaiting_review` is set at the HITL checkpoint and must not be overwritten.
    if not hitl_paused:
        remaining = [s for s in pipeline
                     if s.get("status") in ("pending", "needs_rerun", "running")]
        if remaining:
            plan["pipeline_state"] = "paused"
        elif error_count or blocked_count:
            plan["pipeline_state"] = "error"
        else:
            plan["pipeline_state"] = "completed"
            # SKILL.md Step 9's deliverable, emitted at the moment it becomes
            # true rather than transcribed by hand later.
            emit_rerun_script(plan, output_dir)
        save_plan(plan, plan_path)
    print()


def report_detection(plan_path):
    """--detect-only: report what already exists and what would run. Executes nothing.

    Deliberately does NOT mark anything as skipped. The manifest carries no plan
    version or config hash, so "this file matches the current plan" cannot be
    established — claiming it would be the more dangerous error. Steps are only
    ever skipped on the basis of their recorded `status`, which the runner owns.
    """
    plan = load_plan(plan_path)
    validate_plan_shape(plan, plan_path)
    detected = {d["step_id"]: d for d in detect_existing_outputs(plan)}
    pipeline = plan["pipeline"]

    print(f"\n━━━ Mid-Entry Detection ━━━")
    print(f"Plan: {plan_path}")
    print(f"Output dir: {plan['output_dir']}\n")

    would_run = []
    for step in pipeline:
        sid = step["id"]
        status = step.get("status", "pending")
        runs = status in ("pending", "needs_rerun", "error", "blocked")
        if runs:
            would_run.append(sid)
        mark = "✓" if not runs else "✗"
        files = detected.get(sid, {}).get("files", [])
        note = f"{len(files)} output file(s) on disk" if files else "no output on disk"
        print(f"  {mark} {sid:<25s} status={status:<12s} {note}")

    print(f"\n  Recorded complete: {len(pipeline) - len(would_run)}/{len(pipeline)}")
    print(f"  Would run:         {len(would_run)}/{len(pipeline)}"
          f"{' → ' + ', '.join(would_run) if would_run else ''}")

    # pipeline_state_machine.md:119 — "file exists BUT versions don't match →
    # warn user". Nothing recorded what config produced an output, so the
    # comparison had nothing to compare and the warning could not exist. run_step
    # now stamps each step with the SHA-256 of the config it ran, which is the
    # comparison that actually matters: the plan version can stay put while a
    # covariate is added underneath it.
    output_dir = plan["output_dir"]
    drifted, unstamped = [], []
    for step in pipeline:
        if step["id"] not in detected:
            continue
        recorded = step.get("config_sha256")
        cfg = os.path.join(output_dir, "configs", f"{step['id']}_config.json")
        if not recorded:
            unstamped.append(step["id"])
        elif os.path.exists(cfg) and file_sha256(cfg) != recorded:
            drifted.append(step["id"])
    if drifted:
        print(f"\n  ⚠ Output on disk was produced by a different config: "
              f"{', '.join(drifted)}")
        print("    The config has changed since that output was written. Re-run those")
        print("    steps, or the numbers belong to a specification nobody is reading.")
    if unstamped:
        print(f"\n  · No config hash recorded for {len(unstamped)} step(s) with output on "
              f"disk ({', '.join(unstamped)}) — written before hashes were recorded, so "
              f"whether they match the current config cannot be established here.")

    orphans = [sid for sid in detected
               if next(s for s in pipeline if s["id"] == sid).get("status") != "done"]
    if orphans:
        print(f"\n  ⚠ Output files exist for step(s) not recorded as done: {', '.join(orphans)}")
        print(f"    These will be overwritten on the next run. If they are the results you")
        print(f"    want to keep, back them up or set status=\"done\" in the plan first.")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


RERUN_TEMPLATE = """#!/bin/bash
# Auto-generated by run_pipeline.py --emit-rerun. Re-emit rather than hand-edit.
# Usage: bash rerun.sh [--from STEP_ID] [--only STEP_ID] [--hitl] [--no-parallel]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/scripts/run_pipeline.py" "$SCRIPT_DIR/configs/research_plan.json" "$@"
"""


def emit_rerun_script(plan, output_dir):
    """Write <OUTPUT_DIR>/rerun.sh. Returns its path.

    SKILL.md Step 9 prints this file's contents and asks the user to be told they
    can re-run "without Claude" — while leaving the file itself to be typed out by
    hand each time, which is the one part a person gets wrong. Generating it also
    means the paths can be checked instead of asserted.
    """
    path = os.path.join(output_dir, "rerun.sh")
    with open(path, "w", encoding="utf-8") as f:
        f.write(RERUN_TEMPLATE)
    os.chmod(path, 0o755)

    # The script points at copies that Step 9 makes; say so rather than emit a
    # file that fails on first use.
    missing = [rel for rel in ("scripts/run_pipeline.py", "configs/research_plan.json")
               if not os.path.exists(os.path.join(output_dir, rel))]
    print(f"  Wrote {path}")
    if missing:
        print(f"  ⚠ Not runnable yet — {', '.join(missing)} missing under {output_dir}. "
              f"Complete Step 9 (copy scripts/ and configs/) first.")
    return path


def main():
    parser = argparse.ArgumentParser(description="Run the research analysis pipeline")
    parser.add_argument("plan_path", help="Path to research_plan.json")
    parser.add_argument("--from", dest="run_from", help="Start from this step ID")
    parser.add_argument("--only", dest="run_only", help="Run only this step ID")
    parser.add_argument("--hitl", action="store_true", help="Enable HITL mode (pause after each analysis group)")
    parser.add_argument("--no-parallel", action="store_true", help="Disable parallel execution")
    parser.add_argument("--detect-only", action="store_true",
                        help="Report existing outputs and what would run; execute nothing")
    parser.add_argument("--skip", dest="skip",
                        help="Comma-separated step IDs to mark 'skipped' (an explicit "
                             "user decision; only pending/done steps may be skipped)")
    parser.add_argument("--override-feedback-rounds", action="store_true",
                        help="Continue past max_feedback_rounds (record why in decision_log.md)")
    parser.add_argument("--emit-rerun", action="store_true",
                        help="Write <OUTPUT_DIR>/rerun.sh and exit; execute nothing")
    parser.add_argument("--list-substitutions", action="store_true",
                        help="List every methodological substitution with its id and "
                             "recorded decision, then exit")
    parser.add_argument("--accept-substitution", action="append", metavar="ID:REASON",
                        help="Record a substitution as accepted, with a reason "
                             "(repeatable). The reason is mandatory.")
    parser.add_argument("--reject-substitution", action="append", metavar="ID:REASON",
                        help="Record a substitution as rejected, with a reason "
                             "(repeatable). A rejected substitution blocks the "
                             "manuscript until the plan stops making it.")
    parser.add_argument("--override-watchdog", metavar="DECISION_LOG_ID",
                        help="Release the CURRENT watchdog failure, naming the "
                             "decision_log.md row that carries the reason. The row "
                             "must exist and must name the failure id; the override "
                             "lapses as soon as the failure changes.")
    parser.add_argument("--reason", help="Reason accompanying --override-watchdog")
    parser.add_argument("--skip-precheck", action="store_true",
                        help="Do not run precheck_configs.py. The deterministic checks "
                             "are the cheap half of the QA; skipping them is a choice, "
                             "and the log says it was made.")
    args = parser.parse_args()

    if not os.path.exists(args.plan_path):
        print(f"Error: File not found: {args.plan_path}")
        sys.exit(1)

    # Before any banner, any subcommand, any work. Printing "Research Plan
    # Pipeline Runner" above a fatal plan error reads as though the run started.
    validate_plan_shape(load_plan(args.plan_path), args.plan_path)

    if args.emit_rerun:
        plan = load_plan(args.plan_path)
        validate_plan_shape(plan, args.plan_path)
        emit_rerun_script(plan, plan["output_dir"])
        return

    if args.list_substitutions:
        plan = load_plan(args.plan_path)
        validate_plan_shape(plan, args.plan_path)
        items, err = manifest_warnings(plan["output_dir"])
        if items is None:
            print(f"Cannot read configs/manifest.json: {err}")
            sys.exit(2)
        book = plan.get("substitution_decisions") or {}
        print(f"{len(items)} methodological substitution(s):")
        for sid, text in items:
            d = book.get(sid) or {}
            print(f"  {sid}  {d.get('decision', 'UNDECIDED'):<10s} {text}")
            if d.get("reason"):
                print(f"            reason: {d['reason']}  ({d.get('timestamp')})")
        return

    if args.accept_substitution or args.reject_substitution or args.override_watchdog:
        plan = load_plan(args.plan_path)
        validate_plan_shape(plan, args.plan_path)
        known = dict(manifest_warnings(plan["output_dir"])[0] or [])
        recorded, refused = 0, 0
        for decision, raw_list in (("accepted", args.accept_substitution or []),
                                   ("rejected", args.reject_substitution or [])):
            for raw in raw_list:
                sid, _, reason = raw.partition(":")
                sid = sid.strip()
                if sid not in known:
                    print(f"  ? {sid} is not a substitution in this manifest "
                          f"(--list-substitutions shows the ids)")
                    refused += 1
                    continue
                ok, msg = record_substitution_decision(plan, args.plan_path, sid,
                                                       decision, reason)
                print(f"  {'✓' if ok else '!'} {msg}")
                recorded += 1 if ok else 0
                refused += 0 if ok else 1
        if args.override_watchdog:
            ok, msg = record_watchdog_override(
                plan, args.plan_path, plan["output_dir"], args.override_watchdog,
                args.reason)
            print(f"  {'✓' if ok else '⛔'} {msg}")
            recorded += 1 if ok else 0
            refused += 0 if ok else 1
        total = len(args.accept_substitution or []) + len(args.reject_substitution or []) \
            + (1 if args.override_watchdog else 0)
        print(f"  recorded {recorded} / refused {refused} / requested {total}")
        if refused:
            sys.exit(2)
        return

    if args.detect_only:
        report_detection(args.plan_path)
        return

    print(f"\nResearch Plan Pipeline Runner")
    print(f"Plan: {args.plan_path}")
    if args.run_from:
        print(f"Starting from: {args.run_from}")
    if args.run_only:
        print(f"Running only: {args.run_only}")
    if args.hitl:
        print(f"HITL mode: enabled")
    if args.no_parallel:
        print(f"Parallel execution: disabled")
    print()

    run_pipeline(
        args.plan_path,
        run_from=args.run_from,
        run_only=args.run_only,
        hitl=args.hitl,
        parallel=not args.no_parallel,
        skip_ids=[s.strip() for s in args.skip.split(",") if s.strip()] if args.skip else None,
        skip_precheck=args.skip_precheck,
        override_feedback_rounds=args.override_feedback_rounds,
    )


if __name__ == "__main__":
    main()
