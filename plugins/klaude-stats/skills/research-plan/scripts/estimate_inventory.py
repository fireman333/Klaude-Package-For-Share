#!/usr/bin/env python3
"""Inventory every estimate the pipeline produced, and diff it against what got reported.

Why this exists
---------------
"23 exposure-stratum estimates were executed, 7 reached the deliverable" is a set
difference. It was being discovered by asking an LLM to go and look for things
that were not there — the one search task where a miss is invisible, because a
missed omission and a clean report produce identical output.

This script computes the difference and hands it over. The judgement that stays
with a human (or an LLM) is the one that actually needs judgement: are the
omissions directionally convenient for the hypothesis?

What it reads
-------------
  executed  every `.xlsx` under OUTPUT_DIR and every `*_stats.json` anywhere under it
  reported  every number appearing in the report / manuscript files given with
            --reported (default: `*.md` in OUTPUT_DIR and its parent)

Matching is by value with a relative tolerance, because a report writes 2.22 for
an underlying 2.2183. Anything unmatched is listed, never auto-classified.

Usage
    python3 estimate_inventory.py OUTPUT_DIR [--reported FILE ...] [--report PATH]
                                  [--tolerance 0.005] [--quiet]

Exit codes (same convention as assets/check_freshness.py)
    0  ran, and every executed estimate is accounted for
    1  ran, and at least one executed estimate is missing from the deliverables
    2  cannot run (missing directory, nothing to scan)
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import re
import sys
from datetime import datetime

# Number-like cells: 3.42 (2.21-5.30) / 231 (116) / <0.001* / 0.0043
_DASHES = "–—−-"
_EFFECT_RE = re.compile(
    rf"(-?\d+(?:\.\d+)?)\s*\(\s*(-?\d+(?:\.\d+)?)\s*[{_DASHES}]\s*(-?\d+(?:\.\d+)?)\s*\)"
)
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_P_CELL_RE = re.compile(r"^\s*[<>]?\s*(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*\*?\s*$")

# Column headers that mark a value as an estimate / CI bound / p-value.
#
# Deliberately EXCLUDES the log-scale headers (beta / coef / coefficient) that
# precheck_configs._ESTIMATE_HEADER_SCALES knows about. This is a coverage
# inventory: it counts estimates a manuscript is expected to account for, and a
# log coefficient sitting beside the hazard ratio it exponentiates to is the
# same estimate written twice. Counting it inflates the denominator.
#
# It used to contain "coef" and "beta" but not "coefficient", so the same column
# counted once or twice depending on how the producing script spelled its
# header -- and only when the coefficient was positive, because _P_CELL_RE
# rejects a leading minus. No shipped table spells it "Coef", so nothing
# double-counted in practice; the trap was that renaming a header would have
# silently moved the C7 denominator.
#
# test_pipeline_contract.py pins this against the precheck vocabulary.
_EFFECT_HEADERS = ("or", "hr", "rr", "shr", "estimate",
                   "hazard ratio", "odds ratio", "risk ratio", "rate ratio",
                   "subdistribution hazard ratio",
                   "or (95% ci)", "hr (95% ci)", "c-index", "c index", "auc")
_P_HEADERS = ("p", "p-value", "p value", "pvalue", "p_value")
_CI_LOW_HEADERS = ("95% ci lower", "ci_lower", "ci low", "lower")
_CI_HIGH_HEADERS = ("95% ci upper", "ci_upper", "ci high", "upper")


def _norm_header(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def iter_xlsx_cells(path):
    """Yield (sheet, row, col, value) for every non-empty cell of a workbook."""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        for ws in wb.worksheets:
            for r, row in enumerate(ws.iter_rows(values_only=True), start=1):
                for c, value in enumerate(row, start=1):
                    if value is not None and str(value).strip() != "":
                        yield ws.title, r, c, value
    finally:
        wb.close()


def _row_label(cells_in_row):
    """First non-numeric cell of a row, used as the estimate's human handle."""
    for _c, value in sorted(cells_in_row.items()):
        text = str(value).strip()
        if text and not _NUMBER_RE.fullmatch(text):
            return text
    return ""


