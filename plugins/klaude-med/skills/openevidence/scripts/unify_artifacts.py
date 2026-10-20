#!/usr/bin/env python3
"""
Unify + dedup AMA citations across multiple OE artifact dirs, with orphan
recovery from article.json span walk.

Use when you run multiple `oe_ask` queries with `save_artifacts=true` and need
to assemble a single manuscript / report with one consolidated reference list.

Orphan recovery — the critical bit:
  OE's answer.md uses span-order sequential inline [N] numbering, INCLUDING
  re-citations of the same paper. So an inline [25] in answer.md is NOT
  necessarily an orphan when citations.json only has 14 entries — it's the
  25th citation occurrence in document order (probably a re-cite of an
  earlier paper). Walking article.json's articlesection_set → articleparagraph_set
  → articlespan_set → citations[] tree reconstructs the full [N] → PMID map,
  allowing every inline number to be resolved back to a real reference.

Usage:
    # Single-query dedup + orphan recovery:
    python3 unify_artifacts.py <artifact_dir> [--output <out_dir>]

    # Multi-query unified references:
    python3 unify_artifacts.py <dir_q1> <dir_q2> <dir_q3> [--output <out_dir>]

    # Legacy layout (answer/citations/article side-by-side in one folder,
    # prefixed per query — e.g. q1a_answer.md, q1a_citations.json, q1a_article.json):
    python3 unify_artifacts.py <folder> --qids q1a,q1b,q2a --output <out_dir>

Each artifact dir must contain:
    - answer.md        (OE inline [N] text)
    - citations.json   (per-query citation list)
    - article.json     (full tree with span citations, for orphan recovery)

Output (in <out_dir>, default = first arg):
    - <qid>_answer_remapped.md   (inline [N] mapped to unified numbers)
    - references_ama.md          (consolidated AMA reference list)
    - mapping.json               (per-query mapping + unified_count)
    - orphan_recovery_log.json   (what inline numbers got recovered via article.json)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def load_json(path: Path) -> list | dict:
    return json.loads(path.read_text())


def walk_article_pmids(article: dict) -> list[int | None]:
    """Return PMIDs in document order (span-level citation occurrences)."""
    order: list[int | None] = []
    sections = (
        article.get("output", {}).get("structured_article", {}).get("articlesection_set", [])
    )
    for section in sections:
        for para in section.get("articleparagraph_set", []) or []:
            for span in para.get("articlespan_set", []) or []:
                for cit in span.get("citations", []) or []:
                    meta = cit.get("metadata") or {}
                    pmid = meta.get("citation_detail", {}).get("pmid") or meta.get("id")
                    order.append(pmid)
    return order


def citation_dedup_key(c: dict) -> str:
    pmid = c.get("pmid")
    if pmid:
        return f"PMID:{pmid}"
    doi = c.get("doi")
    if doi:
        return f"DOI:{doi.lower()}"
    return f"KEY:{c.get('key', '?')}"


def resolve_layout(args: argparse.Namespace) -> list[tuple[str, Path, Path, Path]]:
    """Return [(qid, answer_md_path, citations_json_path, article_json_path), ...]."""
    result = []
    if args.qids:
        # Legacy: single folder, prefixed filenames
        folder = Path(args.inputs[0])
        for qid in args.qids.split(","):
            qid = qid.strip()
            result.append((
                qid,
                folder / f"{qid}_answer.md",
                folder / f"{qid}_citations.json",
                folder / f"{qid}_article.json",
            ))
    else:
        # Each input is an artifact dir
        for i, d in enumerate(args.inputs, start=1):
            d = Path(d)
            qid = d.name if d.name else f"q{i}"
            result.append((
                qid,
                d / "answer.md",
                d / "citations.json",
                d / "article.json",
            ))
    # Verify all files exist
    for qid, a, c, art in result:
        missing = [p for p in (a, c, art) if not p.exists()]
        if missing:
            hint = ""
            if any(p.name.endswith("article.json") for p in missing) and a.exists() and c.exists():
                hint = (
                    "\n  HINT: article.json is required for orphan recovery."
                    " If your artifact only has answer.md + citations.json (legacy save),"
                    " use the raw JSON fallback: parse_oe.py <saved_tool_result.txt>"
                )
            sys.exit(f"Missing file(s) for qid '{qid}': {', '.join(str(p) for p in missing)}{hint}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help="Artifact dirs, or one dir with --qids")
    ap.add_argument("--qids", help="Comma-sep qids (legacy prefixed-file layout)")
    ap.add_argument("--output", help="Output directory (default = first input dir)")
    args = ap.parse_args()

    layout = resolve_layout(args)
    if args.output:
        # Treat --output as the parent; always write into <output>/unified/
        out = Path(args.output) / "unified"
    else:
        out = Path(args.inputs[0]) / "unified"
    out.mkdir(exist_ok=True, parents=True)

    # First pass: build unified reference list (first-appearance order)
    unified: dict[str, int] = {}
    unified_citations: list[dict] = []
    per_question_mapping: dict[str, dict[int, int]] = {}

    for qid, _a_path, c_path, _art_path in layout:
        cites = load_json(c_path)
        mapping: dict[int, int] = {}
        for idx, c in enumerate(cites, start=1):
            key = citation_dedup_key(c)
            if key in unified:
                mapping[idx] = unified[key]
            else:
                new_num = len(unified_citations) + 1
                unified[key] = new_num
                unified_citations.append(c)
                mapping[idx] = new_num
        per_question_mapping[qid] = mapping

    # Lookup: PMID (int) → unified ref number
    pmid_to_unified: dict[int, int] = {}
    for i, c in enumerate(unified_citations, start=1):
        pmid = c.get("pmid")
        if pmid is not None:
            pmid_to_unified[int(pmid)] = i

    # Second pass: remap inline [N] with orphan recovery via article.json
    inline_pat = re.compile(r"\[(\d+)\]")
    orphan_recovery: dict[str, list[dict]] = {}

    for qid, a_path, c_path, art_path in layout:
        src = a_path.read_text()
        article = load_json(art_path)
        inline_to_pmid = {
            i + 1: p for i, p in enumerate(walk_article_pmids(article)) if p is not None
        }
        mapping = per_question_mapping[qid]
        recoveries: list[dict] = []

        def _sub(match: re.Match) -> str:
            old = int(match.group(1))
            # Path 1: direct mapping via citations.json index
            if old in mapping:
                return f"[{mapping[old]}]"
            # Path 2: orphan recovery via article.json span walk
            pmid = inline_to_pmid.get(old)
            if pmid and pmid in pmid_to_unified:
                new_num = pmid_to_unified[pmid]
                recoveries.append({
                    "qid": qid,
                    "inline_old": old,
                    "recovered_pmid": pmid,
                    "unified_new": new_num,
                })
                return f"[{new_num}]"
            # Path 3: truly unresolvable
            return ""

        remapped = inline_pat.sub(_sub, src)
        remapped = re.sub(r"\s*\[\s*\]\s*", "", remapped)
        (out / f"{qid}_answer_remapped.md").write_text(remapped)
        orphan_recovery[qid] = recoveries

    # References list
    lines = []
    for i, c in enumerate(unified_citations, start=1):
        s = (c.get("citation", "") or "").strip()
        pmid = c.get("pmid")
        if pmid and f"PMID: {pmid}" not in s and f"PMID:{pmid}" not in s:
            s = s.rstrip(".") + f". PMID: {pmid}."
        lines.append(f"{i}. {s}")
    (out / "references_ama.md").write_text("\n".join(lines) + "\n")

    (out / "mapping.json").write_text(
        json.dumps({"per_question_mapping": per_question_mapping,
                    "unified_count": len(unified_citations)}, indent=2)
    )
    (out / "orphan_recovery_log.json").write_text(json.dumps(orphan_recovery, indent=2))

    # Report
    print(f"Unified {len(unified_citations)} unique citations across {len(layout)} queries.")
    total = 0
    for qid, _, c_path, _ in layout:
        orig = len(load_json(c_path))
        recov = len(orphan_recovery[qid])
        total += recov
        print(f"  {qid}: {orig} original | {recov} orphan re-cites recovered via article.json")
    print(f"Total orphan re-cites recovered: {total}")
    print(f"Output → {out}")


if __name__ == "__main__":
    main()
