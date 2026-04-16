"""Conversion routes — upload SAS files, run pipeline, get results.

Business logic lives in api.services.*:
- conversion_service  : conv_to_out(), STAGES, STAGE_DISPLAY_MAP
- pipeline_service    : run_pipeline_sync()
- translation_service : translate_sas_to_python()
"""

from __future__ import annotations

import asyncio
import html as html_mod
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import PlainTextResponse, StreamingResponse, HTMLResponse

_log = structlog.get_logger("codara.conversions")

from api.core.auth import get_current_user
from api.core.database import (
    get_api_session, ConversionRow, ConversionStageRow,
    UserRow, NotificationRow, CorrectionRow,
)
from api.core.schemas import (
    ConversionOut, PipelineStageInfo, SasFileOut, StartConversionRequest,
    PartitionOut, CorrectionOut, CorrectionCreate,
)
from api.services.conversion_service import conv_to_out, STAGES, STAGE_DISPLAY_MAP
from api.services.pipeline_service import run_pipeline_sync
from api.services.blob_service import blob_service
from api.services.queue_service import queue_service
from config.settings import settings
from config.constants import SSE_MAX_EVENTS, SSE_POLL_INTERVAL_S

router = APIRouter(prefix="/conversions", tags=["conversions"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
_ALLOWED_CONTENT_TYPES = frozenset({
    "text/plain",
    "application/octet-stream",
    "application/x-sas",
    "",  # browsers sometimes omit content-type
})


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=list[SasFileOut])
async def upload_files(
    files: list[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    results: list[SasFileOut] = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".sas"):
            raise HTTPException(status_code=400, detail=f"Only .sas files accepted: {f.filename}")
        mime = (f.content_type or "").split(";")[0].strip().lower()
        if mime not in _ALLOWED_CONTENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid MIME type '{mime}' for {f.filename}. Expected text/plain or application/octet-stream.",
            )
        file_id = f"file-{uuid.uuid4().hex[:8]}"
        content = await f.read()
        if len(content) > _MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File {f.filename} exceeds maximum upload size of 50 MB.",
            )
        await blob_service.upload(file_id, f.filename, content)
        results.append(SasFileOut(
            id=file_id,
            name=f.filename,
            size=len(content),
            modules=[],
            estimatedComplexity="low",
            uploadedAt=datetime.now(timezone.utc).isoformat(),
        ))
    return results


# ── Start conversion ──────────────────────────────────────────────────────────

@router.post("/start", response_model=ConversionOut)
def start_conversion(
    body: StartConversionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    from api.main import engine

    session = get_api_session(engine)
    try:
        file_id = body.fileIds[0] if body.fileIds else None
        if not file_id:
            raise HTTPException(status_code=400, detail="No file specified")

        # Resolve filename from blob or local disk
        import asyncio as _asyncio
        filenames = _asyncio.run(blob_service.list_files(file_id))
        sas_filenames = [n for n in filenames if n.lower().endswith(".sas")]
        if not sas_filenames:
            raise HTTPException(status_code=404, detail=f"No .sas file found for upload {file_id}")
        filename = sas_filenames[0]

        conv_id = f"conv-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        conv = ConversionRow(
            id=conv_id,
            user_id=current_user["sub"],
            file_name=filename,
            status="queued",
            runtime="python",
            created_at=now,
        )
        session.add(conv)

        for stg in STAGES:
            session.add(ConversionStageRow(
                conversion_id=conv_id,
                stage=stg,
                status="pending",
            ))

        session.commit()
        session.refresh(conv)
        result = conv_to_out(conv)

        # Prefer durable Azure Queue; fall back to BackgroundTasks for local dev
        queued = queue_service.enqueue_job(conv_id, file_id, filename, settings.sqlite_path)
        if not queued:
            background_tasks.add_task(run_pipeline_sync, conv_id, file_id, filename, settings.sqlite_path)

        return result
    finally:
        session.close()


