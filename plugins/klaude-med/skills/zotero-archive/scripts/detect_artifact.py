#!/usr/bin/env python3
"""
Detect which report artifact lives in a directory and print the exact
zotero_archive adapter invocation to run for it.

Powers `/zotero-archive archive` — lets you archive an existing report (jc-pptx /
SR / case) without re-running the whole source skill. Pure
filesystem inspection; does NOT touch Zotero.

Signature files (first match wins, in this precedence order):
  synthesis.json   + bibliography.json      -> SR            (deep-research)
  research_findings.json + structured.json  -> journal club  (jc-pptx)
  discussion_trail.json                     -> case          (case-discussion-*)

Usage:
  python3 detect_artifact.py [<dir>]        # default: current dir
  python3 detect_artifact.py <dir> --json   # machine-readable result
"""
import argparse
import json
import shlex
import sys
from pathlib import Path

# sibling skills live next to this skill folder (same plugin)
SKILLS = Path(__file__).resolve().parent.parent.parent

# (adapter relative path, [required signature files], [optional files])
ADAPTERS = [
    ("sr", "deep-research/scripts/zotero_plan_sr.py",
     ["synthesis.json", "bibliography.json"], ["rq_brief.json"]),
    ("journal-club", "journal-club-discussion-pptx/scripts/zotero_plan.py",
     ["research_findings.json", "structured.json"], []),
    ("case", "case-discussion-pptx/scripts/zotero_plan_case.py",
     ["discussion_trail.json"], []),
]


def detect(d: Path) -> dict:
    present = {p.name for p in d.iterdir() if p.is_file()} if d.is_dir() else set()
    matches = []
    for kind, adapter, required, optional in ADAPTERS:
        if (SKILLS / adapter).exists() and all(f in present for f in required):
            args = [shlex.quote(str(d / f)) for f in required]
            for f in optional:
                if f in present and f == "rq_brief.json":
                    args += ["--rq-brief", shlex.quote(str(d / f))]
            cmd = (f"python3 {shlex.quote(str(SKILLS / adapter))} " + " ".join(args)
                   + ' --topic "<topic>" --out /tmp/zotero_plan.json')
            matches.append({"kind": kind, "command": cmd, "matched_on": required})
    return {"dir": str(d), "present": sorted(present), "matches": matches}


def main() -> None:
    ap = argparse.ArgumentParser(description="Detect a report artifact and print its zotero_archive adapter command.")
    ap.add_argument("dir", nargs="?", default=".", help="directory to scan (default: cwd)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    d = Path(args.dir).expanduser().resolve()
    if not d.is_dir():
        print(f"[detect] not a directory: {d}", file=sys.stderr)
        sys.exit(2)
    res = detect(d)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if not res["matches"]:
        print(f"[detect] no recognized report artifact in {d}", file=sys.stderr)
        print("[detect] expected one of: synthesis.json+bibliography.json | "
              "research_findings.json+structured.json | "
              "discussion_trail.json", file=sys.stderr)
        sys.exit(2)
    if len(res["matches"]) > 1:
        kinds = ", ".join(m["kind"] for m in res["matches"])
        print(f"[detect] AMBIGUOUS — multiple artifacts match ({kinds}); pick one:",
              file=sys.stderr)
    for m in res["matches"]:
        print(f"# {m['kind']} (matched on {', '.join(m['matched_on'])})")
        print(m["command"])


if __name__ == "__main__":
    main()
