"""SAS built-in function reference table.

Maps SAS function names to their Python/pandas equivalents.
Injected into the LLM prompt as a ``## SAS Built-in Function Reference``
block when those functions are detected in the source code.

Usage::

    from partition.translation.sas_builtins import get_builtins_hint_block

    hint = get_builtins_hint_block(sas_code)  # "" if no relevant functions
    if hint:
        prompt += "\\n\\n" + hint
"""

from __future__ import annotations

import re
from typing import Optional

# ── Reference table ───────────────────────────────────────────────────────────
# Format: "SAS_FUNCTION": ("python_equivalent", "notes")

_BUILTINS: dict[str, tuple[str, str]] = {
    # ── String functions ──────────────────────────────────────────────────────
    "SUBSTR":      ("str[start:end]",
                    "SAS is 1-indexed; Python is 0-indexed. SUBSTR(s,2,3) → s[1:4]"),
    "SUBSTRING":   ("str[start:end]",
                    "Alias for SUBSTR"),
    "LENGTH":      ("len(str) or df['col'].str.len()",
                    "SAS returns the length WITHOUT trailing spaces"),
    "TRIM":        (".str.rstrip()",
                    "SAS TRIM removes only TRAILING spaces"),
    "STRIP":       (".str.strip()",
                    "SAS STRIP removes both leading and trailing spaces"),
    "LEFT":        (".str.lstrip()",
                    "SAS LEFT removes leading spaces"),
    "COMPRESS":    (".str.replace(r'[chars]', '', regex=True)",
                    "COMPRESS(s,'$ ') removes $ and space. Use re.sub or str.replace."),
    "COMPBL":      (".str.replace(r'\\s+', ' ', regex=True).str.strip()",
                    "Compresses multiple blanks to single blank"),
    "UPCASE":      (".str.upper()",
                    "Direct equivalent"),
    "LOWCASE":     (".str.lower()",
                    "Direct equivalent"),
    "PROPCASE":    (".str.title()",
                    "SAS PROPCASE capitalises first letter of each word"),
    "CATS":        ("''.join([str(x) for x in [...] if pd.notna(x)])",
                    "Concatenate stripping trailing spaces; missing values excluded"),
    "CATX":        ("sep.join([str(x) for x in [...] if pd.notna(x)])",
                    "Concatenate with separator, excluding missing values"),
    "CAT":         ("''.join(str(x) for x in [...])",
                    "Concatenate without stripping; missing values become blanks"),
    "CATT":        ("''.join(str(x).rstrip() for x in [...])",
                    "Concatenate trimming trailing spaces only"),
    "SCAN":        ("str.split()[n-1]",
                    "SCAN(s,2,' ') → s.split(' ')[1]. SAS is 1-indexed."),
    "INDEX":       (".str.find(substr) + 1",
                    "SAS returns 1-based index; 0 if not found. Python .find() returns 0-based; -1 if not found."),
    "FIND":        (".str.find(substr)",
                    "Similar to INDEX but with optional modifier and startpos"),
    "TRANWRD":     (".str.replace(from_str, to_str)",
                    "Replace all occurrences of a word; use str.replace() or re.sub()"),
    "TRANSLATE":   (".str.translate(str.maketrans(from_chars, to_chars))",
                    "Character-level substitution; use str.maketrans + str.translate"),
    "REVERSE":     (".str[::-1]",
                    "Reverse a string"),
    "REPEAT":      ("str * n",
                    "REPEAT('ab', 3) → 'ababab'"),
    "CHAR":        ("chr(n)",
                    "Returns character for ASCII code"),
    "RANK":        ("ord(char)",
                    "Returns ASCII rank/code of a character"),
    "VERIFY":      ("any(c not in allowed for c in s)",
                    "Returns position of first char NOT in character list; 0 if all in list"),

    # ── Numeric functions ─────────────────────────────────────────────────────
    "ABS":         ("abs(x)  /  df['col'].abs()",     "Direct equivalent"),
    "CEIL":        ("math.ceil(x)  /  np.ceil()",     "Direct equivalent"),
    "FLOOR":       ("math.floor(x)  /  np.floor()",   "Direct equivalent"),
    "ROUND":       ("round(x, d)  /  df['col'].round(d)",
                    "SAS ROUND(x,0.01) rounds to nearest 0.01; Python round() uses banker's rounding"),
    "INT":         ("int(x)  /  np.trunc(x)",
                    "SAS INT truncates toward zero; use int() or np.trunc()"),
    "MOD":         ("x % y  /  df['col'] % divisor",  "Modulo; SAS and Python agree for positive values"),
    "SIGN":        ("np.sign(x)",                      "Returns -1, 0, or 1"),
    "SQRT":        ("np.sqrt(x)",                      "Direct equivalent"),
    "EXP":         ("np.exp(x)",                       "e^x"),
    "LOG":         ("np.log(x)",                       "Natural log. SAS LOG is base e."),
    "LOG2":        ("np.log2(x)",                      "Log base 2"),
    "LOG10":       ("np.log10(x)",                     "Log base 10"),
    "MAX":         ("max(x, y)  /  df[['a','b']].max(axis=1)",
                    "SAS MAX ignores missing; pandas max() also ignores NaN by default"),
    "MIN":         ("min(x, y)  /  df[['a','b']].min(axis=1)",
                    "SAS MIN ignores missing; pandas min() also ignores NaN by default"),
    "SUM":         ("sum([x, y])  /  df[['a','b']].sum(axis=1)",
                    "SAS SUM ignores missing values; pandas sum(axis=1, skipna=True) too"),
    "MEAN":        ("np.mean([x, y])  /  df[['a','b']].mean(axis=1)",
                    "Row-wise mean ignoring missing"),
    "N":           ("df[['a','b']].count(axis=1)",
                    "Count of non-missing values across columns"),
    "NMISS":       ("df[['a','b']].isnull().sum(axis=1)",
                    "Count of missing values across columns"),
    "CMISS":       ("df[['a','b']].isnull().sum(axis=1)",
                    "Count of missing (char or numeric) — same as NMISS in pandas context"),
    "MISSING":     ("pd.isna(x)",
                    "Returns True if value is missing (NaN or None)"),
    "COALESCE":    ("df[['a','b','c']].bfill(axis=1).iloc[:,0]",
                    "Returns first non-missing value; pandas bfill across columns then take first"),
    "COALESEC":    ("df[['a','b','c']].bfill(axis=1).iloc[:,0]",
                    "Character version of COALESCE"),
    "RAND":        ("np.random.rand()  /  rng.uniform(0,1)",
                    "SAS RAND('UNIFORM') → np.random.rand(); use np.random.default_rng for reproducibility"),

    # ── Date/Time functions ───────────────────────────────────────────────────
    "TODAY":       ("pd.Timestamp.today().normalize()",
                    "Returns today's date; SAS returns days since 1960-01-01 — use pd.Timestamp.today()"),
    "DATE":        ("pd.Timestamp.today().normalize()",
                    "Alias for TODAY()"),
    "DATETIME":    ("pd.Timestamp.now()",
                    "Returns current datetime"),
    "TIME":        ("pd.Timestamp.now().time()",
                    "Returns current time as seconds since midnight in SAS; use datetime.now().time()"),
    "YEAR":        (".dt.year",
                    "Extracts year from a SAS date variable — use pandas .dt.year"),
    "MONTH":       (".dt.month",
                    "Extracts month (1-12)"),
    "DAY":         (".dt.day",
                    "Extracts day of month"),
    "HOUR":        (".dt.hour",
                    "Extracts hour"),
    "MINUTE":      (".dt.minute",
                    "Extracts minute"),
    "SECOND":      (".dt.second",
                    "Extracts second"),
    "WEEKDAY":     (".dt.dayofweek + 1",
                    "SAS: 1=Sunday..7=Saturday. pandas: 0=Monday..6=Sunday. Add 1 and adjust."),
    "QTR":         ("((df['date'].dt.month - 1) // 3) + 1",
                    "Quarter number 1-4"),
    "MDY":         ("pd.Timestamp(year=y, month=m, day=d)",
                    "MDY(month, day, year) → pd.Timestamp(year=y, month=m, day=d)"),
    "YMD":         ("pd.Timestamp(year=y, month=m, day=d)",
                    "Alias MDY with different arg order"),
    "HMS":         ("pd.Timedelta(hours=h, minutes=m, seconds=s)",
                    "Creates a time value from hours, minutes, seconds"),
    "DHMS":        ("pd.Timestamp + pd.Timedelta(hours=h, minutes=m, seconds=s)",
                    "Creates datetime from date + time components"),
    "DATEPART":    (".dt.normalize()  /  .dt.date",
                    "Extracts date part from SAS datetime"),
    "TIMEPART":    (".dt.time",
                    "Extracts time part from SAS datetime"),
    "INTCK":       ("(end_date - start_date) / pd.Timedelta('1D') for 'DAY'; use relativedelta for months/years",
                    "INTCK('MONTH',start,end) counts interval boundaries crossed — use relativedelta"),
    "INTNX":       ("start_date + pd.DateOffset(months=n) for 'MONTH'; adjust for alignment",
                    "INTNX('MONTH',date,n,'B') advances n months to beginning; use pd.DateOffset"),
    "DATDIF":      ("(date2 - date1).days",
                    "Difference in days between two SAS dates"),
    "YRDIF":       ("(date2 - date1).days / 365.25",
                    "Approximate years between dates; for AGE use relativedelta"),

    # ── Statistical functions ─────────────────────────────────────────────────
    "PROBIT":      ("scipy.stats.norm.ppf(p)",
                    "Inverse normal CDF (probit)"),
    "PROBNORM":    ("scipy.stats.norm.cdf(x)",
                    "Normal CDF P(Z <= x)"),
    "PROBCHI":     ("scipy.stats.chi2.cdf(x, df)",
                    "Chi-squared CDF"),
    "PROBF":       ("scipy.stats.f.cdf(x, df1, df2)",
                    "F distribution CDF"),
    "PROBT":       ("scipy.stats.t.cdf(x, df)",
                    "Student-t CDF"),
    "TINV":        ("scipy.stats.t.ppf(p, df)",
                    "Inverse t-distribution"),
    "FINV":        ("scipy.stats.f.ppf(p, df1, df2)",
                    "Inverse F-distribution"),
    "CINV":        ("scipy.stats.chi2.ppf(p, df)",
                    "Inverse chi-squared distribution"),

    # ── Utility ───────────────────────────────────────────────────────────────
    "PUT":         ("format() or strftime()",
                    "PUT(var, format.) converts a value to its formatted string; use format() or strftime()"),
    "INPUT":       ("pd.to_numeric() or pd.to_datetime()",
                    "INPUT(var, informat.) reads a string as numeric/date; use pd.to_numeric/to_datetime"),
    "LAG":         (".shift(1)",
                    "LAG(var) returns previous row's value; use df['var'].shift(1). Initialises to NaN."),
    "LAG2":        (".shift(2)",
                    "Two-row lag"),
    "LAG3":        (".shift(3)",
                    "Three-row lag"),
    "DIF":         (".diff(1)",
                    "DIF(var) = var - LAG(var); use .diff(1)"),
    "FIRST":       ("df.groupby(grp).cumcount() == 0",
                    "FIRST.var equivalent: first row in each BY group"),
    "LAST":        ("df.groupby(grp).cumcount(ascending=False) == 0",
                    "LAST.var equivalent: last row in each BY group"),
}

