"""Root conftest.py — ensures sas_converter/ is importable in all tests."""

import sys
from pathlib import Path

# Add sas_converter/ to sys.path so `from partition.*` imports work everywhere
_REPO_ROOT = Path(__file__).parent.resolve()
_PKG_DIR = _REPO_ROOT / "sas_converter"
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))
