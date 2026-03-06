# Week 10: Translation Layer (L3) — TranslationAgent + ValidationAgent

> **Priority**: P2  
> **Branch**: `week-10`  
> **Layer**: L3 — Translation  
> **Agents**: TranslationAgent (#12), ValidationAgent (#13)  
> **Prerequisite**: Week 9 complete (250 KB pairs, retry wrappers, robustness)  
> **Status**: ✅ COMPLETE — see [week10Done.md](week10Done.md)  
> **Post-consolidation (Week 13)**: TranslationAgent + ValidationAgent consolidated into `TranslationPipeline` (single wrapper class). Azure OpenAI GPT-4o is primary, Groq is fallback (Ollama removed).  

---

## 🎯 Goal

Implement the core code-generation pipeline: TranslationAgent converts SAS partitions to Python/PySpark using failure-mode-aware prompting and KB retrieval; ValidationAgent verifies the generated code by executing it against synthetic DataFrames. Together they form the L3 translation loop with retry and fallback routing.

---

## Architecture Recap — L3 Data Flow

```
PartitionIR (from L2-E)
  ↓
TranslationAgent (#12)
  ├─ 1. Failure-mode detection (6 rules)
  ├─ 2. KB retrieval (LanceDB k=5, filtered by partition_type + failure_mode + target_runtime)
  ├─ 3. LLM routing: LOW → Ollama 8B, MODERATE/HIGH → Groq 70B
  ├─ 4. Translation prompt (few-shot from KB + failure-mode rules)
  ├─ 5. Cross-verify Prompt C (confidence < 0.75 → retry, max 2)
  └─ 6. SCC batching (from IndexAgent NetworkX graph)
  ↓
ConversionResult
  ↓
ValidationAgent (#13)
  ├─ 1. ast.parse() — syntax check
  ├─ 2. exec() sandbox on synthetic 100-row DataFrame (5s timeout)
  └─ 3. Routing: pass → L4, fail + retry < 2 → retranslate, fail + retry ≥ 2 → PARTIAL
  ↓
ConversionResult (updated status) → L4 Merge
```

---

## Task 1: Failure Mode Detector

**File**: `partition/translation/failure_mode_detector.py`

```python
"""
Rule-based failure mode detection for SAS partitions.
6 failure modes from cahier §5.2.

Returns the detected failure mode (if any) so the translation prompt
can inject failure-mode-specific rules.
"""

import re
from enum import Enum
from typing import Optional


class FailureMode(str, Enum):
    RETAIN = "RETAIN"
    FIRST_LAST = "FIRST_LAST"
    DATE_ARITHMETIC = "DATE_ARITHMETIC"
    MERGE_SEMANTICS = "MERGE_SEMANTICS"
    MISSING_VALUE_COMPARISON = "MISSING_VALUE_COMPARISON"
    PROC_MEANS_OUTPUT = "PROC_MEANS_OUTPUT"


# Patterns are applied to raw_code (case-insensitive)
DETECTION_RULES: list[tuple[FailureMode, list[re.Pattern]]] = [
    (FailureMode.RETAIN, [
        re.compile(r'\bRETAIN\b', re.IGNORECASE),
    ]),
    (FailureMode.FIRST_LAST, [
        re.compile(r'\bFIRST\.\w+', re.IGNORECASE),
        re.compile(r'\bLAST\.\w+', re.IGNORECASE),
    ]),
    (FailureMode.DATE_ARITHMETIC, [
        re.compile(r'\b(INTNX|INTCK|MDY|TODAY\(\)|DATEPART)\b', re.IGNORECASE),
    ]),
    (FailureMode.MERGE_SEMANTICS, [
        re.compile(r'\bMERGE\b.*\bBY\b', re.IGNORECASE | re.DOTALL),
    ]),
    (FailureMode.MISSING_VALUE_COMPARISON, [
        re.compile(r'\b(NMISS|CMISS)\b', re.IGNORECASE),
        re.compile(r'\.[\s]*[<>=]', re.IGNORECASE),  # missing value dot comparisons
    ]),
    (FailureMode.PROC_MEANS_OUTPUT, [
        re.compile(r'PROC\s+MEANS\b.*OUTPUT\s+OUT\s*=', re.IGNORECASE | re.DOTALL),
    ]),
]


def detect_failure_mode(raw_code: str) -> Optional[FailureMode]:
    """
    Detect the primary failure mode in a SAS code block.
    
    Returns the first matching failure mode, or None if no special
    pattern is detected.
    """
    for mode, patterns in DETECTION_RULES:
        for pattern in patterns:
            if pattern.search(raw_code):
                return mode
    return None


def get_failure_mode_rules(mode: FailureMode) -> str:
    """
    Return the failure-mode-specific translation rules
    to inject into the translation prompt.
    """
    RULES = {
        FailureMode.DATE_ARITHMETIC: """
CRITICAL DATE RULES:
- SAS dates count from Jan 1, 1960. Python dates use Jan 1, 1970.
- Do NOT add/subtract 3653 days manually — pandas handles epoch internally.
- Use pd.to_datetime() for date parsing.
- INTNX('MONTH', date, 1) → date + pd.DateOffset(months=1)
- INTCK('DAY', date1, date2) → (date2 - date1).days
- MDY(m, d, y) → pd.Timestamp(year=y, month=m, day=d)
- TODAY() → pd.Timestamp.today()
""",
        FailureMode.MERGE_SEMANTICS: """
CRITICAL MERGE RULES:
- SAS MERGE with BY is sequential (like a zipper), NOT a Cartesian product.
- pd.merge(how='inner') for matching rows; how='outer' for SAS MERGE behavior.
- Many-to-many: SAS handles differently than pandas — use merge_asof() or explicit loop.
- Always verify row counts after merge to detect Cartesian explosion.
""",
        FailureMode.RETAIN: """
CRITICAL RETAIN RULES:
- SAS RETAIN preserves a variable's value across DATA step iterations.
- In pandas: use cumsum(), expanding(), or explicit loops.
- Do NOT use df['col'].shift() as a general RETAIN replacement.
- For running totals: df['running'] = df['value'].cumsum()
- For conditional retain: iterate with iloc or use groupby().transform().
""",
        FailureMode.FIRST_LAST: """
CRITICAL FIRST./LAST. RULES:
- SAS FIRST.var = 1 when current row is first in BY group.
- SAS LAST.var = 1 when current row is last in BY group.
- pandas: df['first_flag'] = df.groupby('var').cumcount() == 0
- pandas: df['last_flag'] = df.groupby('var').cumcount(ascending=False) == 0
- Data MUST be sorted by the BY variable(s) first.
""",
        FailureMode.MISSING_VALUE_COMPARISON: """
CRITICAL MISSING VALUE RULES:
- SAS treats missing numeric (.​) as -infinity in comparisons.
- Python/pandas NaN: x < NaN is False, x > NaN is False.
- Use pd.isna() / pd.notna() for explicit checks.
- Replace SAS c.​ comparisons: if x = . → if pd.isna(x)
- NMISS → df.isna().sum(), CMISS → df.isna().sum() (for char vars)
""",
        FailureMode.PROC_MEANS_OUTPUT: """
CRITICAL PROC MEANS OUTPUT RULES:
- OUTPUT OUT= creates a dataset with _TYPE_, _FREQ_, and statistic columns.
- pandas: df.groupby(class_vars).agg({var: [stat]}).reset_index()
- NWAY: only the full cross-classification row (_TYPE_ = max).
- Map statistic names: MEAN→'mean', STD→'std', MIN→'min', MAX→'max', N→'count'
""",
    }
    return RULES.get(mode, "")
```

---

## Task 2: KB Query Client

**File**: `partition/translation/kb_query.py`

```python
"""
Knowledge Base retrieval for translation context.
Queries LanceDB with filtering by partition_type, failure_mode, and target_runtime.
"""

import lancedb
from typing import Optional
import structlog

logger = structlog.get_logger()


class KBQueryClient:
    """Query the sas_python_examples KB in LanceDB."""

    TABLE_NAME = "sas_python_examples"
    MIN_RELEVANCE = 0.50  # Discard results below this similarity

    def __init__(self, db_path: str = "lancedb_data"):
        self.db = lancedb.connect(db_path)

    def retrieve_examples(
        self,
        query_embedding: list[float],
        partition_type: str,
        failure_mode: Optional[str] = None,
        target_runtime: str = "python",
        k: int = 5,
    ) -> list[dict]:
        """
        Retrieve k most relevant KB examples for a partition.
        
        Filters:
          - partition_type must match (exact)
          - failure_mode must match (if specified)
          - target_runtime must match
          - verified = True only
          - cosine similarity ≥ MIN_RELEVANCE
        
        Returns list of dicts with sas_code, python_code, similarity.
        """
        if self.TABLE_NAME not in self.db.table_names():
            logger.warning("kb_table_missing", table=self.TABLE_NAME)
            return []

        table = self.db.open_table(self.TABLE_NAME)

        # Build filter expression
        where_clause = (
            f"partition_type = '{partition_type}' "
            f"AND target_runtime = '{target_runtime}' "
            f"AND verified = true"
        )
        if failure_mode:
            where_clause += f" AND failure_mode = '{failure_mode}'"

        try:
            results = (
                table.search(query_embedding)
                .where(where_clause)
                .limit(k)
                .to_pandas()
            )

            # Filter by minimum relevance
            if "_distance" in results.columns:
                # LanceDB returns distance (lower = closer)
                # Convert to similarity: 1 - distance for cosine
                results["similarity"] = 1 - results["_distance"]
                results = results[results["similarity"] >= self.MIN_RELEVANCE]

            examples = []
            for _, row in results.iterrows():
                examples.append({
                    "example_id": row["example_id"],
                    "sas_code": row["sas_code"],
                    "python_code": row["python_code"],
                    "similarity": row.get("similarity", 0),
                    "failure_mode": row.get("failure_mode", ""),
                    "category": row.get("category", ""),
                })

            logger.info("kb_retrieved",
                       partition_type=partition_type,
                       failure_mode=failure_mode,
                       k=k,
                       returned=len(examples))
            return examples

        except Exception as e:
            logger.warning("kb_query_failed", error=str(e))
            return []
```

---

## Task 3: TranslationAgent

**File**: `partition/translation/translation_agent.py`

```python
"""
TranslationAgent (#12) — L3

Converts SAS partitions to Python/PySpark using:
1. Failure-mode detection
2. KB retrieval (LanceDB, k=5)
3. LLM routing (LOW→8B, MODERATE/HIGH→70B)
4. Cross-verification (Prompt C)
5. SCC batching for circular dependencies
"""

import uuid
import asyncio
from datetime import datetime
from typing import Optional
import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
import structlog

from partition.agents.base_agent import BaseAgent
from partition.models.partition_ir import PartitionIR
from partition.models.conversion_result import ConversionResult, ConversionStatus
from partition.translation.failure_mode_detector import (
    detect_failure_mode, get_failure_mode_rules
)
from partition.translation.kb_query import KBQueryClient
from partition.raptor.embedder import NomicEmbedder
from partition.utils.retry import with_retry, groq_limiter

logger = structlog.get_logger()


class TranslationOutput(BaseModel):
    python_code: str = Field(..., description="Translated Python/PySpark code")
    imports_detected: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: str = Field(default="")


class CrossVerifyOutput(BaseModel):
    equivalent: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)


class TranslationAgent(BaseAgent):
    """
    Agent #12: SAS → Python/PySpark translation.
    
    Routing:
      - LOW risk → Ollama 8B (fast, local)
      - MODERATE/HIGH → Groq 70B (higher quality)
    
    Fallback chain (from retry policy):
      Groq 70B → Ollama 70B → PARTIAL status
    """

    MAX_RETRIES = 2
    CROSSVERIFY_THRESHOLD = 0.75

    def __init__(
        self,
        target_runtime: str = "python",
        groq_api_key: Optional[str] = None,
    ):
        super().__init__(agent_name="TranslationAgent")
        self.target_runtime = target_runtime
        self.embedder = NomicEmbedder()
        self.kb_client = KBQueryClient()

        # Groq client (70B)
        if groq_api_key:
            self.groq_client = instructor.from_openai(
                OpenAI(
                    api_key=groq_api_key,
                    base_url="https://api.groq.com/openai/v1",
                )
            )
        else:
            self.groq_client = None

        # Ollama client (8B + 70B fallback)
        self.ollama_client = instructor.from_openai(
            OpenAI(
                api_key="ollama",
                base_url="http://localhost:11434/v1",
            )
        )

    async def process(self, partition: PartitionIR) -> ConversionResult:
        """Translate a single partition."""
        trace_id = partition.trace_id or uuid.uuid4()

        # Step 1: Detect failure mode
        failure_mode = detect_failure_mode(partition.raw_code)
        fm_rules = get_failure_mode_rules(failure_mode) if failure_mode else ""

        # Step 2: Retrieve KB examples
        embedding = self.embedder.embed(partition.raw_code)
        kb_examples = self.kb_client.retrieve_examples(
            query_embedding=embedding,
            partition_type=partition.partition_type.value,
            failure_mode=failure_mode.value if failure_mode else None,
            target_runtime=self.target_runtime,
            k=5,
        )

        # Step 3: Build prompt
        prompt = self._build_prompt(partition, kb_examples, fm_rules)

        # Step 4: Route to LLM
        model_used = "ollama_8b"
        translation = None
        retry_count = 0

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if partition.risk_level.value in ("MODERATE", "HIGH", "UNCERTAIN"):
                    translation, model_used = await self._translate_groq(prompt)
                else:
                    translation = await self._translate_ollama_8b(prompt)
                    model_used = "ollama_8b"
                break
            except Exception as e:
                retry_count += 1
                logger.warning("translation_retry",
                              partition_id=str(partition.partition_id),
                              attempt=attempt + 1,
                              error=str(e))
                if attempt == self.MAX_RETRIES:
                    # All retries exhausted → PARTIAL
                    return ConversionResult(
                        conversion_id=uuid.uuid4(),
                        partition_id=partition.partition_id,
                        source_file_id=partition.source_file_id,
                        python_code=f"# PARTIAL: Translation failed after {retry_count} retries\n"
                                    f"# Original SAS:\n"
                                    + "\n".join(f"# {line}" for line in partition.raw_code.split("\n")),
                        imports_detected=[],
                        status=ConversionStatus.PARTIAL,
                        llm_confidence=0.0,
                        failure_mode_flagged=failure_mode.value if failure_mode else "",
                        model_used=model_used,
                        kb_examples_used=[ex["example_id"] for ex in kb_examples],
                        retry_count=retry_count,
                        trace_id=trace_id,
                        created_at=datetime.utcnow(),
                    )

        # Step 5: Cross-verify (Prompt C, separate context)
        verify = await self._cross_verify(
            partition.raw_code,
            translation.python_code,
            failure_mode,
        )

        status = ConversionStatus.SUCCESS
        if verify and verify.confidence < self.CROSSVERIFY_THRESHOLD:
            if retry_count < self.MAX_RETRIES:
                # Retry with enhanced prompt
                retry_count += 1
                enhanced_prompt = prompt + (
                    f"\n\nPREVIOUS ATTEMPT ISSUES:\n"
                    + "\n".join(verify.issues)
                    + "\nPlease fix these issues."
                )
                try:
                    translation, model_used = await self._translate_groq(enhanced_prompt)
                    verify = await self._cross_verify(
                        partition.raw_code, translation.python_code, failure_mode
                    )
                except Exception:
                    pass

            if not verify or verify.confidence < self.CROSSVERIFY_THRESHOLD:
                status = ConversionStatus.PARTIAL

        return ConversionResult(
            conversion_id=uuid.uuid4(),
            partition_id=partition.partition_id,
            source_file_id=partition.source_file_id,
            python_code=translation.python_code,
            imports_detected=translation.imports_detected,
            status=status,
            llm_confidence=verify.confidence if verify else translation.confidence,
            failure_mode_flagged=failure_mode.value if failure_mode else "",
            model_used=model_used,
            kb_examples_used=[ex["example_id"] for ex in kb_examples],
            retry_count=retry_count,
            trace_id=trace_id,
            created_at=datetime.utcnow(),
        )

    def _build_prompt(
        self,
        partition: PartitionIR,
        kb_examples: list[dict],
        fm_rules: str,
    ) -> str:
        """Build the translation prompt with few-shot examples and failure-mode rules."""
        # Few-shot examples section
        few_shot = ""
        if kb_examples:
            few_shot = "\n\n--- REFERENCE EXAMPLES ---\n"
            for i, ex in enumerate(kb_examples[:3], 1):
                few_shot += f"\nExample {i} (similarity: {ex['similarity']:.2f}):\n"
                few_shot += f"SAS:\n```sas\n{ex['sas_code']}\n```\n"
                few_shot += f"Python:\n```python\n{ex['python_code']}\n```\n"

        target_label = "PySpark" if self.target_runtime == "pyspark" else "Python (pandas)"

        prompt = f"""Convert the following SAS code to {target_label}.

Partition type: {partition.partition_type.value}
Risk level: {partition.risk_level.value}
Complexity score: {partition.complexity_score:.2f}

SAS Code:
```sas
{partition.raw_code}
```
{fm_rules}
{few_shot}

Requirements:
- Produce syntactically valid Python code
- Include all necessary import statements
- Use idiomatic {target_label} patterns
- Add brief comments for non-obvious translations
- Handle edge cases (empty DataFrames, null values)
"""
        return prompt

    @with_retry(max_retries=3, base_delay=2.0,
                agent_name="TranslationAgent-Groq")
    async def _translate_groq(self, prompt: str) -> tuple[TranslationOutput, str]:
        """Translate using Groq 70B (with rate limiting)."""
        async with groq_limiter:
            if self.groq_client:
                result = self.groq_client.chat.completions.create(
                    model="llama-3.1-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    response_model=TranslationOutput,
                    max_retries=2,
                )
                return result, "groq_70b"

        # Fallback to Ollama 70B
        result = self.ollama_client.chat.completions.create(
            model="llama3.1:70b",
            messages=[{"role": "user", "content": prompt}],
            response_model=TranslationOutput,
            max_retries=2,
        )
        return result, "ollama_70b"

    async def _translate_ollama_8b(self, prompt: str) -> TranslationOutput:
        """Translate using Ollama 8B (local, fast, for LOW risk)."""
        return self.ollama_client.chat.completions.create(
            model="llama3.1:8b",
            messages=[{"role": "user", "content": prompt}],
            response_model=TranslationOutput,
            max_retries=2,
        )

    async def _cross_verify(
        self,
        sas_code: str,
        python_code: str,
        failure_mode: Optional[object],
    ) -> Optional[CrossVerifyOutput]:
        """Cross-verify SAS↔Python equivalence using separate LLM context (Ollama 8B)."""
        fm_check = ""
        if failure_mode:
            fm_check = (
                f"\nPay special attention to the {failure_mode.value} pattern.\n"
                "Check that the known pitfall for this pattern is correctly handled."
            )

        prompt = f"""Verify if this Python code is semantically equivalent to the SAS code.

SAS:
```sas
{sas_code}
```

Python:
```python
{python_code}
```
{fm_check}

Check for: date epoch errors, merge semantics, RETAIN behavior,
FIRST./LAST. logic, missing value comparisons, PROC MEANS output structure.
"""
        try:
            return self.ollama_client.chat.completions.create(
                model="llama3.1:8b",
                messages=[{"role": "user", "content": prompt}],
                response_model=CrossVerifyOutput,
                max_retries=2,
            )
        except Exception as e:
            logger.warning("crossverify_failed", error=str(e))
            return None
```

---

## Task 4: ValidationAgent

**File**: `partition/translation/validation_agent.py`

```python
"""
ValidationAgent (#13) — L3

Post-translation validation:
1. ast.parse() — syntax check
2. exec() sandbox on synthetic 100-row DataFrame (5s timeout)
3. Routing: pass → L4, fail + retry < 2 → retranslate, fail + retry ≥ 2 → PARTIAL
"""

import ast
import uuid
import signal
import traceback
from datetime import datetime
from typing import Optional
import pandas as pd
import numpy as np
import structlog

from partition.agents.base_agent import BaseAgent
from partition.models.conversion_result import ConversionResult, ConversionStatus
from partition.utils.retry import with_retry

logger = structlog.get_logger()

VALIDATION_TIMEOUT = 5  # seconds


class ValidationResult:
    """Result of validation."""
    def __init__(self, passed: bool, syntax_ok: bool, exec_ok: bool,
                 error_msg: str = "", output: Optional[object] = None):
        self.passed = passed
        self.syntax_ok = syntax_ok
        self.exec_ok = exec_ok
        self.error_msg = error_msg
        self.output = output


class ValidationAgent(BaseAgent):
    """
    Agent #13: Post-translation validation.
    
    For test_coverage_type='full' blocks:
      - ast.parse() syntax check
      - exec() on synthetic 100-row DataFrame
    
    For test_coverage_type='structural_only':
      - ast.parse() only (no execution)
    
    Retry policy: 2 retries, namespace reset between attempts.
    """

    MAX_RETRIES = 2

    def __init__(self):
        super().__init__(agent_name="ValidationAgent")

    @with_retry(max_retries=2, base_delay=1.0,
                agent_name="ValidationAgent")
    async def validate(
        self,
        conversion: ConversionResult,
        test_coverage_type: str = "full",
    ) -> ValidationResult:
        """
        Validate a conversion result.
        
        Args:
            conversion: The ConversionResult to validate.
            test_coverage_type: 'full' or 'structural_only'.
        
        Returns:
            ValidationResult with pass/fail and diagnostics.
        """
        python_code = conversion.python_code

        # Step 1: Syntax check
        syntax_ok, syntax_error = self._check_syntax(python_code)
        if not syntax_ok:
            logger.warning("validation_syntax_fail",
                          conversion_id=str(conversion.conversion_id),
                          error=syntax_error)
            return ValidationResult(
                passed=False, syntax_ok=False, exec_ok=False,
                error_msg=f"SyntaxError: {syntax_error}"
            )

        # Step 2: Execution test (only for full coverage)
        if test_coverage_type == "structural_only":
            return ValidationResult(
                passed=True, syntax_ok=True, exec_ok=True,
                error_msg="structural_only — exec skipped"
            )

        exec_ok, exec_error, output = self._execute_with_timeout(python_code)
        if not exec_ok:
            logger.warning("validation_exec_fail",
                          conversion_id=str(conversion.conversion_id),
                          error=exec_error)
            return ValidationResult(
                passed=False, syntax_ok=True, exec_ok=False,
                error_msg=f"RuntimeError: {exec_error}"
            )

        return ValidationResult(
            passed=True, syntax_ok=True, exec_ok=True,
            output=output
        )

    def _check_syntax(self, code: str) -> tuple[bool, str]:
        """Check Python syntax via ast.parse()."""
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as e:
            return False, f"Line {e.lineno}: {e.msg}"

    def _execute_with_timeout(
        self, code: str, timeout: int = VALIDATION_TIMEOUT
    ) -> tuple[bool, str, Optional[object]]:
        """
        Execute Python code in a sandboxed namespace with timeout.
        
        Creates a synthetic 100-row DataFrame as the default input.
        """
        # Build sandbox namespace with synthetic data
        namespace = self._build_sandbox_namespace()

        try:
            # Use threading-based timeout (cross-platform)
            import threading
            result = {"ok": False, "error": "", "output": None}

            def run_code():
                try:
                    exec(code, namespace)
                    result["ok"] = True
                    # Capture any DataFrame outputs
                    for k, v in namespace.items():
                        if isinstance(v, pd.DataFrame) and not k.startswith("_"):
                            result["output"] = v
                            break
                except Exception as e:
                    result["error"] = f"{type(e).__name__}: {str(e)}"

            thread = threading.Thread(target=run_code)
            thread.start()
            thread.join(timeout=timeout)

            if thread.is_alive():
                return False, f"Timeout after {timeout}s", None

            return result["ok"], result["error"], result["output"]

        except Exception as e:
            return False, f"Sandbox error: {str(e)}", None

    def _build_sandbox_namespace(self) -> dict:
        """
        Create a sandboxed execution namespace with synthetic data.
        
        Provides:
        - A 100-row DataFrame with common column types
        - Standard library imports (pandas, numpy)
        - Restricted builtins (no file I/O, no network)
        """
        np.random.seed(42)

        # Synthetic 100-row DataFrame
        df = pd.DataFrame({
            "customer_id": range(1, 101),
            "name": [f"Customer_{i}" for i in range(1, 101)],
            "amount": np.random.uniform(10, 10000, 100).round(2),
            "quantity": np.random.randint(1, 100, 100),
            "date": pd.date_range("2020-01-01", periods=100, freq="D"),
            "category": np.random.choice(["A", "B", "C", "D"], 100),
            "region": np.random.choice(["North", "South", "East", "West"], 100),
            "score": np.random.normal(50, 15, 100).round(1),
            "is_active": np.random.choice([True, False], 100),
            "missing_col": [
                None if i % 7 == 0 else np.random.uniform(0, 100)
                for i in range(100)
            ],
        })

        # Restricted namespace
        safe_builtins = {
            k: v for k, v in __builtins__.__dict__.items()
            if k not in ("open", "exec", "eval", "__import__",
                        "compile", "globals", "locals", "breakpoint")
        } if hasattr(__builtins__, '__dict__') else {}

        namespace = {
            "__builtins__": safe_builtins,
            "pd": pd,
            "np": np,
            "pandas": pd,
            "numpy": np,
            "df": df.copy(),
            "input_df": df.copy(),
            "data": df.copy(),
            "datetime": __import__("datetime"),
        }

        return namespace
```

---

## Task 5: Translation Pipeline Integration

**File**: `partition/translation/translation_pipeline.py`

```python
"""
L3 Translation Pipeline — integrates TranslationAgent + ValidationAgent.

Routes:
  pass     → ConversionResult(status=SUCCESS) → forward to L4
  fail + retry < 2 → retranslate (enhanced prompt with error)
  fail + retry ≥ 2 → ConversionResult(status=PARTIAL) → forward to L4 with stub
"""

import asyncio
from typing import Optional
import duckdb
import structlog

from partition.models.partition_ir import PartitionIR
from partition.models.conversion_result import ConversionResult, ConversionStatus
from partition.translation.translation_agent import TranslationAgent
from partition.translation.validation_agent import ValidationAgent, ValidationResult

logger = structlog.get_logger()


class TranslationPipeline:
    """End-to-end L3 pipeline: translate → validate → retry loop."""

    MAX_VALIDATION_RETRIES = 2

    def __init__(
        self,
        target_runtime: str = "python",
        groq_api_key: Optional[str] = None,
        duckdb_path: str = "analytics.duckdb",
    ):
        self.translator = TranslationAgent(
            target_runtime=target_runtime,
            groq_api_key=groq_api_key,
        )
        self.validator = ValidationAgent()
        self.duckdb_path = duckdb_path

    async def translate_partition(
        self, partition: PartitionIR
    ) -> ConversionResult:
        """
        Full translate → validate → retry loop for one partition.
        """
        conversion = await self.translator.process(partition)

        # Skip validation for already-PARTIAL translations
        if conversion.status == ConversionStatus.PARTIAL:
            self._log_quality(conversion)
            return conversion

        # Validate
        validation = await self.validator.validate(
            conversion,
            test_coverage_type=partition.test_coverage_type,
        )

        retry_count = 0
        while not validation.passed and retry_count < self.MAX_VALIDATION_RETRIES:
            retry_count += 1
            logger.info("validation_retry",
                       partition_id=str(partition.partition_id),
                       attempt=retry_count,
                       error=validation.error_msg)

            # Retranslate with error context
            conversion = await self.translator.process(partition)
            if conversion.status == ConversionStatus.PARTIAL:
                break

            validation = await self.validator.validate(
                conversion,
                test_coverage_type=partition.test_coverage_type,
            )

        # Final status
        if not validation.passed:
            conversion.status = ConversionStatus.PARTIAL
            conversion.python_code = (
                f"# PARTIAL: Validation failed ({validation.error_msg})\n"
                + conversion.python_code
            )
        conversion.retry_count = retry_count

        self._log_quality(conversion)
        return conversion

    async def translate_batch(
        self, partitions: list[PartitionIR]
    ) -> list[ConversionResult]:
        """Translate a batch of partitions (sequential for rate limiting)."""
        results = []
        for partition in partitions:
            result = await self.translate_partition(partition)
            results.append(result)
            # Small delay for rate limiting
            await asyncio.sleep(0.1)
        return results

    def _log_quality(self, conversion: ConversionResult):
        """Log translation result to DuckDB quality_metrics."""
        try:
            con = duckdb.connect(self.duckdb_path)
            con.execute("""
                INSERT INTO conversion_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                str(conversion.conversion_id),
                str(conversion.partition_id),
                str(conversion.source_file_id),
                conversion.python_code[:10000],  # truncate for storage
                str(conversion.imports_detected),
                conversion.status.value,
                conversion.llm_confidence,
                conversion.failure_mode_flagged,
                conversion.model_used,
                str(conversion.kb_examples_used),
                conversion.retry_count,
                str(conversion.trace_id),
            ])
            con.close()
        except Exception as e:
            logger.warning("quality_log_failed", error=str(e))
```

---

## Task 6: Tests

**File**: `tests/test_translation.py`

```python
import pytest
import asyncio
from partition.translation.failure_mode_detector import (
    detect_failure_mode, FailureMode, get_failure_mode_rules,
)


class TestFailureModeDetector:
    def test_detects_retain(self):
        code = "DATA out; SET in; RETAIN running_total 0; running_total + amount; RUN;"
        assert detect_failure_mode(code) == FailureMode.RETAIN

    def test_detects_first_last(self):
        code = "DATA out; SET in; BY customer_id; IF FIRST.customer_id THEN total=0; RUN;"
        assert detect_failure_mode(code) == FailureMode.FIRST_LAST

    def test_detects_date_arithmetic(self):
        code = "DATA out; SET in; next_month = INTNX('MONTH', today(), 1); RUN;"
        assert detect_failure_mode(code) == FailureMode.DATE_ARITHMETIC

    def test_detects_merge_semantics(self):
        code = "DATA merged; MERGE a b; BY customer_id; RUN;"
        assert detect_failure_mode(code) == FailureMode.MERGE_SEMANTICS

    def test_detects_missing_value(self):
        code = "DATA out; SET in; IF NMISS(of x1-x10) > 0 THEN flag=1; RUN;"
        assert detect_failure_mode(code) == FailureMode.MISSING_VALUE_COMPARISON

    def test_detects_proc_means_output(self):
        code = "PROC MEANS DATA=sales NWAY; CLASS region; VAR amount; OUTPUT OUT=summary MEAN=avg_amt; RUN;"
        assert detect_failure_mode(code) == FailureMode.PROC_MEANS_OUTPUT

    def test_no_failure_mode(self):
        code = "DATA out; SET in; x = 1; IF x > 0 THEN y = 2; RUN;"
        assert detect_failure_mode(code) is None

    def test_rules_not_empty(self):
        for mode in FailureMode:
            rules = get_failure_mode_rules(mode)
            assert len(rules) > 0, f"No rules for {mode}"


class TestValidationAgent:
    def test_syntax_check_valid(self):
        from partition.translation.validation_agent import ValidationAgent
        agent = ValidationAgent()
        ok, err = agent._check_syntax("x = 1\ny = x + 2")
        assert ok is True
        assert err == ""

    def test_syntax_check_invalid(self):
        from partition.translation.validation_agent import ValidationAgent
        agent = ValidationAgent()
        ok, err = agent._check_syntax("def foo(\n  x = ")
        assert ok is False
        assert "SyntaxError" in err or len(err) > 0

    def test_sandbox_has_required_keys(self):
        from partition.translation.validation_agent import ValidationAgent
        agent = ValidationAgent()
        ns = agent._build_sandbox_namespace()
        assert "pd" in ns
        assert "np" in ns
        assert "df" in ns
        assert len(ns["df"]) == 100
        assert "open" not in ns.get("__builtins__", {})

    def test_exec_simple_code(self):
        from partition.translation.validation_agent import ValidationAgent
        agent = ValidationAgent()
        ok, err, output = agent._execute_with_timeout(
            "result = df['amount'].sum()"
        )
        assert ok is True
        assert err == ""

    def test_exec_timeout(self):
        from partition.translation.validation_agent import ValidationAgent
        agent = ValidationAgent()
        ok, err, output = agent._execute_with_timeout(
            "import time; time.sleep(10)", timeout=1
        )
        assert ok is False
        assert "Timeout" in err
```

---

## Checklist — End of Week 10

- [ ] `partition/translation/failure_mode_detector.py` — 6 rules implemented + tested
- [ ] `partition/translation/kb_query.py` — LanceDB retrieval with filtering
- [ ] `partition/translation/translation_agent.py` — TranslationAgent (#12), full prompt pipeline
- [ ] `partition/translation/validation_agent.py` — ValidationAgent (#13), sandbox exec
- [ ] `partition/translation/translation_pipeline.py` — Translate → Validate → Retry loop
- [ ] Failure modes: all 6 detected correctly on test SAS blocks
- [ ] KB retrieval: ≥ 3 relevant examples returned per query (filtered)
- [ ] LLM routing: LOW → 8B, MODERATE/HIGH → 70B (verified via logs)
- [ ] Cross-verify: rejections trigger retry
- [ ] Validation: ast.parse() + exec on synthetic DataFrame
- [ ] Sandbox: no file I/O, no network, 5s timeout enforced
- [ ] Pipeline: translate_batch() processes 10 partitions sequentially
- [ ] Retry policy: 3 retries for Groq, 2 for validation, then PARTIAL
- [ ] DuckDB: conversion_results logged for every translation
- [ ] Tests: 12+ assertions pass
- [ ] Git: `week-10` branch, merged to `main`

---

## Evaluation Metrics for This Week

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Failure mode precision | ≥ 0.80 | 30 test blocks with known modes |
| Failure mode recall | ≥ 0.85 | Same 30 blocks |
| Translation success rate | ≥ 0.70 | n_SUCCESS / n_total |
| Validation pass rate (full) | ≥ 0.60 | Blocks passing exec sandbox |
| CodeBLEU (gold standard) | ≥ 0.55 | Against 50 manual conversions |
| HUMAN_REVIEW rate | ≤ 0.10 | conversion_results |
| Retry rate | ≤ 0.25 | mean(retry_count) |
| KB hit coverage | ≥ 0.80 | Blocks with ≥ 1 KB example |
| Cross-verify agreement | ≥ 0.78 | vs human on 50 samples |

---

## Dependencies Added This Week

| Package | Version | Purpose |
|---------|---------|---------|
| instructor | ≥ 0.6 | Typed LLM output (already installed) |

---

## Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Groq rate limit (30 req/min) | 429 errors in logs | Rate limiter semaphore (max 5 concurrent) |
| Sandbox escape via `__import__` | Security risk | Removed from safe_builtins |
| exec() timeout on Windows | `signal.alarm` unavailable | Threading-based timeout (cross-platform) |
| KB empty for rare partition type | Zero examples retrieved | Fallback to nearest category match |
| Cross-verify always returns high confidence | No quality gate effect | Spot-check 20 pairs, tune Prompt C |
| Large SAS block exceeds context window | Truncated prompt | tiktoken guard (128K tokens for Llama 3.1) |

---

> *Week 10 Complete → You have: TranslationAgent with failure-mode-aware KB retrieval, ValidationAgent with sandbox exec, full retry/fallback loop. Next: Merge Layer (L4) + Continuous Learning (Week 11).*
