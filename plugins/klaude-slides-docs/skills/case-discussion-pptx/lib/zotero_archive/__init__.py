"""
zotero_archive — Shared infrastructure for building a Zotero archiving plan
from any report/SR/MA skill, via a thin per-skill adapter.

WHY this exists
    jc-pptx pioneered "Step 7 — Zotero Archiving": file the papers a report
    actually cited into a per-report Zotero collection with per-section
    subfolders, then let the agent execute the plan through the `zotero` MCP
    tools (create_collection / add_by_doi / manage_collections). That plan-build
    logic is skill-agnostic; only the *parsing* of each skill's own data files
    into a normalized shape is skill-specific. This package holds the agnostic
    core; each skill ships a thin adapter.

Consumer pattern (mirrors open_slide_builder):
    # in <skill>/scripts/zotero_plan.py
    import sys
    from pathlib import Path
    _COMMON = Path(__file__).resolve().parent.parent / "lib"
    sys.path.insert(0, str(_COMMON))
    from zotero_archive import build_plan, natural_key, first_nonempty

    spec = {                              # the adapter's whole job: emit this
        "parent": "Journal Club",         # top-level Zotero collection
        "topic":  "DAPA-HF",              # -> report_collection "<date> <topic>"
        "primary": {"pmid","doi","title"},# optional single anchor paper, or None
        "sections": [                     # ordered; order is respected
            {"id": "Q1", "label": "Q1: Does ... reduce mortality"},
        ],
        "citations": [
            {"pmid","doi","title", "in_sections": ["Q1", "Q2"]},
        ],
    }
    plan = build_plan(spec, date="2026-06")
    print(json.dumps(plan, ensure_ascii=False, indent=2))

NORMALIZED SPEC (adapter output) — canonical contract
    parent     : str, required. Top-level collection name (Journal Club /
                 Meta-analysis / Systematic Review / Manuscripts).
    topic      : str, required-ish. Used to name the report collection. Empty
                 falls back to "Untitled report" with a stderr warning.
    primary    : dict | None. {title, doi, pmid} for the single anchor paper
                 (jc-pptx). None for skills with no single primary (MA/SR).
    sections   : list of {"id": str, "label": str?, "group": str?}. Order is
                 preserved as the subfolder order. label defaults to id when
                 omitted. Optional `group` nests this subfolder under a group
                 collection (2-level: group ▸ subfolder; used by MA's
                 comparison ▸ theme). An adapter that wants numeric/IMRaD
                 ordering sorts BEFORE handing sections in (use natural_key for
                 numeric ids like Q2 < Q10).
    citations  : list of {pmid?, doi?, title?, in_sections: [str]}. A citation
                 may belong to multiple sections (multi-membership is normal in
                 Zotero). Title may be absent — citation_title falls back through
                 author-ish fields then pmid.

PLAN (build_plan output) — what the skill's Step 7 reads
    parent             : str
    report_collection  : str  "<date> <topic>"
    primary_paper      : {title, doi, pmid} | None
    sections           : [{"section_id", "subfolder", "papers": [{pmid,doi,title}],
                           "group"?}]   # group present only for 2-level nesting
    doi_less           : [{pmid, title}]      # cited, lack a DOI -> PMID fallback
    orphan_sections    : [str]                # in_sections refs an unknown id
    stats              : {n_sections, n_papers, n_doi_less, n_orphans}

DISCIPLINE the plan encodes (jc-pptx pilot, inherited by every adapter)
    - No silent loss: a citation pointing at an unknown section id is KEPT in a
      "<id> (orphan)" subfolder AND surfaced in orphan_sections for the
      show->confirm gate.
    - DOI-less papers are listed so Step 7 can do the PMID -> add_by_url fallback.
    - Per-section dedup by (pmid or doi or title) so a re-run / repeated citation
      doesn't double-file.
    Execution discipline (show->confirm, lookup-before-add idempotency,
    create-or-reuse parent) lives in each skill's SKILL.md Step 7 prose.
"""
from __future__ import annotations

import datetime
import re
import sys
from typing import Any

__all__ = [
    "build_plan",
    "natural_key",
    "first_nonempty",
    "citation_title",
    "clean_str",
    "TOPIC_MAX",
]

TOPIC_MAX = 70


def clean_str(v) -> str:
    """Coerce a JSON value to a stripped string for use as a key/id/field.

    str and int pass through (so a numeric pmid like 24237006 isn't lost);
    everything else (None, float, list, dict, bool) -> "". Use this instead of
    `(x or "").strip()` on raw JSON values, which crashes on a non-string.
    """
    if isinstance(v, bool):
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, int):
        return str(v)
    return ""