# ── Pattern scanner ───────────────────────────────────────────────────────────

# Build a compiled regex that detects any known SAS function call
_FUNC_NAMES = sorted(_BUILTINS.keys(), key=len, reverse=True)   # longest first
_DETECT_RE  = re.compile(
    r"\b(" + "|".join(re.escape(fn) for fn in _FUNC_NAMES) + r")\s*\(",
    re.IGNORECASE,
)


def get_builtins_hint_block(sas_code: str, max_functions: int = 10) -> str:
    """Scan SAS code for known built-in functions and return a hint block.

    Returns a Markdown block listing Python equivalents for each detected
    function, or empty string if none are found.

    Args:
        sas_code:      SAS source code to scan.
        max_functions: Maximum number of functions to include (most-specific first).
    """
    found: dict[str, tuple[str, str]] = {}
    for m in _DETECT_RE.finditer(sas_code):
        fn_name = m.group(1).upper()
        if fn_name not in found and fn_name in _BUILTINS:
            found[fn_name] = _BUILTINS[fn_name]
        if len(found) >= max_functions:
            break

    if not found:
        return ""

    lines = ["## SAS Built-in Function Reference (apply these equivalents)"]
    for fn_name, (py_equiv, notes) in found.items():
        lines.append(f"- **`{fn_name}()`** → `{py_equiv}`")
        lines.append(f"  _{notes}_")
    return "\n".join(lines)


def lookup(function_name: str) -> Optional[tuple[str, str]]:
    """Look up a single SAS function by name. Returns (python_equiv, notes) or None."""
    return _BUILTINS.get(function_name.upper())