def scan_workbook(path):
    """Extract estimates from one workbook.

    Two shapes are recognised, which between them cover every output this
    pipeline writes:
      - a formatted cell `3.42 (2.21-5.30)` (the Excel deliverables)
      - separate estimate / CI-lower / CI-upper columns (the CSV companions
        and the wider supplementary sheets)
    """
    rows = {}
    for sheet, r, c, value in iter_xlsx_cells(path):
        rows.setdefault((sheet, r), {})[c] = value

    # Locate header columns per sheet: the first row whose cells look like headers.
    header_cols = {}
    for (sheet, r), cells in sorted(rows.items()):
        for c, value in cells.items():
            h = _norm_header(value)
            if h in _P_HEADERS:
                header_cols.setdefault(sheet, {})[c] = "p"
            elif h in _CI_LOW_HEADERS:
                header_cols.setdefault(sheet, {})[c] = "ci_low"
            elif h in _CI_HIGH_HEADERS:
                header_cols.setdefault(sheet, {})[c] = "ci_high"
            elif h in _EFFECT_HEADERS:
                header_cols.setdefault(sheet, {})[c] = "estimate"

    found = []
    for (sheet, r), cells in sorted(rows.items()):
        label = _row_label(cells)
        roles = header_cols.get(sheet, {})
        packed = {}
        packed_col = None
        for c, value in sorted(cells.items()):
            text = str(value)
            m = _EFFECT_RE.search(text)
            if m:
                found.append({
                    "source": os.path.basename(path), "sheet": sheet, "row": r,
                    "col": c, "label": label,
                    "estimate": float(m.group(1)),
                    "ci_low": float(m.group(2)),
                    "ci_high": float(m.group(3)),
                    "p": None,
                })
                continue
            role = roles.get(c)
            if role:
                pm = _P_CELL_RE.match(text)
                if pm:
                    packed[role] = float(pm.group(1))
                    if role == "estimate":
                        packed_col = c
        if packed.get("estimate") is not None:
            found.append({
                "source": os.path.basename(path), "sheet": sheet, "row": r,
                "col": packed_col, "label": label,
                "estimate": packed.get("estimate"),
                "ci_low": packed.get("ci_low"),
                "ci_high": packed.get("ci_high"),
                "p": packed.get("p"),
            })
        elif packed.get("p") is not None and found and found[-1]["row"] == r:
            found[-1]["p"] = packed["p"]
    return found


