#!/usr/bin/env python3
"""
Convert pptx → pdf → jpg for Step 6 visual QA.

Usage:
    python3 qa_visual.py <input.pptx> [--out-dir jc_qa]

Requires `soffice` (LibreOffice headless) and `pdftoppm` (poppler) on PATH.
After this runs, dispatch a general-purpose subagent to Read the JPGs and
check for overflow / cropping / rule violations (see SKILL.md Step 6).
"""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: str | None = None) -> None:
    print(f"[qa_visual] $ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd, check=False)
    if r.returncode != 0:
        print(f"[qa_visual] ERROR: {' '.join(cmd)} → rc={r.returncode}",
              file=sys.stderr)
        sys.exit(r.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pptx", help="input .pptx path")
    ap.add_argument("--out-dir", default="jc_qa",
                    help="output directory (default: jc_qa)")
    ap.add_argument("--dpi", type=int, default=110,
                    help="jpg DPI (default: 110)")
    args = ap.parse_args()

    pptx = Path(args.pptx).expanduser().resolve()
    if not pptx.exists():
        sys.exit(f"[qa_visual] file not found: {pptx}")

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Tool availability
    for tool in ("soffice", "pdftoppm"):
        if shutil.which(tool) is None:
            sys.exit(f"[qa_visual] missing required tool: {tool}")

    # Clean out previous slide jpgs
    for f in out_dir.glob("slide-*.jpg"):
        f.unlink()

    # pptx → pdf
    run(["soffice", "--headless", "--convert-to", "pdf",
         "--outdir", str(out_dir), str(pptx)])

    pdf = out_dir / (pptx.stem + ".pdf")
    if not pdf.exists():
        sys.exit(f"[qa_visual] soffice did not produce {pdf}")

    # pdf → jpg
    run(["pdftoppm", "-jpeg", "-r", str(args.dpi),
         str(pdf), str(out_dir / "slide")])

    jpgs = sorted(out_dir.glob("slide-*.jpg"))
    print(f"[qa_visual] wrote {len(jpgs)} jpgs to {out_dir}")
    for j in jpgs:
        print(f"  - {j}")

    print()
    print("[qa_visual] Next step: dispatch a general-purpose subagent to Read each jpg")
    print("[qa_visual]            and check for overflow / cropping / Rule 1 / Rule 3.")


if __name__ == "__main__":
    main()