def first_nonempty(d: dict, *keys: str) -> str:
    """First non-empty stripped string value among keys, else ''."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def citation_title(c: dict) -> str:
    """Display title for a citation.

    PubMed-only picks often carry author fields but no `title`; OE citations
    carry `title`. Fall through author-ish fields, then PMID, then a placeholder.
    """
    return first_nonempty(
        c, "title", "article_title", "author_year", "authors_short",
        "full_author_list", "authors",
    ) or (c.get("pmid") or "").strip() or "(no title)"


def natural_key(section_id: str) -> tuple:
    """Sort key so numeric ids order numerically (Q2 before Q10).

    Numeric-bearing ids sort first by their embedded integer; the rest fall back
    to lexical order. Adapters that want this ordering apply it to `sections`
    before calling build_plan (the core preserves the order it is given).
    """
    m = re.search(r"\d+", section_id or "")
    return (0, int(m.group())) if m else (1, section_id or "")


def _validate_spec(spec: Any) -> None:
    if not isinstance(spec, dict):
        raise ValueError(f"zotero_archive spec must be a dict, got {type(spec).__name__}")
    if not isinstance(spec.get("parent"), str) or not spec["parent"].strip():
        raise ValueError("zotero_archive spec needs a non-empty string 'parent'")
    if not isinstance(spec.get("sections"), list):
        raise ValueError("zotero_archive spec 'sections' must be a list")
    if not isinstance(spec.get("citations"), list):
        raise ValueError("zotero_archive spec 'citations' must be a list")
    for i, s in enumerate(spec["sections"]):
        if not isinstance(s, dict) or not str(s.get("id", "")).strip():
            raise ValueError(f"zotero_archive spec sections[{i}] needs a non-empty 'id'")
    for i, c in enumerate(spec["citations"]):
        if not isinstance(c, dict):
            raise ValueError(
                f"zotero_archive spec citations[{i}] must be a dict, got {type(c).__name__}"
            )
    primary = spec.get("primary")
    if primary is not None and not isinstance(primary, dict):
        raise ValueError("zotero_archive spec 'primary' must be a dict or None")


def build_plan(spec: dict, date: str | None = None) -> dict:
    """Turn a normalized adapter spec into a Zotero archiving plan (see module doc).

    Deterministic; does NOT touch Zotero. Pure parse + dedup + orphan/doi-less
    bookkeeping. Raises ValueError on a malformed spec (No Silent Errors).
    """
    _validate_spec(spec)

    date = (date or "").strip() or datetime.date.today().strftime("%Y-%m")

    topic = (spec.get("topic") or "").strip()[:TOPIC_MAX].rstrip()
    if not topic:
        topic = "Untitled report"
        print("[zotero_archive] WARNING: empty topic; using 'Untitled report'",
              file=sys.stderr)
    report_collection = f"{date} {topic}".strip()

    # Known sections, in the order the adapter handed them (order = subfolder order).
    sections: dict[str, dict] = {}
    for s in spec["sections"]:
        sid = str(s["id"]).strip()
        if sid in sections:
            continue  # first declaration wins; ignore accidental duplicate ids
        label = (s.get("label") or "").strip() or sid
        sec = {"section_id": sid, "subfolder": label, "papers": [], "_seen": set()}
        # Optional 2-level nesting: when a section declares a `group`, its
        # subfolder nests under that group collection (group nests under the
        # report collection). Emitted only when present, so single-level skills
        # are unaffected. Used by MA (comparison ▸ theme).
        group = clean_str(s.get("group"))
        if group:
            sec["group"] = group
        sections[sid] = sec

    doi_less: list[dict] = []
    seen_doi_less: set = set()
    orphans: set = set()
    n_papers_total = 0

    for c in spec["citations"]:  # validated as dicts in _validate_spec
        pmid = (c.get("pmid") or "").strip()
        doi = (c.get("doi") or "").strip()
        title = citation_title(c)
        rec = {"pmid": pmid, "doi": doi, "title": title}

        if not doi and pmid and pmid not in seen_doi_less:
            seen_doi_less.add(pmid)
            doi_less.append({"pmid": pmid, "title": title})

        for sid in c.get("in_sections", []) or []:
            sid = str(sid).strip()
            if not sid:
                continue
            sec = sections.get(sid)
            if sec is None:
                # Unknown section id — keep the paper (no silent loss), flag it.
                orphans.add(sid)
                sec = {"section_id": sid, "subfolder": f"{sid} (orphan)",
                       "papers": [], "_seen": set()}
                sections[sid] = sec
            dedup_key = pmid or doi or title
            if dedup_key in sec["_seen"]:
                continue
            sec["_seen"].add(dedup_key)
            sec["papers"].append(rec)
            n_papers_total += 1

    # Declared sections keep the order the adapter handed them (so IMRaD /
    # theme order is respected); orphan sections — citation refs to ids the
    # adapter never declared — are grouped AFTER, in deterministic natural order
    # (so anomalies cluster at the bottom rather than interleaving real sections).
    declared_ids = {str(s["id"]).strip() for s in spec["sections"]}
    declared_list, orphan_list = [], []
    for sid, sec in sections.items():
        sec.pop("_seen", None)
        (declared_list if sid in declared_ids else orphan_list).append(sec)
    orphan_list.sort(key=lambda s: natural_key(s["section_id"]))
    section_list = declared_list + orphan_list

    primary = spec.get("primary")
    primary_paper = None
    if isinstance(primary, dict):
        primary_paper = {
            "title": first_nonempty(primary, "title"),
            "doi": (primary.get("doi") or "").strip(),
            "pmid": (primary.get("pmid") or "").strip(),
        }

    return {
        "parent": spec["parent"].strip(),
        "report_collection": report_collection,
        "primary_paper": primary_paper,
        "sections": section_list,
        "doi_less": doi_less,
        "orphan_sections": sorted(orphans),
        "stats": {
            "n_sections": len({str(s["id"]).strip() for s in spec["sections"]}),
            "n_papers": n_papers_total,
            "n_doi_less": len(doi_less),
            "n_orphans": len(orphans),
        },
    }
