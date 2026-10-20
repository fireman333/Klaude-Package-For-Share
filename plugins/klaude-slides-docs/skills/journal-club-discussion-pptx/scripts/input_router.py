#!/usr/bin/env python3
"""
Detect input type and write intake.json for downstream Step 1 extraction.

Usage:
    python3 input_router.py <input> [--out intake.json]

<input> can be:
    - DOI string (10.xxxx/...)
    - PMID (7-9 digits)
    - PubMed URL (pubmed.ncbi.nlm.nih.gov/12345)
    - any other URL (http/https)
    - file path (*.pdf | *.html | *.md | *.txt)
    - free text paste (treat as markdown)

This script does only local, cheap detection. It does NOT call MCP/PubMed/defuddle
itself — it writes an `intake.json` with `type` + `source_path` + a content placeholder
and lists which upstream skills the main thread should invoke next.

Schema:
    {
        "type": "paper|paper_url|admission|freeform",
        "source_path": "/abs/path/or/url",
        "source_meta": {"pmid": "...", "doi": "...", ...},
        "content_md": "<lazily filled by main thread after upstream skill call>",
        "phi_gate": {...},             # admission only
        "freeform_headings": [...],    # freeform only (optional)
        "next_actions": [              # instructions for main thread
            "Call mcp__pubmed__pubmed_fetch_articles with PMID=12345678",
            ...
        ]
    }
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
PMID_RE = re.compile(r"^\d{7,9}$")
PUBMED_URL_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d{7,9})")
URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def detect(inp: str) -> dict:
    inp = inp.strip()

    # DOI
    if DOI_RE.match(inp):
        return {
            "type": "paper",
            "source_path": inp,
            "source_meta": {"doi": inp},
            "content_md": "",
            "next_actions": [
                f"mcp__pubmed__pubmed_lookup_citation(doi='{inp}') to get PMID",
                "Then mcp__pubmed__pubmed_fetch_articles to get full metadata",
                "Fill content_md with abstract + methods + results extracted from metadata",
            ],
        }

    # PMID
    if PMID_RE.match(inp):
        return {
            "type": "paper",
            "source_path": f"pmid:{inp}",
            "source_meta": {"pmid": inp},
            "content_md": "",
            "next_actions": [
                f"mcp__pubmed__pubmed_fetch_articles(pmids=['{inp}']) for full metadata",
                "Fill content_md with title + abstract + methods + results",
            ],
        }

    # PubMed URL
    m = PUBMED_URL_RE.search(inp)
    if m:
        pmid = m.group(1)
        return {
            "type": "paper",
            "source_path": inp,
            "source_meta": {"pmid": pmid},
            "content_md": "",
            "next_actions": [
                f"mcp__pubmed__pubmed_fetch_articles(pmids=['{pmid}'])",
            ],
        }

    # Other URL
    if URL_RE.match(inp):
        return {
            "type": "paper_url",
            "source_path": inp,
            "source_meta": {},
            "content_md": "",
            "next_actions": [
                "Call Skill(defuddle) to convert URL to clean markdown",
                "If markdown reveals PMID/DOI, re-run input_router to upgrade to type=paper",
            ],
        }

    # File path
    p = Path(os.path.expanduser(inp))
    if p.exists():
        suffix = p.suffix.lower()

        if suffix == ".pdf":
            return {
                "type": "paper",
                "source_path": str(p),
                "source_meta": {},
                "content_md": "",
                "next_actions": [
                    f"Call Skill(marker-pdf-converter) on {p}",
                    "Then parse front page / first section for PMID / DOI / title",
                    "Fill source_meta and content_md",
                ],
            }

        if suffix == ".html" or suffix == ".htm":
            # sniff for a saved hospital-EMR admission note HTML (Taiwan HIS style)
            try:
                head = p.read_text(encoding="utf-8", errors="ignore")[:20000]
            except Exception:
                head = ""
            is_emr = ("AdmissionNoteTab" in head
                       or "主訴" in head)
            if is_emr:
                return {
                    "type": "admission",
                    "source_path": str(p),
                    "source_meta": {},
                    "content_md": "",
                    "phi_gate": {"ran_deid": False,
                                 "patient_warnings": -1,
                                 "reporter_warnings": -1},
                    "next_actions": [
                        f"Convert {p} to plain markdown (chief complaint / history / exam / lab / imaging / pathology / plan sections)",
                        "Call Skill(phi-deid) on it BEFORE Step 1 (no real patient identifiers may enter the deck)",
                        "Fill content_md with the de-identified markdown",
                    ],
                }
            # generic HTML
            return {
                "type": "paper_url",
                "source_path": str(p),
                "source_meta": {},
                "content_md": "",
                "next_actions": [
                    f"Call Skill(defuddle) on {p}",
                ],
            }

        if suffix in (".md", ".txt"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = ""
            headings = re.findall(r"^\s{0,3}#{1,3}\s+(.+)$", text, flags=re.M)
            return {
                "type": "freeform",
                "source_path": str(p),
                "source_meta": {},
                "content_md": text,
                "freeform_headings": headings[:10],
                "next_actions": [
                    "Treat content_md as ground truth; Step 1 extracts section-by-section",
                ],
            }

    # Fallback: treat as pasted markdown
    return {
        "type": "freeform",
        "source_path": "__pasted__",
        "source_meta": {},
        "content_md": inp,
        "freeform_headings": re.findall(r"^\s{0,3}#{1,3}\s+(.+)$", inp, flags=re.M)[:10],
        "next_actions": [
            "Pasted text treated as freeform markdown; Step 1 processes directly",
        ],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", help="DOI / PMID / URL / file path / pasted text")
    ap.add_argument("--out", default="intake.json",
                    help="output JSON path (default: intake.json in cwd)")
    args = ap.parse_args()

    intake = detect(args.input)
    out = Path(args.out).expanduser().resolve()
    out.write_text(json.dumps(intake, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"[input_router] type={intake['type']} source={intake['source_path']}")
    print(f"[input_router] wrote {out}")
    print(f"[input_router] next_actions:")
    for a in intake["next_actions"]:
        print(f"  - {a}")


if __name__ == "__main__":
    main()
