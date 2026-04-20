"""FileMetadata Pydantic model — produced by FileAnalysisAgent."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class FileMetadata(BaseModel):
    """Metadata collected during the initial file scan.

    Attributes:
        file_id: Unique identifier for this file instance.
        file_path: Absolute or project-relative path to the .sas file.
        encoding: Detected character encoding (e.g. 'utf-8', 'ISO-8859-1').
        content_hash: SHA-256 hex digest of the raw file bytes.
        file_size_bytes: Size in bytes.
        line_count: Number of lines in the decoded content.
        lark_valid: Whether the file passed Lark pre-validation.
        lark_errors: List of error messages from the pre-validator.
        created_at: Timestamp when this metadata was generated.
    """

    file_id: UUID = Field(default_factory=uuid4)
    file_path: str
    encoding: str
    content_hash: str
    file_size_bytes: int
    line_count: int
    lark_valid: bool
    lark_errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
