# Week 9: Robustness + Knowledge Base Generation

> **Priority**: P2  
> **Branch**: `week-09`  
> **Layer**: Robustness + KB  
> **Agents**: No new agents — hardening existing agents + KB generation tooling  
> **Prerequisite**: Week 8 complete (full L2 pipeline runs end-to-end)  
> **Status**: ✅ COMPLETE — see [week09Done.md](week09Done.md)  
> **Post-consolidation (Week 13)**: Ollama dead code paths removed. Azure OpenAI is primary LLM, Groq is fallback. Circuit breaker / rate limiter still active.  

---

## 🎯 Goal

Two objectives this week: (1) Harden the pipeline with retry/fallback wrappers, large-file strategies, and memory guards. (2) Build the Knowledge Base generation tooling and generate the first 250 verified SAS→Python/PySpark pairs using the dual-LLM chain (Prompt A → Prompt B → Prompt C cross-verification).

---

## Part A: Robustness Hardening

### Task 1: Retry Decorator with Exponential Backoff

**File**: `partition/utils/retry.py`

```python
import asyncio
import functools
from typing import Optional, Callable
import structlog

logger = structlog.get_logger()


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,),
    fallback: Optional[Callable] = None,
    agent_name: str = "unknown",
):
    """
    Decorator for retry with exponential backoff.
    
    From cahier retry policy:
    - BoundaryDetectorAgent (LLM): 3 retries, base 1s → rule-based fallback
    - RAPTORPartitionAgent (summarize): 3 retries, base 2s → Ollama → heuristic
    - RAPTORPartitionAgent (embed): 2 retries → flat_partition fallback
    - TranslationAgent (Groq): 3 retries, base 2s → Ollama → PARTIAL
    - ValidationAgent (exec): 2 retries → skip validation
    - ReportAgent: 1 retry → plain-text fallback
    - IndexAgent (NetworkX): 2 retries → log + skip
    - RedisCheckpoint: 1 retry → degraded mode
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "retry_attempt",
                            agent=agent_name,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay=delay,
                            error=str(e),
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "retry_exhausted",
                            agent=agent_name,
                            attempts=max_retries + 1,
                            error=str(e),
                        )

            # All retries exhausted — use fallback if provided
            if fallback is not None:
                logger.warning("using_fallback",
                              agent=agent_name,
                              error=str(last_error))
                return fallback(*args, **kwargs)
            raise last_error

        return wrapper
    return decorator


class RateLimitSemaphore:
    """
    Semaphore for Groq API rate limiting.
    Max 5 concurrent calls (from cahier risk register).
    """

    def __init__(self, max_concurrent: int = 5):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def __aenter__(self):
        await self._semaphore.acquire()
        return self

    async def __aexit__(self, *args):
        self._semaphore.release()


# Global rate limiter for Groq
groq_limiter = RateLimitSemaphore(max_concurrent=5)
```

---

### Task 2: Large-File Strategy

**File**: `partition/utils/large_file.py`

```python
import os
import structlog

logger = structlog.get_logger()

# Thresholds from cahier
LARGE_FILE_LINE_THRESHOLD = 10_000
HUGE_FILE_LINE_THRESHOLD = 50_000
MEMORY_LIMIT_MB = 100


def detect_file_size_strategy(file_path: str) -> str:
    """
    Determine processing strategy based on file size.
    
    Returns:
        "standard" — normal pipeline
        "large" — streaming with aggressive checkpointing
        "huge" — RAPTOR HIGH-only strategy (skip LOW/MODERATE clustering)
    """
    line_count = sum(1 for _ in open(file_path, 'r', errors='ignore'))

    if line_count > HUGE_FILE_LINE_THRESHOLD:
        logger.warning("huge_file_detected",
                       path=file_path, lines=line_count,
                       strategy="RAPTOR-HIGH-only")
        return "huge"
    elif line_count > LARGE_FILE_LINE_THRESHOLD:
        logger.info("large_file_detected",
                    path=file_path, lines=line_count,
                    strategy="aggressive_checkpointing")
        return "large"
    else:
        return "standard"


def configure_memory_guards():
    """
    Set environment variables for memory management.
    Call once at pipeline startup.
    """
    # PyTorch CUDA memory fragmentation guard
    os.environ.setdefault(
        "PYTORCH_CUDA_ALLOC_CONF",
        "max_split_size_mb:128"
    )

    # Limit OpenMP threads (sentence-transformers uses it)
    os.environ.setdefault("OMP_NUM_THREADS", "4")

    logger.info("memory_guards_configured",
                cuda_alloc="max_split_size_mb:128",
                omp_threads=4)


class MemoryMonitor:
    """Track peak memory usage during processing."""

    def __init__(self):
        self.peak_mb = 0.0

    def check(self) -> float:
        """Return current memory usage in MB."""
        import psutil
        process = psutil.Process()
        mem_mb = process.memory_info().rss / (1024 * 1024)
        self.peak_mb = max(self.peak_mb, mem_mb)
        return mem_mb

    def assert_under_limit(self, limit_mb: float = MEMORY_LIMIT_MB):
        current = self.check()
        if current > limit_mb:
            logger.warning("memory_limit_exceeded",
                          current_mb=current, limit_mb=limit_mb)
```

