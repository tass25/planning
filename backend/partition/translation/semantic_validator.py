"""semantic_validator.py — Oracle-based semantic correctness validator.

Validates translated Python WITHOUT relying on a SAS runtime.
Computes expected output from SAS semantics directly in pandas,
then diffs against the actual translated code's output.

Catches the class of bugs that sandbox exec misses:
  "it runs, but produces the wrong answer."

Supported oracle patterns (triggered by SAS keyword detection):
  - PROC SORT   → stable sort by BY vars, optional NODUPKEY
  - PROC MEANS  → groupby aggregation (SUM/MEAN/N/MIN/MAX + OUTPUT OUT=)
  - PROC FREQ   → value_counts with percent
  - MERGE (DATA step) → join type inferred from IN=/IF pattern
  - RETAIN      → cumsum per group with FIRST.-reset
  - LAG         → shift(1) with optional BY-group null reset
  - FIRST./LAST. → group boundary row filter
  - Simple filter DATA step → WHERE/IF condition check

Architecture:
  SemanticValidator.validate(partition, python_code)
    1. DummyDataGenerator generates adversarial input frames
    2. _exec_with_inputs() runs the Python with those inputs → actual outputs
    3. _compute_oracle()  derives expected outputs from SAS semantics
    4. _compare()         diffs oracle vs actual, returns SemanticValidationResult
"""

from __future__ import annotations

import ast
import re
import threading
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import structlog

from partition.models.partition_ir import PartitionIR
from partition.translation.dummy_data_generator import DummyDataGenerator

logger = structlog.get_logger()

_EXEC_TIMEOUT_S = 5.0          # max seconds to run translated Python for semantic check
_COMPARE_TOL    = 1e-4         # float comparison tolerance
_MAX_ROWS_SHOWN = 5            # rows shown in repair hint diff

# ── result type ───────────────────────────────────────────────────────────────

@dataclass
class SemanticValidationResult:
    passed:      bool
    error_type:  str = ""
    details:     list[str] = field(default_factory=list)
    oracle_repr: str = ""     # first N rows of expected DataFrame
    actual_repr: str = ""     # first N rows of actual DataFrame

    def to_repair_hint(self) -> str:
        """Render as a Markdown block for injection into the repair LLM prompt."""
        if self.passed:
            return ""
        lines = [
            "## Semantic Oracle Failure — Wrong Answer (not a crash)",
            f"**Error type**: `{self.error_type}`",
        ]
        for d in self.details:
            if d:
                lines.append(f"- {d}")
        if self.oracle_repr:
            lines.append(f"\n**Expected output (oracle)**:\n```\n{self.oracle_repr}\n```")
        if self.actual_repr:
            lines.append(f"\n**Actual output**:\n```\n{self.actual_repr}\n```")
        lines.append(
            "\nThe code ran without error but produced the WRONG result. "
            "Fix the semantic logic — do NOT change imports or unrelated code."
        )
        return "\n".join(lines)


# ── SAS regex helpers ─────────────────────────────────────────────────────────

def _by_cols(sas: str) -> list[str]:
    m = re.search(r"\bby\s+([^;/\n]+?)(?:;|$)", sas, re.IGNORECASE)
    if not m:
        return []
    return [t.strip().lower() for t in m.group(1).split() if t.strip()]


def _var_cols(sas: str) -> list[str]:
    m = re.search(r"\bvar\s+([^;]+);", sas, re.IGNORECASE)
    if not m:
        return []
    return [t.strip().lower() for t in m.group(1).split() if t.strip()]


def _class_cols(sas: str) -> list[str]:
    m = re.search(r"\bclass\s+([^;]+);", sas, re.IGNORECASE)
    if not m:
        return []
    return [t.strip().lower() for t in m.group(1).split() if t.strip()]


