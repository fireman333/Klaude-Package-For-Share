"""
Format a citation dict into a printable reference line.

Input schema (minimum required keys):
    full_author_list | authors_short : str
    title                            : str
    journal                          : str
    year                             : int | str
    volume, issue, pages             : str (optional)
    pmid                             : str (optional)
    doi                              : str (optional)

Styles: vancouver (default), ama, apa7.

Can also be invoked as CLI:
    python3 refs_format.py <research_findings.json> [--style vancouver]

→ prints numbered list to stdout.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def _authors(c: dict) -> str:
    a = c.get("full_author_list") or c.get("authors_short") or "Anonymous"
    return a


def format_citation(c: dict, style: str = "vancouver") -> str:
    authors = _authors(c)
    title = c.get("title", "").rstrip(".")
    journal = c.get("journal", "")
    year = c.get("year", "")
    volume = c.get("volume", "")
    issue = c.get("issue", "")
    pages = c.get("pages", "")
    pmid = c.get("pmid", "")
    doi = c.get("doi", "")

    if style == "vancouver":
        vp = ""
        if volume:
            vp = f"{volume}"
            if issue:
                vp += f"({issue})"
            if pages:
                vp += f":{pages}"
        parts = [f"{authors}. {title}. {journal}."]
        if year or vp:
            tail = f"{year};{vp}" if vp else f"{year}"
            parts[-1] = f"{authors}. {title}. {journal}. {tail}."
        out = parts[0]
        if pmid:
            out += f" PMID: {pmid}."
        if doi:
            out += f" doi: {doi}"
        return out

    if style == "ama":
        # AMA is very close to Vancouver but italicizes journal (we can't in
        # plain-text pptx; fallback identical). Use semicolon between journal
        # and year.
        return format_citation(c, style="vancouver")

    if style == "apa7":
        out = f"{authors} ({year}). {title}. {journal}"
        if volume:
            vp = f", {volume}"
            if issue:
                vp += f"({issue})"
            if pages:
                vp += f", {pages}"
            out += vp
        out += "."
        if doi:
            out += f" https://doi.org/{doi}"
        return out

    raise ValueError(f"Unknown citation style: {style}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("findings_json", help="research_findings.json path")
    ap.add_argument("--style", default="vancouver",
                    choices=["vancouver", "ama", "apa7"])
    args = ap.parse_args()

    data = json.loads(Path(args.findings_json).read_text(encoding="utf-8"))
    all_cites = data.get("all_citations", [])
    for i, c in enumerate(all_cites, 1):
        print(f"{i}. {format_citation(c, style=args.style)}")


if __name__ == "__main__":
    main()