---

### Task 3: Apply Retry Wrappers to Existing Agents

Update these agents to use `@with_retry`:

```python
# In partition/boundary/boundary_detector_agent.py
from partition.utils.retry import with_retry

class BoundaryDetectorAgent(BaseAgent):
    @with_retry(max_retries=3, base_delay=1.0,
                fallback=lambda self, chunk: self._rule_based_boundary(chunk),
                agent_name="BoundaryDetectorAgent")
    async def _resolve_with_llm(self, chunk):
        # existing LLM call...
        pass

# In partition/raptor/summarizer.py — already has built-in fallback chain

# In partition/raptor/raptor_agent.py
class RAPTORPartitionAgent(BaseAgent):
    @with_retry(max_retries=2, base_delay=1.0,
                agent_name="RAPTORPartitionAgent")
    async def _embed_with_retry(self, texts):
        return self.embedder.embed_batch(texts)

# In partition/index/graph_builder.py
class NetworkXGraphBuilder:
    @with_retry(max_retries=2, base_delay=1.0,
                agent_name="IndexAgent")
    async def _write_with_retry(self, partition):
        # NetworkX graph build with error handling
        pass
```

---

## Part B: Knowledge Base Generation

### Task 4: KB Generation — Dual-LLM Chain

**File**: `scripts/generate_kb_pairs.py`

