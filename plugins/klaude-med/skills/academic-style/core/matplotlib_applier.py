"""matplotlib_applier — turn a journal spec into matplotlib rcParams.

Public API:
    apply_journal_theme(journal, *, column="single", figsize=None) -> ContextManager
    figure_size(journal, column="single") -> tuple[float, float]   # inches
    palette(journal, semantic_role) -> str                          # hex
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from .font_resolver import find_first_available
from .theme_loader import load_spec

MM_PER_INCH = 25.4


def _spec_to_rcparams(spec: dict[str, Any]) -> dict[str, Any]:
    """Translate a journal spec dict into a matplotlib rcParams patch."""
    typography = spec["typography"]
    lines = spec["lines"]
    ax = spec["ax_style"]
    submission = spec["submission"]

    font_family = find_first_available(list(typography["font_stack"]))
    sizes = typography["sizes_pt"]

    spines_visible = set(ax.get("spines_visible", []))

    rc: dict[str, Any] = {
        "font.family": font_family,
        "font.size": typography["base_size_pt"],
        "axes.titlesize": sizes["title"],
        "axes.labelsize": sizes["axis_label"],
        "xtick.labelsize": sizes["tick"],
        "ytick.labelsize": sizes["tick"],
        "legend.fontsize": sizes["legend"],
        "axes.linewidth": lines["axis_linewidth"],
        "lines.linewidth": lines["data_linewidth"],
        "xtick.major.size": lines["tick_length"],
        "ytick.major.size": lines["tick_length"],
        "xtick.direction": lines["tick_direction"],
        "ytick.direction": lines["tick_direction"],
        "axes.spines.top": "top" in spines_visible,
        "axes.spines.right": "right" in spines_visible,
        "axes.spines.bottom": "bottom" in spines_visible,
        "axes.spines.left": "left" in spines_visible,
        "axes.grid": ax.get("grid", False),
        "legend.frameon": ax.get("legend_frame", False),
        "savefig.dpi": spec["dimensions"]["dpi_raster"],
        "figure.dpi": spec["dimensions"]["dpi_preview"],
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": submission.get("svg_fonttype", "none"),
    }
    return rc


@contextmanager
def apply_journal_theme(
    journal: str,
    *,
    column: str = "single",
    figsize: tuple[float, float] | None = None,
) -> Iterator[dict[str, Any]]:
    """Context manager that patches matplotlib rcParams for the given journal.

    Usage::

        with apply_journal_theme("nature", column="single"):
            fig, ax = plt.subplots(figsize=figure_size("nature"))
            ...

    Yields the resolved spec dict so callers can read additional fields
    (palette, caption template, table_style) inside the ``with`` block.
    """
    import matplotlib.pyplot as plt

    spec = load_spec(journal)
    rc_patch = _spec_to_rcparams(spec)

    if figsize is not None:
        rc_patch["figure.figsize"] = figsize
    else:
        rc_patch["figure.figsize"] = figure_size(journal, column)

    original = {k: plt.rcParams[k] for k in rc_patch}
    plt.rcParams.update(rc_patch)
    try:
        yield spec
    finally:
        plt.rcParams.update(original)


def figure_size(journal: str, column: str = "single") -> tuple[float, float]:
    """Return ``(width_inches, height_inches)`` for the journal's named column.

    ``column`` accepts ``single`` / ``double`` / ``full``; height defaults
    to ~62% of width (golden-ish), capped by ``max_height``.
    """
    spec = load_spec(journal)
    dim = spec["dimensions"]
    key_map = {"single": "single_column", "double": "double_column", "full": "full_width"}
    key = key_map.get(column, column)
    if key not in dim:
        raise ValueError(f"{journal}: unknown column '{column}', expected one of {list(key_map)}")
    box = dim[key]
    width_mm = box["width"]
    max_h_mm = box.get("max_height", width_mm)
    height_mm = min(width_mm * 0.62, max_h_mm)
    return (width_mm / MM_PER_INCH, height_mm / MM_PER_INCH)


def palette(journal: str, semantic_role_or_name: str) -> str:
    """Return a hex color for a semantic role (e.g. ``primary_method``) or
    a direct palette name (e.g. ``blue_main``).
    """
    spec = load_spec(journal)
    sem = spec["semantic_mapping"]
    pal = spec["palette"]
    if semantic_role_or_name in sem:
        return pal[sem[semantic_role_or_name]]
    if semantic_role_or_name in pal:
        return pal[semantic_role_or_name]
    raise KeyError(
        f"{journal}: '{semantic_role_or_name}' is neither a semantic role "
        f"({sorted(sem)}) nor a palette name ({sorted(pal)})"
    )


def palette_cycle(journal: str, n: int | None = None) -> list[str]:
    """Return an ordered list of palette hexes for line/scatter color cycling."""
    spec = load_spec(journal)
    sem = spec["semantic_mapping"]
    pal = spec["palette"]
    order = ["primary_method", "control_or_negative", "positive_outcome",
             "highlight", "neutral_reference"]
    cycle = []
    for role in order:
        if role in sem:
            cycle.append(pal[sem[role]])
    # Pad with remaining palette entries (skipping black/white/gray ramps if already used)
    extras = [v for k, v in pal.items()
              if k not in {"black", "white"} and v not in cycle]
    cycle.extend(extras)
    return cycle if n is None else cycle[:n]
