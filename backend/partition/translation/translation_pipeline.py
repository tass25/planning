"""TranslationPipeline — end-to-end L3 pipeline.

translate → validate → retry loop with DuckDB quality logging.

Enhancements over baseline:
  - Retry budget differentiation: MACRO/SQL get +1 extra retry; semantic
    errors (exec fails but syntax passes) get +1 extra retry.
  - Stagnation detection: stops retrying when consecutive corrections
    produce no change in generated code (avoids wasting API calls).
  - Error classification + analysis injected into retry context so the
    translator receives a targeted repair hint.
"""

from __future__ import annotations

import asyncio

import structlog

from partition.models.conversion_result import ConversionResult
from partition.models.enums import ConversionStatus, RiskLevel, VerificationStatus
from partition.models.partition_ir import PartitionIR
from partition.orchestration.audit import _get_duckdb
from partition.translation.error_analyst import analyse_error
from partition.translation.error_classifier import SYNTAX, classify_error
from partition.translation.lineage_guard import build_internal_table_set, full_lineage_check
from partition.translation.semantic_validator import SemanticValidator
from partition.translation.translation_agent import TranslationAgent
from partition.translation.validation_agent import ValidationAgent
from partition.verification.z3_agent import Z3VerificationAgent

logger = structlog.get_logger()

# Lazy type hints to avoid circular imports at module level
# CDAISRunner and InvariantSet are imported inside __init__ / methods

# ── Retry budget constants ────────────────────────────────────────────────────
_BASE_RETRIES = 2  # default max validation retries
_MACRO_SQL_BONUS = 1  # extra retry for MACRO_DEFINITION / SQL_BLOCK
_SEMANTIC_ERROR_BONUS = 1  # extra retry when syntax passes but exec fails
_MAX_STAGNANT = 2  # stop if code unchanged for this many consecutive retries


def _retry_budget(partition: PartitionIR) -> int:
    """Compute the retry budget for a partition based on its type."""
    budget = _BASE_RETRIES
    ptype = partition.partition_type.value
    if ptype in ("MACRO_DEFINITION", "MACRO_INVOCATION", "SQL_BLOCK"):
        budget += _MACRO_SQL_BONUS
    return budget


