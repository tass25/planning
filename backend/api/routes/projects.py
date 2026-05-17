"""Projects routes — group related conversions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.core.auth import get_current_user
from api.core.database import (
    ConversionRow,
    ProjectFileRow,
    ProjectRow,
    UserRow,
    get_api_session,
)
from api.core.schemas import ProjectAddFile, ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_to_out(session, row: ProjectRow) -> ProjectOut:
    owner = session.query(UserRow).filter(UserRow.id == row.owner_id).first()
    file_links = (
        session.query(ProjectFileRow).filter(ProjectFileRow.project_id == row.id).all()
    )
    conv_ids = [f.conversion_id for f in file_links]
    total_files = len(conv_ids)
    converted = 0
    if conv_ids:
        converted = (
            session.query(ConversionRow)
            .filter(ConversionRow.id.in_(conv_ids), ConversionRow.status == "completed")
            .count()
        )

    return ProjectOut(
        id=row.id,
        name=row.name,
        ownerId=row.owner_id,
        ownerName=owner.name if owner else "Unknown",
        status=row.status,
        color=row.color,
        files=total_files,
        converted=converted,
        createdAt=row.created_at,
        updatedAt=row.updated_at,
    )


@router.get("", response_model=list[ProjectOut])
def list_projects(current_user: dict = Depends(get_current_user)):
    from api.main import engine

    session = get_api_session(engine)
    try:
        rows = (
            session.query(ProjectRow)
            .filter(ProjectRow.owner_id == current_user["sub"])
            .order_by(ProjectRow.updated_at.desc())
            .all()
        )
        return [_project_to_out(session, r) for r in rows]
    finally:
        session.close()


@router.post("", response_model=ProjectOut)
def create_project(body: ProjectCreate, current_user: dict = Depends(get_current_user)):
    from api.main import engine

    session = get_api_session(engine)
    try:
        now = datetime.now(timezone.utc).isoformat()
        row = ProjectRow(
            id=f"proj-{uuid.uuid4().hex[:8]}",
            name=body.name,
            owner_id=current_user["sub"],
            status="active",
            color=body.color,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _project_to_out(session, row)
    finally:
        session.close()


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: str, body: ProjectUpdate, current_user: dict = Depends(get_current_user)
):
    from api.main import engine

    session = get_api_session(engine)
    try:
        row = session.query(ProjectRow).filter(ProjectRow.id == project_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        if row.owner_id != current_user["sub"] and current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not your project")

        if body.name is not None:
            row.name = body.name
        if body.status is not None:
            row.status = body.status
        if body.color is not None:
            row.color = body.color
        row.updated_at = datetime.now(timezone.utc).isoformat()
        session.commit()
        session.refresh(row)
        return _project_to_out(session, row)
    finally:
        session.close()


@router.delete("/{project_id}")
def delete_project(project_id: str, current_user: dict = Depends(get_current_user)):
    from api.main import engine

    session = get_api_session(engine)
    try:
        row = session.query(ProjectRow).filter(ProjectRow.id == project_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        if row.owner_id != current_user["sub"] and current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Not your project")
        session.delete(row)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.post("/{project_id}/files")
def add_file_to_project(
    project_id: str, body: ProjectAddFile, current_user: dict = Depends(get_current_user)
):
    from api.main import engine

    session = get_api_session(engine)
    try:
        row = session.query(ProjectRow).filter(ProjectRow.id == project_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        existing = (
            session.query(ProjectFileRow)
            .filter(
                ProjectFileRow.project_id == project_id,
                ProjectFileRow.conversion_id == body.conversionId,
            )
            .first()
        )
        if existing:
            return {"ok": True, "message": "Already linked"}

        session.add(ProjectFileRow(project_id=project_id, conversion_id=body.conversionId))
        row.updated_at = datetime.now(timezone.utc).isoformat()
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@router.delete("/{project_id}/files/{conversion_id}")
def remove_file_from_project(
    project_id: str, conversion_id: str, current_user: dict = Depends(get_current_user)
):
    from api.main import engine

    session = get_api_session(engine)
    try:
        link = (
            session.query(ProjectFileRow)
            .filter(
                ProjectFileRow.project_id == project_id,
                ProjectFileRow.conversion_id == conversion_id,
            )
            .first()
        )
        if not link:
            raise HTTPException(status_code=404, detail="File not linked to project")
        session.delete(link)
        session.commit()
        return {"ok": True}
    finally:
        session.close()
