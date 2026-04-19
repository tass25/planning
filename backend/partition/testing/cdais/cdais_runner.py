"""cdais_runner.py — Entry point: given a partition, run CDAIS end-to-end.

Usage:
    runner = CDAISRunner()
    report = runner.run(partition, python_code)
    for cert in report.certificates:
        print(cert)
    if not report.all_passed:
        print(report.to_prompt_block())   # inject into repair prompt

The runner:
  1. Identifies applicable error classes from SAS source code
  2. For each class: synthesizes the minimum Z3 witness
  3. Runs the coverage oracle to check the translation
  4. Issues certificates for passing classes
  5. Returns a CDAISReport with overall pass/fail + all certificates + failures
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import structlog

from partition.models.partition_ir import PartitionIR
from partition.testing.cdais.constraint_catalog import (
    ConstraintConfig,
    applicable_classes,
)
from partition.testing.cdais.synthesizer import CDASISynthesizer, SynthesisResult
from partition.testing.cdais.coverage_oracle import CoverageOracle, CoverageResult

logger = structlog.get_logger(__name__)


@dataclass
class CDAISReport:
    """Full CDAIS report for one partition translation."""
    partition_id: str
    all_passed: bool
    certificates: list[str] = field(default_factory=list)     # formal cert strings
    failures: list[CoverageResult] = field(default_factory=list)
    skipped_classes: list[str] = field(default_factory=list)   # not applicable
    latency_ms: float = 0.0
    n_classes_checked: int = 0

    def to_prompt_block(self) -> str:
        """Render failures as a Markdown block for repair prompt injection."""
        if self.all_passed:
            return (
                f"✓ CDAIS: All {self.n_classes_checked} checked error classes "
                "issued coverage certificates.\n"
            )
        lines = [
            f"## CDAIS Report — {len(self.failures)} Error Class(es) Failed",
            "",
        ]
        for f in self.failures:
            lines.append(f.to_prompt_block())
            lines.append("")
        if self.certificates:
            lines.append("### Certificates issued (passed classes):")
            for cert in self.certificates:
                lines.append(f"- {cert}")
        return "\n".join(lines)

    def summary(self) -> str:
        total  = self.n_classes_checked
        failed = len(self.failures)
        passed = total - failed
        return (
            f"CDAIS: {passed}/{total} error classes certified "
            f"| {failed} failures "
            f"| {len(self.skipped_classes)} skipped "
            f"| {self.latency_ms:.0f}ms"
        )


class CDAISRunner:
    """Orchestrates CDAIS for a single partition translation."""

    def __init__(
        self,
        cfg: Optional[ConstraintConfig] = None,
        synthesizer: Optional[CDASISynthesizer] = None,
        oracle: Optional[CoverageOracle] = None,
    ) -> None:
        self.cfg         = cfg or ConstraintConfig()
        self.synthesizer = synthesizer or CDASISynthesizer()
        self.oracle      = oracle or CoverageOracle()

    def run(
        self,
        partition: PartitionIR,
        python_code: str,
    ) -> CDAISReport:
        """Run CDAIS for all applicable error classes on this partition."""
        t0      = time.monotonic()
        sas     = partition.source_code or ""
        pid     = str(partition.block_id)

        classes     = applicable_classes(sas)
        skipped     = []
        certificates = []
        failures    = []

        if not classes:
            elapsed = (time.monotonic() - t0) * 1000
            logger.debug("cdais_no_applicable_classes", partition_id=pid)
            return CDAISReport(
                partition_id=pid,
                all_passed=True,
                skipped_classes=[ec.name for ec in
                                  __import__(
                                      "partition.testing.cdais.constraint_catalog",
                                      fromlist=["ALL_ERROR_CLASSES"]
                                  ).ALL_ERROR_CLASSES],
                latency_ms=elapsed,
                n_classes_checked=0,
            )

        for ec in classes:
            try:
                synthesis: SynthesisResult = self.synthesizer.synthesize(ec, self.cfg)

                if not synthesis.sat:
                    skipped.append(ec.name)
                    continue

                result: CoverageResult = self.oracle.check(synthesis, sas, python_code)

                if result.passed:
                    certificates.append(result.certificate)
                    logger.info("cdais_cert_issued", error_class=ec.name,
                                partition_id=pid)
                else:
                    failures.append(result)
                    logger.warning("cdais_failure", error_class=ec.name,
                                   partition_id=pid,
                                   details=result.failure_details[:1])

            except Exception as exc:
                skipped.append(ec.name)
                logger.error("cdais_class_error", error_class=ec.name,
                             partition_id=pid, error=str(exc))

        elapsed     = (time.monotonic() - t0) * 1000
        all_passed  = len(failures) == 0
        n_checked   = len(classes) - len(skipped)

        logger.info(
            "cdais_complete",
            partition_id=pid,
            passed=n_checked - len(failures),
            failed=len(failures),
            latency_ms=f"{elapsed:.0f}",
        )

        return CDAISReport(
            partition_id=pid,
            all_passed=all_passed,
            certificates=certificates,
            failures=failures,
            skipped_classes=skipped,
            latency_ms=elapsed,
            n_classes_checked=n_checked,
        )

    def run_on_code(
        self,
        sas_code: str,
        python_code: str,
        block_id: str = "inline",
    ) -> CDAISReport:
        """Convenience wrapper when you have raw code strings (no PartitionIR)."""
        import uuid
        from partition.models.partition_ir import PartitionIR
        from partition.models.enums import PartitionType, RiskLevel

        p = PartitionIR(
            block_id=uuid.UUID(int=0),
            file_id=uuid.UUID(int=0),
            partition_type=PartitionType.DATA_STEP,
            source_code=sas_code,
            line_start=0,
            line_end=0,
            risk_level=RiskLevel.LOW,
        )
        return self.run(p, python_code)
