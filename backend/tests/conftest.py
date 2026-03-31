"""Shared pytest fixtures and output-writing hooks for the Codara test suite."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ── Environment setup ────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _ROOT.parent / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH, override=False)
except ImportError:
    pass  # python-dotenv not installed — env vars must be set externally


# ── Session-scoped fixtures ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def embedder():
    """Load NomicEmbedder once per session (slow: ~7s model load)."""
    from partition.raptor.embedder import NomicEmbedder
    return NomicEmbedder(device="cpu")


@pytest.fixture(scope="session")
def lancedb_path():
    """Absolute path to the populated LanceDB knowledge base."""
    return str(_ROOT / "lancedb_data")


@pytest.fixture(scope="session")
def kb_client(lancedb_path):
    """Session-scoped KBQueryClient pointing at the real LanceDB."""
    from partition.translation.kb_query import KBQueryClient
    return KBQueryClient(db_path=lancedb_path)


@pytest.fixture(scope="session")
def real_graph(tmp_path_factory):
    """Session-scoped NetworkXGraphBuilder with pre-populated nodes and edges.

    Graph topology:
        part-1 → dep-1 → dep-2        (dependency chain)
        scc-a, scc-b, scc-c           (all share scc_id="scc-group-7")
    """
    from partition.index.graph_builder import NetworkXGraphBuilder

    tmp = tmp_path_factory.mktemp("graph")
    builder = NetworkXGraphBuilder(persist_path=str(tmp / "session_graph.gpickle"))

    # Add dependency chain nodes
    for nid, ptype, risk in [
        ("part-1", "DATA_STEP", "LOW"),
        ("dep-1", "DATA_STEP", "LOW"),
        ("dep-2", "DATA_STEP", "LOW"),
    ]:
        builder.graph.add_node(nid, partition_type=ptype, risk_level=risk, scc_id="")

    # Add edges: part-1 → dep-1 → dep-2
    builder.graph.add_edge("part-1", "dep-1", edge_type="DEPENDS_ON")
    builder.graph.add_edge("dep-1", "dep-2", edge_type="DEPENDS_ON")

    # Add SCC group nodes
    for nid in ("scc-a", "scc-b", "scc-c"):
        builder.graph.add_node(
            nid,
            partition_type="DATA_STEP",
            risk_level="LOW",
            scc_id="scc-group-7",
        )

    builder.save()
    return builder


# ── Test result collection ───────────────────────────────────────────────────

# Keyed by test file stem (e.g. "test_rag") → list of result dicts
_results_by_file: dict[str, list[dict]] = {}


def pytest_runtest_logreport(report):
    """Collect per-test results (called by pytest for setup/call/teardown)."""
    if report.when != "call":
        # Only record the actual test call, not setup/teardown
        # But also capture failures in setup/teardown for completeness
        if report.when == "setup" and report.failed:
            pass
        else:
            return

    # Derive file stem from nodeid  e.g. "tests/test_rag.py::TestFoo::test_bar"
    nodeid = report.nodeid
    parts = nodeid.split("::")
    file_part = parts[0]  # "tests/test_rag.py"
    file_name = Path(file_part).name  # "test_rag.py"
    file_stem = Path(file_part).stem  # "test_rag"

    if file_stem not in _results_by_file:
        _results_by_file[file_stem] = []

    test_name = "::".join(parts[1:]) if len(parts) > 1 else nodeid

    if report.passed:
        status = "PASS"
        detail = ""
    elif report.failed:
        status = "FAIL"
        detail = str(report.longrepr) if report.longrepr else ""
    elif report.skipped:
        status = "SKIP"
        detail = str(report.longrepr) if report.longrepr else ""
    else:
        status = "UNKNOWN"
        detail = ""

    _results_by_file[file_stem].append(
        {
            "test_name": test_name,
            "file_name": file_name,
            "status": status,
            "detail": detail,
        }
    )


def pytest_sessionfinish(session, exitstatus):
    """Write per-file result summaries to tests/output/<file_stem>.txt."""
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_at = datetime.now(timezone.utc).isoformat()

    for file_stem, results in _results_by_file.items():
        file_name = f"{file_stem}.py"
        total = len(results)
        passed = sum(1 for r in results if r["status"] == "PASS")
        failed = sum(1 for r in results if r["status"] == "FAIL")
        skipped = sum(1 for r in results if r["status"] == "SKIP")

        lines = [
            f"Test file: {file_name}",
            f"Run at: {run_at}",
            f"Total: {total} | Pass: {passed} | Fail: {failed} | Skip: {skipped}",
            "=" * 60,
            "",
        ]

        for r in results:
            prefix = f"[{r['status']}]"
            lines.append(f"{prefix} {r['test_name']}")
            if r["detail"] and r["status"] in ("FAIL", "SKIP"):
                # Indent the detail block
                for detail_line in r["detail"].splitlines()[:20]:
                    lines.append(f"    {detail_line}")
                lines.append("")

        out_path = output_dir / f"{file_stem}.txt"
        out_path.write_text("\n".join(lines), encoding="utf-8")
