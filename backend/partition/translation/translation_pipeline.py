"""TranslationPipeline — end-to-end L3 pipeline.

translate → validate → retry loop with DuckDB quality logging.
"""

from __future__ import annotations

import asyncio

import structlog

from partition.models.partition_ir import PartitionIR
from partition.models.conversion_result import ConversionResult
from partition.models.enums import ConversionStatus, RiskLevel, VerificationStatus
from partition.orchestration.audit import _get_duckdb
from partition.translation.translation_agent import TranslationAgent
from partition.translation.validation_agent import ValidationAgent, ValidationResult
from partition.verification.z3_agent import Z3VerificationAgent

logger = structlog.get_logger()


class TranslationPipeline:
    """End-to-end L3 pipeline: translate → validate → retry loop."""

    MAX_VALIDATION_RETRIES = 2

    def __init__(
        self,
        target_runtime: str = "python",
        duckdb_path: str = "data/analytics.duckdb",
        translator: TranslationAgent | None = None,
        validator: ValidationAgent | None = None,
        z3: Z3VerificationAgent | None = None,
    ):
        self.translator = translator or TranslationAgent(target_runtime=target_runtime)
        self.validator = validator or ValidationAgent()
        self.z3 = z3 or Z3VerificationAgent()
        self.duckdb_path = duckdb_path

    # Per-partition wall-clock timeout (seconds).  The underlying LLM clients
    # have their own connect timeouts; this outer guard prevents a single
    # stalled partition from blocking the entire pipeline.
    PARTITION_TIMEOUT_S: int = 120

    async def translate_partition(
        self, partition: PartitionIR
    ) -> ConversionResult:
        """Full translate → validate → retry loop for one partition."""
        try:
            async with asyncio.timeout(self.PARTITION_TIMEOUT_S):
                return await self._translate_partition_inner(partition)
        except TimeoutError:
            logger.error(
                "translate_partition_timeout",
                block_id=str(partition.block_id),
                timeout_s=self.PARTITION_TIMEOUT_S,
            )
            from partition.models.enums import ConversionStatus
            import uuid
            return ConversionResult(
                conversion_id=uuid.uuid4(),
                block_id=partition.block_id,
                file_id=partition.file_id,
                python_code=f"# PARTIAL: Translation timed out after {self.PARTITION_TIMEOUT_S}s\n",
                status=ConversionStatus.PARTIAL,
                model_used="timeout",
            )

    async def _translate_partition_inner(
        self, partition: PartitionIR
    ) -> ConversionResult:
        """Inner translate → validate → retry loop (no timeout guard here)."""
        conversion = await self.translator.process(partition)

        # Skip validation for already-PARTIAL translations
        if conversion.status == ConversionStatus.PARTIAL:
            self._log_quality(conversion)
            return conversion

        # Validate
        test_type = partition.metadata.get("test_coverage_type", "full")
        validation = await self.validator.validate(conversion, test_type)

        retry_count = 0
        while (
            not validation.passed
            and retry_count < self.MAX_VALIDATION_RETRIES
        ):
            retry_count += 1
            logger.info(
                "validation_retry",
                block_id=str(partition.block_id),
                attempt=retry_count,
                error=validation.error_msg,
            )
            conversion = await self.translator.process(partition)
            if conversion.status == ConversionStatus.PARTIAL:
                break
            validation = await self.validator.validate(conversion, test_type)

        if not validation.passed:
            conversion.status = ConversionStatus.PARTIAL
            conversion.python_code = (
                f"# PARTIAL: Validation failed ({validation.error_msg})\n"
                + conversion.python_code
            )
        else:
            conversion.validation_passed = True

            # Z3 formal verification (only when validation passed, non-blocking)
            z3_result = await asyncio.to_thread(
                self.z3.verify,
                partition.source_code,
                conversion.python_code,
            )
            conversion.z3_status = VerificationStatus(z3_result.status.value)
            conversion.z3_pattern = z3_result.pattern
            conversion.z3_latency_ms = z3_result.latency_ms

            if z3_result.status.value == "counterexample":
                # CEGAR repair: build a precise repair prompt from the Z3 witness
                # and inject it into partition metadata so the translator uses it.
                cx = z3_result.counterexample
                hint_parts = [
                    "## Z3 Formal Verification Found a Semantic Bug",
                    f"Pattern checked : {z3_result.pattern}",
                    f"Issue           : {cx.get('issue', 'Semantic mismatch detected')}",
                ]
                if cx.get("witness_x"):
                    hint_parts.append(
                        f"Counterexample  : at x = {cx['witness_x']}, "
                        "SAS and Python produce different results"
                    )
                for key in ("expected", "got", "wrong_columns", "wrong"):
                    if cx.get(key):
                        hint_parts.append(f"{key.capitalize():16}: {cx[key]}")
                if cx.get("hint"):
                    hint_parts.append(f"Fix             : {cx['hint']}")
                if cx.get("fix"):
                    hint_parts.append(f"Fix             : {cx['fix']}")
                hint_parts.append(
                    "You MUST fix this specific bug. Do NOT change anything else."
                )
                z3_repair_hint = "\n".join(hint_parts)

                logger.warning(
                    "z3_counterexample_cegar",
                    block_id=str(partition.block_id),
                    pattern=z3_result.pattern,
                    issue=cx.get("issue", ""),
                )

                # Inject hint into metadata and force HIGH risk for full agentic retry
                partition.metadata["z3_repair_hint"] = z3_repair_hint
                partition.risk_level = RiskLevel.HIGH
                conversion = await self.translator.process(partition)
                if conversion.status != ConversionStatus.PARTIAL:
                    conversion.validation_passed = True
                    # Run Z3 again to confirm the repair worked
                    z3_recheck = await asyncio.to_thread(
                        self.z3.verify,
                        partition.source_code,
                        conversion.python_code,
                    )
                    conversion.z3_status = VerificationStatus(z3_recheck.status.value)
                    conversion.z3_pattern = z3_recheck.pattern
                    conversion.z3_latency_ms += z3_recheck.latency_ms
                    logger.info(
                        "z3_cegar_recheck",
                        block_id=str(partition.block_id),
                        status=z3_recheck.status.value,
                    )
                # Clean up hint from metadata to avoid leaking into future blocks
                partition.metadata.pop("z3_repair_hint", None)

        conversion.retry_count = retry_count
        self._log_quality(conversion)
        return conversion

    async def translate_batch(
        self, partitions: list[PartitionIR]
    ) -> list[ConversionResult]:
        """Translate a batch of partitions (sequential for rate limiting)."""
        results = []
        for partition in partitions:
            result = await self.translate_partition(partition)
            results.append(result)
            await asyncio.sleep(0.1)
        return results

    def _log_quality(self, conversion: ConversionResult):
        """Log translation result to DuckDB conversion_results table."""
        try:
            con = _get_duckdb(self.duckdb_path)
            con.execute(
                """
                INSERT INTO conversion_results
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    str(conversion.conversion_id),
                    str(conversion.block_id),
                    str(conversion.file_id),
                    conversion.python_code[:10000],
                    str(conversion.imports_detected),
                    conversion.status.value,
                    conversion.llm_confidence,
                    conversion.failure_mode_flagged,
                    conversion.model_used,
                    str(conversion.kb_examples_used),
                    conversion.retry_count,
                    str(conversion.trace_id),
                ],
            )
        except Exception as e:
            logger.warning("quality_log_failed", error=str(e))
