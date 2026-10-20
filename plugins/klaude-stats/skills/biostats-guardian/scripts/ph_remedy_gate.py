#!/usr/bin/env python3
r"""
PH remedy artifact gate — "declared" must become "has been run" before a manuscript.

Why this exists
---------------
`multivariate-interaction` downgrades a proportional-hazards violation from blocking
to a warning when the plan declares a `ph_violation_remedy`. That downgrade is only
defensible if something later checks the remedy was actually performed. Nothing did:
the skill's own warning says the Sheet 1 HRs "must not be presented as the primary
estimate until the '{remedy}' analysis has been run", and the words "has been run"
had no program behind them. `disclose` was a zero-cost exit — one warning and past.

So this is the deterministic half of RES-015, run at the manuscript gate (2026-08-12
adjudication, dispute 5). It does NOT block the multivariate step itself — the split
matters: the step may legitimately produce an unremediated table as an intermediate;
what may not happen is that table reaching the manuscript unaccompanied.

Contract
--------
  python ph_remedy_gate.py --plan research_plan.json [--output-dir DIR]
      [--decision-log PATH] [--json OUT] [--quiet]

Exit 0 = every violated Cox step has its declared remedy evidenced.
Exit 1 = at least one blocking finding (manuscript must not proceed).
Exit 2 = the gate could not run. Never a pass.

Report provenance (schema `ph_remedy_gate/1`)
---------------------------------------------
The `--json` path is fixed and the consumer does not clear it, so a file sitting
there proves nothing on its own: an older build, a SIGKILL, or an exit on an
unexpected code all leave last run's "pass" in place to be read as this run's.
Two mechanisms, both needed:

  * the report is **deleted before any work starts** and written **atomically** at
    the end, so what is on disk is this run's complete result or nothing at all —
    and "nothing at all" is already blocking everywhere in this layer;
  * every report carries `schema`, `run_id`, `started_at`, `generated_at`,
    `version`, `plan_fingerprint` (delegated to `reviewer_challenge.plan_fingerprint`
    so the two cannot disagree), `plan`, `output_dir` and `exit_code`.

A consumer MUST check that `plan_fingerprint` matches the plan it is about to gate,
and MUST treat `plan_fingerprint: null` (recorded with `plan_fingerprint_error`) as
unverifiable rather than as a pass. Provenance in the file is only half the fix —
the consumer has to verify it, or this is decoration.

Remedy → what counts as evidence
  stratify / time_varying / rmst : a step of that kind whose declared output exists
                                   AND an evidence sidecar `<stem>_remedy.json` bound
                                   to that workbook (name + sha256) whose contents are
                                   cross-checked against the very `*_ph_test.json`
                                   that triggered the remedy. What is checked differs
                                   by remedy, because the ways they go wrong differ:
                                     stratify     — the strata cover the covariates
                                                    that actually violated;
                                     time_varying — the time-varying terms cover them,
                                                    AND the windows came from the plan;
                                     rmst         — tau came from the plan (it is the
                                                    only thing this remedy has to
                                                    defend, since the estimate is an
                                                    integral up to tau).
                                   Without a sidecar, all three fall back to "a file
                                   exists". See "Two kinds of green light" below.
  disclose                       : `ph_disclose_decision_id` in the plan AND that ID
                                   present in decision_log.md. A disclosure with no
                                   permanent decision ID is not a disclosure.

TWO KINDS OF GREEN LIGHT, AND THEY ARE NOT THE SAME
---------------------------------------------------
**Verified.** The remedy step wrote an evidence sidecar (schema
`ph_remedy_evidence/1`) and the gate checked it: that the sidecar describes *this*
workbook and not a leftover from another run (basename + sha256, the same binding the
PSM contrast sidecar uses), that the remedy it reports is the remedy that was
declared, that its status is `computed` rather than "could not" or "not needed", and
— the check that makes this worth doing — that it addresses the violation that
actually happened. A stratified model that stratified on something other than the
covariate the Schoenfeld test flagged is not a remedy for that violation, and until
this check existed nothing said so.

Cross-checking against the PH artifact rather than re-reading the workbook is
deliberate. The sidecar is the single contract; parsing the .xlsx as well would be a
second definition of the same facts, and two definitions of one fact drift. What the
sha256 binding buys is that the sidecar cannot be describing a different table; what
it does not buy is protection against someone deliberately forging both, which no
file test can give.

**Unverified.** No sidecar — a remedy with no shipped generator, or an output built
by hand before the sidecar existed. Then this falls back to what it could always do:
check that *a file* is there. Name a step `stratified_os`, have it write anything at
all, and that check is satisfied. So that path still records a methodological
substitution `ph_remedy_declared_not_computed` in `configs/manifest.json`, and the
pre-manuscript gate demands a named accept/reject with a reason — the author writes
down that they ran the remedy, where the output is, and by what method.

Both paths exit 0. The difference is in `verified_remedies` and
`attestations_unverified` in the report, in the manifest, and in what the pass
message says — and the message says which one happened, in those words, because a
green light that reads the same for both is how the weaker one gets mistaken for the
stronger.

The old split still holds for the unverified path: a script can prove the file is
there; only a person can take responsibility for what is in it. Same shape as the
STROBE sign-off.
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone

# Bumped to /2 when the gate stopped being a pure file-existence test: a pass can
# now mean either "verified against the producer's evidence" or "a file exists",
# and a consumer that treats those as the same thing is reading it wrong.
REPORT_SCHEMA = "ph_remedy_gate/2"

# What research-plan/scripts/ph_stratified.py writes. Kept as a literal for the
# same reason generate_configs duplicates PH_REMEDIES: this gate must run without
# importing a module that needs lifelines.
EVIDENCE_SCHEMA_PREFIX = "ph_remedy_evidence/"

REMEDIES_NEEDING_STEP = ("stratify", "time_varying", "rmst")
ALL_REMEDIES = REMEDIES_NEEDING_STEP + ("disclose",)

# Step-id / skill fragments that would evidence each remedy, if such a step exists.
REMEDY_STEP_HINTS = {
    "stratify": ("stratif",),
    "time_varying": ("time_varying", "timevarying", "extcox", "extended_cox", "tvc"),
    "rmst": ("rmst",),
}

# All three now have shipped generators (generate_configs._REMEDY_STEPS,
# 2026-08-12), so nobody is sent to build a step by hand any more. The set is kept
# rather than deleted because the message it drives — "this remedy has no
# generator, you have to build the step yourself" — is the right thing to say the
# next time a remedy is added to the vocabulary before its generator exists, and
# rebuilding that path under pressure is how a user ends up at a door with no exit.
REMEDIES_WITHOUT_SHIPPED_STEP = set()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clear_stale_output(path):
    """Delete the report before doing any work.

    The output path is fixed and the consumer does not delete it, so a previous
    run's file sitting on disk is indistinguishable from this run's — and if this
    process is killed, is an older build, or dies on an unexpected code, the
    consumer reads last time's findings as though the PH audit had just passed.
    Removing it up front makes the failure mode "the file is absent" instead of
    "the file is wrong", and absent is already treated as blocking everywhere in
    this layer. Combined with the atomic write at the end, the file on disk is
    either this run's complete result or nothing.
    """
    if not path:
        return
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        # Cannot guarantee the file is not stale -> say so and fail closed.
        print(f"[QC_BLOCKING] could not remove the previous report at {path} "
              f"({type(e).__name__}: {e}); refusing to run, because a stale report "
              f"left in place reads as a pass.", file=sys.stderr)
        sys.exit(2)


def write_json_atomic(path, payload):
    """Write via a temp file + rename so a killed run cannot leave a partial report."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def record_manifest_substitution(output_dir, entry, label):
    """Append one methodological substitution to configs/manifest.json.

    Shape and de-duplication key (`kind`) mirror run_pipeline's
    `_append_manifest_warning`, so the pre-manuscript gate picks it up with no
    change on that side: it lists every manifest warning as a substitution that
    must be individually accepted or rejected with a reason, and an unanswered one
    blocks the manuscript. Writing at runtime follows the existing precedent of
    `record_promotion_exemption` / `record_precheck_skip`.

    Returns True when the entry is present in the manifest afterwards.
    """
    path = os.path.join(output_dir, "configs", "manifest.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        print(f"[QC_WARNING] {label} not recorded: configs/manifest.json {exc}. "
              f"The gate's finding stands, but nobody will be asked to sign for it "
              f"at the manuscript gate — raise it manually.", file=sys.stderr)
        return False

    existing = manifest.setdefault("methodological_warnings", [])
    if any(isinstance(w, dict) and w.get("kind") == entry["kind"] for w in existing):
        return True
    existing.append(entry)
    try:
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[QC_WARNING] {label} not recorded: {exc}", file=sys.stderr)
        return False
    print(f"  Recorded {label} in configs/manifest.json "
          f"(the pre-manuscript gate will ask you to accept or reject it)")
    return True


