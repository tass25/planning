"""RAPTORNode — one node in the RAPTOR semantic tree."""

from __future__ import annotations

from uuid import UUID, uuid4
from typing import Optional

from pydantic import BaseModel, Field


class RAPTORNode(BaseModel):
    """A node in the RAPTOR tree built for a single SAS file.

    Levels:
        0 — leaf (one PartitionIR block)
        1 — first clustering pass
        2+ — higher-level summaries
        max_depth — root (whole-file summary)
    """

    node_id: UUID = Field(default_factory=uuid4)
    level: int
    summary: str
    summary_tier: str  # "skipped" | "groq" | "ollama_fallback" | "heuristic_fallback" | "cached"
    embedding: list[float]
    child_ids: list[str] = Field(default_factory=list)
    cluster_label: Optional[int] = None
    file_id: UUID
    partition_ids: list[str] = Field(default_factory=list)
