"""Regression guard: RAPTOR retrieval quality.

Runs in CI. Fails if:
  - RAPTOR hit-rate@5 < 0.82 (overall)
  - RAPTOR advantage < 0.10 on MODERATE/HIGH tiers

Requires ablation.db to exist (run the ablation study first).
"""

from pathlib import Path

import duckdb
import pytest

ABLATION_DB = "ablation.db"


@pytest.fixture
def conn():
    if not Path(ABLATION_DB).exists():
        pytest.skip("ablation.db not found — run ablation study first")
    return duckdb.connect(ABLATION_DB, read_only=True)


def test_raptor_hit_rate_overall(conn):
    """RAPTOR hit-rate@5 must be > 0.82."""
    result = conn.execute("""
        SELECT AVG(CAST(hit_at_5 AS DOUBLE))
        FROM ablation_results
        WHERE index_type = 'raptor'
    """).fetchone()
    assert result[0] is not None, "No RAPTOR results found"
    assert result[0] > 0.82, f"RAPTOR hit-rate@5 = {result[0]:.4f}, expected > 0.82"


def test_raptor_advantage_moderate_high(conn):
    """RAPTOR advantage must be >= 10% on MODERATE/HIGH combined."""
    raptor = conn.execute("""
        SELECT AVG(CAST(hit_at_5 AS DOUBLE))
        FROM ablation_results
        WHERE index_type = 'raptor' AND complexity_tier IN ('MODERATE', 'HIGH')
    """).fetchone()

    flat = conn.execute("""
        SELECT AVG(CAST(hit_at_5 AS DOUBLE))
        FROM ablation_results
        WHERE index_type = 'flat' AND complexity_tier IN ('MODERATE', 'HIGH')
    """).fetchone()

    assert raptor[0] is not None and flat[0] is not None
    advantage = raptor[0] - flat[0]
    assert advantage >= 0.10, (
        f"RAPTOR advantage on MOD/HIGH = {advantage:.4f}, expected >= 0.10. "
        f"RAPTOR={raptor[0]:.4f}, Flat={flat[0]:.4f}"
    )


def test_ablation_query_count(conn):
    """Must have at least 500 query pairs (50 files x 10 queries x 2 indexes)."""
    result = conn.execute(
        "SELECT COUNT(*) FROM ablation_results"
    ).fetchone()
    assert result[0] >= 1000, f"Expected >= 1000 rows, got {result[0]}"