def plan_fingerprint_of(plan):
    """(fingerprint, error). Delegates to reviewer_challenge so the two agree.

    Returns (None, reason) when it cannot be computed — the consumer must treat a
    null fingerprint as unverifiable, i.e. blocking. Guessing a fingerprint here
    would be worse than admitting we do not have one.
    """
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


def iter_steps(plan):
    for s in plan.get("pipeline") or []:
        if s.get("status") != "skipped":
            yield s


def ph_test_files(output_dir):
    return sorted(glob.glob(os.path.join(output_dir, "**", "*_ph_test.json"), recursive=True))


def step_outputs_exist(step, output_dir):
    """Declared outputs of a step that are actually on disk.

    A pipeline step names its output as a STEM, without an extension — the
    generators write `"output_file": "Multi_primary"` and the workbook lands as
    `Multi_primary.xlsx`. Matching the declared string literally therefore never
    found anything a generated step produced, so this half of the gate was a
    silent no-op for exactly the steps the pipeline creates; only the block path
    was ever exercised, and it looked correct because the answer it gave was the
    same one an actually-missing artifact deserves. Extensionless candidates now
    also match `<stem>.*`, which is the convention the rest of the pipeline
    already uses (`_OUTPUT_STEM` in generate_configs.py).
    """
    found = []
    candidates = []
    for key in ("output_file", "output_files", "expected_outputs", "outputs"):
        v = step.get(key)
        if isinstance(v, str):
            candidates.append(v)
        elif isinstance(v, list):
            candidates.extend([x for x in v if isinstance(x, str)])
    patterns = []
    for c in candidates:
        p = c if os.path.isabs(c) else os.path.join(output_dir, c)
        patterns.append(p)
        if not os.path.splitext(p)[1]:
            patterns.append(f"{p}.*")
    for p in patterns:
        for hit in glob.glob(p):
            if os.path.isfile(hit) and os.path.getsize(hit) > 0 and hit not in found:
                found.append(hit)
    return found


def file_sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def remedy_sidecar(artifact_path):
    """(payload, path, error) for ONE workbook: `<stem>_remedy.json`, nothing else.

    Same-stem only, deliberately, and for the reason the PSM contrast sidecar
    learned the hard way: a sidecar found by any looser rule may belong to another
    outcome or to last week's run, and a file that might describe something else
    is not evidence about this one.
    """
    path = f"{os.path.splitext(artifact_path)[0]}_remedy.json"
    if not os.path.exists(path):
        return None, path, None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), path, None
    except Exception as exc:
        return None, path, f"{type(exc).__name__}: {exc}"


def _block(stem, message, evidence, suggestion=None):
    f = {"check_id": "RES-015-det", "severity": "block",
         "message": f"{stem}: {message}", "evidence": evidence}
    if suggestion:
        f["suggestion"] = suggestion
    return f


