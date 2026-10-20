#!/usr/bin/env python3
"""
Research Guardian — Pipeline Runner
Orchestrates gates, manages checkpoints, generates dashboard.

Usage:
  python runner.py review input.txt                    # Quick mode (auto)
  python runner.py review input.txt --mode full        # Full mode
  python runner.py review input.txt --preset ml        # ML paper preset
  python runner.py resume                              # Resume interrupted run
  python runner.py dashboard                           # Generate dashboard HTML
  python runner.py status                              # Show current run status
"""

import json
import os
import sys
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

# === Configuration ===
# To extend: see references/extensibility-guide.md

VERSION = "2.0"

CHECKPOINT_DIR = Path("/tmp/research-guardian/checkpoints")
OUTPUT_DIR = Path("/tmp/research-guardian/output")
DASHBOARD_PATH = OUTPUT_DIR / "dashboard.html"

# ── Extension Point: Gates ──
# Add new gates here. Each entry = an independent subagent call.
# Also update: SKILL.md trigger table, parallel-execution.md, quick-modes.md
GATES = [
    "hypothesis_guard",
    "literature_guard",
    "experiment_guard",
    "result_guard",
    "writing_guard",
    "logic_chain",
]

# ── Extension Point: Presets ──
# Add new domain presets here. Each maps a keyword to a subset of gates.
# Also update: quick-modes.md
PRESETS = {
    "ml":       ["literature_guard", "experiment_guard", "result_guard", "writing_guard", "logic_chain"],
    "clinical": ["hypothesis_guard", "literature_guard", "experiment_guard", "result_guard", "writing_guard", "logic_chain"],
    "socsci":   ["hypothesis_guard", "literature_guard", "experiment_guard", "result_guard", "logic_chain"],
    "sr":       ["literature_guard", "writing_guard", "logic_chain"],
    "proposal": ["hypothesis_guard", "literature_guard", "logic_chain"],
}

# ── Extension Point: Modes ──
# Add new execution modes here.
MODES = {
    "quick":    ["result_guard", "writing_guard"],
    "standard": ["literature_guard", "result_guard", "writing_guard", "logic_chain"],
    "full":     GATES,
}


# === Utility Functions ===

def make_run_id(input_path: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    h = hashlib.sha256(input_path.encode()).hexdigest()[:8]
    return f"run-{ts}-{h}"


def make_paper_id(input_path: str) -> str:
    name = Path(input_path).stem
    return name.lower().replace(" ", "-").replace("_", "-")[:60]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "json").mkdir(exist_ok=True)
    (OUTPUT_DIR / "markdown").mkdir(exist_ok=True)
    (OUTPUT_DIR / "html").mkdir(exist_ok=True)


# === Checkpoint System ===

class Checkpoint:
    """Manages pipeline state for fault tolerance."""

    def __init__(self, run_id: str, paper_id: str, mode: str, preset: str = ""):
        self.path = CHECKPOINT_DIR / f"{run_id}.checkpoint.json"
        self.data = {
            "run_id": run_id,
            "paper_id": paper_id,
            "mode": mode,
            "preset": preset,
            "status": "running",
            "started_at": now_iso(),
            "updated_at": now_iso(),
            "completed_at": None,
            "gates_completed": {},
            "gates_pending": [],
            "escalated_from": None,
            "error_log": [],
        }

    def save(self):
        self.data["updated_at"] = now_iso()
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))

    @classmethod
    def load_latest(cls) -> "Checkpoint | None":
        if not CHECKPOINT_DIR.exists():
            return None
        files = sorted(CHECKPOINT_DIR.glob("*.checkpoint.json"), reverse=True)
        for f in files:
            data = json.loads(f.read_text())
            if data["status"] in ("running", "interrupted"):
                cp = cls.__new__(cls)
                cp.path = f
                cp.data = data
                return cp
        return None

    def mark_gate_start(self, gate_name: str):
        self.data["gates_pending"].append(gate_name)
        self.save()

    def mark_gate_done(self, gate_name: str, result: dict):
        self.data["gates_completed"][gate_name] = result
        if gate_name in self.data["gates_pending"]:
            self.data["gates_pending"].remove(gate_name)
        self.save()

    def mark_gate_error(self, gate_name: str, error: str):
        self.data["error_log"].append(f"{now_iso()} | {gate_name} | {error}")
        if gate_name in self.data["gates_pending"]:
            self.data["gates_pending"].remove(gate_name)
        self.data["gates_completed"][gate_name] = {
            "gate_name": gate_name,
            "status": "error",
            "issues": [],
            "started_at": now_iso(),
            "completed_at": now_iso(),
            "error": error,
        }
        self.save()

    def mark_complete(self):
        self.data["status"] = "completed"
        self.data["completed_at"] = now_iso()
        self.save()

    def mark_interrupted(self):
        self.data["status"] = "interrupted"
        self.save()

    def mark_escalated(self, from_mode: str, to_mode: str):
        self.data["escalated_from"] = from_mode
        self.data["mode"] = to_mode
        self.save()

    def get_remaining_gates(self, gate_list: list[str]) -> list[str]:
        done = set(self.data["gates_completed"].keys())
        return [g for g in gate_list if g not in done]

    @property
    def is_resumable(self) -> bool:
        return self.data["status"] in ("running", "interrupted")


