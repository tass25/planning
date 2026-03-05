"""Rule-based failure mode detection for SAS partitions.

6 failure modes from cahier §5.2.
Returns the detected failure mode (if any) so the translation prompt
can inject failure-mode-specific rules.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class FailureMode(str, Enum):
    RETAIN = "RETAIN"
    FIRST_LAST = "FIRST_LAST"
    DATE_ARITHMETIC = "DATE_ARITHMETIC"
    MERGE_SEMANTICS = "MERGE_SEMANTICS"
    MISSING_VALUE_COMPARISON = "MISSING_VALUE_COMPARISON"
    PROC_MEANS_OUTPUT = "PROC_MEANS_OUTPUT"


# Patterns applied to source_code (case-insensitive)
DETECTION_RULES: list[tuple[FailureMode, list[re.Pattern]]] = [
    (FailureMode.RETAIN, [
        re.compile(r'\bRETAIN\b', re.IGNORECASE),
    ]),
    (FailureMode.FIRST_LAST, [
        re.compile(r'\bFIRST\.\w+', re.IGNORECASE),
        re.compile(r'\bLAST\.\w+', re.IGNORECASE),
    ]),
    (FailureMode.DATE_ARITHMETIC, [
        re.compile(r'\b(INTNX|INTCK|MDY|TODAY\(\)|DATEPART)\b', re.IGNORECASE),
    ]),
    (FailureMode.MERGE_SEMANTICS, [
        re.compile(r'\bMERGE\b.*\bBY\b', re.IGNORECASE | re.DOTALL),
    ]),
    (FailureMode.MISSING_VALUE_COMPARISON, [
        re.compile(r'\b(NMISS|CMISS)\b', re.IGNORECASE),
        re.compile(r'\.[\s]*[<>=]', re.IGNORECASE),
    ]),
    (FailureMode.PROC_MEANS_OUTPUT, [
        re.compile(
            r'PROC\s+MEANS\b.*OUTPUT\s+OUT\s*=', re.IGNORECASE | re.DOTALL
        ),
    ]),
]


def detect_failure_mode(source_code: str) -> Optional[FailureMode]:
    """Detect the primary failure mode in a SAS code block.

    Returns the first matching failure mode, or None if no special
    pattern is detected.
    """
    for mode, patterns in DETECTION_RULES:
        for pattern in patterns:
            if pattern.search(source_code):
                return mode
    return None


def get_failure_mode_rules(mode: FailureMode) -> str:
    """Return failure-mode-specific translation rules for the prompt."""
    _RULES = {
        FailureMode.DATE_ARITHMETIC: """
CRITICAL DATE RULES:
- SAS dates count from Jan 1, 1960. Python dates use Jan 1, 1970.
- Do NOT add/subtract 3653 days manually — pandas handles epoch internally.
- Use pd.to_datetime() for date parsing.
- INTNX('MONTH', date, 1) → date + pd.DateOffset(months=1)
- INTCK('DAY', date1, date2) → (date2 - date1).days
- MDY(m, d, y) → pd.Timestamp(year=y, month=m, day=d)
- TODAY() → pd.Timestamp.today()
""",
        FailureMode.MERGE_SEMANTICS: """
CRITICAL MERGE RULES:
- SAS MERGE with BY is sequential (like a zipper), NOT a Cartesian product.
- pd.merge(how='inner') for matching rows; how='outer' for SAS MERGE behavior.
- Many-to-many: SAS handles differently than pandas — use merge_asof() or explicit loop.
- Always verify row counts after merge to detect Cartesian explosion.
""",
        FailureMode.RETAIN: """
CRITICAL RETAIN RULES:
- SAS RETAIN preserves a variable's value across DATA step iterations.
- In pandas: use cumsum(), expanding(), or explicit loops.
- Do NOT use df['col'].shift() as a general RETAIN replacement.
- For running totals: df['running'] = df['value'].cumsum()
- For conditional retain: iterate with iloc or use groupby().transform().
""",
        FailureMode.FIRST_LAST: """
CRITICAL FIRST./LAST. RULES:
- SAS FIRST.var = 1 when current row is first in BY group.
- SAS LAST.var = 1 when current row is last in BY group.
- pandas: df['first_flag'] = df.groupby('var').cumcount() == 0
- pandas: df['last_flag'] = df.groupby('var').cumcount(ascending=False) == 0
- Data MUST be sorted by the BY variable(s) first.
""",
        FailureMode.MISSING_VALUE_COMPARISON: """
CRITICAL MISSING VALUE RULES:
- SAS treats missing numeric (.) as -infinity in comparisons.
- Python/pandas NaN: x < NaN is False, x > NaN is False.
- Use pd.isna() / pd.notna() for explicit checks.
- Replace SAS . comparisons: if x = . → if pd.isna(x)
- NMISS → df.isna().sum(), CMISS → df.isna().sum() (for char vars)
""",
        FailureMode.PROC_MEANS_OUTPUT: """
CRITICAL PROC MEANS OUTPUT RULES:
- OUTPUT OUT= creates a dataset with _TYPE_, _FREQ_, and statistic columns.
- pandas: df.groupby(class_vars).agg({var: [stat]}).reset_index()
- NWAY: only the full cross-classification row (_TYPE_ = max).
- Map statistic names: MEAN→'mean', STD→'std', MIN→'min', MAX→'max', N→'count'
""",
    }
    return _RULES.get(mode, "")
