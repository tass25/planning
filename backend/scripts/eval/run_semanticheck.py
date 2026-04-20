"""Run SemantiCheck on the torture_test.sas translations.

Loads the torture test SAS blocks and their translations from the last
translate_test run, then computes a full SemantiCheck Score (SCS) for each.

Usage:
    cd backend
    python scripts/eval/run_semanticheck.py
"""

from __future__ import annotations

import sys
import os
import asyncio
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))
os.chdir(Path(__file__).parent.parent.parent)

from dotenv import load_dotenv
load_dotenv()

import structlog
structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(30))  # WARNING+

from partition.verification.semanticheck import semanticheck, SemantiCheckResult
from partition.utils.llm_clients import get_ollama_client, get_ollama_model, get_azure_openai_client, get_deployment_name

# ── Load torture test blocks ─────────────────────────────────────────────────

_ROOT = Path(__file__).parent.parent.parent.parent  # Stage/
TORTURE_SAS = _ROOT / "backend" / "tests" / "fixtures" / "torture_test.sas"
TRANSLATE_OUTPUT = _ROOT / "backend" / "output" / "translate_test"
os.chdir(_ROOT)

BLOCK_DESCRIPTIONS = [
    "RETAIN + BY-group FIRST./LAST.",
    "Missing value logic (SAS . < any number)",
    "PROC SQL with correlated subquery",
    "Macro with parameters + %DO loop",
    "PROC MEANS with CLASS and OUTPUT",
    "PROC SORT NODUPKEY",
    "Hash object for lookup",
    "Multi-level nested macro",
    "PROC TRANSPOSE",
    "Complex WHERE + FORMAT + LABEL",
]


def _load_sas_blocks(path: Path) -> list[str]:
    """Split torture_test.sas into its 10 blocks by /* --- */ separators."""
    text = path.read_text(encoding="utf-8")
    # Blocks are separated by /* ── block N ── */ style comments
    parts = re.split(r"/\*\s*[─=\-]{3,}.*?[─=\-]{3,}\s*\*/", text, flags=re.DOTALL)
    blocks = [p.strip() for p in parts if p.strip()]
    return blocks[:10]


def _load_python_translations(output_dir: Path) -> list[str]:
    """Load translated Python blocks from translate_test output directory."""
    # translate_test writes torture_test_all.py with all blocks concatenated
    all_py = output_dir / "torture_test_all.py"
    if all_py.exists():
        text = all_py.read_text(encoding="utf-8")
        # Split by block separator comments
        parts = re.split(r"# ={10,}.*?={10,}\n", text, flags=re.DOTALL)
        blocks = [p.strip() for p in parts if p.strip() and not p.strip().startswith("#")]
        if len(blocks) >= 10:
            return blocks[:10]

    # Fallback: load individual block files if they exist
    blocks = []
    for i in range(1, 11):
        f = output_dir / f"block_{i:02d}.py"
        if f.exists():
            blocks.append(f.read_text(encoding="utf-8"))
    return blocks


def _get_llm_client():
    """Return the best available raw LLM client for oracle calls."""
    try:
        client = get_ollama_client(async_client=False)
        if client:
            return client, get_ollama_model()
    except Exception:
        pass
    try:
        client = get_azure_openai_client(async_client=False)
        if client:
            return client, get_deployment_name("mini")
    except Exception:
        pass
    return None, ""