# === Gate Runner (Stub — fail-closed per CRITICAL audit fix) ===

def run_gate(gate_name: str, input_text: str, checkpoint: Checkpoint) -> dict:
    """
    Run a single gate.

    CRITICAL FIX (2026-05-08, rg-A-01 + rg-B-01): previous implementation
    returned status="pass" + zero issues for every gate (fail-open stub),
    which meant `research-guardian` claimed to audit research output but
    actually performed zero checks. Worse, the aggregator (line 352) recommended
    `accept` whenever there were zero issues — so a stub-passed gate was
    indistinguishable from a real-passed gate, and downstream skills
    (deep-research / academic-paper / lit-review) trusted that signal.

    Per P-7 audit decision (user 2026-05-08): mark stub + fail-closed default.
    Each gate now returns status="error" + UNVERIFIED issue (block severity)
    so the aggregator (rg-B-01 fix downstream) cannot recommend `accept` while
    the runner is unimplemented. SKILL.md is also updated to label this skill
    as a preflight-only stub.

    To re-enable real audit: replace the body of this function with subagent
    spawn (see commented-out line below for the intended interface).
    """
    started = now_iso()
    checkpoint.mark_gate_start(gate_name)

    # In production: spawn subagent that actually audits the gate.
    # result = await spawn_subagent(gate_name, input_text, checklist)
    # For now, fail-closed:
    # Use severity="critical" so aggregate_results() (line ~382) sets
    # recommendation="reject" — fail-closed default until real runner ships.
    result = {
        "gate_name": gate_name,
        "status": "error",
        "issues": [
            {
                "id": f"{gate_name}-stub",
                "severity": "critical",
                "category": "guardian-stub",
                "message": (
                    f"Gate '{gate_name}' is not implemented (research-guardian "
                    f"runner is currently a stub; see SKILL.md preflight-only note). "
                    f"All gate outputs are UNVERIFIED — do not treat as PASS."
                ),
                "evidence": [],
                "confidence": 1.0,
                "location": {"anchor_id": f"stub-{gate_name}"},
            }
        ],
        "sub_module_used": "stub",
        "logic_layers_run": [],
        "started_at": started,
        "completed_at": now_iso(),
        "duration_seconds": 0,
        "token_usage": 0,
        "stub": True,
    }

    checkpoint.mark_gate_done(gate_name, result)
    return result


# === Pre-scan ===