def _warn(stem, message, evidence):
    return {"check_id": "RES-015-det", "severity": "warn",
            "message": f"{stem}: {message}", "evidence": evidence}


def check_stratify_content(stem, sidecar, sidecar_path, ph_art):
    """The check this whole slice exists for: does the remedy address THE violation?

    Everything before this point establishes that the sidecar describes this
    workbook. This establishes that the workbook is a remedy for the violation
    that actually occurred — a stratified Cox stratified on a variable the
    Schoenfeld test never flagged leaves the violation in the model while looking
    like a fix, and that is precisely the failure a file-existence test cannot see.
    """
    findings = []
    ev = {"sidecar": sidecar_path}

    declared_strata = list(sidecar.get("strata_variables") or [])
    if not declared_strata:
        findings.append(_block(stem, "evidence sidecar 的 strata_variables 是空的——"
                                     "沒有分層變項的「stratified Cox」不是分層模型。",
                               ev))
        return findings

    violators = set(ph_art.get("violating_variables") or [])
    sidecar_violators = set(sidecar.get("ph_violating_variables") or [])
    if sidecar_violators and sidecar_violators != violators:
        findings.append(_block(
            stem,
            f"evidence sidecar 記錄的違反變項 {sorted(sidecar_violators)} 與此次 PH 產物的 "
            f"{sorted(violators)} 不一致——這份 sidecar 讀的是另一次 PH 檢定的結果，"
            f"不能拿來證明這一次的違反已被處置。",
            dict(ev, sidecar_violators=sorted(sidecar_violators),
                 artifact_violators=sorted(violators)),
            "重跑 ph-stratified step，讓它讀當前的 *_ph_test.json。"))
        return findings

    uncovered = sorted(violators - set(declared_strata))
    if uncovered:
        findings.append(_block(
            stem,
            f"宣告 remedy='stratify'，但違反 PH 的變項 {uncovered} 沒有被分層"
            f"（實際分層的是 {sorted(declared_strata)}）。分層在沒有違反的變項上，"
            f"模型裡的違反原封不動，卻多了一張看起來像修正的表。",
            dict(ev, strata_variables=sorted(declared_strata), uncovered=uncovered),
            "把違反的變項納入 outcomes[].ph_strata_variables，或改用 "
            "strata_variables='auto'（預設）讓它直接取自 PH 檢定結果。"))
        return findings

    # Internal consistency: a stratified variable with a hazard ratio would mean
    # the strata never reached the fit.
    without_hr = set(sidecar.get("variables_without_hr") or [])
    if without_hr != set(declared_strata):
        findings.append(_block(
            stem,
            f"evidence sidecar 自相矛盾：strata_variables={sorted(declared_strata)}，"
            f"但 variables_without_hr={sorted(without_hr)}。被分層的變項依定義沒有 HR，"
            f"兩者不一致代表 strata 沒有真的進到模型裡。",
            dict(ev, strata_variables=sorted(declared_strata),
                 variables_without_hr=sorted(without_hr))))
        return findings

    # ── Quality signals. Warnings on purpose: each has a defensible answer that
    # is the author's to choose, and a check that blocks on a judgement call is
    # the kind people learn to route around.
    recheck = sidecar.get("ph_recheck") or {}
    if recheck.get("status") == "computed" and recheck.get("violated"):
        findings.append(_warn(
            stem,
            f"分層後 PH 假設**仍然違反**（{', '.join(recheck.get('violating_variables') or [])}，"
            f"min p={recheck.get('min_p')}）。remedy 有跑，但沒有解決問題——這張表不能當作"
            f"「已修正」呈現。考慮改用 time_varying / rmst，或在 limitations 說明。",
            dict(ev, ph_recheck=recheck)))
    elif recheck.get("status") != "computed":
        findings.append(_warn(
            stem,
            f"分層後沒有重驗 PH 假設（{recheck.get('reason', 'sidecar 未記錄 ph_recheck')}）。"
            f"「套用了 remedy」與「remedy 有效」是兩件事，只有後者值得寫進論文。",
            dict(ev, ph_recheck=recheck)))

    events = sidecar.get("events_per_stratum") or {}
    thin = sorted([k for k, v in events.items() if isinstance(v, int) and v < 10])
    if thin:
        findings.append(_warn(
            stem,
            f"{len(thin)} 個 stratum 的事件數 < 10（{', '.join(thin[:5])}"
            f"{'…' if len(thin) > 5 else ''}）。每層各吃一條 baseline hazard 卻幾乎不貢獻"
            f"資訊，估計會偏不穩定；考慮合併層級。",
            dict(ev, thin_strata=thin, events_per_stratum=events)))
    return findings


def check_rmst_content(stem, sidecar, sidecar_path, ph_art):
    """RMST sidesteps the hazard ratio rather than fixing a variable, so there is
    no "did it cover the offender" check to make. The one thing it has to defend
    is tau: the estimate is an integral up to tau and moves with it, so a tau
    chosen after seeing which value flatters the comparison is the whole
    p-hacking surface of the method.
    """
    findings = []
    ev = {"sidecar": sidecar_path}

    source = sidecar.get("tau_source")
    tau = sidecar.get("tau")
    if tau is None:
        findings.append(_block(stem, "evidence sidecar 沒有記錄 tau。RMST 是到 tau 為止"
                                     "的積分，沒有 tau 就沒有可複現的估計。", ev))
        return findings
    if source not in ("plan_value", "plan_rule"):
        findings.append(_block(
            stem,
            f"tau={tau} 的來源是 {source!r}，不是 research_plan.json。tau 沒有寫進 "
            f"outcomes[] 就不在 plan fingerprint 裡，也就無法證明它早於結果——而"
            f"「tau 是事前定的」正是這個 remedy 唯一要辯護的事。",
            dict(ev, tau=tau, tau_source=source),
            "在 outcomes[<id>] 填 rmst_tau（數值）或 rmst_tau_rule（規則名，目前支援 "
            "min_of_arm_max_followup），然後重跑該 step。"))
        return findings

    contrast = sidecar.get("contrast") or {}
    if not contrast or contrast.get("difference") is None:
        findings.append(_block(stem, "evidence sidecar 沒有兩組之間的 RMST 差值——"
                                     "沒有對比就沒有可報告的結果。", ev))
        return findings

    # Quality signals: each has an author-side answer, so none of them blocks.
    if not sidecar.get("tau_within_followup", True):
        findings.append(_warn(
            stem,
            f"tau={tau} 超出至少一組的最長追蹤時間"
            f"（{sidecar.get('max_followup_by_arm')}）。超過之後曲線是平的外推，"
            f"那一段的面積不是資料。",
            dict(ev, tau=tau,
                 max_followup_by_arm=sidecar.get("max_followup_by_arm"))))
    if sidecar.get("adjusted") is False:
        findings.append(_warn(
            stem,
            "這個 RMST 差值是**未校正**的（各組 Kaplan-Meier，沒有共變項），而它要"
            "取代的是一個校正過的模型——這是 estimand 的改變，不只是尺度的改變。"
            "報告時必須明說；若 confounding 在原模型裡真的有作用，stratify / "
            "time_varying 才是保留校正的選項。",
            dict(ev, adjusted=False)))
    return findings


