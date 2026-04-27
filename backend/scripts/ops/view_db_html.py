"""
view_db_html.py — Generate a beautiful HTML report of all Codara databases.

Databases shown: DuckDB, LanceDB, Redis (SQLite excluded).
Outputs: opens data/db_report.html in the default browser.

Usage (from backend/):
    C:/Users/labou/Desktop/Stage/venv/Scripts/python scripts/ops/view_db_html.py
"""
from __future__ import annotations

import html
import os
import sys
import webbrowser
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", ".."))
_DATA = os.path.join(_BACKEND, "data")

LANCEDB_PATH = os.path.join(_DATA, "lancedb")
DUCKDB_PATH = os.path.join(_DATA, "analytics.duckdb")
OUTPUT_PATH = os.path.join(_DATA, "db_report.html")

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Codara — Database Report</title>
<style>
  :root {{
    --bg: #0d1117;
    --surface: #161b22;
    --surface2: #1c2129;
    --border: #30363d;
    --text: #e6edf3;
    --text-dim: #8b949e;
    --accent: #58a6ff;
    --accent2: #3fb950;
    --accent3: #d2a8ff;
    --accent4: #f0883e;
    --red: #f85149;
    --code-bg: #1a1f27;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    line-height: 1.6;
    padding: 2rem;
  }}
  .header {{
    text-align: center;
    margin-bottom: 3rem;
    padding-bottom: 2rem;
    border-bottom: 1px solid var(--border);
  }}
  .header h1 {{
    font-size: 2.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, var(--accent), var(--accent3));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.5rem;
  }}
  .header .subtitle {{
    color: var(--text-dim);
    font-size: 1rem;
  }}
  .stats-bar {{
    display: flex;
    justify-content: center;
    gap: 2rem;
    margin-top: 1.5rem;
    flex-wrap: wrap;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1rem 1.8rem;
    text-align: center;
    min-width: 150px;
  }}
  .stat-card .stat-value {{
    font-size: 2rem;
    font-weight: 700;
  }}
  .stat-card .stat-label {{
    color: var(--text-dim);
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .stat-card.duckdb .stat-value {{ color: var(--accent4); }}
  .stat-card.lancedb .stat-value {{ color: var(--accent2); }}
  .stat-card.redis .stat-value {{ color: var(--red); }}

  .db-section {{
    margin-bottom: 3rem;
  }}
  .db-header {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
    padding-bottom: 0.75rem;
    border-bottom: 2px solid var(--border);
  }}
  .db-icon {{
    width: 40px;
    height: 40px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.3rem;
    font-weight: 700;
    color: #fff;
    flex-shrink: 0;
  }}
  .db-icon.duckdb {{ background: linear-gradient(135deg, #f0883e, #d29922); }}
  .db-icon.lancedb {{ background: linear-gradient(135deg, #3fb950, #2ea043); }}
  .db-icon.redis {{ background: linear-gradient(135deg, #f85149, #da3633); }}
  .db-header h2 {{
    font-size: 1.5rem;
    font-weight: 600;
  }}
  .db-header .db-meta {{
    color: var(--text-dim);
    font-size: 0.85rem;
    margin-left: auto;
  }}

  .table-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 1.5rem;
    overflow: hidden;
  }}
  .table-card-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1.25rem;
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    user-select: none;
  }}
  .table-card-header:hover {{
    background: #22272e;
  }}
  .table-card-header h3 {{
    font-size: 1rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }}
  .table-card-header h3 .tbl-icon {{
    color: var(--accent);
    font-size: 0.9rem;
  }}
  .badge {{
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
  }}
  .badge-rows {{
    background: rgba(88,166,255,0.15);
    color: var(--accent);
  }}
  .badge-cols {{
    background: rgba(210,168,255,0.15);
    color: var(--accent3);
  }}
  .table-card-body {{
    overflow-x: auto;
    max-height: 600px;
    overflow-y: auto;
  }}
  .table-card-body.collapsed {{
    display: none;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
  }}
  thead {{
    position: sticky;
    top: 0;
    z-index: 1;
  }}
  th {{
    background: var(--surface2);
    color: var(--accent);
    padding: 0.6rem 0.75rem;
    text-align: left;
    font-weight: 600;
    white-space: nowrap;
    border-bottom: 1px solid var(--border);
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }}
  td {{
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid rgba(48,54,61,0.5);
    max-width: 400px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    vertical-align: top;
  }}
  td.wrap {{
    white-space: pre-wrap;
    word-break: break-word;
  }}
  tr:hover td {{
    background: rgba(88,166,255,0.04);
  }}
  tr:nth-child(even) td {{
    background: rgba(255,255,255,0.02);
  }}
  tr:nth-child(even):hover td {{
    background: rgba(88,166,255,0.06);
  }}

  .empty-msg {{
    padding: 2rem;
    text-align: center;
    color: var(--text-dim);
    font-style: italic;
  }}
  .error-msg {{
    padding: 1.5rem;
    color: var(--red);
    background: rgba(248,81,73,0.1);
    border-radius: 8px;
    margin: 1rem;
  }}

  .redis-key {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 1rem;
    overflow: hidden;
  }}
  .redis-key-header {{
    padding: 0.75rem 1.25rem;
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 0.75rem;
    cursor: pointer;
  }}
  .redis-key-header:hover {{ background: #22272e; }}
  .redis-key-header .key-name {{
    font-family: 'Consolas', 'Fira Code', monospace;
    color: var(--red);
    font-weight: 600;
  }}
  .redis-key-header .key-type {{
    font-size: 0.75rem;
    padding: 0.1rem 0.5rem;
    border-radius: 12px;
    background: rgba(248,81,73,0.15);
    color: var(--red);
    font-weight: 600;
  }}
  .redis-key-body {{
    padding: 1rem 1.25rem;
    font-family: 'Consolas', 'Fira Code', monospace;
    font-size: 0.82rem;
    max-height: 400px;
    overflow: auto;
    background: var(--code-bg);
  }}
  .redis-key-body.collapsed {{ display: none; }}
  .redis-key-body pre {{
    white-space: pre-wrap;
    word-break: break-word;
  }}

  .toggle-arrow {{
    transition: transform 0.2s;
    font-size: 0.8rem;
    color: var(--text-dim);
  }}
  .toggle-arrow.open {{ transform: rotate(90deg); }}

  .footer {{
    text-align: center;
    margin-top: 3rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--border);
    color: var(--text-dim);
    font-size: 0.85rem;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>Codara Database Report</h1>
  <p class="subtitle">DuckDB &bull; LanceDB &bull; Redis &mdash; Generated {timestamp}</p>
  <div class="stats-bar">
    {stats_cards}
  </div>
</div>

{sections}

<div class="footer">
  Codara v3.1.0 &mdash; SAS &rarr; Python Conversion Accelerator
</div>

<script>
function toggleTable(id) {{
  const body = document.getElementById(id);
  const arrow = document.getElementById(id + '-arrow');
  if (body.classList.contains('collapsed')) {{
    body.classList.remove('collapsed');
    arrow.classList.add('open');
  }} else {{
    body.classList.add('collapsed');
    arrow.classList.remove('open');
  }}
}}
</script>
</body>
</html>
"""


def _esc(val: object) -> str:
    s = str(val) if val is not None else ""
    if len(s) > 500:
        s = s[:500] + "…"
    return html.escape(s)


def _build_html_table(columns: list[str], rows: list[list], table_id: str) -> str:
    if not rows:
        return f'<div id="{table_id}" class="table-card-body"><div class="empty-msg">No rows</div></div>'

    lines = [f'<div id="{table_id}" class="table-card-body"><table>']
    lines.append("<thead><tr>")
    for col in columns:
        lines.append(f"<th>{_esc(col)}</th>")
    lines.append("</tr></thead><tbody>")
    for row in rows:
        lines.append("<tr>")
        for val in row:
            lines.append(f"<td title=\"{_esc(val)}\">{_esc(val)}</td>")
        lines.append("</tr>")
    lines.append("</tbody></table></div>")
    return "\n".join(lines)


_table_counter = 0


def _next_id() -> str:
    global _table_counter
    _table_counter += 1
    return f"tbl-{_table_counter}"


# ── DuckDB ──────────────────────────────────────────────────────────────────

def collect_duckdb() -> tuple[str, int, int]:
    cards = []
    total_rows = 0
    total_tables = 0

    try:
        import duckdb

        if not os.path.exists(DUCKDB_PATH):
            return '<div class="error-msg">analytics.duckdb not found — pipeline hasn\'t run yet.</div>', 0, 0

        con = duckdb.connect(DUCKDB_PATH, read_only=True)
        tables_df = con.execute("SHOW TABLES").fetchdf()
        table_names = tables_df["name"].tolist()
        total_tables = len(table_names)

        for tname in table_names:
            try:
                count = con.execute(f"SELECT COUNT(*) FROM \"{tname}\"").fetchone()[0]
                total_rows += count
                cols_df = con.execute(f"DESCRIBE \"{tname}\"").fetchdf()
                col_names = cols_df["column_name"].tolist()
                all_rows = con.execute(f"SELECT * FROM \"{tname}\"").fetchall()

                tid = _next_id()
                table_html = _build_html_table(col_names, all_rows, tid)

                cards.append(f"""
<div class="table-card">
  <div class="table-card-header" onclick="toggleTable('{tid}')">
    <h3><span class="tbl-icon">&#9638;</span> {_esc(tname)}</h3>
    <div>
      <span class="badge badge-rows">{count} rows</span>
      <span class="badge badge-cols">{len(col_names)} cols</span>
      <span class="toggle-arrow open" id="{tid}-arrow">&#9654;</span>
    </div>
  </div>
  {table_html}
</div>""")
            except Exception as e:
                cards.append(f'<div class="error-msg">Error reading {tname}: {_esc(e)}</div>')

        con.close()
    except ImportError:
        return '<div class="error-msg">duckdb not installed</div>', 0, 0
    except Exception as e:
        return f'<div class="error-msg">DuckDB error: {_esc(e)}</div>', 0, 0

    return "\n".join(cards), total_rows, total_tables


# ── LanceDB ─────────────────────────────────────────────────────────────────

LANCE_SKIP_COLS = {"vector", "embedding"}


def collect_lancedb() -> tuple[str, int, int]:
    cards = []
    total_rows = 0
    total_tables = 0

    try:
        import lancedb

        if not os.path.exists(LANCEDB_PATH):
            return '<div class="error-msg">data/lancedb not found. Run seed_kb.py to populate.</div>', 0, 0

        db = lancedb.connect(LANCEDB_PATH)
        tables_result = db.list_tables()
        table_names = tables_result.tables if hasattr(tables_result, "tables") else list(tables_result)
        total_tables = len(table_names)

        if not table_names:
            return '<div class="empty-msg">No tables yet. Run seed_kb.py to populate.</div>', 0, 0

        for tname in table_names:
            try:
                t = db.open_table(tname)
                df = t.to_pandas()
                count = len(df)
                total_rows += count

                display_cols = [c for c in df.columns if c.lower() not in LANCE_SKIP_COLS]
                rows_data = []
                for _, row in df.iterrows():
                    rows_data.append([row[c] for c in display_cols])

                tid = _next_id()
                table_html = _build_html_table(display_cols, rows_data, tid)

                cards.append(f"""
<div class="table-card">
  <div class="table-card-header" onclick="toggleTable('{tid}')">
    <h3><span class="tbl-icon">&#9638;</span> {_esc(tname)}</h3>
    <div>
      <span class="badge badge-rows">{count} rows</span>
      <span class="badge badge-cols">{len(display_cols)} cols (vector hidden)</span>
      <span class="toggle-arrow open" id="{tid}-arrow">&#9654;</span>
    </div>
  </div>
  {table_html}
</div>""")
            except Exception as e:
                cards.append(f'<div class="error-msg">Error reading {tname}: {_esc(e)}</div>')

    except ImportError as e:
        return f'<div class="error-msg">Missing dependency: {_esc(e)}</div>', 0, 0
    except Exception as e:
        return f'<div class="error-msg">LanceDB error: {_esc(e)}</div>', 0, 0

    return "\n".join(cards), total_rows, total_tables


# ── Redis ────────────────────────────────────────────────────────────────────

def collect_redis() -> tuple[str, int]:
    cards = []
    total_keys = 0

    try:
        import redis as redis_lib

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis_lib.from_url(redis_url, decode_responses=True)
        r.ping()

        keys = sorted(r.keys("*"))
        total_keys = len(keys)

        if not keys:
            return '<div class="empty-msg">No keys in Redis.</div>', 0

        for key in keys:
            try:
                key_type = r.type(key)
                tid = _next_id()

                if key_type == "string":
                    val = r.get(key) or ""
                    content = _esc(val)
                elif key_type == "hash":
                    val = r.hgetall(key)
                    lines = [f"{_esc(k)}: {_esc(v)}" for k, v in val.items()]
                    content = "\n".join(lines)
                elif key_type == "list":
                    val = r.lrange(key, 0, -1)
                    content = "\n".join(_esc(v) for v in val)
                elif key_type == "set":
                    val = r.smembers(key)
                    content = "\n".join(_esc(v) for v in sorted(val))
                elif key_type == "zset":
                    val = r.zrange(key, 0, -1, withscores=True)
                    lines = [f"[{score}] {_esc(member)}" for member, score in val]
                    content = "\n".join(lines)
                elif key_type == "stream":
                    val = r.xrange(key, count=100)
                    lines = []
                    for entry_id, fields in val:
                        fields_str = "  ".join(f"{_esc(k)}={_esc(v)}" for k, v in fields.items())
                        lines.append(f"{entry_id}  {fields_str}")
                    content = "\n".join(lines) if lines else "(empty stream)"
                else:
                    content = f"(unsupported type: {key_type})"

                ttl = r.ttl(key)
                ttl_label = f" &bull; TTL: {ttl}s" if ttl and ttl > 0 else ""

                cards.append(f"""
<div class="redis-key">
  <div class="redis-key-header" onclick="toggleTable('{tid}')">
    <span class="toggle-arrow open" id="{tid}-arrow">&#9654;</span>
    <span class="key-name">{_esc(key)}</span>
    <span class="key-type">{_esc(key_type)}</span>
    <span style="color: var(--text-dim); font-size: 0.8rem; margin-left: auto;">{_size_label(key_type, r, key)}{ttl_label}</span>
  </div>
  <div id="{tid}" class="redis-key-body"><pre>{content}</pre></div>
</div>""")
            except Exception as e:
                cards.append(f'<div class="error-msg">Error reading key {_esc(key)}: {_esc(e)}</div>')

    except ImportError:
        return '<div class="error-msg">redis package not installed</div>', 0
    except redis_lib.ConnectionError:
        return '<div class="error-msg">Cannot connect to Redis at ' + html.escape(os.environ.get("REDIS_URL", "redis://localhost:6379/0")) + '. Is it running?</div>', 0
    except Exception as e:
        return f'<div class="error-msg">Redis error: {_esc(e)}</div>', 0

    return "\n".join(cards), total_keys


def _size_label(key_type: str, r, key: str) -> str:
    try:
        if key_type == "string":
            return f"{r.strlen(key)} bytes"
        if key_type == "hash":
            return f"{r.hlen(key)} fields"
        if key_type == "list":
            return f"{r.llen(key)} items"
        if key_type == "set":
            return f"{r.scard(key)} members"
        if key_type == "zset":
            return f"{r.zcard(key)} members"
        if key_type == "stream":
            return f"{r.xlen(key)} entries"
    except Exception:
        pass
    return ""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Collecting DuckDB data...")
    duck_html, duck_rows, duck_tables = collect_duckdb()

    print("Collecting LanceDB data...")
    lance_html, lance_rows, lance_tables = collect_lancedb()

    print("Collecting Redis data...")
    redis_html, redis_keys = collect_redis()

    stats_cards = f"""
    <div class="stat-card duckdb">
      <div class="stat-value">{duck_rows}</div>
      <div class="stat-label">DuckDB Rows ({duck_tables} tables)</div>
    </div>
    <div class="stat-card lancedb">
      <div class="stat-value">{lance_rows}</div>
      <div class="stat-label">LanceDB Rows ({lance_tables} tables)</div>
    </div>
    <div class="stat-card redis">
      <div class="stat-value">{redis_keys}</div>
      <div class="stat-label">Redis Keys</div>
    </div>
    """

    sections = f"""
<div class="db-section">
  <div class="db-header">
    <div class="db-icon duckdb">D</div>
    <h2>DuckDB — LLM Audit Logs</h2>
    <span class="db-meta">{DUCKDB_PATH}</span>
  </div>
  {duck_html}
</div>

<div class="db-section">
  <div class="db-header">
    <div class="db-icon lancedb">L</div>
    <h2>LanceDB — Vector Knowledge Base</h2>
    <span class="db-meta">{LANCEDB_PATH}</span>
  </div>
  {lance_html}
</div>

<div class="db-section">
  <div class="db-header">
    <div class="db-icon redis">R</div>
    <h2>Redis — Checkpoints &amp; Cache</h2>
    <span class="db-meta">{os.environ.get("REDIS_URL", "redis://localhost:6379/0")}</span>
  </div>
  {redis_html}
</div>
"""

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    final_html = HTML_TEMPLATE.format(
        timestamp=timestamp,
        stats_cards=stats_cards,
        sections=sections,
    )

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(final_html)

    print(f"\nReport written to: {OUTPUT_PATH}")
    print(f"  DuckDB : {duck_tables} tables, {duck_rows} rows")
    print(f"  LanceDB: {lance_tables} tables, {lance_rows} rows")
    print(f"  Redis  : {redis_keys} keys")

    webbrowser.open(f"file:///{OUTPUT_PATH.replace(os.sep, '/')}")
    print("Opened in browser.")


if __name__ == "__main__":
    main()
