#!/usr/bin/env python3
"""
deep-research (Systematic Review mode) adapter for the shared Zotero planner.

Thin wrapper over `zotero-archive/lib/zotero_archive`: parses an SR run's handoff artifacts
(synthesis.json + bibliography.json, optionally rq_brief.json) into the
normalized spec, then calls the skill-agnostic `build_plan`. Deterministic —
does NOT touch Zotero. The SR-mode "Zotero Archiving" step runs this, shows the
plan for confirmation, then the agent executes it via the Zotero MCP tools.

Folder model (Facet 6 — SR mirrors MA, included-only):
  parent  = "Systematic Review"
  report  = "<YYYY-MM> <topic>"           (母夾)
  subfolder per synthesis THEME           (theme = section)
The whole INCLUDED set (every bibliography.json entry) is archived for the
reading pool. A study cited by a theme's supporting_refs OR contradicting_refs
lands in that theme's subfolder (reading a theme = seeing for- and against-
evidence). An included study no theme references is NOT dropped — it goes to a
visible "Included (unthemed)" subfolder so the user can re-file it at confirm.

Inputs (canonical handoff schemas — deep-research SKILL.md "Handoff Contracts"):
  synthesis.json
      themes[]  : {theme_id, title, supporting_refs[], contradicting_refs[], ...}
  bibliography.json
      entries[] : {bib_key, pmid?, doi?, title, ...}   (the INCLUDED set)
  rq_brief.json (optional)
      {topic, primary_question, ...}                   (topic source)

Output (stdout, and --out if given): the archiving plan JSON, shape defined by
`zotero-archive/lib/zotero_archive` (parent / report_collection / primary_paper(null for
SR) / sections[] / doi_less / orphan_sections / stats).

Usage:
  python3 zotero_plan_sr.py synthesis.json bibliography.json \
      [--rq-brief rq_brief.json] [--topic "SGLT2 inhibitors in heart failure"] \
      [--date 2026-06] [--parent "Systematic Review"] [--out plan.json]
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

# zotero_archive core lives in the sibling zotero-archive skill (same plugin)
_COMMON_DIR = Path(__file__).resolve().parent.parent.parent / "zotero-archive" / "lib"
if str(_COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(_COMMON_DIR))

from zotero_archive import build_plan, clean_str, first_nonempty  # noqa: E402

THEME_TITLE_MAX = 50
UNTHEMED_ID = "_unthemed"
UNTHEMED_LABEL = "Included (unthemed)"


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        sys.exit(f"[zotero_plan_sr] file not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"[zotero_plan_sr] invalid JSON in {path}: {e}")


def _entry_title(e: dict) -> str:
    # authors[] may be a list; first_nonempty wants strings, so fall through
    # title -> first author -> bib_key in build_spec.
    return first_nonempty(e, "title")


def _as_list(v) -> list:
    """Coerce a possibly-scalar field to a list. synthesis.json is LLM-generated,
    so a theme's supporting_refs may arrive as a bare string instead of a list."""
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        return [v]
    return []


def _theme_refs(t: dict) -> list:
    """Cleaned, non-empty string bib_keys a theme references (supporting +
    contradicting). Non-string elements are skipped defensively."""
    out = []
    for k in _as_list(t.get("supporting_refs")) + _as_list(t.get("contradicting_refs")):
        if isinstance(k, str) and k.strip():
            out.append(k.strip())
    return out


