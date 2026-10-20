"""helpers — extras that rcParams alone can't express (panel labels, layout)."""

from __future__ import annotations

from .theme_loader import load_spec


def add_panel_labels(fig, journal: str, *, x: float = 0.02, y: float = 0.98) -> None:
    """Add per-axis panel labels (a/b/c or A/B/C) to a multi-panel figure.

    Args:
        fig: matplotlib Figure with multiple axes.
        journal: short name; reads typography.panel_label.{format,case,style}.
        x, y: axis-fraction position of the label (default top-left of each axes).
    """
    spec = load_spec(journal)
    pl = spec["typography"]["panel_label"]
    case = pl.get("case", "lower")
    style = pl.get("style", "bold")
    fontsize = spec["typography"]["sizes_pt"].get("panel_label", 8)

    base = "abcdefghijklmnop"
    letters = list(base.upper() if case == "upper" else base)

    fontweight = "bold" if style == "bold" else "normal"

    for idx, ax in enumerate(fig.axes):
        if idx >= len(letters):
            break
        ax.text(
            x, y, letters[idx],
            transform=ax.transAxes,
            fontsize=fontsize,
            fontweight=fontweight,
            va="top",
            ha="left",
        )


def multi_panel_layout(
    rows: int,
    cols: int,
    journal: str,
    *,
    column: str = "double",
):
    """Convenience helper: returns a (fig, axes_array) sized to the journal's
    column width and the grid shape.

    Uses constrained_layout so ticks/labels don't collide.
    """
    import matplotlib.pyplot as plt

    from .matplotlib_applier import figure_size

    base_w, base_h = figure_size(journal, column)
    fig, axes = plt.subplots(
        rows, cols,
        figsize=(base_w, base_h * rows / cols if rows >= cols else base_h),
        constrained_layout=True,
    )
    return fig, axes
