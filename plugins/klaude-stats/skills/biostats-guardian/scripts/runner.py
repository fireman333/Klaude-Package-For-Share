#!/usr/bin/env python3
"""
Biostats Guardian — CLI helper.

This script does NOT spawn subagents (that is Claude's job via the Agent tool).
It only validates, aggregates, and formats the JSON artifacts that subagents
produce, and writes back Role 3 issues into research_plan.json's qc_warnings[].

Subcommands:
  validate   Validate a single RoleReport JSON against the schema.
  aggregate  Merge multiple RoleReport JSONs into one GuardianReport JSON.
  summary    Print a 繁中 summary of an existing GuardianReport.
  writeback  Append Role 3 issues into research_plan.pipeline[*].qc_warnings[]
             as [GUARDIAN_WARNING] / [GUARDIAN_BLOCKING] strings.

All I/O is via file paths; stdout is reserved for human-readable summaries.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow running as `python runner.py ...` from anywhere.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from issue_schema import (  # noqa: E402
    GuardianReport,
    Issue,
    RoleReport,
    Severity,
    ValidationError,
    aggregate,
    now_iso,
    validate_report_dict,
)

try:
    from pydantic import BaseModel  # noqa: F401
    PYDANTIC_V2 = True
    try:
        from pydantic import TypeAdapter
    except ImportError:
        PYDANTIC_V2 = False
except ImportError:
    PYDANTIC_V2 = False


# ---------- Helpers ----------

def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _validate_role_report(data: dict) -> RoleReport:
    """Parse a dict into a RoleReport, raising ValidationError on failure."""
    if PYDANTIC_V2:
        return RoleReport.model_validate(data)
    return RoleReport.parse_obj(data)  # type: ignore[attr-defined]


def _report_to_dict(model) -> dict:
    if PYDANTIC_V2:
        return model.model_dump(mode="json", exclude_none=True)
    return json.loads(model.json(exclude_none=True))  # type: ignore[attr-defined]


# ---------- Subcommand: validate ----------

def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.report).expanduser().resolve()
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    try:
        data = _load_json(path)
        report = _validate_role_report(data)
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in {path}: {e}", file=sys.stderr)
        return 2
    except ValidationError as e:
        print(f"ERROR: schema validation failed for {path}:\n{e}", file=sys.stderr)
        return 2

    print(f"OK  {path.name}: role={report.role.value} skill={report.skill} "
          f"status={report.status} issues={len(report.issues)}")
    return 0


# ---------- Subcommand: aggregate ----------

def cmd_aggregate(args: argparse.Namespace) -> int:
    report_paths = [Path(p).expanduser().resolve() for p in args.reports]
    role_reports: list[RoleReport] = []
    errors: list[str] = []

    for p in report_paths:
        if not p.exists():
            errors.append(f"missing file: {p}")
            continue
        try:
            data = _load_json(p)
            role_reports.append(_validate_role_report(data))
        except json.JSONDecodeError as e:
            errors.append(f"{p.name}: invalid JSON — {e}")
        except ValidationError as e:
            errors.append(f"{p.name}: schema error — {e.errors() if hasattr(e, 'errors') else e}")

    # bg-B-1 / bg-R2-1 audit fix (2026-05-08): expected-manifest validation.
    # Previously aggregate had no way to know if subagents were missing — quick
    # mode (7 expected) with 1-2 timeouts could silently pass aggregate as
    # "OK with 5 reports" even though 2 expected reports never arrived.
    # Now: if --expected-manifest is provided, load list of expected
    # (role, skill, step_id) tuples and append _meta error for any missing.
    if args.expected_manifest:
        try:
            manifest_path = Path(args.expected_manifest).expanduser().resolve()
            manifest_data = _load_json(manifest_path)
            expected: list[dict] = manifest_data.get("expected_roles", [])
            seen: set[tuple] = {
                (r.role.value, r.skill, r.step_id) for r in role_reports
            }
            missing: list[str] = []
            for exp in expected:
                key = (exp.get("role"), exp.get("skill"), exp.get("step_id"))
                # Match exact, or match (role, skill, None) when step_id wildcards
                if key not in seen and (key[0], key[1], None) not in seen:
                    missing.append(f"{exp.get('role')}/{exp.get('skill')}/{exp.get('step_id') or '*'}")
            if missing:
                errors.append(
                    f"{len(missing)} expected role-report(s) missing per manifest "
                    f"{manifest_path.name}: {', '.join(missing)}"
                )
        except (json.JSONDecodeError, OSError, KeyError) as e:
            errors.append(f"expected_manifest load error: {e}")

    if errors and args.strict:
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 2

    # Attach error placeholders so aggregated status reflects bad inputs.
    if errors:
        role_reports.append(RoleReport(
            role="column" if args.phase == "pre" else "results",
            skill="_meta",
            status="error",
            issues=[],
            summary=f"{len(errors)} report file(s) failed to load or expected manifest issue: {'; '.join(errors)}",
            completed_at=now_iso(),
        ))

    guardian = aggregate(
        role_reports=role_reports,
        phase=args.phase,
        mode=args.mode,
        plan_path=args.plan,
    )

    out_path = Path(args.out).expanduser().resolve()
    _dump_json(out_path, _report_to_dict(guardian))

    # Human-readable summary to stdout
    _print_summary(guardian)
    print(f"\nWrote: {out_path}")

    if guardian.aggregated_status == "error":
        return 2
    if guardian.aggregated_status == "block":
        return 1
    return 0


# ---------- Subcommand: summary ----------

def cmd_summary(args: argparse.Namespace) -> int:
    path = Path(args.report).expanduser().resolve()
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    try:
        data = _load_json(path)
        guardian = validate_report_dict(data)
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"ERROR: cannot parse {path}: {e}", file=sys.stderr)
        return 2

    _print_summary(guardian)
    return 0


def _print_summary(guardian: GuardianReport) -> None:
    phase_name = {"pre": "Pre-execution", "post": "Post-execution", "ad-hoc": "Ad-hoc"}.get(
        guardian.phase, guardian.phase
    )
    banner = f"Biostats Guardian 審查摘要（{phase_name}, {guardian.mode} mode）"
    bar = "─" * len(banner)
    print(banner)
    print(bar)

    # Group role_reports by skill for display
    by_skill: dict[str, list[RoleReport]] = {}
    for r in guardian.role_reports:
        by_skill.setdefault(r.skill, []).append(r)

    pass_skills = [s for s, reps in by_skill.items()
                   if all(r.status == "pass" for r in reps)]
    warn_skills = [s for s, reps in by_skill.items()
                   if any(r.status == "warn" for r in reps)
                   and not any(r.status in ("block", "error") for r in reps)]
    block_skills = [s for s, reps in by_skill.items()
                    if any(r.status in ("block", "error") for r in reps)]

    total = len(by_skill)
    print(f"✅ 通過：{len(pass_skills)}/{total} skills")
    if warn_skills:
        print(f"⚠️  警告：{len(warn_skills)} skills")
        for s in warn_skills:
            for rep in by_skill[s]:
                for issue in rep.issues:
                    if issue.severity == Severity.WARN:
                        print(f"  - {s}: {issue.check_id} {issue.message}")
    if block_skills:
        print(f"🛑 阻擋：{len(block_skills)} skills")
        for s in block_skills:
            for rep in by_skill[s]:
                for issue in rep.issues:
                    if issue.severity == Severity.BLOCK:
                        print(f"  - {s}: {issue.check_id} {issue.message}")

    counts = guardian.issue_count
    print(f"\n總計 issues: block={counts.get('block', 0)} "
          f"warn={counts.get('warn', 0)} uncertain={counts.get('uncertain', 0)}")
    print(f"aggregated_status: {guardian.aggregated_status}")


# ---------- Subcommand: writeback ----------

def cmd_writeback(args: argparse.Namespace) -> int:
    """Append Role 3 issues into research_plan.json's qc_warnings[] fields."""
    plan_path = Path(args.plan).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve()
    if not plan_path.exists():
        print(f"ERROR: plan not found: {plan_path}", file=sys.stderr)
        return 2
    if not report_path.exists():
        print(f"ERROR: report not found: {report_path}", file=sys.stderr)
        return 2

    try:
        plan_data = _load_json(plan_path)
        report_data = _load_json(report_path)
        guardian = validate_report_dict(report_data)
    except (json.JSONDecodeError, ValidationError) as e:
        print(f"ERROR: cannot parse inputs: {e}", file=sys.stderr)
        return 2

    pipeline = plan_data.get("pipeline", [])
    if not isinstance(pipeline, list):
        print("ERROR: research_plan.pipeline is missing or not a list", file=sys.stderr)
        return 2

    # Build step_id -> index map
    idx_by_step: dict[str, int] = {}
    for i, step in enumerate(pipeline):
        sid = step.get("id") or step.get("step_id")
        if sid:
            idx_by_step[sid] = i

    added = 0
    skipped = 0
    for role_report in guardian.role_reports:
        if role_report.role.value != "results":
            continue
        sid = role_report.step_id
        if not sid or sid not in idx_by_step:
            skipped += len(role_report.issues)
            continue
        step = pipeline[idx_by_step[sid]]
        step.setdefault("qc_warnings", [])
        existing = set(step["qc_warnings"])
        for issue in role_report.issues:
            if issue.severity == Severity.BLOCK:
                tag = "[GUARDIAN_BLOCKING]"
            elif issue.severity == Severity.WARN:
                tag = "[GUARDIAN_WARNING]"
            else:
                continue
            line = f"{tag} {issue.check_id} {sid}: {issue.message}"
            if line not in existing:
                step["qc_warnings"].append(line)
                existing.add(line)
                added += 1

    _dump_json(plan_path, plan_data)
    print(f"Wrote {added} guardian warning line(s) into {plan_path.name} "
          f"(skipped {skipped} orphan issue(s) with no matching step_id)")
    return 0


