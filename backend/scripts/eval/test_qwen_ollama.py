"""test_qwen_ollama.py — Direct test of qwen3-coder-next via Ollama.

Forces Ollama as the ONLY LLM backend (skips Azure/Groq) and translates
each block from torture_test.sas. Prints status, confidence, and a code preview.

Usage:
    cd backend
    python scripts/eval/test_qwen_ollama.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

_HERE = Path(__file__).resolve().parent
BACKEND_DIR = _HERE
while not (BACKEND_DIR / "partition").exists():
    BACKEND_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv(BACKEND_DIR.parent / ".env")

import instructor
from openai import OpenAI
from pydantic import BaseModel, Field
import structlog

structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(30))  # WARNING+

# Force UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Ollama client ────────────────────────────────────────────────────────────

from partition.utils.llm_clients import get_ollama_client, get_ollama_model

GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


class TranslationOutput(BaseModel):
    python_code: str = Field(description="Translated Python/pandas code")
    explanation: str = Field(default="", description="Brief translation notes")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


# ── SAS block parser (same logic as translate_test.py) ──────────────────────

import re as _re

_SAS_CODE_RE = _re.compile(
    r"^\s*(data\s+\w|proc\s+\w|%macro\b|%let\b|%do\b|%put\b|run\s*;|quit\s*;)",
    _re.IGNORECASE | _re.MULTILINE,
)


def parse_blocks(sas_path: Path) -> list[tuple[str, str]]:
    text = sas_path.read_text(encoding="utf-8")
    blocks: list[tuple[str, str]] = []
    current_label = "block_0"
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("/* ──") and "──" in line:
            code = "\n".join(current_lines).strip()
            if code and _SAS_CODE_RE.search(code):
                blocks.append((current_label, code))
            current_label = line.strip("/* ─").strip().rstrip(" */").strip()
            current_lines = []
        else:
            current_lines.append(line)

    code = "\n".join(current_lines).strip()
    if code and _SAS_CODE_RE.search(code):
        blocks.append((current_label, code))

    return blocks


# ── Prompt ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert SAS-to-Python translator. Convert the given SAS code to idiomatic Python using pandas.
Rules:
- RETAIN → accumulate with shift/cumsum or explicit state variable
- FIRST./LAST. → groupby with head(1)/tail(1) or transform
- PROC SQL → pandas merge/groupby or SQLAlchemy
- %macro → Python function with parameters
- PROC MEANS → groupby().agg()
- Hash objects → Python dict or DataFrame merge
- Output clean, runnable Python. Add brief inline comments only where non-obvious.
"""


def build_prompt(sas_code: str) -> str:
    return f"Translate this SAS code to Python:\n\n```sas\n{sas_code}\n```"


# ── Main ─────────────────────────────────────────────────────────────────────

def translate_block(client, model: str, sas_code: str) -> TranslationOutput:
    return client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_prompt(sas_code)},
        ],
        response_model=TranslationOutput,
        max_retries=2,
    )


def run() -> None:
    sas_path = BACKEND_DIR / "tests" / "fixtures" / "torture_test.sas"
    if not sas_path.exists():
        print(f"{RED}torture_test.sas not found at {sas_path}{RESET}")
        sys.exit(1)

    raw_client = get_ollama_client(async_client=False)
    if raw_client is None:
        print(f"{RED}Ollama client unavailable — check OLLAMA_API_KEY and OLLAMA_BASE_URL in .env{RESET}")
        sys.exit(1)

    client = instructor.from_openai(raw_client)
    model  = get_ollama_model()

    blocks = parse_blocks(sas_path)

    sep = "=" * 72
    print(f"\n{CYAN}{BOLD}{sep}")
    print(f"  Codara x Ollama -- qwen3-coder-next direct test")
    print(f"  Model : {model}")
    print(f"  Base  : {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1')}")
    print(f"  Blocks: {len(blocks)}")
    print(f"{sep}{RESET}\n")

    results = []
    total_start = time.monotonic()

    for i, (label, source) in enumerate(blocks):
        print(f"[{i+1:2}/{len(blocks)}] {label[:52]:<52}", end="", flush=True)
        t0 = time.monotonic()
        try:
            out = translate_block(client, model, source)
            elapsed = time.monotonic() - t0
            status = "SUCCESS"
            colour = GREEN
        except Exception as exc:
            elapsed = time.monotonic() - t0
            status = "FAILED"
            colour = RED
            out = TranslationOutput(
                python_code=f"# ERROR: {exc}",
                explanation=str(exc),
                confidence=0.0,
            )

        print(f"{colour}{status:<8}{RESET}  conf={out.confidence:.2f}  {elapsed:.1f}s")
        results.append((label, source, out, status, elapsed))

    total_elapsed = time.monotonic() - total_start
    success = sum(1 for *_, s, _ in results if s == "SUCCESS")
    total   = len(results)

    print(f"\n{CYAN}{'─'*72}")
    print(f"  Results: {GREEN}{success}/{total} SUCCESS{RESET}  ({success/total*100:.0f}%)")
    print(f"  Total time: {total_elapsed:.1f}s  |  avg: {total_elapsed/total:.1f}s/block")
    print(f"{CYAN}{'─'*72}{RESET}")

    # Full translation printout
    print(f"\n{CYAN}{BOLD}{sep}")
    print("  TRANSLATIONS")
    print(f"{sep}{RESET}")

    for label, sas_src, out, status, elapsed in results:
        colour = GREEN if status == "SUCCESS" else RED
        print(f"\n{colour}{BOLD}+-- [{label}]  ({elapsed:.1f}s){RESET}")

        # SAS source (compact)
        print(f"{CYAN}|  SAS source:{RESET}")
        for line in sas_src.splitlines()[:8]:
            print(f"|  {line}")
        if len(sas_src.splitlines()) > 8:
            print(f"|  ... ({len(sas_src.splitlines())} lines total)")

        # Python output
        print(f"{colour}|  Python output:{RESET}")
        for line in out.python_code.splitlines():
            print(f"|  {line}")

        if out.explanation:
            print(f"{YELLOW}│  Note: {out.explanation[:120]}{RESET}")
        print(f"{'─'*72}")


if __name__ == "__main__":
    run()
