"""verify_deliverables.py — check all required project files exist.

Run from the project root:
    cd backend && python scripts/verify_deliverables.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
BACKEND_DIR = _HERE
while not (BACKEND_DIR / "partition").exists():
    BACKEND_DIR = BACKEND_DIR.parent

# Auto-discover backend/ regardless of nesting depth
BACKEND = BACKEND_DIR  # set by auto-discovery above
ROOT = BACKEND.parent
FRONTEND = ROOT / "frontend"

REQUIRED: list[tuple[str, Path]] = [
    # ── Pipeline core ────────────────────────────────────────────────────
    ("Orchestrator",            BACKEND / "partition/orchestration/orchestrator.py"),
    ("StateAgent (FSM)",        BACKEND / "partition/streaming/state_agent.py"),
    ("BoundaryDetector",        BACKEND / "partition/chunking/boundary_detector.py"),
    ("RAPTORAgent",             BACKEND / "partition/raptor/raptor_agent.py"),
    ("RiskRouter",              BACKEND / "partition/complexity/risk_router.py"),
    ("TranslationPipeline",     BACKEND / "partition/translation/translation_pipeline.py"),
    ("MergeAgent",              BACKEND / "partition/merge/merge_agent.py"),
    # ── RAG ──────────────────────────────────────────────────────────────
    ("RAGRouter",               BACKEND / "partition/rag/router.py"),
    ("StaticRAG",               BACKEND / "partition/rag/static_rag.py"),
    ("GraphRAG",                BACKEND / "partition/rag/graph_rag.py"),
    ("AgenticRAG",              BACKEND / "partition/rag/agentic_rag.py"),
    # ── Prompts ──────────────────────────────────────────────────────────
    ("Prompt: translation_static",  BACKEND / "partition/prompts/templates/translation_static.j2"),
    ("Prompt: translation_agentic", BACKEND / "partition/prompts/templates/translation_agentic.j2"),
    ("Prompt: translation_graph",   BACKEND / "partition/prompts/templates/translation_graph.j2"),
    ("Prompt: cross_verify",        BACKEND / "partition/prompts/templates/cross_verify.j2"),
    ("Prompt: reflection",          BACKEND / "partition/prompts/templates/reflection.j2"),
    # ── API ──────────────────────────────────────────────────────────────
    ("FastAPI main",            BACKEND / "api/main.py"),
    ("DB models",               BACKEND / "api/database.py"),
    ("Auth",                    BACKEND / "api/auth.py"),
    ("Conversions route",       BACKEND / "api/routes/conversions.py"),
    # ── Data ─────────────────────────────────────────────────────────────
    ("Gold standard dir",       BACKEND / "knowledge_base/gold_standard"),
    ("Requirements",            BACKEND / "requirements/base.txt"),
    # ── Tests ────────────────────────────────────────────────────────────
    ("Test suite",              BACKEND / "tests"),
    ("Benchmark script",        BACKEND / "benchmark/boundary_benchmark.py"),
    # ── Frontend ─────────────────────────────────────────────────────────
    ("Frontend Workspace",      FRONTEND / "src/pages/Workspace.tsx"),
    ("Frontend types",          FRONTEND / "src/types/index.ts"),
    ("Frontend api.ts",         FRONTEND / "src/lib/api.ts"),
    # ── Infrastructure ───────────────────────────────────────────────────
    ("Docker Compose",          ROOT / "infra/docker-compose.yml"),
    ("Dockerfile",              ROOT / "infra/Dockerfile"),
    ("CI workflow",             ROOT / ".github/workflows/ci.yml"),
    ("CLAUDE.md",               ROOT / "CLAUDE.md"),
    ("README.md",               ROOT / "README.md"),
    # ── Docs ─────────────────────────────────────────────────────────────
    ("Audit report v3",         ROOT / "docs/reports/AUDIT_REPORT_V3.md"),
    ("Changelog 28mars",        ROOT / "docs/planning/28mars.md"),
]

OPTIONAL: list[tuple[str, Path]] = [
    ("LanceDB data dir",        BACKEND / "data/lancedb"),
    ("Ablation DB",             BACKEND / "data/ablation.db"),
    ("Ablation analyzer",       BACKEND / "scripts/analyze_ablation.py"),
    ("Complexity training CSV", BACKEND / "benchmark/complexity_training.csv"),
]


def _check(items: list[tuple[str, Path]], required: bool) -> int:
    label = "REQUIRED" if required else "OPTIONAL"
    failures = 0
    for name, path in items:
        exists = path.exists()
        status = "OK" if exists else ("MISSING" if required else "N/A")
        print(f"  [{status}] {name:<40} {path.relative_to(ROOT)}")
        if required and not exists:
            failures += 1
    return failures


def main() -> None:
    print(f"\n{'='*60}")
    print("  Codara Deliverables Verification")
    print(f"  Root: {ROOT}")
    print(f"{'='*60}\n")

    print("REQUIRED FILES:")
    failures = _check(REQUIRED, required=True)

    print("\nOPTIONAL / RUNTIME FILES:")
    _check(OPTIONAL, required=False)

    # Gold standard block count
    gs_dir = BACKEND / "knowledge_base/gold_standard"
    if gs_dir.exists():
        sas_count = len(list(gs_dir.glob("*.sas")))
        gold_count = len(list(gs_dir.glob("*.gold.json")))
        print(f"\nGold standard corpus: {sas_count} .sas files, {gold_count} .gold.json files")

    print(f"\n{'='*60}")
    if failures == 0:
        print("  [PASS] ALL REQUIRED DELIVERABLES PRESENT")
    else:
        print(f"  [FAIL] {failures} REQUIRED FILE(S) MISSING")
    print(f"{'='*60}\n")
    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()