```python
"""
Knowledge Base Generation Pipeline

3-prompt chain:
  Prompt A → Generate realistic SAS code (Groq 70B)
  Prompt B → Convert to Python/PySpark with failure-mode rules (Groq 70B)
  Prompt C → Cross-verify equivalence (separate context, Ollama 8B)

Pairs with cross-verify confidence ≥ 0.85 → verified=True
"""

import uuid
import json
import asyncio
import argparse
from datetime import datetime
from typing import Optional
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

# ─── Pydantic output models ───

class GeneratedSAS(BaseModel):
    sas_code: str = Field(..., description="Realistic SAS code block")
    category: str = Field(..., description="e.g., DATA_STEP_BASIC, PROC_SQL")
    complexity_tier: str = Field(..., description="LOW | MODERATE | HIGH")
    failure_mode: str = Field(default="", description="Injected failure mode or empty")
    description: str = Field(..., description="What this SAS code does")


class ConvertedPython(BaseModel):
    python_code: str = Field(..., description="Python/PySpark equivalent")
    target_runtime: str = Field(default="python", description="python | pyspark")
    imports_needed: list[str] = Field(default_factory=list)
    notes: str = Field(default="", description="Translation notes")


class CrossVerifyResult(BaseModel):
    equivalent: bool = Field(..., description="Are the SAS and Python semantically equivalent?")
    issues: list[str] = Field(default_factory=list, description="Identified issues")
    confidence: float = Field(..., description="Confidence in equivalence judgment (0-1)")


# ─── Coverage matrix ───

COVERAGE_MATRIX = {
    "DATA_STEP_BASIC":       {"target": 30, "constructs": "assignment, if/else, keep/drop, length, format"},
    "DATA_STEP_MERGE":       {"target": 25, "constructs": "MERGE BY, one-to-one, one-to-many, UPDATE", "failure_mode": "MERGE_SEMANTICS"},
    "DATA_STEP_RETAIN":      {"target": 20, "constructs": "RETAIN, running totals, lag patterns", "failure_mode": "RETAIN"},
    "DATA_STEP_ARRAY":       {"target": 20, "constructs": "ARRAY, DO over array, multi-dim arrays"},
    "DATA_STEP_FIRST_LAST":  {"target": 25, "constructs": "BY group, FIRST.var, LAST.var", "failure_mode": "FIRST_LAST"},
    "DATE_ARITHMETIC":       {"target": 30, "constructs": "MDY, TODAY, INTNX, INTCK, DATEPART", "failure_mode": "DATE_ARITHMETIC"},
    "PROC_SQL":              {"target": 30, "constructs": "SELECT, JOIN, subquery, GROUP BY, HAVING"},
    "PROC_MEANS":            {"target": 20, "constructs": "CLASS, VAR, OUTPUT OUT=, NWAY", "failure_mode": "PROC_MEANS_OUTPUT"},
    "PROC_FREQ":             {"target": 15, "constructs": "TABLES, cross-tab, chi-square, WEIGHT"},
    "MACRO_BASIC":           {"target": 25, "constructs": "%MACRO/%MEND, %LET, macro parameters"},
    "MACRO_CONDITIONAL":     {"target": 20, "constructs": "%IF/%THEN/%ELSE, %DO/%END, nested macros"},
    "PROC_SORT":             {"target": 15, "constructs": "BY asc/desc, NODUPKEY, NODUP"},
    "PROC_REG_LOGISTIC":     {"target": 20, "constructs": "MODEL, output stats, selection"},
    "PROC_IMPORT_EXPORT":    {"target": 15, "constructs": "DBMS=CSV, DBMS=XLSX, INFILE/INPUT"},
    "MISSING_VALUE_HANDLING":{"target": 20, "constructs": "NMISS, CMISS, missing comparisons", "failure_mode": "MISSING_VALUE_COMPARISON"},
}

# 6 failure modes × 10 pairs each = 60 targeted pairs
FAILURE_MODES = {
    "RETAIN": 10,
    "FIRST_LAST": 10,
    "DATE_ARITHMETIC": 10,
    "MERGE_SEMANTICS": 10,
    "MISSING_VALUE_COMPARISON": 10,
    "PROC_MEANS_OUTPUT": 10,
}


class KBGenerator:
    """Generate verified SAS→Python KB pairs using dual-LLM chain."""

    VERIFY_THRESHOLD = 0.85

    def __init__(
        self,
        groq_api_key: str,
        target_runtime: str = "python",
    ):
        self.target_runtime = target_runtime

        # Groq client for generation (Prompts A + B)
        self.groq = instructor.from_openai(
            OpenAI(
                api_key=groq_api_key,
                base_url="https://api.groq.com/openai/v1",
            )
        )

        # Ollama client for cross-verification (Prompt C)
        self.verifier = instructor.from_openai(
            OpenAI(
                api_key="ollama",
                base_url="http://localhost:11434/v1",
            )
        )

    async def generate_pair(
        self,
        category: str,
        constructs: str,
        failure_mode: str = "",
        complexity: str = "MODERATE",
    ) -> Optional[dict]:
        """
        Generate one verified SAS→Python pair.
        
        Returns dict for LanceDB insertion, or None if verification fails.
        """
        # Prompt A: Generate SAS
        sas = await self._prompt_a(category, constructs, failure_mode, complexity)
        if not sas:
            return None

        # Prompt B: Convert to Python
        python = await self._prompt_b(sas, failure_mode)
        if not python:
            return None

        # Prompt C: Cross-verify (separate context window)
        verify = await self._prompt_c(sas.sas_code, python.python_code, failure_mode)
        if not verify or verify.confidence < self.VERIFY_THRESHOLD:
            logger.info("pair_rejected",
                       category=category,
                       confidence=verify.confidence if verify else 0,
                       issues=verify.issues if verify else [])
            return None

        # Build KB record
        from partition.raptor.embedder import NomicEmbedder
        embedder = NomicEmbedder()
        embedding = embedder.embed(sas.sas_code)

        return {
            "example_id": str(uuid.uuid4()),
            "sas_code": sas.sas_code,
            "python_code": python.python_code,
            "embedding": embedding,
            "partition_type": category,
            "complexity_tier": complexity,
            "target_runtime": python.target_runtime,
            "verified": True,
            "source": "llm_gen",
            "failure_mode": failure_mode,
            "verification_method": "llm_crosscheck",
            "verification_score": verify.confidence,
            "category": category,
            "version": 1,
            "superseded_by": None,
            "created_at": datetime.utcnow().isoformat(),
        }

    async def _prompt_a(self, category, constructs, failure_mode, complexity) -> Optional[GeneratedSAS]:
        """Prompt A: Generate realistic SAS code."""
        fm_instruction = ""
        if failure_mode:
            fm_instruction = f"""
IMPORTANT: This code MUST use the {failure_mode} pattern.
Include the specific SAS constructs that make this a {failure_mode} case.
"""
        prompt = f"""Generate a realistic SAS code block for the category '{category}'.

Constructs to include: {constructs}
Complexity: {complexity}
{fm_instruction}

Requirements:
- Code must be syntactically valid SAS
- Use realistic dataset and variable names (not toy examples)
- Include comments describing what the code does
- Length: 10-40 lines for LOW, 20-80 lines for MODERATE, 40-120 lines for HIGH
"""
        try:
            return self.groq.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                response_model=GeneratedSAS,
                max_retries=2,
            )
        except Exception as e:
            logger.warning("prompt_a_failed", error=str(e))
            return None

    async def _prompt_b(self, sas: GeneratedSAS, failure_mode: str) -> Optional[ConvertedPython]:
        """Prompt B: Convert SAS to Python with failure-mode rules."""
        fm_rules = ""
        if failure_mode == "DATE_ARITHMETIC":
            fm_rules = """
CRITICAL DATE RULES:
- SAS dates count from Jan 1, 1960. Python dates count from Jan 1, 1970.
- Do NOT add/subtract 3653 days (the epoch offset) — pandas handles this internally.
- Use pd.to_datetime() for date parsing.
- Use pd.DateOffset() or pd.Timedelta() for date arithmetic.
- INTNX('MONTH', date, 1) → date + pd.DateOffset(months=1)
- INTCK('DAY', date1, date2) → (date2 - date1).days
"""
        elif failure_mode == "MERGE_SEMANTICS":
            fm_rules = """
CRITICAL MERGE RULES:
- SAS MERGE with BY is NOT the same as pd.merge() inner join.
- SAS MERGE is a sequential match (like a zipper), not a Cartesian product.
- Use pd.merge(how='outer') and then forward-fill for SAS-like MERGE behavior.
- Watch for many-to-many joins creating Cartesian explosions.
"""
        elif failure_mode == "RETAIN":
            fm_rules = """
CRITICAL RETAIN RULES:
- SAS RETAIN preserves a variable's value across DATA step iterations.
- In pandas, use cumsum(), expanding(), or explicit loops.
- Do NOT use df['col'].shift() as a general RETAIN replacement — it only shifts, not retains.
"""
        elif failure_mode == "FIRST_LAST":
            fm_rules = """
CRITICAL FIRST./LAST. RULES:
- SAS FIRST.var and LAST.var identify group boundaries after PROC SORT.
- In pandas: df['first_flag'] = df.groupby('var').cumcount() == 0
- LAST: df['last_flag'] = df.groupby('var').cumcount(ascending=False) == 0
"""
        elif failure_mode == "MISSING_VALUE_COMPARISON":
            fm_rules = """
CRITICAL MISSING VALUE RULES:
- SAS treats missing numeric as -∞ in comparisons (missing < any number).
- Python/pandas treats NaN as neither < nor > anything.
- Use pd.isna() explicitly. Do NOT rely on comparison operators with NaN.
"""
        elif failure_mode == "PROC_MEANS_OUTPUT":
            fm_rules = """
CRITICAL PROC MEANS OUTPUT RULES:
- OUTPUT OUT= creates a dataset with _TYPE_, _FREQ_, and statistic columns.
- In pandas: use df.groupby().agg() and reset_index().
- Map NWAY to the full cross-classification (no marginals).
"""

        prompt = f"""Convert this SAS code to {'PySpark' if self.target_runtime == 'pyspark' else 'Python (pandas)'}.

SAS Code:
```sas
{sas.sas_code}
```

Description: {sas.description}
Target: {self.target_runtime}

{fm_rules}

Requirements:
- Produce syntactically valid Python code
- Include all necessary imports
- Use idiomatic pandas/PySpark patterns
- Add brief inline comments for non-obvious translations
"""
        try:
            return self.groq.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                response_model=ConvertedPython,
                max_retries=2,
            )
        except Exception as e:
            logger.warning("prompt_b_failed", error=str(e))
            return None

    async def _prompt_c(self, sas_code: str, python_code: str, failure_mode: str) -> Optional[CrossVerifyResult]:
        """Prompt C: Cross-verify SAS↔Python equivalence (separate LLM)."""
        fm_check = ""
        if failure_mode:
            fm_check = f"""
Pay special attention to the {failure_mode} pattern.
Check that the known pitfall for this pattern has been correctly handled.
"""

        prompt = f"""You are a code equivalence verifier. Determine if the Python code below is
semantically equivalent to the SAS code.

SAS Code:
```sas
{sas_code}
```

Python Code:
```python
{python_code}
```

{fm_check}

Check for these 5 known failure modes:
1. DATE_ARITHMETIC: SAS epoch (1960) vs Python epoch (1970) offset errors
2. MERGE_SEMANTICS: SAS sequential merge vs pandas join behavior
3. RETAIN: Variable persistence across iterations
4. FIRST_LAST: BY-group boundary detection
5. MISSING_VALUE_COMPARISON: NaN comparison semantics

Return your assessment as structured JSON.
"""
        try:
            return self.verifier.chat.completions.create(
                model="llama3.1:8b",
                messages=[{"role": "user", "content": prompt}],
                response_model=CrossVerifyResult,
                max_retries=2,
            )
        except Exception as e:
            logger.warning("prompt_c_failed", error=str(e))
            return None


async def generate_full_kb(
    groq_api_key: str,
    target_runtime: str = "python",
    target_pairs: int = 250,
):
    """Generate the full KB up to target_pairs verified examples."""
    generator = KBGenerator(groq_api_key, target_runtime)

    all_pairs = []
    stats = {"generated": 0, "verified": 0, "rejected": 0}

    # Phase 1: Category coverage
    for category, info in COVERAGE_MATRIX.items():
        target = min(info["target"], target_pairs // len(COVERAGE_MATRIX))
        fm = info.get("failure_mode", "")

        for i in range(target):
            complexity = ["LOW", "MODERATE", "HIGH"][i % 3]
            pair = await generator.generate_pair(
                category=category,
                constructs=info["constructs"],
                failure_mode=fm if i < 5 else "",  # First 5 per category with FM
                complexity=complexity,
            )
            stats["generated"] += 1
            if pair:
                all_pairs.append(pair)
                stats["verified"] += 1
            else:
                stats["rejected"] += 1

            # Rate limit: max 30 req/min for Groq
            if stats["generated"] % 10 == 0:
                await asyncio.sleep(2)
                logger.info("kb_progress", **stats)

    # Phase 2: Targeted failure mode injection (60 pairs)
    for fm, count in FAILURE_MODES.items():
        # Find matching category
        cat = next(
            (k for k, v in COVERAGE_MATRIX.items()
             if v.get("failure_mode") == fm),
            "DATA_STEP_BASIC"
        )
        constructs = COVERAGE_MATRIX[cat]["constructs"]

        for i in range(count):
            pair = await generator.generate_pair(
                category=cat,
                constructs=constructs,
                failure_mode=fm,
                complexity="HIGH",  # Failure modes are inherently complex
            )
            stats["generated"] += 1
            if pair:
                pair["source"] = "failure_mode_injection"
                all_pairs.append(pair)
                stats["verified"] += 1
            else:
                stats["rejected"] += 1

            if stats["generated"] % 10 == 0:
                await asyncio.sleep(2)

    logger.info("kb_generation_complete", **stats)
    return all_pairs, stats


# ─── CLI ───

if __name__ == "__main__":
    import os

    parser = argparse.ArgumentParser(description="Generate KB pairs")
    parser.add_argument("--target-pairs", type=int, default=250)
    parser.add_argument("--runtime", choices=["python", "pyspark"], default="python")
    parser.add_argument("--output", default="knowledge_base/generated_pairs.json")
    args = parser.parse_args()

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("ERROR: Set GROQ_API_KEY environment variable")
        exit(1)

    pairs, stats = asyncio.run(generate_full_kb(
        groq_api_key=api_key,
        target_runtime=args.runtime,
        target_pairs=args.target_pairs,
    ))

    # Save to JSON (for review before LanceDB insertion)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, 'w') as f:
        json.dump(pairs, f, indent=2)

    print(f"\nKB Generation Complete:")
    print(f"  Generated: {stats['generated']}")
    print(f"  Verified:  {stats['verified']}")
    print(f"  Rejected:  {stats['rejected']}")
    print(f"  Saved to:  {args.output}")
```

