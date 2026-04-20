"""Error analyst — root cause diagnosis and structured repair strategy.

Given an ErrorReport, produces an ErrorAnalysis that the corrective
prompt can inject directly, telling the LLM:
  - root_cause       : what went wrong and why
  - non_neg_contract : hard constraints the fix must satisfy
  - forbidden        : things the fix must NOT do
  - repair_strategy  : step-by-step instructions
  - minimal_scope    : how much code should actually change

Usage::

    from partition.translation.error_classifier import classify_error
    from partition.translation.error_analyst import analyse_error

    report   = classify_error(error_msg, traceback, code)
    analysis = analyse_error(report, sas_code, python_code, partition_type)
    # inject analysis.to_prompt_block() into the corrective prompt
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Optional

from partition.translation.error_classifier import (
    COL_MISSING,
    DTYPE_MISMATCH,
    EMPTY_SUSPICIOUS,
    GROUP_BOUNDARY,
    KEY_ERROR,
    LAG_SEQUENCE,
    MERGE_CONTRACT,
    OUTPUT_MISSING,
    RETAIN_SEQUENCE,
    SORT_ORDER,
    TYPE_ERROR,
    VALUE_ERROR,
    ErrorReport,
)


@dataclass
class ErrorAnalysis:
    root_cause: str
    non_neg_contract: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)
    repair_strategy: list[str] = field(default_factory=list)
    minimal_scope: str = "Fix only the failing section; leave all other logic unchanged."
    code_slice: str = ""  # program slice injected from AST analysis

    def to_prompt_block(self) -> str:
        """Render as a Markdown block for injection into a correction prompt."""
        lines = ["## Error Analysis\n"]
        lines.append(f"**Root cause**: {self.root_cause}\n")

        if self.non_neg_contract:
            lines.append("**Non-negotiable constraints** (must hold in the fix):")
            for c in self.non_neg_contract:
                lines.append(f"  - {c}")
            lines.append("")

        if self.forbidden:
            lines.append("**Forbidden actions** (must NOT appear in the fix):")
            for f_ in self.forbidden:
                lines.append(f"  - {f_}")
            lines.append("")

        if self.repair_strategy:
            lines.append("**Repair strategy** (follow in order):")
            for i, s in enumerate(self.repair_strategy, 1):
                lines.append(f"  {i}. {s}")
            lines.append("")

        lines.append(f"**Minimal scope**: {self.minimal_scope}")

        if self.code_slice:
            lines.append(
                "\n### Relevant code slice (>>> marks direct column references)\n"
                "```python\n"
                f"{self.code_slice}\n"
                "```\n"
                "_Fix only these lines. Do NOT modify anything outside this slice._"
            )

        return "\n".join(lines)


# ── Program slicing (Weiser 1984 / SRepair ISSTA 2024) ───────────────────────


def _extract_failing_lineno(traceback_str: str) -> Optional[int]:
    """Extract the last failing line number from a Python traceback string."""
    matches = re.findall(r",\s*line\s+(\d+)", traceback_str)
    if matches:
        return int(matches[-1])
    return None


def _slice_around_line(python_code: str, lineno: int, context: int = 3) -> str:
    """Return ±context lines around lineno (1-based) with line numbers."""
    code_lines = python_code.splitlines()
    start = max(0, lineno - 1 - context)
    end = min(len(code_lines), lineno - 1 + context + 1)
    result = []
    for i in range(start, end):
        marker = ">>>" if i == lineno - 1 else "   "
        result.append(f"{marker} {i + 1:4d} | {code_lines[i]}")
    return "\n".join(result)


def _slice_for_columns(python_code: str, column_names: list[str]) -> str:
    """Backward program slice: find all lines referencing the given column names.

    Implements a lightweight variant of Weiser-style backward slicing:
    - Parses the translated Python with ``ast``.
    - Walks the AST for subscript (``df['col']``) and attribute (``df.col``)
      access patterns that match any name in *column_names*.
    - Expands each hit by ±2 lines of context.

    Returns an annotated snippet where ``>>>`` marks direct column references.
    Returns empty string if no hits or if the code has a SyntaxError.
    """
    if not column_names or not python_code.strip():
        return ""

    try:
        tree = ast.parse(python_code)
    except SyntaxError:
        return ""

    col_set = {c.lower() for c in column_names}
    hitting_lines: set[int] = set()

    for node in ast.walk(tree):
        # df['col_name']  or  df["col_name"]
        if isinstance(node, ast.Subscript) and hasattr(node, "lineno"):
            sl = node.slice
            # Python 3.9+: slice is directly an ast.Constant
            # Python 3.8:  slice is wrapped in ast.Index
            if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                if sl.value.lower() in col_set:
                    hitting_lines.add(node.lineno)
            elif hasattr(sl, "value") and isinstance(getattr(sl, "value", None), ast.Constant):
                inner = sl.value  # type: ignore[attr-defined]
                if isinstance(inner.value, str) and inner.value.lower() in col_set:
                    hitting_lines.add(node.lineno)

        # df.col_name  (attribute access)
        elif isinstance(node, ast.Attribute) and hasattr(node, "lineno"):
            if node.attr.lower() in col_set:
                hitting_lines.add(node.lineno)

    if not hitting_lines:
        return ""

    code_lines = python_code.splitlines()
    selected: set[int] = set()
    for ln in hitting_lines:
        for offset in range(-2, 3):
            idx = ln - 1 + offset
            if 0 <= idx < len(code_lines):
                selected.add(idx + 1)  # keep 1-based

    result: list[str] = []
    prev: Optional[int] = None
    for ln in sorted(selected):
        if prev is not None and ln > prev + 1:
            result.append("    ...")
        marker = ">>>" if ln in hitting_lines else "   "
        result.append(f"{marker} {ln:4d} | {code_lines[ln - 1]}")
        prev = ln

    return "\n".join(result)


# ── SAS contract extractors ───────────────────────────────────────────────────


def _extract_by_vars(sas_code: str) -> list[str]:
    m = re.search(r"\bby\s+([^;]+);", sas_code, re.IGNORECASE)
    if not m:
        return []
    tokens = re.split(r"\s+", m.group(1).strip())
    return [t.lower() for t in tokens if t and t.lower() != "descending"]


def _extract_keep(sas_code: str) -> list[str]:
    m = re.search(r"\bkeep\s+([^;]+);", sas_code, re.IGNORECASE)
    if not m:
        return []
    return [t.lower() for t in re.split(r"\s+", m.group(1).strip()) if t]


def _extract_merge_type(sas_code: str) -> str:
    """Infer pandas merge how= from SAS IN= flags."""
    has_in_a = bool(re.search(r"\bin=\w+", sas_code, re.IGNORECASE))
    if not has_in_a:
        return "outer"
    if re.search(r"if\s+\w+\s+and\s+\w+", sas_code, re.IGNORECASE):
        return "inner"
    if re.search(r"if\s+\w+\s*;", sas_code, re.IGNORECASE):
        return "left"
    return "outer"


def _extract_output_ds(sas_code: str) -> str:
    """Best-effort extraction of the primary output dataset name."""
    # data <out>; ...
    m = re.match(r"data\s+([A-Za-z0-9_.]+)", sas_code.strip(), re.IGNORECASE)
    if m:
        name = m.group(1).lower()
        if "." in name:
            name = name.split(".", 1)[1]
        return name
    # out= on PROC
    m2 = re.search(r"\bout\s*=\s*([A-Za-z0-9_.]+)", sas_code, re.IGNORECASE)
    if m2:
        return m2.group(1).lower().split(".")[-1]
    return ""


# ── Per-category analysis builders ───────────────────────────────────────────


def _analyse_col_missing(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    affected = report.affected_columns
    col_hint = f"column(s) {affected}" if affected else "missing column(s)"
    by_vars = _extract_by_vars(sas)
    keep_col = _extract_keep(sas)

    # Program slice: show exactly where the missing columns are referenced
    code_slice = _slice_for_columns(py, affected) if affected else ""
    if not code_slice and report.traceback:
        ln = _extract_failing_lineno(report.traceback)
        if ln:
            code_slice = _slice_around_line(py, ln)

    return ErrorAnalysis(
        root_cause=(
            f"The translated code references {col_hint} that do not exist in "
            "the DataFrame. Most likely the columns were not lowercased after loading, "
            "or the wrong input table is being used."
        ),
        non_neg_contract=[
            "All DataFrame column names must be lowercased immediately: "
            "`df.columns = df.columns.str.lower().str.strip()`",
            f"BY variables must be present: {by_vars}" if by_vars else "BY columns must exist",
            (
                f"KEEP columns must be in output: {keep_col}"
                if keep_col
                else "Preserve expected output columns"
            ),
        ],
        forbidden=[
            "Do NOT reload internal DataFrames from disk with pd.read_csv()",
            "Do NOT rename columns to uppercase or mixed-case",
        ],
        repair_strategy=[
            "Add `df.columns = df.columns.str.lower().str.strip()` right after any DataFrame creation",
            (
                f"Replace all references to {affected} with the correct lowercased names"
                if affected
                else "Check each column reference against the actual DataFrame columns"
            ),
            "Verify the correct input DataFrame is being used (not a copy with stale schema)",
        ],
        minimal_scope="Fix only the column access / lowercasing issue.",
        code_slice=code_slice,
    )


def _analyse_dtype(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    affected = report.affected_columns

    # Program slice: locate arithmetic / comparison expressions on these columns
    code_slice = _slice_for_columns(py, affected) if affected else ""
    if not code_slice and report.traceback:
        ln = _extract_failing_lineno(report.traceback)
        if ln:
            code_slice = _slice_around_line(py, ln)

    return ErrorAnalysis(
        root_cause=(
            "A column contains string values (object dtype) where numeric is expected, "
            "or vice versa. Likely causes: currency symbols, commas in numbers, "
            "or SAS character variable mistakenly read as string."
        ),
        non_neg_contract=[
            "Numeric columns must be numeric dtype before arithmetic",
            "Strip all non-numeric characters before conversion",
        ],
        forbidden=[
            "Do NOT use direct `int()` or `float()` cast — they crash on NaN or formatted strings",
        ],
        repair_strategy=[
            "Strip currency/comma formatting: `df['col'] = df['col'].astype(str).str.replace(r'[,$]','', regex=True)`",
            "Convert with coercion: `df['col'] = pd.to_numeric(df['col'], errors='coerce')`",
            "After conversion, check for unexpected NaN rows that indicate format issues",
        ],
        minimal_scope="Fix only the dtype conversion for the failing column(s).",
        code_slice=code_slice,
    )


def _analyse_merge_contract(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    merge_how = _extract_merge_type(sas)
    by_vars = _extract_by_vars(sas)
    return ErrorAnalysis(
        root_cause=(
            f"The join semantics do not match the SAS MERGE contract. "
            f"The SAS code implies a `{merge_how}` join on keys {by_vars or '(check BY statement)'}."
        ),
        non_neg_contract=[
            f"Use `pd.merge(..., how='{merge_how}')` on keys {by_vars}",
            "Sort both DataFrames by BY variables before merging",
            "Preserve the output row order (match SAS DATA step merge output order)",
        ],
        forbidden=[
            "Do NOT use inner join if the SAS code retains unmatched rows",
            "Do NOT drop the _merge indicator columns prematurely if they are used for filtering",
        ],
        repair_strategy=[
            f"Sort left and right DataFrames by {by_vars} before merging",
            f"Use `pd.merge(left, right, on={by_vars}, how='{merge_how}')`",
            "Apply any IN= based row filters AFTER the merge using boolean masks",
            "Drop the indicator column at the end if not needed",
        ],
        minimal_scope="Fix only the merge/join call and any post-merge filtering.",
    )


def _analyse_retain(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    by_vars = _extract_by_vars(sas)
    return ErrorAnalysis(
        root_cause=(
            "RETAIN / running accumulation logic is wrong. "
            "SAS RETAIN keeps the previous row's value and resets at BY-group boundaries. "
            "The current translation does not replicate this behaviour."
        ),
        non_neg_contract=[
            "Accumulation must reset at each BY-group boundary",
            f"BY-group columns: {by_vars}" if by_vars else "Identify the BY grouping column",
        ],
        forbidden=[
            "Do NOT use a Python scalar variable as the accumulator in a loop over rows",
            "Do NOT use .apply() with shared mutable state — it is not vectorised",
        ],
        repair_strategy=[
            (
                f"Sort DataFrame by {by_vars} first"
                if by_vars
                else "Sort by the grouping column first"
            ),
            "Use `df.groupby(by_col)['val'].cumsum()` for simple running totals",
            "For conditional accumulation: use `.groupby().transform(lambda s: ...)` with explicit reset logic",
            "For FIRST./LAST. reset: detect boundary with `df['grp'] != df['grp'].shift(1)`",
        ],
        minimal_scope="Fix only the accumulation / RETAIN logic.",
    )


def _analyse_lag(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    by_vars = _extract_by_vars(sas)
    return ErrorAnalysis(
        root_cause=(
            "LAG / shift semantics are wrong. SAS LAG returns the previous observation's value "
            "within a BY group and initialises to missing on the first row."
        ),
        non_neg_contract=[
            "`LAG(var)` must become `df['var'].shift(1)` (or grouped shift with `groupby`)",
            "The first row in each BY group must be NaN (or the SAS initialisation value)",
        ],
        forbidden=[
            "Do NOT use Python's list indexing `df['var'][i-1]` in a row loop",
        ],
        repair_strategy=[
            "Replace `LAG(var)` with `df['var'].shift(1)`",
            (
                f"For BY-group LAG: `df.groupby({by_vars})['var'].shift(1)`"
                if by_vars
                else "Apply shift within appropriate group if BY is present"
            ),
            "Fill NaN on first row with `np.nan` or the correct SAS initialisation value",
        ],
        minimal_scope="Fix only the LAG/shift translation.",
    )


def _analyse_group_boundary(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    by_vars = _extract_by_vars(sas)
    return ErrorAnalysis(
        root_cause=(
            "FIRST./LAST. group boundary flags are wrong. "
            "FIRST.var is True on the first row of each BY-group value; "
            "LAST.var is True on the last row."
        ),
        non_neg_contract=[
            "DataFrame must be sorted by the BY variable first",
            "FIRST.var: row where value changes from the previous row",
            "LAST.var: row where value changes on the next row",
        ],
        forbidden=[
            "Do NOT use `.groupby().first()` — that aggregates; we need a boolean mask per row",
        ],
        repair_strategy=[
            f"Sort by {by_vars}" if by_vars else "Sort by the grouping column",
            "FIRST.var: `df['first_var'] = df['var'] != df['var'].shift(1)`",
            "LAST.var:  `df['last_var']  = df['var'] != df['var'].shift(-1)`",
            "Set first row of FIRST and last row of LAST to True unconditionally (boundary rows)",
        ],
        minimal_scope="Fix only the FIRST./LAST. boundary flag generation.",
    )


def _analyse_output_missing(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    out_ds = _extract_output_ds(sas)
    return ErrorAnalysis(
        root_cause=(
            "The translated code does not produce a named output DataFrame. "
            "The final result must be stored in a top-level variable (not inside a function)."
        ),
        non_neg_contract=[
            (
                f"The final output must be assigned to `{out_ds}`"
                if out_ds
                else "The final output must be a named DataFrame variable"
            ),
            "The script must be FLAT — no `def main()` or wrapper functions",
        ],
        forbidden=[
            "Do NOT wrap the output assignment inside any function",
            "Do NOT use `return` — this is a script, not a function",
        ],
        repair_strategy=[
            "Identify the last transformation in the SAS code",
            (
                f"Ensure the result is assigned to `{out_ds}` at the top level"
                if out_ds
                else "Assign the final DataFrame to a clearly named top-level variable"
            ),
            "Remove any function wrapper (`def main()`, `def process()`, etc.)",
        ],
        minimal_scope="Add or fix the final output variable assignment.",
    )


def _analyse_sort_order(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    by_vars = _extract_by_vars(sas)
    return ErrorAnalysis(
        root_cause=(
            "The output is sorted in the wrong order. SAS PROC SORT uses a stable "
            "sort; the BY statement may include DESCENDING prefixes."
        ),
        non_neg_contract=[
            (
                f"Sort by {by_vars} in the correct direction"
                if by_vars
                else "Sort by the correct BY columns"
            ),
            "Use `kind='mergesort'` for stable sort",
        ],
        forbidden=[
            "Do NOT use default quicksort (`kind='quicksort'`) when stable order matters",
        ],
        repair_strategy=[
            f"Use `df.sort_values(by={by_vars}, ascending=[...], kind='mergesort')`",
            "Set `ascending=False` for DESCENDING columns",
            "Call `.reset_index(drop=True)` after sorting",
        ],
        minimal_scope="Fix only the sort call.",
    )


def _analyse_empty(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    return ErrorAnalysis(
        root_cause=(
            "The output DataFrame is empty when it should contain rows. "
            "The most common cause is an overly strict filter, especially when "
            "SAS missing values (`.`) are compared differently than pandas NaN."
        ),
        non_neg_contract=[
            "Preserve rows that would survive the SAS WHERE / IF condition",
        ],
        forbidden=[
            "Do NOT use `df.dropna()` on the entire DataFrame — it removes all rows with any NaN",
            "Do NOT compare NaN with `== np.nan` — use `pd.isna()` instead",
        ],
        repair_strategy=[
            "Check each filter condition: SAS `. < 0` is TRUE (missing < 0), pandas is not",
            "Replace `df[df['col'] != '']` with `df[df['col'].notna() & (df['col'] != '')]`",
            "Use `pd.isna()` / `pd.notna()` for missing-value guards",
            "If using `.dropna()`, pass `subset=['specific_col']` not the whole frame",
        ],
        minimal_scope="Fix only the filtering / missing-value comparison logic.",
    )


# ── Generic fallbacks ─────────────────────────────────────────────────────────


def _analyse_generic(report: ErrorReport, sas: str, py: str) -> ErrorAnalysis:
    # Attempt line-based slice from traceback when column names are unavailable
    code_slice = ""
    if report.traceback:
        ln = _extract_failing_lineno(report.traceback)
        if ln:
            code_slice = _slice_around_line(py, ln)

    return ErrorAnalysis(
        root_cause=(f"{report.primary_category}: {report.error_message}"),
        non_neg_contract=[
            "The output must match the SAS dataset semantics (rows, columns, values)",
        ],
        forbidden=[
            "Do NOT wrap code in `def main()` or any function",
            "Do NOT reload internal DataFrames from disk",
        ],
        repair_strategy=[
            "Read the full traceback and identify the exact failing line",
            "Fix only the failing operation without changing unrelated logic",
            report.repair_hint,
        ],
        minimal_scope="Fix only the failing section.",
        code_slice=code_slice,
    )


# ── Dispatch map ─────────────────────────────────────────────────────────────

_DISPATCH: dict[str, object] = {
    COL_MISSING: _analyse_col_missing,
    KEY_ERROR: _analyse_col_missing,
    DTYPE_MISMATCH: _analyse_dtype,
    TYPE_ERROR: _analyse_dtype,
    VALUE_ERROR: _analyse_dtype,
    MERGE_CONTRACT: _analyse_merge_contract,
    RETAIN_SEQUENCE: _analyse_retain,
    LAG_SEQUENCE: _analyse_lag,
    GROUP_BOUNDARY: _analyse_group_boundary,
    OUTPUT_MISSING: _analyse_output_missing,
    SORT_ORDER: _analyse_sort_order,
    EMPTY_SUSPICIOUS: _analyse_empty,
}


def analyse_error(
    report: ErrorReport,
    sas_code: str = "",
    python_code: str = "",
    partition_type: str = "",
) -> ErrorAnalysis:
    """Produce a structured error analysis from an ErrorReport.

    Falls back to a generic analysis if no specific handler exists.
    """
    handler = _dispatch(report.primary_category)
    try:
        analysis = handler(report, sas_code, python_code)
    except Exception:
        analysis = _analyse_generic(report, sas_code, python_code)

    # Always append partition_type specific note
    if partition_type in ("MACRO_DEFINITION", "MACRO_INVOCATION"):
        analysis.non_neg_contract.append(
            "This is a macro block — `def` is acceptable ONLY if the macro "
            "is called more than once. Otherwise expand inline."
        )
    elif partition_type == "SQL_BLOCK":
        analysis.non_neg_contract.append(
            "Translate PROC SQL to pandas operations. "
            "Do NOT use `pd.read_sql()` for internal tables."
        )

    return analysis


def _dispatch(category: str):
    return _DISPATCH.get(category, _analyse_generic)
