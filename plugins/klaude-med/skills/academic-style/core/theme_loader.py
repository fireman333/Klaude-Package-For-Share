"""theme_loader — read journals/<name>/spec.yaml + palette.json into a dict."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

JOURNALS_DIR = Path(__file__).resolve().parent.parent / "journals"

REQUIRED_TOP_KEYS = {
    "journal",
    "typography",
    "dimensions",
    "lines",
    "palette",
    "semantic_mapping",
    "submission",
    "caption",
    "ax_style",
    "table_style",
}


class SpecError(ValueError):
    """Raised when a journal spec.yaml is missing required keys or is malformed."""


@lru_cache(maxsize=32)
def load_spec(journal: str) -> dict[str, Any]:
    """Load a journal's spec.yaml and inline its palette.json.

    Args:
        journal: short name, e.g. "nature", "jama", "nejm", "lancet".

    Returns:
        dict with all spec sections + ``palette`` resolved to {name: hex}.

    Raises:
        SpecError: missing folder, missing required keys, or palette ref unresolved.
    """
    journal_dir = JOURNALS_DIR / journal
    if not journal_dir.is_dir():
        raise SpecError(
            f"Unknown journal '{journal}'. "
            f"Available: {sorted(p.name for p in JOURNALS_DIR.iterdir() if p.is_dir())}"
        )

    spec_path = journal_dir / "spec.yaml"
    if not spec_path.is_file():
        raise SpecError(f"{journal}: spec.yaml missing at {spec_path}")

    with spec_path.open("r", encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)

    missing = REQUIRED_TOP_KEYS - set(spec.keys())
    if missing:
        raise SpecError(f"{journal}/spec.yaml missing required keys: {sorted(missing)}")

    # Resolve palette.ref -> palette.json
    palette_section = spec.get("palette", {})
    if isinstance(palette_section, dict) and "ref" in palette_section:
        palette_path = journal_dir / palette_section["ref"]
        if not palette_path.is_file():
            raise SpecError(
                f"{journal}: palette.ref points to {palette_section['ref']} but file not found"
            )
        with palette_path.open("r", encoding="utf-8") as fh:
            palette_data = json.load(fh)
        # Strip _comment-style metadata keys
        spec["palette"] = {k: v for k, v in palette_data.items() if not k.startswith("_")}

    # Validate semantic_mapping references valid palette names
    sem = spec.get("semantic_mapping", {})
    palette_keys = set(spec["palette"].keys())
    bad_refs = {role: name for role, name in sem.items() if name not in palette_keys}
    if bad_refs:
        raise SpecError(
            f"{journal}: semantic_mapping references unknown palette names: {bad_refs}"
        )

    spec["_journal_dir"] = str(journal_dir)
    return spec


def list_journals() -> list[str]:
    """Return sorted list of available journal short names."""
    if not JOURNALS_DIR.is_dir():
        return []
    return sorted(
        p.name
        for p in JOURNALS_DIR.iterdir()
        if p.is_dir() and (p / "spec.yaml").is_file()
    )


def clear_cache() -> None:
    """Clear the LRU cache (useful in tests after editing specs)."""
    load_spec.cache_clear()
