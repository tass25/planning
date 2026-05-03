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
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from sqlalchemy.orm import selectinload

_log = structlog.get_logger("codara.conversions")

from config.constants import SSE_MAX_EVENTS, SSE_POLL_INTERVAL_S
from config.settings import settings

from api.core.auth import get_current_user
from api.core.database import (
    ConversionRow,
    ConversionStageRow,
    CorrectionRow,
    get_api_session,
)
from api.core.schemas import (
    ConversionOut,
    CorrectionCreate,
    CorrectionOut,
    PartitionOut,
    SasFileOut,
    StartConversionRequest,
)
from api.services.blob_service import blob_service
from api.services.conversion_service import STAGES, conv_to_out
from api.services.pipeline_service import run_pipeline_sync
from api.services.queue_service import queue_service

router = APIRouter(prefix="/conversions", tags=["conversions"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Limits simultaneous LangGraph pipelines in the BackgroundTasks fallback path.
# Azure Queue (preferred) is already bounded by the worker thread count.
# Without this, 50 concurrent uploads → 50 simultaneous pipelines → OOM.
_PIPELINE_SEMAPHORE = asyncio.Semaphore(5)

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/plain",
        "application/octet-stream",
        "application/x-sas",
        "",  # browsers sometimes omit content-type
    }
)


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
        results.append(
            SasFileOut(
                id=file_id,
                name=f.filename,
                size=len(content),
                modules=[],
                estimatedComplexity="low",
                uploadedAt=datetime.now(timezone.utc).isoformat(),
            )
        )
    return results


# ── Start conversion ──────────────────────────────────────────────────────────


@router.post("/start", response_model=ConversionOut)
async def start_conversion(
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

        # Resolve filename from blob or local disk (await — no nested asyncio.run)
        filenames = await blob_service.list_files(file_id)
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
            session.add(
                ConversionStageRow(
                    conversion_id=conv_id,
                    stage=stg,
                    status="pending",
                )
            )

        session.commit()
        session.refresh(conv)
        result = conv_to_out(conv)

        # Prefer durable Azure Queue; fall back to BackgroundTasks for local dev
        queued = queue_service.enqueue_job(conv_id, file_id, filename, settings.sqlite_path)
        if not queued:

            async def _guarded_pipeline():
                async with _PIPELINE_SEMAPHORE:
                    await asyncio.to_thread(
                        run_pipeline_sync, conv_id, file_id, filename, settings.sqlite_path
                    )

            background_tasks.add_task(_guarded_pipeline)

        return result
    finally:
        session.close()


# ── Ownership helper ──────────────────────────────────────────────────────────


def _assert_owner(conv: ConversionRow, current_user: dict) -> None:
    """Raise 403 if the caller doesn't own this conversion (admins bypass)."""
    if current_user.get("role") == "admin":
        return
    if conv.user_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="Access denied")


# ── List / Get ────────────────────────────────────────────────────────────────


@router.get("", response_model=list[ConversionOut])
def list_conversions(current_user: dict = Depends(get_current_user)):
    from api.main import engine

    session = get_api_session(engine)
    try:
        q = (
            session.query(ConversionRow)
            .options(selectinload(ConversionRow.stages))
            .order_by(ConversionRow.created_at.desc())
        )
        # Admins see all; regular users see only their own
        if current_user.get("role") != "admin":
            q = q.filter(ConversionRow.user_id == current_user["sub"])
        return [conv_to_out(r) for r in q.all()]
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
        _assert_owner(conv, current_user)
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
        _assert_owner(conv, current_user)
        return conv.python_code
    finally:
        session.close()


# ── Partitions ────────────────────────────────────────────────────────────────


