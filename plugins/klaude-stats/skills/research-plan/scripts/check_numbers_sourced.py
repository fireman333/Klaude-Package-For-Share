#!/usr/bin/env python3
"""Assert that every number in a report can be traced to a machine-generated source.

Why this exists
---------------
Third-party acceptance was checking 543 numbers cell by cell and finding 9 wrong.
That is the low-yield half of the job, and it is arithmetic: does this printed
value occur in any stats file or output workbook, within rounding tolerance.

This script does that half. What is left for a reader is the half that pays:
whether the sourced numbers are the *right* numbers, and what is missing (that
is `estimate_inventory.py`, which runs the diff in the other direction).

Every number the script deliberately does not check — the 95 in "95% CI", a
figure number, a year — is recorded with its reason, so the exclusions are
auditable rather than invisible.

Usage
    python3 check_numbers_sourced.py REPORT [REPORT ...] --output-dir OUTPUT_DIR
                                     [--report PATH] [--tolerance 0.005] [--quiet]

Exit codes (same convention as assets/check_freshness.py)
    0  every checked number resolved to a source
    1  at least one number could not be sourced
    2  cannot run (no reports, no sources)
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys
from datetime import datetime

try:
    from estimate_inventory import _walk_json, iter_xlsx_cells
except ImportError as exc:  # pragma: no cover - surfaced, never silent
    sys.exit(f"[QC_BLOCKING] check_numbers_sourced.py must sit next to "
             f"estimate_inventory.py ({exc})")

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

# Numbers that are structural, not results. Each pattern is matched against the
# 24 characters either side of the number; the first hit becomes the recorded
# reason so a reader can challenge the exclusion.
_IGNORE_CONTEXTS = [
    (re.compile(r"\d\s*%\s*CI", re.IGNORECASE), "confidence-level marker"),
    (re.compile(r"\bCI\b", re.IGNORECASE), "confidence-interval label"),
    (re.compile(r"\bTable\s*\d", re.IGNORECASE), "table number"),
    (re.compile(r"\bFigure\s*\d", re.IGNORECASE), "figure number"),
    (re.compile(r"\bSupplement(ary)?\s*\w*\s*\d", re.IGNORECASE), "supplement number"),
    (re.compile(r"\bversion\s*\d", re.IGNORECASE), "version number"),
    (re.compile(r"\bSTROBE\b", re.IGNORECASE), "STROBE item number"),
    (re.compile(r"\bref(erence)?\.?\s*\[?\d", re.IGNORECASE), "citation marker"),
]
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_LIST_MARKER_RE = re.compile(r"^\s*\d+[.)]\s")


def collect_sources(output_dir, quiet=False):
    """Every number any machine-generated artefact under OUTPUT_DIR contains.

    Returns (values, index, counters) where `index` maps a rounded key to a
    provenance record so a match can say *where* the number came from.
    """
    workbooks = sorted(p for p in glob.glob(os.path.join(output_dir, "**", "*.xlsx"),
                                            recursive=True)
                       if not os.path.basename(p).startswith("~$"))
    jsons = sorted(set(glob.glob(os.path.join(output_dir, "**", "*_stats.json"),
                                 recursive=True))
                   | set(glob.glob(os.path.join(output_dir, "**", "*.json"),
                                   recursive=True)))
    # Configuration is not a result. Sourcing a printed number against the config
    # that produced the analysis would let a hand-typed value vouch for itself.
    _EXCLUDED_JSON = ("manifest.json", "research_plan.json", "coverage_diff.json",
                      "precheck_report.json", "numbers_sourced_report.json")
    jsons = [p for p in jsons
             if os.path.basename(p) not in _EXCLUDED_JSON
             and f"{os.sep}configs{os.sep}" not in p
             and f"{os.sep}logs{os.sep}" not in p]

    values, index, processed, skipped = [], {}, 0, 0

    def record(value, where):
        """Index a source value under every precision a report could print it at.

        Keyed by (decimals, rounded value) rather than by the rounded value
        alone: a report that prints `9.99` must be matched against a source that
        rounds to 9.99 at two decimals, not against anything that happens to
        round to 10 at zero decimals.
        """
        if not math.isfinite(value):
            return
        values.append(value)
        for digits in (0, 1, 2, 3, 4):
            index.setdefault((digits, round(value, digits)), where)

    for path in workbooks:
        try:
            n_before = len(values)
            for sheet, r, c, cell in iter_xlsx_cells(path):
                for m in _NUMBER_RE.finditer(str(cell)):
                    try:
                        record(float(m.group(0)),
                               f"{os.path.basename(path)}!{sheet}!r{r}c{c}")
                    except ValueError:
                        continue
            processed += 1
            if not quiet:
                print(f"  {os.path.basename(path):<34s} {len(values) - n_before} value(s)",
                      file=sys.stderr)
        except Exception as exc:
            skipped += 1
            print(f"  [SKIP] {os.path.basename(path)}: {type(exc).__name__}: {exc}",
                  file=sys.stderr)

    for path in jsons:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            n_before = len(values)
            for key, value in _walk_json(data):
                record(value, f"{os.path.basename(path)}::{key}")
            processed += 1
            if not quiet:
                print(f"  {os.path.basename(path):<34s} {len(values) - n_before} value(s)",
                      file=sys.stderr)
        except Exception as exc:
            skipped += 1
            print(f"  [SKIP] {os.path.basename(path)}: {type(exc).__name__}: {exc}",
                  file=sys.stderr)

    counters = {"processed": processed, "skipped": skipped,
                "total": processed + skipped, "values": len(values)}
    return values, index, counters


def should_ignore(line, start, end, token):
    """Return a reason string when this number is structural, else None."""
    window = line[max(0, start - 24):min(len(line), end + 24)]
    for pattern, reason in _IGNORE_CONTEXTS:
        if pattern.search(window):
            return reason
    if _YEAR_RE.match(token):
        return "looks like a calendar year"
    if _HEADING_RE.match(line) and start <= len(line) - len(line.lstrip()) + 8:
        return "heading numbering"
    if _LIST_MARKER_RE.match(line) and start < 6:
        return "list marker"
    return None


def _decimals(token):
    """How many decimal places the report actually printed."""
    if "e" in token.lower():
        return 4
    return len(token.split(".")[1]) if "." in token else 0


def _sourced(value, token, index, source_values, tolerance):
    """Find a provenance record for `value` as printed in `token`, or None."""
    d = min(_decimals(token), 4)
    for digits in {d, max(d - 1, 0), min(d + 1, 4)}:
        hit = index.get((digits, round(value, digits)))
        if hit:
            return hit
    if tolerance > 0:
        for candidate in source_values:
            scale = max(abs(value), abs(candidate), 1e-6)
            if abs(value - candidate) <= tolerance * scale:
                return f"value match within tolerance (~{candidate:g})"
    return None


def check_report(path, index, source_values, tolerance):
    """Classify every number in one report file."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    sourced, unsourced, ignored = [], [], []
    for line_no, line in enumerate(lines, start=1):
        for m in _NUMBER_RE.finditer(line):
            token = m.group(0)
            try:
                value = float(token)
            except ValueError:
                continue
            reason = should_ignore(line, m.start(), m.end(), token)
            entry = {"file": os.path.basename(path), "line": line_no,
                     "value": value, "text": token, "context": line.strip()[:180]}
            if reason:
                entry["reason"] = reason
                ignored.append(entry)
                continue
            where = _sourced(value, token, index, source_values, tolerance)
            if where:
                entry["source"] = where
                sourced.append(entry)
            else:
                unsourced.append(entry)
    return sourced, unsourced, ignored


