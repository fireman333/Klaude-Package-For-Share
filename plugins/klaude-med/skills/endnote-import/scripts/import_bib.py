#!/usr/bin/env python3
"""Drop a .bib (and optionally .enw) into a centralized inbox for manual EndNote import.

v2 behaviour — no automation:
  1. Validate .bib path
  2. Copy .bib to <inbox>/<YYYYMMDD>_<project>__<basename>.bib
  3. If bibutils available: also write a .enw next to it (EndNote native format)
  4. Archive original .bib snapshot under <project_dir>/endnote_archive/
  5. Append JSON log
  6. Print clear manual EndNote import instructions

Why no AppleScript any more:
  GUI-scripted Group / Group Set creation across EndNote 21.5 Mac was
  unreliable (focus race after Create Group Set swallowed the keystroke
  for the new group's name field). Rather than ship flaky automation,
  we surface the .bib in a known location and let the user do the
  3-click manual import inside EndNote.

Usage:
  python import_bib.py <bib-path> --project <name> [--inbox <dir>] \\
                                  [--archive-dir <dir>] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_INBOX = Path.home() / "Documents" / "EndNote_inbox"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("bib_path", help="Path to source .bib file")
    p.add_argument("--project", required=True, help="Project identifier")
    p.add_argument(
        "--inbox",
        default=str(DEFAULT_INBOX),
        help=f"Centralized inbox folder (default: {DEFAULT_INBOX})",
    )
    p.add_argument(
        "--archive-dir",
        default=None,
        help="Where to archive .bib (default: <bib-parent>/endnote_archive/)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan without copying anything",
    )
    return p.parse_args()


def detect_bibutils() -> bool:
    return shutil.which("bib2xml") is not None and shutil.which("xml2end") is not None


def convert_bib_to_enw(bib_path: Path, out_path: Path) -> None:
    """bib2xml input.bib | xml2end > out.enw"""
    bib2xml = subprocess.Popen(["bib2xml", str(bib_path)], stdout=subprocess.PIPE)
    with out_path.open("wb") as fh:
        xml2end = subprocess.Popen(["xml2end"], stdin=bib2xml.stdout, stdout=fh)
        bib2xml.stdout.close()
        xml2end.wait()
    bib2xml.wait()
    if bib2xml.returncode != 0 or xml2end.returncode != 0:
        raise RuntimeError(
            f"bibutils conversion failed: bib2xml={bib2xml.returncode}, "
            f"xml2end={xml2end.returncode}"
        )


def count_bib_entries(bib_path: Path) -> int:
    try:
        text = bib_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return -1
    return sum(
        1 for line in text.splitlines() if line.lstrip().startswith("@") and "{" in line
    )


def append_log(log_path: Path, record: dict) -> None:
    if log_path.is_file():
        try:
            existing = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = [existing]
        except Exception:
            existing = []
    else:
        existing = []
    existing.append(record)
    log_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    bib_path = Path(args.bib_path).expanduser().resolve()

    if not bib_path.is_file():
        print(f"ERROR: bib file not found: {bib_path}", file=sys.stderr)
        return 2

    inbox = Path(args.inbox).expanduser().resolve()
    archive_dir = (
        Path(args.archive_dir).expanduser().resolve()
        if args.archive_dir
        else bib_path.parent / "endnote_archive"
    )
    log_path = archive_dir / "endnote_import_log.json"

    timestamp = dt.datetime.now()
    date_tag = timestamp.strftime("%Y%m%d")
    time_tag = timestamp.strftime("%Y%m%d_%H%M%S")
    inbox_basename = f"{date_tag}_{args.project}__{bib_path.name}"
    inbox_bib = inbox / inbox_basename
    inbox_enw = inbox / inbox_basename.replace(".bib", ".enw")
    archive_bib = archive_dir / f"{time_tag}_{bib_path.name}"

    entry_count = count_bib_entries(bib_path)
    has_bibutils = detect_bibutils()

    print("== endnote-import (drop-zone mode) ==")
    print(f"  bib:           {bib_path}")
    print(f"  entries:       {entry_count}")
    print(f"  project:       {args.project}")
    print(f"  inbox bib:     {inbox_bib}")
    if has_bibutils:
        print(f"  inbox enw:     {inbox_enw}  (bibutils enabled)")
    else:
        print(f"  inbox enw:     (skipped — install bibutils for .enw)")
    print(f"  archive bib:   {archive_bib}")

    if args.dry_run:
        print("[dry-run] stopping before any side effects.")
        return 0

    # Create directories
    inbox.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Copy to inbox
    shutil.copy2(bib_path, inbox_bib)
    print(f"-> wrote {inbox_bib}")

    # Convert to .enw next to the inbox .bib if bibutils present
    enw_status = "skipped"
    if has_bibutils:
        try:
            convert_bib_to_enw(bib_path, inbox_enw)
            enw_status = "ok"
            print(f"-> wrote {inbox_enw}")
        except Exception as exc:
            enw_status = f"failed: {exc}"
            print(f"WARN: enw conversion failed ({exc}); .bib still available.")

    # Archive snapshot under project
    shutil.copy2(bib_path, archive_bib)
    print(f"-> archived {archive_bib}")

    # Log
    record = {
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "bib_source": str(bib_path),
        "bib_archive": str(archive_bib),
        "inbox_bib": str(inbox_bib),
        "inbox_enw": str(inbox_enw) if has_bibutils else None,
        "project": args.project,
        "entry_count_estimate": entry_count,
        "bibutils_used": has_bibutils,
        "enw_status": enw_status,
    }
    append_log(log_path, record)
    print(f"-> log appended at {log_path}")

    # Manual import reminder
    suggested = inbox_enw if has_bibutils and enw_status == "ok" else inbox_bib
    suggested_filter = "EndNote Import" if suggested.suffix == ".enw" else "BibTeX"
    print()
    print("=" * 60)
    print("📚 NEXT — manual EndNote 21 import (≈ 30 seconds):")
    print(f"  1. Open EndNote 21 → File → Import → File…")
    print(f"  2. Choose: {suggested}")
    print(f"  3. Import Option: {suggested_filter}")
    print(f"  4. Click Import")
    print(f"  5. (Optional) In sidebar: Groups → Create Group Set →")
    print(f"     name it '{args.project}' →")
    print(f"     drag refs from 'Imported References' into the new group set")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
