"""TranslationPipeline — end-to-end L3 pipeline.

translate → validate → retry loop with DuckDB quality logging.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import structlog

from partition.models.partition_ir import PartitionIR
from partition.models.conversion_result import ConversionResult
from partition.models.enums import ConversionStatus
from partition.orchestration.audit import _get_duckdb
from partition.translation.translation_agent import TranslationAgent
from partition.translation.validation_agent import ValidationAgent, ValidationResult

logger = structlog.get_logger()


class TranslationPipeline:
    """End-to-end L3 pipeline: translate → validate → retry loop."""

    MAX_VALIDATION_RETRIES = 2

    def __init__(
        self,
        target_runtime: str = "python",
        duckdb_path: str = "analytics.duckdb",
    ):
        self.translator = TranslationAgent(
            target_runtime=target_runtime,
        )
        self.validator = ValidationAgent()
        self.duckdb_path = duckdb_path

    async def translate_partition(
        self, partition: PartitionIR
    ) -> ConversionResult:
        """Full translate → validate → retry loop for one partition."""
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
