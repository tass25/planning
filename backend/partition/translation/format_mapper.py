"""SAS format/informat → Python mapping.

Two entry points used by TranslationAgent and DeterministicTranslator:

  ``get_format_hint_block(sas_code)``
      Scans a SAS block for FORMAT/INFORMAT statements, returns a Markdown
      ``## SAS Format Reference`` block to inject into the LLM prompt.

  ``extract_proc_format_values(sas_code)``
      Parses PROC FORMAT VALUE blocks and returns a dict of custom format
      definitions: ``{"statusfmt": {"1": "Active", "2": "Closed"}, ...}``
      Injected into the prompt as ``## User-Defined SAS Formats``.

  ``translate_format_to_python(format_name)``
      Returns the Python equivalent string for a named SAS format, or None.

SAS date epoch: January 1, 1960 (day 0). Numeric SAS date variables are
days since this epoch. Use ``pd.Timestamp('1960-01-01') + pd.to_timedelta(col, 'D')``.
"""

from __future__ import annotations

import re
from typing import Optional

# ── Display format map ────────────────────────────────────────────────────────
# Maps SAS format name (uppercase, no trailing dot, no width.dec) →
# (python_equivalent, description, pandas_operation_hint)

_DISPLAY_FORMATS: dict[str, tuple[str, str, str]] = {
    # ── Date formats ──────────────────────────────────────────────────────────
    "DATE9":       ("%d%b%Y",        "01JAN2024",   "strftime('%d%b%Y').str.upper()"),
    "DATE7":       ("%d%b%y",        "01JAN24",     "strftime('%d%b%y').str.upper()"),
    "DDMMYY10":    ("%d/%m/%Y",      "01/01/2024",  "strftime('%d/%m/%Y')"),
    "DDMMYY8":     ("%d/%m/%y",      "01/01/24",    "strftime('%d/%m/%y')"),
    "MMDDYY10":    ("%m/%d/%Y",      "01/31/2024",  "strftime('%m/%d/%Y')"),
    "MMDDYY8":     ("%m/%d/%y",      "01/31/24",    "strftime('%m/%d/%y')"),
    "YYMMDD10":    ("%Y-%m-%d",      "2024-01-31",  "strftime('%Y-%m-%d')"),
    "YYMMDD8":     ("%y-%m-%d",      "24-01-31",    "strftime('%y-%m-%d')"),
    "YYMMDDD8":    ("%Y%m%d",        "20240131",    "strftime('%Y%m%d')"),
    "DATETIME20":  ("%d%b%Y:%H:%M:%S", "01JAN2024:00:00:00", "strftime('%d%b%Y:%H:%M:%S').str.upper()"),
    "DATETIME18":  ("%d%b%Y:%H:%M:%S", "01JAN24:00:00:00",  "strftime('%d%b%y:%H:%M:%S').str.upper()"),
    "TIME8":       ("%H:%M:%S",      "14:30:00",    "strftime('%H:%M:%S')"),
    "TIME5":       ("%H:%M",         "14:30",       "strftime('%H:%M')"),
    "MONYY7":      ("%b%Y",          "JAN2024",     "strftime('%b%Y').str.upper()"),
    "MONYY5":      ("%b%y",          "JAN24",       "strftime('%b%y').str.upper()"),
    "MONNAME":     ("%B",            "January",     "strftime('%B')"),
    "WEEKDATE":    ("%A, %B %d, %Y", "Wednesday, January 01, 2024", "strftime('%A, %B %d, %Y')"),
    "WEEKDATX":    ("%A, %d. %B %Y", "Wednesday, 01. January 2024","strftime('%A, %d. %B %Y')"),
    "WEEKDAY":     ("%w",            "3 (Wednesday)","dt.dayofweek (0=Mon; SAS 1=Sun)"),
    "DAY":         ("%d",            "01",          "dt.day"),
    "MONTH":       ("%m",            "01",          "dt.month"),
    "YEAR":        ("%Y",            "2024",        "dt.year"),
    "QTR":         "quarter",        # special — handled below
    "JULDAY":      "%j",             # day of year
    "JULIAN":      ("%Y%j",          "2024001",     "strftime('%Y%j')"),
    "DOWNAME":     ("%A",            "Wednesday",   "strftime('%A')"),
    # ── Numeric formats ───────────────────────────────────────────────────────
    "COMMA":       ("{:,.Nf}",       "1,234.56",    "apply(lambda x: f'{x:,.Nf}')"),
    "DOLLAR":      ("${:,.Nf}",      "$1,234.56",   "apply(lambda x: f'${x:,.Nf}')"),
    "EURO":        ("€{:,.Nf}",      "€1.234,56",   "apply(lambda x: f'€{x:,.Nf}')"),
    "PERCENT":     ("{:.N%}",        "12.34%",      "apply(lambda x: f'{x:.N%}')"),
    "BEST":        ("{}",            "auto",        "auto — use repr()"),
    "F":           ("{:.Nf}",        "123.46",      "apply(lambda x: f'{x:.Nf}')"),
    "E":           ("{:.Ne}",        "1.23e+02",    "apply(lambda x: f'{x:.Ne}')"),
    "Z":           ("{:0Nd}",        "00123",       "apply(lambda x: f'{int(x):0Nd}')"),
    "HEX":         ("{:NX}",         "0A1B",        "apply(lambda x: f'{int(x):NX}')"),
    "BINARY":      ("{:0Nb}",        "01001011",    "apply(lambda x: f'{int(x):0Nb}')"),
    "OCTAL":       ("{:0No}",        "0173",        "apply(lambda x: f'{int(x):0No}')"),
    # ── Character formats ─────────────────────────────────────────────────────
    "$UPCASE":     (".str.upper()",  "HELLO",       ".str.upper()"),
    "$LOWCASE":    (".str.lower()",  "hello",       ".str.lower()"),
    "$QUOTE":      (".apply(lambda x: f'\\'{x}\\'')", "'hello'", ".apply(lambda x: f'\\'{x}\\'')"),
    "$CHAR":       ("no-op",         "passthrough", "no transformation — char variable passthrough"),
    "$VARYING":    ("no-op",         "passthrough", "variable-length character — use str dtype"),
    # ── Special ───────────────────────────────────────────────────────────────
    "MISSING":     ("pd.isna()",     ".",           "pd.isna(col)"),
    "NLDATE":      ("%d/%m/%Y",      "locale date", "strftime('%d/%m/%Y')"),
    "NLMNY":       ("{:,.2f}",       "locale money","apply(lambda x: f'{x:,.2f}')"),
}

