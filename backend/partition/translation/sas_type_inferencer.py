"""SAS abstract type inferencer — lightweight static type propagation.

Implements a simplified abstract interpretation (Cousot & Cousot, 1977)
over a SAS DATA step to track column types through assignments.

Abstract domain
---------------
Each variable is assigned one of six abstract types:

    NUMERIC    — numeric (integer or float), no format context
    CHARACTER  — character / string ($-prefixed)
    DATE       — numeric holding days since 1960-01-01
    DATETIME   — numeric holding seconds since 1960-01-01 00:00:00
    TIME       — numeric holding seconds since midnight
    UNKNOWN    — could not be determined

Why this matters
----------------
SAS has implicit typing rules that are a primary source of translation errors:
- DATE variables ARE numeric in SAS (stored as days since 1960-01-01)
- A WHERE clause ``IF date > '01JAN2024'D`` compares a numeric to a date literal
- After translation, the LLM often writes `df['date'] > '2024-01-01'` (string comparison)
  when it should write `df['date'] > pd.Timestamp('2024-01-01')`

The inferencer surfaces this type information so ErrorAnalysis can give
precise DTYPE_MISMATCH repair hints instead of generic guidance.

Usage::

    from partition.translation.sas_type_inferencer import infer_types

    report = infer_types(sas_code)
    # report.typed_columns: dict[str, SASType]
    # report.to_prompt_block(): Markdown block for LLM
    # report.get_conversion_hints(): list of concrete pd.to_datetime hints
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SASType(str, Enum):
    NUMERIC   = "NUMERIC"
    CHARACTER = "CHARACTER"
    DATE      = "DATE"
    DATETIME  = "DATETIME"
    TIME      = "TIME"
    UNKNOWN   = "UNKNOWN"


# ── Type inference rules ──────────────────────────────────────────────────────

# Functions that produce DATE output
_DATE_FUNCTIONS = frozenset({
    "TODAY", "DATE", "MDY", "YMD", "DATEPART",
    "INTNX",   # when interval is a date interval
    "INPUT",   # when informat is a date informat — checked separately
})

# Functions that produce DATETIME output
_DATETIME_FUNCTIONS = frozenset({"DATETIME", "DHMS", "DATEPART", "DATETIMEX"})

# Functions that produce TIME output
_TIME_FUNCTIONS = frozenset({"TIME", "HMS", "TIMEPART"})

# Format names that indicate DATE storage (normalized — no width/dec)
_DATE_FORMATS = frozenset({
    "DATE", "DATE7", "DATE9", "DDMMYY", "DDMMYY8", "DDMMYY10",
    "MMDDYY", "MMDDYY8", "MMDDYY10", "YYMMDD", "YYMMDD8", "YYMMDD10",
    "MONYY", "MONYY5", "MONYY7", "MONNAME", "WEEKDATE",
    "JULIAN", "JULDAY", "DAY", "MONTH", "YEAR", "QTR",
    "NLDATE", "IS8601DA", "E8601DA",
})

_DATETIME_FORMATS = frozenset({
    "DATETIME", "DATETIME18", "DATETIME20", "IS8601DT", "E8601DT",
})

_TIME_FORMATS = frozenset({"TIME", "TIME5", "TIME8"})

# Character informat prefix
_CHAR_INFORMAT_RE = re.compile(r"^\$", re.IGNORECASE)

# Dollar-sign prefix on variable names in INPUT statement
_CHAR_VAR_RE = re.compile(r"\$(\w+)", re.IGNORECASE)


def _normalize_format(fmt: str) -> str:
    """Strip width.dec and uppercase: 'date9.' → 'DATE'."""
    s = fmt.strip().upper().rstrip(".")
    return re.sub(r"\d+\.?\d*$", "", s)


@dataclass
class TypeReport:
    """Results of type inference over a SAS DATA step."""
    typed_columns: dict[str, SASType] = field(default_factory=dict)
    format_annotations: dict[str, str] = field(default_factory=dict)  # col → format name

    def get_type(self, col: str) -> SASType:
        return self.typed_columns.get(col.lower(), SASType.UNKNOWN)

    def get_conversion_hints(self) -> list[str]:
        """Return concrete pandas conversion hints for date/datetime columns."""
        hints = []
        for col, stype in self.typed_columns.items():
            fmt = self.format_annotations.get(col, "")
            if stype == SASType.DATE:
                hints.append(
                    f"`{col}`: SAS DATE (numeric days since 1960-01-01) → "
                    f"`pd.to_datetime(df['{col}'], unit='D', origin='1960-01-01')`"
                )
            elif stype == SASType.DATETIME:
                hints.append(
                    f"`{col}`: SAS DATETIME (numeric seconds since 1960-01-01) → "
                    f"`pd.to_datetime(df['{col}'], unit='s', origin='1960-01-01')`"
                )
            elif stype == SASType.TIME:
                hints.append(
                    f"`{col}`: SAS TIME (seconds since midnight) → "
                    f"`pd.to_timedelta(df['{col}'], unit='s')`"
                )
        return hints

    def to_prompt_block(self) -> str:
        """Render as a ## SAS Column Types block for injection into LLM prompt."""
        if not self.typed_columns:
            return ""

        non_numeric = {
            col: stype for col, stype in self.typed_columns.items()
            if stype != SASType.NUMERIC
        }
        if not non_numeric:
            return ""

        lines = ["## SAS Column Type Annotations (inferred from DATA step)"]
        for col, stype in sorted(non_numeric.items()):
            fmt = self.format_annotations.get(col, "")
            fmt_note = f" (format: `{fmt}`)" if fmt else ""
            if stype == SASType.DATE:
                lines.append(
                    f"- `{col}` is **DATE**{fmt_note}: stored as days-since-1960-01-01 (numeric). "
                    "Use `pd.to_datetime(df['col'], unit='D', origin='1960-01-01')`."
                )
            elif stype == SASType.DATETIME:
                lines.append(
                    f"- `{col}` is **DATETIME**{fmt_note}: stored as seconds-since-1960-01-01. "
                    "Use `pd.to_datetime(df['col'], unit='s', origin='1960-01-01')`."
                )
            elif stype == SASType.TIME:
                lines.append(
                    f"- `{col}` is **TIME**{fmt_note}: stored as seconds-since-midnight. "
                    "Use `pd.to_timedelta(df['col'], unit='s')`."
                )
            elif stype == SASType.CHARACTER:
                lines.append(f"- `{col}` is **CHARACTER**: keep as string dtype; do NOT cast to numeric.")
            else:
                lines.append(f"- `{col}` is **{stype.value}**{fmt_note}")

        hints = self.get_conversion_hints()
        if hints:
            lines.append("\n### Concrete conversion expressions")
            lines.extend(f"  {h}" for h in hints)

        return "\n".join(lines)


