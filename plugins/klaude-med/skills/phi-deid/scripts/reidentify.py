#!/usr/bin/env python3
"""
phi-deid reverse step — take an LLM-drafted de-identified note and put real PHI back.

Usage:
    python reidentify.py --session bed12_APR --input deid_progress_draft.txt

Outputs:
    Writes the real-PHI version to session/final_<inputname>.PHI_DO_NOT_READ.txt
    Writes a human-readable report to session/reidentify_report.txt (no PHI)
    Prints JSON summary to stdout.

Exit codes:
    0 — success, no warnings
    2 — success but warnings (unknown pseudonym, coverage loss, merge ambiguity)

The three failure modes we detect:
    1. Unknown pseudonym — LLM invented a token not in mapping. Leave literal.
    2. Dropped anchor — LLM used fewer pseudonym tokens than original deid.txt.
       Indicates the LLM may have paraphrased PATIENT_01 into "病人".
    3. Merged patients — text contains "兩位病人"/"兩人" without a nearby
       pseudonym, when the original had multiple distinct pseudonyms.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import regex as re

sys.path.insert(0, str(Path(__file__).resolve().parent))

import date_shift
import mapping

# Pattern for pseudonym tokens: [PREFIX_01]
_TOKEN_RE = re.compile(r"\[([A-Z_]+)_(\d{2,4})\]")
_MERGE_PHRASES = [r"兩位病人", r"兩位個案", r"兩人", r"倆人", r"這兩位"]
_MERGE_RE = re.compile("|".join(_MERGE_PHRASES))


def _scan_tokens(text: str) -> list[tuple[str, int, int]]:
    """Return list of (token, start, end)."""
    return [(m.group(0), m.start(), m.end()) for m in _TOKEN_RE.finditer(text)]


def _apply_reverse_mapping(text: str, forward_map: dict[str, str]) -> tuple[str, list[str]]:
    """Replace pseudonym tokens in text with real values. Return (new_text, unknown_tokens).

    forward_map: token -> real_text (e.g. '[PATIENT_01]' -> '王小明')
    """
    unknown: list[str] = []

    def sub_fn(m: re.Match) -> str:
        token = m.group(0)
        if token in forward_map:
            return forward_map[token]
        unknown.append(token)
        return token  # leave literal

    result = _TOKEN_RE.sub(sub_fn, text)
    return result, unknown


def _coverage_check(original_deid: str, llm_draft: str) -> list[str]:
    """Compare token counts between original deid.txt and LLM draft.

    Returns warnings for each token whose count dropped.
    """
    from collections import Counter

    orig = Counter(m.group(0) for m in _TOKEN_RE.finditer(original_deid))
    draft = Counter(m.group(0) for m in _TOKEN_RE.finditer(llm_draft))

    warnings: list[str] = []
    for token, orig_n in orig.items():
        draft_n = draft.get(token, 0)
        if draft_n < orig_n:
            warnings.append(
                f"Coverage drop: {token} appeared {orig_n}x in deid.txt but only "
                f"{draft_n}x in draft — potential anchor loss (LLM paraphrased it?)"
            )
    # Tokens invented by LLM (not in original)
    for token, draft_n in draft.items():
        if token not in orig:
            warnings.append(
                f"Invented token: {token} appears in draft but not in original deid.txt"
            )
    return warnings


def _merge_check(llm_draft: str, window: int = 30) -> list[str]:
    """Look for merge phrases without a nearby pseudonym token."""
    warnings: list[str] = []
    for m in _MERGE_RE.finditer(llm_draft):
        lo = max(0, m.start() - window)
        hi = min(len(llm_draft), m.end() + window)
        if not _TOKEN_RE.search(llm_draft[lo:hi]):
            warnings.append(
                f"Possible patient merge: phrase {m.group(0)!r} at offset {m.start()} "
                f"with no pseudonym within {window} chars"
            )
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reverse phi-deid — substitute pseudonyms with real PHI, reverse date shift."
    )
    parser.add_argument("--session", required=True, help="Session alias (patient-key from deid.py)")
    parser.add_argument(
        "--input",
        required=True,
        help="Path to LLM-drafted note (contains pseudonym tokens like [PATIENT_01])",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path. Default: session/final_<input name>.PHI_DO_NOT_READ.txt",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Override session root (default: ~/phi-deid-sessions)",
    )
    args = parser.parse_args()

    root = Path(args.root) if args.root else mapping.DEFAULT_ROOT

    # --- Load session ---
    try:
        session = mapping.Session.load(args.session, root=root)
    except (KeyError, FileNotFoundError) as e:
        print(json.dumps({"error": str(e)}))
        return 1

    # --- Read LLM draft ---
    draft_path = Path(args.input).expanduser()
    if not draft_path.exists():
        print(json.dumps({"error": f"input file not found: {draft_path}"}))
        return 1
    draft_text = draft_path.read_text(encoding="utf-8")

    # --- Coverage + merge checks (against original deid.txt) ---
    warnings: list[str] = []
    original_deid_path = session.folder / "deid.txt"
    if original_deid_path.exists():
        original_deid = original_deid_path.read_text(encoding="utf-8")
        warnings.extend(_coverage_check(original_deid, draft_text))
    else:
        warnings.append("Original deid.txt missing from session — skipping coverage check")
    warnings.extend(_merge_check(draft_text))

    # --- Reverse pseudonyms ---
    restored, unknown = _apply_reverse_mapping(draft_text, session.mapping)
    for tok in unknown:
        warnings.append(f"Unknown pseudonym {tok} — not in mapping, left literal")

    # --- Reverse date shift ---
    restored_text, _, date_warnings = date_shift.reverse_shift(restored, session.date_offset)
    warnings.extend(date_warnings)

    # --- Write outputs ---
    if args.output:
        final_path = Path(args.output).expanduser()
    else:
        final_path = session.folder / f"final_{draft_path.stem}.PHI_DO_NOT_READ.txt"
    final_path.write_text(restored_text, encoding="utf-8")
    try:
        os.chmod(final_path, 0o600)
    except OSError:
        pass

    # Report is SAFE to read — counts + warnings only, no actual content
    report_path = session.folder / "reidentify_report.txt"
    draft_tokens = _scan_tokens(draft_text)
    report_lines = [
        f"phi-deid re-identification report",
        f"Session: {session.alias}",
        f"Draft input: {draft_path}",
        f"Final output: {final_path}",
        f"Date offset reversed: {-session.date_offset} days",
        f"Pseudonym tokens in draft: {len(draft_tokens)}",
        f"Unknown tokens: {len(unknown)}",
        f"Warnings: {len(warnings)}",
        "",
        "--- Warnings ---",
    ]
    report_lines.extend(warnings if warnings else ["(none)"])
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    summary = {
        "session": session.alias,
        "final_output": str(final_path),
        "report": str(report_path),
        "unknown_tokens": unknown,
        "warnings": warnings,
        "draft_token_count": len(draft_tokens),
    }
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 2 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