# ── List / Get ────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ConversionOut])
def list_conversions(current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        rows = session.query(ConversionRow).order_by(ConversionRow.created_at.desc()).all()
        return [conv_to_out(r) for r in rows]
    finally:
        session.close()


@router.get("/{conversion_id}", response_model=ConversionOut)
def get_conversion(conversion_id: str, current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).get(conversion_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversion not found")
        return conv_to_out(conv)
    finally:
        session.close()


@router.get("/{conversion_id}/code", response_class=PlainTextResponse)
def download_code(conversion_id: str, current_user: dict = Depends(get_current_user)):
    from api.main import engine
    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).get(conversion_id)
        if not conv or not conv.python_code:
            raise HTTPException(status_code=404, detail="No generated code")
        return conv.python_code
    finally:
        session.close()


# ── Partitions ────────────────────────────────────────────────────────────────

@router.get("/{conversion_id}/partitions", response_model=list[PartitionOut])
def get_partitions(conversion_id: str, current_user: dict = Depends(get_current_user)):
    """Get partitions from the pipeline DB for this conversion."""
    pipeline_db = UPLOAD_DIR / f"{conversion_id}_pipeline.db"
    if not pipeline_db.exists():
        return []

    try:
        from partition.db.sqlite_manager import get_engine, PartitionIRRow
        pe = get_engine(str(pipeline_db))
        from sqlalchemy.orm import sessionmaker
        ps = sessionmaker(bind=pe)()
    except Exception as exc:
        _log.warning("partition_db_open_failed", conversion_id=conversion_id, error=str(exc))
        return []

    try:
        rows = ps.query(PartitionIRRow).all()
        return [
            PartitionOut(
                id=r.partition_id,
                conversionId=conversion_id,
                sasBlock=r.raw_code or "",
                riskLevel=(r.risk_level or "low").lower(),
                strategy=r.strategy or "unknown",
                translatedCode="",
            )
            for r in rows
        ]
    except Exception as exc:
        _log.warning("partition_query_failed", conversion_id=conversion_id, error=str(exc))
        return []
    finally:
        try:
            ps.close()
        except Exception:
            pass
        try:
            pe.dispose()
        except Exception:
            pass


# ── Corrections ───────────────────────────────────────────────────────────────

@router.post("/{conversion_id}/corrections", response_model=CorrectionOut)
def submit_correction(
    conversion_id: str,
    body: CorrectionCreate,
    current_user: dict = Depends(get_current_user),
):
    from api.main import engine
    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).get(conversion_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversion not found")
        corr = CorrectionRow(
            id=f"corr-{uuid.uuid4().hex[:8]}",
            conversion_id=conversion_id,
            corrected_code=body.correctedCode,
            explanation=body.explanation,
            category=body.category,
            submitted_at=datetime.now(timezone.utc).isoformat(),
        )
        session.add(corr)
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise HTTPException(status_code=500, detail="Failed to save correction")
        return CorrectionOut(
            id=corr.id,
            conversionId=corr.conversion_id,
            correctedCode=corr.corrected_code,
            explanation=corr.explanation,
            category=corr.category,
            submittedAt=corr.submitted_at,
        )
    finally:
        session.close()


# ── Download endpoints ────────────────────────────────────────────────────────

@router.get("/{conversion_id}/download/py")
def download_py(conversion_id: str, current_user: dict = Depends(get_current_user)):
    """Download the converted Python code as a .py file."""
    from api.main import engine
    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).get(conversion_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversion not found")
        code = conv.python_code or "# No converted code available yet"
        filename = conv.file_name.replace(".sas", ".py") if conv.file_name else "converted.py"
        return StreamingResponse(
            io.BytesIO(code.encode("utf-8")),
            media_type="text/x-python",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    finally:
        session.close()


@router.get("/{conversion_id}/download/md")
def download_md(conversion_id: str, current_user: dict = Depends(get_current_user)):
    """Download the conversion report as a Markdown file."""
    from api.main import engine
    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).get(conversion_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversion not found")

        stages_sorted = sorted(
            conv.stages,
            key=lambda s: STAGES.index(s.stage) if s.stage in STAGES else 99,
        )
        lines = [
            f"# Conversion Report: {conv.file_name}",
            "",
            f"- **Status**: {conv.status}",
            f"- **Runtime**: {conv.runtime}",
            f"- **Duration**: {(conv.duration or 0.0):.2f}s",
            f"- **Accuracy**: {conv.accuracy or 0}%",
            f"- **Created**: {conv.created_at}",
            "",
            "## Pipeline Stages",
            "",
            "| Stage | Status | Latency |",
            "|-------|--------|---------|",
        ]
        for s in stages_sorted:
            lat = f"{s.latency:.0f}ms" if s.latency else "—"
            lines.append(f"| {s.stage} | {s.status} | {lat} |")

        if conv.validation_report:
            lines += ["", "## Validation Report", "", conv.validation_report]
        if conv.merge_report:
            lines += ["", "## Merge Report", "", conv.merge_report]
        if conv.sas_code:
            lines += ["", "## Original SAS Code", "", "```sas", conv.sas_code, "```"]
        if conv.python_code:
            lines += ["", "## Converted Python Code", "", "```python", conv.python_code, "```"]

        md = "\n".join(lines)
        filename = conv.file_name.replace(".sas", "_report.md") if conv.file_name else "report.md"
        return StreamingResponse(
            io.BytesIO(md.encode("utf-8")),
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    finally:
        session.close()


@router.get("/{conversion_id}/download/html")
def download_html(conversion_id: str, current_user: dict = Depends(get_current_user)):
    """Download the conversion report as an HTML file."""
    from api.main import engine
    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).get(conversion_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversion not found")

        stages_sorted = sorted(
            conv.stages,
            key=lambda s: STAGES.index(s.stage) if s.stage in STAGES else 99,
        )
        stage_rows = "".join(
            f"<tr><td>{html_mod.escape(s.stage)}</td>"
            f"<td>{html_mod.escape(s.status)}</td>"
            f"<td>{f'{s.latency:.0f}ms' if s.latency else '—'}</td></tr>"
            for s in stages_sorted
        )

        # HTML-escape all user-supplied content to prevent XSS
        safe_file_name   = html_mod.escape(conv.file_name or "unknown")
        safe_status      = html_mod.escape(conv.status or "")
        safe_runtime     = html_mod.escape(conv.runtime or "")
        safe_val_report  = html_mod.escape(conv.validation_report) if conv.validation_report else ""
        safe_merge_report = html_mod.escape(conv.merge_report) if conv.merge_report else ""
        safe_sas         = html_mod.escape(conv.sas_code) if conv.sas_code else ""
        safe_python      = html_mod.escape(conv.python_code) if conv.python_code else ""

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Conversion Report — {safe_file_name}</title>
<style>body{{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
h1{{color:#7c3aed}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#f5f3ff}}pre{{background:#f5f5f5;padding:1rem;border-radius:8px;overflow-x:auto}}
.meta{{display:grid;grid-template-columns:repeat(2,1fr);gap:0.5rem;margin:1rem 0}}
.meta span{{font-size:0.9rem}}.label{{font-weight:600;color:#555}}</style></head>
<body><h1>Conversion Report: {safe_file_name}</h1>
<div class="meta">
<span><span class="label">Status:</span> {safe_status}</span>
<span><span class="label">Runtime:</span> {safe_runtime}</span>
<span><span class="label">Duration:</span> {(conv.duration or 0.0):.2f}s</span>
<span><span class="label">Accuracy:</span> {conv.accuracy or 0}%</span>
</div>
<h2>Pipeline Stages</h2>
<table><tr><th>Stage</th><th>Status</th><th>Latency</th></tr>{stage_rows}</table>
{"<h2>Validation Report</h2><pre>" + safe_val_report + "</pre>" if safe_val_report else ""}
{"<h2>Merge Report</h2><pre>" + safe_merge_report + "</pre>" if safe_merge_report else ""}
{"<h2>Original SAS Code</h2><pre>" + safe_sas + "</pre>" if safe_sas else ""}
{"<h2>Converted Python Code</h2><pre>" + safe_python + "</pre>" if safe_python else ""}
</body></html>"""

        filename = conv.file_name.replace(".sas", "_report.html") if conv.file_name else "report.html"
        return HTMLResponse(content=html, headers={"Content-Disposition": f"attachment; filename={filename}"})
    finally:
        session.close()


@router.get("/{conversion_id}/download/zip")
def download_zip(conversion_id: str, current_user: dict = Depends(get_current_user)):
    """Download everything as a ZIP bundle."""
    from api.main import engine
    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).get(conversion_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversion not found")

        buf = io.BytesIO()
        base = conv.file_name.replace(".sas", "") if conv.file_name else "conversion"

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if conv.python_code:
                zf.writestr(f"{base}.py", conv.python_code)
            if conv.sas_code:
                zf.writestr(f"{base}_original.sas", conv.sas_code)
            if conv.validation_report:
                zf.writestr(f"{base}_validation.txt", conv.validation_report)
            if conv.merge_report:
                zf.writestr(f"{base}_merge.txt", conv.merge_report)
            summary = (
                f"Conversion: {conv.file_name}\n"
                f"Status: {conv.status}\n"
                f"Runtime: {conv.runtime}\n"
                f"Accuracy: {conv.accuracy}%\n"
                f"Duration: {conv.duration:.2f}s"
            )
            zf.writestr("README.txt", summary)

        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={base}_bundle.zip"},
        )
    finally:
        session.close()


# ── SSE status stream ─────────────────────────────────────────────────────────

@router.get("/{conversion_id}/stream")
async def stream_conversion_status(
    conversion_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Server-Sent Events stream for real-time conversion status updates.

    The client connects once and receives JSON events every second until
    the conversion reaches a terminal state (completed | failed | partial).

    Event format:
        data: {"id": "...", "status": "running", "progress": 42, "stage": "..."}
    """
    async def _event_generator():
        last_status: str | None = None
        count = 0
        while count < SSE_MAX_EVENTS:
            from api.main import engine
            session = get_api_session(engine)
            try:
                conv = session.query(ConversionRow).get(conversion_id)
                if conv is None:
                    yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                    return
                status = conv.status or "queued"
                stages_sorted = sorted(
                    conv.stages,
                    key=lambda s: STAGES.index(s.stage) if s.stage in STAGES else 99,
                )
                completed = sum(1 for s in stages_sorted if s.status == "completed")
                total = len(stages_sorted) or 8
                progress = int(completed / total * 100)
                current_stage = next(
                    (s.stage for s in stages_sorted if s.status == "running"), None
                )
                payload = {
                    "id": conversion_id,
                    "status": status,
                    "progress": progress,
                    "stage": current_stage,
                }
                if status != last_status or count % 5 == 0:
                    yield f"data: {json.dumps(payload)}\n\n"
                    last_status = status
                if status in ("completed", "failed", "partial"):
                    return
            except Exception as exc:
                _log.warning("sse_error", conversion_id=conversion_id, error=str(exc))
                yield f"data: {json.dumps({'error': 'stream_error'})}\n\n"
                return
            finally:
                session.close()
            await asyncio.sleep(SSE_POLL_INTERVAL_S)
            count += 1

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
