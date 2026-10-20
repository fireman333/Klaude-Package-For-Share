#!/usr/bin/env python3
"""
Merge OE summaries and PubMed subagent JSONs into a single research_findings.json.

Usage:
    python3 research_synth.py \
        --oe oe_sum_q1.json oe_sum_q2.json oe_sum_q3.json \
        --pubmed pubmed_sub_q1.json pubmed_sub_q2.json pubmed_sub_q3.json \
        --out research_findings.json

Output schema (abbreviated):
    {
      "questions": [
        {
          "question_id": "Q1",
          "question_text": "...",
          "oe":     {"citations": [...], "verdict_sentence": "...", "artifact_path": "..."},
          "pubmed": {"picks": [...], "notes_for_main": "..."},
          "dedup_overlap_pmids": [...],
          "evidence_summary_en": "",   # filled by Claude at Step 4
          "evidence_summary_zh": "",   # filled by Claude at Step 4
        },
        ...
      ],
      "all_citations": [...],          # dedup'd, for references slide
      "failed_questions": [...],
      "oe_failures": [...]
    }

This script does only structural merge + PMID dedup. `evidence_summary_en/zh`
is left empty for Claude main thread to fill when writing DATA.py.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path


def qid_from_path(p: Path) -> str:
    """Extract Q{n} identifier from filename like oe_sum_q2.json → 'Q2'."""
    m = re.search(r"q(\d+)", p.stem, re.IGNORECASE)
    return f"Q{m.group(1)}" if m else p.stem


def load_list(paths: list[str]) -> dict[str, dict]:
    out = {}
    for p in paths:
        pp = Path(p).expanduser().resolve()
        if not pp.exists():
            print(f"[research_synth] WARN missing: {pp}")
            continue
        data = json.loads(pp.read_text(encoding="utf-8"))
        qid = data.get("question_id") or qid_from_path(pp)
        out[qid] = data
    return out


def merge(oe_map: dict[str, dict], pub_map: dict[str, dict]) -> dict:
    all_qids = sorted(set(list(oe_map.keys()) + list(pub_map.keys())))
    questions = []
    all_cites = {}                     # pmid → citation dict
    failed = []
    oe_failures = []

    for qid in all_qids:
        oe = oe_map.get(qid, {})
        pub = pub_map.get(qid, {})

        # Track failures
        if oe.get("failures"):
            oe_failures.append({"qid": qid, "failures": oe["failures"]})
        if pub.get("failures"):
            failed.append({"qid": qid, "failures": pub["failures"]})

        oe_cites = oe.get("citations", []) or []
        pub_picks = pub.get("picks", []) or []

        oe_pmids = {c.get("pmid"): c for c in oe_cites if c.get("pmid")}
        pub_pmids = {c.get("pmid"): c for c in pub_picks if c.get("pmid")}
        overlap = sorted(set(oe_pmids.keys()) & set(pub_pmids.keys()))

        # Accumulate into all_citations (prefer PubMed over OE for metadata ground truth)
        for pmid, c in {**oe_pmids, **pub_pmids}.items():
            if pmid in all_cites:
                used = set(all_cites[pmid].get("used_in_questions", []))
                used.add(qid)
                all_cites[pmid]["used_in_questions"] = sorted(used)
            else:
                rec = dict(c)
                rec["used_in_questions"] = [qid]
                all_cites[pmid] = rec

        q_text = oe.get("question_text") or pub.get("question_text", "")

        questions.append({
            "question_id": qid,
            "question_text": q_text,
            "oe": {
                "citations": oe_cites,
                "verdict_sentence": oe.get("verdict_sentence", ""),
                "artifact_path": oe.get("artifact_path", ""),
            },
            "pubmed": {
                "picks": pub_picks,
                "notes_for_main": pub.get("notes_for_main", ""),
                "search_query": pub.get("search_query", ""),
            },
            "dedup_overlap_pmids": overlap,
            "evidence_summary_en": "",
            "evidence_summary_zh": "",
        })

    return {
        "questions": questions,
        "all_citations": list(all_cites.values()),
        "failed_questions": failed,
        "oe_failures": oe_failures,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--oe", nargs="*", default=[],
                    help="OE summary JSON paths (oe_summary_compactor.py output)")
    ap.add_argument("--pubmed", nargs="*", default=[],
                    help="PubMed subagent JSON paths")
    ap.add_argument("--out", default="research_findings.json",
                    help="output path")
    args = ap.parse_args()

    oe_map = load_list(args.oe)
    pub_map = load_list(args.pubmed)
    findings = merge(oe_map, pub_map)

    out = Path(args.out).expanduser().resolve()
    out.write_text(json.dumps(findings, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"[research_synth] {len(findings['questions'])} questions merged")
    print(f"[research_synth] {len(findings['all_citations'])} unique citations")
    print(f"[research_synth] failures: "
          f"oe={len(findings['oe_failures'])}, "
          f"pubmed={len(findings['failed_questions'])}")
    print(f"[research_synth] wrote {out}")


if __name__ == "__main__":
    main()
