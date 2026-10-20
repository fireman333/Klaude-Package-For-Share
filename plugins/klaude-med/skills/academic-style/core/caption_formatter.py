"""caption_formatter — render figure / table captions per the journal spec."""

from __future__ import annotations

from .theme_loader import load_spec


def format_caption(
    journal: str,
    *,
    n: int,
    title: str,
    body: str,
    panel_descriptions: str = "",
) -> str:
    """Render a figure caption using the journal's caption.template.

    Args:
        journal: short name.
        n: figure number.
        title: short title (no trailing punctuation).
        body: one-to-two-sentence description of the figure.
        panel_descriptions: pre-joined panel-by-panel descriptions
            (e.g. ``"a, ... b, ... c, ..."``).

    Returns:
        The fully rendered caption string.
    """
    spec = load_spec(journal)
    caption = spec["caption"]
    template = caption["template"]
    bold_title = caption.get("bold_title", False)

    rendered_title = f"**{title}**" if bold_title else title

    return template.format(
        n=n,
        bold_title=rendered_title,
        title=title,
        body=body,
        panel_descriptions=panel_descriptions,
    )


def format_p_value(journal: str, p: float) -> str:
    """Format a p-value per the journal's table_style.p_value_format."""
    spec = load_spec(journal)
    style = spec["table_style"]
    threshold_str = style["p_value_format"]
    decimal_places = style["decimal_places"]["p_value"]
    decimal_separator = style.get("decimal_separator", "period")

    # Parse threshold (e.g. "<0.001", "<.001", "<0·0001")
    sep = "·" if decimal_separator == "middle_dot" else "."
    no_lz = threshold_str.startswith("<.")  # JAMA style
    threshold_value = _parse_threshold(threshold_str)

    if p < threshold_value:
        return threshold_str

    formatted = f"{p:.{decimal_places}f}"
    if no_lz and formatted.startswith("0."):
        formatted = formatted[1:]
    if decimal_separator == "middle_dot":
        formatted = formatted.replace(".", "·")
    return formatted


def _parse_threshold(s: str) -> float:
    """Parse a threshold string like '<0.001' / '<.001' / '<0·0001' to a float."""
    body = s.lstrip("<").lstrip("=").strip()
    body = body.replace("·", ".")
    if body.startswith("."):
        body = "0" + body
    return float(body)


def format_decimal(journal: str, value: float, places: int | str) -> str:
    """Format a numeric value with the journal's decimal separator.

    ``places`` may be an int or a key from ``table_style.decimal_places``
    (e.g. ``"percent"``, ``"hr"``, ``"ci"``).
    """
    spec = load_spec(journal)
    style = spec["table_style"]
    if isinstance(places, str):
        places = style["decimal_places"][places]

    formatted = f"{value:.{places}f}"
    if style.get("decimal_separator") == "middle_dot":
        formatted = formatted.replace(".", "·")
    return formatted