# ── Informat map: SAS → pd.to_datetime / pd.to_timedelta kwargs ───────────────
# Values are either a dict of kwargs for pd.to_datetime, or a special string.

_INFORMAT_MAP: dict[str, dict] = {
    "DATE":       {"format": "%d%b%Y"},
    "DATE7":      {"format": "%d%b%y"},
    "DDMMYY":     {"format": "%d/%m/%Y"},
    "DDMMYY10":   {"format": "%d/%m/%Y"},
    "DDMMYY8":    {"format": "%d/%m/%y"},
    "MMDDYY":     {"format": "%m/%d/%Y"},
    "MMDDYY10":   {"format": "%m/%d/%Y"},
    "MMDDYY8":    {"format": "%m/%d/%y"},
    "YYMMDD":     {"format": "%Y-%m-%d"},
    "YYMMDD10":   {"format": "%Y-%m-%d"},
    "ANYDTDTE":   {"infer_datetime_format": True},      # flexible
    "ANYDTDTM":   {"infer_datetime_format": True},
    "DATETIME":   {"format": "%d%b%Y:%H:%M:%S"},
    "DATETIME20": {"format": "%d%b%Y:%H:%M:%S"},
    "TIME":       {"format": "%H:%M:%S"},
    "MONYY":      {"format": "%b%Y"},
    "IS8601DA":   {"format": "%Y-%m-%d"},
    "IS8601DT":   {"format": "%Y-%m-%dT%H:%M:%S"},
    "E8601DA":    {"format": "%Y-%m-%d"},
    "E8601DT":    {"format": "%Y-%m-%dT%H:%M:%S"},
}

# ── SAS date epoch ────────────────────────────────────────────────────────────
SAS_EPOCH = "pd.Timestamp('1960-01-01')"
SAS_DATE_NOTE = (
    "SAS numeric date variables are days since 1960-01-01. "
    "Convert with: `pd.to_datetime(col, unit='D', origin='1960-01-01')`"
)


# ── Public helpers ────────────────────────────────────────────────────────────

def _normalize_format_name(raw: str) -> str:
    """Strip width.dec suffix and uppercase: 'date9.' → 'DATE', 'comma10.2' → 'COMMA'."""
    name = raw.strip().upper().rstrip(".")
    # Remove trailing width/decimal spec: DATE9 → DATE, COMMA10 → COMMA, F8 → F
    name = re.sub(r"\d+\.?\d*$", "", name)
    return name


def translate_format_to_python(format_name: str) -> Optional[str]:
    """Return the Python/pandas equivalent string for a named SAS format."""
    key = _normalize_format_name(format_name)
    entry = _DISPLAY_FORMATS.get(key)
    if entry is None:
        return None
    if isinstance(entry, tuple):
        return entry[2]  # pandas_operation_hint
    return str(entry)


def _extract_format_statements(sas_code: str) -> list[tuple[str, str]]:
    """Return list of (variable, format_spec) from FORMAT var fmt.; statements."""
    results = []
    for m in re.finditer(
        r"\bformat\b\s+([A-Za-z_]\w*)\s+(\$?[A-Za-z_]\w*\d*\.?\d*)\s*;",
        sas_code, re.IGNORECASE,
    ):
        results.append((m.group(1).lower(), m.group(2)))
    return results