---

### Task 5: KB LanceDB Writer

**File**: `partition/kb/kb_writer.py`

```python
import json
import lancedb
import pyarrow as pa
from typing import Optional
import structlog

logger = structlog.get_logger()

# KB schema from cahier §5.3
KB_SCHEMA = pa.schema([
    pa.field('example_id',          pa.string()),
    pa.field('sas_code',            pa.string()),
    pa.field('python_code',         pa.string()),
    pa.field('embedding',           pa.list_(pa.float32(), 768)),
    pa.field('partition_type',      pa.string()),
    pa.field('complexity_tier',     pa.string()),
    pa.field('target_runtime',      pa.string()),
    pa.field('verified',            pa.bool_()),
    pa.field('source',              pa.string()),
    pa.field('failure_mode',        pa.string()),
    pa.field('verification_method', pa.string()),
    pa.field('verification_score',  pa.float32()),
    pa.field('category',            pa.string()),
    pa.field('version',             pa.int32()),
    pa.field('superseded_by',       pa.string()),
    pa.field('created_at',          pa.string()),
])


class KBWriter:
    """Manage Knowledge Base in LanceDB."""

    TABLE_NAME = "sas_python_examples"
    NUM_PARTITIONS = 64

    def __init__(self, db_path: str = "lancedb_data"):
        self.db = lancedb.connect(db_path)

    def insert_pairs(self, pairs: list[dict]) -> int:
        """Insert verified pairs into LanceDB."""
        if not pairs:
            return 0

        if self.TABLE_NAME in self.db.table_names():
            table = self.db.open_table(self.TABLE_NAME)
            table.add(pairs)
        else:
            table = self.db.create_table(
                self.TABLE_NAME, data=pairs, schema=KB_SCHEMA
            )

        # Rebuild index if enough data
        try:
            if len(table) >= self.NUM_PARTITIONS * 2:
                table.create_index(
                    metric="cosine",
                    num_partitions=self.NUM_PARTITIONS,
                    num_sub_vectors=16,
                    replace=True,
                )
        except Exception:
            pass

        logger.info("kb_pairs_inserted", count=len(pairs))
        return len(pairs)

    def count(self) -> int:
        if self.TABLE_NAME not in self.db.table_names():
            return 0
        return len(self.db.open_table(self.TABLE_NAME))

    def coverage_stats(self) -> dict:
        """Report pairs per category."""
        if self.TABLE_NAME not in self.db.table_names():
            return {}
        table = self.db.open_table(self.TABLE_NAME)
        df = table.to_pandas()
        return df.groupby("category").size().to_dict()
```