def check_time_varying_content(stem, sidecar, sidecar_path, ph_art):
    """Two things to check, and they are the two ways this remedy goes wrong.

    The coverage check is the same shape as stratify's: giving a time-varying
    coefficient to a covariate the Schoenfeld test never flagged leaves the
    violation in the model. The cut-point check is the same shape as RMST's tau:
    windows drawn after seeing where the effect changes are a subgroup search
    along the time axis, not a pre-specified remedy.
    """
    findings = []
    ev = {"sidecar": sidecar_path}

    tv_vars = list(sidecar.get("time_varying_variables") or [])
    if not tv_vars:
        findings.append(_block(stem, "evidence sidecar 的 time_varying_variables 是空的"
                                     "——沒有任何係數隨時間變的模型不是這個 remedy。", ev))
        return findings

    violators = set(ph_art.get("violating_variables") or [])
    sidecar_violators = set(sidecar.get("ph_violating_variables") or [])
    if sidecar_violators and sidecar_violators != violators:
        findings.append(_block(
            stem,
            f"evidence sidecar 記錄的違反變項 {sorted(sidecar_violators)} 與此次 PH 產物的 "
            f"{sorted(violators)} 不一致——這份 sidecar 讀的是另一次 PH 檢定的結果。",
            dict(ev, sidecar_violators=sorted(sidecar_violators),
                 artifact_violators=sorted(violators))))
        return findings

    uncovered = sorted(violators - set(tv_vars))
    if uncovered:
        findings.append(_block(
            stem,
            f"宣告 remedy='time_varying'，但違反 PH 的變項 {uncovered} 的係數仍是固定的"
            f"（做成隨時間變的是 {sorted(tv_vars)}）。違反原封不動留在模型裡，"
            f"卻多了一張看起來像修正的表。",
            dict(ev, time_varying_variables=sorted(tv_vars), uncovered=uncovered),
            "把違反的變項納入 outcomes[].time_varying_variables，或改用預設的 "
            "'auto' 讓它直接取自 PH 檢定結果。"))
        return findings

    if sidecar.get("cut_points_source") != "plan":
        findings.append(_block(
            stem,
            f"時間窗的切點來源是 {sidecar.get('cut_points_source')!r}，不是 "
            f"research_plan.json（切點 {sidecar.get('cut_points')}）。切點沒有寫進 "
            f"outcomes[] 就不在 plan fingerprint 裡，無法證明它早於結果——看完效應"
            f"在哪裡轉向才畫的時間窗，是沿著時間軸做的次族群搜尋，不是 remedy。",
            dict(ev, cut_points=sidecar.get("cut_points"),
                 cut_points_source=sidecar.get("cut_points_source")),
            "在 outcomes[<id>].tv_cut_points 填切點（該 outcome 的 time_unit 為單位），"
            "然後重跑該 step。"))
        return findings

    # Quality signals.
    het = sidecar.get("heterogeneity") or {}
    for var, h in het.items():
        if h.get("status") == "computed" and not h.get("differs"):
            findings.append(_warn(
                stem,
                f"{var}：各時間窗的係數彼此無法區分（p={h.get('p')}）。模型有跑，但"
                f"這張表沒有證明效應真的隨時間改變——「我們跑了 time-varying 模型」"
                f"與「效應確實移動了」是兩個不同的宣稱。",
                dict(ev, heterogeneity=h)))
        elif h.get("status") != "computed":
            findings.append(_warn(
                stem,
                f"{var}：各時間窗的係數沒有被比較（{h.get('reason', '未記錄')}）。",
                dict(ev, heterogeneity=h)))
    events = sidecar.get("events_by_period") or {}
    thin = sorted([k for k, v in events.items()
                   if isinstance(v, dict) and isinstance(v.get("events"), int)
                   and v["events"] < 10])
    if thin:
        findings.append(_warn(
            stem,
            f"時間窗 {thin} 的事件數 < 10，那幾段的 HR 是用很少的資料估的，區間會很寬。"
            f"考慮改用較少、較寬的窗。",
            dict(ev, events_by_period=events)))
    return findings


CONTENT_CHECKS = {
    "stratify": check_stratify_content,
    "rmst": check_rmst_content,
    "time_varying": check_time_varying_content,
}


