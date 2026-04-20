"""regression_runner.py — Oracle-based semantic regression suite.

Runs the SemanticValidator oracle against every gold standard SAS file
WITHOUT requiring LLM API calls.  Two modes:

  Mode A — DETERMINISTIC (default, CI-safe):
    For each gold-standard SAS partition that the deterministic translator
    can handle, run the oracle + deterministic Python, compare, report.

  Mode B — FULL (requires LLM keys):
    Load pre-translated Python from knowledge_base/gold_standard/*.gold.json
    if a ``python_code`` field exists, run oracle against it.

Output:
    A RegressionReport printed to stdout (+ optionally written to a JSON file).
    Exit code 0 = all cases pass, 1 = at least one failure.

Usage::

    # Deterministic mode (no LLM needed):
    python -m benchmark.regression_runner

    # Full mode with pre-translated gold JSON:
    python -m benchmark.regression_runner --mode full

    # Write JSON report:
    python -m benchmark.regression_runner --out reports/regression.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()

# ── paths ─────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_GOLD_DIR = _PROJECT_ROOT / "knowledge_base" / "gold_standard"


# ── result types ──────────────────────────────────────────────────────────────


@dataclass
class CaseResult:
    case_id: str
    sas_file: str
    status: str  # "pass" | "fail" | "skip" | "error"
    error_type: str = ""
    details: list[str] = field(default_factory=list)
    oracle_repr: str = ""
    actual_repr: str = ""
    duration_ms: float = 0.0
    partition_type: str = ""


@dataclass
class RegressionReport:
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    cases: list[CaseResult] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def pass_rate(self) -> float:
        denom = self.total - self.skipped
        return (self.passed / denom * 100) if denom > 0 else 0.0

    def print_summary(self) -> None:
        width = 70
        print("=" * width)
        print("  SEMANTIC REGRESSION REPORT")
        print("=" * width)
        print(f"  Total   : {self.total}")
        print(f"  Passed  : {self.passed}")
        print(f"  Failed  : {self.failed}")
        print(f"  Skipped : {self.skipped}  (no oracle for this SAS pattern)")
        print(f"  Errors  : {self.errors}")
        print(f"  Pass %  : {self.pass_rate:.1f}%")
        print(f"  Duration: {self.duration_s:.1f}s")
        print("-" * width)

        failures = [c for c in self.cases if c.status == "fail"]
        if failures:
            print(f"\n  FAILURES ({len(failures)}):")
            for c in failures:
                print(f"\n  [{c.case_id}]  {c.sas_file}")
                print(f"    type   : {c.partition_type}")
                print(f"    error  : {c.error_type}")
                for d in c.details:
                    print(f"    detail : {d}")
                if c.oracle_repr:
                    print(f"    oracle :\n{_indent(c.oracle_repr)}")
                if c.actual_repr:
                    print(f"    actual :\n{_indent(c.actual_repr)}")
        print("=" * width)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)


def _indent(text: str, prefix: str = "      ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


# ── core runner ───────────────────────────────────────────────────────────────


def _load_gold_pairs(gold_dir: Path) -> list[tuple[Path, dict]]:
    """Return [(sas_path, gold_dict)] for every matching pair in gold_dir."""
    pairs: list[tuple[Path, dict]] = []
    for sas_path in sorted(gold_dir.glob("*.sas")):
        json_path = sas_path.with_suffix(".gold.json")
        if not json_path.exists():
            continue
        try:
            gold = json.loads(json_path.read_text(encoding="utf-8"))
            pairs.append((sas_path, gold))
        except Exception as exc:
            logger.warning("gold_json_load_error", file=str(json_path), error=str(exc))
    return pairs


def _partition_sas_blocks(sas_code: str) -> list[str]:
    """Naively split SAS code into DATA/PROC blocks for individual testing."""
    blocks: list[str] = []
    current: list[str] = []
    for line in sas_code.splitlines(keepends=True):
        current.append(line)
        stripped = line.strip().lower()
        if stripped == "run;" or stripped == "quit;":
            block = "".join(current).strip()
            if block:
                blocks.append(block)
            current = []
    if current:
        remaining = "".join(current).strip()
        if remaining:
            blocks.append(remaining)
    return blocks or [sas_code]


def _detect_partition_type(sas_block: str) -> str:
    """Quick regex-based partition type label for reporting."""
    s = sas_block.lower()
    if "proc sort" in s:
        return "PROC_SORT"
    if "proc means" in s:
        return "PROC_MEANS"
    if "proc freq" in s:
        return "PROC_FREQ"
    if "proc sql" in s:
        return "SQL_BLOCK"
    if "proc transpose" in s:
        return "PROC_TRANSPOSE"
    if "proc format" in s:
        return "PROC_FORMAT"
    if "%macro" in s:
        return "MACRO_DEFINITION"
    if "data " in s and "set " in s and "merge" in s:
        return "DATA_MERGE"
    if "data " in s and "retain" in s:
        return "DATA_RETAIN"
    if "data " in s and "lag(" in s:
        return "DATA_LAG"
    if "data " in s and ("first." in s or "last." in s):
        return "DATA_FIRST_LAST"
    if "data " in s:
        return "DATA_STEP"
    return "UNKNOWN"


def run_regression(
    gold_dir: Path = _GOLD_DIR,
    mode: str = "deterministic",
    verbose: bool = False,
) -> RegressionReport:
    """Run all gold-standard SAS files through the semantic oracle.

    Args:
        gold_dir:  Path to the gold standard directory.
        mode:      "deterministic" (no LLM) or "full" (uses gold.json python_code).
        verbose:   Print per-case details while running.

    Returns:
        RegressionReport with case-by-case results.
    """
    # Lazy imports to avoid circular dependencies at module level
    from partition.translation.deterministic_translator import try_deterministic
    from partition.translation.semantic_validator import SemanticValidator

    validator = SemanticValidator()
    report = RegressionReport()
    t0_total = time.perf_counter()

    pairs = _load_gold_pairs(gold_dir)
    if not pairs:
        logger.warning("regression_no_gold_pairs", gold_dir=str(gold_dir))
        report.duration_s = 0.0
        return report

    for sas_path, gold in pairs:
        try:
            sas_code = sas_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            sas_code = sas_path.read_text(encoding="utf-8", errors="replace")
        blocks = _partition_sas_blocks(sas_code)
        case_base = sas_path.stem

        for b_idx, block in enumerate(blocks):
            case_id = f"{case_base}__b{b_idx:02d}"
            ptype = _detect_partition_type(block)
            t0_case = time.perf_counter()

            try:
                # Determine which Python code to test against
                python_code: str | None = None

                if mode == "full":
                    # Try to get pre-translated Python from gold JSON
                    partitions = gold.get("partitions", [])
                    if b_idx < len(partitions):
                        python_code = partitions[b_idx].get("python_code")

                if python_code is None:
                    # Deterministic translation (no LLM)
                    det_result = try_deterministic(block)
                    python_code = det_result.code if det_result else None

                if python_code is None:
                    # No translation available → skip
                    report.cases.append(
                        CaseResult(
                            case_id=case_id,
                            sas_file=sas_path.name,
                            status="skip",
                            partition_type=ptype,
                            duration_ms=(time.perf_counter() - t0_case) * 1000,
                        )
                    )
                    report.skipped += 1
                    report.total += 1
                    continue

                # Run semantic oracle + compare
                # Build a dummy PartitionIR-like object for SemanticValidator
                dummy_partition = _DummyPartition(source_code=block, metadata={})
                result = validator.validate(dummy_partition, python_code)

                dur_ms = (time.perf_counter() - t0_case) * 1000

                if result.passed:
                    cr = CaseResult(
                        case_id=case_id,
                        sas_file=sas_path.name,
                        status="pass",
                        partition_type=ptype,
                        duration_ms=dur_ms,
                    )
                    report.passed += 1
                else:
                    cr = CaseResult(
                        case_id=case_id,
                        sas_file=sas_path.name,
                        status="fail",
                        error_type=result.error_type,
                        details=result.details,
                        oracle_repr=result.oracle_repr,
                        actual_repr=result.actual_repr,
                        partition_type=ptype,
                        duration_ms=dur_ms,
                    )
                    report.failed += 1

            except Exception as exc:
                dur_ms = (time.perf_counter() - t0_case) * 1000
                cr = CaseResult(
                    case_id=case_id,
                    sas_file=sas_path.name,
                    status="error",
                    details=[str(exc)],
                    partition_type=ptype,
                    duration_ms=dur_ms,
                )
                report.errors += 1
                logger.warning("regression_case_error", case_id=case_id, error=str(exc))

            report.cases.append(cr)
            report.total += 1
            if verbose:
                icon = (
                    "PASS" if cr.status == "pass" else ("SKIP" if cr.status == "skip" else "FAIL")
                )
                print(f"  [{icon}] {case_id:<42} {ptype:<22} {cr.duration_ms:.0f}ms")

    report.duration_s = time.perf_counter() - t0_total
    return report


# ── thin shim so SemanticValidator can accept our simple dict ─────────────────


class _DummyPartition:
    """Minimal PartitionIR-compatible object for standalone regression use."""

    def __init__(self, source_code: str, metadata: dict) -> None:
        self.source_code = source_code
        self.metadata = metadata
        self.block_id = None
        self.file_id = None


# ── CLI ───────────────────────────────────────────────────────────────────────


def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Semantic regression runner for Codara gold standard pairs"
    )
    parser.add_argument(
        "--gold-dir",
        default=str(_GOLD_DIR),
        help="Path to gold_standard/ directory",
    )
    parser.add_argument(
        "--mode",
        choices=["deterministic", "full"],
        default="deterministic",
        help="deterministic = no LLM; full = uses python_code from gold JSON",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Write JSON report to this file path",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-case results while running",
    )
    args = parser.parse_args()

    gold_dir = Path(args.gold_dir)
    if not gold_dir.exists():
        print(f"ERROR: gold_dir not found: {gold_dir}", file=sys.stderr)
        sys.exit(2)

    report = run_regression(
        gold_dir=gold_dir,
        mode=args.mode,
        verbose=args.verbose,
    )
    report.print_summary()

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.to_json(), encoding="utf-8")
        print(f"\nJSON report written to: {out_path}")

    sys.exit(0 if report.failed == 0 and report.errors == 0 else 1)


if __name__ == "__main__":
    _cli()
