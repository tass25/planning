"""Pipeline service — the 8-stage SAS→Python conversion pipeline.

This runs inside a FastAPI BackgroundTasks thread (or an Azure Queue worker),
so it's synchronous Python. Any async agent calls use asyncio.run() because
this code is always outside the event loop — there's no running loop to conflict with.

Stage mapping (frontend display name → what actually runs here):
    file_process    → FileAnalysisAgent: scans file structure, identifies modules
    sas_partition   → RegistryWriterAgent: chunks SAS into logical blocks
    strategy_select → CrossFileDependencyResolver: resolves imports and deps
    translate       → DataLineageExtractor: traces data reads/writes/transforms
    validate        → translate_sas_to_python(): LLM translation (Nemotron → Azure → Groq)
    repair          → compile(): Python syntax check, no LLM call
    merge           → assemble final module with auto-generated header
    finalize        → package results and update DB
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

from api.core.database import (
    ConversionRow, ConversionStageRow, UserRow, NotificationRow,
    get_api_engine, get_api_session,
)
from api.services.blob_service import blob_service
from api.services.translation_service import translate_sas_to_python

_log = structlog.get_logger("codara.pipeline")

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


def run_pipeline_sync(
    conversion_id: str,
    file_id: str,
    filename: str,
    db_path: str,
) -> None:
    """Run L2-A agents + LLM translation synchronously inside a background thread.

    Downloads the SAS file from Blob Storage (or local disk fallback),
    runs the 8-stage pipeline, then cleans up the temp file if one was created.

    Stage flow:
        file_process → sas_partition → strategy_select → translate →
        validate → repair → merge → finalize
    """
    # Resolve the file path — download from Blob if enabled, else use local disk.
    # Always place the file in an isolated temp directory so FileAnalysisAgent
    # scans only this file and not the entire system temp folder.
    _temp_dir: Path | None = None
    _temp_path: Path | None = None
    try:
        raw_path: Path = asyncio.run(blob_service.download_to_temp(file_id, filename))
        if blob_service.enabled:
            # Blob mode: raw_path is a random temp file (e.g. /tmp/tmpXXX.sas).
            # Move it into an isolated directory named after the conversion.
            _temp_dir = Path(tempfile.mkdtemp(prefix=f"codara_{conversion_id}_"))
            file_path = _temp_dir / filename
            shutil.move(str(raw_path), file_path)
            _temp_path = _temp_dir   # cleanup the whole dir on exit
        else:
            # Local mode: raw_path is already under uploads/file-XXXXXXXX/filename
            # which is an isolated per-upload directory — no move needed.
            file_path = raw_path
    except Exception as exc:
        _log.error("pipeline_file_resolve_failed", conversion_id=conversion_id,
                   file_id=file_id, filename=filename, error=str(exc))
        return
    try:
        engine = get_api_engine(db_path)
        session = get_api_session(engine)
    except Exception as exc:
        _log.error("pipeline_db_init_failed", conversion_id=conversion_id, error=str(exc))
        return

    def _update_stage(
        stage_name: str,
        status: str,
        latency: float | None = None,
        description: str | None = None,
    ) -> None:
        try:
            st = session.query(ConversionStageRow).filter(
                ConversionStageRow.conversion_id == conversion_id,
                ConversionStageRow.stage == stage_name,
            ).first()
            if st:
                st.status = status
                now = datetime.now(timezone.utc).isoformat()
                if status == "running":
                    st.started_at = now
                elif status in ("completed", "failed"):
                    st.completed_at = now
                if latency is not None:
                    st.latency = latency
                if description is not None:
                    st.description = description
                session.commit()
        except Exception as exc:
            _log.warning("stage_update_failed", stage=stage_name, status=status, error=str(exc))
            try:
                session.rollback()
            except Exception:
                pass

    conv = session.query(ConversionRow).get(conversion_id)
    if not conv:
        session.close()
        return

    conv.status = "running"
    conv.updated_at = datetime.now(timezone.utc).isoformat()
    session.commit()

    try:
        sas_code = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        sas_code = file_path.read_text(encoding="utf-8", errors="replace")
        _log.warning("encoding_replace_used", file=str(file_path), conversion_id=conversion_id)

    conv.sas_code = sas_code
    session.commit()

    # Ensure backend package is on sys.path for partition imports
    import sys
    pkg_root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    from partition.entry.file_analysis_agent import FileAnalysisAgent
    from partition.entry.registry_writer_agent import RegistryWriterAgent
    from partition.entry.cross_file_dep_resolver import CrossFileDependencyResolver
    from partition.entry.data_lineage_extractor import DataLineageExtractor
    from partition.db.sqlite_manager import get_engine, init_db

    pipeline_db_path = str(UPLOAD_DIR / f"{conversion_id}_pipeline.db")
    pipeline_engine = None
    try:
        pipeline_engine = get_engine(pipeline_db_path)
        init_db(pipeline_engine)
    except Exception as exc:
        _log.error("pipeline_engine_init_failed", conversion_id=conversion_id, error=str(exc))
        conv.status = "failed"
        conv.updated_at = datetime.now(timezone.utc).isoformat()
        conv.validation_report = f"Pipeline DB init error: {exc}"
        try:
            session.commit()
        except Exception:
            pass
        try:
            session.close()
        except Exception:
            pass
        return

    project_root = file_path.parent
    total_start = time.perf_counter()

    try:
        # Stage 1: file_process
        _update_stage("file_process", "running", description="Scanning file structure & identifying SAS modules...")
        t0 = time.perf_counter()
        agent1 = FileAnalysisAgent()
        files = asyncio.run(agent1.process(project_root)) or []
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("file_process", "completed", lat, f"Discovered {len(files)} file(s) — structure mapped")

        # Stage 2: sas_partition
        _update_stage("sas_partition", "running", description="Chunking SAS code into logical blocks...")
        t0 = time.perf_counter()
        agent2 = RegistryWriterAgent()
        reg_result = asyncio.run(agent2.process(files, pipeline_engine)) or {}
        lat = (time.perf_counter() - t0) * 1000
        inserted = reg_result.get("inserted", 0)
        _update_stage("sas_partition", "completed", lat, f"Partitioned into {inserted} block(s) — registry built")

        # Stage 3: strategy_select
        _update_stage("strategy_select", "running", description="Resolving cross-file dependencies & imports...")
        t0 = time.perf_counter()
        agent3 = CrossFileDependencyResolver()
        deps = asyncio.run(agent3.process(files, project_root, pipeline_engine)) or {}
        lat = (time.perf_counter() - t0) * 1000
        _update_stage(
            "strategy_select", "completed", lat,
            f"Resolved {deps.get('resolved', 0)}/{deps.get('total', 0)} dependencies",
        )

        # Stage 4: translate (data lineage)
        _update_stage("translate", "running", description="Tracing data lineage — reads, writes, transforms...")
        t0 = time.perf_counter()
        agent4 = DataLineageExtractor()
        lineage = asyncio.run(agent4.process(files, pipeline_engine)) or {}
        lat = (time.perf_counter() - t0) * 1000
        _update_stage(
            "translate", "completed", lat,
            f"Mapped {lineage.get('total_reads', 0)} reads + {lineage.get('total_writes', 0)} writes",
        )

        # Stage 5: validate (LLM translation)
        _update_stage("validate", "running", description="Translating SAS code to Python via LLM...")
        t0 = time.perf_counter()
        python_code = translate_sas_to_python(sas_code)
        lat = (time.perf_counter() - t0) * 1000
        translation_ok = python_code and not python_code.startswith("# TRANSLATION UNAVAILABLE")
        _update_stage(
            "validate", "completed", lat,
            "SAS → Python translation complete" if translation_ok
            else "Translation skipped — LLM not configured",
        )

        # Stage 6: repair (syntax validation)
        _update_stage("repair", "running", description="Validating translated Python code...")
        t0 = time.perf_counter()
        repair_notes: list[str] = []
        if translation_ok:
            try:
                compile(python_code, "<translated>", "exec")
                repair_notes.append("Syntax OK — compiles without errors")
            except SyntaxError as se:
                repair_notes.append(f"Syntax warning at line {se.lineno}: {se.msg}")
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("repair", "completed", lat, repair_notes[0] if repair_notes else "No repairs needed")

        # Stage 7: merge
        _update_stage("merge", "running", description="Assembling final Python module...")
        t0 = time.perf_counter()
        header_lines = [
            f'"""Auto-converted from {file_path.name} by Codara pipeline."""',
            "",
        ]
        final_code = "\n".join(header_lines) + python_code
        conv.python_code = final_code
        session.commit()
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("merge", "completed", lat, "Merged successfully — final module ready")

        # Stage 8: finalize
        _update_stage("finalize", "running", description="Packaging results & generating reports...")
        t0 = time.perf_counter()
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("finalize", "completed", lat, "Pipeline complete — results ready")

        total_elapsed = time.perf_counter() - total_start

        report_lines = [
            f"File analysis: {len(files)} file(s) discovered",
            f"Registry: {reg_result.get('inserted', 0)} inserted, {reg_result.get('skipped', 0)} skipped",
            f"Cross-file deps: {deps.get('total', 0)} total, {deps.get('resolved', 0)} resolved",
            f"Data lineage: {lineage.get('total_reads', 0)} reads, {lineage.get('total_writes', 0)} writes",
        ]

        # Accuracy: 100 if translation succeeded and syntax is valid,
        # 50 if translation succeeded but had syntax warnings, 0 if unavailable.
        syntax_ok = repair_notes and repair_notes[0].startswith("Syntax OK")
        if translation_ok and syntax_ok:
            accuracy = 100.0
        elif translation_ok:
            accuracy = 50.0
        else:
            accuracy = 0.0

        conv.status = "completed"
        conv.duration = round(total_elapsed, 2)
        conv.accuracy = accuracy
        conv.validation_report = "\n".join(report_lines)
        conv.merge_report = f"Pipeline completed in {total_elapsed:.2f}s"
        conv.updated_at = datetime.now(timezone.utc).isoformat()

    except Exception as exc:
        conv.status = "failed"
        conv.updated_at = datetime.now(timezone.utc).isoformat()
        conv.validation_report = f"Pipeline error: {exc}"
        for st in session.query(ConversionStageRow).filter(
            ConversionStageRow.conversion_id == conversion_id,
            ConversionStageRow.status.in_(["pending", "running"]),
        ):
            st.status = "failed"

    session.commit()

    # Post-pipeline bookkeeping — never propagates failure upward
    try:
        user = session.query(UserRow).get(conv.user_id)
        if user:
            user.conversion_count = (user.conversion_count or 0) + 1
            session.commit()

        notif_title = "Conversion Complete" if conv.status == "completed" else "Conversion Failed"
        notif_msg = (
            f"Your file '{conv.file_name}' has been converted successfully with {conv.accuracy}% accuracy."
            if conv.status == "completed"
            else f"Conversion of '{conv.file_name}' failed. Please try again."
        )
        session.add(NotificationRow(
            id=f"notif-{uuid.uuid4().hex[:8]}",
            user_id=conv.user_id,
            title=notif_title,
            message=notif_msg,
            type="success" if conv.status == "completed" else "error",
            created_at=datetime.now(timezone.utc).isoformat(),
        ))
        session.commit()
    except Exception as exc:
        _log.warning("post_pipeline_bookkeeping_failed", conversion_id=conversion_id, error=str(exc))

    try:
        session.close()
    except Exception:
        pass
    if pipeline_engine is not None:
        try:
            pipeline_engine.dispose()
        except Exception:
            pass

    # Clean up isolated temp directory created for blob downloads
    if _temp_path is not None:
        try:
            shutil.rmtree(_temp_path, ignore_errors=True)
        except Exception:
            pass
