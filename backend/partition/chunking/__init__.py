"""L2-C Chunking Layer — public API.

Agents:
    BoundaryDetectorAgent  — deterministic + LLM boundary detection
    PartitionBuilderAgent  — BlockBoundaryEvent → PartitionIR

Helpers:
    BoundaryDetector       — pure rule-based detector (no LLM)
    LLMBoundaryResolver    — Groq (default) / Azure OpenAI / Ollama resolver
Models:
    BlockBoundaryEvent     — detection event emitted per SAS block
"""

from .boundary_detector import BoundaryDetector, BoundaryDetectorAgent
from .llm_boundary_resolver import LLMBoundaryResolver
from .models import COVERAGE_MAP, BlockBoundaryEvent
from .partition_builder import PartitionBuilderAgent

__all__ = [
    "BlockBoundaryEvent",
    "COVERAGE_MAP",
    "BoundaryDetector",
    "BoundaryDetectorAgent",
    "LLMBoundaryResolver",
    "PartitionBuilderAgent",
]