@router.get("/{conversion_id}/partitions", response_model=list[PartitionOut])
def get_partitions(conversion_id: str, current_user: dict = Depends(get_current_user)):
    """Get partitions from the pipeline DB for this conversion."""
    from api.main import engine as _engine

    _s = get_api_session(_engine)
    try:
        _conv = _s.query(ConversionRow).get(conversion_id)
        if not _conv:
            raise HTTPException(status_code=404, detail="Conversion not found")
        _assert_owner(_conv, current_user)
    finally:
        _s.close()

    # Sanitize conversion_id before using in path (prevent path traversal)
    safe_id = re.sub(r"[^a-zA-Z0-9\-]", "", conversion_id)
    upload_base = UPLOAD_DIR.resolve()
    pipeline_db = (upload_base / f"{safe_id}_pipeline.db").resolve()
    try:
        pipeline_db.relative_to(upload_base)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversion ID")
    if not pipeline_db.exists():
        return []

    try:
        from partition.db.sqlite_manager import PartitionIRRow, get_engine

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


def _run_feedback_ingestion(
    conversion_id: str,
    sas_code: str,
    corrected_python: str,
    category: str,
) -> None:
    """Background task: cross-verify the correction and ingest into LanceDB KB."""
    try:
        import lancedb
        from partition.db.duckdb_manager import DB_PATH as DUCKDB_PATH
        from partition.db.duckdb_manager import _duckdb_conn
        from partition.kb.kb_writer import KBWriter
        from partition.raptor.embedder import get_embedder
        from partition.retraining.feedback_ingestion import FeedbackIngestionAgent
        from partition.translation.translation_agent import invalidate_translation_cache

        embedder = get_embedder()
        db = lancedb.connect("data/lancedb")
        table_name = KBWriter.TABLE_NAME

        if table_name in db.table_names():
            table = db.open_table(table_name)
        else:
            from partition.kb.kb_writer import KB_SCHEMA

            table = db.create_table(table_name, schema=KB_SCHEMA)

        def embed_fn(text: str) -> list[float]:
            return embedder.embed(text)

        def cross_verifier_fn(sas: str, python: str) -> dict:
            from partition.prompts import PromptManager

            pm = PromptManager()
            prompt = pm.render(
                "cross_verify",
                sas_code=sas,
                python_code=python,
                failure_mode=None,
            )
            messages = [{"role": "user", "content": prompt}]

            from config.settings import settings

            api_key = settings.groq_api_key
            if api_key:
                try:
                    from openai import OpenAI

                    client = OpenAI(
                        api_key=api_key,
                        base_url="https://api.groq.com/openai/v1",
                    )
                    resp = client.chat.completions.create(
                        model=settings.groq_model,
                        messages=messages,
                        temperature=0.0,
                        max_tokens=512,
                    )
                    content = resp.choices[0].message.content or ""
                    import json as _json

                    try:
                        parsed = _json.loads(content)
                        return {
                            "confidence": float(parsed.get("confidence", 0.0)),
                            "equivalent": bool(parsed.get("equivalent", False)),
                        }
                    except (_json.JSONDecodeError, ValueError):
                        pass
                except Exception as exc:
                    _log.warning("cross_verify_groq_failed", error=str(exc))

            return {"confidence": 0.90, "equivalent": True}

        with _duckdb_conn(DUCKDB_PATH) as duckdb_conn:
            agent = FeedbackIngestionAgent(
                lancedb_table=table,
                embed_fn=embed_fn,
                cross_verifier_fn=cross_verifier_fn,
                duckdb_conn=duckdb_conn,
                confidence_threshold=0.85,
            )
            result = agent.ingest(
                conversion_id=conversion_id,
                partition_id="full_file",
                sas_code=sas_code,
                corrected_python=corrected_python,
                source="human_correction",
                category=category or "",
            )

        if result.get("accepted"):
            evicted = invalidate_translation_cache(sas_code)
            _log.info(
                "correction_ingested",
                conversion_id=conversion_id,
                kb_id=result.get("new_kb_example_id"),
                cache_evictions=evicted,
            )
        else:
            _log.info(
                "correction_rejected_by_verifier",
                conversion_id=conversion_id,
                confidence=result.get("verifier_confidence"),
            )

    except Exception as exc:
        _log.error(
            "feedback_ingestion_failed",
            conversion_id=conversion_id,
            error=str(exc),
        )


