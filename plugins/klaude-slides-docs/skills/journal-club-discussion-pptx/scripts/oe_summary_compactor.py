#!/usr/bin/env python3
"""
Compact an OpenEvidence MCP artifact into a small JSON that the main thread
can Read without blowing the context window.

Usage:
    # Preferred: point at the OE MCP artifactDir (has citations.json + answer.md)
    python3 oe_summary_compactor.py <artifact_dir> <out.json> \
        --qid Q1 --question "What is ..."

    # Fallback: raw .txt / .md artifact (regex-only, used when citations.json
    # is unavailable — the structured route is always preferable)
    python3 oe_summary_compactor.py <artifact.txt> <out.json> ...

When given a directory, reads `citations.json` (structured, crossref-validated
list OE already extracted — 2026-04-23 verified on real DAPA-HF artifact:
regex-only mode captured 0/9 citations because OE's `[N]` bracket style doesn't
match `PMID: NNN` literal). Regex on `.md` is fallback for when OE changes
schema or the dir is missing.

Output schema:
    {
      "question_id": "Q1",
      "question_text": "...",
      "artifact_path": "/path/to/source",
      "source_mode": "artifact_dir | regex_fallback",
      "verdict_sentence": "<first strong summary sentence from answer.md>",
      "citations": [
          {"pmid": "12345678", "doi": "...", "authors_short": "...",
           "year": 2024, "journal": "...", "title": "...",
           "take_home": "..."}
      ],
      "failures": []
    }
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path


PMID_RE = re.compile(r"PMID[:\s]*(\d{7,9})", re.IGNORECASE)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/\S+?)(?=[\s,;\)\]]|$)", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _first_strong_sentence(text: str) -> str:
    """Pick the first sentence that looks like a verdict (≥ 50 chars, contains
    an evidentiary verb)."""
    verbs = ("support", "suggest", "indicate", "show", "demonstrat",
             "contradict", "oppose", "reject", "refute", "associate",
             "reduce", "increase", "improve", "worsen", "benefit",
             "recommend", "evidence favors", "no significant")
    for para in text.split("\n\n")[:8]:
        for s in re.split(r"(?<=[\.\!\?])\s+", para):
            s = s.strip()
            if len(s) < 50:
                continue
            lo = s.lower()
            if any(v in lo for v in verbs):
                return s[:500]
    # fallback: first non-empty ≥ 50 char sentence
    for para in text.split("\n\n")[:5]:
        for s in re.split(r"(?<=[\.\!\?])\s+", para):
            s = s.strip()
            if len(s) >= 50:
                return s[:500]
    return ""


def _extract_citations(text: str, max_n: int = 8) -> list[dict]:
    """Find PMID / DOI tokens with surrounding context to assemble citation entries."""
    out = []
    seen_pmids = set()

    for m in PMID_RE.finditer(text):
        pmid = m.group(1)
        if pmid in seen_pmids:
            continue
        seen_pmids.add(pmid)

        # Context: 200 chars before + 100 after (more before because author/year usually precedes)
        s = max(0, m.start() - 240)
        e = min(len(text), m.end() + 140)
        ctx = text[s:e]

        doi_m = DOI_RE.search(ctx)
        year_m = YEAR_RE.search(ctx)
        # crude author-year heuristic: "Smith et al., 2024" or "(Smith, 2024)"
        author_m = re.search(
            r"([A-Z][a-z]+(?:\s+et\s+al\.?)?)[,\s]+(?:\(?(19|20)\d{2})",
            ctx)
        authors_short = author_m.group(1) if author_m else ""

        # Take-home: the sentence containing the PMID, truncated
        sent_start = max(0, m.start() - 200)
        sent_end = min(len(text), m.end() + 80)
        sentence_region = text[sent_start:sent_end]
        # nearest period before match, nearest period after
        before = sentence_region[:m.start() - sent_start]
        after = sentence_region[m.start() - sent_start:]
        lp = before.rfind(". ")
        rp = after.find(". ")
        take_home = ((before[lp + 2:] if lp >= 0 else before)
                     + (after[:rp + 1] if rp >= 0 else after)).strip()
        take_home = re.sub(r"\s+", " ", take_home)[:260]

        out.append({
            "pmid": pmid,
            "doi": doi_m.group(1) if doi_m else "",
            "authors_short": authors_short,
            "year": int(year_m.group(0)) if year_m else "",
            "journal": "",
            "take_home": take_home,
        })
        if len(out) >= max_n:
            break
    return out


def _load_structured_citations(citations_json_path: Path) -> list[dict]:
    """Load OE's pre-extracted citations.json. Schema per 2026-04-23 verification:
    list of dicts with keys: citation, title, href, doi, pmid, repository,
    published, authors, journal, publicationInfo, crossref."""
    raw = json.loads(citations_json_path.read_text(encoding="utf-8"))
    out = []
    for c in raw:
        pub = c.get("published", "") or ""
        year = ""
        if isinstance(pub, str) and len(pub) >= 4 and pub[:4].isdigit():
            year = int(pub[:4])
        authors = c.get("authors", "") or ""
        authors_short = authors.split(",")[0].strip() if "," in authors else authors.strip()
        cr = c.get("crossref") or {}
        out.append({
            "pmid": str(c.get("pmid") or ""),
            "doi": c.get("doi", "") or "",
            "authors_short": authors_short,
            "year": year,
            "journal": c.get("journal", "") or "",
            "title": c.get("title", "") or "",
            "take_home": c.get("publicationInfo", "") or c.get("citation", "")[:260],
            "crossref_status": cr.get("status", "") if isinstance(cr, dict) else "",
        })
    return out


def compact_from_dir(artifact_dir: Path) -> dict:
    """Preferred path: artifact_dir has answer.md + citations.json from OE MCP."""
    answer_path = artifact_dir / "answer.md"
    citations_path = artifact_dir / "citations.json"
    failures: list[str] = []

    if not answer_path.exists():
        failures.append(f"missing:answer.md in {artifact_dir}")
        verdict = ""
    else:
        verdict = _first_strong_sentence(
            answer_path.read_text(encoding="utf-8", errors="ignore"))

    if citations_path.exists():
        citations = _load_structured_citations(citations_path)
    else:
        failures.append(f"missing:citations.json in {artifact_dir} → fallback regex on answer.md")
        text = answer_path.read_text(encoding="utf-8", errors="ignore") if answer_path.exists() else ""
        citations = _extract_citations(text)

    return {
        "source_mode": "artifact_dir",
        "verdict_sentence": verdict,
        "citations": citations,
        "failures": failures,
    }


def compact(artifact_text: str) -> dict:
    """Regex fallback. Use when artifact_dir not available."""
    return {
        "source_mode": "regex_fallback",
        "verdict_sentence": _first_strong_sentence(artifact_text),
        "citations": _extract_citations(artifact_text),
        "failures": [] if artifact_text.strip() else ["empty_artifact"],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact", help="OE artifact dir (preferred) OR .txt/.md file (regex fallback)")
    ap.add_argument("out", help="output JSON path")
    ap.add_argument("--qid", default="Q?", help="question ID (e.g. Q1)")
    ap.add_argument("--question", default="", help="question text")
    args = ap.parse_args()

    p = Path(args.artifact).expanduser().resolve()
    if p.is_dir():
        out = compact_from_dir(p)
    elif p.is_file():
        text = p.read_text(encoding="utf-8", errors="ignore")
        out = compact(text)
    else:
        raise FileNotFoundError(f"neither file nor dir: {p}")
    out["question_id"] = args.qid
    out["question_text"] = args.question
    out["artifact_path"] = str(p)

    outp = Path(args.out).expanduser().resolve()
    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"[oe_compactor] mode={out['source_mode']} → {len(out['citations'])} citations")
    if out["failures"]:
        print(f"[oe_compactor] failures: {out['failures']}")
    print(f"[oe_compactor] wrote {outp}")


if __name__ == "__main__":
    main()
