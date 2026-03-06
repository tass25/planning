"""ValidationAgent (#13) — L3

Post-translation validation:
1. ast.parse() — syntax check
2. exec() sandbox on synthetic 100-row DataFrame (5s timeout)
3. Routing: pass → L4, fail + retry < 2 → retranslate, fail + retry >= 2 → PARTIAL

Windows-compatible: uses threading-based timeout (no signal.alarm).
"""

from __future__ import annotations

import ast
import threading
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


class ValidationAgent(BaseAgent):
    """Agent #13: Post-translation validation.

    For test_coverage_type='full':
      - ast.parse() syntax check
      - exec() on synthetic 100-row DataFrame

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

    # Builtins blocked from the exec() sandbox to prevent escape.
    _BLOCKED_BUILTINS = frozenset({
        "open", "__import__", "exec", "eval", "compile",
        "exit", "quit", "input", "breakpoint",
        # Block attribute introspection to prevent getattr(__builtins__, ...) bypass
        "getattr", "setattr", "delattr",
        # Block reflection helpers that expose internals
        "globals", "locals", "vars", "dir",
        # Block type introspection that enables __subclasses__() escape
        "type", "classmethod", "staticmethod", "super",
        "memoryview",  # can leak raw memory
    })

    def _build_sandbox_namespace(self) -> dict:
        """Build a restricted namespace for exec() sandboxing.

        Provides: pd, np, df (synthetic 100-row DataFrame).
        Removes dangerous builtins (see ``_BLOCKED_BUILTINS``).
        """
        rng = np.random.default_rng(42)
        df = pd.DataFrame({
            "id": range(1, 101),
            "amount": rng.uniform(10, 1000, 100).round(2),
            "category": rng.choice(["A", "B", "C", "D"], 100),
            "date": pd.date_range("2023-01-01", periods=100, freq="D"),
            "flag": rng.choice([0, 1], 100),
        })

        blocked = self._BLOCKED_BUILTINS

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

        return {
            "__builtins__": safe_builtins,
            "pd": pd,
            "np": np,
            "df": df,
        }

    def _execute_with_timeout(
        self, code: str, timeout: int = VALIDATION_TIMEOUT
    ) -> tuple[bool, str, Optional[object]]:
        """Execute code in sandbox with threading-based timeout (Windows-safe)."""
        namespace = self._build_sandbox_namespace()
        result_container: dict = {"ok": False, "error": "", "output": None}

        def _run():
            try:
                exec(code, namespace)  # noqa: S102 — sandboxed
                result_container["ok"] = True
                result_container["output"] = {
                    k: v
                    for k, v in namespace.items()
                    if not k.startswith("_") and k not in ("pd", "np", "df")
                }
            except Exception as e:
                result_container["error"] = str(e)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            return False, f"Timeout after {timeout}s", None

        return (
            result_container["ok"],
            result_container["error"],
            result_container["output"],
        )
