#!/usr/bin/env python3
r"""
Plan-level statistical routing audit — the gap that hash equality cannot cover.

Why this exists
---------------
`script_hashes.py` proves the pipeline's code is byte-identical to the shipped
version. `test_routes_synthetic.py` proves the shipped code routes its own canned
fixtures correctly. Neither says anything about *this project*: the shipped script
can be untouched and the fixtures green while the generated config for this study
drops a pre-specified adjuster, or sends a competing-risk question into a plain Cox.
The deleted Role 2 auditor caught that class because it read the plan and the config
together (its own worked example was "missing adjust=true covariate = CODE-005").

So this check is deliberately independent of script drift: it compares what the
**plan declares** against what the **configs actually ask for**, and it is
deterministic — no LLM needed for any of it.

Contract
--------
  python plan_routing_audit.py --plan research_plan.json [--configs DIR] \
      [--json OUT] [--quiet]

Exit 0 = no blocking findings.  Exit 1 = blocking findings.
Exit 2 = the audit could not run (plan unreadable / no configs found). Never a pass:
         "we could not check the routing" is not "the routing is fine".

Anything this script cannot determine is reported as a WARNING naming the missing
field — silence is never used to mean "passed".
"""

import argparse
import glob
import json
import os
import sys
import uuid
from datetime import datetime, timezone

# Bumped when the report shape changes in a way a consumer has to notice.
REPORT_SCHEMA = "plan_routing_audit/1"

TIME_TO_EVENT_TYPES = ("time_to_event", "competing_risk")

# Where each skill's config keeps the covariate/variable set, and how strictly the
# plan's adjustment set has to appear in it.
#   "block" - the model is an adjusted estimate; a missing adjuster changes the number
#   "warn"  - descriptive output; a missing variable is a reporting gap, not a wrong estimate
COVARIATE_CONTRACT = {
    "multivariate-interaction": ("sections", "block"),
    "univariate-forest": ("sections", "block"),
    "psm-matching": ("matching_variables", "block"),
    "table1": ("sections", "warn"),
}

# Skills that declare a model family and must agree with the outcome's type.
MODEL_FAMILY_SKILLS = ("multivariate-interaction", "univariate-forest")


def clear_stale_output(path):
    """Delete the report before any work. See ph_remedy_gate.py for the argument:
    a fixed output path plus a killed run means last run's verdict is read as this
    run's. Absent is blocking everywhere in this layer; stale is not."""
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"[QC_BLOCKING] could not remove the previous report at {path} "
              f"({type(e).__name__}: {e}); refusing to run.", file=sys.stderr)
        sys.exit(2)


def write_json_atomic(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def plan_fingerprint_of(plan):
    """(fingerprint, error) via reviewer_challenge, so the two cannot disagree."""
    rc_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "research-plan", "scripts", "reviewer_challenge.py")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_rc_fp", rc_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.plan_fingerprint(plan), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def norm_outcome_type(t):
    if t is None:
        return None
    s = str(t).strip().lower().replace("-", "_")
    if s in ("competing_risk", "competingrisk"):
        return "competing_risk"
    if s in ("time_to_event", "timetoevent", "survival"):
        return "time_to_event"
    if s in ("binary", "logistic", "dichotomous"):
        return "binary"
    return s


def iter_outcomes(plan):
    """Yield outcome dicts regardless of whether `outcomes` is a dict or a list."""
    oc = plan.get("outcomes")
    if isinstance(oc, dict):
        if oc.get("primary"):
            yield oc["primary"]
        for s in oc.get("secondary") or []:
            yield s
    elif isinstance(oc, list):
        for s in oc:
            yield s


def find_outcome(plan, outcome_id):
    for o in iter_outcomes(plan):
        if o.get("id") == outcome_id:
            return o
    return None


def config_columns(config, container_key):
    """Collect declared variable columns out of a sections-style container."""
    cols = []
    for group in config.get(container_key) or []:
        for var in group.get("variables") or []:
            if var.get("column"):
                cols.append(var["column"])
    return cols


