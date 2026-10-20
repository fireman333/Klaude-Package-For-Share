#!/usr/bin/env python3
"""Print formatted pipeline status from research_plan.json."""

import json
import os
import sys


STATUS_ICONS = {
    "done": "✓",
    "error": "✗",
    "pending": "○",
    "running": "▶",
    "needs_rerun": "↺",
    "skipped": "⊘",
    "blocked": "⛔",
}

# Guardian writeback uses [GUARDIAN_*]; treat it with the same severity as [QC_*],
# otherwise a guardian blocker is displayed as a mere warning.
BLOCKING_MARKERS = ("[QC_BLOCKING]", "[GUARDIAN_BLOCKING]")

# Skills that produce both .xlsx and .png
DUAL_OUTPUT_SKILLS = {
    "flowchart",
    "kaplan-meier",
    "competing-risk",
    "univariate-forest",
    "psm-matching",
    "missing-data",
}

# Skills whose PNG is not simply <output_file stem>.png.
# missing-data is resolved per step (assessment vs imputation), not by skill alone.
PNG_SUFFIX_OVERRIDES = {
    "psm-matching": "_loveplot",
}

PNG_NOTES = {
    "univariate-forest": "(forest plot)",
    "psm-matching": "(love plot)",
}


def load_plan(plan_path):
    with open(plan_path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_progress_bar(plan):
    """Print a one-line pipeline progress bar."""
    steps = plan["pipeline"]
    parts = []
    for step in steps:
        status = step.get("status", "pending")
        icon = STATUS_ICONS.get(status, "?")
        sid = step["id"]
        # Shorten step id for display
        short = sid[:12] + ".." if len(sid) > 14 else sid
        parts.append(f"[{icon}]{short}")
    print(f"  Pipeline: {' → '.join(parts)}")


def print_group_status(plan):
    """Print status organized by analysis groups."""
    groups = {}
    for step in plan["pipeline"]:
        skill = step["skill"]
        outcome = step.get("outcome")
        # Keep in step with run_pipeline.group_steps_by_analysis_group(): the
        # assessment step (`missingness`, no outcome) is Foundation, while
        # `mi_{outcome}` falls through to its outcome group below.
        if skill in ("flowchart", "table1") or (skill == "missing-data" and not outcome):
            gid = "Foundation"
        elif skill in ("manuscript-results", "strobe", "reviewer-challenge"):
            gid = "Manuscript"
        elif skill in ("psm-matching", "auc-cstat", "calibration", "weighting", "evalue"):
            gid = "Supplementary"
        elif outcome:
            gid = f"Outcome: {outcome}"
        else:
            gid = "Other"
        groups.setdefault(gid, []).append(step)

    for gid, steps in groups.items():
        step_strs = []
        for s in steps:
            icon = STATUS_ICONS.get(s.get("status", "pending"), "?")
            # Use skill name for brevity
            step_strs.append(f"[{icon}] {s['id']}")
        print(f"  {gid:<20s} {' '.join(step_strs)}")


def print_qc_warnings(plan):
    """Print collected QC warnings from all steps."""
    has_warnings = False
    for step in plan["pipeline"]:
        warnings = step.get("qc_warnings", [])
        if warnings:
            if not has_warnings:
                print("=" * 78)
                print("  Statistical QC Warnings")
                print("=" * 78)
                print()
                has_warnings = True
            for w in warnings:
                severity = "BLOCKING" if any(m in w for m in BLOCKING_MARKERS) else "WARNING"
                print(f"  {step['id']:<22s} [{severity}] {w.split('] ', 1)[-1] if '] ' in w else w}")
    if has_warnings:
        print()


def print_timing_stats(plan):
    """Print timing statistics."""
    runtimes = []
    for step in plan["pipeline"]:
        rt = step.get("runtime_seconds")
        if rt is not None:
            runtimes.append((step["id"], rt))
    if runtimes:
        total = sum(r for _, r in runtimes)
        avg = total / len(runtimes)
        slowest = max(runtimes, key=lambda x: x[1])
        print(f"  Timing: total {total:.1f}s │ avg {avg:.1f}s │ slowest: {slowest[0]} ({slowest[1]:.1f}s)")


def print_version_history(plan):
    """Print version history if available."""
    history = plan.get("version_history", [])
    if len(history) > 1:
        print("=" * 78)
        print("  Version History")
        print("=" * 78)
        print()
        for entry in history:
            print(f"  v{entry['version']}  {entry.get('created_at', '—')[:10]}  {entry.get('reason', '—')}")
        print()


def print_diff_report(plan, compare_version=None):
    """Compare current outputs with a previous version."""
    output_dir = plan["output_dir"]
    version = plan.get("version", 1)
    if compare_version is None:
        compare_version = version - 1
    if compare_version < 1:
        return

    backup_dir = os.path.join(output_dir, f"v{compare_version}")
    if not os.path.isdir(backup_dir):
        print(f"  No backup found for v{compare_version}")
        return

    print("=" * 78)
    print(f"  Diff Report (v{compare_version} → v{version})")
    print("=" * 78)
    print()

    # Compare file existence
    for step in plan["pipeline"]:
        output_base = step.get("output_file", step["id"])
        current = os.path.join(output_dir, f"{output_base}.xlsx")
        backup = os.path.join(backup_dir, f"{output_base}.xlsx")

        if os.path.exists(current) and os.path.exists(backup):
            # Both exist — report sizes as proxy for content change
            cur_size = os.path.getsize(current)
            bak_size = os.path.getsize(backup)
            changed = "changed" if cur_size != bak_size else "unchanged"
            print(f"  {step['id']:<22s} {changed} (v{compare_version}: {bak_size:,}B → v{version}: {cur_size:,}B)")
        elif os.path.exists(current) and not os.path.exists(backup):
            print(f"  {step['id']:<22s} NEW (not in v{compare_version})")
        elif not os.path.exists(current) and os.path.exists(backup):
            print(f"  {step['id']:<22s} REMOVED (was in v{compare_version})")
    print()


def print_status(plan_path):
    plan = load_plan(plan_path)
    output_dir = plan["output_dir"]
    tfm = plan.get("table_figure_mapping", {})

    title = plan["study"].get("title", "Research Plan")
    version = plan.get("version", 1)

    print()
    print("=" * 78)
    print(f"  Research Plan Pipeline Status")
    print(f"  Study: {title}")
    print(f"  Version: {version}")
    print("=" * 78)
    print()

    # Progress bar
    print_progress_bar(plan)
    print()

    # Group status
    print_group_status(plan)
    print()

    # Step table header
    print(f"  {'Step ID':<22s} {'Skill':<28s} {'Status':<12s} {'Time':<8s} {'Figure/Table'}")
    print(f"  {'─' * 74}")

    done_count = 0
    error_count = 0
    pending_count = 0
    error_steps = []

    for step in plan["pipeline"]:
        step_id = step["id"]
        skill = step["skill"]
        status = step.get("status", "pending")
        icon = STATUS_ICONS.get(status, "?")
        runtime = step.get("runtime_seconds")
        time_str = f"{runtime:.1f}s" if runtime is not None else "—"
        fig_table = tfm.get(step_id, "—")

        print(f"  {step_id:<22s} {skill:<28s} {icon} {status:<9s} {time_str:<8s} {fig_table}")

        if status == "done":
            done_count += 1
        elif status == "error":
            error_count += 1
            error_steps.append(step)
        else:
            pending_count += 1

    total = len(plan["pipeline"])
    print(f"  {'─' * 74}")
    print(f"  Summary: {done_count} done │ {error_count} error │ {pending_count} pending │ Total: {total} steps")

    # Timing statistics
    print_timing_stats(plan)
    print()

    # Output files
    print("=" * 78)
    print("  Output Files")
    print("=" * 78)
    print()

    found_files = []
    for step in plan["pipeline"]:
        step_id = step["id"]
        skill = step["skill"]
        output_base = step.get("output_file", step_id)
        fig_table = tfm.get(step_id, "")

        if skill == "manuscript-results":
            docx_path = os.path.join(output_dir, f"{output_base}.docx")
            if os.path.exists(docx_path):
                found_files.append((fig_table or "Results", docx_path, ""))
            continue

        # Check xlsx
        xlsx_path = os.path.join(output_dir, f"{output_base}.xlsx")
        if os.path.exists(xlsx_path):
            found_files.append((fig_table, xlsx_path, ""))

        # Check png
        if skill in DUAL_OUTPUT_SKILLS:
            suffix = PNG_SUFFIX_OVERRIDES.get(skill, "")
            if skill == "missing-data":
                # assessment -> Missingness_pattern.png; imputation -> MI_x_diagnostics.png
                suffix = "_pattern" if not step.get("outcome") else "_diagnostics"
            png_path = os.path.join(output_dir, f"{output_base}{suffix}.png")
            if os.path.exists(png_path):
                note = PNG_NOTES.get(skill, "")
                if skill == "missing-data":
                    note = "(missingness pattern)" if not step.get("outcome") else "(MI diagnostics)"
                found_files.append(("", png_path, note))

    if found_files:
        for label, path, note in found_files:
            note_str = f"  {note}" if note else ""
            print(f"  {label:<12s} │ {path}{note_str}")
    else:
        print("  No output files found yet.")
    print()

    # QC Warnings
    print_qc_warnings(plan)

    # Errors
    if error_steps:
        print("=" * 78)
        print("  Errors")
        print("=" * 78)
        print()
        for step in error_steps:
            step_id = step["id"]
            msg = step.get("error_message", "Unknown error")
            log_path = os.path.join(output_dir, "logs", f"{step_id}.log")
            print(f"  {step_id}: {msg[:100]}")
            if os.path.exists(log_path):
                print(f"    Log: {log_path}")
        print()

    # Version history
    print_version_history(plan)

    print("=" * 78)
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Print pipeline status")
    parser.add_argument("plan_path", help="Path to research_plan.json")
    parser.add_argument("--diff", type=int, metavar="VERSION", help="Compare with this version")
    args = parser.parse_args()

    if not os.path.exists(args.plan_path):
        print(f"Error: File not found: {args.plan_path}")
        sys.exit(1)
    print_status(args.plan_path)
    if args.diff is not None:
        plan = load_plan(args.plan_path)
        print_diff_report(plan, args.diff)
