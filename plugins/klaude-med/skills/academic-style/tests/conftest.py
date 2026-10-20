"""conftest — make `core/` importable from tests without pip install."""

import sys
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent.parent  # academic-style/
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))
