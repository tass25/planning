"""Fine-tuning dataset builder — Week 15.

Collects SAS→Python pairs from multiple free sources and produces
a deduplicated JSONL file ready for QLoRA SFT training.

Sources (all free):
  1. Internal gold standard (45 files already in repo)
  2. Existing KB pairs from LanceDB (330 entries)
  3. Teacher LLM distillation using Gemini 2.0 Flash (free 1M TPM/day)
  4. The Stack v2 via HuggingFace datasets (SAS files, no API key)

Usage:
    cd backend
    python scripts/kb/build_dataset.py --output data/sft_train.jsonl --target 1000
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Iterator

# Auto-discover backend/ (works regardless of how deep this script is nested)
_HERE = Path(__file__).resolve().parent
BACKEND_DIR = _HERE
while not (BACKEND_DIR / "partition").exists():
    BACKEND_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND_DIR.parent / ".env")

import structlog

logger = structlog.get_logger(__name__)

# ── Prompt format (Alpaca-style with SAS context) ────────────────────
SYSTEM_PROMPT = (
    "You are an expert SAS-to-Python migration engineer. "
    "Convert the given SAS code to clean, idiomatic Python. "
    "Preserve all semantics exactly: variable naming, missing value handling, "
    "BY-group processing, RETAIN behaviour, and PROC equivalents."
)

def to_training_example(sas_code: str, python_code: str, category: str = "") -> dict:
    """Format a pair into the Alpaca training format expected by unsloth."""
    return {
        "instruction": SYSTEM_PROMPT,
        "input": f"Convert this SAS code to Python:\n\n```sas\n{sas_code.strip()}\n```",
        "output": f"```python\n{python_code.strip()}\n```",
        "category": category,
        "source": "codara_dataset",
    }


# ── Source 1: internal gold standard ────────────────────────────────
def load_gold_standard(gold_dir: Path) -> Iterator[dict]:
    """Load .gold.json pairs from the gold standard corpus."""
    for gold_file in sorted(gold_dir.glob("*.gold.json")):
        sas_file = gold_dir / gold_file.name.replace(".gold.json", ".sas")
        if not sas_file.exists():
            continue
        try:
            gold = json.loads(gold_file.read_text(encoding="utf-8"))
            sas_code = sas_file.read_text(encoding="utf-8")
            python_code = gold.get("python_translation", "")
            if sas_code.strip() and python_code.strip():
                yield to_training_example(sas_code, python_code, gold.get("category", "gold_standard"))
        except Exception as exc:
            logger.warning("gold_standard_load_error", file=str(gold_file), error=str(exc))


# ── Source 2: existing LanceDB KB ────────────────────────────────────
def load_lancedb_pairs(lancedb_path: str) -> Iterator[dict]:
    """Load verified pairs from the LanceDB knowledge base."""
    try:
        import lancedb
        db = lancedb.connect(lancedb_path)
        table = db.open_table("sas_python_examples")
        df = table.to_pandas()
        verified = df[df["verified"] == True]  # noqa: E712
        for _, row in verified.iterrows():
            if row.get("sas_snippet") and row.get("python_translation"):
                yield to_training_example(
                    row["sas_snippet"],
                    row["python_translation"],
                    row.get("category", "kb_pair"),
                )
    except Exception as exc:
        logger.warning("lancedb_load_error", error=str(exc))


# ── Source 3: Gemini distillation ────────────────────────────────────
async def distill_with_gemini(
    sas_snippets: list[str],
    batch_size: int = 10,
) -> Iterator[dict]:
    """Use Gemini 2.0 Flash as teacher to translate SAS snippets."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("gemini_distill_skipped", reason="GEMINI_API_KEY not set")
        return

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
    except ImportError:
        logger.warning("gemini_distill_skipped", reason="google-generativeai not installed")
        return

    for i in range(0, len(sas_snippets), batch_size):
        batch = sas_snippets[i : i + batch_size]
        for sas_code in batch:
            try:
                prompt = f"""{SYSTEM_PROMPT}

SAS code to convert:
```sas
{sas_code}
```

Respond with ONLY the Python code, no explanation, wrapped in ```python ... ```."""
                response = await asyncio.to_thread(model.generate_content, prompt)
                python_code = _extract_code_block(response.text, "python")
                if python_code:
                    yield to_training_example(sas_code, python_code, "gemini_distilled")
                    logger.info("gemini_distill_success", chars=len(sas_code))
            except Exception as exc:
                logger.warning("gemini_distill_error", error=str(exc))
            await asyncio.sleep(0.1)  # stay within free rate limit


def _extract_code_block(text: str, lang: str) -> str:
    """Extract code from a markdown fenced block."""
    pattern = rf"```{lang}\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


# ── Source 4: The Stack v2 (HuggingFace, no API key needed) ─────────
def load_the_stack(max_samples: int = 300) -> Iterator[dict]:
    """Stream SAS files from The Stack v2 and distill them locally.

    Note: This only downloads SAS source files — translation happens
    via Gemini in the distillation step above.  Returns raw SAS snippets.
    """
    try:
        from datasets import load_dataset  # type: ignore[import]
        ds = load_dataset(
            "bigcode/the-stack-v2-train-smol-ids",
            data_files={"train": "data/sas/*.parquet"},
            split="train",
            streaming=True,
            trust_remote_code=True,
        )
        for i, row in enumerate(ds):
            if i >= max_samples:
                break
            content = row.get("content", "")
            if content and len(content) > 50:
                yield content  # raw SAS code for distillation
    except Exception as exc:
        logger.warning("thestack_load_error", error=str(exc))