def _extract_informat_statements(sas_code: str) -> list[tuple[str, str]]:
    """Return list of (variable, informat_spec) from INFORMAT var fmt.; statements."""
    results = []
    for m in re.finditer(
        r"\binformat\b\s+([A-Za-z_]\w*)\s+(\$?[A-Za-z_]\w*\d*\.?\d*)\s*;",
        sas_code, re.IGNORECASE,
    ):
        results.append((m.group(1).lower(), m.group(2)))
    return results


def extract_proc_format_values(sas_code: str) -> dict[str, dict[str, str]]:
    """Parse PROC FORMAT VALUE blocks.

    Handles::

        proc format;
          value $statusfmt
            1 = 'Active'
            2 = 'Closed'
            other = 'Unknown';
        run;

    Returns::

        {"statusfmt": {"1": "Active", "2": "Closed", "other": "Unknown"}}
    """
    result: dict[str, dict[str, str]] = {}

    proc_fmt_pattern = re.compile(
        r"proc\s+format[^;]*;(.*?)run\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    value_block_pattern = re.compile(
        r"value\s+(\$?\w+)\s+((?:[^;]*\n?)*?);",
        re.IGNORECASE,
    )
    pair_pattern = re.compile(
        r"([\d.\-]+|['\"].*?['\"]|other|low|high|\.)\s*(?:[-,]\s*(?:[\d.\-]+|['\"].*?['\"]|other))?\s*=\s*['\"]([^'\"]*)['\"]",
        re.IGNORECASE,
    )

    for proc_m in proc_fmt_pattern.finditer(sas_code):
        body = proc_m.group(1)
        for val_m in value_block_pattern.finditer(body):
            fmt_name = val_m.group(1).lower().lstrip("$")
            pairs_text = val_m.group(2)
            mapping: dict[str, str] = {}
            for pair_m in pair_pattern.finditer(pairs_text):
                key = pair_m.group(1).strip("\"'").strip()
                label = pair_m.group(2)
                mapping[key] = label
            if mapping:
                result[fmt_name] = mapping
    return result


def get_format_hint_block(sas_code: str) -> str:
    """Build a Markdown ## SAS Format Reference block for injection into LLM prompt.

    Scans FORMAT, INFORMAT statements and PROC FORMAT blocks.
    Returns empty string if nothing relevant found.
    """
    lines: list[str] = []

    # FORMAT statements
    fmt_stmts = _extract_format_statements(sas_code)
    if fmt_stmts:
        lines.append("### Variable Display Formats")
        has_date = False
        for var, fmt_spec in fmt_stmts:
            key = _normalize_format_name(fmt_spec)
            entry = _DISPLAY_FORMATS.get(key)
            if entry and isinstance(entry, tuple):
                strftime, example, pandas_op = entry
                lines.append(f"- `{var}` uses `{fmt_spec}` → `{pandas_op}` (example: `{example}`)")
                # Flag date variables for epoch note
                if key in ("DATE", "DATE7", "DATE9", "DATETIME", "DATETIME20", "DATETIME18"):
                    has_date = True
            else:
                lines.append(f"- `{var}` uses `{fmt_spec}` — translate display formatting appropriately")
        if has_date:
            lines.append(f"\n> ⚠ **SAS Date Note**: {SAS_DATE_NOTE}")

    # INFORMAT statements
    informat_stmts = _extract_informat_statements(sas_code)
    if informat_stmts:
        lines.append("\n### Variable Read Informats (for pd.to_datetime)")
        for var, inf_spec in informat_stmts:
            key = _normalize_format_name(inf_spec)
            inf_entry = _INFORMAT_MAP.get(key)
            if inf_entry:
                fmt_str = inf_entry.get("format", "infer")
                if "format" in inf_entry:
                    lines.append(f"- `{var}`: `pd.to_datetime(df['{var}'], format='{fmt_str}')`")
                else:
                    lines.append(f"- `{var}`: `pd.to_datetime(df['{var}'], infer_datetime_format=True)`")
            else:
                lines.append(f"- `{var}` informat `{inf_spec}`: use `pd.to_datetime()` with appropriate format")

    # PROC FORMAT VALUE blocks
    proc_fmts = extract_proc_format_values(sas_code)
    if proc_fmts:
        lines.append("\n### User-Defined Formats (from PROC FORMAT)")
        for fmt_name, mapping in proc_fmts.items():
            map_repr = "{" + ", ".join(f"{repr(k)}: {repr(v)}" for k, v in list(mapping.items())[:8]) + "}"
            if len(mapping) > 8:
                map_repr = map_repr[:-1] + ", ...}"
            lines.append(
                f"- Format `{fmt_name}`: translate as `df['col'].map({map_repr}).fillna('Other')` "
                f"— **NEVER overwrite the original column**; store result in a new `_fmt` column."
            )

    if not lines:
        return ""

    header = "## SAS Format Reference (apply these mappings in the translation)"
    return header + "\n" + "\n".join(lines)