def _output_name(sas: str) -> Optional[str]:
    """First DATA <name> or OUT=<name> in the SAS code."""
    m = re.search(r"^\s*data\s+([\w.]+)", sas, re.IGNORECASE | re.MULTILINE)
    if m:
        return m.group(1).split(".")[-1].lower()
    m = re.search(r"\bout\s*=\s*([\w.]+)", sas, re.IGNORECASE)
    if m:
        return m.group(1).split(".")[-1].lower()
    return None


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase columns, reset index."""
    d = df.copy()
    d.columns = [str(c).lower() for c in d.columns]
    return d.reset_index(drop=True)


def _coerce_numeric(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        return pd.to_numeric(
            series.astype(str).str.replace(r"[$,]", "", regex=True),
            errors="coerce",
        )
    return pd.to_numeric(series, errors="coerce")


def _df_repr(df: Optional[pd.DataFrame], n: int = _MAX_ROWS_SHOWN) -> str:
    if df is None or df.empty:
        return "<empty>"
    return df.head(n).to_string(index=False)


# ── frame comparison ──────────────────────────────────────────────────────────

def _compare_frames(
    oracle: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    sort_cols: Optional[list[str]] = None,
    check_order: bool = False,
    tol: float = _COMPARE_TOL,
) -> tuple[bool, list[str]]:
    """Return (match, details).  details is empty when match=True."""
    oracle = _normalize(oracle)
    actual = _normalize(actual)

    # Row count
    if len(oracle) != len(actual):
        return False, [
            f"Row count mismatch: oracle={len(oracle)}, actual={len(actual)}"
        ]

    # Column presence
    missing = [c for c in oracle.columns if c not in actual.columns]
    extra   = [c for c in actual.columns  if c not in oracle.columns]
    if missing:
        return False, [f"Missing columns in output: {missing}"]
    if extra:
        return False, [f"Unexpected extra columns in output: {extra}"]

    # Sort if needed
    common = [c for c in oracle.columns if c in actual.columns]
    if sort_cols:
        sc = [c for c in sort_cols if c in oracle.columns and c in actual.columns]
        if sc:
            oracle = oracle.sort_values(sc, kind="mergesort").reset_index(drop=True)
            actual = actual.sort_values(sc, kind="mergesort").reset_index(drop=True)
    elif not check_order:
        oracle = oracle.sort_values(common, kind="mergesort").reset_index(drop=True)
        actual = actual.sort_values(common, kind="mergesort").reset_index(drop=True)

    # Value comparison column by column
    for col in common:
        o_col = oracle[col]
        a_col = actual[col]
        try:
            o_num = _coerce_numeric(o_col)
            a_num = _coerce_numeric(a_col)
            if o_num.notna().any() and a_num.notna().any():
                if not np.allclose(
                    o_num.fillna(0), a_num.fillna(0),
                    atol=tol, rtol=tol, equal_nan=False,
                ):
                    return False, [
                        f"Column `{col}` values differ.",
                        f"  oracle sample : {o_num.head(3).tolist()}",
                        f"  actual sample : {a_num.head(3).tolist()}",
                    ]
                continue
        except Exception:
            pass
        if not o_col.astype(str).reset_index(drop=True).equals(
            a_col.astype(str).reset_index(drop=True)
        ):
            return False, [
                f"Column `{col}` string values differ.",
                f"  oracle sample : {o_col.head(3).tolist()}",
                f"  actual sample : {a_col.head(3).tolist()}",
            ]

    return True, []


# ── oracle computations ───────────────────────────────────────────────────────

def _oracle_proc_sort(
    sas: str,
    frames: dict[str, pd.DataFrame],
) -> Optional[dict[str, pd.DataFrame]]:
    if not re.search(r"\bproc\s+sort\b", sas, re.IGNORECASE):
        return None
    by = _by_cols(sas)
    if not by:
        return None
    # Find input table (DATA= or first table in BY context)
    m_data = re.search(r"\bdata\s*=\s*([\w.]+)", sas, re.IGNORECASE)
    m_out  = re.search(r"\bout\s*=\s*([\w.]+)", sas, re.IGNORECASE)
    in_name  = m_data.group(1).split(".")[-1].lower() if m_data else None
    out_name = m_out.group(1).split(".")[-1].lower() if m_out else None

    input_df = None
    if in_name and in_name in frames:
        input_df = _normalize(frames[in_name])
    if input_df is None and frames:
        input_df = _normalize(next(iter(frames.values())))
    if input_df is None:
        return None

    valid_by = [c for c in by if c in input_df.columns]
    if not valid_by:
        return None

    result = input_df.sort_values(valid_by, ascending=True, kind="mergesort").reset_index(drop=True)
    if re.search(r"\bnodupkey\b", sas, re.IGNORECASE):
        result = result.drop_duplicates(subset=valid_by, keep="first").reset_index(drop=True)

    key = out_name or (in_name or "output")
    return {key: result}


def _oracle_proc_means(
    sas: str,
    frames: dict[str, pd.DataFrame],
) -> Optional[dict[str, pd.DataFrame]]:
    if not re.search(r"\bproc\s+means\b", sas, re.IGNORECASE):
        return None
    if not re.search(r"\boutput\s+out\s*=", sas, re.IGNORECASE):
        return None

    class_c = _class_cols(sas)
    var_c   = _var_cols(sas)

    input_df = None
    if frames:
        input_df = _normalize(next(iter(frames.values())))
    if input_df is None or not var_c:
        return None

    # Parse OUTPUT OUT= spec
    output_spec_m = re.search(
        r"\boutput\s+out\s*=\s*[\w.]+\s+(.*?);",
        sas, re.IGNORECASE | re.DOTALL,
    )
    out_name_m = re.search(r"\boutput\s+out\s*=\s*([\w.]+)", sas, re.IGNORECASE)
    out_name = out_name_m.group(1).split(".")[-1].lower() if out_name_m else "output"

    # Parse stat=alias mappings
    stats_map: list[tuple[str, list[str]]] = []  # [(stat, [alias1, alias2, ...])]
    if output_spec_m:
        body = output_spec_m.group(1)
        for stat_m in re.finditer(
            r"\b(sum|mean|n|min|max)\s*=\s*(.+?)(?=\s+\b(?:sum|mean|n|min|max)\b\s*=|$)",
            body, re.IGNORECASE | re.DOTALL,
        ):
            aliases = re.findall(r"[A-Za-z_]\w*", stat_m.group(2))
            stats_map.append((stat_m.group(1).lower(), [a.lower() for a in aliases]))

    if not stats_map:
        stats_map = [("n", ["_freq_"])]

    # numeric coercion for var columns
    work = input_df.copy()
    valid_var = [c for c in var_c if c in work.columns]
    for c in valid_var:
        work[c] = _coerce_numeric(work[c])

    valid_class = [c for c in class_c if c in work.columns]

    if valid_class:
        grouped = work.groupby(valid_class, dropna=False, sort=False)
        result  = grouped.size().reset_index(name="_freq_")
        result["_type_"] = (2 ** len(valid_class)) - 1
        for stat, aliases in stats_map:
            for idx, vc in enumerate(valid_var):
                alias = aliases[idx] if idx < len(aliases) else f"{vc}_{stat}"
                if stat == "sum":
                    vals = grouped[vc].sum(min_count=1).reset_index(name=alias)
                elif stat == "mean":
                    vals = grouped[vc].mean().reset_index(name=alias)
                elif stat == "n":
                    vals = grouped[vc].count().reset_index(name=alias)
                elif stat == "min":
                    vals = grouped[vc].min().reset_index(name=alias)
                else:
                    vals = grouped[vc].max().reset_index(name=alias)
                result = result.merge(vals, on=valid_class, how="left")
    else:
        result = pd.DataFrame({"_type_": [0], "_freq_": [len(work)]})
        for stat, aliases in stats_map:
            for idx, vc in enumerate(valid_var):
                alias = aliases[idx] if idx < len(aliases) else f"{vc}_{stat}"
                s = work[vc] if vc in work.columns else pd.Series(dtype="float64")
                if stat == "sum":
                    result[alias] = [s.sum(min_count=1)]
                elif stat == "mean":
                    result[alias] = [s.mean()]
                elif stat == "n":
                    result[alias] = [s.count()]
                elif stat == "min":
                    result[alias] = [s.min()]
                else:
                    result[alias] = [s.max()]

    return {out_name: result}


def _oracle_proc_freq(
    sas: str,
    frames: dict[str, pd.DataFrame],
) -> Optional[dict[str, pd.DataFrame]]:
    if not re.search(r"\bproc\s+freq\b", sas, re.IGNORECASE):
        return None
    if not re.search(r"/\s*out\s*=", sas, re.IGNORECASE):
        return None

    table_m = re.search(r"\btables\s+([A-Za-z_]\w*)", sas, re.IGNORECASE)
    out_m   = re.search(r"/.*?out\s*=\s*([\w.]+)", sas, re.IGNORECASE)
    if not table_m:
        return None

    freq_col = table_m.group(1).lower()
    out_name = out_m.group(1).split(".")[-1].lower() if out_m else "freq_out"

    input_df = None
    if frames:
        input_df = _normalize(next(iter(frames.values())))
    if input_df is None or freq_col not in input_df.columns:
        return None

    include_missing = bool(re.search(r"\bmissing\b", sas, re.IGNORECASE))
    counts = (
        input_df[freq_col]
        .value_counts(dropna=not include_missing)
        .reset_index()
    )
    counts.columns = [freq_col, "count"]
    counts["percent"] = (counts["count"] / counts["count"].sum() * 100).round(2)
    return {out_name: counts}


def _oracle_retain(
    sas: str,
    frames: dict[str, pd.DataFrame],
) -> Optional[dict[str, pd.DataFrame]]:
    if not re.search(r"\bretain\b", sas, re.IGNORECASE):
        return None

    # Parse SUM statements: total + amount;  or  total = total + amount;
    sum_specs: list[tuple[str, str]] = []
    for m in re.finditer(
        r"^\s*([A-Za-z_]\w*)\s*\+\s*([A-Za-z_]\w*|\d+(?:\.\d+)?)\s*;",
        sas, re.IGNORECASE | re.MULTILINE,
    ):
        sum_specs.append((m.group(1).lower(), m.group(2).lower()))
    for m in re.finditer(
        r"^\s*([A-Za-z_]\w*)\s*=\s*\1\s*\+\s*([A-Za-z_]\w*|\d+(?:\.\d+)?)\s*;",
        sas, re.IGNORECASE | re.MULTILINE,
    ):
        spec = (m.group(1).lower(), m.group(2).lower())
        if spec not in sum_specs:
            sum_specs.append(spec)

    if not sum_specs:
        return None

    by = _by_cols(sas)
    input_df = None
    if frames:
        input_df = _normalize(next(iter(frames.values())))
    if input_df is None:
        return None

    reset_on_first = bool(
        re.search(r"\bif\s+first\.\w+\s+then\s+do\s*;", sas, re.IGNORECASE)
        or re.search(r"\bif\s+first\.\w+\s+then\s+[A-Za-z_]\w+\s*=\s*(?:0|\.)", sas, re.IGNORECASE)
    )
    keep_first = bool(re.search(r"\bif\s+first\.\w+\s*;|\bif\s+first\.\w+\s+then\s+output\b", sas, re.IGNORECASE))
    keep_last  = bool(re.search(r"\bif\s+last\.\w+\s*;|\bif\s+last\.\w+\s+then\s+output\b", sas, re.IGNORECASE))

    work = input_df.copy()
    valid_by = [c for c in by if c in work.columns]

    for target, operand in sum_specs:
        if operand in work.columns:
            op_series = _coerce_numeric(work[operand]).fillna(0)
        else:
            try:
                op_series = pd.Series([float(operand)] * len(work), index=work.index)
            except ValueError:
                continue

        if valid_by and reset_on_first:
            work[target] = op_series.groupby(
                [work[c] for c in valid_by], dropna=False, sort=False
            ).cumsum()
        else:
            work[target] = op_series.cumsum()

    if keep_first and valid_by:
        work = work.loc[work.groupby(valid_by, dropna=False, sort=False).cumcount() == 0].copy()
    if keep_last and valid_by:
        last_mask = work.iloc[::-1].groupby(
            [work[c] for c in valid_by], dropna=False, sort=False
        ).cumcount().iloc[::-1] == 0
        work = work.loc[last_mask].copy()

    out_name = _output_name(sas) or "output"
    return {out_name: work.reset_index(drop=True)}


def _oracle_lag(
    sas: str,
    frames: dict[str, pd.DataFrame],
) -> Optional[dict[str, pd.DataFrame]]:
    m = re.search(
        r"\b([A-Za-z_]\w*)\s*=\s*lag\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;",
        sas, re.IGNORECASE,
    )
    if not m:
        return None

    target_col = m.group(1).lower()
    source_col = m.group(2).lower()
    by = _by_cols(sas)

    input_df = None
    if frames:
        input_df = _normalize(next(iter(frames.values())))
    if input_df is None or source_col not in input_df.columns:
        return None

    work = input_df.copy()
    work[target_col] = work[source_col].shift(1)

    # Reset at group boundaries if first. reset pattern present
    valid_by = [c for c in by if c in work.columns]
    if valid_by and re.search(
        rf"\bif\s+first\.\w+\s+then\s+{re.escape(target_col)}\s*=\s*\.",
        sas, re.IGNORECASE,
    ):
        first_mask = work.groupby(valid_by, dropna=False, sort=False).cumcount() == 0
        work.loc[first_mask, target_col] = np.nan

    out_name = _output_name(sas) or "output"
    return {out_name: work.reset_index(drop=True)}


def _oracle_first_last(
    sas: str,
    frames: dict[str, pd.DataFrame],
) -> Optional[dict[str, pd.DataFrame]]:
    if not re.search(r"\bfirst\.\w+|\blast\.\w+", sas, re.IGNORECASE):
        return None
    if re.search(r"\bretain\b|\blag\s*\(", sas, re.IGNORECASE):
        return None   # handled by _oracle_retain/_oracle_lag

    by = _by_cols(sas)
    if not by:
        return None

    keep_first = bool(
        re.search(r"\bif\s+first\.\w+\s*;|\bif\s+first\.\w+\s+then\s+output\b", sas, re.IGNORECASE)
    )
    keep_last  = bool(
        re.search(r"\bif\s+last\.\w+\s*;|\bif\s+last\.\w+\s+then\s+output\b", sas, re.IGNORECASE)
    )
    if not keep_first and not keep_last:
        return None

    input_df = None
    if frames:
        input_df = _normalize(next(iter(frames.values())))
    if input_df is None:
        return None

    valid_by = [c for c in by if c in input_df.columns]
    if not valid_by:
        return None

    first_mask = input_df.groupby(valid_by, dropna=False, sort=False).cumcount() == 0
    last_mask  = (
        input_df.iloc[::-1]
        .groupby([input_df[c] for c in valid_by], dropna=False, sort=False)
        .cumcount().iloc[::-1] == 0
    )
    mask = pd.Series(False, index=input_df.index)
    if keep_first:
        mask |= first_mask
    if keep_last:
        mask |= last_mask

    out_name = _output_name(sas) or "output"
    return {out_name: input_df.loc[mask].reset_index(drop=True)}


def _oracle_merge(
    sas: str,
    frames: dict[str, pd.DataFrame],
) -> Optional[dict[str, pd.DataFrame]]:
    if not re.search(r"\bmerge\b", sas, re.IGNORECASE):
        return None

    merge_m = re.search(r"\bmerge\s+(.+?);", sas, re.IGNORECASE | re.DOTALL)
    if not merge_m:
        return None

    sources = re.findall(
        r"([\w.]+)(?:\s*\(\s*in\s*=\s*([A-Za-z_]\w*)\s*\))?",
        merge_m.group(1), re.IGNORECASE,
    )
    if len(sources) < 2:
        return None

    left_name  = sources[0][0].split(".")[-1].lower()
    right_name = sources[1][0].split(".")[-1].lower()
    left_alias = (sources[0][1] or "").lower()
    right_alias= (sources[1][1] or "").lower()
    by = _by_cols(sas)

    left_df  = _normalize(frames.get(left_name, pd.DataFrame()))
    right_df = _normalize(frames.get(right_name, pd.DataFrame()))
    if left_df.empty or right_df.empty or not by:
        return None

    valid_by = [c for c in by if c in left_df.columns and c in right_df.columns]
    if not valid_by:
        return None

    # Detect join type from IF <alias> pattern
    if_m = re.search(r"\bif\s+([^;]+);", sas, re.IGNORECASE)
    if_expr = if_m.group(1).strip().lower() if if_m else ""
    if "then" in if_expr:
        if_expr = ""

    how = "outer"
    if left_alias and if_expr == left_alias:
        how = "left"
    elif right_alias and if_expr == right_alias:
        how = "right"
    elif left_alias and right_alias and if_expr in {
        f"{left_alias} and {right_alias}", f"{right_alias} and {left_alias}"
    }:
        how = "inner"

    result = left_df.merge(right_df, on=valid_by, how=how, sort=False, suffixes=("_x", "_y"))
    out_name = _output_name(sas) or "output"
    return {out_name: result.reset_index(drop=True)}


# ── translated Python executor ────────────────────────────────────────────────

def _exec_with_inputs(
    python_code: str,
    input_frames: dict[str, pd.DataFrame],
    expected_output_names: list[str],
    timeout_s: float = _EXEC_TIMEOUT_S,
) -> Optional[dict[str, pd.DataFrame]]:
    """Run translated Python with specific input DataFrames injected.

    Returns dict of {name: DataFrame} for any DataFrames in the namespace
    whose names match expected_output_names.  Returns None on timeout/crash.
    """
    namespace: dict = {
        "pd": pd,
        "np": np,
        "__builtins__": {
            k: v for k, v in __builtins__.items()  # type: ignore[union-attr]
            if k not in {"open", "__import__", "exec", "eval", "compile",
                         "exit", "quit", "input", "breakpoint"}
        } if isinstance(__builtins__, dict) else __builtins__,
    }
    # Inject input frames under their names and common aliases
    for name, df in input_frames.items():
        namespace[name] = df.copy()
        # Also inject as df / df_in for generic code
        if "df" not in namespace:
            namespace["df"] = df.copy()
        if "df_in" not in namespace:
            namespace["df_in"] = df.copy()

    result_holder: list[Optional[dict[str, pd.DataFrame]]] = [None]
    error_holder:  list[str] = []

    def _run() -> None:
        try:
            exec(python_code, namespace)  # noqa: S102
            outputs: dict[str, pd.DataFrame] = {}
            for name in expected_output_names:
                if name in namespace and isinstance(namespace[name], pd.DataFrame):
                    outputs[name] = namespace[name].copy()
            # Fallback: any DataFrame not in inputs
            if not outputs:
                for k, v in namespace.items():
                    if (
                        isinstance(v, pd.DataFrame)
                        and k not in input_frames
                        and not k.startswith("_")
                        and k not in ("pd", "np", "df", "df_in")
                    ):
                        outputs[k] = v.copy()
            result_holder[0] = outputs
        except Exception as exc:
            error_holder.append(str(exc))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        return None   # timed out
    if error_holder:
        return None   # crashed — already caught by ValidationAgent
    return result_holder[0]


# ── main class ────────────────────────────────────────────────────────────────

class SemanticValidator:
    """Oracle-based semantic correctness check for translated SAS partitions.

    Called AFTER ValidationAgent (syntax + exec pass).  Generates adversarial
    dummy data, runs the translated Python with it, computes the oracle, diffs.
    """

    # Oracle functions in priority order — first match wins
    _ORACLES = [
        _oracle_proc_sort,
        _oracle_proc_means,
        _oracle_proc_freq,
        _oracle_retain,
        _oracle_lag,
        _oracle_first_last,
        _oracle_merge,
    ]

    def validate(
        self,
        partition: PartitionIR,
        python_code: str,
    ) -> SemanticValidationResult:
        """Run oracle check for one partition.

        Returns SemanticValidationResult(passed=True) when:
          - no oracle applies to this SAS pattern, or
          - the translated Python output matches the oracle.
        """
        sas_code = partition.source_code or ""

        try:
            # 1. Generate adversarial inputs
            gen        = DummyDataGenerator(sas_code=sas_code)
            input_frames = gen.generate()
            out_names  = gen.output_table_names()

            # 2. Compute oracle (first applicable pattern)
            oracle_frames: Optional[dict[str, pd.DataFrame]] = None
            for oracle_fn in self._ORACLES:
                try:
                    oracle_frames = oracle_fn(sas_code, input_frames)
                    if oracle_frames is not None:
                        break
                except Exception as exc:
                    logger.debug("oracle_fn_error", fn=oracle_fn.__name__, error=str(exc))

            if oracle_frames is None:
                # No oracle available for this pattern — skip
                return SemanticValidationResult(passed=True)

            # 3. Run translated Python with injected inputs
            actual_frames = _exec_with_inputs(
                python_code, input_frames, out_names or list(oracle_frames.keys())
            )
            if actual_frames is None:
                # Crashed or timed out — ValidationAgent already handles this
                return SemanticValidationResult(passed=True)

            # 4. Compare oracle vs actual for each expected output
            for out_name, oracle_df in oracle_frames.items():
                actual_df = (
                    actual_frames.get(out_name)
                    or (next(iter(actual_frames.values())) if actual_frames else None)
                )
                if actual_df is None:
                    return SemanticValidationResult(
                        passed=False,
                        error_type="OUTPUT_MISSING",
                        details=[
                            f"Expected output table `{out_name}` was not produced.",
                            "The code ran without error but created no output DataFrame.",
                        ],
                        oracle_repr=_df_repr(oracle_df),
                        actual_repr="<no DataFrame found in namespace>",
                    )

                matched, details = _compare_frames(
                    oracle_df, actual_df,
                    sort_cols=_by_cols(sas_code) or None,
                    check_order=bool(re.search(r"\bproc\s+sort\b", sas_code, re.IGNORECASE)),
                )
                if not matched:
                    # Determine error type from context
                    error_type = _classify_semantic_error(sas_code, details)
                    return SemanticValidationResult(
                        passed=False,
                        error_type=error_type,
                        details=details,
                        oracle_repr=_df_repr(oracle_df),
                        actual_repr=_df_repr(actual_df),
                    )

            return SemanticValidationResult(passed=True)

        except Exception as exc:
            logger.warning("semantic_validator_error", error=str(exc))
            return SemanticValidationResult(passed=True)   # fail open


def _classify_semantic_error(sas_code: str, details: list[str]) -> str:
    """Map SAS pattern + diff details to a named error type."""
    sas_lower = sas_code.lower()
    detail_str = " ".join(details).lower()

    if "row count" in detail_str:
        if re.search(r"\bproc\s+sort\b", sas_code, re.IGNORECASE):
            return "SORT_ROWCOUNT_WRONG"
        if re.search(r"\bmerge\b", sas_code, re.IGNORECASE):
            return "MERGE_CONTRACT_WRONG"
        if re.search(r"\bfirst\.\w+|\blast\.\w+", sas_code, re.IGNORECASE):
            return "GROUP_BOUNDARY_WRONG"
    if re.search(r"\bretain\b", sas_code, re.IGNORECASE):
        return "RETAIN_SEQUENCE_WRONG"
    if re.search(r"\blag\s*\(", sas_code, re.IGNORECASE):
        return "LAG_SEQUENCE_WRONG"
    if re.search(r"\bproc\s+sort\b", sas_code, re.IGNORECASE):
        return "SORT_ORDER_WRONG"
    if re.search(r"\bproc\s+means\b", sas_code, re.IGNORECASE):
        return "AGGREGATION_WRONG"
    if re.search(r"\bproc\s+freq\b", sas_code, re.IGNORECASE):
        return "FREQ_COUNT_WRONG"
    if re.search(r"\bmerge\b", sas_code, re.IGNORECASE):
        return "MERGE_RESULT_WRONG"
    if "missing" in detail_str or "column" in detail_str:
        return "COLUMN_MISMATCH"
    return "SEMANTIC_WRONG"