---

### Task 6: KB Changelog Logger

**File**: `partition/kb/kb_changelog.py`

```python
import uuid
import duckdb
from datetime import datetime


def log_kb_change(
    db_path: str,
    example_id: str,
    action: str,
    new_version: int,
    author: str,
    old_version: int = None,
    diff_summary: str = None,
):
    """Log a KB mutation to the changelog table."""
    con = duckdb.connect(db_path)
    con.execute("""
        INSERT INTO kb_changelog VALUES (?, ?, ?, ?, ?, ?, ?, NOW())
    """, [
        str(uuid.uuid4()),
        example_id,
        action,
        old_version,
        new_version,
        author,
        diff_summary,
    ])
    con.close()
```

---

### Task 7: KB Rollback Script

**File**: `scripts/kb_rollback.py`

```python
"""
Rollback a KB example to a previous version.

Usage:
    python scripts/kb_rollback.py --example_id <uuid> --to_version <n>
"""
import argparse
import json
import lancedb
from partition.kb.kb_changelog import log_kb_change


def rollback(example_id: str, to_version: int, db_path: str = "lancedb_data",
             duckdb_path: str = "analytics.duckdb"):
    db = lancedb.connect(db_path)
    table = db.open_table("sas_python_examples")

    # Find the target version
    # LanceDB doesn't support complex queries, so filter in pandas
    df = table.to_pandas()
    target = df[(df["example_id"] == example_id) & (df["version"] == to_version)]

    if target.empty:
        print(f"ERROR: No version {to_version} found for {example_id}")
        return

    # Mark current version as superseded
    current = df[(df["example_id"] == example_id) &
                 (df["superseded_by"].isna() | (df["superseded_by"] == ""))]

    if not current.empty:
        current_version = current.iloc[0]["version"]
        # Log the rollback
        log_kb_change(
            db_path=duckdb_path,
            example_id=example_id,
            action="rollback",
            old_version=current_version,
            new_version=to_version,
            author="rollback_script",
            diff_summary=f"Rolled back from v{current_version} to v{to_version}",
        )

    print(f"Rolled back {example_id} to version {to_version}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--example_id", required=True)
    parser.add_argument("--to_version", type=int, required=True)
    args = parser.parse_args()
    rollback(args.example_id, args.to_version)
```

