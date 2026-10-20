#!/usr/bin/env python3
"""rewrite.py — re-style an existing figure under a journal theme.

Usage:
    python rewrite.py figures/km_curve.png --style nature
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_PKG_DIR = _THIS_DIR.parent
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

from core.post_processor import rewrite_figure  # noqa: E402
from core.theme_loader import list_journals  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-style an existing figure.")
    parser.add_argument("figure", help="Path to PNG/SVG figure")
    parser.add_argument(
        "--style", "--journal",
        required=True, choices=list_journals(),
        help="Target journal short name",
    )
    args = parser.parse_args(argv)

    out = rewrite_figure(args.figure, args.style)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
