"""Tests for caption_formatter — caption rendering + p-value formatting per
journal style."""

from __future__ import annotations

import pytest

from core.caption_formatter import format_caption, format_decimal, format_p_value
from core.theme_loader import list_journals

JOURNALS = list_journals()


@pytest.mark.parametrize("journal", JOURNALS)
def test_caption_renders(journal: str) -> None:
    out = format_caption(
        journal,
        n=1,
        title="Survival outcomes",
        body="Kaplan-Meier curves comparing two arms",
        panel_descriptions="A, overall. B, by subgroup.",
    )
    assert "1" in out
    assert "Survival outcomes" in out


def test_p_value_jama_no_leading_zero() -> None:
    # JAMA: <.001 with no leading zero
    assert format_p_value("jama", 0.0001) == "<.001"
    formatted = format_p_value("jama", 0.045)
    assert formatted.startswith(".")  # no leading zero


def test_p_value_lancet_middle_dot() -> None:
    assert "·" in format_p_value("lancet", 0.00001)
    formatted = format_p_value("lancet", 0.0234)
    assert "·" in formatted and "." not in formatted


def test_p_value_nejm_period() -> None:
    formatted = format_p_value("nejm", 0.045)
    assert formatted.startswith("0.") and "·" not in formatted


def test_decimal_lancet_uses_middle_dot() -> None:
    out = format_decimal("lancet", 12.5, "percent")
    assert "·" in out


def test_decimal_jama_uses_period() -> None:
    out = format_decimal("jama", 12.5, "percent")
    assert "." in out and "·" not in out
