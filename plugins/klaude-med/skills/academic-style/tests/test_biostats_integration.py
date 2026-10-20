"""Tests: --style flag is consumed correctly, byte-identity preserved when absent."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from core.biostats_integration import _consume_style_flag, apply_style_from_argv, palette_for


def test_consume_equals_form() -> None:
    argv = ["script.py", "config.json", "--style=nature", "--other"]
    out = _consume_style_flag(argv)
    assert out == "nature"
    assert argv == ["script.py", "config.json", "--other"]


def test_consume_space_form() -> None:
    argv = ["script.py", "--style", "jama", "config.json"]
    out = _consume_style_flag(argv)
    assert out == "jama"
    assert argv == ["script.py", "config.json"]


def test_consume_absent_returns_none() -> None:
    argv = ["script.py", "config.json"]
    assert _consume_style_flag(argv) is None
    assert argv == ["script.py", "config.json"]


def test_apply_unknown_journal_returns_none() -> None:
    argv = ["script.py", "--style=not_a_journal"]
    out = apply_style_from_argv(argv)
    assert out is None


def test_apply_nature_modifies_rcparams() -> None:
    before = plt.rcParams["axes.linewidth"]
    argv = ["script.py", "--style=nature"]
    out = apply_style_from_argv(argv)
    assert out == "nature"
    # Nature has axes.linewidth = 0.5
    assert plt.rcParams["axes.linewidth"] == 0.5
    # Restore
    plt.rcParams["axes.linewidth"] = before


def test_palette_for_with_journal() -> None:
    color = palette_for("nature", "primary_method", "#999999")
    assert color.startswith("#")
    assert color != "#999999"


def test_palette_for_without_journal() -> None:
    assert palette_for(None, "primary_method", "#1F77B4") == "#1F77B4"