def verify_evidence(stem, remedy, artifacts, ph_art):
    """(findings, verified) — `verified` is None when there is nothing to verify.

    None means "fall back to the file-existence path", and it is returned for the
    two honest reasons: no sidecar was written (a hand-built step, or a remedy
    with no generator yet), or there is no content check for this remedy. It is
    never returned to paper over a sidecar that failed a check — those return
    findings, and blocking findings are what stop the run.
    """
    findings = []
    verified = None
    seen = set()
    for artifact in artifacts:
        # One step can leave several files (a workbook and a plot), and they all
        # resolve to the same sidecar. Check it once: the same finding reported
        # twice reads as two problems.
        stem_key = os.path.splitext(artifact)[0]
        if stem_key in seen:
            continue
        seen.add(stem_key)
        sidecar, sidecar_path, err = remedy_sidecar(artifact)
        if err:
            findings.append(_block(
                stem, f"evidence sidecar {os.path.basename(sidecar_path)} 無法解析"
                      f"（{err}）。無法確認 remedy 的內容。",
                {"artifact": artifact, "sidecar": sidecar_path}))
            continue
        if sidecar is None:
            continue

        ev = {"artifact": artifact, "sidecar": sidecar_path}
        schema = str(sidecar.get("schema") or "")
        if not schema.startswith(EVIDENCE_SCHEMA_PREFIX):
            findings.append(_block(
                stem, f"{os.path.basename(sidecar_path)} 的 schema={schema!r} 不是 "
                      f"{EVIDENCE_SCHEMA_PREFIX}*；這不是本閘門看得懂的 evidence 格式。",
                dict(ev, schema=schema)))
            continue

        # Binding. All three failures mean the same thing — the file is about
        # something else — and none of them is recoverable by reading harder.
        declared_table = sidecar.get("table_basename")
        declared_hash = sidecar.get("table_sha256")
        if not declared_table and not declared_hash:
            findings.append(_block(
                stem, f"{os.path.basename(sidecar_path)} 沒有 table_basename / "
                      f"table_sha256，無法證明它描述的是 {os.path.basename(artifact)}。"
                      f"未綁定的 sidecar 不能當證據。",
                ev, "重跑該 step 重新產生 sidecar。"))
            continue
        if declared_table and declared_table != os.path.basename(artifact):
            findings.append(_block(
                stem, f"{os.path.basename(sidecar_path)} 自稱描述 {declared_table!r}，"
                      f"卻放在 {os.path.basename(artifact)} 旁邊。",
                dict(ev, declared_table=declared_table)))
            continue
        actual_hash = file_sha256(artifact)
        if declared_hash and actual_hash and declared_hash != actual_hash:
            findings.append(_block(
                stem, f"{os.path.basename(sidecar_path)} 是為另一個版本的 "
                      f"{os.path.basename(artifact)} 寫的（sha256 "
                      f"{str(declared_hash)[:12]}… vs {actual_hash[:12]}…）。兩者其一"
                      f"被重新產生過，sidecar 描述的不是磁碟上這張表。",
                dict(ev, declared_sha256=declared_hash, actual_sha256=actual_hash),
                "重跑該 step，讓表與 sidecar 一起重生。"))
            continue

        if sidecar.get("remedy") != remedy:
            findings.append(_block(
                stem, f"{os.path.basename(sidecar_path)} 記錄的 remedy="
                      f"{sidecar.get('remedy')!r}，但 plan 宣告的是 {remedy!r}。"
                      f"跑的與宣告的必須是同一個 remedy。",
                dict(ev, sidecar_remedy=sidecar.get("remedy"))))
            continue

        # Three states, kept apart. Both non-computed states are blocking here,
        # but for different reasons and with different fixes — collapsing them
        # into one message is how the wrong fix gets attempted.
        status = sidecar.get("status")
        if status == "not_computed":
            findings.append(_block(
                stem, f"remedy '{remedy}' 的 evidence status=not_computed"
                      f"（{sidecar.get('reason', '')}）。算不出來不是通過——未處置的 HR "
                      f"不得進 manuscript。",
                dict(ev, status=status)))
            continue
        if status == "not_applicable":
            findings.append(_block(
                stem, f"remedy '{remedy}' 的 evidence status=not_applicable"
                      f"（{sidecar.get('reason', '')}），但這個 PH 產物顯示假設**確實被違反**。"
                      f"兩者矛盾：remedy step 看到的與這裡看到的不是同一次分析。",
                dict(ev, status=status)))
            continue
        if status != "computed":
            findings.append(_block(
                stem, f"remedy '{remedy}' 的 evidence status={status!r} 不是三態 "
                      f"(computed / not_computed / not_applicable) 之一。",
                dict(ev, status=status)))
            continue

        checker = CONTENT_CHECKS.get(remedy)
        if checker is None:
            findings.append(_warn(
                stem, f"remedy '{remedy}' 有 evidence sidecar，但本閘門還沒有這個 remedy "
                      f"的內容檢查，因此**沒有驗證它的統計內容**，退回「檔案存在」路徑。",
                ev))
            continue

        content = checker(stem, sidecar, sidecar_path, ph_art)
        findings.extend(content)
        if any(f["severity"] == "block" for f in content):
            continue
        verified = {
            "stem": stem, "remedy": remedy, "artifact": artifact,
            "sidecar": sidecar_path,
            "method": sidecar.get("method"),
            # `source_table` is the cross-reference a manuscript needs: the
            # unremediated workbook this table is the remedy for.
            "source_table": sidecar.get("source_table"),
            "n": sidecar.get("n"), "n_events": sidecar.get("n_events"),
            "detail": _verified_detail(remedy, sidecar),
            "ph_recheck_status": (sidecar.get("ph_recheck") or {}).get("status"),
            "ph_recheck_violated": (sidecar.get("ph_recheck") or {}).get("violated"),
        }
    return findings, verified


