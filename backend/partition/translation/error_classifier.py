"""Error classifier for translated Python code.

Buckets runtime/validation errors into 17 categories so the
error analyst and corrective prompts can give targeted guidance.

Usage::

    report = classify_error("KeyError: 'amount'", traceback_str, code)
    print(report.primary_category)   # "COL_MISSING"
    print(report.repair_hint)        # targeted fix hint
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Category constants ────────────────────────────────────────────────────────

SYNTAX = "SYNTAX"
TIMEOUT = "TIMEOUT"
NAME_ERROR = "NAME_ERROR"
IMPORT_ERROR = "IMPORT_ERROR"
KEY_ERROR = "KEY_ERROR"  # column / key missing
TYPE_ERROR = "TYPE_ERROR"
VALUE_ERROR = "VALUE_ERROR"
ATTRIBUTE_ERROR = "ATTRIBUTE_ERROR"
DTYPE_MISMATCH = "DTYPE_MISMATCH"  # object instead of numeric
COL_MISSING = "COL_MISSING"  # column not found (KeyError on df col)
COL_EXTRA = "COL_EXTRA"  # unexpected output column
MERGE_CONTRACT = "MERGE_CONTRACT"  # join semantics wrong
SORT_ORDER = "SORT_ORDER"  # wrong sort / unstable
RETAIN_SEQUENCE = "RETAIN_SEQUENCE"  # RETAIN / cumsum reset wrong
LAG_SEQUENCE = "LAG_SEQUENCE"  # LAG / shift semantics wrong
GROUP_BOUNDARY = "GROUP_BOUNDARY"  # FIRST. / LAST. logic wrong
EMPTY_SUSPICIOUS = "EMPTY_SUSPICIOUS"  # output is empty but shouldn't be
OUTPUT_MISSING = "OUTPUT_MISSING"  # final DataFrame not assigned / returned
RUNTIME_GENERAL = "RUNTIME_GENERAL"  # catch-all runtime


# ── Repair hints per category ─────────────────────────────────────────────────

REPAIR_HINTS: dict[str, str] = {
    SYNTAX: (
        "Fix the Python syntax error. Check for unmatched brackets, "
        "wrong indentation, or invalid f-strings."
    ),
    TIMEOUT: (
        "The code took too long. Avoid nested Python loops on DataFrames; "
        "replace with vectorised pandas operations."
    ),
    NAME_ERROR: (
        "A variable name is undefined. Make sure all SAS dataset names are "
        "declared as DataFrames before use, and that macro variables are "
        "resolved to their Python equivalents."
    ),
    IMPORT_ERROR: (
        "A required library is not imported. Add the necessary import at the "
        "top of the script (e.g., `import numpy as np`)."
    ),
    KEY_ERROR: (
        "A dictionary key or DataFrame column is missing. "
        "Lowercase all column names immediately after loading: "
        "`df.columns = df.columns.str.lower()`. "
        "Check that the column exists in the input DataFrame."
    ),
    COL_MISSING: (
        "A column referenced in the code does not exist in the DataFrame. "
        "Ensure column names are lowercased and that the correct input table "
        "is being used. SAS column names are case-insensitive; Python is not."
    ),
    TYPE_ERROR: (
        "A type mismatch occurred. Check arithmetic between string and numeric "
        "columns. Strip currency symbols / commas before converting: "
        "`df['col'] = pd.to_numeric(df['col'].str.replace(',','').str.replace('$',''), errors='coerce')`."
    ),
    VALUE_ERROR: (
        "A value conversion failed. Use `pd.to_numeric(..., errors='coerce')` "
        "instead of direct casting. Check for NaN / empty strings."
    ),
    ATTRIBUTE_ERROR: (
        "A method or attribute does not exist on the object. "
        "Check that the variable is a DataFrame (not a Series or None) "
        "before calling DataFrame methods."
    ),
    DTYPE_MISMATCH: (
        "A column is the wrong dtype (e.g., 'object' instead of numeric). "
        "Strip non-numeric characters and use `pd.to_numeric(..., errors='coerce')` "
        "before arithmetic operations."
    ),
    COL_EXTRA: (
        "The output DataFrame has unexpected extra columns. "
        "Apply the correct KEEP/DROP list from the SAS code. "
        "Use `df = df[expected_cols]` to enforce the output schema."
    ),
    MERGE_CONTRACT: (
        "The join semantics are wrong. Determine the SAS merge type:\n"
        "  - `IN=a AND IN=b` (both) → `how='inner'`\n"
        "  - `IN=a` only (left only) → `how='left'` then filter where right NaN\n"
        "  - All rows → `how='outer'`\n"
        "Use `pd.merge(left, right, on=keys, how=...)` and preserve BY-group sort order."
    ),
    SORT_ORDER: (
        "The output is sorted incorrectly. Use `sort_values(by=[...], ascending=[...], "
        "kind='mergesort')` to match SAS stable sort behaviour. "
        "Ensure DESCENDING columns use `ascending=False`."
    ),
    RETAIN_SEQUENCE: (
        "RETAIN / cumulative logic is wrong. Use `.cumsum()` for running totals, "
        "`.expanding().sum()` for expanding windows, or `groupby(...).cumsum()` "
        "for by-group accumulation. Reset accumulators at group boundaries with "
        "`.groupby(group_col).transform(lambda x: ...)` patterns."
    ),
    LAG_SEQUENCE: (
        "LAG / shift logic is wrong. `LAG(var)` → `df['var'].shift(1)`. "
        "SAS LAG resets at DATA step boundaries — within a BY group use "
        "`df.groupby(by_col)['var'].shift(1)`. "
        "Fill the first row with `np.nan` or the initial value from the SAS code."
    ),
    GROUP_BOUNDARY: (
        "FIRST./LAST. logic is wrong. To detect group boundaries:\n"
        "  FIRST.var: `df['first_var'] = df['var'] != df['var'].shift(1)`\n"
        "  LAST.var:  `df['last_var'] = df['var'] != df['var'].shift(-1)`\n"
        "Sort by the BY variable first, then apply these masks."
    ),
    EMPTY_SUSPICIOUS: (
        "The output DataFrame is unexpectedly empty. "
        "Check filter conditions — SAS missing values compare differently than pandas NaN. "
        "Use `pd.isna()` checks instead of `== ''` or `== 0` for missing value tests."
    ),
    OUTPUT_MISSING: (
        "The translated code does not assign a final output DataFrame. "
        "Make sure the last statement produces a named variable matching the "
        "SAS output dataset name. Do NOT wrap the code in `def main()` — "
        "produce a flat script with the output DataFrame as a top-level variable."
    ),
    RUNTIME_GENERAL: (
        "A runtime error occurred. Read the traceback carefully, identify the "
        "failing line, and fix the underlying logic issue."
    ),
}


# ── Classification rules ──────────────────────────────────────────────────────


@dataclass
class ErrorReport:
    primary_category: str
    all_categories: list[str] = field(default_factory=list)
    error_message: str = ""
    traceback: str = ""
    affected_columns: list[str] = field(default_factory=list)
    repair_hint: str = ""


def classify_error(
    error_message: str,
    traceback_str: str = "",
    code: str = "",
) -> ErrorReport:
    """Classify an error into one of 17 categories.

    Args:
        error_message: The exception message (e.g. ``"KeyError: 'amount'"``)
        traceback_str: Full traceback string (optional)
        code:          The translated Python code (optional, for context)

    Returns:
        ``ErrorReport`` with ``primary_category``, ``all_categories``,
        and a targeted ``repair_hint``.
    """
    msg = error_message.lower()
    tb = traceback_str.lower()
    combined = msg + " " + tb

    categories: list[str] = []
    affected_cols: list[str] = []

    # ── Syntax ──
    if "syntaxerror" in combined or error_message.startswith("SyntaxError"):
        categories.append(SYNTAX)

    # ── Timeout ──
    if "timeout" in combined or "timed out" in combined:
        categories.append(TIMEOUT)

    # ── Import ──
    if (
        "importerror" in combined
        or "modulenotfounderror" in combined
        or "no module named" in combined
    ):
        categories.append(IMPORT_ERROR)

    # ── NameError ──
    if "nameerror" in combined or "name '" in combined:
        categories.append(NAME_ERROR)

    # ── AttributeError ──
    if "attributeerror" in combined:
        categories.append(ATTRIBUTE_ERROR)

    # ── KeyError — distinguish column vs generic dict ──
    if "keyerror" in combined:
        col_m = re.search(r"keyerror[:\s]*['\"]?([A-Za-z_]\w*)['\"]?", combined)
        if col_m:
            affected_cols.append(col_m.group(1))
        # column access on a DataFrame → COL_MISSING, otherwise KEY_ERROR
        if "df[" in code.lower() or "columns" in combined or "column" in combined:
            categories.append(COL_MISSING)
        else:
            categories.append(KEY_ERROR)

    # ── TypeError ──
    if "typeerror" in combined:
        if "str" in combined and ("+" in error_message or "concatenat" in combined):
            categories.append(DTYPE_MISMATCH)
        else:
            categories.append(TYPE_ERROR)

    # ── ValueError ──
    if "valueerror" in combined:
        if "could not convert" in combined or "invalid literal" in combined:
            categories.append(DTYPE_MISMATCH)
        categories.append(VALUE_ERROR)

    # ── DTYPE ──
    if any(x in combined for x in ("object dtype", "cannot convert", "unsupported operand")):
        if DTYPE_MISMATCH not in categories:
            categories.append(DTYPE_MISMATCH)

    # ── Merge contract ──
    if any(x in combined for x in ("merge", "join", "in_left", "in_right", "_merge")):
        categories.append(MERGE_CONTRACT)

    # ── Sort order ──
    if "sort" in combined and any(x in combined for x in ("order", "ascending", "descending")):
        categories.append(SORT_ORDER)

    # ── RETAIN ──
    if any(x in combined for x in ("retain", "cumsum", "cumulative")):
        categories.append(RETAIN_SEQUENCE)

    # ── LAG ──
    if any(x in combined for x in ("lag", "shift", "lag_")):
        categories.append(LAG_SEQUENCE)

    # ── FIRST./LAST. group boundary ──
    if any(x in combined for x in ("first.", "last.", "group_boundary", "first_", "last_")):
        categories.append(GROUP_BOUNDARY)

    # ── Empty output ──
    if any(x in combined for x in ("empty dataframe", "length 0", "0 rows", "empty result")):
        categories.append(EMPTY_SUSPICIOUS)

    # ── Missing output ──
    if any(x in combined for x in ("not defined", "no output", "output_missing")):
        categories.append(OUTPUT_MISSING)

    # ── Fall-through ──
    if not categories:
        categories.append(RUNTIME_GENERAL)

    primary = categories[0]
    hint = REPAIR_HINTS.get(primary, REPAIR_HINTS[RUNTIME_GENERAL])

    return ErrorReport(
        primary_category=primary,
        all_categories=list(dict.fromkeys(categories)),  # deduplicated, order preserved
        error_message=error_message,
        traceback=traceback_str,
        affected_columns=affected_cols,
        repair_hint=hint,
    )