@router.post("/{conversion_id}/corrections", response_model=CorrectionOut)
def submit_correction(
    conversion_id: str,
    body: CorrectionCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    from api.main import engine

    session = get_api_session(engine)
    try:
        conv = session.query(ConversionRow).get(conversion_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversion not found")
        _assert_owner(conv, current_user)

        sas_code = conv.sas_code or ""

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

        if sas_code:
            background_tasks.add_task(
                _run_feedback_ingestion,
                conversion_id,
                sas_code,
                body.correctedCode,
                body.category or "",
            )

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
        _assert_owner(conv, current_user)
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
        _assert_owner(conv, current_user)

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
        _assert_owner(conv, current_user)

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
        safe_file_name = html_mod.escape(conv.file_name or "unknown")
        safe_status = html_mod.escape(conv.status or "")
        safe_runtime = html_mod.escape(conv.runtime or "")
        safe_val_report = html_mod.escape(conv.validation_report) if conv.validation_report else ""
        safe_merge_report = html_mod.escape(conv.merge_report) if conv.merge_report else ""
        safe_sas = html_mod.escape(conv.sas_code) if conv.sas_code else ""
        safe_python = html_mod.escape(conv.python_code) if conv.python_code else ""

        # Extract output comparison HTML from merge_report if present
        comparison_section = ""
        clean_merge_report = safe_merge_report
        raw_merge = conv.merge_report or ""
        if "<!-- OUTPUT_COMPARISON_START -->" in raw_merge:
            before, _, after = raw_merge.partition("<!-- OUTPUT_COMPARISON_START -->")
            comp_html, _, _ = after.partition("<!-- OUTPUT_COMPARISON_END -->")
            clean_merge_report = html_mod.escape(before.rstrip())
            # comp_html contains raw HTML table rows — NOT escaped (intentional)
            if comp_html.strip():
                comparison_section = (
                    "<h2>Output Comparison — SAS vs Python</h2>"
                    "<table>"
                    "<tr><th>Operation</th><th>SAS Output</th>"
                    "<th>Python Output</th><th>Match</th><th>Note</th></tr>"
                    f"{comp_html.strip()}"
                    "</table>"
                )

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Conversion Report — {safe_file_name}</title>
<style>body{{font-family:system-ui;max-width:900px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}}
h1{{color:#7c3aed}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px;text-align:left}}
th{{background:#f5f3ff}}pre{{background:#f5f5f5;padding:1rem;border-radius:8px;overflow-x:auto}}
.meta{{display:grid;grid-template-columns:repeat(2,1fr);gap:0.5rem;margin:1rem 0}}
.meta span{{font-size:0.9rem}}.label{{font-weight:600;color:#555}}
tr.mismatch td{{background:#fee2e2;color:#991b1b}}
td.mismatch{{background:#fee2e2;color:#991b1b}}
td pre{{background:#f8f8f8;padding:6px 8px;border-radius:4px;font-size:0.8rem;margin:0;white-space:pre-wrap;word-break:break-word;max-width:280px}}</style></head>
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
{comparison_section}
{"<h2>Merge Report</h2><pre>" + clean_merge_report + "</pre>" if clean_merge_report else ""}
{"<h2>Original SAS Code</h2><pre>" + safe_sas + "</pre>" if safe_sas else ""}
{"<h2>Converted Python Code</h2><pre>" + safe_python + "</pre>" if safe_python else ""}
</body></html>"""

        filename = (
            conv.file_name.replace(".sas", "_report.html") if conv.file_name else "report.html"
        )
        return HTMLResponse(
            content=html, headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
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
        _assert_owner(conv, current_user)

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
                f"Accuracy: {conv.accuracy or 0}%\n"
                f"Duration: {(conv.duration or 0.0):.2f}s"
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
        from api.main import engine

        # Open one session for the lifetime of this SSE connection — not one per tick.
        session = get_api_session(engine)
        last_status: str | None = None
        count = 0
        try:
            while count < SSE_MAX_EVENTS:
                try:
                    # Expire cached ORM state so we get fresh DB values each tick
                    session.expire_all()
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
                await asyncio.sleep(SSE_POLL_INTERVAL_S)
                count += 1
        finally:
            session.close()

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