def pre_scan(input_text: str) -> dict:
    """Content-aware pre-scan: determines mode, domain, study type, and sub-modules."""
    text_lower = input_text.lower()

    # --- Mode selection (risk level) ---
    overclaim_words = sum(1 for w in ["prove", "revolutionary", "definitive", "breakthrough",
                                       "miracle", "first ever", "proves", "demonstrated"]
                          if w in text_lower)
    has_limitations = "limitation" in text_lower
    has_citations = "[" in input_text or "et al" in text_lower
    word_count = len(input_text.split())

    risk = "low"
    if overclaim_words >= 2 or not has_limitations:
        risk = "medium"
    if overclaim_words >= 3 and not has_limitations:
        risk = "high"

    suggested_mode = {"low": "quick", "medium": "standard", "high": "full"}[risk]

    # --- Domain detection (Pattern 1: content-aware routing) ---
    domains = []
    domain_signals = {
        "biomedical": ["patient", "clinical", "rct", "placebo", "dosage", "cohort",
                       "pubmed", "lancet", "nejm", "jama", "bmj", "irb", "informed consent"],
        "cs-ml":      ["model", "accuracy", "epoch", "gpu", "fine-tun", "benchmark",
                       "arxiv", "neurips", "icml", "iclr", "transformer", "dataset"],
        "social-science": ["participant", "survey", "likert", "cronbach", "anova",
                           "psychol", "sociol", "questionnaire", "self-report"],
    }
    for domain, signals in domain_signals.items():
        hits = sum(1 for s in signals if s in text_lower)
        if hits >= 3:
            domains.append({"domain": domain, "confidence": "high" if hits >= 5 else "medium"})
        elif hits >= 1:
            domains.append({"domain": domain, "confidence": "low"})

    # --- Study type detection ---
    study_type = None
    study_signals = {
        "rct":           ["randomized", "blinded", "placebo", "allocation", "consort"],
        "observational": ["cohort", "case-control", "cross-sectional", "odds ratio", "strobe"],
        "ml-experiment": ["fine-tun", "trained", "benchmark", "baseline", "ablation", "epoch"],
        "qualitative":   ["interview", "thematic", "saturation", "phenomenol", "grounded theory"],
    }
    best_type, best_count = None, 0
    for stype, signals in study_signals.items():
        hits = sum(1 for s in signals if s in text_lower)
        if hits > best_count:
            best_type, best_count = stype, hits
    if best_count >= 2:
        study_type = best_type

    # --- Stat framework detection ---
    stat_framework = None
    stat_signals = {
        "frequentist": ["t(", "f(", "p =", "p<", "chi-square", "χ²", "anova"],
        "bayesian":    ["posterior", "hdi", "bayes factor", "mcmc", "rope", "prior"],
        "ml-metrics":  ["auroc", "auprc", "f1", "precision", "recall", "accuracy"],
    }
    best_stat, best_stat_count = None, 0
    for sframework, signals in stat_signals.items():
        hits = sum(1 for s in signals if s in text_lower)
        if hits > best_stat_count:
            best_stat, best_stat_count = sframework, hits
    if best_stat_count >= 2:
        stat_framework = best_stat

    # --- Compute sub-modules to load ---
    sub_modules = []
    for d in domains:
        if d["confidence"] in ("high", "medium"):
            sub_modules.append(f"hypothesis/{d['domain']}.md")
            sub_modules.append(f"literature/{d['domain']}.md")
    if study_type:
        sub_modules.append(f"experiment/{study_type}.md")
    if stat_framework:
        sub_modules.append(f"result/{stat_framework}.md")

    # --- Domain confidence for routing mode ---
    domain_confidence = "high"
    if not domains:
        domain_confidence = "low"
    elif all(d["confidence"] == "low" for d in domains):
        domain_confidence = "low"
    elif any(d["confidence"] == "medium" for d in domains):
        domain_confidence = "medium"

    return {
        "risk": risk,
        "suggested_mode": suggested_mode,
        "domains": domains,
        "domain_confidence": domain_confidence,
        "study_type": study_type,
        "stat_framework": stat_framework,
        "sub_modules_to_load": sub_modules,
        "signals": {
            "has_limitations": has_limitations,
            "overclaim_words": overclaim_words,
            "has_citations": has_citations,
            "word_count": word_count,
        },
    }


# === Aggregator ===

