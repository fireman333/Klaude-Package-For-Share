"""Smoke tests: every shipped journal's spec.yaml loads, palette resolves, all
required keys present."""

from __future__ import annotations

import pytest

from core.theme_loader import SpecError, list_journals, load_spec

JOURNALS = list_journals()


@pytest.mark.parametrize("journal", JOURNALS)
def test_spec_loads(journal: str) -> None:
    spec = load_spec(journal)
    assert spec["journal"]["short"] == journal
    assert "name" in spec["journal"]
    assert "spec_version" in spec["journal"]


@pytest.mark.parametrize("journal", JOURNALS)
def test_palette_resolves(journal: str) -> None:
    spec = load_spec(journal)
    palette = spec["palette"]
    assert isinstance(palette, dict) and len(palette) >= 5
    for name, hex_code in palette.items():
        assert isinstance(hex_code, str)
        assert hex_code.startswith("#")
        assert len(hex_code) == 7  # #RRGGBB


@pytest.mark.parametrize("journal", JOURNALS)
def test_semantic_mapping_valid(journal: str) -> None:
    spec = load_spec(journal)
    sem = spec["semantic_mapping"]
    palette = spec["palette"]
    for role, name in sem.items():
        assert name in palette, f"{journal}: semantic role {role} → {name} not in palette"


@pytest.mark.parametrize("journal", JOURNALS)
def test_required_sections_present(journal: str) -> None:
    spec = load_spec(journal)
    for key in (
        "typography", "dimensions", "lines", "submission",
        "caption", "ax_style", "table_style",
    ):
        assert key in spec, f"{journal}: missing top-level section {key}"


def test_unknown_journal_raises() -> None:
    with pytest.raises(SpecError):
        load_spec("not_a_real_journal")


def test_list_journals_includes_all_four() -> None:
    js = set(list_journals())
    assert {"nature", "jama", "nejm", "lancet"}.issubset(js)
