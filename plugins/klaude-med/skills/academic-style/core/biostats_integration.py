"""biostats_integration — one-call helper for biostats skills (Wave 1-2).

Each biostats skill adds a small block to its ``main()`` to enable
``--style=<journal>``. The block (~5 lines) auto-detects this skill folder,
calls :func:`apply_style_from_argv`, and applies the matplotlib rcParams
patch globally before any plotting code runs.

Behavior contract:
- If ``--style`` is absent from argv, returns ``None`` and does nothing.
  The skill's existing behavior is unchanged (byte-identical output).
- If ``--style`` is present, the flag (and its value) is **consumed and
  removed** from argv so the skill's own argparse / sys.argv handling
  doesn't see an unknown flag.
- Failures (unknown journal, missing yaml, etc.) emit a warning and
  return ``None``; the skill continues with default styling.
"""

from __future__ import annotations

import sys
import warnings
from typing import Optional


def apply_style_from_argv(argv: list[str] | None = None) -> Optional[str]:
    """Extract and apply ``--style=<journal>`` from argv.

    Args:
        argv: argument list to mutate (typically ``sys.argv``).
            If ``None``, defaults to ``sys.argv``.

    Returns:
        The journal short name on success, or ``None`` if no ``--style``
        flag was present or application failed.
    """
    if argv is None:
        argv = sys.argv

    style = _consume_style_flag(argv)
    if not style:
        return None

    try:
        import matplotlib.pyplot as plt
        from .matplotlib_applier import _spec_to_rcparams
        from .theme_loader import load_spec
        spec = load_spec(style)
        plt.rcParams.update(_spec_to_rcparams(spec))
    except Exception as e:
        warnings.warn(
            f"academic-style: --style={style} failed to apply ({e}); "
            f"continuing with default style.",
            stacklevel=2,
        )
        return None
    return style


def _consume_style_flag(argv: list[str]) -> Optional[str]:
    """Remove ``--style[=<journal>]`` from argv in place; return journal name."""
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg.startswith("--style="):
            value = arg.split("=", 1)[1]
            argv.pop(i)
            return value
        if arg == "--style":
            if i + 1 < len(argv):
                value = argv[i + 1]
                argv.pop(i)  # remove flag
                argv.pop(i)  # remove value (now at same position)
                return value
            argv.pop(i)
            return None
        i += 1
    return None


def palette_for(journal: str | None, semantic_role_or_name: str, default: str) -> str:
    """Return a palette hex if a journal is active, else fall back to ``default``.

    Convenience for biostats scripts that want a one-line color override::

        color = palette_for(_AS_STYLE, "primary_method", "#1F77B4")
    """
    if journal is None:
        return default
    try:
        from .matplotlib_applier import palette
        return palette(journal, semantic_role_or_name)
    except Exception:
        return default
