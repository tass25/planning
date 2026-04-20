"""dummy_data_generator.py — Adversarial SAS-aware test DataFrame generator.

Generates input DataFrames that specifically stress-test SAS→Python migration
failure modes rather than random/benign data:

  - NaN injection         : SAS handles missing (.) per-variable; pandas NaN
                            propagates differently in arithmetic and groupby.
  - Currency strings      : $1,234.56 triggers dtype coercion bugs.
  - Sort instability      : duplicate BY-key rows expose mergesort vs quicksort.
  - Mixed-case strings    : 'NORTH' vs 'north' — SAS comparisons are case-sensitive
                            unless UPCASE() is used; translators often forget.
  - Multi-group BY layout : ≥3 groups × ≥3 rows/group so RETAIN reset and
                            FIRST./LAST. logic is exercised across group boundaries.
  - Numeric edge cases    : zeros, negatives, very large values.
  - Exact duplicate rows  : exposes NODUP/NODUPKEY translation bugs.

Usage::

    gen = DummyDataGenerator(sas_code)
    frames = gen.generate()          # dict[str, pd.DataFrame]
    # frames keys = input table names parsed from SET/MERGE statements
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

random.seed(42)
np.random.seed(42)

# ── defaults ──────────────────────────────────────────────────────────────────
_DEFAULT_N_ROWS = 30  # total rows per table
_NULL_RATE = 0.08  # 8% of numeric cells are NaN
_N_GROUPS = 3  # distinct BY-group values
_ROWS_PER_GROUP = 10  # rows per group (N_GROUPS × ROWS_PER_GROUP = N_ROWS)
_N_DUPLICATES = 2  # extra exact-duplicate rows appended
_CURRENCY_COL_MAX = 1  # at most 1 numeric col rendered as "$x,xxx.xx"

# ── SAS-aware column name lists ───────────────────────────────────────────────
_NUMERIC_CONTEXTS = re.compile(
    r"""
    (?:retain|sum|mean|min|max|n\b|lag\d*\s*\()  # retain / aggregation / lag
    \s+[^;]*?([A-Za-z_]\w*)                      # captures col name
    |([A-Za-z_]\w*)\s*[+\-*/]=                   # arithmetic assignment
    |([A-Za-z_]\w*)\s*\+\s*[A-Za-z0-9_]         # sum accumulator
    |var\s+([A-Za-z_]\w*)                         # PROC VAR statement
    """,
    re.IGNORECASE | re.VERBOSE,
)

_STRING_CONTEXTS = re.compile(
    r"""
    ([A-Za-z_]\w*)\s*=\s*['"]         # lhs = "literal"
    |([A-Za-z_]\w*)\s+in\s*\(         # col IN ('a','b')
    |upcase\s*\(\s*([A-Za-z_]\w*)     # UPCASE(col)
    |input\s+[^;]*?([A-Za-z_]\w*)\s+\$  # INPUT col $
    """,
    re.IGNORECASE | re.VERBOSE,
)

_BY_RE = re.compile(r"\bby\s+([^;/\n]+?)(?:;|$|\n)", re.IGNORECASE)
_SET_RE = re.compile(r"\bset\s+([A-Za-z0-9_. ]+?)(?:;|$|\n)", re.IGNORECASE)
_MERGE_RE = re.compile(r"\bmerge\s+([A-Za-z0-9_. ()=\n\t]+?)(?:;|$)", re.IGNORECASE | re.DOTALL)
_DATA_OUT_RE = re.compile(r"^\s*data\s+([\w.]+)", re.IGNORECASE | re.MULTILINE)
_OUT_RE = re.compile(r"\bout\s*=\s*([\w.]+)", re.IGNORECASE)

_SAS_RESERVED = frozenset(
    {
        "and",
        "by",
        "data",
        "do",
        "drop",
        "else",
        "end",
        "first",
        "if",
        "in",
        "keep",
        "lag",
        "last",
        "like",
        "merge",
        "not",
        "or",
        "output",
        "retain",
        "run",
        "set",
        "then",
        "to",
        "until",
        "when",
        "where",
        "while",
    }
)

_GROUP_LABELS = ["NORTH", "SOUTH", "EAST", "WEST", "CENTRAL"]
_STATUS_LABELS = ["ACTIVE", "CLOSED", "PENDING", "REVIEW", "HOLD"]
_TYPE_LABELS = ["TYPE_A", "TYPE_B", "TYPE_C"]


# ── helpers ───────────────────────────────────────────────────────────────────


def _clean_name(raw: str) -> str:
    """Strip libname prefix, lower-case."""
    return raw.strip().lower().split(".")[-1]


def _parse_table_names(sas_code: str, pattern: re.Pattern) -> list[str]:
    names: list[str] = []
    for m in pattern.finditer(sas_code):
        for tok in re.split(r"[\s\n\t]+", m.group(1)):
            tok = re.sub(r"\(.*?\)", "", tok).strip()
            if tok and re.match(r"^[A-Za-z_]\w*", tok):
                cleaned = _clean_name(tok)
                if cleaned not in _SAS_RESERVED and cleaned not in names:
                    names.append(cleaned)
    return names


def _parse_by_columns(sas_code: str) -> list[str]:
    cols: list[str] = []
    for m in _BY_RE.finditer(sas_code):
        for tok in m.group(1).split():
            t = tok.strip().lower()
            if t and t not in _SAS_RESERVED and t not in cols:
                cols.append(t)
    return cols


def _infer_numeric_cols(sas_code: str) -> set[str]:
    cols: set[str] = set()
    for m in _NUMERIC_CONTEXTS.finditer(sas_code):
        for g in m.groups():
            if g:
                c = g.strip().lower()
                if c and c not in _SAS_RESERVED:
                    cols.add(c)
    return cols


def _infer_string_cols(sas_code: str) -> set[str]:
    cols: set[str] = set()
    for m in _STRING_CONTEXTS.finditer(sas_code):
        for g in m.groups():
            if g:
                c = g.strip().lower()
                if c and c not in _SAS_RESERVED:
                    cols.add(c)
    return cols


def _all_referenced_cols(sas_code: str) -> set[str]:
    """Any word that looks like a column reference (not a keyword, not a literal)."""
    cols: set[str] = set()
    for tok in re.findall(r"\b([A-Za-z_]\w*)\b", sas_code):
        t = tok.lower()
        if t not in _SAS_RESERVED and len(t) > 1:
            cols.add(t)
    return cols


# ── column generators ─────────────────────────────────────────────────────────


def _gen_numeric_col(n: int, as_currency: bool = False) -> list:
    """Numeric column with NaN injection, zeros, negatives."""
    rng = np.random.default_rng(42)
    values = rng.uniform(100, 50_000, n).round(2).tolist()
    # Inject edge cases
    values[0] = 0.0
    values[1] = -rng.uniform(1, 100, 1)[0].round(2)
    values[2] = 999_999.99
    # NaN injection
    n_nulls = max(1, int(n * _NULL_RATE))
    for idx in random.sample(range(3, n), n_nulls):
        values[idx] = float("nan")
    if as_currency:
        return [f"${v:,.2f}" if not (isinstance(v, float) and np.isnan(v)) else "" for v in values]
    return values


def _gen_string_col(n: int, labels: list[str], mixed_case: bool = False) -> list:
    """String column with optional mixed-case adversarial values."""
    cycle = (labels * ((n // len(labels)) + 1))[:n]
    if mixed_case:
        # Mix: all-caps, all-lower, title-case → exposes case-sensitivity bugs
        variants = [
            cycle[i].upper() if i % 3 == 0 else cycle[i].lower() if i % 3 == 1 else cycle[i].title()
            for i in range(n)
        ]
        return variants
    return cycle


def _gen_by_col(n: int, n_groups: int, col_name: str) -> list:
    """BY-group column: exactly n_groups groups, sorted, ≥_ROWS_PER_GROUP rows each."""
    labels = _GROUP_LABELS[:n_groups]
    per_group = n // n_groups
    col = []
    for label in labels:
        col.extend([label] * per_group)
    # pad remainder
    while len(col) < n:
        col.append(labels[-1])
    return col


# ── main class ────────────────────────────────────────────────────────────────


@dataclass
class DummyDataGenerator:
    """Generate adversarial input DataFrames from a SAS code block.

    Args:
        sas_code:  The SAS source code of the partition to test.
        n_rows:    Number of rows per generated table (default 30).
    """

    sas_code: str
    n_rows: int = _DEFAULT_N_ROWS

    # populated by generate()
    _input_tables: list[str] = field(default_factory=list, init=False)
    _by_cols: list[str] = field(default_factory=list, init=False)
    _numeric_cols: set[str] = field(default_factory=set, init=False)
    _string_cols: set[str] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        code = self.sas_code or ""
        self._input_tables = _parse_table_names(code, _SET_RE) + _parse_table_names(code, _MERGE_RE)
        if not self._input_tables:
            self._input_tables = ["_input"]

        self._by_cols = _parse_by_columns(code)
        self._numeric_cols = _infer_numeric_cols(code)
        self._string_cols = _infer_string_cols(code)

        # Anything remaining that looks like a column but isn't classified
        all_refs = _all_referenced_cols(code)
        for c in all_refs:
            if c not in self._numeric_cols and c not in self._string_cols:
                if c not in self._by_cols:
                    # Default to numeric for unclassified columns
                    self._numeric_cols.add(c)

    # ── public ────────────────────────────────────────────────────────────────

    def generate(self) -> dict[str, pd.DataFrame]:
        """Return a dict of {table_name: adversarial DataFrame}."""
        frames: dict[str, pd.DataFrame] = {}
        for i, tname in enumerate(self._input_tables):
            frames[tname] = self._build_frame(seed_offset=i)
        return frames

    def output_table_names(self) -> list[str]:
        """Parse expected output table names from DATA/OUT= statements."""
        names: list[str] = []
        for m in _DATA_OUT_RE.finditer(self.sas_code):
            n = _clean_name(m.group(1))
            if n not in _SAS_RESERVED and n not in names:
                names.append(n)
        for m in _OUT_RE.finditer(self.sas_code):
            n = _clean_name(m.group(1))
            if n not in _SAS_RESERVED and n not in names:
                names.append(n)
        return names

    # ── private ───────────────────────────────────────────────────────────────

    def _build_frame(self, seed_offset: int = 0) -> pd.DataFrame:
        n = self.n_rows
        rng = np.random.default_rng(42 + seed_offset)
        cols: dict[str, list] = {}

        # 1. BY columns first (pre-sorted for SAS BY-group processing)
        if self._by_cols:
            primary_by = self._by_cols[0]
            cols[primary_by] = _gen_by_col(n, _N_GROUPS, primary_by)
            for extra_by in self._by_cols[1:]:
                # Secondary BY: numeric sequence within group
                group_size = n // _N_GROUPS
                seq = list(range(1, group_size + 1)) * _N_GROUPS
                cols[extra_by] = seq[:n]

        # 2. Numeric columns (one rendered as currency for adversarial dtype)
        currency_used = False
        for ci, col in enumerate(sorted(self._numeric_cols)):
            if col in cols:
                continue
            as_currency = not currency_used and ci == 0 and col not in (self._by_cols or [])
            cols[col] = _gen_numeric_col(n, as_currency=as_currency)
            if as_currency:
                currency_used = True

        # 3. String columns — first one gets mixed-case treatment
        first_str = True
        for col in sorted(self._string_cols):
            if col in cols:
                continue
            labels = _STATUS_LABELS if "status" in col else _TYPE_LABELS
            cols[col] = _gen_string_col(n, labels, mixed_case=first_str)
            first_str = False

        # 4. Always add a generic numeric "value" col if nothing else was generated
        if not cols or all(k in self._by_cols for k in cols):
            cols["value"] = _gen_numeric_col(n)
            cols["amount"] = rng.uniform(10, 1000, n).round(2).tolist()
            cols["category"] = _gen_by_col(n, _N_GROUPS, "category")

        df = pd.DataFrame(cols)

        # 5. Sort by BY columns (SAS requires pre-sorted data for BY-group processing)
        if self._by_cols:
            valid_by = [c for c in self._by_cols if c in df.columns]
            if valid_by:
                df = df.sort_values(valid_by, kind="mergesort").reset_index(drop=True)

        # 6. Append exact duplicate rows (exposes NODUP/NODUPKEY bugs)
        if len(df) >= _N_DUPLICATES:
            dupes = df.iloc[:_N_DUPLICATES].copy()
            df = pd.concat([df, dupes], ignore_index=True)

        return df
