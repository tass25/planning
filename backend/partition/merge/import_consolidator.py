"""ImportConsolidator — Merge Layer (L4)

Collects imports_detected from all ConversionResult objects for a file,
deduplicates, orders per PEP 8, and maps to canonical import statements.
"""

from __future__ import annotations

from collections import defaultdict

# Canonical import alias map
CANONICAL_ALIASES: dict[str, str] = {
    "pandas": "import pandas as pd",
    "numpy": "import numpy as np",
    "statsmodels": "import statsmodels.api as sm",
    "statsmodels.api": "import statsmodels.api as sm",
    "matplotlib": "import matplotlib.pyplot as plt",
    "matplotlib.pyplot": "import matplotlib.pyplot as plt",
    "scipy": "import scipy",
    "scipy.stats": "from scipy import stats",
}

# Known stdlib modules (subset used by generated code)
STDLIB_MODULES = {
    "os", "sys", "re", "json", "csv", "datetime", "pathlib",
    "collections", "itertools", "functools", "math", "uuid",
    "typing", "dataclasses", "enum", "logging", "warnings",
    "hashlib", "copy", "io", "textwrap", "contextlib",
}

SECTION_ORDER = ["stdlib", "third_party", "local"]


def _classify_import(module_name: str) -> str:
    """Classify a module as stdlib, third_party, or local."""
    root = module_name.split(".")[0]
    if root in STDLIB_MODULES:
        return "stdlib"
    if root.startswith("partition"):
        return "local"
    return "third_party"


def _to_import_statement(module_name: str) -> str:
    """Convert a module name to a canonical import statement."""
    if module_name in CANONICAL_ALIASES:
        return CANONICAL_ALIASES[module_name]
    root = module_name.split(".")[0]
    if root in CANONICAL_ALIASES:
        return CANONICAL_ALIASES[root]
    return f"import {module_name}"


def consolidate_imports(all_imports: list[list[str]]) -> str:
    """Consolidate imports from multiple ConversionResult.imports_detected lists.

    Returns formatted import block with PEP 8 ordering:
    stdlib → third-party → local, separated by blank lines.
    """
    seen_statements: set[str] = set()
    sections: dict[str, list[str]] = defaultdict(list)

    for imports_list in all_imports:
        for module_name in imports_list:
            stmt = _to_import_statement(module_name)
            if stmt not in seen_statements:
                seen_statements.add(stmt)
                section = _classify_import(module_name)
                sections[section].append(stmt)

    for section in sections:
        sections[section].sort()

    blocks = []
    for section_key in SECTION_ORDER:
        if sections[section_key]:
            blocks.append("\n".join(sections[section_key]))

    return "\n\n".join(blocks)