class Findings:
    def __init__(self):
        self.items = []

    def add(self, check_id, severity, message, evidence=None, suggestion=None):
        self.items.append({
            "check_id": check_id,
            "severity": severity,
            "message": message,
            "evidence": evidence or {},
            "suggestion": suggestion or "",
        })

    def blocking(self):
        return [i for i in self.items if i["severity"] == "block"]

    def warnings(self):
        return [i for i in self.items if i["severity"] == "warn"]


def adjustment_set(plan):
    """Covariates the plan says belong in adjusted models.

    `adjust: false` is an explicit opt-out and is honoured; a covariate with no
    `adjust` key counts as an adjuster, because that is how the generator builds
    its sections (every covariate goes in).
    """
    declared, opted_out = [], []
    for cov in plan.get("covariates") or []:
        col = cov.get("column")
        if not col:
            continue
        if cov.get("adjust") is False:
            opted_out.append(col)
        else:
            declared.append(col)
    return declared, opted_out


def audit(plan, configs_dir, findings):
    steps = plan.get("pipeline") or []
    if not steps:
        findings.add("PR-000", "warn",
                     "plan 沒有 pipeline[]，無法比對 routing。",
                     {"plan_key": "pipeline"},
                     "確認這份 plan 是否已跑過 generate_configs.py。")
        return 0

    declared, opted_out = adjustment_set(plan)
    if not declared:
        findings.add("PR-000", "warn",
                     "plan 沒有 covariates[]（或全部 adjust=false），跳過 adjuster 比對。",
                     {"plan_key": "covariates"})

    n_checked = 0
    for step in steps:
        step_id = step.get("id")
        skill = step.get("skill")
        if not step_id or not skill:
            findings.add("PR-000", "warn",
                         f"pipeline step 缺 id 或 skill，無法比對：{step!r}")
            continue
        if step.get("status") == "skipped":
            continue

        matches = glob.glob(os.path.join(configs_dir, f"{step_id}_config.json"))
        if not matches:
            findings.add("PR-000", "warn",
                         f"找不到 step '{step_id}'（{skill}）的 config，無法比對其 routing。",
                         {"expected": os.path.join(configs_dir, f"{step_id}_config.json")},
                         "先跑 generate_configs.py，或確認 --configs 指到正確目錄。")
            continue
        with open(matches[0], "r", encoding="utf-8") as f:
            config = json.load(f)
        n_checked += 1
        ptr = os.path.basename(matches[0])

        # ── PR-001 the pre-specified adjustment set actually reaches the model ──
        contract = COVARIATE_CONTRACT.get(skill)
        if contract and declared:
            container, severity = contract
            present = set(config_columns(config, container))
            # The grouping/exposure column is added as a main effect by the script,
            # so it counts as present even when it is not in `sections`.
            grp = ((config.get("grouping") or {}).get("column")
                   or (plan.get("grouping") or {}).get("column"))
            if grp:
                present.add(grp)
            step_excluded = set(step.get("exclude_covariates") or [])
            missing = [c for c in declared if c not in present and c not in step_excluded]
            if missing:
                findings.add(
                    "PR-001", severity,
                    f"step '{step_id}'（{skill}）漏掉 plan 事前指定的共變項：{', '.join(missing)}。"
                    f"腳本位元組正確也救不了這個——輸出的是一個校正不足的估計值。",
                    {"config": f"{ptr}$.{container}", "missing": missing,
                     "declared_n": len(declared), "present_n": len(present)},
                    "把遺漏的共變項加回 config（或在 plan 標 adjust=false / step 標 "
                    "exclude_covariates 並在 decision_log.md 說明理由），然後重跑該 step。")
            if step_excluded:
                findings.add(
                    "PR-001", "warn",
                    f"step '{step_id}' 用 exclude_covariates 排除了 "
                    f"{', '.join(sorted(step_excluded))}；這是宣告過的例外，但理由必須在 "
                    f"decision_log.md 找得到。",
                    {"config": ptr, "excluded": sorted(step_excluded)})
            extra = [c for c in present
                     if c not in declared and c not in opted_out and c != grp]
            if extra:
                findings.add(
                    "PR-001", "warn",
                    f"step '{step_id}' 的 config 含 plan 沒宣告的變項：{', '.join(sorted(extra))}"
                    f"（silent scope change）。",
                    {"config": f"{ptr}$.{container}", "undeclared": sorted(extra)})

        # ── PR-002 outcome type ↔ model family ↔ column wiring ────────────────
        outcome_id = step.get("outcome")
        outcome = find_outcome(plan, outcome_id) if outcome_id else None
        if outcome_id and outcome is None:
            findings.add("PR-002", "block",
                         f"step '{step_id}' 指向 plan 裡不存在的 outcome '{outcome_id}'。",
                         {"config": ptr, "outcome": outcome_id})
        elif outcome is not None and skill in MODEL_FAMILY_SKILLS:
            otype = norm_outcome_type(outcome.get("type"))
            atype = config.get("analysis_type")
            if otype is None:
                findings.add("PR-002", "warn",
                             f"outcome '{outcome_id}' 沒有 type 欄位，無法驗證 model family。",
                             {"plan_key": f"outcomes[{outcome_id}].type"})
            elif otype in TIME_TO_EVENT_TYPES and atype != "cox":
                findings.add("PR-002", "block",
                             f"step '{step_id}': outcome type='{otype}'（time-to-event）"
                             f"卻用 analysis_type='{atype}'。時間結構被丟掉，估的不是同一個量。",
                             {"config": f"{ptr}$.analysis_type", "outcome_type": otype},
                             "把 analysis_type 改成 'cox'，或改用適合該 outcome 的 skill。")
            elif otype == "binary" and atype != "logistic":
                findings.add("PR-002", "block",
                             f"step '{step_id}': outcome type='binary' 卻用 "
                             f"analysis_type='{atype}'。",
                             {"config": f"{ptr}$.analysis_type", "outcome_type": otype})
            elif atype == "cox":
                cs = config.get("cox_settings") or {}
                for key, plan_key in (("time_column", "time_column"),
                                      ("event_column", "event_column")):
                    want, got = outcome.get(plan_key), cs.get(key)
                    if want and got and want != got:
                        findings.add("PR-002", "block",
                                     f"step '{step_id}': cox_settings.{key}='{got}' 與 plan 的 "
                                     f"outcome '{outcome_id}'.{plan_key}='{want}' 不符。"
                                     f"分析的是另一個結局。",
                                     {"config": f"{ptr}$.cox_settings.{key}",
                                      "plan": want, "config_value": got})
            elif atype == "logistic":
                got = (config.get("logistic_settings") or {}).get("outcome_column")
                want = outcome.get("event_column") or outcome.get("outcome_column")
                if want and got and want != got:
                    findings.add("PR-002", "block",
                                 f"step '{step_id}': logistic outcome_column='{got}' 與 plan 的 "
                                 f"'{want}' 不符。",
                                 {"config": f"{ptr}$.logistic_settings.outcome_column",
                                  "plan": want, "config_value": got})

        # ── PR-004 grouping / exposure integrity ──────────────────────────────
        plan_grp = plan.get("grouping") or {}
        cfg_grp = config.get("grouping") or {}
        if plan_grp.get("column") and cfg_grp.get("column"):
            if plan_grp["column"] != cfg_grp["column"]:
                findings.add("PR-004", "block",
                             f"step '{step_id}': grouping column='{cfg_grp['column']}' 與 plan 的 "
                             f"'{plan_grp['column']}' 不符——比較的不是同一個曝險。",
                             {"config": f"{ptr}$.grouping.column", "plan": plan_grp["column"]})
            else:
                pv = [g.get("value") for g in (plan_grp.get("groups") or [])]
                cv = [g.get("value") for g in (cfg_grp.get("groups") or [])]
                if pv and cv and pv != cv:
                    findings.add("PR-004", "block",
                                 f"step '{step_id}': grouping 的組別順序/值 {cv} 與 plan 的 {pv} 不符。"
                                 f"參照組換掉會讓效應量方向反過來。",
                                 {"config": f"{ptr}$.grouping.groups", "plan": pv,
                                  "config_value": cv})

    # ── PR-003 competing-risk routing (plan level, once) ──────────────────────
    skills_in_pipeline = {s.get("skill") for s in steps if s.get("status") != "skipped"}
    for o in iter_outcomes(plan):
        if norm_outcome_type(o.get("type")) == "competing_risk":
            oid = o.get("id")
            has_cr = any(s.get("skill") == "competing-risk" and s.get("outcome") == oid
                         and s.get("status") != "skipped" for s in steps)
            if not has_cr:
                findings.add("PR-003", "block",
                             f"outcome '{oid}' 宣告為 competing_risk，但 pipeline 沒有對應的 "
                             f"competing-risk step（現有 skills: {sorted(skills_in_pipeline)}）。"
                             f"只用 cause-specific Cox / KM 會高估絕對風險。",
                             {"plan": f"outcomes[{oid}].type", "value": "competing_risk"},
                             "加一個 competing-risk step，或在 plan 說明為何 cause-specific "
                             "估計就是這裡要的量（並寫進 decision_log.md）。")
    return n_checked


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--configs", default=None,
                    help="config 目錄（預設 <plan 目錄>/configs，再退到 <output_dir>/configs）")
    ap.add_argument("--json", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = uuid.uuid4().hex[:12]
    clear_stale_output(args.json)

    if not os.path.exists(args.plan):
        print(f"[QC_BLOCKING] plan not found: {args.plan}. Routing was not audited — "
              f"that is not the same as routing being correct.", file=sys.stderr)
        sys.exit(2)
    with open(args.plan, "r", encoding="utf-8") as f:
        plan = json.load(f)

    candidates = []
    if args.configs:
        candidates.append(args.configs)
    else:
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(args.plan)), "configs"))
        if plan.get("output_dir"):
            candidates.append(os.path.join(plan["output_dir"], "configs"))
    configs_dir = next((c for c in candidates if os.path.isdir(c)), None)
    if configs_dir is None:
        print(f"[QC_BLOCKING] no config directory found (tried: {candidates}). "
              f"Routing was not audited.", file=sys.stderr)
        sys.exit(2)

    findings = Findings()
    n_checked = audit(plan, configs_dir, findings)

    fingerprint, fp_error = plan_fingerprint_of(plan)
    if fingerprint is None:
        print(f"[QC_WARNING] plan fingerprint could not be computed ({fp_error}); a "
              f"consumer must treat plan_fingerprint=null as unverifiable, not a pass.",
              file=sys.stderr)
    result = {
        "schema": REPORT_SCHEMA,
        "tool": "biostats-guardian/scripts/plan_routing_audit.py",
        "run_id": run_id,
        "started_at": started_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": plan.get("version"),
        "plan_fingerprint": fingerprint,
        "plan_fingerprint_error": fp_error,
        "plan": os.path.abspath(args.plan),
        "configs_dir": os.path.abspath(configs_dir),
        "n_steps_checked": n_checked,
        "n_blocking": len(findings.blocking()),
        "n_warning": len(findings.warnings()),
        "exit_code": 1 if findings.blocking() else 0,
        "findings": findings.items,
    }
    if args.json:
        write_json_atomic(args.json, result)

    for i in findings.warnings():
        print(f"[QC_WARNING] {i['check_id']} {i['message']}", file=sys.stderr)
    for i in findings.blocking():
        print(f"[QC_BLOCKING] {i['check_id']} {i['message']}", file=sys.stderr)

    if not args.quiet:
        if not findings.items:
            print(f"plan routing 稽核通過：{n_checked} 個 step 的 config 與 plan 宣告一致")
        else:
            print(f"plan routing 稽核：{n_checked} 個 step，"
                  f"{len(findings.blocking())} 個阻擋、{len(findings.warnings())} 個警告")

    if n_checked == 0:
        print("[QC_BLOCKING] PR-000 沒有任何 step 被比對到，routing 等於沒稽核。",
              file=sys.stderr)
        sys.exit(2)
    sys.exit(1 if findings.blocking() else 0)


if __name__ == "__main__":
    main()