async def run():
    import re

    print("\n" + "=" * 70)
    print("  SemantiCheck — Semantic Equivalence Verification")
    print("  torture_test.sas — 10 blocks")
    print("=" * 70 + "\n")

    # Load SAS blocks
    if not TORTURE_SAS.exists():
        print(f"ERROR: {TORTURE_SAS} not found")
        sys.exit(1)

    sas_text = TORTURE_SAS.read_text(encoding="utf-8")
    # Split on block separator comments: /* ── N. Description ── */
    raw_blocks = re.split(r"/\*\s*[─\-=]{2,}.*?[─\-=]{2,}\s*\*/", sas_text, flags=re.DOTALL)
    sas_blocks = [b.strip() for b in raw_blocks if b.strip()][:10]

    if len(sas_blocks) < 10:
        # Fallback: try splitting on /* block */ style
        raw_blocks = re.split(r"/\*.*?\*/", sas_text, flags=re.DOTALL)
        sas_blocks = [b.strip() for b in raw_blocks if b.strip() and len(b.strip()) > 20][:10]

    # Load Python translations
    if not TRANSLATE_OUTPUT.exists():
        print(f"ERROR: {TRANSLATE_OUTPUT} not found. Run translate_test.py first.")
        sys.exit(1)

    all_py_file = TRANSLATE_OUTPUT / "torture_test_all.py"
    if all_py_file.exists():
        py_text = all_py_file.read_text(encoding="utf-8")
        # Each block is separated by a comment header
        py_blocks_raw = re.split(r"# (?:Block|block|\d+\.)[^\n]*\n", py_text)
        py_blocks = [b.strip() for b in py_blocks_raw if b.strip() and len(b.strip()) > 10][:10]
    else:
        # Try numbered files
        py_blocks = []
        for f in sorted(TRANSLATE_OUTPUT.glob("*.py"))[:10]:
            py_blocks.append(f.read_text(encoding="utf-8"))

    if not py_blocks:
        print(f"ERROR: No Python translation files found in {TRANSLATE_OUTPUT}")
        print("Run translate_test.py first to generate translations.")
        sys.exit(1)

    # Pad if we have fewer than 10
    while len(sas_blocks) < 10:
        sas_blocks.append("")
    while len(py_blocks) < 10:
        py_blocks.append("# PARTIAL")

    # Get LLM client for oracle
    llm_client, llm_model = _get_llm_client()
    if llm_client:
        print(f"  Oracle LLM: {llm_model}")
    else:
        print("  Oracle LLM: unavailable (L4 will be skipped)")
    print()

    results: list[SemantiCheckResult] = []
    total = min(len(sas_blocks), len(py_blocks), 10)

    for i in range(total):
        desc = BLOCK_DESCRIPTIONS[i] if i < len(BLOCK_DESCRIPTIONS) else f"Block {i+1}"
        sas  = sas_blocks[i]
        py   = py_blocks[i]

        is_partial = py.strip().startswith("# PARTIAL")

        result = await semanticheck(
            sas_code=sas,
            python_code=py,
            z3_score=None,    # would come from z3_agent in full pipeline
            cdais_score=None, # would come from CDAIS in full pipeline
            llm_client=llm_client,
            llm_model=llm_model,
        )
        results.append(result)

        verdict_color = {
            "VERIFIED":         "\033[32m",  # green
            "LIKELY_CORRECT":   "\033[32m",
            "UNCERTAIN":        "\033[33m",  # yellow
            "LIKELY_INCORRECT": "\033[31m",  # red
        }.get(result.verdict, "")
        reset = "\033[0m"

        filled = int(result.scs * 20)
        scs_bar = "#" * filled + "-" * (20 - filled)

        print(f"[{i+1:2d}/10] {desc[:50]:<50}")
        print(f"       SCS: {result.scs:.3f}  [{scs_bar}]  "
              f"{verdict_color}{result.verdict}{reset}")
        print(f"       L3(contract)={result.contract_score:.2f}  "
              f"L4(oracle)={'N/A' if result.oracle_score is None else f'{result.oracle_score:.2f}'}"
              + (" ⚠ PARTIAL" if is_partial else ""))
        print()

    # Summary
    print("=" * 70)
    print("  SemantiCheck Summary")
    print("=" * 70)
    avg_scs = sum(r.scs for r in results) / len(results) if results else 0
    verified = sum(1 for r in results if r.verdict in ("VERIFIED", "LIKELY_CORRECT"))
    uncertain = sum(1 for r in results if r.verdict == "UNCERTAIN")
    likely_wrong = sum(1 for r in results if r.verdict == "LIKELY_INCORRECT")

    print(f"  Avg SemantiCheck Score : {avg_scs:.3f}")
    print(f"  VERIFIED/LIKELY_CORRECT: {verified}/10")
    print(f"  UNCERTAIN              : {uncertain}/10")
    print(f"  LIKELY_INCORRECT       : {likely_wrong}/10")
    print()
    print(f"  Avg L3 (Contract)      : {sum(r.contract_score or 0 for r in results)/len(results):.3f}")
    oracle_scores = [r.oracle_score for r in results if r.oracle_score is not None]
    if oracle_scores:
        print(f"  Avg L4 (Oracle)        : {sum(oracle_scores)/len(oracle_scores):.3f}")
    print("=" * 70)

    # Save JSON report
    report = {
        "summary": {
            "avg_scs": round(avg_scs, 3),
            "verified_or_likely_correct": verified,
            "uncertain": uncertain,
            "likely_incorrect": likely_wrong,
            "avg_contract": round(sum(r.contract_score or 0 for r in results) / len(results), 3),
        },
        "blocks": [
            {
                "block": i + 1,
                "description": BLOCK_DESCRIPTIONS[i] if i < len(BLOCK_DESCRIPTIONS) else f"Block {i+1}",
                **r.to_dict(),
            }
            for i, r in enumerate(results)
        ],
    }
    out_path = TRANSLATE_OUTPUT / "semanticheck_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Report saved -> {out_path}")


if __name__ == "__main__":
    asyncio.run(run())
