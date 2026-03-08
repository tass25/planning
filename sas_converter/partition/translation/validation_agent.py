"""ValidationAgent (#13) — L3

Post-translation validation:
1. ast.parse() — syntax check
2. exec() sandbox on synthetic 100-row DataFrame (5s timeout)
3. Routing: pass → L4, fail + retry < 2 → retranslate, fail + retry >= 2 → PARTIAL

Uses subprocess-based isolation to kill runaway code on timeout.
"""

from __future__ import annotations

import ast
import multiprocessing
from typing import Optional

import numpy as np
import pandas as pd
import structlog

from partition.base_agent import BaseAgent
from partition.models.conversion_result import ConversionResult
from partition.models.enums import ConversionStatus

logger = structlog.get_logger()

VALIDATION_TIMEOUT = 5  # seconds


class ValidationResult:
    """Result of validation."""

    def __init__(
        self,
        passed: bool,
        syntax_ok: bool,
        exec_ok: bool,
        error_msg: str = "",
        output: Optional[object] = None,
    ):
        self.passed = passed
        self.syntax_ok = syntax_ok
        self.exec_ok = exec_ok
        self.error_msg = error_msg
        self.output = output


def _sandbox_exec(code: str, result_dict: dict) -> None:
    """Run code in a sandboxed subprocess (target for multiprocessing).

    Provides: pd, np, df (synthetic 100-row DataFrame).
    Blocks dangerous builtins.
    """
    import numpy as _np
    import pandas as _pd

    blocked = frozenset({
        "open", "__import__", "exec", "eval", "compile",
        "exit", "quit", "input", "breakpoint",
        "getattr", "setattr", "delattr",
        "globals", "locals", "vars", "dir",
        "type", "classmethod", "staticmethod", "super",
        "memoryview",
    })

    rng = _np.random.default_rng(42)
    df = _pd.DataFrame({
        "id": range(1, 101),
        "amount": rng.uniform(10, 1000, 100).round(2),
        "category": rng.choice(["A", "B", "C", "D"], 100),
        "date": _pd.date_range("2023-01-01", periods=100, freq="D"),
        "flag": rng.choice([0, 1], 100),
    })

    if isinstance(__builtins__, dict):
        safe_builtins = {
            k: v for k, v in __builtins__.items()
            if k not in blocked and not k.startswith("_")
        }
    else:
        safe_builtins = {
            k: getattr(__builtins__, k)
            for k in dir(__builtins__)
            if k not in blocked and not k.startswith("_")
        }

    namespace = {
        "__builtins__": safe_builtins,
        "pd": _pd,
        "np": _np,
        "df": df,
    }

    try:
        exec(code, namespace)  # noqa: S102 — sandboxed in subprocess
        result_dict["ok"] = True
    except Exception as e:
        result_dict["error"] = str(e)


class ValidationAgent(BaseAgent):
    """Agent #13: Post-translation validation.

    For test_coverage_type='full':
      - ast.parse() syntax check
      - exec() in a subprocess sandbox (killed on timeout)

    For test_coverage_type='structural_only':
      - ast.parse() only (no execution)

    Retry policy: 2 retries, namespace reset between attempts.
    """

    MAX_RETRIES = 2

    @property
    def agent_name(self) -> str:
        return "ValidationAgent"

    def __init__(self):
        super().__init__()

    async def process(self, conversion: ConversionResult, **kwargs):
        """BaseAgent entry point — delegates to validate()."""
        test_type = kwargs.get("test_coverage_type", "full")
        return await self.validate(conversion, test_type)

    async def validate(
        self,
        conversion: ConversionResult,
        test_coverage_type: str = "full",
    ) -> ValidationResult:
        """Validate a conversion result."""
        python_code = conversion.python_code

        # Step 1: Syntax check
        syntax_ok, syntax_error = self._check_syntax(python_code)
        if not syntax_ok:
            logger.warning(
                "validation_syntax_fail",
                conversion_id=str(conversion.conversion_id),
                error=syntax_error,
            )
            return ValidationResult(
                passed=False,
                syntax_ok=False,
                exec_ok=False,
                error_msg=f"SyntaxError: {syntax_error}",
            )

        # Step 2: Execution test (only for full coverage)
        if test_coverage_type == "structural_only":
            return ValidationResult(
                passed=True,
                syntax_ok=True,
                exec_ok=True,
                error_msg="structural_only — exec skipped",
            )

        exec_ok, exec_error, output = self._execute_with_timeout(python_code)
        if not exec_ok:
            logger.warning(
                "validation_exec_fail",
                conversion_id=str(conversion.conversion_id),
                error=exec_error,
            )
            return ValidationResult(
                passed=False,
                syntax_ok=True,
                exec_ok=False,
                error_msg=f"RuntimeError: {exec_error}",
            )

        return ValidationResult(
            passed=True, syntax_ok=True, exec_ok=True, output=output
        )

    def _check_syntax(self, code: str) -> tuple[bool, str]:
        """Check Python syntax via ast.parse()."""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, str(e)

    def _execute_with_timeout(
        self, code: str, timeout: int = VALIDATION_TIMEOUT
    ) -> tuple[bool, str, Optional[object]]:
        """Execute code in a subprocess sandbox. Kills the process on timeout.

        Uses multiprocessing instead of threading so runaway code is truly
        terminated via process kill rather than leaked as a daemon thread.
        """
        manager = multiprocessing.Manager()
        result_dict = manager.dict({"ok": False, "error": "", "output": None})

        proc = multiprocessing.Process(
            target=_sandbox_exec,
            args=(code, result_dict),
            daemon=True,
        )
        proc.start()
        proc.join(timeout=timeout)

        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)
            return False, f"Timeout after {timeout}s (process killed)", None

        return (
            bool(result_dict.get("ok", False)),
            str(result_dict.get("error", "")),
            result_dict.get("output"),
        )
