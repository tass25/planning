"""Deterministic (rule-based) SAS→Python translator.

Handles well-known, high-confidence patterns without touching the LLM:
  - PROC SORT / PROC SORT NODUPKEY
  - PROC IMPORT (CSV / Excel)
  - PROC EXPORT (CSV / Excel)
  - DATALINES / CARDS inline data
  - Simple DATA SET (copy / rename-only, no conditions)
  - PROC PRINT (head / display)

Returns a ``DeterministicResult`` (code + reason) when a pattern matches,
or ``None`` when the chunk requires LLM translation.

Usage in TranslationAgent::

    result = try_deterministic(partition.source_code)
    if result:
        return result.code, "deterministic"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger()


@dataclass
class DeterministicResult:
    code: str
    reason: str   # which rule matched


# ── helpers ───────────────────────────────────────────────────────────────────

def _strip_comments(sas: str) -> str:
    """Remove /* ... */ and * ...; comments."""
    sas = re.sub(r"/\*.*?\*/", "", sas, flags=re.DOTALL)
    sas = re.sub(r"^\s*\*[^;]*;", "", sas, flags=re.MULTILINE)
    return sas.strip()


def _clean(sas: str) -> str:
    return re.sub(r"\s+", " ", _strip_comments(sas)).strip()


def _name(raw: str) -> str:
    """Normalise a SAS name: lowercase, drop libref dot notation."""
    raw = raw.strip().lower()
    if "." in raw:
        raw = raw.split(".", 1)[1]
    return raw


# ── PROC SORT ─────────────────────────────────────────────────────────────────

_PROC_SORT_RE = re.compile(
    r"proc\s+sort\s+"
    r"(?:data\s*=\s*(?P<data>[A-Za-z0-9_.]+))?"
    r"(?:\s+out\s*=\s*(?P<out>[A-Za-z0-9_.]+))?"
    r"(?P<opts>[^;]*);"
    r".*?by\s+(?P<by>[^;]+);"
    r"(?:\s*run\s*;)?",
    re.IGNORECASE | re.DOTALL,
)


def _try_proc_sort(sas: str) -> Optional[DeterministicResult]:
    m = _PROC_SORT_RE.search(_clean(sas))
    if not m:
        return None

    data_ds  = _name(m.group("data") or "df")
    out_ds   = _name(m.group("out") or m.group("data") or "df")
    opts     = (m.group("opts") or "").lower()
    by_raw   = m.group("by").strip()
    nodupkey = "nodupkey" in opts
    noduprec = "noduprec" in opts

    # Parse BY variables — may have DESCENDING prefix
    by_vars: list[str] = []
    ascending: list[bool] = []
    for token in re.split(r"\s+", by_raw):
        tok = token.lower().strip()
        if tok == "descending":
            ascending.append(False)
        elif tok:
            by_vars.append(tok)
            ascending.append(True)  # may be overwritten next token

    if not by_vars:
        return None

    ascending_flags = ascending[: len(by_vars)]
    by_list   = str(by_vars)
    asc_list  = str(ascending_flags)

    lines = [
        "import pandas as pd  # noqa",
        f"{out_ds} = {data_ds}.sort_values({by_list}, ascending={asc_list}, kind='mergesort').reset_index(drop=True)",
    ]
    if nodupkey:
        lines.append(f"{out_ds} = {out_ds}.drop_duplicates(subset={by_list}).reset_index(drop=True)")
    elif noduprec:
        lines.append(f"{out_ds} = {out_ds}.drop_duplicates().reset_index(drop=True)")

    reason = "PROC SORT" + (" NODUPKEY" if nodupkey else "")
    return DeterministicResult(code="\n".join(lines), reason=reason)


# ── PROC IMPORT ───────────────────────────────────────────────────────────────

_PROC_IMPORT_RE = re.compile(
    r"proc\s+import\s+"
    r"(?:datafile\s*=\s*['\"]?(?P<file>[^'\";\s]+)['\"]?)?"
    r".*?out\s*=\s*(?P<out>[A-Za-z0-9_.]+)"
    r".*?dbms\s*=\s*(?P<dbms>\w+)"
    r"[^;]*;",
    re.IGNORECASE | re.DOTALL,
)


def _try_proc_import(sas: str) -> Optional[DeterministicResult]:
    m = _PROC_IMPORT_RE.search(sas)
    if not m:
        return None

    filepath = (m.group("file") or "input_file.csv").strip()
    out_ds   = _name(m.group("out"))
    dbms     = (m.group("dbms") or "csv").lower().strip()

    if dbms in ("csv", "dlm", "tab"):
        sep = "\\t" if dbms == "tab" else ","
        code = (
            f"import pandas as pd  # noqa\n"
            f"{out_ds} = pd.read_csv('{filepath}', sep='{sep}')\n"
            f"{out_ds}.columns = {out_ds}.columns.str.lower().str.strip()"
        )
    elif dbms in ("xlsx", "excel", "xls", "excelcs"):
        # Check for getnames / sheet options
        sheet_m = re.search(r"sheet\s*=\s*['\"]?([^'\";\s]+)", sas, re.IGNORECASE)
        sheet   = f", sheet_name='{sheet_m.group(1)}'" if sheet_m else ""
        code = (
            f"import pandas as pd  # noqa\n"
            f"{out_ds} = pd.read_excel('{filepath}'{sheet})\n"
            f"{out_ds}.columns = {out_ds}.columns.str.lower().str.strip()"
        )
    else:
        return None   # unknown DBMS — let LLM handle

    return DeterministicResult(code=code, reason=f"PROC IMPORT ({dbms.upper()})")


# ── PROC EXPORT ───────────────────────────────────────────────────────────────

_PROC_EXPORT_RE = re.compile(
    r"proc\s+export\s+"
    r"data\s*=\s*(?P<data>[A-Za-z0-9_.]+)"
    r".*?outfile\s*=\s*['\"]?(?P<file>[^'\";\s]+)['\"]?"
    r".*?dbms\s*=\s*(?P<dbms>\w+)"
    r"[^;]*;",
    re.IGNORECASE | re.DOTALL,
)


def _try_proc_export(sas: str) -> Optional[DeterministicResult]:
    m = _PROC_EXPORT_RE.search(sas)
    if not m:
        return None

    data_ds  = _name(m.group("data"))
    filepath = m.group("file").strip()
    dbms     = m.group("dbms").lower().strip()

    if dbms in ("csv", "dlm", "tab"):
        sep = "\\t" if dbms == "tab" else ","
        code = f"{data_ds}.to_csv('{filepath}', index=False, sep='{sep}')"
    elif dbms in ("xlsx", "excel", "xls"):
        code = f"{data_ds}.to_excel('{filepath}', index=False)"
    else:
        return None

    return DeterministicResult(code=code, reason=f"PROC EXPORT ({dbms.upper()})")


# ── DATALINES / CARDS ─────────────────────────────────────────────────────────

_DATALINES_RE = re.compile(
    r"data\s+(?P<out>[A-Za-z0-9_.]+)\s*;"
    r".*?input\s+(?P<vars>[^;]+);"
    r".*?(?:datalines|cards)\s*;\s*\n(?P<rows>.*?)\s*;\s*\n?"
    r"(?:\s*run\s*;)?",
    re.IGNORECASE | re.DOTALL,
)


def _try_datalines(sas: str) -> Optional[DeterministicResult]:
    m = _DATALINES_RE.search(sas)
    if not m:
        return None

    out_ds   = _name(m.group("out"))
    vars_raw = m.group("vars").strip()
    rows_raw = m.group("rows").strip()

    # Parse column names (strip format specs like $20. or date9.)
    cols: list[str] = []
    for tok in re.split(r"\s+", vars_raw):
        tok = tok.strip()
        if not tok or re.match(r"^[\$@]", tok):
            continue
        if re.match(r"^[A-Za-z_]\w*$", tok):
            cols.append(tok.lower())

    if not cols:
        return None

    rows = [r for r in rows_raw.split("\n") if r.strip()]
    data_repr = repr(rows)
    cols_repr = repr(cols)

    code = (
        "import io\nimport pandas as pd  # noqa\n"
        f"_raw = {data_repr}\n"
        f"{out_ds} = pd.read_csv(io.StringIO('\\n'.join(_raw)), sep=r'\\s+', "
        f"header=None, names={cols_repr})"
    )
    return DeterministicResult(code=code, reason="DATALINES/CARDS")


# ── Simple DATA SET (copy / rename, no conditions) ────────────────────────────

_SIMPLE_DATA_RE = re.compile(
    r"^data\s+(?P<out>[A-Za-z0-9_.]+)\s*;"
    r"\s*set\s+(?P<inp>[A-Za-z0-9_.]+)\s*;"
    r"(?P<body>.*?)"
    r"(?:run\s*;|$)",
    re.IGNORECASE | re.DOTALL,
)

_RENAME_RE = re.compile(
    r"rename\s+(?P<pairs>[^;]+);", re.IGNORECASE
)
_KEEP_RE   = re.compile(r"keep\s+(?P<cols>[^;]+);", re.IGNORECASE)
_DROP_RE   = re.compile(r"drop\s+(?P<cols>[^;]+);", re.IGNORECASE)


def _try_simple_data_step(sas: str) -> Optional[DeterministicResult]:
    """Only handles DATA out; SET in; with optional KEEP/DROP/RENAME."""
    m = _SIMPLE_DATA_RE.search(_strip_comments(sas))
    if not m:
        return None

    body = m.group("body") or ""

    # Bail if there are IF statements, RETAIN, LAG, OUTPUT, DO loops, etc.
    complex_keywords = re.compile(
        r"\b(if|retain|lag|output|do\s|merge|by\s|where|array|put|call)\b",
        re.IGNORECASE,
    )
    if complex_keywords.search(body):
        return None

    out_ds = _name(m.group("out"))
    inp_ds = _name(m.group("inp"))

    lines = [
        "import pandas as pd  # noqa",
        f"{out_ds} = {inp_ds}.copy()",
    ]

    # KEEP
    keep_m = _KEEP_RE.search(body)
    if keep_m:
        cols = [c.lower() for c in re.split(r"\s+", keep_m.group("cols").strip()) if c]
        lines.append(f"{out_ds} = {out_ds}[{cols}]")

    # DROP
    drop_m = _DROP_RE.search(body)
    if drop_m:
        cols = [c.lower() for c in re.split(r"\s+", drop_m.group("cols").strip()) if c]
        lines.append(f"{out_ds} = {out_ds}.drop(columns={cols}, errors='ignore')")

    # RENAME  var1=new1 var2=new2
    rename_m = _RENAME_RE.search(body)
    if rename_m:
        mapping: dict[str, str] = {}
        for pair in re.findall(r"(\w+)\s*=\s*(\w+)", rename_m.group("pairs")):
            mapping[pair[0].lower()] = pair[1].lower()
        if mapping:
            lines.append(f"{out_ds} = {out_ds}.rename(columns={mapping})")

    return DeterministicResult(code="\n".join(lines), reason="Simple DATA SET (copy/keep/drop/rename)")


# ── PROC PRINT ────────────────────────────────────────────────────────────────

_PROC_PRINT_RE = re.compile(
    r"proc\s+print\s+data\s*=\s*(?P<data>[A-Za-z0-9_.]+)"
    r"(?:\s*\(\s*obs\s*=\s*(?P<obs>\d+)\s*\))?"
    r"[^;]*;",
    re.IGNORECASE,
)


def _try_proc_print(sas: str) -> Optional[DeterministicResult]:
    m = _PROC_PRINT_RE.search(sas)
    if not m:
        return None

    data_ds = _name(m.group("data"))
    obs     = m.group("obs")

    if obs:
        code = f"print({data_ds}.head({obs}))"
    else:
        code = f"print({data_ds})"

    return DeterministicResult(code=code, reason="PROC PRINT")


# ── PROC FORMAT VALUE (discrete label mappings) ───────────────────────────────

_PROC_FORMAT_OUTER_RE = re.compile(
    r"proc\s+format\s*;(.+?)(?:run|quit)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_FORMAT_VALUE_BLOCK_RE = re.compile(
    r"value\s+(\$?\w+)\s+(.+?)\s*;",
    re.IGNORECASE | re.DOTALL,
)
# Matches a discrete pair:  'key' = 'label'  /  1 = 'label'  /  1,2 = 'label'
_DISCRETE_PAIR_RE = re.compile(
    r"(['\"][\w\s]+['\"]|\d+(?:\s*,\s*\d+)*)\s*=\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_OTHER_RE = re.compile(r"\bother\b\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
# Numeric range pattern:  18-64  /  low-17  /  65-high
_RANGE_RE = re.compile(r"\b(?:low|\d+)\s*-\s*(?:\d+|high)\b", re.IGNORECASE)


def _try_proc_format_value(sas: str) -> Optional[DeterministicResult]:
    """Translate PROC FORMAT VALUE discrete-label blocks to Python dicts.

    Only handles exact-value mappings (string → label, integer → label).
    Numeric range formats (e.g. 18-64) are left to the LLM.
    """
    outer = _PROC_FORMAT_OUTER_RE.search(sas)
    if not outer:
        return None

    body = outer.group(1)
    fmt_blocks = _FORMAT_VALUE_BLOCK_RE.findall(body)
    if not fmt_blocks:
        return None

    output_lines: list[str] = ["import pandas as pd  # noqa", ""]
    found_any = False

    for fmt_name_raw, pairs_raw in fmt_blocks:
        fmt_name = fmt_name_raw.lstrip("$").lower().strip()

        # Bail on range-based formats
        if _RANGE_RE.search(pairs_raw):
            return None

        mapping: dict[str, str] = {}
        for pair_m in _DISCRETE_PAIR_RE.finditer(pairs_raw):
            keys_str = pair_m.group(1).strip()
            label    = pair_m.group(2).strip()
            for k in re.split(r"\s*,\s*", keys_str):
                k = k.strip().strip("'\"")
                if k:
                    mapping[k] = label

        if not mapping:
            return None  # Nothing parseable — let LLM handle

        default_m = _OTHER_RE.search(pairs_raw)
        default_label = default_m.group(1) if default_m else None

        found_any = True
        output_lines.append(f"# PROC FORMAT VALUE {fmt_name_raw.strip()}")
        output_lines.append(f"{fmt_name}_fmt = {repr(mapping)}")
        if default_label:
            output_lines.append(
                f"# Usage: df['col'].map({fmt_name}_fmt).fillna({repr(default_label)})"
            )
        else:
            output_lines.append(f"# Usage: df['col'].map({fmt_name}_fmt)")
        output_lines.append("")

    if not found_any:
        return None

    return DeterministicResult(
        code="\n".join(output_lines).strip(),
        reason="PROC FORMAT VALUE (discrete label mapping)",
    )


# ── PROC SQL (simple SELECT — no joins, no GROUP BY, no subqueries) ───────────

_PROC_SQL_OUTER_RE = re.compile(
    r"proc\s+sql\s*;(.+?)quit\s*;",
    re.IGNORECASE | re.DOTALL,
)
_CREATE_SELECT_RE = re.compile(
    r"create\s+table\s+(?P<out>\w+)\s+as\s+select\s+(?P<cols>.+?)"
    r"\s+from\s+(?P<tbl>\w+)"
    r"(?:\s+where\s+(?P<where>.+?))?"
    r"(?:\s+order\s+by\s+(?P<orderby>[^;]+))?"
    r"\s*;",
    re.IGNORECASE | re.DOTALL,
)
_SQL_COMPLEX_RE = re.compile(
    r"\b(join|left\s+join|right\s+join|inner\s+join|full\s+join|"
    r"outer\s+join|having|exists|subquery|union|intersect|except|"
    r"case\s+when|over\s*\(|select\s+distinct|group\s+by|calculated)\b",
    re.IGNORECASE,
)
_SQL_SIMPLE_WHERE_RE = re.compile(
    r"^(\w+)\s*(=|!=|<>|>=|<=|>|<)\s*(.+)$",
)


def _try_proc_sql_simple(sas: str) -> Optional[DeterministicResult]:
    """Translate simple PROC SQL CREATE TABLE AS SELECT to pandas.

    Covers:
      SELECT cols FROM tbl WHERE simple_cond ORDER BY cols
    Returns None for any join, GROUP BY, window function, subquery, or complex WHERE.
    """
    outer = _PROC_SQL_OUTER_RE.search(sas)
    if not outer:
        return None

    sql_body = outer.group(1)

    if _SQL_COMPLEX_RE.search(sql_body):
        return None

    stmt_m = _CREATE_SELECT_RE.search(sql_body)
    if not stmt_m:
        return None

    out_ds   = stmt_m.group("out").lower()
    cols_raw = stmt_m.group("cols").strip()
    tbl      = stmt_m.group("tbl").lower()
    where    = (stmt_m.group("where") or "").strip()
    orderby  = (stmt_m.group("orderby") or "").strip()

    lines = ["import pandas as pd  # noqa"]

    # Column selection
    if cols_raw == "*":
        lines.append(f"{out_ds} = {tbl}.copy()")
    else:
        col_defs = [c.strip() for c in cols_raw.split(",")]
        select_cols: list[str] = []
        renames: dict[str, str] = {}
        for col_def in col_defs:
            alias_m = re.match(r"^(\w+)\s+as\s+(\w+)$", col_def.strip(), re.IGNORECASE)
            if alias_m:
                src, alias = alias_m.group(1).lower(), alias_m.group(2).lower()
                select_cols.append(src)
                renames[src] = alias
            elif re.match(r"^\w+$", col_def.strip()):
                select_cols.append(col_def.strip().lower())
            else:
                return None  # Expression column — let LLM handle

        col_select = f"{out_ds} = {tbl}[{select_cols}].copy()"
        if renames:
            col_select += f"\n{out_ds} = {out_ds}.rename(columns={repr(renames)})"
        lines.append(col_select)

    # WHERE clause — only simple single-condition comparisons
    if where:
        if re.search(r"\b(and|or|not|between|in\s*\()\b", where, re.IGNORECASE):
            return None
        where_m = _SQL_SIMPLE_WHERE_RE.match(where.strip())
        if not where_m:
            return None

        col_name = where_m.group(1).lower()
        op       = where_m.group(2).replace("<>", "!=")
        if op == "=":
            op = "=="
        val_raw  = where_m.group(3).strip().strip("'\"")
        try:
            float(val_raw)
            py_val = val_raw
        except ValueError:
            py_val = repr(val_raw)

        lines.append(f"{out_ds} = {out_ds}[{out_ds}['{col_name}'] {op} {py_val}]")

    # ORDER BY → sort_values
    if orderby:
        by_tokens = [t.strip() for t in orderby.split(",")]
        by_cols: list[str] = []
        asc_flags: list[bool] = []
        for tok in by_tokens:
            parts = tok.split()
            by_cols.append(parts[0].lower())
            asc_flags.append(len(parts) < 2 or parts[1].upper() != "DESC")
        lines.append(
            f"{out_ds} = {out_ds}.sort_values("
            f"{by_cols}, ascending={asc_flags}, kind='mergesort'"
            f").reset_index(drop=True)"
        )

    return DeterministicResult(
        code="\n".join(lines),
        reason="PROC SQL (simple SELECT/WHERE/ORDER BY)",
    )


# ── Public entry point ────────────────────────────────────────────────────────

_RULES = [
    _try_proc_sort,
    _try_proc_import,
    _try_proc_export,
    _try_datalines,
    _try_simple_data_step,
    _try_proc_print,
    _try_proc_format_value,
    _try_proc_sql_simple,
]


def try_deterministic(sas_code: str) -> Optional[DeterministicResult]:
    """Try each rule in order; return the first match or None."""
    for rule in _RULES:
        try:
            result = rule(sas_code)
            if result:
                return result
        except Exception as exc:
            logger.warning("deterministic_rule_error", rule=rule.__name__, error=str(exc))
    return None
