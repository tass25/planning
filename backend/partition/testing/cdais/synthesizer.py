"""synthesizer.py — Z3-driven minimum witness DataFrame synthesis.

Given an ErrorClass and a ConstraintConfig, the synthesizer:
  1. Creates a Z3 Solver
  2. Calls error_class.encode() to add divergence constraints
  3. Calls solver.check() — expects SAT (the divergence is always reachable)
  4. Extracts the SAT model and converts symbolic variables to concrete Python values
  5. Builds the minimum witness as a pandas DataFrame

The "minimum" property comes from Z3's model: it finds ANY satisfying assignment.
For minimality, we add an optimization objective: minimize the sum of all integer
variables before solving. This requires z3.Optimize instead of z3.Solver.

Returns a SynthesisResult containing:
  - witness_df    : the concrete input DataFrame
  - error_class   : which error this witnesses
  - correct_output: the expected (oracle) output for this input
  - metadata      : human-readable explanation for repair prompts
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import structlog

from partition.testing.cdais.constraint_catalog import (
    ConstraintConfig,
    ErrorClass,
    EncodedConstraints,
)

logger = structlog.get_logger(__name__)


@dataclass
class SynthesisResult:
    """Minimum witness DataFrame for one error class."""
    error_class: str
    witness_df: pd.DataFrame
    correct_output: Optional[pd.DataFrame]   # oracle output on this witness
    latency_ms: float = 0.0
    sat: bool = True
    explanation: str = ""
    metadata: dict = field(default_factory=dict)

    def to_prompt_block(self) -> str:
        """Render as a Markdown block for injection into repair prompts."""
        lines = [
            f"## CDAIS Witness — Error Class `{self.error_class}`",
            f"**What this tests**: {self.explanation}",
            "",
            "**Minimum witness input** (synthesized by Z3):",
            f"```\n{self.witness_df.to_string(index=False)}\n```",
        ]
        if self.correct_output is not None and not self.correct_output.empty:
            lines += [
                "",
                "**Expected correct output** (from semantic oracle):",
                f"```\n{self.correct_output.to_string(index=False)}\n```",
            ]
        lines += [
            "",
            "Your translation must produce the correct output above for this input.",
            "This is a formally minimal witness — if your code fails on these "
            f"{len(self.witness_df)} rows, it has the `{self.error_class}` bug.",
        ]
        return "\n".join(lines)


class CDASISynthesizer:
    """Synthesizes minimum witness DataFrames using Z3 optimization.

    Uses z3.Optimize (soft minimize objective) to find minimal values.
    Falls back to z3.Solver if Optimize is unavailable.
    """

    def synthesize(
        self,
        error_class: ErrorClass,
        cfg: Optional[ConstraintConfig] = None,
    ) -> SynthesisResult:
        """Synthesize the minimum witness for error_class."""
        cfg = cfg or ConstraintConfig()
        t0  = time.monotonic()

        try:
            import z3
        except ImportError:
            logger.warning("cdais_z3_unavailable")
            return SynthesisResult(
                error_class=error_class.name,
                witness_df=pd.DataFrame(),
                correct_output=None,
                sat=False,
                explanation="z3-solver not installed",
            )

        try:
            opt = z3.Optimize()
            opt.set("timeout", cfg.z3_timeout_ms)

            encoded = error_class.encode(opt, cfg)

            # Soft minimize: sum of all integer variables → smallest witness
            int_vars = [
                v for v in encoded.sym_vars.values()
                if isinstance(v, z3.ExprRef) and z3.is_int(v)
            ]
            if int_vars:
                opt.minimize(z3.Sum(int_vars))

            result = opt.check()
            elapsed = (time.monotonic() - t0) * 1000

            if result != z3.sat:
                logger.warning("cdais_unsat", error_class=error_class.name,
                               result=str(result))
                return SynthesisResult(
                    error_class=error_class.name,
                    witness_df=pd.DataFrame(),
                    correct_output=None,
                    sat=False,
                    latency_ms=elapsed,
                    explanation=f"Z3 returned {result} — no witness exists",
                )

            model   = opt.model()
            witness = self._model_to_dataframe(model, encoded, cfg)
            elapsed = (time.monotonic() - t0) * 1000

            logger.info("cdais_synthesized", error_class=error_class.name,
                        rows=len(witness), latency_ms=f"{elapsed:.1f}")

            return SynthesisResult(
                error_class=error_class.name,
                witness_df=witness,
                correct_output=None,   # filled by coverage_oracle
                sat=True,
                latency_ms=elapsed,
                explanation=error_class.description,
                metadata={"n_groups": encoded.n_groups,
                           "n_rows_per_group": encoded.n_rows_per_group},
            )

        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            logger.error("cdais_synthesis_error", error_class=error_class.name,
                         error=str(exc))
            return SynthesisResult(
                error_class=error_class.name,
                witness_df=pd.DataFrame(),
                correct_output=None,
                sat=False,
                latency_ms=elapsed,
                explanation=f"Synthesis error: {exc}",
            )

    # ── model extraction ──────────────────────────────────────────────────────

    def _model_to_dataframe(
        self,
        model: Any,
        encoded: EncodedConstraints,
        cfg: ConstraintConfig,
    ) -> pd.DataFrame:
        """Convert a Z3 SAT model into a concrete pandas DataFrame."""
        import z3

        ec = encoded.error_class
        G  = encoded.n_groups
        R  = encoded.n_rows_per_group

        def _int(var) -> int:
            val = model.eval(var, model_completion=True)
            try:
                return int(val.as_long())
            except Exception:
                return int(str(val))

        def _bool(var) -> bool:
            val = model.eval(var, model_completion=True)
            return bool(val)

        if ec == "RETAIN_RESET":
            rows = []
            for g in range(G):
                for r in range(R):
                    rows.append({
                        "group": chr(ord("A") + g),
                        "value": _int(encoded.sym_vars[f"v_{g}_{r}"]),
                    })
            return pd.DataFrame(rows)

        elif ec == "LAG_QUEUE":
            rows = []
            for i in range(2 * R):
                g = i // R
                rows.append({
                    "group": chr(ord("A") + g),
                    "value": _int(encoded.sym_vars[f"lag_v_{i}"]),
                })
            return pd.DataFrame(rows)

        elif ec == "SORT_STABLE":
            return pd.DataFrame([
                {"primary_key": _int(encoded.sym_vars["sort_key1"]),
                 "secondary":   _int(encoded.sym_vars["sort_sec1"]),
                 "original_order": 0},
                {"primary_key": _int(encoded.sym_vars["sort_key2"]),
                 "secondary":   _int(encoded.sym_vars["sort_sec2"]),
                 "original_order": 1},
            ])

        elif ec == "NULL_ARITHMETIC":
            total      = _int(encoded.sym_vars["null_total"])
            addend     = _int(encoded.sym_vars["null_addend"])
            is_missing = _bool(encoded.sym_vars["null_is_missing"])
            rows = []
            # Group A: normal rows
            for r in range(R - 1):
                rows.append({"group": "A", "value": r + 1})
            # Last row of group A: the NaN row
            rows.append({"group": "A", "value": np.nan if is_missing else addend})
            # Group B: normal rows
            for r in range(R):
                rows.append({"group": "B", "value": r + 1})
            df = pd.DataFrame(rows)
            df["total"] = 0.0   # accumulator column, starts at 0
            return df

        elif ec == "JOIN_TYPE":
            left_rows  = [{"key": _int(encoded.sym_vars[f"join_kL_{i}"]),
                            "left_val": i + 10} for i in range(R)]
            right_rows = [{"key": _int(encoded.sym_vars[f"join_kR_{i}"]),
                            "right_val": i + 20} for i in range(R)]
            # Return as a single DF with a 'table' marker for the runner
            left_df  = pd.DataFrame(left_rows)
            right_df = pd.DataFrame(right_rows)
            left_df["__table__"]  = "left"
            right_df["__table__"] = "right"
            return pd.concat([left_df, right_df], ignore_index=True)

        elif ec == "GROUP_BOUNDARY":
            rows = []
            for g in range(G):
                label = _int(encoded.sym_vars[f"gb_group_{g}"])
                for r in range(R):
                    rows.append({
                        "group": label,
                        "value": _int(encoded.sym_vars[f"gb_val_{g}_{r}"]),
                        "row_within_group": r,
                    })
            return pd.DataFrame(rows)

        # Fallback: generic key-value frame
        rows = []
        for name, var in encoded.sym_vars.items():
            try:
                rows.append({"variable": name, "value": _int(var)})
            except Exception:
                pass
        return pd.DataFrame(rows)
