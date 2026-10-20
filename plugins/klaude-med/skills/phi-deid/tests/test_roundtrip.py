#!/usr/bin/env python3
"""
End-to-end round-trip test for phi-deid.

For each sample_*.txt fixture:
    1. Run deid.py (with --validate, --no-ckip)
    2. Verify deid.txt contains no leaks
    3. Run reidentify.py
    4. diff original vs restored — must be byte-identical

Also tests:
    - Clinical tokens preserved (POD#3, q8h, 住院第N天, HH:MM)
    - Cross-note consistency: same patient across admission/progress/discharge
      gets the same pseudonyms and same date offset
    - Coverage check: dropping an anchor from draft triggers a warning

Run:
    python -m tests.test_roundtrip
    # or from skill root:
    python tests/test_roundtrip.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_ROOT / "scripts"
FIXTURES = SKILL_ROOT / "tests"

FIXTURE_NAMES = [
    "sample_admission.txt",
    "sample_progress.txt",
    "sample_discharge.txt",
    "sample_handoff.txt",
]

# Clinical tokens that must never be shifted or corrupted
PROTECTED_TOKENS = [
    "POD#", "POD#0", "POD#1", "POD#2", "POD#3",
    "q8h", "q24h", "q6h", "qd", "bid", "tid",
    "住院第",  # just check the prefix; number might vary
    "NPO",
]


def run_script(args: list[str], tmp_root: Path) -> dict:
    """Run a phi-deid script with --root override, return parsed JSON stdout."""
    cmd = [sys.executable] + args + ["--root", str(tmp_root)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in (0, 2):  # 2 = warnings
        print(f"STDERR: {result.stderr}", file=sys.stderr)
        raise RuntimeError(f"Script failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")
    # stdout might have warnings/info lines before JSON; parse last JSON object
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # Strip leading non-JSON text, try again
        idx = result.stdout.find("{")
        return json.loads(result.stdout[idx:])


def test_single_roundtrip(fixture: str, tmp_root: Path) -> None:
    """Round-trip one fixture: deid -> reidentify -> diff."""
    alias = f"test_{fixture.replace('.txt', '').replace('sample_', '')}"
    src = FIXTURES / fixture

    print(f"\n=== Round-trip: {fixture} (alias={alias}) ===")

    # 1. deid
    summary = run_script(
        [str(SCRIPTS / "deid.py"),
         "--input", str(src),
         "--patient-key", alias,
         "--no-ckip",
         "--validate"],
        tmp_root,
    )
    assert summary["leak_count"] == 0, f"Leak detected: {summary.get('warnings')}"
    deid_path = Path(summary["deid_output"])
    assert deid_path.exists(), f"deid.txt not produced: {deid_path}"
    deid_text = deid_path.read_text(encoding="utf-8")

    # 2. Verify clinical tokens preserved
    src_text = src.read_text(encoding="utf-8")
    for tok in PROTECTED_TOKENS:
        if tok in src_text:
            assert tok in deid_text, f"Clinical token {tok!r} lost in deid output"

    # 3. reidentify
    restore_summary = run_script(
        [str(SCRIPTS / "reidentify.py"),
         "--session", alias,
         "--input", str(deid_path)],
        tmp_root,
    )
    final_path = Path(restore_summary["final_output"])
    assert final_path.exists()
    restored = final_path.read_text(encoding="utf-8")

    # 4. Byte-identical to original
    if restored != src_text:
        # Print first differing line for debugging
        for i, (a, b) in enumerate(zip(src_text.splitlines(), restored.splitlines())):
            if a != b:
                print(f"    FIRST DIFF at line {i+1}:")
                print(f"      original: {a!r}")
                print(f"      restored: {b!r}")
                break
        raise AssertionError(f"Round-trip mismatch for {fixture}")

    # 5. Coverage check: unknowns and warnings should be empty for honest inputs
    assert not restore_summary["unknown_tokens"], (
        f"Unknown tokens in round-trip: {restore_summary['unknown_tokens']}"
    )

    print(f"    OK: {summary['counts']}  offset={summary['date_offset_days']}d  {summary['date_shifts']} dates")


def test_cross_note_consistency(tmp_root: Path) -> None:
    """Admission + progress + discharge for same patient must share pseudonyms."""
    print("\n=== Cross-note consistency test ===")
    alias = "xn_patient_01"

    fixtures = ["sample_admission.txt", "sample_progress.txt", "sample_discharge.txt"]
    offsets: list[int] = []
    patient_tokens: list[str] = []

    for i, fx in enumerate(fixtures):
        extra = ["--reuse-session"] if i > 0 else []
        summary = run_script(
            [str(SCRIPTS / "deid.py"),
             "--input", str(FIXTURES / fx),
             "--patient-key", alias,
             "--no-ckip",
             "--validate"] + extra,
            tmp_root,
        )
        assert summary["leak_count"] == 0, f"Leak in {fx}: {summary['warnings']}"
        offsets.append(summary["date_offset_days"])

        # Read the deid.txt and check that [PATIENT_01] (or whatever the patient token is) appears
        deid = Path(summary["deid_output"]).read_text(encoding="utf-8")
        import regex as re
        tokens = set(re.findall(r"\[PATIENT_\d+\]", deid))
        if tokens:
            patient_tokens.append(sorted(tokens)[0])

    assert len(set(offsets)) == 1, f"Date offset not consistent across notes: {offsets}"
    # Patient token should be the same across notes (they all mention the same patient)
    assert len(set(patient_tokens)) == 1, (
        f"Patient pseudonym drifted across notes: {patient_tokens}"
    )
    print(f"    OK: offset={offsets[0]}d stable; patient={patient_tokens[0]} consistent")


def test_coverage_loss_warning(tmp_root: Path) -> None:
    """If the draft drops a pseudonym anchor, reidentify should warn."""
    print("\n=== Coverage-loss warning test ===")
    alias = "cov_loss_01"

    summary = run_script(
        [str(SCRIPTS / "deid.py"),
         "--input", str(FIXTURES / "sample_admission.txt"),
         "--patient-key", alias,
         "--no-ckip"],
        tmp_root,
    )
    deid_path = Path(summary["deid_output"])
    draft = deid_path.read_text(encoding="utf-8")

    # Find any pseudonym token and remove one occurrence
    import regex as re
    m = re.search(r"\[PATIENT_\d+\]", draft)
    assert m, "No PATIENT token in deid output — fixture broken?"
    token = m.group(0)
    # Replace only the first occurrence with "病人" (Chinese paraphrase)
    paraphrased = draft.replace(token, "病人", 1)

    tampered = deid_path.parent / "tampered_draft.txt"
    tampered.write_text(paraphrased, encoding="utf-8")

    restore_summary = run_script(
        [str(SCRIPTS / "reidentify.py"),
         "--session", alias,
         "--input", str(tampered)],
        tmp_root,
    )

    warnings_blob = " ".join(restore_summary["warnings"])
    assert "Coverage drop" in warnings_blob, (
        f"Expected coverage-drop warning, got: {restore_summary['warnings']}"
    )
    print(f"    OK: coverage drop detected for {token}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="phi_deid_test_") as tmp:
        tmp_root = Path(tmp)
        try:
            for fx in FIXTURE_NAMES:
                test_single_roundtrip(fx, tmp_root)
            test_cross_note_consistency(tmp_root)
            test_coverage_loss_warning(tmp_root)
        except AssertionError as e:
            print(f"\nFAIL: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"\nERROR: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            return 1
    print("\n========== ALL TESTS PASSED ==========")
    return 0


if __name__ == "__main__":
    sys.exit(main())
