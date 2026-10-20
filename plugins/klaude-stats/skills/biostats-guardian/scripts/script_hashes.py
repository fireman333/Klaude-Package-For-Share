#!/usr/bin/env python3
"""
Pipeline script integrity check — the deterministic replacement for Role 2 (Code Auditor).

Why this exists
---------------
Role 2 used to send one LLM subagent per pipeline step to read the pipeline's own
`.py` files. Those files are version-controlled and byte-identical across every
project, so the same 104 KB of `missing_data.py` was re-read on every step of every
run. Nothing was ever found. The information that actually matters is binary: *has
any of this code changed since the skill shipped it?* That is a hash comparison.

Contract
--------
  python script_hashes.py check   [--project-dir DIR] [--json OUT] [--baseline F]
  python script_hashes.py update  [--baseline F] [--note "reason"]

`check` exits 0 when everything matches the baseline (the caller then skips the code
audit entirely) and 1 when anything drifted (the caller then spawns exactly one
auditor, scoped to the drifted files only). Exit 2 means the check itself could not
run — a missing baseline is NOT "no changes", so it must never be read as a pass.

`update` regenerates the baseline. On first use after installing the plugin, run it once
(the shipped baseline is an empty placeholder, so `check` exits 2 until you do):

    python scripts/script_hashes.py update --note "first install"

Run `update` again only after you have deliberately changed a pipeline script. An agent
that finds drift may spawn a Code Auditor and report, and should not bless the drift away.

Optional hardening (off by default so a plain plugin install works):
  --require-clean-git   refuse unless the covered scripts are committed in a git repo
  --run-tests           run the bundled route/contract tests first and refuse on failure

`--project-dir` additionally hashes vendored copies of the pipeline scripts that
several skills drop next to their output (the "re-runnable script" convention). A
project-local copy that no longer matches the shipped file is exactly the case the
old Role 2 was supposed to catch. Project-local files are compared, never written
into the baseline.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

# Sibling skills live next to this one: <skills>/biostats-guardian/scripts/script_hashes.py
SKILLS_ROOT = str(Path(__file__).resolve().parents[2])
DEFAULT_BASELINE = os.environ.get("BIOSTATS_GUARDIAN_BASELINE") or str(
    Path(__file__).resolve().parents[1] / "baselines" / "pipeline_scripts.json")

# Optional: git working tree backing the skills directory (only used with --require-clean-git).
GIT_ROOT = os.path.dirname(os.path.realpath(SKILLS_ROOT))
SKILLS_PREFIX = os.path.basename(os.path.realpath(SKILLS_ROOT))

# Tests that must pass before a baseline can be blessed. Byte-identity says nothing
# about behaviour; these fixtures are the only thing that does.
GATE_TESTS = [
    "research-plan/scripts/test_routes_synthetic.py",
    "research-plan/scripts/test_pipeline_contract.py",
]

# An unattended auto-sync commit is not review. If HEAD looks like one, "committed"
# stops being evidence that a human saw the change.
AUTOSYNC_MARKERS = ("auto-sync", "autosync", "automated commit")

# Every directory whose .py files the deleted Role 2 used to read. Keep this list in
# sync with the skills that `research-plan` can put into a pipeline.
COVERED_DIRS = [
    "research-plan/scripts",
    # 看門狗本體（check_freshness.py）住在 assets/，不在 scripts/ 底下。漏掉它等於
    # 稽核工具自己不受稽核：改動看門狗的判準或閘門完全不會被 hash 比對抓到。
    "research-plan/assets",
    "table1/scripts",
    "flowchart/scripts",
    "kaplan-meier/scripts",
    "competing-risk/scripts",
    "univariate-forest/scripts",
    "multivariate-interaction/scripts",
    "psm-matching/scripts",
    "auc-cstat/scripts",
]

# Files that are expected to differ per project or are not part of the analysis path.
EXCLUDE_BASENAMES = {"__init__.py"}
EXCLUDE_DIR_PARTS = {"__pycache__", ".ruff_cache", ".pytest_cache"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def collect(skills_root=SKILLS_ROOT):
    """Return {relative_path: sha256} for every covered pipeline script."""
    out = {}
    for rel_dir in COVERED_DIRS:
        abs_dir = os.path.join(skills_root, rel_dir)
        if not os.path.isdir(abs_dir):
            continue
        for name in sorted(os.listdir(abs_dir)):
            if not name.endswith((".py", ".R")):
                continue
            if name in EXCLUDE_BASENAMES:
                continue
            abs_path = os.path.join(abs_dir, name)
            if not os.path.isfile(abs_path):
                continue
            out[f"{rel_dir}/{name}"] = sha256_file(abs_path)
    return out


def load_baseline(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _git(*argv):
    """Run a git command in the config repo. Returns (rc, stdout)."""
    r = subprocess.run(["git", "-C", GIT_ROOT, *argv],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout or "").strip()


def check_clean_tree():
    """(ok, detail). The baseline may only point at a committed state."""
    rc, _ = _git("rev-parse", "--git-dir")
    if rc != 0:
        return False, (f"{GIT_ROOT} is not a git repository, so a baseline cannot be "
                       f"tied to a commit. Refusing to bless an untraceable state.")
    paths = [f"{SKILLS_PREFIX}/{d}" for d in COVERED_DIRS]
    rc, out = _git("status", "--porcelain", "--", *paths)
    if rc != 0:
        return False, "git status failed; cannot establish whether the tree is clean."
    if out:
        listing = "\n    ".join(out.splitlines()[:20])
        return False, ("covered scripts have uncommitted changes; commit first — the "
                       "baseline must point at a commit:\n    " + listing)
    return True, ""


def run_gate_tests(skills_root=SKILLS_ROOT):
    """(ok, detail). Byte-identity is not behaviour; the fixtures are."""
    for rel in GATE_TESTS:
        path = os.path.join(skills_root, rel)
        if not os.path.exists(path):
            return False, (f"required test not found: {path}. A baseline may not be "
                           f"blessed without the fixtures that give it meaning.")
        r = subprocess.run([sys.executable, path], capture_output=True, text=True,
                           cwd=os.path.dirname(path))
        if r.returncode != 0:
            tail = "\n    ".join((r.stdout + r.stderr).strip().splitlines()[-15:])
            return False, (f"{rel} failed (exit {r.returncode}); refusing to bless code "
                           f"whose route tests do not pass:\n    " + tail)
    return True, ""


def cmd_update(args):
    note = args.note or "first install baseline"

    dirty_ok = True
    if args.require_clean_git:
        dirty_ok, dirty_detail = check_clean_tree()
        if not dirty_ok:
            print(f"[GUARDIAN_BLOCKING] {dirty_detail}", file=sys.stderr)
            return 2

    if args.run_tests:
        ok, detail = run_gate_tests()
        if not ok:
            print(f"[GUARDIAN_BLOCKING] {detail}", file=sys.stderr)
            return 2

    commit, subject = None, ""
    if os.path.isdir(os.path.join(GIT_ROOT, ".git")):
        rc, c = _git("rev-parse", "HEAD")
        commit = c if rc == 0 else None
        rc, sj = _git("log", "-1", "--pretty=%s")
        subject = sj if rc == 0 else ""

    hashes = collect()
    previous = {}
    if os.path.exists(args.baseline):
        try:
            previous = load_baseline(args.baseline).get("files", {})
        except Exception:
            previous = {}
    changed = sorted(set(
        [p for p in hashes if previous.get(p) != hashes[p]]
        + [p for p in previous if p not in hashes]))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
                "git_commit": commit,
        "git_subject": subject,
        "tree_clean": bool(dirty_ok),
        "tests_run": GATE_TESTS if args.run_tests else [],
        "note": note,
        "n_files": len(hashes),
        "changed_since_previous": changed,
        "files": hashes,
    }
    os.makedirs(os.path.dirname(args.baseline), exist_ok=True)
    with open(args.baseline, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Baseline written: {args.baseline} ({len(hashes)} files, "
          f"commit {commit or 'unknown'}, {len(changed)} changed since previous)")
    for p in changed[:20]:
        print(f"  blessed change: {p}")
    return 0


def scan_project_copies(project_dir, baseline_files):
    """Vendored copies of shipped scripts living in the project output directory."""
    by_basename = {}
    for rel, digest in baseline_files.items():
        by_basename.setdefault(os.path.basename(rel), []).append((rel, digest))

    findings = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_PARTS]
        for name in files:
            if name not in by_basename:
                continue
            abs_path = os.path.join(root, name)
            digest = sha256_file(abs_path)
            shipped = by_basename[name]
            if any(digest == d for _, d in shipped):
                findings.append({"path": abs_path, "status": "OK", "shipped_as": shipped[0][0]})
            else:
                findings.append({"path": abs_path, "status": "MODIFIED", "shipped_as": shipped[0][0],
                                 "sha256": digest})
    return findings


def cmd_check(args):
    first_run_msg = (f"[GUARDIAN_BLOCKING] no script hash baseline yet ({args.baseline}). "
                     f"First use: run `python scripts/script_hashes.py update --note \"first install\"` "
                     f"from the biostats-guardian skill folder once, then re-run check. "
                     f"A missing baseline is not a pass — or run the code audit manually.")
    if not os.path.exists(args.baseline):
        print(first_run_msg, file=sys.stderr)
        return 2

    baseline = load_baseline(args.baseline)
    if baseline.get("placeholder") or not baseline.get("files"):
        print(first_run_msg, file=sys.stderr)
        return 2
    expected = baseline["files"]
    current = collect()

    modified = sorted(p for p in expected if p in current and current[p] != expected[p])
    missing = sorted(p for p in expected if p not in current)
    added = sorted(p for p in current if p not in expected)

    project = scan_project_copies(args.project_dir, expected) if args.project_dir else []
    project_modified = [f for f in project if f["status"] == "MODIFIED"]

    drift = bool(modified or missing or added or project_modified)
    result = {
        "baseline": args.baseline,
        "baseline_generated_at": baseline.get("generated_at"),
        "n_checked": len(current),
        "modified": modified,
        "missing": missing,
        "added": added,
        "project_copies": project,
        "drift": drift,
        "audit_scope": modified + added + [f["path"] for f in project_modified],
    }

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
            f.write("\n")

    # Always say which blessing this is being judged against: "who blessed this
    # baseline, in what state" should be visible on every run, not archaeology.
    prov = (f"baseline: commit {baseline.get('git_commit') or 'unknown'}"
            f"{'' if baseline.get('tree_clean', True) else ' [DIRTY TREE]'}"
            f"{'' if baseline.get('tests_run') else ' [tests skipped]'}"
            f" — {baseline.get('note') or 'no note'}")
    print(prov)

    if not drift:
        print(f"pipeline 腳本未修改（{len(current)} 個檔案雜湊與出貨版一致），跳過程式稽核")
        return 0

    print(f"pipeline 腳本與出貨版不一致 — 需要對以下檔案派一隻 code auditor（共 {len(result['audit_scope'])} 個）:")
    for p in modified:
        print(f"  MODIFIED  {p}")
    for p in missing:
        print(f"  MISSING   {p}  (baseline 有、現在沒有)")
    for p in added:
        print(f"  ADDED     {p}  (baseline 沒有、現在有)")
    for f in project_modified:
        print(f"  PROJECT   {f['path']}  (vendored copy of {f['shipped_as']} has diverged)")
    return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="compare current scripts against the baseline")
    c.add_argument("--baseline", default=DEFAULT_BASELINE)
    c.add_argument("--project-dir", default=None, help="also check vendored copies under this directory")
    c.add_argument("--json", default=None, help="write the full result as JSON here")
    c.set_defaults(func=cmd_check)

    u = sub.add_parser("update",
                       help="regenerate the baseline (run once on first use; afterwards only after deliberate script changes)")
    u.add_argument("--baseline", default=DEFAULT_BASELINE)
    u.add_argument("--note", default=None,
                   help="why the baseline was regenerated (default: 'first install baseline')")
    u.add_argument("--require-clean-git", action="store_true",
                   help="refuse unless covered scripts are committed in a git repo")
    u.add_argument("--run-tests", action="store_true",
                   help="run the bundled route/contract tests first (slow, minutes)")
    u.set_defaults(func=cmd_update)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
