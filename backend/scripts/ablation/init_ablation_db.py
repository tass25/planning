"""Initialize the ablation_results DuckDB table.

Safety net — should already exist from AblationRunner, but ensures
the schema is present before running analysis scripts.
"""

import argparse

import duckdb


def init_ablation_schema(db_path: str = "ablation.db") -> None:
    conn = duckdb.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ablation_results (
            run_id           VARCHAR,
            file_id          VARCHAR,
            query_id         VARCHAR,
            index_type       VARCHAR,
            hit_at_5         BOOLEAN,
            reciprocal_rank  DOUBLE,
            query_latency_ms DOUBLE,
            complexity_tier  VARCHAR,
            depth_level      INTEGER,
            created_at       VARCHAR
        )
    """)
    print(f"ablation_results table ready in {db_path}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="ablation.db")
    args = parser.parse_args()
    init_ablation_schema(args.db)
