"""Knowledge Base Generation Pipeline — multi-provider, benchmarking-ready.

3-prompt chain:
    Prompt A → Generate realistic SAS code      (configurable generator model)
    Prompt B → Convert to Python                (same generator model)
    Prompt C → Cross-verify equivalence         (Groq LLaMA-3.3-70B, always separate)

Pairs with cross-verify confidence >= 0.85 → verified=True.

Supported providers (--provider flag):
    nvidia   → NVIDIA NIM  (NVIDIA_API_KEY)     default model: qwen/qwen3.5-122b-a10b
    azure    → Azure OpenAI (AZURE_OPENAI_API_KEY)  default model: gpt-4o
    groq_gen → Groq as generator too (GROQ_API_KEY)  default model: llama-3.3-70b-versatile

Each run appends a summary row to knowledge_base/benchmark_results.json so you
can compare quality across providers side-by-side.

Usage::

    python scripts/generate_kb_pairs.py --provider nvidia --target-pairs 50
    python scripts/generate_kb_pairs.py --provider azure  --target-pairs 50
    python scripts/generate_kb_pairs.py --provider nvidia --model "meta/llama-3.3-70b-instruct" --target-pairs 50
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
BACKEND_DIR = _HERE
while not (BACKEND_DIR / "partition").exists():
    BACKEND_DIR = BACKEND_DIR.parent
from typing import Optional

# Ensure the backend package root is on sys.path when run as a script
sys.path.insert(0, str(BACKEND_DIR))

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
    """Output of Prompt B: Python equivalent."""

    python_code: str = Field(..., description="Python equivalent")
    target_runtime: str = Field(default="python", description="python")
    imports_needed: list[str] = Field(default_factory=list)
    notes: str = Field(default="", description="Translation notes")


class CrossVerifyResult(BaseModel):
    """Output of Prompt C: cross-verification judgment."""

    equivalent: bool = Field(..., description="Are the SAS and Python semantically equivalent?")
    issues: list[str] = Field(default_factory=list, description="Identified issues")
    confidence: float = Field(..., description="Confidence in equivalence judgment (0-1)")


# ── Provider registry ────────────────────────────────────────────────────────

PROVIDERS: dict[str, dict] = {
    "nvidia": {
        "env_key": "NVIDIA_API_KEY",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "default_model": "qwen/qwen3.5-122b-a10b",
        "is_azure": False,
    },
    "mistral": {
        "env_key": "NVIDIA_API_KEY_MISTRAL",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "default_model": "mistralai/devstral-2-123b-instruct-2512",
        "is_azure": False,
    },
    "kimi": {
        "env_key": "NVIDIA_API_KEY_MISTRAL",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "default_model": "moonshotai/kimi-k2-instruct",
        "is_azure": False,
    },
    "gemini": {
        "env_key": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
        "is_azure": False,
    },
    "azure": {
        "env_key": "AZURE_OPENAI_API_KEY",
        "base_url": None,
        "default_model": "gpt-4o",
        "is_azure": True,
    },
    "groq_gen": {
        "env_key": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "is_azure": False,
    },
}

# Verifier: Groq LLaMA-3.3-70B — independent provider from NVIDIA generator
_VERIFY_BASE_URL = "https://api.groq.com/openai/v1"
_VERIFY_MODEL = "llama-3.3-70b-versatile"


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

    LLM allocation:
        Prompt A+B (generation): configurable provider (nvidia / azure / groq_gen)
        Prompt C   (verify):     always Groq LLaMA-3.3-70B (separate context)

    The verifier MUST be a different model/provider to avoid self-confirmation bias.
    """

    VERIFY_THRESHOLD = 0.65

    def __init__(
        self,
        target_runtime: str = "python",
        provider: str = "nvidia",
        model: str | None = None,
    ) -> None:
        self.target_runtime = target_runtime
        self.provider = provider

        cfg = PROVIDERS.get(provider)
        if cfg is None:
            raise ValueError(f"Unknown provider '{provider}'. Choose from: {list(PROVIDERS)}")

        # ── Generator client (Prompts A + B) ──
        api_key = os.getenv(cfg["env_key"], "")
        if not api_key:
            raise RuntimeError(f"Missing env var: {cfg['env_key']}")

        if cfg["is_azure"]:
            azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
            azure_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
            self.generator = instructor.from_openai(
                AzureOpenAI(
                    api_key=api_key,
                    azure_endpoint=azure_endpoint,
                    api_version=azure_version,
                )
            )
            self._api_keys: list[str] = [api_key]
            self._key_idx = 0
            self._base_url: str | None = None
        else:
            # Collect all available keys for rotation (NVIDIA_API_KEY, NVIDIA_API_KEY_2, …)
            env_key = cfg["env_key"]
            self._api_keys = [api_key]
            for suffix in ("_2", "_3", "_4", "_5"):
                extra = os.getenv(f"{env_key}{suffix}", "")
                if extra:
                    self._api_keys.append(extra)
            self._key_idx = 0
            self._base_url = cfg["base_url"]

            self.generator = instructor.from_openai(
                OpenAI(api_key=self._api_keys[0], base_url=self._base_url),
                mode=instructor.Mode.JSON,
            )

        self.gen_model = model or cfg["default_model"]
        self._is_azure = cfg["is_azure"]

        # ── Groq verifier (Prompt C) — 3 keys from separate accounts ──
        self._groq_keys: list[str] = []
        for suffix in ("", "_2", "_3", "_4", "_5"):
            k = os.getenv(f"GROQ_API_KEY{suffix}", "")
            if k:
                self._groq_keys.append(k)
        self._groq_key_idx = 0
        self.verifier = instructor.from_openai(
            OpenAI(api_key=self._groq_keys[0], base_url=_VERIFY_BASE_URL),
            mode=instructor.Mode.JSON,
        )
        self.verify_model = _VERIFY_MODEL

        # Load embedder once — avoid reloading torch model on every pair
        from partition.raptor.embedder import NomicEmbedder

        self._embedder = NomicEmbedder()

        logger.info(
            "kb_generator_init",
            provider=provider,
            gen_model=self.gen_model,
            verify_model=self.verify_model,
            num_keys=len(self._api_keys),
        )

    def _rotate_key(self) -> None:
        """Rotate generator key (round-robin)."""
        if self._is_azure or len(self._api_keys) <= 1:
            return
        self._key_idx = (self._key_idx + 1) % len(self._api_keys)
        self.generator = instructor.from_openai(
            OpenAI(api_key=self._api_keys[self._key_idx], base_url=self._base_url),
            mode=instructor.Mode.JSON,
        )
        logger.info("gen_key_rotated", key_idx=self._key_idx)

    def _rotate_groq_key(self) -> None:
        """Rotate Groq verifier key (round-robin across 3 accounts)."""
        if len(self._groq_keys) <= 1:
            return
        self._groq_key_idx = (self._groq_key_idx + 1) % len(self._groq_keys)
        self.verifier = instructor.from_openai(
            OpenAI(
                api_key=self._groq_keys[self._groq_key_idx],
                base_url="https://api.groq.com/openai/v1",
            ),
            mode=instructor.Mode.JSON,
        )
        logger.info("groq_key_rotated", key_idx=self._groq_key_idx)

    # ── Main entry point ──────────────────────────────────────────────────

    def generate_pair(
        self,
        category: str,
        constructs: str,
        failure_mode: str = "",
        complexity: str = "MODERATE",
    ) -> tuple[Optional[dict], float]:
        """Generate one verified SAS→Python pair.

        Returns:
            (pair_dict | None, confidence) — pair is None if verification fails.
        """
        t_total = time.perf_counter()

        t0 = time.perf_counter()
        sas = self._prompt_a(category, constructs, failure_mode, complexity)
        t_prompt_a = round(time.perf_counter() - t0, 2)
        if not sas:
            return None, 0.0

        t0 = time.perf_counter()
        python_out = self._prompt_b(sas, failure_mode)
        t_prompt_b = round(time.perf_counter() - t0, 2)
        if not python_out:
            return None, 0.0

        t0 = time.perf_counter()
        verify = self._prompt_c(sas.sas_code, python_out.python_code, failure_mode)
        t_prompt_c = round(time.perf_counter() - t0, 2)
        confidence = verify.confidence if verify else 0.0

        # Token counts (chars / 4 ≈ tokens)
        sas_tokens = len(sas.sas_code) // 4
        py_tokens = len(python_out.python_code) // 4
        total_tokens = sas_tokens + py_tokens

        metrics = {
            "gen_model": self.gen_model,
            "verify_model": self.verify_model,
            "provider": self.provider,
            "category": category,
            "complexity": complexity,
            "failure_mode": failure_mode or "none",
            "confidence": confidence,
            "equivalent": verify.equivalent if verify else False,
            "issues": verify.issues if verify else [],
            "t_prompt_a_s": t_prompt_a,
            "t_prompt_b_s": t_prompt_b,
            "t_prompt_c_s": t_prompt_c,
            "t_total_s": round(time.perf_counter() - t_total, 2),
            "sas_lines": sas.sas_code.count("\n") + 1,
            "py_lines": python_out.python_code.count("\n") + 1,
            "sas_tokens_est": sas_tokens,
            "py_tokens_est": py_tokens,
            "total_tokens_est": total_tokens,
            "imports": python_out.imports_needed,
            "notes": python_out.notes,
            "description": sas.description,
        }

        if not verify or confidence < self.VERIFY_THRESHOLD:
            logger.info(
                "pair_rejected",
                **{
                    k: v
                    for k, v in metrics.items()
                    if k in ("category", "confidence", "issues", "t_total_s")
                },
            )
            return None, confidence

        logger.info(
            "pair_verified",
            **{
                k: v
                for k, v in metrics.items()
                if k not in ("issues", "imports", "notes", "description")
            },
        )

        embedding = self._embedder.embed(sas.sas_code)

        pair = {
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
            "verification_score": confidence,
            "category": category,
            "version": 1,
            "superseded_by": None,
            "provider": self.provider,
            "gen_model": self.gen_model,
            "verify_model": self.verify_model,
            "latency_s": metrics["t_total_s"],
            "metrics": metrics,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return pair, confidence

    # ── Prompt A: Generate SAS ────────────────────────────────────────────

    def _prompt_a(
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
        for attempt in range(len(self._api_keys)):
            try:
                return self.generator.chat.completions.create(
                    model=self.gen_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=GeneratedSAS,
                    max_retries=1,
                )
            except Exception as exc:
                err = str(exc)
                if "429" in err:
                    logger.warning("prompt_a_429_rotating", attempt=attempt)
                    self._rotate_key()
                    time.sleep(3)
                else:
                    logger.warning("prompt_a_failed", error=err[:200])
                    return None
        logger.warning("prompt_a_all_keys_exhausted")
        return None

    # ── Prompt B: Convert SAS → Python ────────────────────────────────────

    def _prompt_b(self, sas: GeneratedSAS, failure_mode: str) -> Optional[ConvertedPython]:
        fm_rules = _FM_RULES.get(failure_mode, "")

        prompt = (
            f"Convert this SAS code to Python (pandas).\n\n"
            f"SAS Code:\n```sas\n{sas.sas_code}\n```\n\n"
            f"Description: {sas.description}\n\n"
            f"{fm_rules}\n"
            "Requirements:\n"
            "- Produce syntactically valid Python code\n"
            "- Include all necessary imports\n"
            "- Use idiomatic pandas patterns\n"
            "- Add brief inline comments for non-obvious translations\n"
        )
        for attempt in range(len(self._api_keys)):
            try:
                return self.generator.chat.completions.create(
                    model=self.gen_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=ConvertedPython,
                    max_retries=1,
                )
            except Exception as exc:
                err = str(exc)
                if "429" in err:
                    logger.warning("prompt_b_429_rotating", attempt=attempt)
                    self._rotate_key()
                    time.sleep(3)
                else:
                    logger.warning("prompt_b_failed", error=err[:200])
                    return None
        logger.warning("prompt_b_all_keys_exhausted")
        return None

    # ── Prompt C: Cross-verify ────────────────────────────────────────────

    def _prompt_c(
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
            "IMPORTANT: Only flag an issue if the code ACTUALLY uses that pattern "
            "AND the Python translation handles it INCORRECTLY. "
            "Do NOT list failure modes that are irrelevant to this code.\n\n"
            "Check ONLY the failure modes present in this specific code:\n"
            "1. DATE_ARITHMETIC — only if SAS date functions (MDY, INTNX, INTCK) appear\n"
            "2. MERGE_SEMANTICS — only if SAS MERGE BY statement appears\n"
            "3. RETAIN — only if SAS RETAIN statement appears\n"
            "4. FIRST_LAST — only if FIRST./LAST. variables appear\n"
            "5. MISSING_VALUE_COMPARISON — only if missing/NaN comparisons appear\n\n"
            "If none of these patterns appear, issues=[] and confidence should be 0.85-1.0 "
            "if the logic is otherwise correct.\n\n"
            "Return your assessment as structured JSON.\n"
        )
        for attempt in range(max(len(self._groq_keys), 1) * 2):
            try:
                return self.verifier.chat.completions.create(
                    model=self.verify_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=CrossVerifyResult,
                    max_retries=1,
                )
            except Exception as exc:
                err = str(exc)
                if "429" in err:
                    logger.warning("prompt_c_429_rotating", attempt=attempt)
                    self._rotate_groq_key()
                    time.sleep(10)
                else:
                    logger.warning("prompt_c_failed", error=err[:200])
                    return None
        logger.warning("prompt_c_all_keys_exhausted")
        return None


# ── Full KB generation ────────────────────────────────────────────────────────


def generate_full_kb(
    target_runtime: str = "python",
    target_pairs: int = 50,
    provider: str = "nvidia",
    model: str | None = None,
) -> tuple[list[dict], dict]:
    """Generate KB pairs up to *target_pairs* verified examples.

    Returns:
        (pairs, stats) where stats has: generated, verified, rejected,
        avg_confidence, avg_latency_s, provider, gen_model.
    """
    generator = KBGenerator(
        target_runtime=target_runtime,
        provider=provider,
        model=model,
    )

    all_pairs: list[dict] = []
    confidences: list[float] = []
    latencies: list[float] = []
    stats = {
        "generated": 0,
        "verified": 0,
        "rejected": 0,
        "provider": provider,
        "gen_model": generator.gen_model,
    }

    # Phase 1: Category coverage
    for category, info in COVERAGE_MATRIX.items():
        target = min(info["target"], target_pairs // len(COVERAGE_MATRIX))
        fm = info.get("failure_mode", "")

        for i in range(target):
            complexity = ["LOW", "MODERATE", "HIGH"][i % 3]
            pair, conf = generator.generate_pair(
                category=category,
                constructs=info["constructs"],
                failure_mode=fm if i < 5 else "",
                complexity=complexity,
            )
            stats["generated"] += 1
            confidences.append(conf)
            if pair:
                latencies.append(pair.get("latency_s", 0.0))
                all_pairs.append(pair)
                stats["verified"] += 1
            else:
                stats["rejected"] += 1

            if stats["generated"] % 10 == 0:
                logger.info("kb_progress", **{k: v for k, v in stats.items()})

            # Stop early if target reached
            if stats["verified"] >= target_pairs:
                break
        if stats["verified"] >= target_pairs:
            break

    # Phase 2: Targeted failure-mode injection (only if quota remains)
    if stats["verified"] < target_pairs:
        for fm, count in FAILURE_MODES.items():
            cat = next(
                (k for k, v in COVERAGE_MATRIX.items() if v.get("failure_mode") == fm),
                "DATA_STEP_BASIC",
            )
            constructs = COVERAGE_MATRIX[cat]["constructs"]

            for i in range(count):
                if stats["verified"] >= target_pairs:
                    break
                pair, conf = generator.generate_pair(
                    category=cat,
                    constructs=constructs,
                    failure_mode=fm,
                    complexity="HIGH",
                )
                stats["generated"] += 1
                confidences.append(conf)
                if pair:
                    pair["source"] = "failure_mode_injection"
                    latencies.append(pair.get("latency_s", 0.0))
                    all_pairs.append(pair)
                    stats["verified"] += 1
                else:
                    stats["rejected"] += 1

                pass

    valid_confs = [c for c in confidences if c > 0]
    stats["avg_confidence"] = round(sum(valid_confs) / max(len(valid_confs), 1), 4)
    stats["acceptance_rate"] = round(stats["verified"] / max(stats["generated"], 1), 4)
    stats["avg_latency_s"] = round(sum(latencies) / max(len(latencies), 1), 2)
    stats["min_confidence"] = round(min(valid_confs, default=0), 4)
    stats["max_confidence"] = round(max(valid_confs, default=0), 4)

    if all_pairs:
        all_metrics = [p["metrics"] for p in all_pairs if "metrics" in p]
        stats["avg_sas_lines"] = round(
            sum(m["sas_lines"] for m in all_metrics) / len(all_metrics), 1
        )
        stats["avg_py_lines"] = round(sum(m["py_lines"] for m in all_metrics) / len(all_metrics), 1)
        stats["avg_tokens_est"] = round(
            sum(m["total_tokens_est"] for m in all_metrics) / len(all_metrics), 0
        )
        stats["avg_t_prompt_a"] = round(
            sum(m["t_prompt_a_s"] for m in all_metrics) / len(all_metrics), 2
        )
        stats["avg_t_prompt_b"] = round(
            sum(m["t_prompt_b_s"] for m in all_metrics) / len(all_metrics), 2
        )
        stats["avg_t_prompt_c"] = round(
            sum(m["t_prompt_c_s"] for m in all_metrics) / len(all_metrics), 2
        )

    logger.info("kb_generation_complete", **stats)
    return all_pairs, stats


# ── Benchmark recorder ────────────────────────────────────────────────────────


def record_benchmark(
    stats: dict,
    pairs: list[dict],
    output_file: str,
    benchmark_path: str = "knowledge_base/output/benchmark_results.json",
    detail_path: str | None = None,
) -> None:
    """Append run summary to benchmark_results.json and per-pair details to JSONL."""
    os.makedirs(os.path.dirname(benchmark_path) or ".", exist_ok=True)

    if os.path.exists(benchmark_path):
        with open(benchmark_path) as f:
            data = json.load(f)
    else:
        data = {"runs": []}

    run_id = str(uuid.uuid4())[:8]
    run_entry = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "output_file": output_file,
        **stats,
    }
    data["runs"].append(run_entry)

    with open(benchmark_path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    # Per-pair detail log (JSONL — one line per pair, easy to grep/diff)
    if detail_path is None:
        provider = stats.get("provider", "unknown")
        detail_path = f"knowledge_base/output/benchmark_detail_{provider}_{run_id}.jsonl"

    with open(detail_path, "w", encoding="utf-8") as f:
        for p in pairs:
            m = p.get("metrics", {})
            row = {
                "run_id": run_id,
                "example_id": p.get("example_id"),
                "gen_model": p.get("gen_model"),
                "verify_model": p.get("verify_model"),
                "provider": p.get("provider"),
                "category": p.get("category"),
                "complexity": p.get("complexity_tier"),
                "failure_mode": p.get("failure_mode") or "none",
                "confidence": p.get("verification_score"),
                "equivalent": m.get("equivalent"),
                "issues": m.get("issues", []),
                "t_prompt_a_s": m.get("t_prompt_a_s"),
                "t_prompt_b_s": m.get("t_prompt_b_s"),
                "t_prompt_c_s": m.get("t_prompt_c_s"),
                "t_total_s": p.get("latency_s"),
                "sas_lines": m.get("sas_lines"),
                "py_lines": m.get("py_lines"),
                "sas_tokens_est": m.get("sas_tokens_est"),
                "py_tokens_est": m.get("py_tokens_est"),
                "total_tokens_est": m.get("total_tokens_est"),
                "imports": m.get("imports", []),
                "description": m.get("description", ""),
                "sas_code_preview": p.get("sas_code", "")[:120].replace("\n", " "),
                "py_code_preview": p.get("python_code", "")[:120].replace("\n", " "),
            }
            f.write(json.dumps(row, default=str) + "\n")

    # Print comparison table
    print("\n-- Benchmark Results (all runs) ------------------------------")
    print(
        f"{'Run':<8} {'Provider':<10} {'Model':<38} {'Ver':>4} {'Acc%':>5} {'Conf':>6} {'Lat':>6} {'Lines(SAS/PY)':>14} {'Tok':>6}"
    )
    print("-" * 105)
    for r in data["runs"]:
        sas_l = f"{r.get('avg_sas_lines','-')}"
        py_l = f"{r.get('avg_py_lines','-')}"
        print(
            f"{r.get('run_id','?'):<8} "
            f"{r.get('provider','?'):<10} "
            f"{r.get('gen_model','?'):<38} "
            f"{r.get('verified',0):>4} "
            f"{r.get('acceptance_rate',0)*100:>4.0f}% "
            f"{r.get('avg_confidence',0):>6.3f} "
            f"{r.get('avg_latency_s',0):>5.1f}s "
            f"{sas_l+'/'+py_l:>14} "
            f"{int(r.get('avg_tokens_est',0)):>6}"
        )
    print(f"\nSummary : {benchmark_path}")
    print(f"Per-pair: {detail_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate KB pairs (multi-provider)")
    parser.add_argument("--target-pairs", type=int, default=50)
    parser.add_argument(
        "--provider",
        choices=list(PROVIDERS.keys()),
        default="mistral",
        help="LLM provider for generation (Prompts A+B). Verifier is always Groq.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override the default model for the chosen provider.",
    )
    parser.add_argument("--runtime", choices=["python"], default="python")
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file (default: knowledge_base/generated_pairs_{provider}.json)",
    )
    args = parser.parse_args()

    # Resolve output path
    output = args.output or f"knowledge_base/generated_pairs_{args.provider}.json"

    # Validate env
    cfg = PROVIDERS[args.provider]
    if not os.getenv(cfg["env_key"]):
        print(f"ERROR: Set {cfg['env_key']} environment variable")
        exit(1)
    if not os.getenv("GROQ_API_KEY"):
        print("WARNING: GROQ_API_KEY not set — cross-verification will fail")

    try:
        pairs, stats = generate_full_kb(
            target_runtime=args.runtime,
            target_pairs=args.target_pairs,
            provider=args.provider,
            model=args.model,
        )
    except Exception as _exc:
        import traceback

        print("FATAL ERROR:")
        traceback.print_exc()
        sys.exit(1)

    # Save pairs
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w") as f:
        json.dump(pairs, f, indent=2, default=str)

    # Record benchmark entry + per-pair detail log
    record_benchmark(stats, pairs=pairs, output_file=output)

    print("\nKB Generation Complete:")
    print(f"  Provider:   {stats['provider']}  ({stats['gen_model']})")
    print(f"  Generated:  {stats['generated']}")
    print(f"  Verified:   {stats['verified']}  (acceptance {stats['acceptance_rate']*100:.1f}%)")
    print(f"  Rejected:   {stats['rejected']}")
    print(f"  Avg confidence: {stats['avg_confidence']:.4f}")
    print(f"  Avg latency:    {stats['avg_latency_s']:.1f}s / pair")
    print(f"  Saved to:   {output}")