class TranslationPipeline:
    """End-to-end L3 pipeline: translate → validate → retry loop."""

    MAX_VALIDATION_RETRIES = _BASE_RETRIES

    def __init__(
        self,
        target_runtime: str = "python",
        duckdb_path: str = "data/analytics.duckdb",
        translator: TranslationAgent | None = None,
        validator: ValidationAgent | None = None,
        z3: Z3VerificationAgent | None = None,
        sem_validator: SemanticValidator | None = None,
        cdais: object | None = None,
        invariant_set: object | None = None,
    ):
        from partition.testing.cdais.cdais_runner import CDAISRunner

        self.translator = translator or TranslationAgent(target_runtime=target_runtime)
        self.validator = validator or ValidationAgent()
        self.z3 = z3 or Z3VerificationAgent()
        self.sem_validator = sem_validator or SemanticValidator()
        self.cdais = cdais or CDAISRunner()
        self.invariant_set = invariant_set  # None = MIS disabled; call load_invariants() to enable
        self.duckdb_path = duckdb_path

    def load_invariants(self, gold_dir: str | None = None) -> None:
        """Synthesize MIS invariants from the gold corpus (blocking — call in a thread)."""
        from partition.invariant.invariant_synthesizer import MigrationInvariantSynthesizer

        synth = MigrationInvariantSynthesizer(gold_standard_dir=gold_dir)
        self.invariant_set = synth.synthesize()
        logger.info(
            "mis_invariants_loaded",
            confirmed=len(self.invariant_set.confirmed),
            rejected=len(self.invariant_set.rejected),
        )

    # Per-partition wall-clock timeout (seconds).  The underlying LLM clients
    # have their own connect timeouts; this outer guard prevents a single
    # stalled partition from blocking the entire pipeline.
    PARTITION_TIMEOUT_S: int = 120

    async def translate_partition(self, partition: PartitionIR) -> ConversionResult:
        """Full translate → validate → retry loop for one partition."""
        try:
            return await asyncio.wait_for(
                self._translate_partition_inner(partition),
                timeout=self.PARTITION_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error(
                "translate_partition_timeout",
                block_id=str(partition.block_id),
                timeout_s=self.PARTITION_TIMEOUT_S,
            )
            import uuid

            from partition.models.enums import ConversionStatus

            return ConversionResult(
                conversion_id=uuid.uuid4(),
                block_id=partition.block_id,
                file_id=partition.file_id,
                python_code=f"# PARTIAL: Translation timed out after {self.PARTITION_TIMEOUT_S}s\n",
                status=ConversionStatus.PARTIAL,
                model_used="timeout",
            )

    async def _translate_partition_inner(self, partition: PartitionIR) -> ConversionResult:
        """Inner translate → validate → retry loop (no timeout guard here).

        Retry behaviour:
          - Budget: base 2 + 1 for MACRO/SQL + 1 for semantic (exec) errors.
          - Stagnation: stops when ``_MAX_STAGNANT`` consecutive retries
            produce identical code.
          - Error context: injects ErrorAnalysis into partition metadata so
            the translator can give targeted guidance on the next attempt.
        """
        conversion = await self.translator.process(partition)

        # Skip validation for already-PARTIAL translations
        if conversion.status == ConversionStatus.PARTIAL:
            self._log_quality(conversion)
            return conversion

        # Validate
        test_type = partition.metadata.get("test_coverage_type", "full")
        validation = await self.validator.validate(conversion, test_type)

        max_retries = _retry_budget(partition)
        retry_count = 0
        stagnant = 0
        last_code = conversion.python_code

        while not validation.passed and retry_count < max_retries:
            # Classify and analyse the error
            err_report = classify_error(
                validation.error_msg,
                getattr(validation, "traceback", ""),
                conversion.python_code,
            )
            err_analysis = analyse_error(
                err_report,
                sas_code=partition.source_code,
                python_code=conversion.python_code,
                partition_type=partition.partition_type.value,
            )

            # Semantic errors (syntax ok, exec fails) get one extra attempt
            if (
                err_report.primary_category != SYNTAX
                and validation.syntax_ok
                and not getattr(validation, "exec_ok", True)
                and retry_count == max_retries - 1
            ):
                max_retries += _SEMANTIC_ERROR_BONUS

            retry_count += 1
            logger.info(
                "validation_retry",
                block_id=str(partition.block_id),
                attempt=retry_count,
                max=max_retries,
                error_category=err_report.primary_category,
                error=validation.error_msg[:120],
            )

            # Build repair hint: structured error analysis + EGS execution state
            hint_parts = [err_analysis.to_prompt_block()]
            egs_block = validation.egs_context_block()
            if egs_block:
                hint_parts.append(egs_block)
            partition.metadata["error_analysis_hint"] = "\n\n".join(hint_parts)
            partition.metadata["error_category"] = err_report.primary_category

            prev_conversion = conversion
            try:
                conversion = await self.translator.process(partition)
            finally:
                # Always clean up — even if process() raises mid-way
                partition.metadata.pop("error_analysis_hint", None)
                partition.metadata.pop("error_category", None)

            if conversion.status == ConversionStatus.PARTIAL:
                break

            # Stagnation check — stop if code hasn't changed
            if conversion.python_code == last_code:
                stagnant += 1
                if stagnant >= _MAX_STAGNANT:
                    logger.warning(
                        "validation_stagnation",
                        block_id=str(partition.block_id),
                        stagnant_count=stagnant,
                    )
                    conversion = prev_conversion
                    break
            else:
                stagnant = 0
                last_code = conversion.python_code

            validation = await self.validator.validate(conversion, test_type)

        if not validation.passed:
            conversion.status = ConversionStatus.PARTIAL
            conversion.python_code = (
                f"# PARTIAL: Validation failed ({validation.error_msg})\n" + conversion.python_code
            )
        else:
            conversion.validation_passed = True

            # ── Lineage guard (static, cheap — no LLM call unless violations found)
            internal_tables = build_internal_table_set(partition.source_code or "")
            lin_report, mac_report = full_lineage_check(conversion.python_code, internal_tables)
            lineage_hint_parts: list[str] = []
            if not lin_report.ok:
                lineage_hint_parts.append(lin_report.to_prompt_block())
            if not mac_report.ok:
                lineage_hint_parts.append(mac_report.to_prompt_block())
            if lineage_hint_parts:
                logger.warning(
                    "lineage_violation",
                    block_id=str(partition.block_id),
                    n_violations=len(lin_report.violations) + len(mac_report.violations),
                )
                partition.metadata["error_analysis_hint"] = "\n\n".join(lineage_hint_parts)
                partition.metadata["error_category"] = "LINEAGE"
                try:
                    repaired = await self.translator.process(partition)
                    if repaired.status != ConversionStatus.PARTIAL:
                        conversion = repaired
                        retry_count += 1
                finally:
                    partition.metadata.pop("error_analysis_hint", None)
                    partition.metadata.pop("error_category", None)

            # ── Semantic oracle check (oracle-computed expected vs actual output)
            sem_result = await asyncio.to_thread(
                self.sem_validator.validate,
                partition,
                conversion.python_code,
            )
            if not sem_result.passed:
                logger.warning(
                    "semantic_oracle_failure",
                    block_id=str(partition.block_id),
                    error_type=sem_result.error_type,
                )
                partition.metadata["error_analysis_hint"] = sem_result.to_repair_hint()
                partition.metadata["error_category"] = sem_result.error_type
                try:
                    repaired = await self.translator.process(partition)
                    if repaired.status != ConversionStatus.PARTIAL:
                        conversion = repaired
                        retry_count += 1
                finally:
                    partition.metadata.pop("error_analysis_hint", None)
                    partition.metadata.pop("error_category", None)

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
                hint_parts.append("You MUST fix this specific bug. Do NOT change anything else.")
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

            # ── CDAIS coverage check (post-Z3, issues formal certificates) ──
            cdais_report = await asyncio.to_thread(
                self.cdais.run, partition, conversion.python_code
            )
            conversion.cdais_all_passed = cdais_report.all_passed
            conversion.cdais_certificates = cdais_report.certificates
            conversion.cdais_failures_count = len(cdais_report.failures)
            if cdais_report.n_classes_checked > 0:
                logger.info(
                    "cdais_complete",
                    block_id=str(partition.block_id),
                    summary=cdais_report.summary(),
                )
            if not cdais_report.all_passed:
                logger.warning(
                    "cdais_failures",
                    block_id=str(partition.block_id),
                    n_failures=len(cdais_report.failures),
                )
                partition.metadata["error_analysis_hint"] = cdais_report.to_prompt_block()
                partition.metadata["error_category"] = "CDAIS"
                try:
                    repaired = await self.translator.process(partition)
                    if repaired.status != ConversionStatus.PARTIAL:
                        conversion = repaired
                        retry_count += 1
                        conversion.cdais_all_passed = True
                finally:
                    partition.metadata.pop("error_analysis_hint", None)
                    partition.metadata.pop("error_category", None)
            else:
                partition.metadata["cdais_certificates"] = cdais_report.certificates

            # ── MIS invariant check (catches errors outside the 6 CDAIS classes) ──
            if self.invariant_set is not None:
                inv_violations = await asyncio.to_thread(
                    self.invariant_set.check_translation,
                    partition.source_code or "",
                    conversion.python_code,
                )
                conversion.mis_violations = inv_violations
                # Namespace violations = column-schema invariants surfaced to UI
                conversion.namespace_violations = [
                    v
                    for v in inv_violations
                    if any(kw in v for kw in ("COLUMN", "DTYPE", "NAMESPACE", "SUPERSET"))
                ]
                if inv_violations:
                    logger.warning(
                        "mis_invariant_violations",
                        block_id=str(partition.block_id),
                        violations=inv_violations,
                    )
                    inv_hint = (
                        "## MIS Invariant Violations\n\n"
                        + "\n".join(f"- `{v}`" for v in inv_violations)
                        + "\n\nFix the translation to satisfy all confirmed migration invariants."
                    )
                    partition.metadata["error_analysis_hint"] = inv_hint
                    partition.metadata["error_category"] = "MIS_INVARIANT"
                    try:
                        repaired = await self.translator.process(partition)
                        if repaired.status != ConversionStatus.PARTIAL:
                            conversion = repaired
                            retry_count += 1
                    finally:
                        partition.metadata.pop("error_analysis_hint", None)
                        partition.metadata.pop("error_category", None)

        conversion.retry_count = retry_count
        self._log_quality(conversion)
        return conversion

    async def translate_batch(self, partitions: list[PartitionIR]) -> list[ConversionResult]:
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
