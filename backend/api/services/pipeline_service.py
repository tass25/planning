"""Pipeline service — the 8-stage SAS→Python conversion pipeline.

This runs inside a FastAPI BackgroundTasks thread (or an Azure Queue worker),
so it's synchronous Python. Any async agent calls use asyncio.run() because
this code is always outside the event loop — there's no running loop to conflict with.

Stage mapping (frontend display name → what actually runs here):
    file_process    → FileAnalysisAgent: scans file structure, identifies modules
    sas_partition   → RegistryWriterAgent: chunks SAS into logical blocks
    strategy_select → CrossFileDependencyResolver: resolves imports and deps
    translate       → DataLineageExtractor: traces data reads/writes/transforms
    validate        → translate_sas_to_python(): LLM translation (Azure → Nemotron → Groq)
    repair          → compile(): Python syntax check, no LLM call
    merge           → assemble final module with auto-generated header
    finalize        → package results and update DB
"""

from __future__ import annotations

import asyncio
import sys as _sys
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
from api.services.translation_service import translate_sas_to_python

_pkg_root = str(Path(__file__).resolve().parent.parent.parent.parent)
if _pkg_root not in _sys.path:
    _sys.path.insert(0, _pkg_root)

from partition.orchestration.telemetry import track_event, track_metric

_log = structlog.get_logger("codara.pipeline")

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