def aggregate_results(gate_results: dict[str, dict]) -> dict:
    """Merge all gate results, deduplicate issues, compute scorecard."""
    all_issues = []
    for gate_name, result in gate_results.items():
        for issue in result.get("issues", []):
            issue["detected_by"] = issue.get("detected_by", []) + [gate_name]
            all_issues.append(issue)

    # Deduplicate by location + category
    seen = {}
    deduped = []
    for issue in all_issues:
        key = (issue.get("location", {}).get("anchor_id", ""), issue.get("category", ""))
        if key in seen:
            existing = seen[key]
            existing["detected_by"] = list(set(existing["detected_by"] + issue["detected_by"]))
            sev_rank = {"critical": 0, "major": 1, "minor": 2}
            if sev_rank.get(issue["severity"], 2) < sev_rank.get(existing["severity"], 2):
                existing["severity"] = issue["severity"]
            existing["confidence"] = max(existing["confidence"], issue.get("confidence", 0.5))
        else:
            seen[key] = issue
            deduped.append(issue)

    # Severity boost: detected by 2+ gates → upgrade
    for issue in deduped:
        if len(issue.get("detected_by", [])) >= 2:
            upgrades = {"minor": "major", "major": "critical"}
            issue["severity"] = upgrades.get(issue["severity"], issue["severity"])

    # Sort
    sev_order = {"critical": 0, "major": 1, "minor": 2}
    deduped.sort(key=lambda i: (sev_order.get(i["severity"], 3), -i.get("confidence", 0)))

    # Compute recommendation
    critical = sum(1 for i in deduped if i["severity"] == "critical")
    major = sum(1 for i in deduped if i["severity"] == "major")

    if critical > 0:
        recommendation = "reject"
    elif major >= 4:
        recommendation = "weak_reject"
    elif major >= 2:
        recommendation = "borderline"
    elif major >= 1:
        recommendation = "weak_accept"
    else:
        recommendation = "accept"

    # Rejection risk
    risk_score = min(0.95, critical * 0.25 + major * 0.08 + (len(deduped) - critical - major) * 0.02)
    risk_level = "low" if risk_score < 0.2 else "medium" if risk_score < 0.4 else "high" if risk_score < 0.6 else "very_high"

    return {
        "issues": deduped,
        "issue_count": {"critical": critical, "major": major, "minor": len(deduped) - critical - major},
        "recommendation": recommendation,
        "rejection_risk": {"score": round(risk_score, 3), "level": risk_level},
    }


# === Dashboard Generator ===