def _verified_detail(remedy, sidecar):
    """One line naming what was actually checked, per remedy.

    The summary has to say which remedy was verified and on what, because "1
    remedy verified" reads the same whether the check was the strong one or a
    weaker one that happened to pass.
    """
    if remedy == "stratify":
        return (f"分層於 {', '.join(sidecar.get('strata_variables') or []) or '(未列出)'}"
                f"，涵蓋了實際違反 PH 的變項")
    if remedy == "rmst":
        c = sidecar.get("contrast") or {}
        diff = c.get("difference")
        return (f"tau={sidecar.get('tau')}（來源 {sidecar.get('tau_source')}，"
                f"事前指定）"
                + (f"，RMST 差值 {diff:+.3f}" if isinstance(diff, (int, float)) else "")
                + ("；未校正" if sidecar.get("adjusted") is False else ""))
    if remedy == "time_varying":
        return (f"{', '.join(sidecar.get('time_varying_variables') or []) or '(未列出)'} "
                f"的係數依事前指定的時間窗 {sidecar.get('cut_points')} 分段，"
                f"涵蓋了實際違反 PH 的變項")
    return sidecar.get("method") or ""


def audit(plan, output_dir, decision_log_path):
    findings = []
    attestations = []          # remedies passed on file existence alone
    verifieds = []             # remedies whose evidence sidecar was checked
    checked = 0

    files = ph_test_files(output_dir)
    if not files:
        return findings, checked, ("no *_ph_test.json found under "
                                   f"{output_dir} — either no Cox step ran, or the PH "
                                   "artifacts were never produced. Both need a human "
                                   "look before a manuscript; this gate cannot tell "
                                   "them apart."), attestations, verifieds

    decision_log = ""
    if decision_log_path and os.path.exists(decision_log_path):
        with open(decision_log_path, "r", encoding="utf-8") as f:
            decision_log = f.read()

    steps = list(iter_steps(plan))

    for path in files:
        checked += 1
        try:
            art = load_json(path)
        except Exception as e:
            findings.append({
                "check_id": "RES-015-det", "severity": "block",
                "message": f"{os.path.basename(path)} 無法解析（{type(e).__name__}）；"
                           f"無法確認 PH 是否被處置。",
                "evidence": {"artifact": path}})
            continue

        status = art.get("status")
        if status == "not_computed":
            findings.append({
                "check_id": "RES-015-det", "severity": "block",
                "message": f"{os.path.basename(path)}: PH 檢定 status=not_computed"
                           f"（{art.get('reason', '')}）。算不出來不是通過，"
                           f"未處置的 HR 不得進 manuscript。",
                "evidence": {"artifact": path, "status": status}})
            continue
        if status != "computed":
            findings.append({
                "check_id": "RES-015-det", "severity": "warn",
                "message": f"{os.path.basename(path)}: status={status}"
                           f"（{art.get('reason', '')}）。",
                "evidence": {"artifact": path, "status": status}})
            continue

        if art.get("borderline"):
            findings.append({
                "check_id": "RES-015-det", "severity": "warn",
                "message": f"{os.path.basename(path)}: PH borderline"
                           f"（min p={art.get('min_p')}）。不擋稿，但 reviewer challenge "
                           f"domain 5 必須逐條表態（dismiss with reason / escalate）。",
                "evidence": {"artifact": path, "min_p": art.get("min_p"),
                             "effect_size": art.get("effect_size")}})

        if not art.get("violated"):
            continue

        # Which step produced this artifact? (…/Multi_os_ph_test.json -> Multi_os)
        stem = os.path.basename(path)[: -len("_ph_test.json")]
        remedy = art.get("declared_remedy") or _remedy_from_configs(output_dir, stem, plan)

        if not remedy:
            findings.append({
                "check_id": "RES-015-det", "severity": "block",
                "message": f"{stem}: PH 違反且沒有任何 declared remedy。產生該表的 step "
                           f"應已 exit 2；若它仍走到這裡，代表被 override 繞過。",
                "evidence": {"artifact": path}})
            continue
        if remedy not in ALL_REMEDIES:
            findings.append({
                "check_id": "RES-015-det", "severity": "block",
                "message": f"{stem}: declared remedy '{remedy}' 不是合法值 {list(ALL_REMEDIES)}。",
                "evidence": {"artifact": path, "remedy": remedy}})
            continue

        if remedy == "disclose":
            # Prefer the per-outcome field: `outcomes` is in reviewer_challenge's
            # FINGERPRINT_FIELDS, so a decision ID declared there cannot be added or
            # swapped without invalidating the challenge. A top-level
            # `ph_disclose_decision_id` is NOT fingerprinted (measured), so it is
            # accepted but flagged — it can be edited silently.
            did = None
            for o in _iter_outcomes(plan):
                if o.get("ph_disclose_decision_id"):
                    did = o["ph_disclose_decision_id"]
                    break
            if not did and plan.get("ph_disclose_decision_id"):
                did = plan["ph_disclose_decision_id"]
                findings.append({
                    "check_id": "RES-015-det", "severity": "warn",
                    "message": f"{stem}: ph_disclose_decision_id 宣告在 plan 頂層，"
                               f"而頂層不在 reviewer_challenge 的 FINGERPRINT_FIELDS —— "
                               f"這個 ID 可以被靜默改掉而不作廢 challenge。"
                               f"建議改宣告在 outcomes[].ph_disclose_decision_id。",
                    "evidence": {"artifact": path, "decision_id": did}})
            if not did:
                findings.append({
                    "check_id": "RES-015-det", "severity": "block",
                    "message": f"{stem}: remedy='disclose' 但 plan 沒有 "
                               f"`ph_disclose_decision_id`。零成本的 disclose 不算處置——"
                               f"揭露必須是一列有永久 ID 的決策。",
                    "evidence": {"artifact": path, "remedy": remedy},
                    "suggestion": "在 decision_log.md 開一列（例 D-017），把該 ID 寫進 "
                                  "plan 的 ph_disclose_decision_id。"})
            elif not decision_log:
                findings.append({
                    "check_id": "RES-015-det", "severity": "block",
                    "message": f"{stem}: 宣告了 ph_disclose_decision_id='{did}' 但找不到 "
                               f"decision_log.md（查了 {decision_log_path}）。",
                    "evidence": {"artifact": path, "decision_id": did}})
            elif not re.search(re.escape(str(did)), decision_log):
                findings.append({
                    "check_id": "RES-015-det", "severity": "block",
                    "message": f"{stem}: ph_disclose_decision_id='{did}' 在 decision_log.md "
                               f"裡找不到。ID 指向不存在的決策等於沒有決策。",
                    "evidence": {"artifact": path, "decision_id": did,
                                 "decision_log": decision_log_path}})
            continue

        # stratify / time_varying / rmst: a real analysis has to exist.
        hints = REMEDY_STEP_HINTS[remedy]
        evidence_steps = []
        for s in steps:
            hay = f"{s.get('id', '')} {s.get('skill', '')} {s.get('analysis', '')}".lower()
            if any(h in hay for h in hints):
                outs = step_outputs_exist(s, output_dir)
                evidence_steps.append({"step": s.get("id"), "skill": s.get("skill"),
                                       "outputs_found": outs})
        produced = [e for e in evidence_steps if e["outputs_found"]]
        if not produced:
            extra = ""
            if remedy in REMEDIES_WITHOUT_SHIPPED_STEP:
                extra = (f" 注意：目前的 pipeline 沒有 '{remedy}' 的 step generator，"
                         f"這個 remedy 必須自建 step（或改宣告成做得到的 remedy），"
                         f"否則這道 gate 會把人擋在沒有出口的門前。")
            findings.append({
                "check_id": "RES-015-det", "severity": "block",
                "message": f"{stem}: declared remedy '{remedy}' has no artifact; "
                           f"the unremediated Sheet 1 HR may not reach the manuscript."
                           f"{extra}",
                "evidence": {"artifact": path, "remedy": remedy,
                             "candidate_steps": evidence_steps},
                "suggestion": f"把 '{remedy}' 分析做成獨立 step 並產出檔案，"
                              f"manuscript 的主估計指向該表。"})
        else:
            artifacts = [o for e in produced for o in e["outputs_found"]]
            ev_findings, verified = verify_evidence(stem, remedy, artifacts, art)
            findings.extend(ev_findings)
            if verified:
                verifieds.append(verified)
            elif not any(f["severity"] == "block" for f in ev_findings):
                # No sidecar to check, and nothing failed — the pre-2026-08-12
                # path. Passing here proves a file exists and nothing about its
                # contents, so it becomes a substitution the pre-manuscript gate
                # makes a named person state they ran, where, and how.
                attestations.append({
                    "stem": stem, "remedy": remedy,
                    "artifacts": artifacts,
                    "steps": [e["step"] for e in produced],
                })
                findings.append({
                    "check_id": "RES-015-det", "severity": "warn",
                    "message": (f"{stem}: declared remedy '{remedy}' 的產物存在"
                                f"（{', '.join(e['step'] or '?' for e in produced)}），"
                                f"但旁邊沒有 evidence sidecar，所以**本次只驗到檔案存在，"
                                f"沒有驗其統計內容**——沒有任何檢查證明那個檔案裡真的做了 "
                                f"'{remedy}'。因此會在 manifest 記一條 "
                                f"`ph_remedy_declared_not_computed`，manuscript 之前"
                                f"必須由作者具名說明「我算了什麼、產物在哪、用什麼方法」。"),
                    "evidence": {"artifact": path, "remedy": remedy,
                                 "artifacts_found": artifacts,
                                 "expected_sidecar": [
                                     f"{os.path.splitext(a)[0]}_remedy.json"
                                     for a in artifacts]},
                    "suggestion": ("改用 pipeline 產生的 remedy step（stratify 已有 "
                                   "`ph-stratified` generator），它會寫出可驗證的 "
                                   "evidence sidecar；或在 pre-manuscript gate 用 "
                                   "--accept-substitution SUB-xxxx:\"理由\" 具名接受，"
                                   "理由要寫得足以在 rebuttal letter 引用。")})
    return findings, checked, None, attestations, verifieds


