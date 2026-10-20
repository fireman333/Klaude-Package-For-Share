#!/usr/bin/env python3
"""
phi-deid main entry — de-identify a Taiwan medical note.

Usage:
    python deid.py --input raw_note.txt --patient-key bed12_APR

Output:
    JSON summary to stdout (Claude Code reads this — no PHI appears here).
    Files written to ~/phi-deid-sessions/<stamp>_<patient-key>/:
        raw.PHI_DO_NOT_READ.txt  (chmod 600, contains PHI)
        deid.txt                 (SAFE to read — all PHI redacted)
        mapping.json             (chmod 600, contains pseudonym -> real map)
        date_offset.txt          (chmod 600, contains signed integer days)

The stdout JSON schema:
    {
      "session": "<alias>",
      "session_folder": "<path>",
      "deid_output": "<path to deid.txt>",
      "counts": {"PATIENT_NAME": 2, "MRN": 1, ...},
      "date_shifts": <int>,
      "warnings": [<str>, ...]
    }
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Allow `from patterns import ...` when invoked as a script from any CWD
sys.path.insert(0, str(Path(__file__).resolve().parent))

import date_shift
import mapping
import patterns
from patterns import Detection


def _apply_redactions(text: str, detections: list[Detection], session: mapping.Session) -> str:
    """Replace each detection in `text` with its pseudonym token.

    Walks detections in reverse position order to keep offsets valid during
    substitution.
    """
    detections_sorted = sorted(detections, key=lambda d: d.start, reverse=True)
    result = text
    for d in detections_sorted:
        token = session.token_for(d.category, d.text)
        result = result[: d.start] + token + result[d.end :]
    return result


def _run_detectors(
    text: str,
    use_ckip: bool,
    warnings: list[str],
) -> list[Detection]:
    """Run all detectors and return merged (non-overlapping) detections."""
    detections: list[Detection] = []
    detections.extend(patterns.find_regex_phi(text))
    detections.extend(patterns.find_name_candidates(text))
    detections.extend(patterns.find_hospitals(text))

    if use_ckip:
        try:
            import ner_ckip
            if ner_ckip.is_installed():
                ckip_dets = ner_ckip.detect(text)
                detections.extend(ckip_dets)
            else:
                warnings.append(
                    "CKIP not installed — name detection may miss cases. "
                    "Install with: python scripts/ner_ckip.py --install"
                )
        except Exception as e:
            warnings.append(f"CKIP failed: {e} — falling back to rule-based only")

    return patterns.merge_detections(detections)


def _validate_leak(deid_text: str) -> list[Detection]:
    """Re-run all regex detectors against the de-identified text.

    Any hit (excluding pseudonym tokens themselves) indicates a leak.
    Pseudonym tokens look like `[<PREFIX>_<NN>]` — exclude those.
    """
    # Strip tokens from text so we don't re-detect them
    import regex as re
    stripped = re.sub(r"\[[A-Z_]+_\d+\]", "", deid_text)
    return patterns.find_regex_phi(stripped)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="De-identify a Taiwan medical record. Output: JSON summary to stdout."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to raw note file (will be copied to session folder with chmod 600)",
    )
    parser.add_argument(
        "--patient-key",
        required=True,
        help="User-chosen alias for this patient (no spaces, no path separators, no real name)",
    )
    parser.add_argument(
        "--no-ckip",
        action="store_true",
        help="Skip CKIP NER (use rule-based only)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="After redaction, re-scan deid output for leaks. Report any hits in warnings.",
    )
    parser.add_argument(
        "--reuse-session",
        action="store_true",
        help="If the patient-key alias already exists in registry, reuse its session instead of erroring.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Override session root (default: ~/phi-deid-sessions)",
    )
    args = parser.parse_args()

    root = Path(args.root) if args.root else mapping.DEFAULT_ROOT

    # --- Load or create session ---
    reg = mapping.load_registry(root)
    if args.patient_key in reg:
        if not args.reuse_session:
            # Claude should default to --reuse-session when the user has already
            # worked on this patient. But we error loudly by default so we don't
            # silently pollute an existing session.
            print(
                json.dumps(
                    {
                        "error": f"Session {args.patient_key!r} already exists. "
                        "Use --reuse-session to append to it, or pick a different --patient-key.",
                    }
                )
            )
            return 1
        session = mapping.Session.load(args.patient_key, root=root)
    else:
        session = mapping.Session.new(args.patient_key, root=root)

    # --- Read raw input ---
    raw_path = Path(args.input).expanduser()
    if not raw_path.exists():
        print(json.dumps({"error": f"input file not found: {raw_path}"}))
        return 1
    raw_text = raw_path.read_text(encoding="utf-8")

    # Copy raw to session folder with chmod 600 (for audit; NEVER read by Claude)
    raw_in_session = session.folder / "raw.PHI_DO_NOT_READ.txt"
    shutil.copyfile(raw_path, raw_in_session)
    os.chmod(raw_in_session, 0o600)

    warnings: list[str] = []

    # --- Date shift on raw text (preserves original char variants) ---
    raw_shifted, shifts, shift_warnings = date_shift.apply_shift(raw_text, session.date_offset)
    warnings.extend(shift_warnings)

    # --- Detect PHI on a normalized copy (offsets align: normalize preserves length) ---
    normalized_shifted = patterns.normalize(raw_shifted)
    detections = _run_detectors(normalized_shifted, use_ckip=not args.no_ckip, warnings=warnings)

    # Rewrite each Detection's .text using the RAW (un-normalized) slice so the
    # mapping stores what the user actually wrote (e.g. 臺, not 台). Offsets are
    # unchanged since normalize() is 1-to-1 per char.
    detections = [
        patterns.Detection(
            category=d.category,
            text=raw_shifted[d.start:d.end],
            start=d.start,
            end=d.end,
            role_hint=d.role_hint,
        )
        for d in detections
    ]

    # --- Redact the raw-shifted text ---
    deid_text = _apply_redactions(raw_shifted, detections, session)

    # --- Write outputs ---
    deid_path = session.folder / "deid.txt"
    deid_path.write_text(deid_text, encoding="utf-8")

    session.save()

    # --- Validate (optional) ---
    leaks: list[Detection] = []
    if args.validate:
        leaks = _validate_leak(deid_text)
        for leak in leaks:
            warnings.append(
                f"Potential leak: {leak.category} at offset {leak.start} ({leak.text!r})"
            )

    # --- Summarize ---
    counts: dict[str, int] = {}
    for d in detections:
        counts[d.category] = counts.get(d.category, 0) + 1

    summary = {
        "session": session.alias,
        "session_folder": str(session.folder),
        "deid_output": str(deid_path),
        "counts": counts,
        "date_shifts": len(shifts),
        "date_offset_days": session.date_offset,
        "warnings": warnings,
        "leak_count": len(leaks),
    }
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if not leaks else 2  # exit 2 if --validate found leaks


if __name__ == "__main__":
    sys.exit(main())