def run(report_files, output_dir, report_path, tolerance, quiet):
    if not report_files:
        print("[QC_BLOCKING] no report files given", file=sys.stderr)
        return 2
    if not os.path.isdir(output_dir):
        print(f"[QC_BLOCKING] not a directory: {output_dir}", file=sys.stderr)
        return 2

    print(f"check_numbers_sourced.py — sources under {output_dir}", file=sys.stderr)
    source_values, index, src_counts = collect_sources(output_dir, quiet=quiet)
    print(f"  sources: processed {src_counts['processed']} / skipped "
          f"{src_counts['skipped']} / total {src_counts['total']} file(s), "
          f"{src_counts['values']} value(s)", file=sys.stderr)
    if not source_values:
        print("[QC_BLOCKING] no machine-generated numbers found; nothing to source against",
              file=sys.stderr)
        return 2

    all_sourced, all_unsourced, all_ignored = [], [], []
    processed = skipped = 0
    for path in report_files:
        try:
            sourced, unsourced, ignored = check_report(path, index, source_values, tolerance)
        except Exception as exc:
            skipped += 1
            print(f"  [SKIP] {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        processed += 1
        all_sourced.extend(sourced)
        all_unsourced.extend(unsourced)
        all_ignored.extend(ignored)
        if not quiet:
            print(f"  {os.path.basename(path):<34s} {len(sourced)} sourced / "
                  f"{len(unsourced)} unsourced / {len(ignored)} structural",
                  file=sys.stderr)

    print(f"  reports: processed {processed} / skipped {skipped} / "
          f"total {processed + skipped} file(s)", file=sys.stderr)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "output_dir": os.path.abspath(output_dir),
        "report_files": [os.path.abspath(p) for p in report_files],
        "tolerance": tolerance,
        "counters": {"sources": src_counts,
                     "reports_processed": processed, "reports_skipped": skipped,
                     "sourced": len(all_sourced), "unsourced": len(all_unsourced),
                     "structural_ignored": len(all_ignored)},
        "unsourced": all_unsourced,
        "sourced": all_sourced,
        "structural_ignored": all_ignored,
        "note": ("`unsourced` is a list for a human to read, not a verdict: a number "
                 "may be legitimately derived (a difference, a percentage) rather than "
                 "copied. What it rules out is a number that was typed."),
    }
    out_path = report_path or os.path.join(output_dir, "numbers_sourced_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\nnumbers: {len(all_sourced)} sourced / {len(all_unsourced)} unsourced / "
          f"{len(all_ignored)} structural", file=sys.stderr)
    if all_unsourced:
        print(f"[QC_WARNING] SOURCE: {len(all_unsourced)} reported number(s) do not "
              f"resolve to any stats file or output workbook", file=sys.stderr)
        for e in all_unsourced[:15]:
            print(f"    - {e['file']}:{e['line']} {e['text']}  |  {e['context']}",
                  file=sys.stderr)
        if len(all_unsourced) > 15:
            print(f"    ... and {len(all_unsourced) - 15} more", file=sys.stderr)
    print(f"Report written: {out_path}", file=sys.stderr)
    return 1 if all_unsourced else 0


def main():
    parser = argparse.ArgumentParser(
        description="Check that every number in a report resolves to a machine-generated "
                    "stats file or output workbook.")
    parser.add_argument("reports", nargs="+", help="Report / manuscript files to check")
    parser.add_argument("--output-dir", required=True,
                        help="Pipeline OUTPUT_DIR holding the .xlsx / *_stats.json sources")
    parser.add_argument("--report", help="Where to write numbers_sourced_report.json "
                                         "(default <output_dir>/numbers_sourced_report.json)")
    parser.add_argument("--tolerance", type=float, default=0.0,
                        help="Extra relative slack on top of the rounding match, for unit "
                             "conversions (default 0.0 = rounding match only)")
    parser.add_argument("--quiet", action="store_true", help="Suppress the per-file listing")
    args = parser.parse_args()
    return run(args.reports, args.output_dir, args.report, args.tolerance, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