def _iter_outcomes(plan):
    oc = plan.get("outcomes")
    if isinstance(oc, dict):
        if oc.get("primary"):
            yield oc["primary"]
        for s in oc.get("secondary") or []:
            yield s
    elif isinstance(oc, list):
        for s in oc:
            yield s


def _remedy_from_configs(output_dir, stem, plan):
    """The remedy the producing step actually ran with.

    Read from the generated config (that is what the script saw), falling back to the
    plan. Deliberately not the other way round: if they disagree, the config is what
    produced the number on the table.
    """
    for cand in glob.glob(os.path.join(output_dir, "**", "*_config.json"), recursive=True):
        try:
            cfg = load_json(cand)
        except Exception:
            continue
        out = cfg.get("output_file") or ""
        if out and os.path.splitext(os.path.basename(out))[0] == stem:
            if cfg.get("ph_violation_remedy"):
                return cfg["ph_violation_remedy"]
    for o in _iter_outcomes(plan):
        if o.get("ph_violation_remedy"):
            return o["ph_violation_remedy"]
    return plan.get("ph_violation_remedy")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--decision-log", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = uuid.uuid4().hex[:12]

    # Before anything else, including the early exits below: any abnormal end must
    # leave no report, never last run's.
    clear_stale_output(args.json)

    if not os.path.exists(args.plan):
        print(f"[QC_BLOCKING] plan not found: {args.plan}. PH remedies were not audited — "
              f"that is not the same as them being satisfied.", file=sys.stderr)
        sys.exit(2)
    plan = load_json(args.plan)

    output_dir = args.output_dir or plan.get("output_dir") or os.path.dirname(
        os.path.abspath(args.plan))
    if not os.path.isdir(output_dir):
        print(f"[QC_BLOCKING] output dir not found: {output_dir}. PH remedies were not "
              f"audited.", file=sys.stderr)
        sys.exit(2)

    decision_log = args.decision_log
    if not decision_log:
        for cand in ("report/decision_log.md", "decision_log.md",
                     "analysis/report/decision_log.md"):
            p = os.path.join(output_dir, cand)
            if os.path.exists(p):
                decision_log = p
                break
        decision_log = decision_log or os.path.join(output_dir, "decision_log.md")

    findings, checked, fatal, attestations, verifieds = audit(
        plan, output_dir, decision_log)
    if fatal:
        print(f"[QC_BLOCKING] {fatal}", file=sys.stderr)
        sys.exit(2)

    # Anything that passed on file existence alone becomes a substitution somebody
    # has to sign for. Done BEFORE the report is written and the exit decided, so
    # the report records what actually happened rather than what was intended.
    recorded = True
    if attestations:
        lines = "；".join(
            f"{a['stem']} 宣告 remedy='{a['remedy']}'，產物 "
            f"{', '.join(os.path.basename(x) for x in a['artifacts']) or '(未列出)'}"
            for a in attestations)
        recorded = record_manifest_substitution(output_dir, {
            "kind": "ph_remedy_declared_not_computed",
            "source": "runtime",
            "text": (f"PH 違反後宣告的 remedy 只驗到「檔案存在」，沒有任何檢查證明那些檔案"
                     f"裡真的做了所宣告的分析：{lines}。接受這一條等於具名聲明：這個 remedy "
                     f"是我自己算的、產物在上述路徑、使用的方法是 <請在理由中寫明>。"
                     f"若實際上沒有算，請改宣告 disclose（並附 decision_log ID）或補做該分析。"),
        }, "PH remedy 只驗到檔案存在（ph_remedy_declared_not_computed）")
        if not recorded:
            # The green light was only defensible because someone would be asked to
            # sign for the remedy. If that request cannot be recorded, the premise is
            # gone and this must not pass.
            findings.append({
                "check_id": "RES-015-det", "severity": "block",
                "message": ("PH remedy 只驗到檔案存在，而 `ph_remedy_declared_not_computed` "
                            "無法寫進 configs/manifest.json（見上方 QC_WARNING）。"
                            "沒有人會在 manuscript 前被要求為這個 remedy 具名表態，"
                            "所以這個綠燈沒有根據——修好 manifest 或手動把這條記進去。"),
                "evidence": {"output_dir": output_dir,
                             "manifest": os.path.join(output_dir, "configs", "manifest.json"),
                             "attestations": attestations}})

    blocking = [f for f in findings if f["severity"] == "block"]
    warns = [f for f in findings if f["severity"] == "warn"]

    # Provenance, so the consumer can prove this report is about THIS analysis and
    # was produced by THIS run. Without it a file at a fixed path is just a file:
    # nothing distinguishes last week's pass from today's.
    fingerprint, fp_error = plan_fingerprint_of(plan)
    if fingerprint is None:
        print(f"[QC_WARNING] plan fingerprint could not be computed ({fp_error}); the "
              f"report is written with plan_fingerprint=null and a consumer must treat "
              f"that as unverifiable, not as a pass.", file=sys.stderr)

    result = {
        "schema": REPORT_SCHEMA,
        "tool": "biostats-guardian/scripts/ph_remedy_gate.py",
        "run_id": run_id,
        "started_at": started_at,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": plan.get("version"),
        "plan_fingerprint": fingerprint,
        "plan_fingerprint_error": fp_error,
        "plan": os.path.abspath(args.plan),
        "output_dir": os.path.abspath(output_dir),
        "decision_log": decision_log,
        "n_ph_artifacts": checked,
        "n_blocking": len(blocking),
        "n_warning": len(warns),
        # What this run verified only as "a file exists" — the consumer should read
        # this as "unverified", not as part of the pass.
        "attestations_unverified": attestations,
        # Remedies whose evidence sidecar was bound to the artifact and
        # cross-checked against the PH test that triggered them. Also the
        # cross-reference a manuscript needs: `source_table` is the unremediated
        # workbook this table is the remedy for.
        "verified_remedies": verifieds,
        "manifest_substitution_recorded": recorded,
        "verified_scope": (
            f"{len(verifieds)} remedy/remedies verified against a bound evidence "
            f"sidecar (declared remedy, computed status, and the stratification "
            f"actually covering the covariates that violated PH); "
            f"{len(attestations)} passed on artifact existence alone, with the "
            f"statistical content NOT checked"),
        "exit_code": 1 if blocking else 0,
        "findings": findings,
    }
    if args.json:
        write_json_atomic(args.json, result)

    for f in warns:
        print(f"[QC_WARNING] {f['check_id']} {f['message']}", file=sys.stderr)
    for f in blocking:
        print(f"[QC_BLOCKING] {f['check_id']} {f['message']}", file=sys.stderr)

    if not args.quiet:
        # Wording matters here: this gate's green light is weaker than every other
        # deterministic gate around it, and a summary that reads like "PH remedy
        # handled" is where the wrong mental model comes from.
        print(f"PH remedy gate: 檢查了 {checked} 個 PH 產物，{len(blocking)} 個阻擋、"
              f"{len(warns)} 個警告")
        for v in verifieds:
            print(f"  ✓ {v['stem']}: remedy '{v['remedy']}' 已對 evidence sidecar 驗證"
                  f"（{v.get('detail')}；n={v.get('n')}, events={v.get('n_events')}）。")
            if v.get("ph_recheck_violated"):
                print(f"      ⚠ 但處置後 PH 仍違反 —— remedy 有跑，沒有解決問題。")
        if attestations:
            print(f"  ⚠ 另有 {len(attestations)} 個 remedy 只驗證了「宣告的產物存在」"
                  f"（旁邊沒有 evidence sidecar）；**這幾個的統計內容未經驗證**。"
                  + ("已記入 manifest，manuscript 前須作者具名表態。" if recorded
                     else "且無法記入 manifest —— 已改為阻擋。"))
        if not blocking and not attestations and not verifieds:
            print("  通過範圍：每個 PH 違反都有宣告的 remedy，且 disclose 類都有 "
                  "decision_log ID。本次沒有需要驗證產物的 remedy。")
    sys.exit(1 if blocking else 0)


if __name__ == "__main__":
    main()
