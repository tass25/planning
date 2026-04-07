"""ConversionResult — output model for L3 translation pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any

from pydantic import BaseModel, Field

from .enums import ConversionStatus, VerificationStatus


class ConversionResult(BaseModel):
    """Result of translating a single SAS partition to Python.

    Produced by TranslationAgent (#12) and refined by ValidationAgent (#13).
    Z3 fields populated by Z3VerificationAgent after validation.
    """

    conversion_id: UUID = Field(default_factory=uuid4)
    block_id: UUID
    file_id: UUID
    python_code: str
    imports_detected: list[str] = Field(default_factory=list)
    status: ConversionStatus = ConversionStatus.HUMAN_REVIEW
    llm_confidence: float = 0.0
    failure_mode_flagged: str = ""
    model_used: str = ""
    kb_examples_used: list[str] = Field(default_factory=list)
    retry_count: int = 0
    validation_passed: bool = False
    trace_id: UUID = Field(default_factory=uuid4)
    rag_paradigm: str = ""
    # Z3 formal verification fields (populated by Z3VerificationAgent)
    z3_status: VerificationStatus = VerificationStatus.SKIPPED
    z3_pattern: str = ""          # which Z3 pattern matched (e.g. "linear_arithmetic")
    z3_latency_ms: float = 0.0
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
