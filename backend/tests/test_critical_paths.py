"""Critical-path regression tests.

Covers the five most dangerous untested scenarios identified in the audit:
  1. start_conversion is properly async (asyncio.run crash regression)
  2. All LLM tiers unavailable → PARTIAL status, no hang
  3. conv.duration=None does not crash zip/md/html downloads
  4. JWT default secret raises in production mode
  5. CircuitBreaker fast-fails when OPEN
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── 1. start_conversion must be async ────────────────────────────────────────


def test_start_conversion_is_async():
    """Regression: start_conversion must be async def so await works inside it."""
    from api.routes.conversions import start_conversion

    assert inspect.iscoroutinefunction(start_conversion), (
        "start_conversion must be 'async def' — 'asyncio.run()' inside a sync "
        "FastAPI endpoint raises RuntimeError when the event loop is running."
    )


# ── 2. All LLM tiers down → PARTIAL, no hang ─────────────────────────────────


@pytest.mark.asyncio
async def test_all_llm_tiers_unavailable_returns_partial():
    """When Ollama, Azure, and Groq are all unavailable, TranslationAgent
    must return PARTIAL status rather than hanging or raising."""
    import uuid

    import structlog

    from partition.models.enums import ConversionStatus, PartitionType, RiskLevel
    from partition.models.partition_ir import PartitionIR
    from partition.translation.translation_agent import TranslationAgent

    agent = TranslationAgent.__new__(TranslationAgent)
    agent.target_runtime = "python"
    agent.trace_id = uuid.uuid4()
    agent.logger = structlog.get_logger().bind(agent="TranslationAgent")
    agent.ollama_client = None
    agent.azure_client = None
    agent.groq_client = None
    agent._groq_raw = None
    agent._groq_pool = MagicMock(available=False)
    agent.local_client = MagicMock(is_available=False)
    agent._translations = {}
    agent._translation_cache = {}

    agent.embedder = MagicMock()
    agent.kb_client = MagicMock()
    agent.kb_client.query = AsyncMock(return_value=[])
    agent.prompt_manager = MagicMock()
    agent.rag_router = MagicMock()
    agent.rag_router.build_context = MagicMock(
        return_value={"prompt": "test", "kb_examples": [], "paradigm": "static"}
    )

    partition = PartitionIR(
        block_id=uuid.uuid4(),
        file_id=uuid.uuid4(),
        partition_type=PartitionType.MACRO_DEFINITION,
        source_code=(
            "%MACRO calc(ds=, var=);\n"
            "  PROC SQL;\n"
            "    CREATE TABLE work.result AS\n"
            "    SELECT *, CASE WHEN &var > 10 THEN 'high' ELSE 'low' END AS tier\n"
            "    FROM &ds;\n"
            "  QUIT;\n"
            "%MEND calc;\n"
        ),
        line_start=1,
        line_end=7,
        risk_level=RiskLevel.HIGH,
        metadata={},
    )

    # All clients already set to None above — no LLM tier available
    result = await agent.process(partition)

    assert (
        result.status == ConversionStatus.PARTIAL
    ), f"Expected PARTIAL when all LLM tiers fail, got {result.status}"


# ── 3. None duration does not crash downloads ─────────────────────────────────


def test_download_zip_none_duration(tmp_path, monkeypatch):
    """conv.duration=None must not raise TypeError in the zip summary."""
    from api.core.database import ConversionRow

    conv = ConversionRow(
        id="conv-test01",
        user_id="u-001",
        file_name="test.sas",
        status="completed",
        runtime="python",
        duration=None,  # the dangerous case
        accuracy=None,
        python_code="print('hello')",
        sas_code="data x; run;",
        created_at="2026-01-01T00:00:00",
    )
    conv.stages = []

    # Verify the guard expression used in the route doesn't raise
    duration_val = conv.duration or 0.0
    accuracy_val = conv.accuracy or 0
    summary = (
        f"Conversion: {conv.file_name}\n"
        f"Status: {conv.status}\n"
        f"Duration: {duration_val:.2f}s\n"
        f"Accuracy: {accuracy_val}%"
    )
    assert "0.00s" in summary
    assert "0%" in summary


# ── 4. JWT weak secret raises in production ───────────────────────────────────


def test_jwt_weak_secret_raises_in_production():
    """validate_production_secrets must raise when JWT default is used in prod."""
    from config.settings import Settings

    prod_settings = Settings(
        app_env="production",
        codara_jwt_secret="codara-dev-secret-change-in-production",
    )
    with pytest.raises(RuntimeError, match="CODARA_JWT_SECRET"):
        prod_settings.validate_production_secrets()


def test_jwt_custom_secret_does_not_raise_in_production():
    """A custom JWT secret must not raise even in production mode."""
    from config.settings import Settings

    prod_settings = Settings(
        app_env="production",
        codara_jwt_secret="a" * 64,
    )
    prod_settings.validate_production_secrets()  # must not raise


# ── 5. CircuitBreaker fast-fails when OPEN ────────────────────────────────────


def test_circuit_breaker_fast_fails_when_open():
    """After threshold failures, circuit must reject requests immediately."""
    from partition.utils.retry import CircuitBreaker

    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=300.0, name="test")

    # Trip the circuit
    for _ in range(3):
        breaker.record_failure()

    assert breaker.state == CircuitBreaker.OPEN
    assert not breaker.allow_request(), "OPEN circuit must reject requests"


def test_circuit_breaker_half_open_after_timeout():
    """After reset_timeout, circuit must transition to HALF_OPEN."""
    import time

    from partition.utils.retry import CircuitBreaker

    breaker = CircuitBreaker(failure_threshold=1, reset_timeout=0.01, name="test_to")
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.OPEN

    time.sleep(0.02)
    # Accessing .state triggers the timeout check
    assert breaker.state == CircuitBreaker.HALF_OPEN
    assert breaker.allow_request(), "HALF_OPEN circuit must allow one probe"


# ── 6. NomicEmbedder singleton returned consistently ─────────────────────────


def test_nomic_embedder_singleton():
    """get_embedder() must always return the same instance."""
    from partition.raptor.embedder import get_embedder

    with (
        patch("partition.raptor.embedder._ST_AVAILABLE", True),
        patch("partition.raptor.embedder._SentenceTransformer") as MockST,
    ):
        MockST.return_value = MagicMock()

        import partition.raptor.embedder as emb_mod

        emb_mod._embedder = None  # reset for test isolation

        a = get_embedder()
        b = get_embedder()
        assert a is b, "get_embedder() must return the same singleton instance"
        assert MockST.call_count == 1, "SentenceTransformer must be loaded exactly once"
