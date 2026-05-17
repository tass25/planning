"""Prompt template CRUD — reads/writes the actual Jinja2 files on disk."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.core.auth import get_current_user

log = structlog.get_logger()

router = APIRouter(prefix="/admin/prompts", tags=["prompts"])


def _require_admin(current_user: dict):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "partition" / "prompts" / "templates"

_TEMPLATE_META: dict[str, dict] = {
    "translation_static": {
        "display_name": "Static RAG translation",
        "description": "Low-risk partitions with simple retrieval",
        "model": "minimax-m2.7:cloud",
        "category": "translation",
        "agent_name": "TranslationAgent",
    },
    "translation_agentic": {
        "display_name": "Agentic RAG translation",
        "description": "MOD/HIGH risk — adaptive retrieval with escalation and retry",
        "model": "minimax-m2.7:cloud",
        "category": "translation",
        "agent_name": "TranslationAgent",
    },
    "translation_graph": {
        "display_name": "GraphRAG translation",
        "description": "Dependency-aware translation with graph context injection",
        "model": "minimax-m2.7:cloud",
        "category": "translation",
        "agent_name": "TranslationAgent",
    },
    "cross_verify": {
        "display_name": "Cross-verification",
        "description": "Independent equivalence check between SAS and Python",
        "model": "llama-3.3-70b",
        "category": "verification",
        "agent_name": "CrossVerifier",
    },
    "reflection": {
        "display_name": "Reflexion retry",
        "description": "Failure analysis prompt for retry attempts",
        "model": "minimax-m2.7:cloud",
        "category": "verification",
        "agent_name": "ReflectionAgent",
    },
    "entity_extraction": {
        "display_name": "Entity extraction",
        "description": "Extract SAS constructs and relationships for knowledge graph",
        "model": "minimax-m2.7:cloud",
        "category": "indexing",
        "agent_name": "EntityExtractor",
    },
}


class PromptTemplateOut(BaseModel):
    id: str
    name: str
    displayName: str
    description: str
    model: str
    category: str
    status: str
    content: str
    variables: list[str]
    uses: int
    avgLatency: float
    successRate: float
    lastEdited: str
    version: str


class PromptTemplateUpdate(BaseModel):
    content: Optional[str] = None
    status: Optional[str] = None


def _extract_variables(content: str) -> list[str]:
    """Extract Jinja2 variable names from template content."""
    pattern = r"\{\{[\s]*([a-zA-Z_][a-zA-Z0-9_]*)(?:\s*\|[^}]*)?\s*\}\}"
    found = set(re.findall(pattern, content))
    found -= {"loop"}
    return sorted(found)


def _get_usage_stats(agent_name: str) -> dict:
    """Pull usage stats from DuckDB llm_audit table."""
    try:
        import duckdb

        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "analytics.duckdb"
        if not db_path.exists():
            return {"uses": 0, "avg_latency": 0.0, "success_rate": 0.0}

        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as uses,
                    COALESCE(AVG(latency_ms), 0) as avg_latency,
                    COALESCE(
                        SUM(CASE WHEN success THEN 1 ELSE 0 END) * 100.0 / NULLIF(COUNT(*), 0),
                        0
                    ) as success_rate
                FROM llm_audit
                WHERE agent_name = ?
                """,
                [agent_name],
            ).fetchone()
            return {
                "uses": row[0] if row else 0,
                "avg_latency": round(row[1], 1) if row else 0.0,
                "success_rate": round(row[2], 1) if row else 0.0,
            }
        finally:
            conn.close()
    except Exception:
        return {"uses": 0, "avg_latency": 0.0, "success_rate": 0.0}


def _template_to_out(name: str, content: str, meta: dict, stats: dict) -> PromptTemplateOut:
    """Build output model for a template."""
    tpl_path = _TEMPLATES_DIR / f"{name}.j2"
    mtime = datetime.fromtimestamp(tpl_path.stat().st_mtime, tz=timezone.utc).isoformat()

    return PromptTemplateOut(
        id=name,
        name=name,
        displayName=meta["display_name"],
        description=meta["description"],
        model=meta["model"],
        category=meta["category"],
        status="active",
        content=content,
        variables=_extract_variables(content),
        uses=stats["uses"],
        avgLatency=stats["avg_latency"],
        successRate=stats["success_rate"],
        lastEdited=mtime,
        version="v1.0",
    )


@router.get("", response_model=list[PromptTemplateOut])
async def list_templates(current_user: dict = Depends(get_current_user)):
    """List all prompt templates with usage stats."""
    _require_admin(current_user)
    results = []
    for name, meta in _TEMPLATE_META.items():
        tpl_path = _TEMPLATES_DIR / f"{name}.j2"
        if not tpl_path.exists():
            continue
        content = tpl_path.read_text(encoding="utf-8")
        stats = _get_usage_stats(meta["agent_name"])
        results.append(_template_to_out(name, content, meta, stats))
    return results


@router.get("/{template_id}", response_model=PromptTemplateOut)
async def get_template(template_id: str, current_user: dict = Depends(get_current_user)):
    """Get a single template by ID."""
    _require_admin(current_user)
    if template_id not in _TEMPLATE_META:
        raise HTTPException(404, f"Template '{template_id}' not found")
    tpl_path = _TEMPLATES_DIR / f"{template_id}.j2"
    if not tpl_path.exists():
        raise HTTPException(404, f"Template file missing: {template_id}.j2")
    content = tpl_path.read_text(encoding="utf-8")
    meta = _TEMPLATE_META[template_id]
    stats = _get_usage_stats(meta["agent_name"])
    return _template_to_out(template_id, content, meta, stats)


@router.put("/{template_id}", response_model=PromptTemplateOut)
async def update_template(
    template_id: str,
    body: PromptTemplateUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update a template's content."""
    _require_admin(current_user)
    if template_id not in _TEMPLATE_META:
        raise HTTPException(404, f"Template '{template_id}' not found")
    tpl_path = _TEMPLATES_DIR / f"{template_id}.j2"
    if not tpl_path.exists():
        raise HTTPException(404, f"Template file missing: {template_id}.j2")

    if body.content is not None:
        tpl_path.write_text(body.content, encoding="utf-8")
        log.info("prompt_template_updated", template_id=template_id)

    content = tpl_path.read_text(encoding="utf-8")
    meta = _TEMPLATE_META[template_id]
    stats = _get_usage_stats(meta["agent_name"])
    return _template_to_out(template_id, content, meta, stats)
