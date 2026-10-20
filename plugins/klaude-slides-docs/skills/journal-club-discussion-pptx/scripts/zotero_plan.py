#!/usr/bin/env python3
"""
jc-pptx adapter for the shared Zotero archiving planner.

Thin wrapper over `case-discussion-pptx/lib/zotero_archive`: parses a finished jc-pptx run
(research_findings.json + structured.json) into the normalized spec, then calls
the skill-agnostic `build_plan`. Deterministic — does NOT touch Zotero. The
"Step 7 — Zotero Archiving" stage runs this, shows the plan for confirmation,
then the agent executes it via the Zotero MCP tools.

Inputs:
  research_findings.json  (from scripts/research_synth.py)
      - questions[]      : {question_id, question_text, ...}
      - all_citations[]  : {pmid, doi?, title?/author_year?/authors_short?,
                            used_in_questions[]}
  structured.json        (from Step 1 paper_extract)
      - paper_meta       : {title, doi?, pmid?, ...}   (the primary paper)

Output (stdout, and --out if given): the archiving plan JSON. Shape is defined
by `case-discussion-pptx/lib/zotero_archive` (parent / report_collection / primary_paper /
sections[] with section_id+subfolder+papers / doi_less / orphan_sections /
stats).

Usage:
  python3 zotero_plan.py research_findings.json structured.json \
      [--topic "DAPA-HF"] [--date 2026-06] [--parent "Journal Club"] \
      [--out plan.json]
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

# Put the bundled lib/ (sibling skill) on sys.path so `import zotero_archive` works.
_COMMON_DIR = Path(__file__).resolve().parent.parent.parent / "case-discussion-pptx" / "lib"
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from zotero_archive import build_plan, clean_str, first_nonempty, natural_key  # noqa: E402

SUBFOLDER_QTEXT_MAX = 50


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"[zotero_plan] file not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"[zotero_plan] invalid JSON in {path}: {e}")


def build_spec(findings: dict, structured: dict, topic: str, parent: str) -> dict:
    """jc-pptx data files -> normalized zotero_archive spec."""
    pmeta = structured.get("paper_meta", {}) if isinstance(structured, dict) else {}

    if not topic:
        topic = first_nonempty(pmeta, "title") or "Untitled report"

    # Sections from questions[], natural-sorted so Q2 precedes Q10. The core
    # preserves whatever order we hand it, so the sort happens here.
    sections = []
    for q in sorted(findings.get("questions", []),
                    key=lambda q: natural_key(q.get("question_id", ""))):
        qid = clean_str(q.get("question_id"))
        if not qid:
            continue
        qtext = clean_str(q.get("question_text"))
        label = qtext[:SUBFOLDER_QTEXT_MAX].rstrip()
        sections.append({"id": qid, "label": f"{qid}: {label}" if label else qid})

    citations = []
    for c in findings.get("all_citations", []):
        if not isinstance(c, dict):
            continue
        citations.append({
            "pmid": clean_str(c.get("pmid")),
            "doi": clean_str(c.get("doi")),
            # Keep author-ish fields so citation_title can fall through them.
            "title": c.get("title", ""),
            "article_title": c.get("article_title", ""),
            "author_year": c.get("author_year", ""),
            "authors_short": c.get("authors_short", ""),
            "full_author_list": c.get("full_author_list", ""),
            "authors": c.get("authors", ""),
            "in_sections": c.get("used_in_questions", []) or [],
        })

    return {
        "parent": parent,
        "topic": topic,
        "primary": {
            "title": first_nonempty(pmeta, "title"),
            "doi": clean_str(pmeta.get("doi")),
            "pmid": clean_str(pmeta.get("pmid")),
        },
        "sections": sections,
        "citations": citations,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a Zotero archiving plan for a jc-pptx run.")
    ap.add_argument("research_findings", help="path to research_findings.json")
    ap.add_argument("structured", help="path to structured.json")
    ap.add_argument("--topic", default="", help="report topic (default: paper title)")
    ap.add_argument("--date", default="", help="YYYY-MM (default: current month)")
    ap.add_argument("--parent", default="Journal Club", help="parent collection name")
    ap.add_argument("--out", default="", help="also write plan JSON to this path")
    args = ap.parse_args()

    date = args.date.strip() or datetime.date.today().strftime("%Y-%m")

    spec = build_spec(
        _load(args.research_findings),
        _load(args.structured),
        args.topic.strip(),
        args.parent,
    )
    plan = build_plan(spec, date=date)

    out_str = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_str)
        print(f"[zotero_plan] wrote {args.out}", file=sys.stderr)
    print(out_str)
    s = plan["stats"]
    print(
        f"[zotero_plan] {s['n_sections']} sections, {s['n_papers']} paper-slots, "
        f"{s['n_doi_less']} DOI-less (PMID fallback)"
        + (f", {s['n_orphans']} ORPHAN section(s): {plan['orphan_sections']}"
           if s["n_orphans"] else ""),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