def sha256_file(path):
    """Content hash of one file, or None when it cannot be read.

    Content, not mtime. A coverage audit is stale when the workbooks it scanned
    have been rebuilt, and mtime answers that question only until someone runs
    `touch` — or until a rebuild happens to preserve the timestamp. The hash
    says whether these are the same bytes that were audited.
    """
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError as exc:
        print(f"  [SKIP] cannot hash {os.path.basename(path)}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    return h.hexdigest()


def plan_fingerprint_for(plan):
    """(fingerprint, error) using reviewer_challenge's definition.

    Imported rather than reimplemented: a fingerprint computed from a diverged
    field list would silently disagree with every other consumer of it, which is
    worse than not having one.
    """
    if not plan:
        return None, "no plan was available to fingerprint"
    try:
        from reviewer_challenge import plan_fingerprint
    except Exception as exc:
        return None, f"reviewer_challenge could not be imported ({type(exc).__name__}: {exc})"
    try:
        return plan_fingerprint(plan), None
    except Exception as exc:
        return None, f"plan_fingerprint failed ({type(exc).__name__}: {exc})"


def estimate_id(record, workbook, index=0):
    """The join key between run_pipeline's ledger and coverage_diff.json.

    Exported because it is a contract between two files, and a contract that
    each side reimplements is a coincidence. run_pipeline.py built this string
    itself; the two already differed latently — this one strips the extension
    off the workbook name, that one used the plan's `output_file` verbatim, so a
    plan declaring "PSM.xlsx" instead of "PSM" produced ids that would never
    join. Add an extension, normalise a label or append a collision suffix here
    and every id in the ledger silently stops matching.

    The column is in the key because a row can hold more than one estimate. It
    could not until the AUC step learned to measure incremental value: that
    table reports the candidate alone, the clinical model, the clinical model
    plus the candidate and their difference — four different numbers, one row,
    one row label. Without the column all four answered to
    `AUC:AUC Analysis:5:Exposed, n (%)`, so the omission listing printed the
    same handle beside three different values and no join could tell the base
    model's discrimination from the full model's. Column, not a collision
    counter: a counter depends on the order cells happen to be scanned in, and
    an id that moves when nothing moved is the failure this docstring is about.
    """
    stem = os.path.splitext(os.path.basename(str(workbook)))[0]
    sheet = record.get("sheet") or "json"
    row = record.get("row") or index
    col = record.get("col")
    label = str(record.get("label") or "")[:40]
    return f"{stem}:{sheet}:{row}:{col if col is not None else '-'}:{label}"


def _walk_json(node, path=""):
    """Yield (dotted_key, numeric_value) for every number in a stats JSON."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_json(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_json(v, f"{path}[{i}]")
    elif isinstance(node, bool):
        return
    elif isinstance(node, (int, float)) and math.isfinite(node):
        yield path, float(node)


def scan_stats_json(path):
    """Extract every numeric leaf of a *_stats.json as a candidate estimate."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [{"source": os.path.basename(path), "sheet": None, "row": None,
             "label": key, "estimate": value, "ci_low": None, "ci_high": None,
             "p": None}
            for key, value in _walk_json(data)]


