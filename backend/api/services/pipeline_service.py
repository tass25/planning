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
import os
import shutil
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

from api.core.database import (
    ConversionRow,
    ConversionStageRow,
    NotificationRow,
    UserRow,
    get_api_engine,
    get_api_session,
)
from api.services.blob_service import blob_service

_log = structlog.get_logger("codara.pipeline")

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


def _judge_translation_accuracy(sas_code: str, python_code: str) -> float:
    """Score semantic equivalence using NVIDIA NIM as an independent judge.

    NVIDIA NIM (meta/llama-3.1-70b-instruct) is used because it is completely
    separate from the translation chain (Ollama/Azure/Groq), giving an unbiased
    evaluation. Rotates across up to 5 NVIDIA API keys on failure.

    Returns 0-100.0 or -1.0 when unavailable (caller uses structural fallback).
    """
    import json
    import re

    from openai import OpenAI

    # Collect all NVIDIA keys in order (NVIDIA_API_KEY, NVIDIA_API_KEY_2, …5)
    nvidia_keys = []
    primary = os.getenv("NVIDIA_API_KEY", "").strip()
    if primary:
        nvidia_keys.append(primary)
    for i in range(2, 6):
        k = os.getenv(f"NVIDIA_API_KEY_{i}", "").strip()
        if k:
            nvidia_keys.append(k)

    if not nvidia_keys:
        return -1.0

    sas_snippet = sas_code[:3000]
    py_snippet = python_code[:3000]

    prompt = (
        "You are an independent code reviewer evaluating a SAS-to-Python translation.\n"
        "Score 0 to 100 using this rubric:\n"
        "  - Semantic equivalence: same logic and data transformations (50 pts)\n"
        "  - Completeness: all SAS blocks represented in Python (25 pts)\n"
        "  - Correctness: syntactically valid, idiomatic Python (25 pts)\n\n"
        'Reply ONLY with a JSON object — no prose, no markdown:\n'
        '{"score": <integer 0-100>, "reason": "<one sentence>"}\n\n'
        f"### Original SAS code\n{sas_snippet}\n\n"
        f"### Translated Python code\n{py_snippet}"
    )

    for key in nvidia_keys:
        try:
            client = OpenAI(api_key=key, base_url="https://integrate.api.nvidia.com/v1")
            resp = client.chat.completions.create(
                model="meta/llama-3.1-70b-instruct",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.0,
                timeout=25,
            )
            raw = (resp.choices[0].message.content or "").strip()
            # NVIDIA doesn't always honour json_object mode — parse via regex
            m = re.search(r"\{[^}]+\}", raw, re.DOTALL)
            if m:
                data = json.loads(m.group())
                score = float(data.get("score", -1))
                if 0.0 <= score <= 100.0:
                    _log.info(
                        "judge_accuracy_ok",
                        provider="nvidia",
                        score=score,
                        reason=data.get("reason", "")[:80],
                    )
                    return round(score, 1)
        except Exception as exc:
            _log.warning("judge_nvidia_failed", error=str(exc))

    return -1.0


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
            _temp_path = _temp_dir  # cleanup the whole dir on exit
        else:
            # Local mode: raw_path is already under uploads/file-XXXXXXXX/filename
            # which is an isolated per-upload directory — no move needed.
            file_path = raw_path
    except Exception as exc:
        _log.error(
            "pipeline_file_resolve_failed",
            conversion_id=conversion_id,
            file_id=file_id,
            filename=filename,
            error=str(exc),
        )
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
            st = (
                session.query(ConversionStageRow)
                .filter(
                    ConversionStageRow.conversion_id == conversion_id,
                    ConversionStageRow.stage == stage_name,
                )
                .first()
            )
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

    total_start = time.perf_counter()
    pipeline_engine = None

    try:
        from partition.orchestration.orchestrator import PartitionOrchestrator

        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        duckdb_path = os.getenv("DUCKDB_PATH", "data/analytics.duckdb")

        orchestrator = PartitionOrchestrator(
            redis_url=redis_url,
            duckdb_path=duckdb_path,
            target_runtime=conv.runtime or "python",
        )

        # Signal the frontend that the pipeline is running.
        _update_stage(
            "file_process", "running", description="Full 8-node LangGraph pipeline starting..."
        )
        for _s in (
            "sas_partition",
            "strategy_select",
            "translate",
            "validate",
            "repair",
            "merge",
            "finalize",
        ):
            _update_stage(_s, "running", description="Queued — waiting for upstream stage...")

        final_state = asyncio.run(orchestrator.run([str(file_path)]))

        total_elapsed = time.perf_counter() - total_start

        # --- Map orchestrator state → display stages ---
        n_files = len(final_state.get("file_metas", []))
        n_parts = final_state.get("partition_count", 0)
        n_raptor = len(final_state.get("raptor_nodes", []))
        conv_res = final_state.get("conversion_results", [])
        val_passed = final_state.get("validation_passed", 0)
        merge_res = final_state.get("merge_results", [])
        n_errors = len(final_state.get("errors", []))
        n_warnings = len(final_state.get("warnings", []))

        _update_stage(
            "file_process", "completed", None, f"{n_files} file(s) scanned — registry built"
        )
        _update_stage(
            "sas_partition",
            "completed",
            None,
            f"{n_parts} partition(s) — streaming + boundary detection",
        )
        _update_stage(
            "strategy_select",
            "completed",
            None,
            f"RAPTOR: {n_raptor} nodes — risk + strategy assigned",
        )
        _update_stage(
            "translate", "completed", None, f"{len(conv_res)} block(s) translated via 3-tier RAG"
        )
        _update_stage(
            "validate",
            "completed",
            None,
            f"{val_passed}/{len(conv_res)} passed semantic validation",
        )
        _update_stage("repair", "completed", None, f"{n_errors} error(s) | {n_warnings} warning(s)")
        _update_stage("merge", "completed", None, f"{len(merge_res)} script(s) assembled")
        _update_stage("finalize", "completed", None, f"Pipeline complete in {total_elapsed:.1f}s")

        # --- Extract python code and accuracy from first merge result ---
        python_code = ""
        merge_status_str = "FAILED"
        validation_report = ""
        merge_report = ""

        if merge_res:
            first = merge_res[0]
            merged = first.get("merged_script", {})
            python_code = merged.get("python_script", "")
            merge_status_str = merged.get("status", "FAILED")
            block_count = merged.get("block_count", 1) or 1
            partial = merged.get("partial_count", 0)
            human_rev = merged.get("human_review_count", 0)
            syntax_valid = merged.get("syntax_valid", False)

            report_obj = first.get("report", {})
            validation_report = (
                report_obj.get("report_md", "") if isinstance(report_obj, dict) else str(report_obj)
            )
            merge_report = (
                f"Merge status: {merge_status_str} | "
                f"Blocks: {block_count} | Partial: {partial} | "
                f"Human review: {human_rev} | Syntax valid: {syntax_valid}"
            )

        # Independent LLM judge (Groq) evaluates semantic equivalence.
        # Falls back to structural completeness metric when Groq is unavailable.
        judged_score = _judge_translation_accuracy(sas_code, python_code) if python_code else -1.0
        if judged_score >= 0.0:
            accuracy = judged_score
        elif merge_status_str == "SUCCESS":
            accuracy = 100.0
        elif merge_status_str == "HAS_GAPS":
            merged_block_count = merge_res[0].get("merged_script", {}).get("block_count", 1) or 1
            gaps = merge_res[0].get("merged_script", {}).get("partial_count", 0) + merge_res[0].get(
                "merged_script", {}
            ).get("human_review_count", 0)
            accuracy = round(100.0 * (merged_block_count - gaps) / merged_block_count, 1)
        else:
            accuracy = 0.0

        conv.python_code = python_code
        conv.status = "completed"
        conv.duration = round(total_elapsed, 2)
        conv.accuracy = accuracy
        conv.validation_report = validation_report
        conv.merge_report = merge_report
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
        session.add(
            NotificationRow(
                id=f"notif-{uuid.uuid4().hex[:8]}",
                user_id=conv.user_id,
                title=notif_title,
                message=notif_msg,
                type="success" if conv.status == "completed" else "error",
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        session.commit()
    except Exception as exc:
        _log.warning(
            "post_pipeline_bookkeeping_failed", conversion_id=conversion_id, error=str(exc)
        )

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
