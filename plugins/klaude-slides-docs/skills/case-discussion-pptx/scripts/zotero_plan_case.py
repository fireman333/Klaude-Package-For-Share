#!/usr/bin/env python3
"""
case-discussion adapter for the shared Zotero archiving planner.

Serves BOTH case-discussion-pptx and case-discussion-docx (they share the same
case CONTENT.discussionTrail). Thin wrapper over `lib/zotero_archive`:
parses the discussionTrail into the normalized spec, then calls the
skill-agnostic `build_plan`. Deterministic — does NOT touch Zotero.

Folder model:
  parent  = "Case Discussions"
  report  = "<YYYY-MM> <case title>"     (母夾)
  subfolder per discussion QUESTION      (Q1, Q2, … — like jc-pptx)

The new wrinkle vs other adapters: discussionTrail citations are PROSE strings,
e.g. "[1] PMID 12345 — Smith AB. NEJM 2020;383:1—9" or "[2] DOI 10.x — …" or
even "[3] Beets-Tan RGH. Eur Radiol 2018" (no PMID/DOI at all). This adapter
regex-extracts pmid/doi and keeps the human-readable remainder as the title. A
citation with neither pmid nor doi is still emitted (title = the prose) so it
surfaces at show→confirm — EXECUTION.md step 3 records it on the skip list
rather than dropping it.

Input (agent-dumped from CONTENT.discussionTrail):
  discussion_trail.json  — a JSON array of entries, index-ordered:
      [{"question": "...", "citations": ["[1] PMID 12345 — …", ...], ...}, ...]

Output (stdout, and --out if given): the archiving plan JSON, shape defined by
`lib/zotero_archive`.

Usage:
  python3 zotero_plan_case.py discussion_trail.json --topic "<case title>" \
      [--date 2026-06] [--parent "Case Discussions"] [--out plan.json]
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

_COMMON_DIR = Path(__file__).resolve().parent.parent / "lib"
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from zotero_archive import build_plan, clean_str  # noqa: E402

QTEXT_MAX = 50

_PMID_RE = re.compile(r"PMID[:\s#]*(\d+)", re.I)
_DOI_RE = re.compile(r"(10\.\d{4,9}/\S+)")
_DOI_TOKEN_RE = re.compile(r"(?:DOI[:\s]*)?10\.\d{4,9}/\S+", re.I)
_LEAD_RE = re.compile(r"^\s*\[\d+\]\s*")  # leading "[N] "


def _clean_doi(d: str) -> str:
    """Trim trailing prose punctuation off a greedily-captured DOI while keeping
    balanced internal parens (legacy Wiley/SICI DOIs contain them)."""
    d = d.rstrip(".,;")
    for close, opn in ((")", "("), ("]", "["), ("}", "{")):
        while d.endswith(close) and d.count(close) > d.count(opn):
            d = d[:-1].rstrip(".,;")
    return d


def _load(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"[zotero_plan_case] file not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"[zotero_plan_case] invalid JSON in {path}: {e}")


def parse_citation(s) -> dict:
    """Pull pmid/doi out of a discussionTrail prose citation; keep the rest as
    the display title. Returns {} for an empty/non-string entry."""
    if not isinstance(s, str) or not s.strip():
        return {}
    s = s.strip()
    pm = _PMID_RE.search(s)
    do = _DOI_RE.search(s)
    pmid = pm.group(1) if pm else ""
    doi = _clean_doi(do.group(1)) if do else ""
    title = _LEAD_RE.sub("", s)            # drop leading [N]
    title = _PMID_RE.sub("", title)        # drop the PMID token
    title = _DOI_TOKEN_RE.sub("", title)   # drop the DOI token (± "DOI" word)
    title = title.strip(" .—–-:")          # tidy leftover separators
    return {"pmid": pmid, "doi": doi, "title": title or s}


def build_spec(trail, topic: str, parent: str) -> dict:
    if not isinstance(trail, list):
        sys.exit("[zotero_plan_case] discussion_trail.json must be a JSON array of entries")
    entries = trail

    if not topic:
        topic = "Untitled case"

    sections = []
    citations = []
    for i, e in enumerate(entries, 1):
        if not isinstance(e, dict):
            print(f"[zotero_plan_case] WARNING: skipping non-dict discussionTrail "
                  f"entry {i}", file=sys.stderr)
            continue
        qid = f"Q{i}"
        qtext = clean_str(e.get("question"))
        label = qtext[:QTEXT_MAX].rstrip()
        sections.append({"id": qid, "label": f"{qid}: {label}" if label else qid})
        cits = e.get("citations")
        if isinstance(cits, str):
            cits = [cits]  # tolerate a single citation passed as a bare string
        elif not isinstance(cits, list):
            if cits is not None:
                print(f"[zotero_plan_case] WARNING: {qid} 'citations' is "
                      f"{type(cits).__name__}, expected list — ignored", file=sys.stderr)
            cits = []
        for cit in cits:
            rec = parse_citation(cit)
            if not rec:
                continue
            rec["in_sections"] = [qid]
            citations.append(rec)

    return {
        "parent": parent,
        "topic": topic,
        "primary": None,            # a patient case has no primary publication
        "sections": sections,
        "citations": citations,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a Zotero archiving plan for a case discussion.")
    ap.add_argument("discussion_trail", help="path to discussion_trail.json (CONTENT.discussionTrail dumped as JSON)")
    ap.add_argument("--topic", default="", help="case title (default: 'Untitled case')")
    ap.add_argument("--date", default="", help="YYYY-MM (default: current month)")
    ap.add_argument("--parent", default="Case Discussions", help="parent collection name")
    ap.add_argument("--out", default="", help="also write plan JSON to this path")
    args = ap.parse_args()

    date = args.date.strip() or datetime.date.today().strftime("%Y-%m")

    spec = build_spec(_load(args.discussion_trail), args.topic.strip(), args.parent)
    plan = build_plan(spec, date=date)

    out_str = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_str)
        print(f"[zotero_plan_case] wrote {args.out}", file=sys.stderr)
    print(out_str)
    s = plan["stats"]
    print(
        f"[zotero_plan_case] {s['n_sections']} question-folders, {s['n_papers']} paper-slots, "
        f"{s['n_doi_less']} DOI-less (PMID fallback)"
        + (f", {s['n_orphans']} ORPHAN section(s): {plan['orphan_sections']}"
           if s["n_orphans"] else ""),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
