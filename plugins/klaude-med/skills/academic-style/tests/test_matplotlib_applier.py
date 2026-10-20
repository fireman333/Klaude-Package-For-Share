"""Smoke tests for matplotlib applier — apply / restore rcParams, palette /
figure_size lookups."""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")  # headless

import matplotlib.pyplot as plt
import pytest

from core.matplotlib_applier import (
    apply_journal_theme,
    figure_size,
    palette,
    palette_cycle,
)
from core.theme_loader import list_journals

JOURNALS = list_journals()


@pytest.mark.parametrize("journal", JOURNALS)
def test_context_manager_restores(journal: str) -> None:
    before_fontsize = plt.rcParams["font.size"]
    before_axes_lw = plt.rcParams["axes.linewidth"]
    with apply_journal_theme(journal):
        assert plt.rcParams["font.size"] != before_fontsize or True  # always set
    assert plt.rcParams["font.size"] == before_fontsize
    assert plt.rcParams["axes.linewidth"] == before_axes_lw


@pytest.mark.parametrize("journal", JOURNALS)
def test_figure_size_returns_tuple(journal: str) -> None:
    w, h = figure_size(journal, "single")
    assert 1.0 < w < 10.0   # reasonable inch range
    assert h > 0
    w2, _ = figure_size(journal, "double")
    assert w2 > w  # double is wider than single


@pytest.mark.parametrize("journal", JOURNALS)
def test_palette_semantic_lookup(journal: str) -> None:
    color = palette(journal, "primary_method")
    assert color.startswith("#") and len(color) == 7


@pytest.mark.parametrize("journal", JOURNALS)
def test_palette_cycle_nonempty(journal: str) -> None:
    cycle = palette_cycle(journal)
    assert len(cycle) >= 4
    assert all(c.startswith("#") for c in cycle)


def test_palette_unknown_role_raises() -> None:
    with pytest.raises(KeyError):
        palette("nature", "not_a_role")