def generate_dashboard(checkpoint: Checkpoint, aggregated: dict | None = None) -> str:
    """Generate an HTML dashboard showing pipeline status and results."""
    d = checkpoint.data
    gates = d.get("gates_completed", {})

    gate_rows = ""
    for gate_name in GATES:
        if gate_name in gates:
            g = gates[gate_name]
            status = g.get("status", "?")
            issues = len(g.get("issues", []))
            dur = g.get("duration_seconds", 0)
            color = {"pass": "#22ddcc", "warn": "#ffaa22", "fail": "#ff4d4d",
                     "skip": "#888", "error": "#ff4d4d", "timeout": "#ffaa22"}.get(status, "#888")
            gate_rows += f'<tr><td>{gate_name}</td><td style="color:{color}">{status.upper()}</td><td>{issues}</td><td>{dur:.1f}s</td></tr>\n'
        elif gate_name in d.get("gates_pending", []):
            gate_rows += f'<tr><td>{gate_name}</td><td style="color:#ffaa22">RUNNING</td><td>-</td><td>-</td></tr>\n'
        else:
            gate_rows += f'<tr><td>{gate_name}</td><td style="color:#555">PENDING</td><td>-</td><td>-</td></tr>\n'

    issue_rows = ""
    if aggregated:
        for issue in aggregated.get("issues", [])[:20]:
            sev = issue["severity"]
            color = {"critical": "#ff4d4d", "major": "#ffaa22", "minor": "#888"}.get(sev, "#888")
            issue_rows += (
                f'<tr><td style="color:{color}">{sev.upper()}</td>'
                f'<td>{issue.get("id", "?")}</td>'
                f'<td>{issue.get("title", "?")}</td>'
                f'<td>{issue.get("confidence", 0):.0%}</td>'
                f'<td>{", ".join(issue.get("detected_by", []))}</td></tr>\n'
            )

    risk_html = ""
    if aggregated and "rejection_risk" in aggregated:
        rr = aggregated["rejection_risk"]
        risk_color = {"low": "#22ddcc", "medium": "#ffaa22", "high": "#ff8833", "very_high": "#ff4d4d"}.get(rr["level"], "#888")
        risk_html = f'<div style="font-size:48px;color:{risk_color};font-weight:700">{rr["score"]:.0%}</div><div>Rejection Risk: {rr["level"].upper()}</div>'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Research Guardian Dashboard</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'IBM Plex Sans',system-ui,sans-serif; background:#0a0a0f; color:#e8e6e3; padding:24px; }}
  h1 {{ font-size:20px; margin-bottom:4px; }}
  .meta {{ font-size:12px; color:#888; margin-bottom:20px; font-family:monospace; }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:20px; }}
  .card {{ background:#141419; border:1px solid #2a2a35; border-radius:8px; padding:16px; }}
  .card h2 {{ font-size:14px; color:#888; margin-bottom:12px; text-transform:uppercase; letter-spacing:1px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; color:#888; padding:6px 8px; border-bottom:1px solid #2a2a35; font-weight:500; }}
  td {{ padding:6px 8px; border-bottom:1px solid #1a1a22; }}
  .status-badge {{ display:inline-block; padding:2px 10px; border-radius:4px; font-size:11px; font-weight:600; }}
  .risk-box {{ text-align:center; padding:24px; }}
  .rec {{ font-size:24px; font-weight:700; margin:8px 0; }}
  .timestamp {{ font-size:11px; color:#555; font-family:monospace; }}
</style></head><body>
<h1>Research Guardian v{VERSION} — Dashboard</h1>
<div class="meta">
  Run: {d.get("run_id", "?")} | Paper: {d.get("paper_id", "?")} | Mode: {d.get("mode", "?").upper()} | Status: {d.get("status", "?").upper()}
  {f' | Escalated from: {d.get("escalated_from")}' if d.get("escalated_from") else ""}
</div>

<div class="grid">
  <div class="card">
    <h2>Gate Status</h2>
    <table>
      <tr><th>Gate</th><th>Status</th><th>Issues</th><th>Time</th></tr>
      {gate_rows}
    </table>
  </div>
  <div class="card risk-box">
    <h2>Rejection Risk</h2>
    {risk_html if risk_html else '<div style="color:#555">Pending...</div>'}
    {f'<div class="rec" style="color:#22ddcc">{aggregated["recommendation"].upper()}</div>' if aggregated else ""}
  </div>
</div>

<div class="card">
  <h2>Issues ({aggregated["issue_count"]["critical"]}C / {aggregated["issue_count"]["major"]}M / {aggregated["issue_count"]["minor"]}m)</h2>
  <table>
    <tr><th>Severity</th><th>ID</th><th>Title</th><th>Confidence</th><th>Detected By</th></tr>
    {issue_rows}
  </table>
</div>

{f'<div class="card"><h2>Errors</h2><pre style="font-size:12px;color:#ff4d4d">' + chr(10).join(d.get("error_log", [])) + '</pre></div>' if d.get("error_log") else ""}

<div class="timestamp">Generated: {now_iso()} | Checkpoint: {checkpoint.path}</div>
</body></html>"""

    return html


# === Main Pipeline ===

def run_pipeline(input_path: str, mode: str = "auto", preset: str = "", resume: bool = False):
    """Main entry point for the review pipeline."""
    ensure_dirs()

    # Resume from checkpoint if requested
    if resume:
        cp = Checkpoint.load_latest()
        if cp and cp.is_resumable:
            print(f"Resuming run {cp.data['run_id']} (status: {cp.data['status']})")
            cp.data["status"] = "resuming"
            cp.save()
            # Try to read original input from checkpoint's stored path
            stored_path = cp.data.get("input_path", "")
            if stored_path and Path(stored_path).exists():
                input_text = Path(stored_path).read_text(encoding="utf-8")
            else:
                print(f"⚠ Original input not found at '{stored_path}'. Provide input path as argument.")
                print(f"  Usage: python runner.py resume <input_file>")
                if input_path and Path(input_path).is_file():
                    input_text = Path(input_path).read_text(encoding="utf-8")
                else:
                    return
            paper_id = cp.data["paper_id"]
        else:
            print("No resumable checkpoint found.")
            return
    else:
        input_text = Path(input_path).read_text(encoding="utf-8")
        paper_id = make_paper_id(input_path)
        run_id = make_run_id(input_path)

        # Pre-scan (content-aware routing)
        scan = pre_scan(input_text)
        print(f"Pre-scan: risk={scan['risk']}, mode={scan['suggested_mode']}")
        if scan['domains']:
            print(f"  Domains: {[d['domain'] + '(' + d['confidence'] + ')' for d in scan['domains']]}")
        if scan['study_type']:
            print(f"  Study type: {scan['study_type']}")
        if scan['stat_framework']:
            print(f"  Stat framework: {scan['stat_framework']}")
        if scan['sub_modules_to_load']:
            print(f"  Sub-modules: {scan['sub_modules_to_load']}")

        if mode == "auto":
            mode = scan["suggested_mode"]

        gate_list = PRESETS.get(preset, MODES.get(mode, GATES))
        cp = Checkpoint(run_id, paper_id, mode, preset)
        cp.data["input_path"] = str(Path(input_path).resolve())
        cp.data["gates_pending"] = list(gate_list)
        cp.save()

        print(f"Starting run {run_id} | mode={mode} | gates={len(gate_list)}")

    # Determine remaining gates
    gate_list = PRESETS.get(cp.data.get("preset", ""), MODES.get(cp.data["mode"], GATES))
    remaining = cp.get_remaining_gates(gate_list)
    print(f"Gates to run: {remaining}")

    # Run gates (in production: parallel via asyncio)
    for gate_name in remaining:
        try:
            print(f"  Running {gate_name}...")
            result = run_gate(gate_name, input_text, cp)
            print(f"  {gate_name}: {result['status']} ({len(result['issues'])} issues)")
        except KeyboardInterrupt:
            print(f"\nInterrupted! Checkpoint saved at {cp.path}")
            cp.mark_interrupted()
            return
        except Exception as e:
            print(f"  {gate_name}: ERROR — {e}")
            cp.mark_gate_error(gate_name, str(e))

    # Escalation check
    all_issues = []
    for g in cp.data["gates_completed"].values():
        all_issues.extend(g.get("issues", []))
    critical_count = sum(1 for i in all_issues if i.get("severity") == "critical")

    if cp.data["mode"] == "quick" and (critical_count > 0 or len(all_issues) > 3):
        print("Escalating from QUICK to STANDARD...")
        cp.mark_escalated("quick", "standard")
        remaining = cp.get_remaining_gates(MODES["standard"])
        for gate_name in remaining:
            run_gate(gate_name, input_text, cp)

    if cp.data["mode"] == "standard" and critical_count > 0:
        print("Escalating from STANDARD to FULL...")
        cp.mark_escalated("standard", "full")
        remaining = cp.get_remaining_gates(MODES["full"])
        for gate_name in remaining:
            run_gate(gate_name, input_text, cp)

    # Aggregate
    aggregated = aggregate_results(cp.data["gates_completed"])

    # Generate outputs
    report = {
        "paper_id": paper_id,
        "run_id": cp.data["run_id"],
        "mode": cp.data["mode"],
        "preset": cp.data.get("preset", ""),
        "gate_results": cp.data["gates_completed"],
        "issues": aggregated["issues"],
        "issue_count": aggregated["issue_count"],
        "recommendation": aggregated["recommendation"],
        "rejection_risk": aggregated["rejection_risk"],
        "version": VERSION,
    }

    # Write JSON
    json_path = OUTPUT_DIR / "json" / f"{paper_id}.review.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # Write Markdown
    md = generate_markdown(report)
    md_path = OUTPUT_DIR / "markdown" / f"{paper_id}.review.md"
    md_path.write_text(md)

    # Write Dashboard
    dashboard_html = generate_dashboard(cp, aggregated)
    DASHBOARD_PATH.write_text(dashboard_html)

    cp.mark_complete()

    print(f"\n✅ Review complete!")
    print(f"  JSON:      {json_path}")
    print(f"  Markdown:  {md_path}")
    print(f"  Dashboard: {DASHBOARD_PATH}")
    print(f"  Checkpoint: {cp.path}")
    print(f"  Recommendation: {aggregated['recommendation']}")
    print(f"  Rejection Risk: {aggregated['rejection_risk']['score']:.0%} ({aggregated['rejection_risk']['level']})")


def generate_markdown(report: dict) -> str:
    """Generate Markdown review report."""
    ic = report.get("issue_count", {})
    rr = report.get("rejection_risk", {})
    lines = [
        f"# Research Guardian Review: {report['paper_id']}",
        f"",
        f"**Mode**: {report['mode'].upper()} | **Recommendation**: {report['recommendation'].upper()} | **Rejection Risk**: {rr.get('score', 0):.0%} ({rr.get('level', '?')})",
        f"",
        f"## Issue Summary",
        f"- Critical: {ic.get('critical', 0)}",
        f"- Major: {ic.get('major', 0)}",
        f"- Minor: {ic.get('minor', 0)}",
        f"",
        f"## Issues",
    ]
    for issue in report.get("issues", []):
        sev = issue.get("severity", "?").upper()
        lines.append(f"### [{sev}] {issue.get('id', '?')}: {issue.get('title', '?')}")
        lines.append(f"{issue.get('description', '')}")
        if issue.get("suggested_fix"):
            lines.append(f"**Fix**: {issue['suggested_fix']}")
        lines.append("")

    return "\n".join(lines)


# === CLI ===

def show_status():
    """Show status of latest run."""
    cp = Checkpoint.load_latest()
    if not cp:
        # Check for any completed checkpoints
        if CHECKPOINT_DIR.exists():
            files = sorted(CHECKPOINT_DIR.glob("*.checkpoint.json"), reverse=True)
            if files:
                data = json.loads(files[0].read_text())
                print(f"Latest run: {data['run_id']} — {data['status'].upper()}")
                print(f"  Paper: {data['paper_id']}")
                print(f"  Mode: {data['mode']}")
                completed = len(data.get('gates_completed', {}))
                print(f"  Gates: {completed} completed")
                return
        print("No runs found.")
        return

    d = cp.data
    print(f"Run: {d['run_id']} — {d['status'].upper()}")
    print(f"  Paper: {d['paper_id']}")
    print(f"  Mode: {d['mode']}")
    print(f"  Started: {d['started_at']}")
    print(f"  Gates completed: {list(d['gates_completed'].keys())}")
    print(f"  Gates pending: {d['gates_pending']}")
    if d.get("error_log"):
        print(f"  Errors: {len(d['error_log'])}")
    print(f"  Checkpoint: {cp.path}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "review":
        input_path = sys.argv[2] if len(sys.argv) > 2 else None
        if not input_path:
            print("Usage: python runner.py review <input_file> [--mode quick|standard|full] [--preset ml|clinical|socsci|sr|proposal]")
            return

        mode = "auto"
        preset = ""
        for i, arg in enumerate(sys.argv):
            if arg == "--mode" and i + 1 < len(sys.argv):
                mode = sys.argv[i + 1]
            if arg == "--preset" and i + 1 < len(sys.argv):
                preset = sys.argv[i + 1]

        run_pipeline(input_path, mode=mode, preset=preset)

    elif cmd == "resume":
        input_path = sys.argv[2] if len(sys.argv) > 2 else ""
        run_pipeline(input_path, resume=True)

    elif cmd == "status":
        show_status()

    elif cmd == "dashboard":
        cp = Checkpoint.load_latest()
        if not cp:
            files = sorted(CHECKPOINT_DIR.glob("*.checkpoint.json"), reverse=True)
            if files:
                cp = Checkpoint.__new__(Checkpoint)
                cp.path = files[0]
                cp.data = json.loads(files[0].read_text())
        if cp:
            html = generate_dashboard(cp)
            DASHBOARD_PATH.write_text(html)
            print(f"Dashboard written to {DASHBOARD_PATH}")
        else:
            print("No checkpoint found to generate dashboard from.")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
