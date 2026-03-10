"""Knowledge Base CRUD routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from api.auth import get_current_user
from api.database import get_api_session, KBEntryRow, KBChangelogRow
from api.schemas import (
    KnowledgeBaseEntryOut, KBEntryCreate, KBEntryUpdate,
    KBChangelogEntryOut,
)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


def _kb_to_out(row: KBEntryRow) -> KnowledgeBaseEntryOut:
    return KnowledgeBaseEntryOut(
        id=row.id,
        sasSnippet=row.sas_snippet,
        pythonTranslation=row.python_translation,
        category=row.category,
        confidence=row.confidence,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


def _log_change(session, entry_id: str, action: str, user_email: str, description: str):
    session.add(KBChangelogRow(
        id=f"cl-{uuid.uuid4().hex[:8]}",
        entry_id=entry_id,
        action=action,
        user=user_email,
        timestamp=datetime.now(timezone.utc).isoformat(),
        description=description,
    ))


@router.get("", response_model=list[KnowledgeBaseEntryOut])
def list_entries(current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        rows = session.query(KBEntryRow).order_by(KBEntryRow.updated_at.desc()).all()
        return [_kb_to_out(r) for r in rows]
    finally:
        session.close()


@router.get("/changelog", response_model=list[KBChangelogEntryOut])
def get_changelog(current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        rows = session.query(KBChangelogRow).order_by(KBChangelogRow.timestamp.desc()).all()
        return [
            KBChangelogEntryOut(
                id=r.id, entryId=r.entry_id, action=r.action,
                user=r.user, timestamp=r.timestamp, description=r.description,
            )
            for r in rows
        ]
    finally:
        session.close()


@router.get("/{entry_id}", response_model=KnowledgeBaseEntryOut)
def get_entry(entry_id: str, current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        row = session.query(KBEntryRow).get(entry_id)
        if not row:
            raise HTTPException(status_code=404, detail="KB entry not found")
        return _kb_to_out(row)
    finally:
        session.close()


@router.post("", response_model=KnowledgeBaseEntryOut)
def create_entry(body: KBEntryCreate, current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        now = datetime.now(timezone.utc).isoformat()
        entry = KBEntryRow(
            id=f"kb-{uuid.uuid4().hex[:8]}",
            sas_snippet=body.sasSnippet,
            python_translation=body.pythonTranslation,
            category=body.category,
            confidence=body.confidence,
            created_at=now,
            updated_at=now,
        )
        session.add(entry)
        _log_change(session, entry.id, "add", current_user["email"], f"Added {body.category} entry")
        session.commit()
        session.refresh(entry)
        return _kb_to_out(entry)
    finally:
        session.close()


@router.put("/{entry_id}", response_model=KnowledgeBaseEntryOut)
def update_entry(entry_id: str, body: KBEntryUpdate, current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        row = session.query(KBEntryRow).get(entry_id)
        if not row:
            raise HTTPException(status_code=404, detail="KB entry not found")
        changes: list[str] = []
        if body.sasSnippet is not None:
            row.sas_snippet = body.sasSnippet
            changes.append("sasSnippet")
        if body.pythonTranslation is not None:
            row.python_translation = body.pythonTranslation
            changes.append("pythonTranslation")
        if body.category is not None:
            row.category = body.category
            changes.append("category")
        if body.confidence is not None:
            row.confidence = body.confidence
            changes.append("confidence")
        row.updated_at = datetime.now(timezone.utc).isoformat()
        _log_change(session, entry_id, "edit", current_user["email"], f"Updated: {', '.join(changes)}")
        session.commit()
        session.refresh(row)
        return _kb_to_out(row)
    finally:
        session.close()


@router.delete("/{entry_id}")
def delete_entry(entry_id: str, current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        row = session.query(KBEntryRow).get(entry_id)
        if not row:
            raise HTTPException(status_code=404, detail="KB entry not found")
        _log_change(session, entry_id, "delete", current_user["email"], f"Deleted entry {entry_id}")
        session.delete(row)
        session.commit()
        return {"deleted": entry_id}
    finally:
        session.close()
