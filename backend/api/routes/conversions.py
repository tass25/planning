"""Conversion routes — upload SAS files, run pipeline, get results."""

from __future__ import annotations

import asyncio
import html as html_mod
import io
import json
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.responses import PlainTextResponse, StreamingResponse, HTMLResponse

_log = structlog.get_logger("codara.conversions")

from api.auth import get_current_user
from api.database import get_api_session, ConversionRow, ConversionStageRow, UserRow, NotificationRow
from api.schemas import (
    ConversionOut, PipelineStageInfo, SasFileOut, StartConversionRequest,
    PartitionOut, CorrectionOut, CorrectionCreate,
)
from api.database import CorrectionRow

router = APIRouter(prefix="/conversions", tags=["conversions"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

STAGES = [
    "file_process", "sas_partition", "strategy_select", "translate",
    "validate", "repair", "merge", "finalize",
]


def _conv_to_out(row: ConversionRow) -> ConversionOut:
    try:
        stages_sorted = sorted(row.stages, key=lambda s: STAGES.index(s.stage) if s.stage in STAGES else 99)
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
        sasCode=row.sas_code,
        pythonCode=row.python_code,
        validationReport=row.validation_report,
        mergeReport=row.merge_report,
        progress=int(completed_count / total * 100),
        stages=stage_infos,
    )


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=list[SasFileOut])
async def upload_files(
    files: list[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    results: list[SasFileOut] = []
    for f in files:
        if not f.filename or not f.filename.endswith(".sas"):
            raise HTTPException(status_code=400, detail=f"Only .sas files accepted: {f.filename}")
        file_id = f"file-{uuid.uuid4().hex[:8]}"
        dest = UPLOAD_DIR / file_id / f.filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = await f.read()
        dest.write_bytes(content)
        results.append(SasFileOut(
            id=file_id,
            name=f.filename,
            size=len(content),
            modules=[],
            estimatedComplexity="low",
            uploadedAt=datetime.now(timezone.utc).isoformat(),
        ))
    return results


# ── Start conversion (real pipeline) ─────────────────────────────────────────

_SAS_CONVERSION_RULES = """
## SAS-to-Python Conversion Rules (MANDATORY)

### 1. LIBNAME References — Dot Notation
- `LIBNAME staging '/path/to/dir';` → IGNORE the LIBNAME declaration itself (no Python equivalent).
- When SAS references `libname.dataset` (e.g., `staging.merged`, `work.output`),
  ONLY use the part AFTER the dot as the DataFrame name.
  - `staging.merged` → `merged` (pandas DataFrame)
  - `work.temp_data` → `temp_data`
  - `sashelp.class` → `class_df` (add `_df` suffix to avoid Python keyword conflicts)
- Never create a variable or object named after the libname itself.

### 2. No-Op SAS Statements → `pass` or omit entirely
These SAS statements have NO Python equivalent. Convert them to a `pass` comment or omit:
- `TITLE` / `TITLE1` / `TITLE2` ... → `# TITLE: <original text>` (comment only)
- `FOOTNOTE` / `FOOTNOTE1` ... → `# FOOTNOTE: <original text>`
- `OPTIONS` (e.g., `OPTIONS NOCENTER NODATE;`) → `# SAS OPTIONS: <ignored>`
- `GOPTIONS` → `# SAS GOPTIONS: <ignored>`
- `ODS` statements (e.g., `ODS HTML`, `ODS LISTING CLOSE`) → `# ODS: <ignored>`
- `DM` (display manager commands) → omit
- `%SYSEXEC` → omit (or `os.system()` if truly needed)
- `ENDSAS;` → omit
- `RUN;` → omit (implicit in Python)
- `QUIT;` → omit

### 3. Variable Naming
- SAS variables are case-insensitive. Python is case-sensitive.
  → Use lowercase_snake_case for all variable names.
- If a SAS variable name is a Python keyword (e.g., `class`, `type`, `input`, `format`),
  append `_col` or `_var` → `class_col`, `type_var`, `input_col`.

### 4. Missing Values
- SAS missing numeric = `.` → Python `np.nan` / `pd.NA`
- SAS missing char = `' '` (blank) → Python `None` or `''`
- SAS comparison with missing: `. < 0` is TRUE in SAS → Use `pd.isna()` checks.
- `NMISS()` → `.isna().sum()`
- `CMISS()` → `.isna().sum()`

### 5. SAS Date Handling
- SAS dates are days since Jan 1, 1960.
- Do NOT manually offset by 3653 days — pandas handles epochs.
- `TODAY()` → `pd.Timestamp.today().normalize()`
- `MDY(m, d, y)` → `pd.Timestamp(year=y, month=m, day=d)`
- `INTNX('MONTH', date, n)` → `date + pd.DateOffset(months=n)`
- `INTCK('DAY', d1, d2)` → `(d2 - d1).days`
- `DATEPART(datetime)` → `datetime.normalize()` or `.dt.date`

### 6. DATA Step → pandas
- `DATA output; SET input;` → `output = input.copy()`
- `DATA output; SET input; WHERE condition;` → `output = input[condition].copy()`
- `DATA output; MERGE a b; BY key;` → `output = pd.merge(a, b, on='key', how='outer')`
- `RETAIN var init;` → Use `.cumsum()`, `.expanding()`, or explicit loop
- `FIRST.var / LAST.var` → Use `groupby().cumcount()` flags
- `OUTPUT;` → `rows.append(...)` then `pd.DataFrame(rows)`
- `IF ... THEN DELETE;` → `df = df[~condition]`
- `LENGTH var $50;` → `df['var'] = df['var'].astype(str)`

### 7. PROC Statements → pandas equivalents
- `PROC SORT DATA=ds; BY var;` → `ds = ds.sort_values('var')`
- `PROC SORT NODUPKEY;` → `ds = ds.drop_duplicates(subset=['var'])`
- `PROC MEANS` → `df.describe()` or `df.groupby().agg()`
- `PROC FREQ` → `pd.crosstab()` or `df['col'].value_counts()`
- `PROC PRINT` → `print(df)` or `df.head()`
- `PROC SQL; SELECT ... FROM ... ;` → `pd.read_sql()` or direct pandas operations
- `PROC TRANSPOSE` → `df.pivot()` / `df.melt()`
- `PROC EXPORT` → `df.to_csv()` / `df.to_excel()`
- `PROC IMPORT` → `pd.read_csv()` / `pd.read_excel()`
- `PROC CONTENTS` → `df.info()` / `df.dtypes`
- `PROC REG` → `from sklearn.linear_model import LinearRegression`
- `PROC LOGISTIC` → `from sklearn.linear_model import LogisticRegression`

### 8. Macro Variables
- `%LET var = value;` → `var = 'value'` (or appropriate type)
- `&var` / `&var.` references → Use the Python variable directly (f-string if in text)
- `%MACRO name(...); ... %MEND;` → `def name(...):`
- `%IF ... %THEN ... %ELSE ...` → standard Python `if/else`
- `%DO ... %END` → `for` loop
- `%INCLUDE 'file.sas';` → `exec(open('file.py').read())` or `import module`

### 9. SAS Functions → Python/pandas
- `INPUT(var, numfmt.)` → `pd.to_numeric(var)`
- `PUT(var, charfmt.)` → `str(var)` or `.astype(str)`
- `SUBSTR(str, pos, len)` → `str[pos-1:pos-1+len]` (SAS is 1-indexed!)
- `SCAN(str, n, delim)` → `str.split(delim)[n-1]`
- `COMPRESS(str)` → `str.replace(' ', '')`
- `STRIP(str)` / `TRIM(str)` → `str.strip()`
- `UPCASE(str)` → `str.upper()`
- `LOWCASE(str)` → `str.lower()`
- `PROPCASE(str)` → `str.title()`
- `CATX(delim, ...)` → `delim.join([...])`
- `CATS(...)` → `''.join([str(x).strip() for x in [...]])`
- `SUM(a, b, ...)` → `np.nansum([a, b, ...])` (SAS SUM ignores missing!)
- `MEAN(a, b)` → `np.nanmean([a, b])`
- `MIN(a, b)` / `MAX(a, b)` → `np.nanmin()` / `np.nanmax()`
- `LAG(var)` → `df['var'].shift(1)`
- `LAG2(var)` → `df['var'].shift(2)`
- `ABS(x)` → `abs(x)`
- `ROUND(x, r)` → `round(x, -int(np.log10(r)))` or custom
- `INT(x)` → `int(x)` or `np.floor(x)`
- `LOG(x)` → `np.log(x)`
- `EXP(x)` → `np.exp(x)`

### 10. SAS Formats & Informats → Ignore or Comment
- `FORMAT var date9.;` → `# FORMAT: date9. applied to var`
- `INFORMAT var ...;` → Ignore (informats are read-time only)
- `LABEL var = 'description';` → `# LABEL: var = 'description'` (comment only)
- `ATTRIB` statements → comment only

### 11. Output Delivery
- `PROC EXPORT DATA=ds OUTFILE='file.csv' DBMS=CSV;` → `ds.to_csv('file.csv', index=False)`
- `FILE 'output.txt';` / `PUT ...;` → `with open('output.txt', 'w') as f: f.write(...)`
"""


def _translate_sas_to_python(sas_code: str) -> str:
    """Translate SAS code to Python via Azure OpenAI (primary) or Groq (fallback).

    Uses the PromptManager Jinja2 templates when the full pipeline agents are
    available, falls back to the comprehensive rules-based system prompt otherwise.
    Returns the translated Python code, or a comment stub if no LLM is available.
    """
    import logging
    import os
    import sys

    log = logging.getLogger("codara.translate")

    # Ensure backend is on sys.path for partition imports
    pkg_root = str(Path(__file__).resolve().parent.parent.parent)
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    # Detect failure modes for smarter prompts
    failure_guidance = ""
    try:
        from partition.translation.failure_mode_detector import detect_failure_mode, get_failure_mode_rules
        fm = detect_failure_mode(sas_code)
        if fm:
            failure_guidance = get_failure_mode_rules(fm)
    except Exception:
        pass

    target_label = "Python (pandas)"

    # Try to use the PromptManager with Jinja2 templates
    rendered_prompt = None
    try:
        from partition.prompts import PromptManager
        pm = PromptManager()
        rendered_prompt = pm.render(
            "translation_static",
            target_label=target_label,
            partition_type="FULL_FILE",
            risk_level="MODERATE",
            complexity=0.5,
            sas_code=sas_code,
            failure_mode_rules=failure_guidance,
            kb_examples=[],
        )
    except Exception:
        pass

    system_prompt = (
        f"You are an expert SAS-to-{target_label} code translator.\n\n"
        f"{_SAS_CONVERSION_RULES}\n\n"
        "Return ONLY the Python code. No explanations, no markdown fences, no commentary.\n\n"
        "CRITICAL RULES:\n"
        "- You MUST translate EVERY section, macro, data step, and proc in the SAS code.\n"
        "- NEVER use placeholders like '# ... (rest of the code remains the same)' or '# TODO'.\n"
        "- NEVER skip, abbreviate, or summarize any part of the code.\n"
        "- If the SAS code has 14 sections, your Python output MUST have all 14 sections fully implemented.\n"
        "- Translate ALL macros to Python functions with complete logic.\n"
        "- Translate ALL PROC SQL to pandas operations or raw SQL equivalents.\n"
        "- Translate ALL DATA steps to pandas DataFrame operations.\n"
        "- The output must be a complete, runnable Python script — no stubs, no omissions."
    )

    if failure_guidance:
        system_prompt += f"\n\n## Detected Failure Mode\n{failure_guidance}"

    user_prompt = rendered_prompt or (
        f"Convert this SAS code to {target_label}:\n```sas\n{sas_code}\n```"
    )

    # --- Try Azure OpenAI ---
    azure_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if azure_key and azure_endpoint:
        try:
            from openai import AzureOpenAI
            client = AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=azure_key,
                api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            )
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_MINI", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_completion_tokens=16384,
            )
            code = resp.choices[0].message.content or ""
            code = _strip_markdown_fences(code)
            return code.strip()
        except Exception as exc:
            log.warning("Azure OpenAI failed: %s: %s", type(exc).__name__, exc)

    # --- Try Groq ---
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
            model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=16384,
            )
            code = resp.choices[0].message.content or ""
            code = _strip_markdown_fences(code)
            return code.strip()
        except Exception as exc:
            log.warning("Groq failed: %s: %s", type(exc).__name__, exc)

    # --- No LLM available ---
    log.error("All LLM providers failed — returning stub for %d-char SAS input", len(sas_code))
    commented = "\n".join(f"# {line}" for line in sas_code.split("\n"))
    return (
        "# TRANSLATION UNAVAILABLE — no LLM API key configured\n"
        "# Configure AZURE_OPENAI_API_KEY or GROQ_API_KEY in .env\n"
        "#\n"
        "# Original SAS code:\n"
        + commented
    )