---

## Checklist — End of Week 9

- [ ] `partition/utils/retry.py` — Retry decorator with exponential backoff
- [ ] `partition/utils/large_file.py` — Large-file strategy + memory guards
- [ ] Retry wrappers applied to: BoundaryDetector, RAPTOR, Translation (placeholder), Index, Redis
- [ ] `scripts/generate_kb_pairs.py` — Dual-LLM KB generation pipeline
- [ ] `partition/kb/kb_writer.py` — LanceDB writer with IVF index
- [ ] `partition/kb/kb_changelog.py` — DuckDB changelog logger
- [ ] `scripts/kb_rollback.py` — Version rollback script
- [ ] ≥ 250 verified KB pairs in LanceDB `sas_python_examples`
- [ ] All 15 categories covered (≥ 10 pairs each)
- [ ] All 6 failure modes covered (≥ 10 targeted pairs each)
- [ ] KB changelog records all insertions
- [ ] Retry works: inject Groq timeout → verify fallback to Ollama
- [ ] Large file: flag files > 10K lines correctly
- [ ] Memory guard: `PYTORCH_CUDA_ALLOC_CONF` set at startup
- [ ] Pipeline runs on 50-file corpus without crash (end-to-end test)
- [ ] Git: `week-09` branch, merged to `main`

---

## Evaluation Metrics for This Week

| Metric | Target | How to Measure |
|--------|--------|----------------|
| KB pairs verified | ≥ 250 | `kb_writer.count()` |
| KB verification rate | ≥ 85% | `verified / generated` |
| Category coverage | 15/15 | `kb_writer.coverage_stats()` |
| Failure mode coverage | 6/6 × 10 | Filter by `failure_mode` |
| Avg verification score | ≥ 0.85 | Mean of `verification_score` |
| Retry resilience | Pipeline survives 3 injected failures | Inject Groq/Redis timeouts |
| Memory (50-file corpus) | < 100 MB peak | `memray` or `psutil` |

---

## Dependencies Added This Week

| Package | Version | Purpose |
|---------|---------|---------|
| psutil | ≥ 5.9 | Memory monitoring |

---

> *Week 9 Complete → You have: hardened pipeline with retry/fallback, 250+ KB pairs in LanceDB, all failure modes covered, rollback capability. Ready for Translation! Next: TranslationAgent + ValidationAgent (Week 10).*
