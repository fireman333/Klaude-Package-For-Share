"""post_processor — re-render an existing figure under a journal theme.

Strategy:
  (1) If a sibling Python script (`*.py`) is found, prefer re-running with --style.
  (2) Otherwise, do a best-effort PIL re-color (limited scope) and warn.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Optional


def find_sibling_script(figure_path: Path) -> Optional[Path]:
    """Look for a Python script in the same folder or one level up."""
    folder = figure_path.parent
    candidates = sorted(folder.glob("*.py")) + sorted(folder.parent.glob("scripts/*.py"))
    return candidates[0] if candidates else None


def rewrite_figure(figure_path: str | Path, journal: str) -> Path:
    """Re-render a figure under the given journal theme.

    Returns the output path; emits a warning if the rewrite is best-effort only.
    """
    figure_path = Path(figure_path).resolve()
    if not figure_path.is_file():
        raise FileNotFoundError(figure_path)

    out = figure_path.with_name(f"{figure_path.stem}_{journal}{figure_path.suffix}")

    sibling = find_sibling_script(figure_path)
    if sibling:
        warnings.warn(
            f"Found sibling script {sibling}. For full-quality restyling, re-run that "
            f"script with `--style={journal}`. The PIL post-processor only adjusts "
            f"the existing raster.",
            stacklevel=2,
        )

    # Best-effort raster path: just copy and let the caller know post-processor is limited.
    try:
        from PIL import Image
    except ImportError as e:
        raise RuntimeError("PIL/Pillow required for post-processor") from e

    img = Image.open(figure_path)
    img.save(out)
    warnings.warn(
        "post_processor.rewrite_figure currently only copies the raster. "
        "For real palette swap, prefer re-running the source script with --style.",
        stacklevel=2,
    )
    return out
