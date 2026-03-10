"""Knowledge Base Generation Pipeline — dual-LLM chain.

3-prompt chain:
    Prompt A → Generate realistic SAS code (Azure OpenAI GPT-4o)
    Prompt B → Convert to Python/PySpark with failure-mode rules (Azure OpenAI GPT-4o)
    Prompt C → Cross-verify equivalence (Groq LLaMA 70B, separate context)

Pairs with cross-verify confidence >= 0.85 → verified=True.

Azure migration (Week 9):
    Primary LLM changed from Groq to Azure OpenAI GPT-4o.
    Cross-verifier changed from Ollama to Groq (separate context window).
    Env vars: AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT,
              AZURE_OPENAI_DEPLOYMENT_FULL, GROQ_API_KEY.

Usage::

    python scripts/generate_kb_pairs.py --target-pairs 250 --runtime python
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Optional

import instructor
import structlog
from openai import AzureOpenAI, OpenAI
from pydantic import BaseModel, Field

logger = structlog.get_logger()


# ── Pydantic output models ───────────────────────────────────────────────────

class GeneratedSAS(BaseModel):
    """Output of Prompt A: a realistic SAS code block."""

    sas_code: str = Field(..., description="Realistic SAS code block")
    category: str = Field(..., description="e.g., DATA_STEP_BASIC, PROC_SQL")
    complexity_tier: str = Field(..., description="LOW | MODERATE | HIGH")
    failure_mode: str = Field(default="", description="Injected failure mode or empty")
    description: str = Field(..., description="What this SAS code does")


class ConvertedPython(BaseModel):
    """Output of Prompt B: Python/PySpark equivalent."""

    python_code: str = Field(..., description="Python/PySpark equivalent")
    target_runtime: str = Field(default="python", description="python | pyspark")
    imports_needed: list[str] = Field(default_factory=list)
    notes: str = Field(default="", description="Translation notes")


class CrossVerifyResult(BaseModel):
    """Output of Prompt C: cross-verification judgment."""

    equivalent: bool = Field(
        ..., description="Are the SAS and Python semantically equivalent?"
    )
    issues: list[str] = Field(
        default_factory=list, description="Identified issues"
    )
    confidence: float = Field(
        ..., description="Confidence in equivalence judgment (0-1)"
    )


# ── Coverage matrix (15 SAS categories) ──────────────────────────────────────

COVERAGE_MATRIX = {
    "DATA_STEP_BASIC": {
        "target": 30,
        "constructs": "assignment, if/else, keep/drop, length, format",
    },
    "DATA_STEP_MERGE": {
        "target": 25,
        "constructs": "MERGE BY, one-to-one, one-to-many, UPDATE",
        "failure_mode": "MERGE_SEMANTICS",
    },
    "DATA_STEP_RETAIN": {
        "target": 20,
        "constructs": "RETAIN, running totals, lag patterns",
        "failure_mode": "RETAIN",
    },
    "DATA_STEP_ARRAY": {
        "target": 20,
        "constructs": "ARRAY, DO over array, multi-dim arrays",
    },
    "DATA_STEP_FIRST_LAST": {
        "target": 25,
        "constructs": "BY group, FIRST.var, LAST.var",
        "failure_mode": "FIRST_LAST",
    },
    "DATE_ARITHMETIC": {
        "target": 30,
        "constructs": "MDY, TODAY, INTNX, INTCK, DATEPART",
        "failure_mode": "DATE_ARITHMETIC",
    },
    "PROC_SQL": {
        "target": 30,
        "constructs": "SELECT, JOIN, subquery, GROUP BY, HAVING",
    },
    "PROC_MEANS": {
        "target": 20,
        "constructs": "CLASS, VAR, OUTPUT OUT=, NWAY",
        "failure_mode": "PROC_MEANS_OUTPUT",
    },
    "PROC_FREQ": {
        "target": 15,
        "constructs": "TABLES, cross-tab, chi-square, WEIGHT",
    },
    "MACRO_BASIC": {
        "target": 25,
        "constructs": "%MACRO/%MEND, %LET, macro parameters",
    },
    "MACRO_CONDITIONAL": {
        "target": 20,
        "constructs": "%IF/%THEN/%ELSE, %DO/%END, nested macros",
    },
    "PROC_SORT": {
        "target": 15,
        "constructs": "BY asc/desc, NODUPKEY, NODUP",
    },
    "PROC_REG_LOGISTIC": {
        "target": 20,
        "constructs": "MODEL, output stats, selection",
    },
    "PROC_IMPORT_EXPORT": {
        "target": 15,
        "constructs": "DBMS=CSV, DBMS=XLSX, INFILE/INPUT",
    },
    "MISSING_VALUE_HANDLING": {
        "target": 20,
        "constructs": "NMISS, CMISS, missing comparisons",
        "failure_mode": "MISSING_VALUE_COMPARISON",
    },
}

# 6 failure modes × 10 targeted pairs each = 60 extra pairs
FAILURE_MODES = {
    "RETAIN": 10,
    "FIRST_LAST": 10,
    "DATE_ARITHMETIC": 10,
    "MERGE_SEMANTICS": 10,
    "MISSING_VALUE_COMPARISON": 10,
    "PROC_MEANS_OUTPUT": 10,
}


# ── Failure-mode conversion rules ────────────────────────────────────────────

_FM_RULES: dict[str, str] = {
    "DATE_ARITHMETIC": """