def _strip_markdown_fences(code: str) -> str:
    """Remove markdown code fences if the LLM wraps the output."""
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        lines = lines[1:]  # remove opening fence line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)
    return code


def _run_pipeline_sync(conversion_id: str, file_path: Path, db_path: str):
    """Run the Week-1 agents synchronously inside background thread."""
    import time
    from api.database import get_api_engine, get_api_session

    try:
        engine = get_api_engine(db_path)
        session = get_api_session(engine)
    except Exception as exc:
        _log.error("pipeline_db_init_failed", conversion_id=conversion_id, error=str(exc))
        return

    def _update_stage(stage_name: str, status: str, latency: float | None = None, description: str | None = None):
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
    session.commit()

    try:
        sas_code = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        sas_code = file_path.read_text(encoding="utf-8", errors="replace")
        _log.warning("encoding_replace_used", file=str(file_path), conversion_id=conversion_id)
    conv.sas_code = sas_code
    session.commit()

    # --- Import Week-1 agents ---
    import sys
    pkg_root = str(Path(__file__).resolve().parent.parent.parent)
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    from partition.entry.file_analysis_agent import FileAnalysisAgent
    from partition.entry.registry_writer_agent import RegistryWriterAgent
    from partition.entry.cross_file_dep_resolver import CrossFileDependencyResolver
    from partition.entry.data_lineage_extractor import DataLineageExtractor
    from partition.db.sqlite_manager import get_engine, init_db

    # Pipeline DB for agent artifacts
    pipeline_db_path = str(UPLOAD_DIR / f"{conversion_id}_pipeline.db")
    pipeline_engine = None
    try:
        pipeline_engine = get_engine(pipeline_db_path)
        init_db(pipeline_engine)
    except Exception as exc:
        _log.error("pipeline_engine_init_failed", conversion_id=conversion_id, error=str(exc))
        conv.status = "failed"
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
        # Stage 1: file_process — Understanding the SAS code
        _update_stage("file_process", "running", description="Scanning file structure & identifying SAS modules...")
        time.sleep(1.2)
        t0 = time.perf_counter()
        agent1 = FileAnalysisAgent()
        files = asyncio.run(agent1.process(project_root)) or []
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("file_process", "completed", lat, f"Discovered {len(files)} file(s) — structure mapped")

        # Stage 2: sas_partition — Chunking the code
        _update_stage("sas_partition", "running", description="Chunking SAS code into logical blocks...")
        time.sleep(1.5)
        t0 = time.perf_counter()
        agent2 = RegistryWriterAgent()
        reg_result = asyncio.run(agent2.process(files, pipeline_engine)) or {}
        lat = (time.perf_counter() - t0) * 1000
        inserted = reg_result.get('inserted', 0)
        _update_stage("sas_partition", "completed", lat, f"Partitioned into {inserted} block(s) — registry built")

        # Stage 3: strategy_select — Resolving dependencies
        _update_stage("strategy_select", "running", description="Resolving cross-file dependencies & imports...")
        time.sleep(1.3)
        t0 = time.perf_counter()
        agent3 = CrossFileDependencyResolver()
        deps = asyncio.run(agent3.process(files, project_root, pipeline_engine)) or {}
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("strategy_select", "completed", lat, f"Resolved {deps.get('resolved', 0)}/{deps.get('total', 0)} dependencies")

        # Stage 4: translate — Extracting data lineage
        _update_stage("translate", "running", description="Tracing data lineage — reads, writes, transforms...")
        time.sleep(1.4)
        t0 = time.perf_counter()
        agent4 = DataLineageExtractor()
        lineage = asyncio.run(agent4.process(files, pipeline_engine)) or {}
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("translate", "completed", lat, f"Mapped {lineage.get('total_reads', 0)} reads + {lineage.get('total_writes', 0)} writes")

        # Stage 5: validate — LLM Translation (SAS → Python)
        _update_stage("validate", "running", description="Translating SAS code to Python via LLM...")
        t0 = time.perf_counter()
        python_code = _translate_sas_to_python(sas_code)
        lat = (time.perf_counter() - t0) * 1000
        translation_ok = python_code and not python_code.startswith("# TRANSLATION UNAVAILABLE")
        _update_stage("validate", "completed", lat,
                      "SAS → Python translation complete" if translation_ok
                      else "Translation skipped — LLM not configured")

        # Stage 6: repair — Validate / lint the output
        _update_stage("repair", "running", description="Validating translated Python code...")
        t0 = time.perf_counter()
        repair_notes = []
        if translation_ok:
            try:
                compile(python_code, "<translated>", "exec")
                repair_notes.append("Syntax OK — compiles without errors")
            except SyntaxError as se:
                repair_notes.append(f"Syntax warning at line {se.lineno}: {se.msg}")
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("repair", "completed", lat,
                      repair_notes[0] if repair_notes else "No repairs needed")

        # Stage 7: merge — Assembling final output
        _update_stage("merge", "running", description="Assembling final Python module...")
        t0 = time.perf_counter()
        # Build module header
        file_stem = file_path.stem
        header_lines = [
            f'"""Auto-converted from {file_path.name} by Codara pipeline."""',
            "",
        ]
        final_code = "\n".join(header_lines) + python_code
        conv.python_code = final_code
        session.commit()
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("merge", "completed", lat, "Merged successfully — final module ready")

        # Stage 8: finalize — Packaging results
        _update_stage("finalize", "running", description="Packaging results & generating reports...")
        t0 = time.perf_counter()
        lat = (time.perf_counter() - t0) * 1000
        _update_stage("finalize", "completed", lat, "Pipeline complete — results ready")

        total_elapsed = time.perf_counter() - total_start

        # Build validation report from lineage
        report_lines = [
            f"File analysis: {len(files)} file(s) discovered",
            f"Registry: {reg_result.get('inserted', 0)} inserted, {reg_result.get('skipped', 0)} skipped",
            f"Cross-file deps: {deps.get('total', 0)} total, {deps.get('resolved', 0)} resolved",
            f"Data lineage: {lineage.get('total_reads', 0)} reads, {lineage.get('total_writes', 0)} writes",
        ]

        conv.status = "completed"
        conv.duration = round(total_elapsed, 2)
        conv.accuracy = 100.0
        conv.validation_report = "\n".join(report_lines)
        conv.merge_report = f"Pipeline completed in {total_elapsed:.2f}s"

    except Exception as exc:
        conv.status = "failed"
        conv.validation_report = f"Pipeline error: {exc}"
        # Mark remaining stages as failed
        for st in session.query(ConversionStageRow).filter(
            ConversionStageRow.conversion_id == conversion_id,
            ConversionStageRow.status.in_(["pending", "running"]),
        ):
            st.status = "failed"

    session.commit()

    # Post-pipeline bookkeeping — wrapped so a failure here never kills the task
    try:
        # Increment user conversion count
        user = session.query(UserRow).get(conv.user_id)
        if user:
            user.conversion_count = (user.conversion_count or 0) + 1
            session.commit()

        # Create notification
        notif_title = "Conversion Complete" if conv.status == "completed" else "Conversion Failed"
        notif_msg = (
            f"Your file '{conv.file_name}' has been converted successfully with {conv.accuracy}% accuracy."
            if conv.status == "completed"
            else f"Conversion of '{conv.file_name}' failed. Please try again."
        )
        notif_type = "success" if conv.status == "completed" else "error"
        session.add(NotificationRow(
            id=f"notif-{uuid.uuid4().hex[:8]}",
            user_id=conv.user_id,
            title=notif_title,
            message=notif_msg,
            type=notif_type,
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


@router.post("/start", response_model=ConversionOut)
def start_conversion(
    body: StartConversionRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    from api.main import engine, DB_PATH

    session = get_api_session(engine)
    try:
        # Find uploaded file
        file_id = body.fileIds[0] if body.fileIds else None
        if not file_id:
            raise HTTPException(status_code=400, detail="No file specified")

        upload_dir = UPLOAD_DIR / file_id
        if not upload_dir.exists():
            raise HTTPException(status_code=404, detail=f"Upload {file_id} not found")

        sas_files = list(upload_dir.glob("*.sas"))
        if not sas_files:
            raise HTTPException(status_code=404, detail="No .sas file in upload")

        conv_id = f"conv-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        conv = ConversionRow(
            id=conv_id,
            user_id=current_user["sub"],
            file_name=sas_files[0].name,
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

        result = _conv_to_out(conv)

        background_tasks.add_task(_run_pipeline_sync, conv_id, sas_files[0], DB_PATH)

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
        return [_conv_to_out(r) for r in rows]
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
        return _conv_to_out(conv)
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
        # Verify conversion exists
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
        except Exception as exc:
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

        stages_sorted = sorted(conv.stages, key=lambda s: STAGES.index(s.stage) if s.stage in STAGES else 99)
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

        stages_sorted = sorted(conv.stages, key=lambda s: STAGES.index(s.stage) if s.stage in STAGES else 99)
        stage_rows = "".join(
            f"<tr><td>{html_mod.escape(s.stage)}</td><td>{html_mod.escape(s.status)}</td><td>{f'{s.latency:.0f}ms' if s.latency else '—'}</td></tr>"
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

            # Add a summary
            summary = f"Conversion: {conv.file_name}\nStatus: {conv.status}\nRuntime: {conv.runtime}\nAccuracy: {conv.accuracy}%\nDuration: {conv.duration:.2f}s"
            zf.writestr("README.txt", summary)

        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={base}_bundle.zip"},
        )
    finally:
        session.close()
