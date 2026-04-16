"""Lineage guard — detects internal table reloads in translated code.

A common LLM mistake: the model emits ``pd.read_csv('customers.csv')``
for a DataFrame that was produced by an earlier pipeline chunk and should
be passed in directly (not re-read from disk).

Usage::

    names = {"customers", "transactions", "orders"}
    report = check_lineage(python_code, internal_table_names=names)
    if not report.ok:
        for v in report.violations:
            print(v.table_name, v.line_no, v.snippet)
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LineageViolation:
    table_name: str       # the name that was reloaded
    line_no: int          # 1-based line number in python_code
    snippet: str          # the offending line
    suggestion: str       # how to fix it


@dataclass
class LineageReport:
    ok: bool
    violations: list[LineageViolation] = field(default_factory=list)
    error_message: str = ""

    def to_prompt_block(self) -> str:
        if self.ok:
            return ""
        lines = ["## Lineage Violation — Internal Table Reload\n"]
        lines.append(
            "The following internal DataFrames should NOT be loaded from disk "
            "— they are passed in from a previous pipeline step:\n"
        )
        for v in self.violations:
            lines.append(f"  - Line {v.line_no}: `{v.snippet.strip()}`")
            lines.append(f"    Fix: {v.suggestion}\n")
        return "\n".join(lines)


# ── Heuristic name extractor ──────────────────────────────────────────────────

_READ_PATTERNS = [
    # pd.read_csv('name.csv')  /  pd.read_csv("name.csv")
    re.compile(r"""pd\.read_csv\s*\(\s*['"]([^'"]+)['"]"""),
    # pd.read_excel('name.xlsx')
    re.compile(r"""pd\.read_excel\s*\(\s*['"]([^'"]+)['"]"""),
    # pd.read_parquet('name.parquet')
    re.compile(r"""pd\.read_parquet\s*\(\s*['"]([^'"]+)['"]"""),
    # pd.read_table('name.tsv')
    re.compile(r"""pd\.read_table\s*\(\s*['"]([^'"]+)['"]"""),
    # open('name.csv')
    re.compile(r"""open\s*\(\s*['"]([^'"]+)['"]"""),
]


def _filepath_to_name(filepath: str) -> str:
    """Convert 'path/to/customers.csv' → 'customers'."""
    name = filepath.split("/")[-1].split("\\")[-1]
    for ext in (".csv", ".xlsx", ".xls", ".parquet", ".tsv", ".txt"):
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
    return name.lower().replace("-", "_").replace(" ", "_")


def check_lineage(
    python_code: str,
    internal_table_names: set[str] | None = None,
    *,
    strict: bool = False,
) -> LineageReport:
    """Scan translated Python for illegal disk reads of internal tables.

    Args:
        python_code:          The translated Python script to check.
        internal_table_names: Set of lowercased table names that should NOT
                              be loaded from disk (they come from prior chunks).
                              If ``None``, heuristics auto-detect obvious cases.
        strict:               If True, flag ANY ``pd.read_csv`` call (no whitelist).

    Returns:
        ``LineageReport`` with ``ok=True`` if no violations found.
    """
    if not python_code or not python_code.strip():
        return LineageReport(ok=True)

    internal = {n.lower() for n in (internal_table_names or set())}
    violations: list[LineageViolation] = []

    code_lines = python_code.split("\n")

    for line_no, line in enumerate(code_lines, start=1):
        stripped = line.strip()
        # Skip comments
        if stripped.startswith("#"):
            continue

        for pattern in _READ_PATTERNS:
            for m in pattern.finditer(line):
                filepath = m.group(1)
                table_name = _filepath_to_name(filepath)

                is_internal = (
                    strict
                    or (internal and table_name in internal)
                    or _looks_internal(filepath, table_name)
                )

                if is_internal:
                    violations.append(LineageViolation(
                        table_name=table_name,
                        line_no=line_no,
                        snippet=line,
                        suggestion=(
                            f"Remove this read call. `{table_name}` is an internal "
                            f"DataFrame produced by a prior step — use it directly "
                            f"as a variable named `{table_name}`."
                        ),
                    ))

    if violations:
        table_list = ", ".join(f"`{v.table_name}`" for v in violations)
        return LineageReport(
            ok=False,
            violations=violations,
            error_message=(
                f"Internal table(s) {table_list} are being reloaded from disk. "
                "These DataFrames should be passed in directly from prior pipeline steps."
            ),
        )

    return LineageReport(ok=True)


def _looks_internal(filepath: str, table_name: str) -> bool:
    """Heuristic: looks like an internal SAS dataset name (not a real input file).

    Real external files tend to have explicit paths or non-SAS names.
    Internal tables look like SAS variable names.
    """
    # Has a real path component → probably external
    if "/" in filepath or "\\" in filepath:
        return False
    # Has a non-SAS extension like .db, .json → probably external
    fp_lower = filepath.lower()
    if any(fp_lower.endswith(ext) for ext in (".json", ".db", ".sqlite", ".pkl")):
        return False
    # Pure SAS-style name (all word chars, no dots in name part) → likely internal
    return bool(re.match(r"^[a-z_]\w*\.(csv|xlsx?|parquet)$", fp_lower))


# ── Convenience: extract referenced DataFrames from code ─────────────────────

def extract_referenced_names(python_code: str) -> set[str]:
    """Return the set of variable names that look like DataFrame reads."""
    names: set[str] = set()
    for pattern in _READ_PATTERNS:
        for m in pattern.finditer(python_code):
            names.add(_filepath_to_name(m.group(1)))
    return names


def build_internal_table_set(sas_code: str) -> set[str]:
    """Extract all output dataset names from a SAS script as internal tables.

    These names should NOT be reloaded from disk in any downstream chunk.
    """
    names: set[str] = set()

    # DATA <out>; ...
    for m in re.finditer(r"data\s+([A-Za-z0-9_.]+)", sas_code, re.IGNORECASE):
        raw = m.group(1).lower()
        names.add(raw.split(".")[-1])

    # out= on PROCs
    for m in re.finditer(r"\bout\s*=\s*([A-Za-z0-9_.]+)", sas_code, re.IGNORECASE):
        raw = m.group(1).lower()
        names.add(raw.split(".")[-1])

    # WORK library (always internal)
    names.discard("work")
    return names
