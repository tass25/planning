"""L2-C Chunking Layer — public API.

Agents:
    BoundaryDetectorAgent  — deterministic + LLM boundary detection
    PartitionBuilderAgent  — BlockBoundaryEvent → PartitionIR

Helpers:
    BoundaryDetector       — pure rule-based detector (no LLM)
    LLMBoundaryResolver    — Ollama / Azure OpenAI resolver

Models:
    BlockBoundaryEvent     — detection event emitted per SAS block
"""

from .models import BlockBoundaryEvent, COVERAGE_MAP
from .boundary_detector import BoundaryDetector, BoundaryDetectorAgent
from .llm_boundary_resolver import LLMBoundaryResolver
from .partition_builder import PartitionBuilderAgent

__all__ = [
    "BlockBoundaryEvent",
    "COVERAGE_MAP",
    "BoundaryDetector",
    "BoundaryDetectorAgent",
    "LLMBoundaryResolver",
    "PartitionBuilderAgent",
]
