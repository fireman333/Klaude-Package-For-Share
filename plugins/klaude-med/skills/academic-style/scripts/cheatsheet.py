#!/usr/bin/env python3
"""cheatsheet.py — print a journal's style summary (palette, fonts, dimensions, sample caption).

Usage:
    python cheatsheet.py --list
    python cheatsheet.py nature
    python cheatsheet.py jama --json    # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make the local `core/` importable when run as a plain script (no pip install).
_THIS_DIR = Path(__file__).resolve().parent
_PKG_DIR = _THIS_DIR.parent  # academic-style/ root
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

from core.theme_loader import load_spec, list_journals  # noqa: E402


def _swatch(hex_code: str) -> str:
    """Return an ANSI-colored block for a hex color (best effort)."""
    h = hex_code.lstrip("#")
    if len(h) != 6:
        return "  "
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"\x1b[48;2;{r};{g};{b}m  \x1b[0m"


def render_cheatsheet(journal: str) -> str:
    spec = load_spec(journal)
    j = spec["journal"]
    typo = spec["typography"]
    dim = spec["dimensions"]
    sub = spec["submission"]
    pal = spec["palette"]
    sem = spec["semantic_mapping"]

    lines = []
    lines.append(f"== {j['name']} ({j['short']}) — spec {j['spec_version']} ==")
    lines.append(f"Publisher : {j.get('publisher', '?')}")
    lines.append(f"Guideline : {j.get('sources', {}).get('author_guideline', '?')}")
    lines.append("")
    lines.append("Typography")
    lines.append(f"  Font stack    : {typo['font_stack']}")
    lines.append(f"  Base size     : {typo['base_size_pt']} pt")
    lines.append(f"  Title / axis  : {typo['sizes_pt']['title']} / {typo['sizes_pt']['axis_label']} pt")
    lines.append(f"  Panel labels  : {typo['panel_label']['format']} ({typo['panel_label']['case']}, {typo['panel_label']['style']})")
    lines.append("")
    lines.append("Dimensions")
    lines.append(f"  Single column : {dim['single_column']['width']} mm")
    lines.append(f"  Double column : {dim['double_column']['width']} mm")
    lines.append(f"  Raster DPI    : {dim['dpi_raster']}")
    lines.append("")
    lines.append("Submission")
    lines.append(f"  Vector format : {sub['vector_format']}")
    lines.append(f"  Raster format : {sub['raster_format']}")
    lines.append(f"  Embed fonts   : {sub.get('embed_fonts', True)}")
    lines.append("")
    lines.append("Semantic palette")
    for role, name in sem.items():
        hex_code = pal.get(name, "?")
        lines.append(f"  {role:<24} {_swatch(hex_code)} {hex_code:<8}  ({name})")
    lines.append("")
    lines.append("Sample caption")
    lines.append(f"  {spec['caption']['template']}")
    lines.append("")
    lines.append("Table style")
    lines.append(f"  P-value format : {spec['table_style']['p_value_format']}")
    lines.append(f"  Decimal places : {spec['table_style']['decimal_places']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a journal style cheat sheet.")
    parser.add_argument("journal", nargs="?", help="Journal short name (nature/jama/nejm/lancet)")
    parser.add_argument("--list", action="store_true", help="List supported journals")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text")
    args = parser.parse_args(argv)

    if args.list or not args.journal:
        journals = list_journals()
        if args.json:
            print(json.dumps(journals))
        else:
            print("Supported journals:")
            for j in journals:
                spec = load_spec(j)
                print(f"  - {j:<10} {spec['journal']['name']}")
        return 0

    if args.json:
        print(json.dumps(load_spec(args.journal), default=str, ensure_ascii=False, indent=2))
    else:
        print(render_cheatsheet(args.journal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