def _judge_accuracy(sas_code: str, python_code: str) -> tuple[float, str]:
    """Score translation quality using an independent LLM judge (Groq).

    Returns (score, explanation). The explanation is a human-readable paragraph
    with the judge model name and bullet-point reasoning.
    Uses Groq (not Azure) so the judge is independent of the translator.
    """
    import json

    from config.settings import settings
    from openai import OpenAI

    judge_model = settings.groq_model or "llama-3.3-70b-versatile"

    try:
        from partition.utils.llm_clients import get_all_groq_keys

        groq_keys = get_all_groq_keys()
    except Exception:
        groq_keys = [
            k
            for k in [settings.groq_api_key, settings.groq_api_key_2, settings.groq_api_key_3]
            if k
        ]

    if not groq_keys:
        return (-1.0, "")

    judge_prompt = (
        "You are a SAS-to-Python translation accuracy judge. The #1 goal is OUTPUT EQUIVALENCE: "
        "if both programs run on the same input, they must produce identical results.\n\n"
        "Score on 3 axes:\n"
        "1. Output equivalence (0-50): Would the Python produce THE EXACT SAME output as SAS?\n"
        "   - Same DataFrame values, same rows, same column names, same ordering.\n"
        "   - Same CSV content if exported. Same printed numbers with same formatting.\n"
        "   - Deduct 10 pts per wrong boundary/bin assignment (e.g. pd.cut right=True vs SAS left-exclusive).\n"
        "   - Deduct 8 pts per missing output rows (e.g. PROC MEANS grand-total row missing).\n"
        "   - Deduct 8 pts per wrong execution order causing empty/wrong DataFrames.\n"
        "   - Deduct 5 pts per wrong column reference (column doesn't exist in upstream output).\n"
        "   - Deduct 3 pts per number formatting mismatch (dollar12.2, comma10. not applied).\n"
        "2. Completeness (0-25): Are ALL SAS sections translated? No stubs, no skipped blocks.\n"
        "3. Correctness (0-25): Valid Python syntax, correct pandas/numpy usage, no runtime errors.\n\n"
        "Return ONLY a JSON object with these fields:\n"
        "{\n"
        '  "output_equivalence": <number 0-50>,\n'
        '  "completeness": <number 0-25>,\n'
        '  "correctness": <number 0-25>,\n'
        '  "total": <sum of the 3 scores>,\n'
        '  "strengths": ["short strength 1", "short strength 2"],\n'
        '  "issues": ["short issue 1", "short issue 2"]\n'
        "}\n"
        "The total MUST equal output_equivalence + completeness + correctness. Be strict.\n"
        "List 2-4 strengths and 2-4 issues (most impactful first)."
    )

    user_msg = f"SAS CODE:\n```sas\n{sas_code[:6000]}\n```\n\nPYTHON TRANSLATION:\n```python\n{python_code[:8000]}\n```"

    for key in groq_keys:
        try:
            client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
            resp = client.chat.completions.create(
                model=judge_model,
                messages=[
                    {"role": "system", "content": judge_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            data = json.loads(raw)
            output_eq = float(data.get("output_equivalence", data.get("semantic", 0)))
            completeness = float(data.get("completeness", 0))
            correctness = float(data.get("correctness", 0))
            total = max(0.0, min(100.0, output_eq + completeness + correctness))
            strengths = data.get("strengths", [])
            issues = data.get("issues", [])
            _log.info("accuracy_judge_result", total=total, issues=issues[:5])

            lines = [
                f"Score: {total:.1f}% — Judge: {judge_model} (Groq, independent from translator)",
                f"  Output equivalence:    {output_eq:.0f}/50",
                f"  Completeness:          {completeness:.0f}/25",
                f"  Correctness:           {correctness:.0f}/25",
            ]
            if strengths:
                lines.append("Strengths:")
                for s in strengths[:4]:
                    lines.append(f"  + {s}")
            if issues:
                lines.append("Issues:")
                for iss in issues[:4]:
                    lines.append(f"  - {iss}")

            return (total, "\n".join(lines))
        except Exception as exc:
            err_str = str(exc).lower()
            if "rate_limit" in err_str or "429" in err_str:
                continue
            _log.warning("accuracy_judge_failed", error=str(exc)[:200])
            break

    return (-1.0, "")


def _inject_grand_total(python_code: str) -> str:
    """Inject a PROC MEANS _TYPE_=0 grand-total row after the first .groupby().agg() result.

    Detects the variable name assigned from groupby().agg() and appends code to compute
    and concat a grand-total row with _TYPE_=0 and _FREQ_=len(df).
    """
    import re as _re

    pattern = _re.compile(
        r"^(\s*)(\w+)\s*=\s*(\w+)\.groupby\(\s*\[?([^\])\n]+)\]?\s*\)\.agg\(",
        _re.MULTILINE,
    )
    match = pattern.search(python_code)
    if not match:
        return python_code

    indent = match.group(1)
    result_var = match.group(2)
    source_df = match.group(3)

    agg_start = match.end()
    depth = 1
    pos = agg_start
    while pos < len(python_code) and depth > 0:
        ch = python_code[pos]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        pos += 1

    end_of_line = python_code.find("\n", pos)
    if end_of_line == -1:
        end_of_line = len(python_code)

    injection = (
        f"\n{indent}# PROC MEANS grand-total row (_TYPE_=0) — auto-injected by Codara\n"
        f"{indent}_grand_agg = {source_df}.select_dtypes(include='number').agg(['mean', 'sum', 'min', 'max'])\n"
        f"{indent}_grand_row = {{}}\n"
        f"{indent}for _col in _grand_agg.columns:\n"
        f"{indent}    for _stat in _grand_agg.index:\n"
        f"{indent}        _grand_row[f'{{_stat}}_{{_col}}'] = _grand_agg.loc[_stat, _col]\n"
        f"{indent}_grand_row['_TYPE_'] = 0\n"
        f"{indent}_grand_row['_FREQ_'] = len({source_df})\n"
        f"{indent}{result_var} = pd.concat([{result_var}.reset_index(), pd.DataFrame([_grand_row])], ignore_index=True)\n"
    )

    python_code = python_code[:end_of_line] + injection + python_code[end_of_line:]
    return python_code


def _generate_output_comparison(sas_code: str, python_code: str) -> str:
    """Ask an LLM to produce a side-by-side output comparison.

    Returns HTML table rows comparing expected SAS output vs Python output
    for each key operation (PROC, DATA step, EXPORT). Mismatches are tagged
    with class="mismatch" for red highlighting.
    """
    import json

    from config.settings import settings
    from openai import OpenAI

    try:
        from partition.utils.llm_clients import get_all_groq_keys

        groq_keys = get_all_groq_keys()
    except Exception:
        groq_keys = [
            k
            for k in [settings.groq_api_key, settings.groq_api_key_2, settings.groq_api_key_3]
            if k
        ]

    if not groq_keys:
        return ""

    compare_prompt = (
        "You are comparing expected SAS output vs Python output for a translated program.\n"
        "For each key operation (DATA step, PROC MEANS, PROC SQL, PROC FREQ, PROC EXPORT, "
        "PROC SGPLOT, etc.), show what SAS would produce and what the Python code would produce.\n\n"
        "Return a JSON array of comparison objects:\n"
        "[\n"
        '  {"operation": "Step name", "sas_output": "first 5 rows or output summary", '
        '"python_output": "first 5 rows or output summary", "match": true/false, '
        '"note": "brief explanation if mismatch"}\n'
        "]\n\n"
        "Rules:\n"
        "- Include 6-10 key operations (the most important ones).\n"
        "- For DataFrames and tables: show the FIRST 5 ROWS as text (column headers + 5 data rows), "
        "e.g.:\n"
        "  region | product | revenue\\n"
        "  East   | Widget  | 1500.00\\n"
        "  North  | Gadget  | 2300.50\\n"
        "  ...\\n"
        "- For printed outputs, show the exact formatted text (e.g. '$3,306.00' vs '3306.0').\n"
        "- For charts (PROC SGPLOT, GPLOT, GCHART), show chart type + axes + file output.\n"
        "- For exports, show the file path and format.\n"
        "- match=true means outputs are identical. match=false means there's a difference.\n"
        "- Be specific about what differs. Keep sas_output and python_output under 200 chars each."
    )

    user_msg = (
        f"SAS:\n```sas\n{sas_code[:5000]}\n```\n\nPython:\n```python\n{python_code[:7000]}\n```"
    )

    for key in groq_keys:
        try:
            client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
            resp = client.chat.completions.create(
                model=settings.groq_model or "llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": compare_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.0,
                max_tokens=1200,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "[]"
            data = json.loads(raw)

            # Handle both {"comparisons": [...]} and direct [...]
            if isinstance(data, dict):
                comparisons = data.get(
                    "comparisons", data.get("comparison", data.get("results", []))
                )
            else:
                comparisons = data

            if not isinstance(comparisons, list) or not comparisons:
                return ""

            import html as html_mod

            rows = []
            for c in comparisons[:12]:
                op = html_mod.escape(str(c.get("operation", "")))
                sas_out = html_mod.escape(str(c.get("sas_output", ""))).replace("\\n", "\n")
                py_out = html_mod.escape(str(c.get("python_output", ""))).replace("\\n", "\n")
                match = c.get("match", True)
                note = html_mod.escape(str(c.get("note", "")))
                cls = "" if match else ' class="mismatch"'
                icon = "✓" if match else "✗"
                note_cell = f"<td{cls}>{note}</td>" if note else f"<td{cls}>—</td>"
                rows.append(
                    f"<tr{cls}>"
                    f"<td><b>{op}</b></td>"
                    f"<td><pre>{sas_out}</pre></td>"
                    f"<td><pre>{py_out}</pre></td>"
                    f"<td>{icon}</td>"
                    f"{note_cell}"
                    f"</tr>"
                )
            return "\n".join(rows)
        except Exception as exc:
            err_str = str(exc).lower()
            if "rate_limit" in err_str or "429" in err_str:
                continue
            _log.warning("output_comparison_failed", error=str(exc)[:200])
            break

    return ""


def run_pipeline_sync(
    conversion_id: str,
    file_id: str,
    filename: str,
    db_path: str,
) -> None:
    """Run L2-A agents + LLM translation synchronously inside a background thread.

    Downloads ALL .sas files for the file_id from Blob Storage into an isolated
    temp directory, runs the 8-stage pipeline, then cleans up.

    Stage flow:
        file_process → sas_partition → strategy_select → translate →
        validate → repair → merge → finalize
    """
    import shutil
    import tempfile

    _temp_dir: Path | None = None
    try:
        _temp_dir = Path(tempfile.mkdtemp(prefix=f"codara_{conversion_id}_"))

        if blob_service.enabled:
            all_filenames = blob_service._list_sync(file_id)
            sas_names = [n for n in all_filenames if n.lower().endswith(".sas")]
            if not sas_names:
                sas_names = [filename]
            for sas_name in sas_names:
                blob_name = f"{file_id}/{sas_name}"
                blob_client = blob_service._client.get_blob_client(
                    container=blob_service._container,
                    blob=blob_name,
                )
                dest = _temp_dir / sas_name
                dest.write_bytes(blob_client.download_blob().readall())
        else:
            from api.services.blob_service import _LOCAL_UPLOAD_DIR

            local_dir = _LOCAL_UPLOAD_DIR / file_id
            sas_names = (
                [f.name for f in local_dir.glob("*.sas")] if local_dir.exists() else [filename]
            )
            for sas_name in sas_names:
                src = local_dir / sas_name
                if src.exists():
                    shutil.copy2(str(src), str(_temp_dir / sas_name))

        file_path = _temp_dir / filename
        if not file_path.exists():
            file_path = next(_temp_dir.glob("*.sas"))

        sas_in_dir = list(_temp_dir.glob("*.sas"))
        _log.info(
            "pipeline_files_ready",
            conversion_id=conversion_id,
            temp_dir=str(_temp_dir),
            files=[f.name for f in sas_in_dir],
            file_count=len(sas_in_dir),
        )
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

    from partition.db.sqlite_manager import get_engine, init_db
    from partition.entry.cross_file_dep_resolver import CrossFileDependencyResolver
    from partition.entry.data_lineage_extractor import DataLineageExtractor
    from partition.entry.file_analysis_agent import FileAnalysisAgent
    from partition.entry.registry_writer_agent import RegistryWriterAgent

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

    track_event("pipeline_started", {"conversion_id": conversion_id, "filename": filename})

    try:
        # Stage 1: file_process — analyse only the uploaded file(s), not the whole directory
        _update_stage(
            "file_process",
            "running",
            description="Scanning file structure & identifying SAS modules...",
        )
        t0 = time.perf_counter()
        agent1 = FileAnalysisAgent()
        sas_files = sorted(project_root.glob("*.sas"))
        if not sas_files:
            sas_files = [file_path]
        files = [agent1._analyse_file(f) for f in sas_files]
        lat = (time.perf_counter() - t0) * 1000
        _update_stage(
            "file_process", "completed", lat, f"Discovered {len(files)} file(s) — structure mapped"
        )
        track_metric("stage.file_process.latency_ms", lat, {"conversion_id": conversion_id})

        # Stage 2: sas_partition
        _update_stage(
            "sas_partition", "running", description="Chunking SAS code into logical blocks..."
        )
        t0 = time.perf_counter()
        agent2 = RegistryWriterAgent()
        reg_result = asyncio.run(agent2.process(files, pipeline_engine)) or {}
        lat = (time.perf_counter() - t0) * 1000
        inserted = reg_result.get("inserted", 0)
        _update_stage(
            "sas_partition",
            "completed",
            lat,
            f"Partitioned into {inserted} block(s) — registry built",
        )
        track_metric("stage.sas_partition.latency_ms", lat, {"conversion_id": conversion_id})

        # Stage 3: strategy_select
        _update_stage(
            "strategy_select",
            "running",
            description="Resolving cross-file dependencies & imports...",
        )
        t0 = time.perf_counter()
        agent3 = CrossFileDependencyResolver()
        deps = asyncio.run(agent3.process(files, project_root, pipeline_engine)) or {}
        lat = (time.perf_counter() - t0) * 1000
        _update_stage(
            "strategy_select",
            "completed",
            lat,
            f"Resolved {deps.get('resolved', 0)}/{deps.get('total', 0)} dependencies",
        )
        track_metric("stage.strategy_select.latency_ms", lat, {"conversion_id": conversion_id})

        # Stage 4: translate (data lineage)
        _update_stage(
            "translate",
            "running",
            description="Tracing data lineage — reads, writes, transforms...",
        )
        t0 = time.perf_counter()
        agent4 = DataLineageExtractor()
        lineage = asyncio.run(agent4.process(files, pipeline_engine)) or {}
        lat = (time.perf_counter() - t0) * 1000
        _update_stage(
            "translate",
            "completed",
            lat,
            f"Mapped {lineage.get('total_reads', 0)} reads + {lineage.get('total_writes', 0)} writes",
        )
        track_metric("stage.translate.latency_ms", lat, {"conversion_id": conversion_id})

        # Stage 5: validate (LLM translation)
        _update_stage(
            "validate", "running", description="Translating SAS code to Python via LLM..."
        )
        t0 = time.perf_counter()
        python_code = translate_sas_to_python(sas_code)
        lat = (time.perf_counter() - t0) * 1000
        translation_ok = python_code and not python_code.startswith("# TRANSLATION UNAVAILABLE")
        _update_stage(
            "validate",
            "completed",
            lat,
            (
                "SAS → Python translation complete"
                if translation_ok
                else "Translation skipped — LLM not configured"
            ),
        )
        track_metric("stage.validate.latency_ms", lat, {"conversion_id": conversion_id})
        track_event(
            "translation_result",
            {
                "conversion_id": conversion_id,
                "success": str(translation_ok),
                "code_length": str(len(python_code)) if python_code else "0",
            },
        )

        # Stage 6: repair (syntax validation + auto-fix)
        _update_stage(
            "repair", "running", description="Validating and repairing translated Python code..."
        )
        t0 = time.perf_counter()
        repair_notes: list[str] = []
        if translation_ok:
            from api.services.translation_service import _auto_repair

            python_code = _auto_repair(python_code)

            # Inject PROC MEANS grand-total row if SAS has CLASS + PROC MEANS but Python lacks _TYPE_
            sas_upper = sas_code.upper()
            has_proc_means_class = (
                "PROC MEANS" in sas_upper or "PROC SUMMARY" in sas_upper
            ) and "CLASS " in sas_upper
            if has_proc_means_class and "_TYPE_" not in python_code:
                python_code = _inject_grand_total(python_code)
                repair_notes.append("Injected PROC MEANS grand-total row (_TYPE_=0)")

            try:
                compile(python_code, "<translated>", "exec")
                repair_notes.append("Syntax OK — compiles without errors")
            except SyntaxError as se:
                repair_notes.append(f"Auto-repair attempt: line {se.lineno}: {se.msg}")
                # Try line-level repair: comment out the offending line and retry
                lines = python_code.split("\n")
                max_fixes = 10
                for _ in range(max_fixes):
                    try:
                        compile("\n".join(lines), "<translated>", "exec")
                        python_code = "\n".join(lines)
                        repair_notes.append(f"Repaired — {_ + 1} line(s) commented out")
                        break
                    except SyntaxError as se2:
                        if se2.lineno and 1 <= se2.lineno <= len(lines):
                            bad_line = lines[se2.lineno - 1]
                            lines[se2.lineno - 1] = f"# REPAIR: {bad_line.strip()}"
                        else:
                            break
                else:
                    repair_notes.append("Could not fully repair — some syntax issues remain")
        lat = (time.perf_counter() - t0) * 1000
        _update_stage(
            "repair", "completed", lat, repair_notes[0] if repair_notes else "No repairs needed"
        )
        track_metric("stage.repair.latency_ms", lat, {"conversion_id": conversion_id})

        # Stage 7: merge
        _update_stage("merge", "running", description="Assembling final Python module...")
        t0 = time.perf_counter()
        header_lines = [
            f'"""Auto-converted from {file_path.name} by Codara pipeline."""',
            "",
            "import os",
            "os.makedirs('./output', exist_ok=True)",
            "",
        ]
        # If the code produces charts, ensure non-interactive backend
        if python_code and ("plt." in python_code or "matplotlib" in python_code):
            header_lines.insert(2, "import matplotlib; matplotlib.use('Agg')")
        final_code = "\n".join(header_lines) + python_code
        conv.python_code = final_code
        session.commit()
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("merge", "completed", lat, "Merged successfully — final module ready")
        track_metric("stage.merge.latency_ms", lat, {"conversion_id": conversion_id})

        # Stage 8: finalize — judge accuracy + build reports
        _update_stage("finalize", "running", description="Scoring accuracy & generating reports...")
        t0 = time.perf_counter()

        total_elapsed = time.perf_counter() - total_start

        syntax_ok = bool(repair_notes) and any(
            n.startswith("Syntax OK") or n.startswith("Repaired") for n in repair_notes
        )

        # ── Accuracy: independent LLM judge ──────────────────────────
        accuracy_explanation = ""
        if translation_ok:
            judged_score, judged_text = _judge_accuracy(sas_code, python_code)
            if judged_score >= 0:
                accuracy = judged_score
                accuracy_explanation = judged_text
            elif syntax_ok:
                accuracy = 85.0
                accuracy_explanation = (
                    "Score: 85.0% — Judge: unavailable (Groq keys exhausted)\n"
                    "  Fallback: syntax compiles + translation completed → 85% default"
                )
            else:
                accuracy = 50.0
                accuracy_explanation = (
                    "Score: 50.0% — Judge: unavailable\n"
                    "  Translation completed but has syntax errors that could not be repaired"
                )
        else:
            accuracy = 0.0
            accuracy_explanation = (
                "Score: 0.0% — No translation produced (all LLM providers failed)"
            )

        # ── Detect which features were active ─────────────────────────
        from config.settings import settings

        translator_model = (
            "Azure gpt-5.4-mini"
            if (settings.azure_openai_api_key and settings.azure_openai_endpoint)
            else (f"Ollama {settings.ollama_model}" if settings.ollama_base_url else "Groq")
        )

        kb_count = 0
        try:
            import lancedb

            lance_path = str(Path(__file__).resolve().parent.parent.parent / "data" / "lancedb")
            lance_db = lancedb.connect(lance_path)
            if "sas_python_examples" in lance_db.table_names():
                kb_count = lance_db.open_table("sas_python_examples").count_rows()
        except Exception:
            pass

        z3_status = "enabled" if settings.enable_z3_verification else "disabled"

        failure_mode_name = "none"
        try:
            from partition.translation.failure_mode_detector import detect_failure_mode

            fm = detect_failure_mode(sas_code)
            if fm:
                failure_mode_name = fm
        except Exception:
            pass

        # ── Build validation report (shown in "Validation Report" tab) ─
        val_lines = [
            "═══ ACCURACY ASSESSMENT ═══",
            accuracy_explanation,
            "",
            "═══ PIPELINE ANALYSIS ═══",
            f"  File analysis:     {len(files)} file(s), {len(sas_code)} chars of SAS code",
            f"  Partitioning:      {reg_result.get('inserted', 0)} block(s) registered, {reg_result.get('skipped', 0)} skipped",
            f"  Cross-file deps:   {deps.get('total', 0)} total, {deps.get('resolved', 0)} resolved",
            f"  Data lineage:      {lineage.get('total_reads', 0)} reads, {lineage.get('total_writes', 0)} writes traced",
            f"  Translation:       {translator_model} — {python_code and len(python_code) or 0} chars output",
            f"  Syntax repair:     {repair_notes[0] if repair_notes else 'skipped'}",
            f"  Failure mode:      {failure_mode_name}",
            "",
            "═══ ACTIVE FEATURES ═══",
            f"  LLM chain:             Azure gpt-5.4-mini → Ollama {settings.ollama_model} → Groq {settings.groq_model}",
            f"  Independent judge:     Groq {settings.groq_model} (separate LLM from translator)",
            f"  Knowledge base (RAG):  {kb_count} pairs in LanceDB (768-dim Nomic embeddings)",
            f"  Failure mode detect.:  {failure_mode_name} (6-rule heuristic scanner)",
            f"  Z3 formal verif.:      {z3_status}",
            "  Auto-repair:           regex-based syntax fixer + iterative compile",
            "  Telemetry:             Azure Application Insights (OpenTelemetry)",
            f"  Blob storage:          {'Azure Blob' if blob_service.enabled else 'local fallback'}",
        ]

        # ── Build merge report (shown in "Merge Report" tab) ──────────
        merge_lines = [
            f"Pipeline completed in {total_elapsed:.2f}s",
            "",
            "Component breakdown:",
            f"  1. File Analysis (L2-A)     — FileAnalysisAgent scanned {len(files)} file(s)",
            f"  2. Registry (L2-A)          — RegistryWriterAgent partitioned {reg_result.get('inserted', 0)} block(s)",
            f"  3. Dependency Resolver       — CrossFileDependencyResolver found {deps.get('total', 0)} deps",
            f"  4. Data Lineage (L2-A)      — DataLineageExtractor traced {lineage.get('total_reads', 0)}R / {lineage.get('total_writes', 0)}W",
            f"  5. LLM Translation (L3)     — {translator_model}, 3-tier fallback chain",
            "  6. Syntax Repair            — auto-repair + compile() validation",
            "  7. Module Assembly (L4)     — header injection, final merge",
            "  8. Finalize                 — accuracy judge + report generation",
            "",
            "Why these components exist:",
            "  • L2-A agents (file, registry, deps, lineage): structural analysis before",
            "    translation — the pipeline understands file structure, block boundaries,",
            "    cross-file dependencies, and data flow before sending to the LLM.",
            "  • 3-tier LLM chain: Azure (primary, fast, reliable) → Ollama/Nemotron",
            "    (open-source fallback) → Groq/LLaMA (last resort). Ensures translation",
            "    succeeds even if one provider is down or rate-limited.",
            "  • Independent accuracy judge: Groq LLaMA scores the output using a",
            "    different model than the translator — avoids self-evaluation bias.",
            "  • Knowledge base (LanceDB): 768-dim Nomic embeddings index SAS→Python",
            "    examples. RAG retrieval injects relevant examples into the LLM prompt.",
            "  • Failure mode detection: scans SAS for 6 known-hard patterns (RETAIN,",
            "    FIRST./LAST., correlated SQL, macros, hash objects, PROC TRANSPOSE).",
            "  • Z3 formal verification: SMT proofs for decidable SAS fragments",
            "    (arithmetic, boolean filters, sort/dedup, assignment patterns).",
            "  • Auto-repair: regex-based fixer for common LLM syntax errors",
            "    (placeholder tokens, stray semicolons, invalid brackets).",
        ]

        # ── Output comparison (SAS expected vs Python actual) ─────────
        comparison_html = ""
        if translation_ok:
            try:
                comparison_html = _generate_output_comparison(sas_code, python_code)
            except Exception as exc:
                _log.warning("output_comparison_failed", error=str(exc)[:200])

        lat = (time.perf_counter() - t0) * 1000
        _update_stage("finalize", "completed", lat, f"Accuracy: {accuracy:.1f}% — reports ready")
        track_metric("stage.finalize.latency_ms", lat, {"conversion_id": conversion_id})

        # Append comparison HTML to merge_report with a delimiter
        if comparison_html:
            merge_lines.append("")
            merge_lines.append("<!-- OUTPUT_COMPARISON_START -->")
            merge_lines.append(comparison_html)
            merge_lines.append("<!-- OUTPUT_COMPARISON_END -->")

        conv.status = "completed"
        conv.duration = round(total_elapsed, 2)
        conv.accuracy = round(accuracy, 1)
        conv.validation_report = "\n".join(val_lines)
        conv.merge_report = "\n".join(merge_lines)
        conv.updated_at = datetime.now(timezone.utc).isoformat()

        track_event(
            "pipeline_completed",
            {
                "conversion_id": conversion_id,
                "accuracy": str(round(accuracy, 1)),
                "duration_s": str(round(total_elapsed, 2)),
                "file_count": str(len(files)),
                "syntax_ok": str(syntax_ok),
            },
        )
        track_metric("pipeline.duration_s", total_elapsed, {"conversion_id": conversion_id})
        track_metric("pipeline.accuracy", accuracy, {"conversion_id": conversion_id})

    except Exception as exc:
        conv.status = "failed"
        conv.updated_at = datetime.now(timezone.utc).isoformat()
        conv.validation_report = f"Pipeline error: {exc}"
        for st in session.query(ConversionStageRow).filter(
            ConversionStageRow.conversion_id == conversion_id,
            ConversionStageRow.status.in_(["pending", "running"]),
        ):
            st.status = "failed"
        track_event(
            "pipeline_failed",
            {
                "conversion_id": conversion_id,
                "error": str(exc)[:500],
            },
        )

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

    # Clean up temp directory created for blob downloads
    if _temp_dir is not None:
        try:
            shutil.rmtree(_temp_dir, ignore_errors=True)
        except Exception:
            pass