def collect_executed(output_dir, quiet=False):
    """Every estimate the pipeline wrote. Returns (records, counters)."""
    workbooks = sorted(p for p in glob.glob(os.path.join(output_dir, "**", "*.xlsx"),
                                            recursive=True)
                       if not os.path.basename(p).startswith("~$"))
    stats_files = sorted(glob.glob(os.path.join(output_dir, "**", "*_stats.json"),
                                   recursive=True))
    records, processed, skipped = [], 0, 0

    for path in workbooks:
        try:
            found = scan_workbook(path)
        except Exception as exc:
            skipped += 1
            print(f"  [SKIP] {os.path.basename(path)}: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            continue
        processed += 1
        for rec in found:
            rec["source_path"] = path
        records.extend(found)
        if not quiet:
            print(f"  {os.path.basename(path):<34s} {len(found)} estimate(s)", file=sys.stderr)

    for path in stats_files:
        try:
            found = scan_stats_json(path)
        except Exception as exc:
            skipped += 1
            print(f"  [SKIP] {os.path.basename(path)}: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            continue
        processed += 1
        for rec in found:
            rec["source_path"] = path
        records.extend(found)
        if not quiet:
            print(f"  {os.path.basename(path):<34s} {len(found)} value(s)", file=sys.stderr)

    for i, rec in enumerate(records):
        rec["analysis_id"] = os.path.splitext(rec["source"])[0]
        rec["estimate_id"] = estimate_id(rec, rec["source"], i)

    counters = {"processed": processed, "skipped": skipped,
                "total": processed + skipped, "estimates": len(records)}
    return records, counters


_TEXT_DELIVERABLE_EXT = (".md", ".txt", ".markdown", ".rst", ".html", ".csv", ".tex")


def read_deliverable(path):
    """Text of one deliverable, or None when the format has no reader here.

    `.docx` is handled because that is what `manuscript-results` writes
    (`Results_Section.docx`). Reading only markdown meant the pipeline's own
    manuscript was invisible to this check, and every estimate in it would have
    been reported as omitted.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        try:
            import docx
        except ImportError:
            print("  [SKIP] python-docx is not installed; .docx deliverables cannot "
                  "be read (python3 -m pip install python-docx)", file=sys.stderr)
            return None
        document = docx.Document(path)
        chunks = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                chunks.extend(cell.text for cell in row.cells)
        return "\n".join(chunks)
    if ext in _TEXT_DELIVERABLE_EXT or ext == "":
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    return None


def default_report_files(output_dir):
    """Report / manuscript candidates: prose deliverables in OUTPUT_DIR and its parent."""
    parent = os.path.dirname(os.path.abspath(output_dir.rstrip(os.sep)))
    patterns = []
    for ext in ("md", "docx"):
        patterns.append(os.path.join(output_dir, "**", f"*.{ext}"))
        patterns.append(os.path.join(parent, f"*.{ext}"))
    files = []
    for pat in patterns:
        files.extend(glob.glob(pat, recursive=True))
    # Working files this tool writes itself are not deliverables.
    skip = ("decision_log.md", "coverage_diff.json")
    return sorted(f for f in set(files)
                  if os.path.basename(f) not in skip
                  and not os.path.basename(f).startswith("~$"))


def collect_reported(files, quiet=False):
    """Every number quoted in the deliverable prose. Returns (values, counters)."""
    values, processed, skipped = [], 0, 0
    for path in files:
        try:
            text = read_deliverable(path)
        except Exception as exc:
            skipped += 1
            print(f"  [SKIP] {path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if text is None:
            skipped += 1
            print(f"  [SKIP] {path}: no reader for this file type; its numbers were "
                  f"not compared", file=sys.stderr)
            continue
        processed += 1
        hits = 0
        for line_no, line in enumerate(text.splitlines(), start=1):
            for m in _NUMBER_RE.finditer(line):
                try:
                    val = float(m.group(0))
                except ValueError:
                    continue
                values.append({"value": val, "file": os.path.basename(path),
                               "line": line_no, "context": line.strip()[:160]})
                hits += 1
        if not quiet:
            print(f"  {os.path.basename(path):<34s} {hits} number(s)", file=sys.stderr)
    counters = {"processed": processed, "skipped": skipped,
                "total": processed + skipped, "numbers": len(values)}
    return values, counters


def _close(a, b, tolerance):
    """Relative match with an absolute floor, so 0.0 and small p-values behave."""
    if a is None or b is None:
        return False
    if not (math.isfinite(a) and math.isfinite(b)):
        return False
    scale = max(abs(a), abs(b), 1e-6)
    return abs(a - b) <= max(tolerance * scale, 5e-4)


def _rounded_forms(value):
    """The ways a report could legitimately print this number."""
    forms = {value}
    for digits in (1, 2, 3):
        try:
            forms.add(round(value, digits))
        except (TypeError, ValueError):
            continue
    return forms


def diff_coverage(executed, reported, tolerance):
    """Which executed estimates appear in the prose, and which do not."""
    reported_values = [r["value"] for r in reported]
    covered, omitted = [], []
    for rec in executed:
        est = rec.get("estimate")
        if est is None:
            continue
        hit = None
        for form in _rounded_forms(est):
            for i, val in enumerate(reported_values):
                if _close(form, val, tolerance):
                    hit = reported[i]
                    break
            if hit:
                break
        entry = dict(rec)
        if hit:
            entry["matched_in"] = {"file": hit["file"], "line": hit["line"],
                                   "context": hit["context"]}
            covered.append(entry)
        else:
            omitted.append(entry)
    return covered, omitted


# `status` values written into coverage_diff.json. The watchdog's C7 keys off
# these: the point is that "the deliverable does not exist yet" and "the
# deliverable exists and omits 16 estimates" are different states that must not
# both look like an empty omitted list.
STATUS_COMPARED = "compared"
STATUS_NO_DELIVERABLE = "no_deliverable_found"
STATUS_UNREADABLE = "deliverable_unreadable"


def build_coverage(output_dir, reported_files=None, tolerance=0.005, quiet=True,
                   plan=None):
    """Compute the coverage payload. No printing, no exiting, no file written.

    The single implementation behind both entry points — the CLI below and
    `precheck_configs.py --stage post`. Raises ValueError when it cannot run at
    all, so neither caller has to reproduce that judgement.
    """
    if not os.path.isdir(output_dir):
        raise ValueError(f"not a directory: {output_dir}")

    executed, exec_counts = collect_executed(output_dir, quiet=quiet)
    if exec_counts["estimates"] == 0:
        raise ValueError("no estimates found; nothing to diff. Has the pipeline run?")

    searched_default = not reported_files
    if searched_default:
        reported_files = default_report_files(output_dir)
    reported, rep_counts = collect_reported(reported_files, quiet=quiet)

    if not reported_files:
        status = STATUS_NO_DELIVERABLE
    elif rep_counts["processed"] == 0:
        status = STATUS_UNREADABLE
    else:
        status = STATUS_COMPARED

    # Only a deliverable that was actually read can be omitted *from*. Calling
    # every estimate "omitted" because no manuscript exists yet would turn a
    # normal mid-pipeline state into 20 findings.
    if status == STATUS_COMPARED:
        covered, omitted = diff_coverage(executed, reported, tolerance)
    else:
        covered, omitted = [], []

    if plan is None:
        candidate = os.path.join(output_dir, "research_plan.json")
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    plan = json.load(f)
            except Exception as exc:
                print(f"  [SKIP] could not read {candidate} for the plan fingerprint "
                      f"({type(exc).__name__}: {exc})", file=sys.stderr)
    fingerprint, fingerprint_error = plan_fingerprint_for(plan)

    source_hashes = {}
    for rec in records_with_paths(executed):
        name, path = rec
        if name not in source_hashes:
            source_hashes[name] = sha256_file(path)
    deliverable_hashes = {os.path.basename(p): sha256_file(p)
                          for p in (reported_files or []) if os.path.exists(p)}

    generated_at = datetime.now().isoformat()
    return {
        "generated_at": generated_at,
        "output_dir": os.path.abspath(output_dir),
        "tolerance": tolerance,
        "status": status,
        # Provenance, so a consumer can tell "this audit covers these bytes" from
        # "this audit is left over from the previous run". Keyed by the same
        # `source` basename the `executed` records carry, so the two join without
        # a translation step.
        "provenance": {
            "generated_at": generated_at,
            "hash_algorithm": "sha256",
            "plan_fingerprint": fingerprint,
            "plan_fingerprint_error": fingerprint_error,
            "source_hashes": source_hashes,
            "deliverable_hashes": deliverable_hashes,
        },
        "counters": {"executed_files": exec_counts, "reported_files": rep_counts,
                     "executed_estimates": len(executed),
                     "reported_estimates": len(covered),
                     "omitted_estimates": len(omitted)},
        "reported_source_files": [os.path.basename(p) for p in reported_files],
        "searched_default_locations": searched_default,
        "executed": executed,
        "reported": covered,
        "omitted": omitted,
        "note": ("Omitted entries are unmatched by value, not judged. The question "
                 "that needs a human: are these omissions directionally convenient "
                 "for the hypothesis? When status is not 'compared', `omitted` is "
                 "empty because there was nothing to omit from — read `status`, not "
                 "the length of the list."),
    }


def records_with_paths(records):
    """(basename, full path) for every distinct source file behind the records."""
    seen = set()
    for rec in records:
        name, path = rec.get("source"), rec.get("source_path")
        if name and path and name not in seen:
            seen.add(name)
            yield name, path


def write_coverage(payload, output_dir, report_path=None):
    out_path = report_path or os.path.join(output_dir, "coverage_diff.json")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out_path


def run(output_dir, reported_files, report_path, tolerance, quiet, plan_path=None):
    print(f"estimate_inventory.py — scanning {output_dir}", file=sys.stderr)
    plan = None
    if plan_path:
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
        except Exception as exc:
            print(f"[QC_WARNING] --plan {plan_path} could not be read "
                  f"({type(exc).__name__}: {exc}); the coverage report will carry no "
                  f"plan fingerprint", file=sys.stderr)
    try:
        payload = build_coverage(output_dir, reported_files, tolerance, quiet, plan)
    except ValueError as exc:
        print(f"[QC_BLOCKING] {exc}", file=sys.stderr)
        return 2

    counters = payload["counters"]
    print(f"  executed: processed {counters['executed_files']['processed']} / skipped "
          f"{counters['executed_files']['skipped']} / total "
          f"{counters['executed_files']['total']} file(s), "
          f"{counters['executed_estimates']} estimate(s)", file=sys.stderr)
    print(f"  reported: processed {counters['reported_files']['processed']} / skipped "
          f"{counters['reported_files']['skipped']} / total "
          f"{counters['reported_files']['total']} file(s), "
          f"{counters['reported_files']['numbers']} number(s)", file=sys.stderr)

    out_path = write_coverage(payload, output_dir, report_path)
    omitted = payload["omitted"]

    if payload["status"] != STATUS_COMPARED:
        print(f"\ncoverage: status={payload['status']} — "
              f"{counters['executed_estimates']} estimate(s) inventoried, nothing to "
              f"compare them against", file=sys.stderr)
        print(f"[QC_WARNING] COVERAGE: {payload['status']}; no deliverable was read, so "
              f"selective presentation could not be assessed. Searched: "
              f"{payload['reported_source_files'] or 'the default locations'}",
              file=sys.stderr)
        print(f"Report written: {out_path}", file=sys.stderr)
        return 0

    print(f"\ncoverage: {len(payload['reported'])} reported / {len(omitted)} omitted / "
          f"{counters['executed_estimates']} executed", file=sys.stderr)
    if omitted:
        print(f"[QC_WARNING] COVERAGE: {len(omitted)} executed estimate(s) do not appear "
              f"in the deliverables; see {os.path.basename(out_path)} :: omitted",
              file=sys.stderr)
        for rec in omitted[:10]:
            print(f"    - {rec['estimate_id']} = {rec['estimate']}", file=sys.stderr)
        if len(omitted) > 10:
            print(f"    ... and {len(omitted) - 10} more", file=sys.stderr)
    print(f"Report written: {out_path}", file=sys.stderr)
    return 1 if omitted else 0


def main():
    parser = argparse.ArgumentParser(
        description="Inventory every executed estimate and diff it against the numbers "
                    "quoted in the report / manuscript. Writes coverage_diff.json.")
    parser.add_argument("output_dir", help="Pipeline OUTPUT_DIR (holds the .xlsx outputs)")
    parser.add_argument("--reported", nargs="*", default=None,
                        help="Report / manuscript files to scan for quoted numbers "
                             "(default: *.md in OUTPUT_DIR and its parent)")
    parser.add_argument("--report", help="Where to write coverage_diff.json "
                                         "(default <output_dir>/coverage_diff.json)")
    parser.add_argument("--tolerance", type=float, default=0.005,
                        help="Relative tolerance when matching a reported number to an "
                             "executed estimate (default 0.005)")
    parser.add_argument("--plan", help="research_plan.json, for the plan fingerprint "
                                       "(default <output_dir>/research_plan.json)")
    parser.add_argument("--quiet", action="store_true", help="Suppress the per-file listing")
    args = parser.parse_args()
    return run(args.output_dir, args.reported, args.report, args.tolerance, args.quiet,
               args.plan)


if __name__ == "__main__":
    sys.exit(main())