# ── MinHash LSH deduplication ────────────────────────────────────────
def deduplicate(examples: list[dict], threshold: float = 0.8) -> list[dict]:
    """Remove near-duplicate pairs using MinHash LSH."""
    try:
        from datasketch import MinHash, MinHashLSH  # type: ignore[import]

        lsh = MinHashLSH(threshold=threshold, num_perm=128)
        unique = []

        for i, ex in enumerate(examples):
            text = ex["input"] + ex["output"]
            tokens = set(text.lower().split())
            mh = MinHash(num_perm=128)
            for token in tokens:
                mh.update(token.encode("utf-8"))

            key = f"ex_{i}"
            if not lsh.query(mh):
                lsh.insert(key, mh)
                unique.append(ex)

        removed = len(examples) - len(unique)
        logger.info("dedup_complete", original=len(examples), unique=len(unique), removed=removed)
        return unique

    except ImportError:
        logger.warning("dedup_skipped", reason="datasketch not installed")
        return examples


# ── DPO pairs from corrections table ────────────────────────────────
def load_dpo_pairs(db_path: str) -> list[dict]:
    """Build DPO preference pairs from human corrections in SQLite."""
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT c.conversion_id, c.corrected_code, c.explanation,
                   cv.sas_code AS original_sas, cv.python_code AS bad_translation
            FROM corrections c
            JOIN conversions cv ON c.conversion_id = cv.id
            WHERE c.corrected_code IS NOT NULL
              AND cv.sas_code IS NOT NULL
              AND cv.python_code IS NOT NULL
        """).fetchall()
        conn.close()

        pairs = []
        for _, corrected, _, sas_code, bad_translation in rows:
            if sas_code and corrected and bad_translation:
                pairs.append({
                    "prompt": f"Convert this SAS code to Python:\n\n```sas\n{sas_code.strip()}\n```",
                    "chosen": f"```python\n{corrected.strip()}\n```",
                    "rejected": f"```python\n{bad_translation.strip()}\n```",
                })
        logger.info("dpo_pairs_loaded", count=len(pairs))
        return pairs
    except Exception as exc:
        logger.warning("dpo_pairs_error", error=str(exc))
        return []


# ── Main ──────────────────────────────────────────────────────────────
async def main(args: argparse.Namespace) -> None:
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_examples: list[dict] = []

    # Source 1 & 2 (fast, local)
    gold_dir = BACKEND_DIR / "knowledge_base" / "gold_standard"
    if gold_dir.exists():
        gold = list(load_gold_standard(gold_dir))
        logger.info("loaded_gold_standard", count=len(gold))
        all_examples.extend(gold)

    kb_pairs = list(load_lancedb_pairs(os.getenv("LANCEDB_PATH", "data/lancedb")))
    logger.info("loaded_kb_pairs", count=len(kb_pairs))
    all_examples.extend(kb_pairs)

    # Source 4: The Stack SAS snippets → distill with Gemini
    if len(all_examples) < args.target:
        needed = args.target - len(all_examples)
        logger.info("fetching_thestack", needed=needed)
        raw_sas = list(load_the_stack(max_samples=needed * 2))

        if raw_sas and os.getenv("GEMINI_API_KEY"):
            distilled = []
            async for ex in distill_with_gemini(raw_sas[:needed]):
                distilled.append(ex)
                if len(distilled) % 50 == 0:
                    logger.info("distillation_progress", done=len(distilled))
            logger.info("distilled_from_thestack", count=len(distilled))
            all_examples.extend(distilled)

    # Dedup
    all_examples = deduplicate(all_examples, threshold=0.8)

    # Split train / val (90/10)
    val_size = max(50, len(all_examples) // 10)
    val_examples = all_examples[-val_size:]
    train_examples = all_examples[:-val_size]

    # Write SFT JSONL
    with output_path.open("w", encoding="utf-8") as f:
        for ex in train_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    val_path = output_path.parent / "sft_val.jsonl"
    with val_path.open("w", encoding="utf-8") as f:
        for ex in val_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    logger.info(
        "dataset_complete",
        train=len(train_examples),
        val=len(val_examples),
        output=str(output_path),
    )
    print(f"\nDataset ready:")
    print(f"  Train: {len(train_examples)} examples → {output_path}")
    print(f"  Val:   {len(val_examples)} examples → {val_path}")

    # DPO pairs
    dpo_pairs = load_dpo_pairs(os.getenv("SQLITE_PATH", "data/codara_api.db"))
    if dpo_pairs:
        dpo_path = output_path.parent / "dpo_train.jsonl"
        with dpo_path.open("w", encoding="utf-8") as f:
            for p in dpo_pairs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        print(f"  DPO:   {len(dpo_pairs)} preference pairs → {dpo_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build fine-tuning dataset")
    parser.add_argument("--output", default="data/sft_train.jsonl")
    parser.add_argument("--target", type=int, default=1000,
                        help="Target number of training pairs")
    asyncio.run(main(parser.parse_args()))
