"""
view_db.py — Interactive database viewer for Codara.

Usage (from backend/):
    venv/Scripts/python scripts/ops/view_db.py              # show all
    venv/Scripts/python scripts/ops/view_db.py lance        # LanceDB only
    venv/Scripts/python scripts/ops/view_db.py duck         # DuckDB only
    venv/Scripts/python scripts/ops/view_db.py sqlite       # SQLite only
    venv/Scripts/python scripts/ops/view_db.py lance search "IF balance < 0"
"""

from __future__ import annotations

import sys
import os

# ensure backend/ is on sys.path so partition.* imports work from anywhere
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# ── paths (resolved relative to this file: backend/scripts/ops/view_db.py) ──
_HERE        = os.path.dirname(os.path.abspath(__file__))          # .../backend/scripts/ops
_BACKEND     = os.path.abspath(os.path.join(_HERE, "..", ".."))    # .../backend
_DATA        = os.path.join(_BACKEND, "data")

LANCEDB_PATH  = os.path.join(_DATA, "lancedb")
DUCKDB_PATH   = os.path.join(_DATA, "analytics.duckdb")
SQLITE_PATH   = os.path.join(_DATA, "codara_api.db")

SEP  = "=" * 72
SEP2 = "-" * 72

def _hdr(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


# ── LanceDB ──────────────────────────────────────────────────────────────────

def show_lancedb(search_query: str = ""):
    _hdr("LanceDB  —  Vector KB  (data/lancedb)")
    try:
        import lancedb
        import pandas as pd

        if not os.path.exists(LANCEDB_PATH):
            print("  [!] data/lancedb not found. Run: venv/Scripts/python scripts/kb/seed_kb.py --clear")
            return

        db = lancedb.connect(LANCEDB_PATH)
        tables_result = db.list_tables()
        tables = tables_result.tables if hasattr(tables_result, "tables") else list(tables_result)
        print(f"  Tables : {tables}")

        if not tables:
            print("  [!] No tables yet. Run seed_kb.py --clear to populate.")
            return

        t  = db.open_table(tables[0])
        df = t.to_pandas()

        print(f"  Rows   : {len(df)}")
        print(f"  Cols   : {list(df.columns)}\n")

        # Coverage by category
        print("  Coverage by category:")
        print(SEP2)
        cov = df["category"].value_counts()
        for cat, n in cov.items():
            print(f"    {cat:<35} {n} pair(s)")

        # Coverage by partition_type
        print(f"\n  Coverage by partition_type:")
        print(SEP2)
        for pt, n in df["partition_type"].value_counts().items():
            print(f"    {pt:<35} {n}")

        # Verified stats
        if "verified" in df.columns:
            n_verified = df["verified"].sum()
            print(f"\n  Verified: {n_verified}/{len(df)}")

        # Similarity score range
        if "similarity_score" in df.columns:
            s = df["similarity_score"].dropna()
            if len(s):
                print(f"  Similarity score: min={s.min():.3f}  max={s.max():.3f}  mean={s.mean():.3f}")

        # Semantic search
        if search_query:
            print(f"\n  Semantic search: '{search_query}'")
            print(SEP2)
            try:
                from partition.raptor.embedder import NomicEmbedder
                emb = NomicEmbedder()
                vec = emb.embed_query(search_query).tolist()
                results = t.search(vec).limit(5).to_pandas()
                for i, row in results.iterrows():
                    print(f"\n  [{i+1}] category={row.get('category','')}  partition_type={row.get('partition_type','')}")
                    print(f"       SAS  : {str(row.get('sas_code',''))[:120].strip()}")
                    print(f"       Python: {str(row.get('python_code',''))[:120].strip()}")
            except Exception as e:
                print(f"  [!] Search failed: {e}")

        # First 5 rows — key columns
        print(f"\n  First 5 rows (key columns):")
        print(SEP2)
        display_cols = ["category", "partition_type", "failure_mode", "verified", "sas_code", "python_code"]
        display_cols = [c for c in display_cols if c in df.columns]
        preview = df[display_cols].head(5).copy()
        # truncate long code fields so the table stays readable
        for col in ("sas_code", "python_code"):
            if col in preview.columns:
                preview[col] = preview[col].astype(str).str.split("\n").str[0].str[:70]
        print(preview.to_string(index=False))

    except ImportError as e:
        print(f"  [!] Missing dependency: {e}")
    except Exception as e:
        print(f"  [!] Error: {e}")


# ── DuckDB ───────────────────────────────────────────────────────────────────

def show_duckdb():
    _hdr("DuckDB  —  LLM Audit Logs  (data/analytics.duckdb)")
    try:
        import duckdb

        if not os.path.exists(DUCKDB_PATH):
            print("  [!] analytics.duckdb not found — pipeline hasn't run yet.")
            return

        con = duckdb.connect(DUCKDB_PATH, read_only=True)
        tables = con.execute("SHOW TABLES").fetchdf()
        print(f"  Tables : {tables['name'].tolist()}\n")

        for tname in tables["name"]:
            try:
                count = con.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
                print(f"  {tname:<40} {count} rows")
            except Exception:
                pass

        # first 5 rows of every table
        print(f"\n  First 5 rows per table:")
        for tname in tables["name"]:
            print(f"\n  [{tname}]")
            print(SEP2)
            try:
                df = con.execute(f"SELECT * FROM {tname} LIMIT 5").fetchdf()
                if df.empty:
                    print("  (empty)")
                else:
                    # truncate any text column > 80 chars so output stays readable
                    for col in df.select_dtypes(include="object").columns:
                        df[col] = df[col].astype(str).str[:80]
                    print(df.to_string(index=False))
            except Exception as e:
                print(f"  (error: {e})")

        # conversion_results aggregates
        if "conversion_results" in tables["name"].values:
            print(f"\n  conversion_results — aggregates by status:")
            print(SEP2)
            agg = con.execute("""
                SELECT
                    status,
                    COUNT(*)                      AS count,
                    ROUND(AVG(llm_confidence), 3) AS avg_conf,
                    SUM(retry_count)              AS total_retries
                FROM conversion_results
                GROUP BY status
                ORDER BY count DESC
            """).fetchdf()
            print(agg.to_string(index=False))

        con.close()

    except ImportError:
        print("  [!] duckdb not installed: venv/Scripts/pip install duckdb")
    except Exception as e:
        print(f"  [!] Error: {e}")


# ── SQLite ────────────────────────────────────────────────────────────────────

def show_sqlite():
    _hdr("SQLite  —  API Database  (data/codara_api.db)")
    try:
        import sqlite3
        import pandas as pd

        if not os.path.exists(SQLITE_PATH):
            print("  [!] codara_api.db not found — start the API first (uvicorn api.main:app).")
            return

        con = sqlite3.connect(SQLITE_PATH)

        tables = pd.read_sql(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
            con
        )["name"].tolist()
        print(f"  Tables : {tables}\n")

        for tname in tables:
            try:
                count = pd.read_sql(f"SELECT COUNT(*) AS n FROM {tname}", con)["n"][0]
                print(f"  {tname:<40} {count} rows")
            except Exception:
                pass

        # first 5 rows of every table
        print(f"\n  First 5 rows per table:")
        for tname in tables:
            print(f"\n  [{tname}]")
            print(SEP2)
            try:
                df = pd.read_sql(f"SELECT * FROM {tname} LIMIT 5", con)
                if df.empty:
                    print("  (empty)")
                else:
                    for col in df.select_dtypes(include="object").columns:
                        df[col] = df[col].astype(str).str[:80]
                    print(df.to_string(index=False))
            except Exception as e:
                print(f"  (error: {e})")

        con.close()

    except ImportError as e:
        print(f"  [!] Missing dependency: {e}")
    except Exception as e:
        print(f"  [!] Error: {e}")


# ── entrypoint ────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    target = args[0].lower() if args else "all"
    search = " ".join(args[2:]) if len(args) >= 3 and args[1] == "search" else ""

    if target in ("all", "lance"):
        show_lancedb(search_query=search)
    if target in ("all", "duck"):
        show_duckdb()
    if target in ("all", "sqlite"):
        show_sqlite()

    if target not in ("all", "lance", "duck", "sqlite"):
        print(__doc__)

    print(f"\n{SEP}")
    print("  Done.")
    print(SEP)


if __name__ == "__main__":
    main()