# ---------- CLI ----------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="biostats-guardian-runner",
        description="Validate/aggregate Biostats Guardian subagent reports.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_val = sub.add_parser("validate", help="Validate one RoleReport JSON.")
    p_val.add_argument("--report", required=True, help="Path to RoleReport JSON.")
    p_val.set_defaults(func=cmd_validate)

    p_agg = sub.add_parser("aggregate", help="Aggregate multiple RoleReports into a GuardianReport.")
    p_agg.add_argument("--phase", choices=["pre", "post", "ad-hoc"], required=True)
    p_agg.add_argument("--mode", choices=["off", "quick", "standard", "full"], required=True)
    p_agg.add_argument("--plan", default=None, help="Path to research_plan.json (optional, recorded in report).")
    p_agg.add_argument("--reports", nargs="+", required=True, help="Paths to RoleReport JSON files.")
    p_agg.add_argument("--out", required=True, help="Output path for GuardianReport JSON.")
    p_agg.add_argument("--strict", action="store_true", help="Fail (exit 2) if any input is malformed.")
    p_agg.add_argument(
        "--expected-manifest", default=None,
        help="Optional path to JSON manifest listing expected role-reports "
             "(format: {\"expected_roles\": [{\"role\": \"column\", \"skill\": \"table1\", "
             "\"step_id\": \"step1\"}, ...]}). bg-B-1 audit fix: when provided, missing "
             "expected reports become _meta errors so partial-failure isn't silent."
    )
    p_agg.set_defaults(func=cmd_aggregate)

    p_sum = sub.add_parser("summary", help="Print a 繁中 summary of an existing GuardianReport.")
    p_sum.add_argument("--report", required=True, help="Path to GuardianReport JSON.")
    p_sum.set_defaults(func=cmd_summary)

    p_wb = sub.add_parser("writeback", help="Write Role 3 issues back into research_plan.json qc_warnings[].")
    p_wb.add_argument("--plan", required=True, help="Path to research_plan.json (edited in place).")
    p_wb.add_argument("--report", required=True, help="Path to post-phase GuardianReport JSON.")
    p_wb.set_defaults(func=cmd_writeback)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