# ── Inference engine ──────────────────────────────────────────────────────────

class _TypeEnv:
    """Mutable type environment for a single DATA step analysis pass."""

    def __init__(self):
        self._types: dict[str, SASType] = {}
        self._formats: dict[str, str] = {}

    def set(self, var: str, stype: SASType, fmt: str = "") -> None:
        var = var.lower()
        # Lattice join: DATE/DATETIME/TIME overrides NUMERIC/UNKNOWN; CHAR never demoted
        current = self._types.get(var, SASType.UNKNOWN)
        if current == SASType.CHARACTER and stype != SASType.CHARACTER:
            return   # char never becomes numeric
        if stype in (SASType.DATE, SASType.DATETIME, SASType.TIME):
            self._types[var] = stype
        elif current == SASType.UNKNOWN:
            self._types[var] = stype
        if fmt:
            self._formats[var] = fmt

    def get(self, var: str) -> SASType:
        return self._types.get(var.lower(), SASType.UNKNOWN)

    def to_report(self) -> TypeReport:
        return TypeReport(
            typed_columns={k: v for k, v in self._types.items()},
            format_annotations=dict(self._formats),
        )


def _infer_from_format_statements(sas_code: str, env: _TypeEnv) -> None:
    """Extract FORMAT / INFORMAT statements and annotate variable types."""
    # FORMAT var fmt;
    for m in re.finditer(
        r"\bformat\b\s+([A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*)\s+(\$?[A-Za-z_]\w*\d*\.?\d*)\s*;",
        sas_code, re.IGNORECASE,
    ):
        raw_vars = m.group(1).strip().split()
        raw_fmt  = m.group(2)
        norm_fmt = _normalize_format(raw_fmt.lstrip("$"))
        for var in raw_vars:
            if raw_fmt.startswith("$"):
                env.set(var, SASType.CHARACTER, raw_fmt)
            elif norm_fmt in _DATE_FORMATS:
                env.set(var, SASType.DATE, norm_fmt)
            elif norm_fmt in _DATETIME_FORMATS:
                env.set(var, SASType.DATETIME, norm_fmt)
            elif norm_fmt in _TIME_FORMATS:
                env.set(var, SASType.TIME, norm_fmt)

    # INFORMAT var inf;
    for m in re.finditer(
        r"\binformat\b\s+([A-Za-z_]\w*(?:\s+[A-Za-z_]\w*)*)\s+(\$?[A-Za-z_]\w*\d*\.?\d*)\s*;",
        sas_code, re.IGNORECASE,
    ):
        raw_vars = m.group(1).strip().split()
        raw_inf  = m.group(2)
        norm_inf = _normalize_format(raw_inf.lstrip("$"))
        for var in raw_vars:
            if raw_inf.startswith("$"):
                env.set(var, SASType.CHARACTER, raw_inf)
            elif norm_inf in _DATE_FORMATS:
                env.set(var, SASType.DATE, norm_inf)
            elif norm_inf in _DATETIME_FORMATS:
                env.set(var, SASType.DATETIME, norm_inf)


