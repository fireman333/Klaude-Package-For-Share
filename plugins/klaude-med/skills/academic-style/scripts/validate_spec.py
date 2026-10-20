#!/usr/bin/env python3
"""validate_spec.py — verify a journal's plugin folder is complete & well-formed.

Usage:
    python validate_spec.py journals/nature/
    python validate_spec.py journals/<new>/    # for new-journal PRs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REQUIRED_FILES = ["spec.yaml", "palette.json", "prompt.md", "references.md"]
REQUIRED_SPEC_TOP_KEYS = [
    "journal", "typography", "dimensions", "lines", "palette",
    "semantic_mapping", "submission", "caption", "ax_style", "table_style",
]
REQUIRED_JOURNAL_KEYS = ["name", "short", "spec_version", "sources"]


def validate(folder: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []

    if not folder.is_dir():
        return False, [f"Not a directory: {folder}"]

    for fname in REQUIRED_FILES:
        if not (folder / fname).is_file():
            errors.append(f"Missing required file: {fname}")

    if errors:
        return False, errors

    try:
        spec = yaml.safe_load((folder / "spec.yaml").read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return False, [f"spec.yaml: malformed YAML — {e}"]

    for key in REQUIRED_SPEC_TOP_KEYS:
        if key not in spec:
            errors.append(f"spec.yaml missing top-level key: {key}")

    journal = spec.get("journal", {})
    for key in REQUIRED_JOURNAL_KEYS:
        if key not in journal:
            errors.append(f"spec.yaml: journal.{key} missing")

    sources = journal.get("sources", {})
    if "author_guideline" not in sources:
        errors.append("spec.yaml: journal.sources.author_guideline required")

    sample_dois = sources.get("sample_dois", [])
    if not isinstance(sample_dois, list) or len(sample_dois) < 2:
        errors.append("spec.yaml: journal.sources.sample_dois must list ≥ 2 DOIs")

    try:
        palette = json.loads((folder / "palette.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, errors + [f"palette.json: malformed JSON — {e}"]

    palette_keys = {k for k in palette if not k.startswith("_")}
    sem = spec.get("semantic_mapping", {})
    for role, name in sem.items():
        if name not in palette_keys:
            errors.append(f"semantic_mapping.{role} = {name!r} not found in palette.json")

    refs = (folder / "references.md").read_text(encoding="utf-8")
    if "http" not in refs:
        errors.append("references.md: no URL found (need ≥ 1 author guideline URL)")
    if refs.count("DOI") < 1 and refs.count("doi") < 1:
        errors.append("references.md: should mention DOI(s) for sample papers")

    prompt_text = (folder / "prompt.md").read_text(encoding="utf-8").strip()
    if len(prompt_text) < 50:
        errors.append("prompt.md: too short (<50 chars). Provide caption + abstract + cover-letter voice.")

    return (len(errors) == 0), errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a journals/<name>/ folder.")
    parser.add_argument("folder", help="Path to a journal plugin folder")
    args = parser.parse_args(argv)

    folder = Path(args.folder).resolve()
    ok, errors = validate(folder)

    if ok:
        print(f"OK  {folder}")
        return 0
    print(f"FAIL  {folder}")
    for e in errors:
        print(f"  - {e}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