CRITICAL DATE RULES:
- SAS dates count from Jan 1, 1960. Python dates count from Jan 1, 1970.
- Do NOT add/subtract 3653 days — pandas handles this internally.
- Use pd.to_datetime() for date parsing.
- Use pd.DateOffset() or pd.Timedelta() for date arithmetic.
- INTNX('MONTH', date, 1) → date + pd.DateOffset(months=1)
- INTCK('DAY', date1, date2) → (date2 - date1).days
""",
    "MERGE_SEMANTICS": """
CRITICAL MERGE RULES:
- SAS MERGE with BY is NOT pd.merge() inner join.
- SAS MERGE is a sequential match (zipper), not a Cartesian product.
- Use pd.merge(how='outer') and forward-fill for SAS-like behaviour.
- Watch for many-to-many joins creating Cartesian explosions.
""",
    "RETAIN": """
CRITICAL RETAIN RULES:
- SAS RETAIN preserves a variable's value across DATA step iterations.
- In pandas, use cumsum(), expanding(), or explicit loops.
- Do NOT use df['col'].shift() as a general RETAIN replacement.
""",
    "FIRST_LAST": """
CRITICAL FIRST./LAST. RULES:
- SAS FIRST.var and LAST.var identify group boundaries after PROC SORT.
- In pandas: df['first_flag'] = df.groupby('var').cumcount() == 0
- LAST: df['last_flag'] = df.groupby('var').cumcount(ascending=False) == 0
""",
    "MISSING_VALUE_COMPARISON": """
CRITICAL MISSING VALUE RULES:
- SAS treats missing numeric as -∞ in comparisons (missing < any number).
- Python/pandas treats NaN as neither < nor > anything.
- Use pd.isna() explicitly. Do NOT rely on comparison operators with NaN.
""",
    "PROC_MEANS_OUTPUT": """
