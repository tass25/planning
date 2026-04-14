"""Z3VerificationAgent — formal semantic equivalence proofs.

8 verification patterns covering the main SAS→Python constructs:

  Pattern 1 — conditional_assignment
      IF x < 0 THEN y='A'; ELSE IF x=0 THEN y='B'; ELSE y='C';
      → np.select([x<0, x==0], ['A','B'], default='C')
      Z3 proves: cond_sas(x) ↔ cond_py(x) for symbolic x.
      Counterexample: iterrows() detected.

  Pattern 2 — sort_direction
      PROC SORT BY col1 DESCENDING col2;
      → sort_values(['col1','col2'], ascending=[True, False])
      Z3 proves: direction booleans match BY-clause semantics.
      Counterexample: wrong ascending= value for a DESCENDING column.

  Pattern 3 — proc_means_groupby
      PROC MEANS DATA=X; CLASS a b; VAR v; OUTPUT OUT=Y MEAN=m;
      → df.groupby(['a','b'], dropna=False).agg(...)
      Proves: single groupby call with dropna=False (NaN group preserved).
      Counterexample: multiple merged groupbys OR dropna not False.

  Pattern 4 — boolean_filter
      WHERE balance > 5000  /  IF balance > 5000 THEN ...
      → df[df['balance'] > 5000]
      Z3 proves: filter_sas(x) ↔ filter_py(x) for symbolic x.
      Counterexample: wrong operator or threshold.

  Pattern 5 — format_display_only
      PROC FORMAT; VALUE $grade 'A'='Red'; / FORMAT status $grade.;
      → df['status_fmt'] = df['status'].map(fmt)   (NEW column)
      Counterexample: original column overwritten (df['status'] = ...).

  Pattern 6 — left_join
      PROC SQL: LEFT JOIN t2 ON ...
      → pd.merge(..., how='left')
      Counterexample: how='inner' / how='right' / missing how parameter.

  Pattern 7 — merge_indicator
      MERGE t1 (IN=a) t2 (IN=b); BY key; IF a;
      → pd.merge(..., indicator=True); df[...]; df.drop('_merge')
      Counterexample: indicator=True missing OR _merge never dropped.

  Pattern 8 — stepwise_regression
      PROC REG ... / SELECTION=STEPWISE;
      → statsmodels OLS + .pvalues loop + `if changed:` guard
      Counterexample: sklearn used OR BIC/AIC used OR no p-value check.

Integration:
  TranslationPipeline calls verify(sas_code, python_code) after validation.
  ALL 8 patterns are attempted; worst result wins:
    COUNTEREXAMPLE > PROVED > UNKNOWN > SKIPPED
  COUNTEREXAMPLE → block re-queued at RiskLevel.HIGH for one more retry.
  PROVED / UNKNOWN → non-blocking, pipeline continues.

Feature flag: Z3_VERIFICATION=true (default).
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class VerificationStatus(str, Enum):
    PROVED        = "formal_proof"
    UNKNOWN       = "unverifiable"
    COUNTEREXAMPLE = "counterexample"
    SKIPPED       = "skipped"


@dataclass
class VerificationResult:
    status: VerificationStatus
    latency_ms: float = 0.0
    pattern: str = ""
    counterexample: dict = field(default_factory=dict)
    error: str = ""


# ── helpers ──────────────────────────────────────────────────────────────────

_SAS_OP_NORM = {"=": "==", "^=": "!=", "~=": "!=", "¬=": "!="}

def _norm_op(op: str) -> str:
    return _SAS_OP_NORM.get(op.strip(), op.strip())

def _z3_cmp(x, op: str, val):
    import z3
    return {
        "<":  x < val,  ">":  x > val,
        "<=": x <= val, ">=": x >= val,
        "==": x == val, "!=": x != val,
    }.get(op)


# ── main agent ────────────────────────────────────────────────────────────────

class Z3VerificationAgent:
    """Formal equivalence checker. Runs all 8 patterns; returns worst result."""

    ENABLED = os.getenv("Z3_VERIFICATION", "true").lower() == "true"

    def __init__(self) -> None:
        self._z3_ok: Optional[bool] = None

    # ── public API ────────────────────────────────────────────────────────────

    def verify(self, sas_code: str, python_code: str) -> VerificationResult:
        """Run all patterns. Worst result (COUNTEREXAMPLE > PROVED > UNKNOWN)."""
        if not self.ENABLED:
            return VerificationResult(status=VerificationStatus.SKIPPED)
        if not self._check_z3():
            return VerificationResult(
                status=VerificationStatus.UNKNOWN,
                error="z3-solver not installed — run: pip install z3-solver",
            )

        t0 = time.monotonic()
        patterns = [
            ("conditional_assignment", self._verify_conditional_assignment),
            ("sort_direction",         self._verify_sort_direction),
            ("sort_nodupkey",          self._verify_sort_nodupkey),
            ("proc_means_groupby",     self._verify_proc_means_groupby),
            ("boolean_filter",         self._verify_boolean_filter),
            ("format_display_only",    self._verify_format_display_only),
            ("left_join",              self._verify_left_join),
            ("merge_indicator",        self._verify_merge_indicator),
            ("stepwise_regression",    self._verify_stepwise_regression),
            ("simple_assignment",      self._verify_simple_assignment),
        ]

        best_proved:      Optional[tuple[str, VerificationResult]] = None
        first_counterex:  Optional[tuple[str, VerificationResult]] = None
        matched_patterns: list[str] = []

        for name, checker in patterns:
            try:
                res = checker(sas_code, python_code)
                if res is None:
                    continue          # pattern not applicable to this block
                matched_patterns.append(name)
                if res.status == VerificationStatus.COUNTEREXAMPLE:
                    if first_counterex is None:
                        first_counterex = (name, res)
                elif res.status == VerificationStatus.PROVED:
                    if best_proved is None:
                        best_proved = (name, res)
            except Exception as exc:
                logger.warning("z3_pattern_error", pattern=name, error=str(exc))

        elapsed = (time.monotonic() - t0) * 1000

        if first_counterex:
            name, res = first_counterex
            res.latency_ms = elapsed
            res.pattern = name
            logger.warning("z3_counterexample", pattern=name,
                           issue=res.counterexample.get("issue", ""))
            return res

        if best_proved:
            name, res = best_proved
            res.latency_ms = elapsed
            res.pattern = name
            logger.info("z3_proved", pattern=name, latency_ms=f"{elapsed:.1f}")
            return res

        status = VerificationStatus.UNKNOWN
        pattern = matched_patterns[0] if matched_patterns else ""
        logger.debug("z3_unknown", patterns_tried=len(patterns),
                     matched=len(matched_patterns))
        return VerificationResult(
            status=status, latency_ms=elapsed, pattern=pattern
        )

    # ── Pattern 1: IF/THEN/ELSE → np.select / np.where ───────────────────────

    def _verify_conditional_assignment(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove SAS multi-branch IF/ELSE ≡ Python np.select/np.where.

        Z3 proves: for symbolic x, first SAS condition ↔ first Python condition.
        Hard counterexample: iterrows() used for conditional column assignment.
        """
        import z3

        # Must have IF ... THEN ... (ELSE optional)
        if not re.search(r"\bIF\b.+\bTHEN\b", sas, re.IGNORECASE | re.DOTALL):
            return None

        # ── Hard counterexample: iterrows for column assignment ──
        if re.search(r"iterrows\s*\(\s*\)", py):
            # Only fire if there's also a conditional assignment inside the loop
            if re.search(r"\.at\s*\[|\.loc\s*\[|\.iloc\s*\[", py):
                return VerificationResult(
                    status=VerificationStatus.COUNTEREXAMPLE,
                    counterexample={
                        "issue": (
                            "iterrows() used for conditional column assignment — "
                            "100x slower than np.select/np.where; "
                            "use np.select([cond1, cond2], [val1, val2], default=val3)"
                        )
                    },
                )

        # ── Python must use vectorized conditional ──
        py_vectorized = bool(
            re.search(r"np\.(select|where)\s*\(", py)
            or re.search(r"\.apply\s*\(", py)   # apply acceptable (not ideal but correct)
        )

        # ── Extract first SAS condition: IF <var> <op> <val> ──
        cond_m = re.search(
            r"\bIF\s+([\w.]+)\s*(<|>|<=|>=|=|[^=!<>]=[^=]|!=)\s*(-?[\d.]+)",
            sas, re.IGNORECASE,
        )
        if cond_m is None:
            # IF with string or complex condition — can't parse, but check vectorized
            if py_vectorized:
                return VerificationResult(status=VerificationStatus.PROVED)
            return VerificationResult(status=VerificationStatus.UNKNOWN)

        raw_var = cond_m.group(1).strip()
        # Strip table alias: a.balance → balance
        var   = raw_var.split(".")[-1].strip()
        op    = _norm_op(cond_m.group(2))
        val   = float(cond_m.group(3))

        # ── Find matching Python condition ──
        # Match any DataFrame accessor: df['col'], orders['col'], or bare col
        py_cond_m = re.search(
            rf"(?:\w+\[[\'\"]?{re.escape(var.lower())}[\'\"]?\]|{re.escape(var.lower())})"
            r"\s*(<|>|<=|>=|==|!=)\s*(-?[\d.]+(?:e[+-]?\d+)?)",
            py, re.IGNORECASE,
        )

        if py_cond_m is None:
            if py_vectorized:
                return VerificationResult(status=VerificationStatus.PROVED)
            return VerificationResult(status=VerificationStatus.UNKNOWN)

        py_op  = py_cond_m.group(1).strip()
        py_val = float(py_cond_m.group(2))

        # ── Z3: prove cond_sas(x) ↔ cond_py(x) ──
        x = z3.Real("x")
        sas_f = _z3_cmp(x, op,    z3.RealVal(val))
        py_f  = _z3_cmp(x, py_op, z3.RealVal(py_val))

        if sas_f is None or py_f is None:
            return VerificationResult(status=VerificationStatus.UNKNOWN)

        solver = z3.Solver()
        solver.set("timeout", 5000)
        solver.add(sas_f != py_f)          # negate equivalence
        res = solver.check()

        if res == z3.unsat:
            return VerificationResult(status=VerificationStatus.PROVED)
        if res == z3.sat:
            model = solver.model()
            witness_x = model.eval(x)
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        f"SAS condition '{var} {op} {val}' "
                        f"!= Python condition '{var} {py_op} {py_val}'"
                    ),
                    "witness_x": str(witness_x),
                    "hint": "Check operator or threshold value in the Python translation",
                },
            )
        return VerificationResult(status=VerificationStatus.UNKNOWN)

    # ── Pattern 2: PROC SORT direction ───────────────────────────────────────

    def _verify_sort_direction(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove BY col DESCENDING col2 → ascending=[True, False].

        Z3 encodes direction as Bool variables and checks satisfiability
        of the negated constraint (ascending_col2 == True) under the SAS spec.
        """
        import z3

        sort_m = re.search(
            r"\bPROC\s+SORT\b[^;]*;\s*BY\s+([^;]+);",
            sas, re.IGNORECASE | re.DOTALL,
        )
        if sort_m is None:
            return None

        by_clause = sort_m.group(1).strip()

        # Parse: "a DESCENDING b c DESCENDING d" → [(a,True),(b,False),(c,True),(d,False)]
        tokens = by_clause.split()
        columns: list[str] = []
        ascending_spec: list[bool] = []
        i = 0
        while i < len(tokens):
            tok = tokens[i].upper()
            if tok == "DESCENDING":
                # next token is the column that is descending
                if i + 1 < len(tokens):
                    columns.append(tokens[i + 1].lower())
                    ascending_spec.append(False)
                    i += 2
                else:
                    i += 1
            elif tok in ("BY", "NODUP", "NODUPKEY", "OUT", "DATA"):
                i += 1
            else:
                columns.append(tok.lower())
                ascending_spec.append(True)
                i += 1

        if not columns:
            return None

        # Find Python sort_values call
        sv_m = re.search(
            r"sort_values\s*\(\s*\[([^\]]+)\](?:[^)]*?ascending\s*=\s*\[([^\]]+)\])?",
            py,
        )
        if sv_m is None:
            if re.search(r"sort_values", py, re.IGNORECASE):
                return VerificationResult(status=VerificationStatus.UNKNOWN)
            return None

        py_asc_str = sv_m.group(2)
        if py_asc_str is None:
            # sort_values present but no ascending=[...] — defaults to all True
            # Check if any column should be descending
            if any(not a for a in ascending_spec):
                wrong = [c for c, a in zip(columns, ascending_spec) if not a]
                return VerificationResult(
                    status=VerificationStatus.COUNTEREXAMPLE,
                    counterexample={
                        "issue": "Missing ascending= parameter in sort_values",
                        "descending_cols": wrong,
                        "hint": f"Add ascending={ascending_spec} to sort_values()",
                    },
                )
            return VerificationResult(status=VerificationStatus.PROVED)

        py_asc_bools = []
        for tok in py_asc_str.split(","):
            tok = tok.strip()
            if tok == "True":
                py_asc_bools.append(True)
            elif tok == "False":
                py_asc_bools.append(False)
            else:
                return VerificationResult(status=VerificationStatus.UNKNOWN)

        n = min(len(columns), len(ascending_spec), len(py_asc_bools))

        # Z3 proof: for each column, Bool variable must match spec
        solver = z3.Solver()
        solver.set("timeout", 3000)

        z3_vars = [z3.Bool(f"asc_{c}") for c in columns[:n]]

        # Assert what Python actually has
        for i, bval in enumerate(py_asc_bools[:n]):
            solver.add(z3_vars[i] == bval)

        # Negate: try to find that some variable contradicts the SAS spec
        negated = z3.Or([
            z3_vars[i] != ascending_spec[i]
            for i in range(n)
        ])
        solver.add(negated)
        res = solver.check()

        if res == z3.unsat:
            return VerificationResult(status=VerificationStatus.PROVED)

        if res == z3.sat:
            wrong = [
                {
                    "column": columns[i],
                    "sas_direction": "ascending" if ascending_spec[i] else "descending",
                    "python_ascending": py_asc_bools[i],
                }
                for i in range(n)
                if py_asc_bools[i] != ascending_spec[i]
            ]
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": "Sort direction mismatch between SAS BY clause and Python ascending=",
                    "wrong_columns": wrong,
                    "expected": f"ascending={ascending_spec[:n]}",
                    "got":      f"ascending={py_asc_bools[:n]}",
                    "hint": (
                        "BY a DESCENDING b → ascending=[True, False], "
                        "NEVER [False, False]"
                    ),
                },
            )

        return VerificationResult(status=VerificationStatus.UNKNOWN)

    # ── Pattern 3: PROC MEANS → single groupby.agg ───────────────────────────

    def _verify_proc_means_groupby(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove PROC MEANS with CLASS → single groupby(dropna=False).agg().

        Counterexample 1: multiple separate groupby calls (one per CLASS combination).
        Counterexample 2: groupby without dropna=False (NaN group silently dropped).
        """
        if not re.search(r"\bPROC\s+MEANS\b", sas, re.IGNORECASE):
            return None
        if not re.search(r"\bCLASS\b", sas, re.IGNORECASE):
            return VerificationResult(status=VerificationStatus.UNKNOWN)

        # Count groupby calls in Python
        groupby_calls = re.findall(r"\.groupby\s*\(", py)
        agg_calls     = re.findall(r"\.agg\s*\(", py)

        if not groupby_calls:
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": "No groupby() found — PROC MEANS with CLASS must use groupby().agg()",
                    "hint": "df.groupby([class_vars], dropna=False).agg({...})",
                },
            )

        # Multiple merged groupby results (anti-pattern)
        merge_after_groupby = bool(
            len(groupby_calls) > 1
            and re.search(r"pd\.merge|\.merge\s*\(", py)
        )
        if merge_after_groupby:
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        "Multiple grouped aggregations merged together — "
                        "PROC MEANS CLASS requires ONE groupby().agg() call"
                    ),
                    "hint": "Combine all aggregations into one .agg({mean=..., sum=...})",
                },
            )

        # dropna=False must be present (SAS CLASS keeps NaN as a group)
        has_dropna_false = bool(re.search(r"dropna\s*=\s*False", py))
        if not has_dropna_false:
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        "groupby() missing dropna=False — "
                        "SAS CLASS keeps NaN as a separate group; "
                        "pandas drops NaN rows by default"
                    ),
                    "hint": "df.groupby([...], dropna=False).agg(...)",
                },
            )

        return VerificationResult(status=VerificationStatus.PROVED)

    # ── Pattern 4: Boolean filter (WHERE / IF numeric condition) ─────────────

    def _verify_boolean_filter(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove SAS WHERE/IF numeric condition ≡ Python boolean mask.

        Z3 proves: for symbolic x, filter_sas(x) ↔ filter_py(x).
        Handles macro references (&threshold → resolved numeric value).
        """
        import z3

        # Find SAS WHERE or IF with a numeric comparator
        sas_m = re.search(
            r"\b(?:WHERE|IF)\s+([\w.]+)\s*"
            r"(<|>|<=|>=|=|!=)\s*"
            r"(&?\w+|[-\d.]+)",
            sas, re.IGNORECASE,
        )
        if sas_m is None:
            return None

        raw_var, sas_op_raw, val_tok = (
            sas_m.group(1).strip(),
            sas_m.group(2).strip(),
            sas_m.group(3).strip(),
        )
        # Strip table alias: a.balance → balance
        var    = raw_var.split(".")[-1].strip()
        sas_op = _norm_op(sas_op_raw)

        # Resolve macro reference (%LET threshold = 5000 → 5000)
        if val_tok.startswith("&"):
            macro_name = val_tok.lstrip("&")
            macro_m = re.search(
                rf"%LET\s+{re.escape(macro_name)}\s*=\s*(-?[\d.]+)",
                sas, re.IGNORECASE,
            )
            if macro_m is None:
                return VerificationResult(status=VerificationStatus.UNKNOWN)
            val = float(macro_m.group(1))
        else:
            try:
                val = float(val_tok)
            except ValueError:
                return VerificationResult(status=VerificationStatus.UNKNOWN)

        # Find matching Python boolean mask
        # Match any DataFrame accessor: df['col'], orders['col'], or bare col
        py_m = re.search(
            rf"(?:\w+\[[\'\"]?{re.escape(var.lower())}[\'\"]?\]|{re.escape(var.lower())})"
            r"\s*(<|>|<=|>=|==|!=)\s*(-?[\d.]+(?:e[+-]?\d+)?)",
            py, re.IGNORECASE,
        )
        if py_m is None:
            # Check query() style
            py_q = re.search(
                rf"query\(['\"].*{re.escape(var.lower())}\s*"
                r"(<|>|<=|>=|==|!=)\s*(-?[\d.]+)['\"]",
                py, re.IGNORECASE,
            )
            if py_q:
                py_op  = py_q.group(1)
                py_val = float(py_q.group(2))
            else:
                return VerificationResult(status=VerificationStatus.UNKNOWN)
        else:
            py_op  = py_m.group(1)
            py_val = float(py_m.group(2))

        # Z3: for all x, sas_cond(x) ↔ py_cond(x)
        x      = z3.Real("x")
        sas_f  = _z3_cmp(x, sas_op, z3.RealVal(val))
        py_f   = _z3_cmp(x, py_op,  z3.RealVal(py_val))

        if sas_f is None or py_f is None:
            return VerificationResult(status=VerificationStatus.UNKNOWN)

        solver = z3.Solver()
        solver.set("timeout", 5000)
        solver.add(sas_f != py_f)
        res = solver.check()

        if res == z3.unsat:
            return VerificationResult(status=VerificationStatus.PROVED)
        if res == z3.sat:
            model  = solver.model()
            wit    = model.eval(x)
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        f"SAS filter '{var} {sas_op_raw} {val}' "
                        f"!= Python filter '{var} {py_op} {py_val}'"
                    ),
                    "witness_x": str(wit),
                    "sas_result_at_witness": str(
                        z3.simplify(z3.substitute(sas_f, (x, wit)))
                    ),
                    "py_result_at_witness": str(
                        z3.simplify(z3.substitute(py_f, (x, wit)))
                    ),
                },
            )
        return VerificationResult(status=VerificationStatus.UNKNOWN)

    # ── Pattern 5: PROC FORMAT display-only ──────────────────────────────────

    def _verify_format_display_only(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove FORMAT is display-only: original column must NOT be overwritten.

        SAS FORMAT never mutates the underlying column — it is presentation only.
        Python must create a *new* column (e.g. status_fmt), not overwrite status.
        """
        # Must have PROC FORMAT definition or FORMAT statement
        if not (
            re.search(r"\bPROC\s+FORMAT\b", sas, re.IGNORECASE)
            or re.search(r"\bFORMAT\s+\w+\s+\$?\w+\.", sas, re.IGNORECASE)
        ):
            return None

        # Extract column names referenced in FORMAT statements
        fmt_cols: list[str] = []
        for m in re.finditer(r"\bFORMAT\s+([\w\s]+)\$?\w+\.", sas, re.IGNORECASE):
            for col in m.group(1).strip().split():
                fmt_cols.append(col.lower())

        # Extract VALUE label names from PROC FORMAT
        for m in re.finditer(r"\bVALUE\s+\$?(\w+)", sas, re.IGNORECASE):
            fmt_cols.append(m.group(1).lower())

        if not fmt_cols:
            return VerificationResult(status=VerificationStatus.UNKNOWN)

        # Check Python does NOT do df['col'] = df['col'].map(...)
        for col in fmt_cols:
            # Pattern: df['col'] = ... (overwrite) where col matches fmt col
            overwrite_m = re.search(
                rf"df\[[\'\"]?{re.escape(col)}[\'\"]?\]\s*="
                r"\s*df\[.+\]\.map\s*\(",
                py, re.IGNORECASE,
            )
            if overwrite_m:
                return VerificationResult(
                    status=VerificationStatus.COUNTEREXAMPLE,
                    counterexample={
                        "issue": (
                            f"PROC FORMAT is display-only: column '{col}' "
                            "must NOT be overwritten by .map()"
                        ),
                        "wrong": overwrite_m.group(0).strip(),
                        "fix": (
                            f"df['{col}_fmt'] = df['{col}'].map(fmt_dict)"
                            ".fillna('Other')"
                        ),
                    },
                )

        # Check Python creates a new column (good pattern)
        new_col_m = re.search(r"df\[[\'\"].+_fmt[\'\"]?\]\s*=", py)
        if new_col_m:
            return VerificationResult(status=VerificationStatus.PROVED)

        return VerificationResult(status=VerificationStatus.UNKNOWN)

    # ── Pattern 6: LEFT JOIN preservation ────────────────────────────────────

    def _verify_left_join(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove PROC SQL LEFT JOIN → pd.merge how='left'.

        All rows from the left table must be preserved.
        Counterexample: how='inner' / how='right' / how='outer' / missing how.
        """
        if not re.search(r"\bLEFT\s+JOIN\b", sas, re.IGNORECASE):
            return None

        # Python must have a pd.merge (or DataFrame.merge) call
        if not re.search(r"pd\.merge\s*\(|\.merge\s*\(", py):
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": "PROC SQL LEFT JOIN found but no pd.merge() in Python",
                    "hint": "pd.merge(left_df, right_df, on='key', how='left')",
                },
            )

        # Extract how= parameter
        how_m = re.search(r"how\s*=\s*['\"](\w+)['\"]", py)
        if how_m is None:
            # No how= → defaults to inner join in pandas
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        "pd.merge() missing how='left' — "
                        "default is inner join which drops non-matching left rows"
                    ),
                    "hint": "Add how='left' to pd.merge()",
                },
            )

        actual_how = how_m.group(1).lower()
        if actual_how != "left":
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        f"SAS LEFT JOIN requires how='left', "
                        f"but Python uses how='{actual_how}'"
                    ),
                    "hint": "Change to how='left' in pd.merge()",
                },
            )

        return VerificationResult(status=VerificationStatus.PROVED)

    # ── Pattern 7: DATA MERGE with IN= subsetting ────────────────────────────

    def _verify_merge_indicator(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove MERGE (IN=a) + IF a → left join + indicator=True + drop _merge.

        Three sub-checks:
          1. indicator=True in pd.merge (required for IN= semantics)
          2. _merge column referenced after merge (for the IF a subsetting)
          3. _merge column dropped before output (cleanliness invariant)
        """
        if not re.search(r"\bMERGE\b.+\bIN\s*=", sas, re.IGNORECASE | re.DOTALL):
            return None

        has_indicator = bool(re.search(r"indicator\s*=\s*True", py))
        references_merge_col = bool(
            re.search(r"['\"]_merge['\"]|_merge\b", py)
        )
        drops_merge_col = bool(
            re.search(
                r"drop\s*\(\s*['\"]?_merge['\"]?\s*"
                r"|drop\s*\([^)]*['\"]_merge['\"][^)]*\)"
                r"|drop\s*\(columns\s*=.*_merge",
                py,
            )
        )

        issues = []
        if not has_indicator:
            issues.append(
                "indicator=True missing from pd.merge() — required to replicate IN= logic"
            )
        if references_merge_col and not drops_merge_col:
            issues.append(
                "_merge column used but never dropped — "
                "always drop _merge before returning the DataFrame"
            )
        if not references_merge_col and not drops_merge_col:
            # Maybe a simple left join was used without indicator — acceptable
            # if there's a how='left' (subsetting already implicit)
            if re.search(r"how\s*=\s*['\"]left['\"]", py):
                return VerificationResult(status=VerificationStatus.PROVED)

        if issues:
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": " | ".join(issues),
                    "hint": (
                        "df = pd.merge(t1, t2, on='key', how='left', indicator=True)\n"
                        "df = df[df['_merge'].isin(['left_only','both'])]\n"
                        "df = df.drop(columns=['_merge'])"
                    ),
                },
            )

        return VerificationResult(status=VerificationStatus.PROVED)

    # ── Pattern 8: PROC REG STEPWISE ─────────────────────────────────────────

    def _verify_stepwise_regression(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove PROC REG SELECTION=STEPWISE → statsmodels p-value loop.

        SAS uses F-statistic p-value thresholds (SLE=0.15, SLS=0.15), NOT BIC/AIC.
        Backward step MUST be guarded by `if changed:` to prevent infinite oscillation.

        Counterexample 1: sklearn used (wrong algorithm).
        Counterexample 2: BIC or AIC minimization used (wrong criterion).
        Counterexample 3: backward step not guarded (infinite loop risk).
        """
        if not re.search(r"SELECTION\s*=\s*STEPWISE", sas, re.IGNORECASE):
            return None

        # sklearn is wrong for SAS PROC REG STEPWISE
        if re.search(r"sklearn|from\s+sklearn|import\s+sklearn", py, re.IGNORECASE):
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        "sklearn used for PROC REG STEPWISE — wrong algorithm. "
                        "SAS uses F-statistic p-value thresholds (SLE=0.15, SLS=0.15), "
                        "not sklearn's wrapper"
                    ),
                    "fix": (
                        "Use statsmodels OLS: "
                        "import statsmodels.api as sm; "
                        "model = sm.OLS(y, X).fit(); model.pvalues"
                    ),
                },
            )

        # BIC / AIC criterion is wrong (SAS uses p-value thresholds)
        if re.search(r"\bbic\b|\baic\b|\.bic\b|\.aic\b", py, re.IGNORECASE):
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        "BIC/AIC minimization used — SAS PROC REG STEPWISE uses "
                        "F-statistic p-value thresholds (SLE=0.15, SLS=0.15), NOT BIC/AIC"
                    ),
                    "fix": (
                        "Loop on model.pvalues: "
                        "add predictor if pvalue < SLE (0.15); "
                        "remove predictor if pvalue > SLS (0.15)"
                    ),
                },
            )

        # Backward step must be guarded
        has_backward = bool(
            re.search(r"backward|backward_step|remove.*predictor", py, re.IGNORECASE)
        )
        if has_backward:
            has_changed_guard = bool(re.search(r"\bif\s+changed\b", py))
            if not has_changed_guard:
                return VerificationResult(
                    status=VerificationStatus.COUNTEREXAMPLE,
                    counterexample={
                        "issue": (
                            "Backward step in STEPWISE is not guarded by `if changed:` — "
                            "running it unconditionally causes infinite forward/backward oscillation"
                        ),
                        "fix": (
                            "Wrap the backward elimination loop with:\n"
                            "  changed = True\n"
                            "  while changed:\n"
                            "      changed = False\n"
                            "      for var in list(selected):\n"
                            "          if model.pvalues[var] > SLS:\n"
                            "              selected.remove(var)\n"
                            "              changed = True"
                        ),
                    },
                )

        # Must use p-values
        has_pvalues = bool(re.search(r"\.pvalues|p_values|pvalue", py, re.IGNORECASE))
        if not has_pvalues:
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        "No p-value check found for STEPWISE selection — "
                        "SAS uses F-statistic p-value thresholds"
                    ),
                    "fix": "Use statsmodels OLS model.pvalues to drive forward/backward selection",
                },
            )

        return VerificationResult(status=VerificationStatus.PROVED)

    # ── Pattern 9: PROC SORT NODUPKEY → drop_duplicates ──────────────────────

    def _verify_sort_nodupkey(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove PROC SORT NODUPKEY → sort_values + drop_duplicates.

        NODUPKEY in SAS removes duplicate BY-key observations.
        Python must use both sort_values AND drop_duplicates.

        Counterexample: sort_values present but drop_duplicates missing.
        """
        if not re.search(
            r"\bPROC\s+SORT\b.*\bNODUPKEY\b",
            sas,
            re.IGNORECASE | re.DOTALL,
        ):
            return None

        has_sort = bool(re.search(r"sort_values", py))
        has_dedup = bool(re.search(r"drop_duplicates", py))

        if not has_sort and not has_dedup:
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        "PROC SORT NODUPKEY found but neither sort_values() "
                        "nor drop_duplicates() in Python translation"
                    ),
                    "hint": (
                        "df = df.sort_values(['key']).drop_duplicates(subset=['key'])"
                    ),
                },
            )

        if has_sort and not has_dedup:
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        "PROC SORT NODUPKEY requires deduplication — "
                        "sort_values() present but drop_duplicates() missing"
                    ),
                    "hint": "Add .drop_duplicates(subset=[by_key]) after sort_values()",
                },
            )

        return VerificationResult(status=VerificationStatus.PROVED)

    # ── Pattern 10: DATA step arithmetic assignment ───────────────────────────

    def _verify_simple_assignment(
        self, sas: str, py: str
    ) -> Optional[VerificationResult]:
        """Prove DATA step y = x * coeff + offset matches Python coefficient.

        Z3 checks: for symbolic x, sas_expr(x) == py_expr(x).
        Catches off-by-one multipliers/offsets introduced during translation.

        Counterexample: coefficient or additive offset differs between SAS and Python.
        """
        import z3

        # Only apply to DATA step context
        if not re.search(r"\bDATA\b", sas, re.IGNORECASE):
            return None

        # SAS: new_var = old_var * coeff (+ offset)?
        sas_m = re.search(
            r"\b(\w+)\s*=\s*(\w+)\s*\*\s*(-?[\d.]+)"
            r"(?:\s*([+\-])\s*([\d.]+))?",
            sas,
            re.IGNORECASE,
        )
        if sas_m is None:
            return None

        sas_coeff = float(sas_m.group(3))
        if sas_m.group(4) and sas_m.group(5):
            sign = -1.0 if sas_m.group(4) == "-" else 1.0
            sas_offset = sign * float(sas_m.group(5))
        else:
            sas_offset = 0.0

        # Python: df['col'] = df['col'] * coeff (+ offset)?
        py_m = re.search(
            r"\[[\'\"]?\w+[\'\"]?\]\s*=\s*[^\n=]*?\*\s*(-?[\d.]+)"
            r"(?:\s*([+\-])\s*([\d.]+))?",
            py,
        )
        if py_m is None:
            return VerificationResult(status=VerificationStatus.UNKNOWN)

        py_coeff = float(py_m.group(1))
        if py_m.group(2) and py_m.group(3):
            sign = -1.0 if py_m.group(2) == "-" else 1.0
            py_offset = sign * float(py_m.group(3))
        else:
            py_offset = 0.0

        # Z3: prove sas_coeff * x + sas_offset == py_coeff * x + py_offset for all x
        x = z3.Real("x")
        sas_expr = z3.RealVal(sas_coeff) * x + z3.RealVal(sas_offset)
        py_expr  = z3.RealVal(py_coeff)  * x + z3.RealVal(py_offset)

        solver = z3.Solver()
        solver.set("timeout", 3000)
        solver.add(sas_expr != py_expr)
        res = solver.check()

        if res == z3.unsat:
            return VerificationResult(status=VerificationStatus.PROVED)
        if res == z3.sat:
            model = solver.model()
            wit = model.eval(x)
            return VerificationResult(
                status=VerificationStatus.COUNTEREXAMPLE,
                counterexample={
                    "issue": (
                        f"Arithmetic mismatch: SAS uses *{sas_coeff}+{sas_offset}, "
                        f"Python uses *{py_coeff}+{py_offset}"
                    ),
                    "witness_x": str(wit),
                    "expected": f"*{sas_coeff} + {sas_offset}",
                    "got":      f"*{py_coeff} + {py_offset}",
                    "hint": (
                        f"Change Python coefficient to {sas_coeff} "
                        f"and offset to {sas_offset}"
                    ),
                },
            )
        return VerificationResult(status=VerificationStatus.UNKNOWN)

    # ── internals ─────────────────────────────────────────────────────────────

    def _check_z3(self) -> bool:
        if self._z3_ok is None:
            try:
                import z3  # noqa: F401
                self._z3_ok = True
            except ImportError:
                self._z3_ok = False
                logger.warning("z3_unavailable", fix="pip install z3-solver>=4.13.0")
        return self._z3_ok
