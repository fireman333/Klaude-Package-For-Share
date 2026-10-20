"""font_resolver — walk the font_stack and return the first font available locally."""

from __future__ import annotations

import warnings
from functools import lru_cache


@lru_cache(maxsize=1)
def _system_font_names() -> set[str]:
    """Return the set of font family names matplotlib can find on this system."""
    try:
        from matplotlib import font_manager
    except ImportError:
        return set()
    return {f.name for f in font_manager.fontManager.ttflist}


def find_first_available(font_stack: list[str]) -> str:
    """Walk font_stack, return the first one matplotlib can find.

    Always falls back to ``DejaVu Sans`` (matplotlib's own bundled font) and
    emits a warning if no preferred font in the stack is installed.
    """
    available = _system_font_names()
    for name in font_stack:
        if name in available:
            return name
    fallback = "DejaVu Sans"
    warnings.warn(
        f"None of {font_stack} are installed on this system; "
        f"falling back to {fallback!r}. "
        "Install Helvetica/Arial for full journal compliance.",
        stacklevel=2,
    )
    return fallback