def _infer_from_input_statement(sas_code: str, env: _TypeEnv) -> None:
    """Infer types from INPUT statement variable declarations."""
    # INPUT name $ ... name informat.
    input_m = re.search(r"\binput\b([^;]+);", sas_code, re.IGNORECASE)
    if not input_m:
        return
    input_body = input_m.group(1)
    tokens = input_body.split()
    i = 0
    pending_var: Optional[str] = None
    while i < len(tokens):
        tok = tokens[i]
        if tok == "$":
            if pending_var:
                env.set(pending_var, SASType.CHARACTER)
            i += 1
        elif re.match(r"^\$\w+$", tok):
            env.set(tok[1:], SASType.CHARACTER)
            pending_var = None
            i += 1
        elif "." in tok or re.match(r"^[A-Z]+\d*$", tok, re.IGNORECASE):
            # Looks like a format/informat
            norm = _normalize_format(tok.lstrip("$"))
            if pending_var:
                if tok.startswith("$"):
                    env.set(pending_var, SASType.CHARACTER, tok)
                elif norm in _DATE_FORMATS:
                    env.set(pending_var, SASType.DATE, norm)
                elif norm in _DATETIME_FORMATS:
                    env.set(pending_var, SASType.DATETIME, norm)
            pending_var = None
            i += 1
        elif re.match(r"^[A-Za-z_]\w*$", tok):
            pending_var = tok
            i += 1
        else:
            i += 1


def _infer_from_assignments(sas_code: str, env: _TypeEnv) -> None:
    """Infer types from assignment statements using RHS function calls."""
    # var = FUNCTION(...);
    assign_re = re.compile(
        r"([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\(", re.IGNORECASE
    )
    for m in assign_re.finditer(sas_code):
        var = m.group(1)
        fn  = m.group(2).upper()
        if fn in _DATE_FUNCTIONS:
            env.set(var, SASType.DATE)
        elif fn in _DATETIME_FUNCTIONS:
            env.set(var, SASType.DATETIME)
        elif fn in _TIME_FUNCTIONS:
            env.set(var, SASType.TIME)

    # var = 'string'  (string literal assignment → CHARACTER)
    str_assign_re = re.compile(
        r"([A-Za-z_]\w*)\s*=\s*['\"]", re.IGNORECASE
    )
    for m in str_assign_re.finditer(sas_code):
        var = m.group(1)
        if env.get(var) == SASType.UNKNOWN:
            env.set(var, SASType.CHARACTER)


def infer_types(sas_code: str) -> TypeReport:
    """Run abstract type inference over a SAS code block.

    Works on DATA steps, PROC SQL, and mixed blocks.
    Returns a TypeReport with typed_columns and format_annotations.
    """
    env = _TypeEnv()
    _infer_from_format_statements(sas_code, env)
    _infer_from_input_statement(sas_code, env)
    _infer_from_assignments(sas_code, env)
    return env.to_report()