def build_spec(synthesis: dict, biblio: dict, topic: str, parent: str) -> dict:
    themes = synthesis.get("themes", []) if isinstance(synthesis, dict) else []
    entries = biblio.get("entries", []) if isinstance(biblio, dict) else []

    # Index the included set by bib_key (the ref token themes use).
    by_key: dict[str, dict] = {}
    for e in entries:
        if not isinstance(e, dict):
            continue
        key = clean_str(e.get("bib_key"))
        if not key:
            # No bib_key -> can't be theme-linked; still keep via a synthetic key
            # so it isn't lost (lands in unthemed).
            key = clean_str(e.get("doi")) or clean_str(e.get("pmid"))
        if not key or key in by_key:
            continue
        by_key[key] = e

    # Sections = themes, in synthesis order (the core preserves order given).
    sections = []
    for t in themes:
        if not isinstance(t, dict):
            continue
        tid = clean_str(t.get("theme_id"))
        if not tid:
            continue
        title = clean_str(t.get("title"))[:THEME_TITLE_MAX].rstrip()
        sections.append({"id": tid, "label": f"{tid}: {title}" if title else tid})

    # Map each bib_key -> the theme ids that reference it (supporting OR
    # contradicting). A study under no theme goes to the unthemed bucket.
    refs_by_key: dict[str, list[str]] = {}
    for t in themes:
        if not isinstance(t, dict):
            continue
        tid = clean_str(t.get("theme_id"))
        if not tid:
            continue
        for k in _theme_refs(t):
            lst = refs_by_key.setdefault(k, [])
            if tid not in lst:
                lst.append(tid)

    any_unthemed = False
    citations = []
    for key, e in by_key.items():
        in_sections = refs_by_key.get(key, [])
        if not in_sections:
            in_sections = [UNTHEMED_ID]
            any_unthemed = True
        authors = e.get("authors")
        author0 = authors[0] if isinstance(authors, list) and authors else ""
        citations.append({
            "pmid": clean_str(e.get("pmid")),
            "doi": clean_str(e.get("doi")),
            "title": _entry_title(e) or (author0 if isinstance(author0, str) else "") or key,
            "in_sections": in_sections,
        })

    # Also surface theme refs that point at a bib_key absent from the
    # bibliography (dangling ref) — keep nothing silently; the core will flag
    # them as orphan_sections only if the section id is unknown, but a dangling
    # *ref* (known theme, missing study) needs its own signal. Emit a stub
    # citation per (theme, missing-key) so EVERY theme with a bad ref shows it
    # at confirm rather than vanishing.
    seen_stub: set = set()
    for t in themes:
        if not isinstance(t, dict):
            continue
        tid = clean_str(t.get("theme_id"))
        if not tid:
            continue
        for k in _theme_refs(t):
            if k not in by_key and (tid, k) not in seen_stub:
                seen_stub.add((tid, k))
                citations.append({
                    "pmid": "", "doi": "",
                    "title": f"(missing from bibliography: {k})",
                    "in_sections": [tid],
                })

    if any_unthemed:
        sections.append({"id": UNTHEMED_ID, "label": UNTHEMED_LABEL})

    return {
        "parent": parent,
        "topic": topic,
        "primary": None,            # SR has no single primary paper
        "sections": sections,
        "citations": citations,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a Zotero archiving plan for an SR run.")
    ap.add_argument("synthesis", help="path to synthesis.json")
    ap.add_argument("bibliography", help="path to bibliography.json")
    ap.add_argument("--rq-brief", default="", help="path to rq_brief.json (topic source)")
    ap.add_argument("--topic", default="", help="report topic (default: rq_brief topic)")
    ap.add_argument("--date", default="", help="YYYY-MM (default: current month)")
    ap.add_argument("--parent", default="Systematic Review", help="parent collection name")
    ap.add_argument("--out", default="", help="also write plan JSON to this path")
    args = ap.parse_args()

    date = args.date.strip() or datetime.date.today().strftime("%Y-%m")

    topic = args.topic.strip()
    if not topic and args.rq_brief.strip():
        brief = _load(args.rq_brief)
        topic = first_nonempty(brief, "topic", "primary_question")
    if not topic:
        topic = "Untitled review"

    spec = build_spec(
        _load(args.synthesis),
        _load(args.bibliography),
        topic,
        args.parent,
    )
    plan = build_plan(spec, date=date)

    out_str = json.dumps(plan, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_str)
        print(f"[zotero_plan_sr] wrote {args.out}", file=sys.stderr)
    print(out_str)
    s = plan["stats"]
    print(
        f"[zotero_plan_sr] {s['n_sections']} theme-folders, {s['n_papers']} paper-slots, "
        f"{s['n_doi_less']} DOI-less (PMID fallback)"
        + (f", {s['n_orphans']} ORPHAN section(s): {plan['orphan_sections']}"
           if s["n_orphans"] else ""),
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
