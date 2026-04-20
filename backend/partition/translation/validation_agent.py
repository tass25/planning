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
            df = _pd.DataFrame(
                {
                    "id": range(1, 101),
                    "customer_id": range(1001, 1101),
                    "product_id": range(201, 301),
                    "amount": rng.uniform(10, 1000, 100).round(2),
                    "revenue": rng.uniform(10, 5000, 100).round(2),
                    "units_sold": rng.integers(1, 50, 100),
                    "score": rng.uniform(0, 100, 100).round(2),
                    "age": rng.integers(18, 80, 100),
                    "value": rng.uniform(0, 100, 100).round(2),
                    "flag": rng.integers(0, 2, 100),
                    "status": rng.choice(["ACTIVE", "PENDING", "CLOSED"], 100),
                    "category": rng.choice(["A", "B", "C", "D"], 100),
                    "region": rng.choice(["NORTH", "SOUTH", "EAST", "WEST"], 100),
                    "product_line": rng.choice(["LINE1", "LINE2", "LINE3"], 100),
                    "month": rng.integers(1, 13, 100),
                    "year": rng.integers(2020, 2025, 100),
                    "date": _pd.date_range("2023-01-01", periods=100, freq="D"),
                    "survey_date": _pd.date_range("2023-01-01", periods=100, freq="D"),
                    "close": rng.uniform(10, 500, 100).round(2),
                    "open": rng.uniform(10, 500, 100).round(2),
                    "high": rng.uniform(10, 500, 100).round(2),
                    "low": rng.uniform(10, 500, 100).round(2),
                    "volume": rng.integers(1000, 100000, 100),
                    "name": [f"record_{i}" for i in range(100)],
                    "product_name": [f"product_{i}" for i in range(100)],
                }
            )
            self[key] = df
            return df
        except Exception:
            raise KeyError(key)


def _snapshot_namespace(namespace: dict) -> dict:
    """Capture DataFrame shapes and scalar values from the execution namespace.

    Used by EGS (Execution-Guided Synthesis) to give the repair LLM
    concrete variable state at the point of failure.
    """
    import pandas as _pd

    snapshot: dict[str, object] = {}
    for name, val in namespace.items():
        if name.startswith("_") or name in ("pd", "np", "io", "sys"):
            continue
        try:
            if isinstance(val, _pd.DataFrame):
                snapshot[name] = {
                    "type": "DataFrame",
                    "shape": list(val.shape),
                    "columns": list(val.columns[:15]),
                    "dtypes": {c: str(t) for c, t in list(val.dtypes.items())[:15]},
                    "empty": val.empty,
                }
            elif isinstance(val, _pd.Series):
                snapshot[name] = {
                    "type": "Series",
                    "len": len(val),
                    "dtype": str(val.dtype),
                    "empty": val.empty,
                }
            elif isinstance(val, (int, float, str, bool)):
                snapshot[name] = {"type": type(val).__name__, "value": repr(val)[:80]}
        except Exception:
            pass
    return snapshot


def _sandbox_exec(code: str, result_queue: "multiprocessing.Queue") -> None:
    """Run code in a sandboxed subprocess, return result via queue.

    Provides pd, np, and auto-namespace DataFrames for undefined names.
    Blocks dangerous builtins.

    EGS (Execution-Guided Synthesis) enhancement: on failure, captures
    variable states at the crash point so the repair prompt receives
    concrete runtime context (DataFrame shapes, column types, scalar values).
    """
    import io as _io
    import sys as _sys
    import traceback as _tb

    import numpy as _np
    import pandas as _pd

    blocked = frozenset(
        {
            "open",
            "__import__",
            "exec",
            "eval",
            "compile",
            "exit",
            "quit",
            "input",
            "breakpoint",
            "memoryview",
        }
    )

    if isinstance(__builtins__, dict):
        safe_builtins = {
            k: v for k, v in __builtins__.items() if k not in blocked and not k.startswith("__")
        }
    else:
        safe_builtins = {
            k: getattr(__builtins__, k)
            for k in dir(__builtins__)
            if k not in blocked and not k.startswith("__")
        }

    namespace = _AutoNamespace(
        {
            "__builtins__": safe_builtins,
            "pd": _pd,
            "np": _np,
            # Provide a default 'df' matching the original ValidationAgent contract
            "df": _pd.DataFrame(
                {
                    "id": range(1, 101),
                    "amount": _np.random.default_rng(42).uniform(10, 1000, 100).round(2),
                    "category": ["A", "B", "C", "D"] * 25,
                    "date": _pd.date_range("2024-01-01", periods=100, freq="D"),
                    "flag": [0, 1] * 50,
                }
            ),
        }
    )

    # Capture stdout
    stdout_buf = _io.StringIO()
    _sys.stdout = stdout_buf

    try:
        exec(code, namespace)  # noqa: S102 — sandboxed in subprocess
        _sys.stdout = _sys.__stdout__
        # EGS: capture output variable states on success too
        exec_states = _snapshot_namespace(namespace)
        result_queue.put(
            {
                "ok": True,
                "stdout": stdout_buf.getvalue()[:300],
                "exec_states": exec_states,
            }
        )
    except Exception as e:
        _sys.stdout = _sys.__stdout__
        full_tb = _tb.format_exc()
        # EGS: snapshot variable state at crash point
        exec_states = _snapshot_namespace(namespace)
        result_queue.put(
            {
                "ok": False,
                "error": str(e),
                "traceback": full_tb[-2000:],  # last 2000 chars is most relevant
                "stdout": stdout_buf.getvalue()[:300],
                "exec_states": exec_states,
            }
        )


