"""Conversion service — presentation mapping and stage constants.

Extracted from api.routes.conversions to keep route handlers thin.
"""

from __future__ import annotations

import json

from api.core.schemas import ConversionOut, PipelineStageInfo

# Display stage names surfaced to the frontend (matches frontend/src/types/index.ts PipelineStage)
STAGES: list[str] = [
    "file_process",
    "sas_partition",
    "strategy_select",
    "translate",
    "validate",
    "repair",
    "merge",
    "finalize",
]

# Real orchestrator node name → frontend display name
STAGE_DISPLAY_MAP: dict[str, str] = {
    "file_process": "file_process",
    "streaming": "sas_partition",
    "chunking": "sas_partition",
    "raptor": "strategy_select",
    "risk_routing": "strategy_select",
    "persist_index": "translate",
    "translation": "translate",
    "validation": "validate",
    "repair": "repair",
    "merge": "merge",
    "finalize": "finalize",
}


def conv_to_out(row) -> ConversionOut:
    """Map a ConversionRow ORM object to the ConversionOut Pydantic schema."""
    try:
        stages_sorted = sorted(
            row.stages,
            key=lambda s: STAGES.index(s.stage) if s.stage in STAGES else 99,
        )
    except Exception:
        stages_sorted = list(row.stages) if row.stages else []

    completed_count = sum(1 for s in stages_sorted if s.status == "completed")
    total = len(stages_sorted) or 8

    stage_infos = []
    for s in stages_sorted:
        try:
            warnings_list = json.loads(s.warnings) if s.warnings else []
        except (json.JSONDecodeError, TypeError):
            warnings_list = []
        try:
            stage_infos.append(
                PipelineStageInfo(
                    stage=s.stage,
                    status=s.status,
                    latency=s.latency,
                    retryCount=s.retry_count or 0,
                    warnings=warnings_list,
                    description=s.description,
                    startedAt=s.started_at,
                    completedAt=s.completed_at,
                )
            )
        except Exception:
            pass  # skip malformed stage row rather than crash

    return ConversionOut(
        id=row.id,
        fileName=row.file_name or "unknown",
        status=row.status or "queued",
        runtime=row.runtime or "python",
        duration=row.duration or 0.0,
        accuracy=row.accuracy or 0.0,
        createdAt=row.created_at or "",
        updatedAt=getattr(row, "updated_at", None),
        sasCode=row.sas_code,
        pythonCode=row.python_code,
        validationReport=row.validation_report,
        mergeReport=row.merge_report,
        progress=int(completed_count / total * 100),
        stages=stage_infos,
    )
