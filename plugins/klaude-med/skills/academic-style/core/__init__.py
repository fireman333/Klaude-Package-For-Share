"""academic_style.core — internal modules."""

from .theme_loader import load_spec, list_journals
from .matplotlib_applier import (
    apply_journal_theme,
    figure_size,
    palette,
)
from .caption_formatter import format_caption
from .font_resolver import find_first_available

__all__ = [
    "load_spec",
    "list_journals",
    "apply_journal_theme",
    "figure_size",
    "palette",
    "format_caption",
    "find_first_available",
]
