"""ValidationAgent (#13) — L3

Post-translation validation:
1. ast.parse() — syntax check
2. exec() sandbox with a rich auto-namespace (15s timeout)
3. Routing: pass → L4, fail + retry < 2 → retranslate, fail + retry >= 2 → PARTIAL

Subprocess isolation via multiprocessing.Process + Queue (not Manager).
Manager() is avoided because on Windows it spawns a separate manager
process (~3s startup) which consistently eats the timeout budget.
Queue only adds one child process, which starts fast enough on all platforms.

Auto-namespace: any undefined variable referenced by translated code
automatically receives a synthetic DataFrame, so translations that
reference SAS dataset names (transactions, raw_data, customers, …)
execute without NameError even without real input files.
"""

from __future__ import annotations

import ast
import multiprocessing
import sys
from typing import Optional

import structlog

from partition.base_agent import BaseAgent
from partition.models.conversion_result import ConversionResult
from partition.models.enums import ConversionStatus

logger = structlog.get_logger()

# Windows subprocess spawn is slow (~2-4s per process).
# 15s gives enough headroom for spawn + imports + user code.
VALIDATION_TIMEOUT = 15 if sys.platform == "win32" else 8


# ── Sandbox ──────────────────────────────────────────────────────────────────

class _AutoNamespace(dict):
    """Namespace dict that returns a synthetic DataFrame for any unknown key.

    This lets translated code reference SAS dataset names
    (transactions, raw_data, customers, etc.) without NameError,
    as long as the column access doesn't require specific column names
    that we can't predict. Column-name errors are still real failures.
    """

    def __missing__(self, key: str):
        # Let Python builtins, dunder names, and keywords fall through normally
        import builtins as _builtins
        if key.startswith("_") or hasattr(_builtins, key):
            raise KeyError(key)
        try:
            import numpy as _np
            import pandas as _pd

            rng = _np.random.default_rng(42)
            # Build a DataFrame with many common SAS column name patterns
            df = _pd.DataFrame({
                "id":          range(1, 101),
                "customer_id": range(1001, 1101),
                "product_id":  range(201, 301),
                "amount":      rng.uniform(10, 1000, 100).round(2),
                "revenue":     rng.uniform(10, 5000, 100).round(2),
                "units_sold":  rng.integers(1, 50, 100),
                "score":       rng.uniform(0, 100, 100).round(2),
                "age":         rng.integers(18, 80, 100),
                "value":       rng.uniform(0, 100, 100).round(2),
                "flag":        rng.integers(0, 2, 100),
                "status":      rng.choice(["ACTIVE", "PENDING", "CLOSED"], 100),
                "category":    rng.choice(["A", "B", "C", "D"], 100),
                "region":      rng.choice(["NORTH", "SOUTH", "EAST", "WEST"], 100),
                "product_line": rng.choice(["LINE1", "LINE2", "LINE3"], 100),
                "month":       rng.integers(1, 13, 100),
                "year":        rng.integers(2020, 2025, 100),
                "date":        _pd.date_range("2023-01-01", periods=100, freq="D"),
                "survey_date": _pd.date_range("2023-01-01", periods=100, freq="D"),
                "close":       rng.uniform(10, 500, 100).round(2),
                "open":        rng.uniform(10, 500, 100).round(2),
                "high":        rng.uniform(10, 500, 100).round(2),
                "low":         rng.uniform(10, 500, 100).round(2),
                "volume":      rng.integers(1000, 100000, 100),
                "name":        [f"record_{i}" for i in range(100)],
                "product_name": [f"product_{i}" for i in range(100)],
            })
            self[key] = df
            return df
        except Exception:
            raise KeyError(key)


def _sandbox_exec(code: str, result_queue: "multiprocessing.Queue") -> None:
    """Run code in a sandboxed subprocess, return result via queue.

    Provides pd, np, and auto-namespace DataFrames for undefined names.
    Blocks dangerous builtins.
    """
    import numpy as _np
    import pandas as _pd

    blocked = frozenset({
        "open", "__import__", "exec", "eval", "compile",
        "exit", "quit", "input", "breakpoint",
        "memoryview",
    })

    if isinstance(__builtins__, dict):
        safe_builtins = {
            k: v for k, v in __builtins__.items()
            if k not in blocked and not k.startswith("__")
        }
    else:
        safe_builtins = {
            k: getattr(__builtins__, k)
            for k in dir(__builtins__)
            if k not in blocked and not k.startswith("__")
        }

    namespace = _AutoNamespace({
        "__builtins__": safe_builtins,
        "pd": _pd,
        "np": _np,
        # Provide a default 'df' matching the original ValidationAgent contract
        "df": _pd.DataFrame({
            "id":       range(1, 101),
            "amount":   _np.random.default_rng(42).uniform(10, 1000, 100).round(2),
            "category": ["A", "B", "C", "D"] * 25,
            "date":     _pd.date_range("2024-01-01", periods=100, freq="D"),
            "flag":     [0, 1] * 50,
        }),
    })

    try:
        exec(code, namespace)  # noqa: S102 — sandboxed in subprocess
        result_queue.put({"ok": True})
    except Exception as e:
        result_queue.put({"ok": False, "error": str(e)})


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

        # Step 1: Syntax check (always)
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

        Uses a Queue instead of Manager().dict() — Manager() spawns a
        separate manager process which is ~3s overhead on Windows, reliably
        eating the 5s timeout before any user code runs.
        """
        result_queue: multiprocessing.Queue = multiprocessing.Queue()

        proc = multiprocessing.Process(
            target=_sandbox_exec,
            args=(code, result_queue),
            daemon=True,
        )
        proc.start()
        proc.join(timeout=timeout)

        if proc.is_alive():
            proc.kill()
            proc.join(timeout=2)
            return False, f"Timeout after {timeout}s (process killed)", None

        if not result_queue.empty():
            result = result_queue.get_nowait()
            if result.get("ok"):
                return True, "", None
            return False, result.get("error", "unknown error"), None

        return False, "subprocess exited with no result", None