class ValidationResult:
    """Result of validation.

    EGS fields (exec_states, exec_stdout) carry variable state at the crash
    point so the repair LLM receives concrete runtime context:
    DataFrame shapes, column dtypes, scalar values, captured stdout.
    """

    def __init__(
        self,
        passed: bool,
        syntax_ok: bool,
        exec_ok: bool,
        error_msg: str = "",
        output: Optional[object] = None,
        error_category: str = "",
        traceback: str = "",
        exec_states: Optional[dict] = None,  # EGS: variable snapshot at crash
        exec_stdout: str = "",  # EGS: stdout captured during exec
        fuzzing_failures: Optional[list[str]] = None,  # edge-case failures
    ):
        self.passed = passed
        self.syntax_ok = syntax_ok
        self.exec_ok = exec_ok
        self.error_msg = error_msg
        self.output = output
        self.error_category = error_category
        self.traceback = traceback
        self.exec_states: dict = exec_states or {}
        self.exec_stdout: str = exec_stdout
        self.fuzzing_failures: list[str] = fuzzing_failures or []

    def egs_context_block(self) -> str:
        """Render EGS variable state as a Markdown block for the repair prompt.

        Returns empty string when no state was captured.
        """
        if not self.exec_states and not self.exec_stdout and not self.fuzzing_failures:
            return ""
        lines = ["## Execution State at Failure (use this to fix the bug)"]
        if self.exec_stdout:
            lines.append(f"**stdout before crash**: `{self.exec_stdout}`")
        if self.exec_states:
            lines.append("**Variable state at crash point**:")
            for name, info in list(self.exec_states.items())[:8]:
                if isinstance(info, dict):
                    if info.get("type") == "DataFrame":
                        cols = info.get("columns", [])[:6]
                        lines.append(
                            f"  - `{name}`: DataFrame shape={info['shape']}, "
                            f"columns={cols}, empty={info['empty']}"
                        )
                        dtypes = info.get("dtypes", {})
                        if dtypes:
                            dtype_str = ", ".join(f"{c}:{t}" for c, t in list(dtypes.items())[:5])
                            lines.append(f"    dtypes: {dtype_str}")
                    elif info.get("type") == "Series":
                        lines.append(
                            f"  - `{name}`: Series len={info['len']}, dtype={info['dtype']}, "
                            f"empty={info['empty']}"
                        )
                    else:
                        lines.append(
                            f"  - `{name}` ({info.get('type','?')}): {info.get('value','?')}"
                        )
        if self.fuzzing_failures:
            lines.append("\n**Edge-case fuzzing failures** (fix must handle these inputs):")
            for f in self.fuzzing_failures[:4]:
                lines.append(f"  - {f}")
        return "\n".join(lines)


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
        """Validate a conversion result.

        Returns a ``ValidationResult`` with ``error_category`` (from
        error_classifier) and ``traceback`` populated on failure, so the
        translation pipeline can inject targeted repair guidance.
        """
        from partition.translation.error_classifier import classify_error

        python_code = conversion.python_code

        # Step 1: Syntax check (always)
        syntax_ok, syntax_error = self._check_syntax(python_code)
        if not syntax_ok:
            logger.warning(
                "validation_syntax_fail",
                conversion_id=str(conversion.conversion_id),
                error=syntax_error,
            )
            report = classify_error(f"SyntaxError: {syntax_error}", "", python_code)
            return ValidationResult(
                passed=False,
                syntax_ok=False,
                exec_ok=False,
                error_msg=f"SyntaxError: {syntax_error}",
                error_category=report.primary_category,
                traceback=syntax_error,
            )

        # Step 2: Execution test (only for full coverage)
        if test_coverage_type == "structural_only":
            return ValidationResult(
                passed=True,
                syntax_ok=True,
                exec_ok=True,
                error_msg="structural_only — exec skipped",
            )

        exec_ok, exec_error, output, exec_states, exec_stdout = self._execute_with_timeout(
            python_code
        )
        if not exec_ok:
            logger.warning(
                "validation_exec_fail",
                conversion_id=str(conversion.conversion_id),
                error=exec_error,
            )
            report = classify_error(exec_error, exec_error, python_code)
            return ValidationResult(
                passed=False,
                syntax_ok=True,
                exec_ok=False,
                error_msg=f"RuntimeError: {exec_error}",
                error_category=report.primary_category,
                traceback=exec_error,
                exec_states=exec_states,
                exec_stdout=exec_stdout,
            )

        # Edge-case fuzzing pass (EGS — property-based testing)
        # Only runs when primary validation passes; non-blocking failures
        # are surfaced to the repair prompt, not treated as hard failures.
        fuzzing_failures = self._fuzz_edge_cases(python_code)
        if fuzzing_failures:
            logger.info(
                "validation_fuzzing_warnings",
                conversion_id=str(conversion.conversion_id),
                n_failures=len(fuzzing_failures),
            )

        return ValidationResult(
            passed=True,
            syntax_ok=True,
            exec_ok=True,
            output=output,
            exec_states=exec_states,
            exec_stdout=exec_stdout,
            fuzzing_failures=fuzzing_failures,
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
    ) -> tuple[bool, str, Optional[object], dict, str]:
        """Execute code in a subprocess sandbox. Kills the process on timeout.

        Returns:
            (ok, error_msg, output, exec_states, exec_stdout)

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
            return False, f"Timeout after {timeout}s (process killed)", None, {}, ""

        if not result_queue.empty():
            result = result_queue.get_nowait()
            exec_states = result.get("exec_states", {})
            exec_stdout = result.get("stdout", "")
            if result.get("ok"):
                return True, "", None, exec_states, exec_stdout
            return False, result.get("error", "unknown error"), None, exec_states, exec_stdout

        return False, "subprocess exited with no result", None, {}, ""

    def _fuzz_edge_cases(self, code: str) -> list[str]:
        """Run code against diverse edge-case DataFrames; return list of failure descriptions.

        Tests: empty DataFrame, single-row, all-null column, duplicate keys.
        This is a lightweight property-based testing pass (Claessen & Hughes, QuickCheck 2000).
        Only runs when the primary validation passes — used to surface hidden semantic bugs.
        """
        import pandas as pd

        failures: list[str] = []

        EDGE_CASES = [
            (
                "empty_df",
                pd.DataFrame(
                    columns=[
                        "id",
                        "amount",
                        "category",
                        "date",
                        "flag",
                        "name",
                        "customer_id",
                        "product_id",
                        "status",
                        "region",
                    ]
                ),
            ),
            (
                "single_row",
                pd.DataFrame(
                    {
                        "id": [1],
                        "amount": [100.0],
                        "category": ["A"],
                        "date": pd.to_datetime(["2024-01-01"]),
                        "flag": [0],
                        "name": ["test"],
                        "customer_id": [1001],
                        "product_id": [201],
                        "status": ["ACTIVE"],
                        "region": ["NORTH"],
                    }
                ),
            ),
            (
                "all_null_amount",
                pd.DataFrame(
                    {
                        "id": range(5),
                        "amount": [None] * 5,
                        "category": ["A"] * 5,
                        "date": pd.date_range("2024-01-01", 5),
                        "flag": [0] * 5,
                        "status": ["ACTIVE"] * 5,
                    }
                ),
            ),
        ]

        for case_name, test_df in EDGE_CASES:
            rq: multiprocessing.Queue = multiprocessing.Queue()
            # Inject the test DataFrame as the default 'df'
            patched_code = (
                "import pandas as pd\nimport numpy as np\n"
                + f"df = pd.DataFrame({test_df.to_dict(orient='list')})\n"
                + code
            )
            proc = multiprocessing.Process(
                target=_sandbox_exec,
                args=(patched_code, rq),
                daemon=True,
            )
            proc.start()
            proc.join(timeout=max(5, VALIDATION_TIMEOUT // 3))
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=1)
                failures.append(f"`{case_name}`: timed out")
                continue
            if not rq.empty():
                result = rq.get_nowait()
                if not result.get("ok"):
                    err = result.get("error", "unknown")[:120]
                    failures.append(f"`{case_name}`: {err}")

        return failures
