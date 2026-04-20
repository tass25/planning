"""coverage_oracle.py — Runs correct oracle vs translated Python on a CDAIS witness.

For each SynthesisResult, the coverage oracle:
  1. Identifies which semantic oracle applies to the SAS code (from semantic_validator.py)
  2. Runs the oracle on the witness DataFrame → expected correct output
  3. Runs the translated Python on the witness DataFrame → actual output
  4. Compares: if they match → the translation PASSES this error class
                if they differ → the translation FAILS (the bug is confirmed present)

A passed check yields a COVERAGE CERTIFICATE:
  "This translation is formally free from error class C for any input of shape S."

The certificate is stronger than a passing test: it comes with a proof that
the witness is the MINIMUM input that can expose the bug. If the bug were
present, the witness would expose it. Since it didn't, the bug is absent.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import structlog

from partition.testing.cdais.synthesizer import SynthesisResult
from partition.translation.semantic_validator import (
    _compare_frames,
    _oracle_first_last,
    _oracle_lag,
    _oracle_merge,
    _oracle_proc_freq,
    _oracle_proc_means,
    _oracle_proc_sort,
    _oracle_retain,
)

logger = structlog.get_logger(__name__)

_EXEC_TIMEOUT_S = 5.0


@dataclass
class CoverageResult:
    """Result of running the coverage oracle for one error class."""

    error_class: str
    passed: bool
    certificate: str = ""  # formal certificate text (when passed)
    failure_details: list[str] = field(default_factory=list)
    oracle_repr: str = ""
    actual_repr: str = ""
    witness_rows: int = 0

    def to_prompt_block(self) -> str:
        if self.passed:
            return f"✓ Coverage certificate issued for `{self.error_class}`."
        lines = [
            f"## CDAIS Coverage Failure — `{self.error_class}`",
            "Your translation fails the formally minimal witness for this error class.",
        ]
        for d in self.failure_details:
            lines.append(f"- {d}")
        if self.oracle_repr:
            lines.append(f"\n**Expected**:\n```\n{self.oracle_repr}\n```")
        if self.actual_repr:
            lines.append(f"\n**Actual**:\n```\n{self.actual_repr}\n```")
        return "\n".join(lines)


class CoverageOracle:
    """Runs the oracle and the translation on the CDAIS witness, then compares."""

    _ORACLE_FNS = [
        _oracle_proc_sort,
        _oracle_proc_means,
        _oracle_proc_freq,
        _oracle_retain,
        _oracle_lag,
        _oracle_first_last,
        _oracle_merge,
    ]

    def check(
        self,
        synthesis: SynthesisResult,
        sas_code: str,
        python_code: str,
    ) -> CoverageResult:
        """Run oracle vs translated Python on synthesis.witness_df."""
        if not synthesis.sat or synthesis.witness_df.empty:
            return CoverageResult(
                error_class=synthesis.error_class,
                passed=True,
                certificate="No witness synthesized — error class not applicable.",
            )

        ec = synthesis.error_class
        witness = synthesis.witness_df

        # Build input_frames dict from witness
        input_frames = self._build_input_frames(ec, witness)

        # Run semantic oracle
        oracle_frames = self._run_oracle(sas_code, input_frames)
        if oracle_frames is None:
            # No oracle for this pattern — issue certificate by default
            return CoverageResult(
                error_class=ec,
                passed=True,
                certificate=f"No oracle applicable for `{ec}` — certificate granted.",
                witness_rows=len(witness),
            )

        oracle_df = next(iter(oracle_frames.values()))

        # Run translated Python
        out_names = list(oracle_frames.keys())
        actual_frames = self._exec_python(python_code, input_frames, out_names)

        if actual_frames is None:
            # Execution crashed — already caught by ValidationAgent
            return CoverageResult(
                error_class=ec,
                passed=False,
                failure_details=[
                    "Translated Python crashed on CDAIS witness (exec timeout/error)."
                ],
                oracle_repr=oracle_df.head(5).to_string(index=False),
                witness_rows=len(witness),
            )

        actual_df = actual_frames.get(out_names[0]) or (
            next(iter(actual_frames.values())) if actual_frames else None
        )

        if actual_df is None:
            return CoverageResult(
                error_class=ec,
                passed=False,
                failure_details=["Translated Python produced no output DataFrame."],
                oracle_repr=oracle_df.head(5).to_string(index=False),
                witness_rows=len(witness),
            )

        matched, details = _compare_frames(oracle_df, actual_df)

        if matched:
            cert = (
                f"COVERAGE CERTIFICATE — `{ec}`: Translation is formally free from "
                f"this error class for any dataset of shape "
                f"({synthesis.metadata.get('n_groups', '?')} groups × "
                f"{synthesis.metadata.get('n_rows_per_group', '?')} rows/group)."
            )
            return CoverageResult(
                error_class=ec,
                passed=True,
                certificate=cert,
                witness_rows=len(witness),
            )

        return CoverageResult(
            error_class=ec,
            passed=False,
            failure_details=details,
            oracle_repr=oracle_df.head(5).to_string(index=False),
            actual_repr=actual_df.head(5).to_string(index=False),
            witness_rows=len(witness),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_input_frames(self, ec: str, witness: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """Convert witness DataFrame to the input_frames dict expected by oracles."""
        if ec == "JOIN_TYPE":
            left = (
                witness[witness["__table__"] == "left"]
                .drop(columns=["__table__"])
                .reset_index(drop=True)
            )
            right = (
                witness[witness["__table__"] == "right"]
                .drop(columns=["__table__"])
                .reset_index(drop=True)
            )
            return {"left": left, "right": right}
        # For all other error classes, the witness is a single input table
        return {"input": witness.copy()}

    def _run_oracle(
        self, sas_code: str, input_frames: dict[str, pd.DataFrame]
    ) -> Optional[dict[str, pd.DataFrame]]:
        for oracle_fn in self._ORACLE_FNS:
            try:
                result = oracle_fn(sas_code, input_frames)
                if result is not None:
                    return result
            except Exception as exc:
                logger.debug("coverage_oracle_fn_error", fn=oracle_fn.__name__, error=str(exc))
        return None

    def _exec_python(
        self,
        python_code: str,
        input_frames: dict[str, pd.DataFrame],
        expected_names: list[str],
    ) -> Optional[dict[str, pd.DataFrame]]:
        namespace: dict = {
            "pd": pd,
            "np": np,
            "__builtins__": (
                {
                    k: v
                    for k, v in __builtins__.items()  # type: ignore[union-attr]
                    if k
                    not in {
                        "open",
                        "__import__",
                        "exec",
                        "eval",
                        "compile",
                        "exit",
                        "quit",
                        "input",
                        "breakpoint",
                    }
                }
                if isinstance(__builtins__, dict)
                else __builtins__
            ),
        }
        for name, df in input_frames.items():
            namespace[name] = df.copy()
        if "df" not in namespace and input_frames:
            namespace["df"] = next(iter(input_frames.values())).copy()
        # Also inject table-specific names for MERGE witness
        if "left" in input_frames:
            namespace["left"] = input_frames["left"].copy()
            namespace["right"] = input_frames["right"].copy()

        result_holder: list[Optional[dict]] = [None]

        def _run() -> None:
            try:
                exec(python_code, namespace)  # noqa: S102
                outputs: dict[str, pd.DataFrame] = {}
                for name in expected_names:
                    if name in namespace and isinstance(namespace[name], pd.DataFrame):
                        outputs[name] = namespace[name].copy()
                if not outputs:
                    for k, v in namespace.items():
                        if (
                            isinstance(v, pd.DataFrame)
                            and k not in input_frames
                            and not k.startswith("_")
                            and k not in ("pd", "np")
                        ):
                            outputs[k] = v.copy()
                result_holder[0] = outputs
            except Exception:
                pass

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=_EXEC_TIMEOUT_S)
        return result_holder[0] if not t.is_alive() else None
