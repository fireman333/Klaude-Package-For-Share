"""academic-style — journal-specific figure & table styling for biostats outputs.

This file provides the public API when installed via ``pip install -e .``
(see pyproject.toml). It silently no-ops if loaded as a non-package module
(e.g. by pytest collection from the script-mode folder layout).
"""

__version__ = "0.1.0"

try:
    from .core.theme_loader import load_spec, list_journals
    from .core.matplotlib_applier import (
        apply_journal_theme,
        figure_size,
        palette,
    )
    __all__ = [
        "load_spec",
        "list_journals",
        "apply_journal_theme",
        "figure_size",
        "palette",
        "__version__",
    ]
except ImportError:
    # Loaded as a non-package module (script mode without pip install).
    # The CLI scripts and biostats integrations import directly from `core`
    # via sys.path manipulation; the public-API names above are only
    # available after `pip install -e .`.
    __all__ = ["__version__"]
