"""Root conftest.py — ensures backend/ is importable in all tests."""

import sys
from pathlib import Path

# Add backend/ to sys.path so `from partition.*` and `from api.*` imports work
_BACKEND_ROOT = Path(__file__).parent.resolve()
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