CRITICAL PROC MEANS OUTPUT RULES:
- OUTPUT OUT= creates a dataset with _TYPE_, _FREQ_, and statistic columns.
- In pandas: use df.groupby().agg() and reset_index().
- Map NWAY to the full cross-classification (no marginals).
""",
}


# ── KBGenerator ───────────────────────────────────────────────────────────────

class KBGenerator:
    """Generate verified SAS→Python KB pairs using dual-LLM chain.

    LLM allocation (Azure-first):
        Prompt A (SAS generation):        Azure OpenAI GPT-4o
        Prompt B (Python conversion):     Azure OpenAI GPT-4o
        Prompt C (cross-verification):    Groq LLaMA-3.1-70B (separate context)

    The verifier **must** be a different model/provider than the generator
    to avoid confirming its own mistakes.
    """

    VERIFY_THRESHOLD = 0.85

    def __init__(
        self,
        target_runtime: str = "python",
    ) -> None:
        self.target_runtime = target_runtime

        # ── Azure OpenAI client for generation (Prompts A + B) ──
        azure_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        azure_endpoint = os.getenv(
            "AZURE_OPENAI_ENDPOINT", "https://models.inference.ai.azure.com"
        )
        azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_FULL", "gpt-4o")

        self.generator = instructor.from_openai(
            AzureOpenAI(
                api_key=azure_key,
                azure_endpoint=azure_endpoint,
                api_version="2024-10-21",
            )
        )
        self.gen_model = azure_deployment

        # ── Groq client for cross-verification (Prompt C) ──
        groq_key = os.getenv("GROQ_API_KEY", "")
        self.verifier = instructor.from_openai(
            OpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
            )
        )
        self.verify_model = "llama-3.1-70b-versatile"

    # ── Main entry point ──────────────────────────────────────────────────

    async def generate_pair(
        self,
        category: str,
        constructs: str,
        failure_mode: str = "",
        complexity: str = "MODERATE",
    ) -> Optional[dict]:
        """Generate one verified SAS→Python pair.

        Returns:
            Dict for LanceDB insertion, or ``None`` if verification fails.
        """
        # Prompt A: Generate SAS
        sas = await self._prompt_a(category, constructs, failure_mode, complexity)
        if not sas:
            return None

        # Prompt B: Convert to Python
        python_out = await self._prompt_b(sas, failure_mode)
        if not python_out:
            return None

        # Prompt C: Cross-verify (separate LLM context)
        verify = await self._prompt_c(sas.sas_code, python_out.python_code, failure_mode)
        if not verify or verify.confidence < self.VERIFY_THRESHOLD:
            logger.info(
                "pair_rejected",
                category=category,
                confidence=verify.confidence if verify else 0,
                issues=verify.issues if verify else [],
            )
            return None

        # Embed the SAS code for vector search
        from partition.raptor.embedder import NomicEmbedder

        embedder = NomicEmbedder()
        embedding = embedder.embed(sas.sas_code)

        return {
            "example_id": str(uuid.uuid4()),
            "sas_code": sas.sas_code,
            "python_code": python_out.python_code,
            "embedding": embedding,
            "partition_type": category,
            "complexity_tier": complexity,
            "target_runtime": python_out.target_runtime,
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

    # ── Prompt A: Generate SAS ────────────────────────────────────────────

    async def _prompt_a(
        self, category: str, constructs: str, failure_mode: str, complexity: str
    ) -> Optional[GeneratedSAS]:
        fm_instruction = ""
        if failure_mode:
            fm_instruction = (
                f"\nIMPORTANT: This code MUST use the {failure_mode} pattern.\n"
                f"Include the specific SAS constructs that make this a {failure_mode} case.\n"
            )

        prompt = (
            f"Generate a realistic SAS code block for the category '{category}'.\n\n"
            f"Constructs to include: {constructs}\n"
            f"Complexity: {complexity}\n"
            f"{fm_instruction}\n"
            "Requirements:\n"
            "- Code must be syntactically valid SAS\n"
            "- Use realistic dataset and variable names (not toy examples)\n"
            "- Include comments describing what the code does\n"
            "- Length: 10-40 lines for LOW, 20-80 for MODERATE, 40-120 for HIGH\n"
        )
        try:
            return self.generator.chat.completions.create(
                model=self.gen_model,
                messages=[{"role": "user", "content": prompt}],
                response_model=GeneratedSAS,
                max_retries=2,
            )
        except Exception as exc:
            logger.warning("prompt_a_failed", error=str(exc))
            return None

    # ── Prompt B: Convert SAS → Python ────────────────────────────────────

    async def _prompt_b(
        self, sas: GeneratedSAS, failure_mode: str
    ) -> Optional[ConvertedPython]:
        fm_rules = _FM_RULES.get(failure_mode, "")
        runtime_label = (
            "PySpark" if self.target_runtime == "pyspark" else "Python (pandas)"
        )

        prompt = (
            f"Convert this SAS code to {runtime_label}.\n\n"
            f"SAS Code:\n```sas\n{sas.sas_code}\n```\n\n"
            f"Description: {sas.description}\n"
            f"Target: {self.target_runtime}\n\n"
            f"{fm_rules}\n"
            "Requirements:\n"
            "- Produce syntactically valid Python code\n"
            "- Include all necessary imports\n"
            "- Use idiomatic pandas/PySpark patterns\n"
            "- Add brief inline comments for non-obvious translations\n"
        )
        try:
            return self.generator.chat.completions.create(
                model=self.gen_model,
                messages=[{"role": "user", "content": prompt}],
                response_model=ConvertedPython,
                max_retries=2,
            )
        except Exception as exc:
            logger.warning("prompt_b_failed", error=str(exc))
            return None

    # ── Prompt C: Cross-verify ────────────────────────────────────────────

    async def _prompt_c(
        self, sas_code: str, python_code: str, failure_mode: str
    ) -> Optional[CrossVerifyResult]:
        fm_check = ""
        if failure_mode:
            fm_check = (
                f"\nPay special attention to the {failure_mode} pattern.\n"
                "Check that the known pitfall for this pattern has been "
                "correctly handled.\n"
            )

        prompt = (
            "You are a code equivalence verifier. Determine if the Python "
            "code below is semantically equivalent to the SAS code.\n\n"
            f"SAS Code:\n```sas\n{sas_code}\n```\n\n"
            f"Python Code:\n```python\n{python_code}\n```\n\n"
            f"{fm_check}\n"
            "Check for these 5 known failure modes:\n"
            "1. DATE_ARITHMETIC: SAS epoch (1960) vs Python epoch (1970)\n"
            "2. MERGE_SEMANTICS: SAS sequential merge vs pandas join\n"
            "3. RETAIN: Variable persistence across iterations\n"
            "4. FIRST_LAST: BY-group boundary detection\n"
            "5. MISSING_VALUE_COMPARISON: NaN comparison semantics\n\n"
            "Return your assessment as structured JSON.\n"
        )
        try:
            return self.verifier.chat.completions.create(
                model=self.verify_model,
                messages=[{"role": "user", "content": prompt}],
                response_model=CrossVerifyResult,
                max_retries=2,
            )
        except Exception as exc:
            logger.warning("prompt_c_failed", error=str(exc))
            return None


# ── Full KB generation ────────────────────────────────────────────────────────

async def generate_full_kb(
    target_runtime: str = "python",
    target_pairs: int = 250,
) -> tuple[list[dict], dict]:
    """Generate the full KB up to *target_pairs* verified examples.

    Returns:
        (pairs, stats) where stats has keys: generated, verified, rejected.
    """
    generator = KBGenerator(target_runtime=target_runtime)

    all_pairs: list[dict] = []
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
                failure_mode=fm if i < 5 else "",
                complexity=complexity,
            )
            stats["generated"] += 1
            if pair:
                all_pairs.append(pair)
                stats["verified"] += 1
            else:
                stats["rejected"] += 1

            # Rate limit: respect Azure 60 RPM
            if stats["generated"] % 10 == 0:
                await asyncio.sleep(2)
                logger.info("kb_progress", **stats)

    # Phase 2: Targeted failure-mode injection (60 pairs)
    for fm, count in FAILURE_MODES.items():
        cat = next(
            (k for k, v in COVERAGE_MATRIX.items() if v.get("failure_mode") == fm),
            "DATA_STEP_BASIC",
        )
        constructs = COVERAGE_MATRIX[cat]["constructs"]

        for i in range(count):
            pair = await generator.generate_pair(
                category=cat,
                constructs=constructs,
                failure_mode=fm,
                complexity="HIGH",
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


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate KB pairs")
    parser.add_argument("--target-pairs", type=int, default=250)
    parser.add_argument(
        "--runtime", choices=["python", "pyspark"], default="python"
    )
    parser.add_argument(
        "--output", default="knowledge_base/generated_pairs.json"
    )
    args = parser.parse_args()

    # Validate Azure env vars
    if not os.getenv("AZURE_OPENAI_API_KEY"):
        print("ERROR: Set AZURE_OPENAI_API_KEY environment variable")
        exit(1)
    if not os.getenv("GROQ_API_KEY"):
        print("WARNING: GROQ_API_KEY not set — cross-verification will fail")

    pairs, stats = asyncio.run(
        generate_full_kb(
            target_runtime=args.runtime,
            target_pairs=args.target_pairs,
        )
    )

    # Save to JSON for review before LanceDB insertion
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(pairs, f, indent=2, default=str)

    print(f"\nKB Generation Complete:")
    print(f"  Generated: {stats['generated']}")
    print(f"  Verified:  {stats['verified']}")
    print(f"  Rejected:  {stats['rejected']}")
    print(f"  Saved to:  {args.output}")
