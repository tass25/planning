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
    SORT_DIRECTION = "SORT_DIRECTION"
    PROC_FORMAT = "PROC_FORMAT"
    COMPRESS_FUNCTION = "COMPRESS_FUNCTION"
    PROC_REG_STEPWISE = "PROC_REG_STEPWISE"


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
    (FailureMode.SORT_DIRECTION, [
        re.compile(r'\bBY\b.*\bDESCENDING\b', re.IGNORECASE),
        re.compile(r'\bPROC\s+SORT\b.*\bDESCENDING\b', re.IGNORECASE | re.DOTALL),
    ]),
    (FailureMode.PROC_FORMAT, [
        re.compile(r'\bPROC\s+FORMAT\b', re.IGNORECASE),
        re.compile(r'\bFORMAT\s+\w+\s+\$?\w+\.\s*;', re.IGNORECASE),
    ]),
    (FailureMode.COMPRESS_FUNCTION, [
        re.compile(r'\bCOMPRESS\s*\(', re.IGNORECASE),
    ]),
    (FailureMode.PROC_REG_STEPWISE, [
        re.compile(r'PROC\s+REG\b.*SELECTION\s*=\s*STEPWISE', re.IGNORECASE | re.DOTALL),
        re.compile(r'PROC\s+REG\b.*SELECTION\s*=\s*(FORWARD|BACKWARD)', re.IGNORECASE | re.DOTALL),
    ]),
]


def detect_failure_mode(source_code: str) -> Optional[FailureMode]:
    """Detect the primary (first matching) failure mode in a SAS code block."""
    for mode, patterns in DETECTION_RULES:
        for pattern in patterns:
            if pattern.search(source_code):
                return mode
    return None


def detect_all_failure_modes(source_code: str) -> list[FailureMode]:
    """Detect ALL failure modes present in a SAS code block."""
    found: list[FailureMode] = []
    for mode, patterns in DETECTION_RULES:
        for pattern in patterns:
            if pattern.search(source_code):
                found.append(mode)
                break  # one match per mode is enough
    return found


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
- SAS MERGE with BY is sequential (like a zipper), NOT a hash join.
- Use pd.merge(how='left') to match SAS MERGE + IF a; (keep all primary records).
- Use pd.merge(how='outer') for SAS MERGE without IN= subsetting.
- Many-to-many: verify unique keys or use groupby first to avoid Cartesian explosion.
- IN= variables: use indicator=True ONLY in DATA STEP MERGE translations, never in PROC SQL joins.
  PROC SQL LEFT JOIN has no IN= — do NOT add indicator=True there.
  After using indicator=True in a MERGE, always drop the _merge column before returning.
- COLUMN NAME CASE — this is the #1 runtime crash cause:
  SAS is case-insensitive for variable names; Python is NOT.
  Before EVERY merge/join, normalize the key columns to the same case on BOTH sides:
    df_a.columns = df_a.columns.str.lower()
    df_b.columns = df_b.columns.str.lower()
  OR use explicit left_on/right_on if datasets come from different sources with different
  naming conventions (e.g., one from groupby→lowercase, one from hardcoded→mixed case).
  NEVER assume column names match without verifying both DataFrames.
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
- OUTPUT OUT= creates ONE dataset with all statistics in the same row per class group.
- Use a SINGLE groupby().agg() call with ALL required statistics — do NOT merge separate groupby results.
  WRONG: merge( groupby(class).mean(), groupby(region).sum() ) → duplicates sum across sub-groups.
  RIGHT: groupby(class_vars, dropna=False).agg(
             avg_balance=('var','mean'), N=('var','count'), total_regional_val=('var','sum'), ...
         ).reset_index()
- Always use dropna=False in groupby to preserve NaN groups (SAS CLASS includes missing).
- Map statistic names: MEAN→'mean', STD→'std', MIN→'min', MAX→'max', N→'count', SUM→'sum'
- NWAY option: means "output only the full cross-classification level" — it is the DEFAULT pandas
  groupby behavior. Do NOT add .dropna() to simulate NWAY. NWAY does NOT filter anything.
  The pandas groupby on all CLASS variables already produces the NWAY-equivalent output.
""",
        FailureMode.SORT_DIRECTION: """
CRITICAL SORT DIRECTION RULES:
- SAS `BY a DESCENDING b` means: a is ASCENDING, b is DESCENDING.
  → df.sort_values(['a', 'b'], ascending=[True, False])
- SAS `BY DESCENDING a b` means: a is DESCENDING, b is ASCENDING.
  → df.sort_values(['a', 'b'], ascending=[False, True])
- `BY DESCENDING a DESCENDING b` → ascending=[False, False]
- The default in SAS is ascending; DESCENDING only applies to the immediately following variable.
- In PROC SORT: `by a descending b;` → sort a ascending, b descending.
""",
        FailureMode.PROC_FORMAT: """
CRITICAL PROC FORMAT RULES:
- SAS FORMAT is DISPLAY-ONLY — it never modifies the underlying data values.
- NEVER overwrite the source column with formatted values.
  WRONG: df['status'] = df['status'].map(fmt_dict)  ← destroys 'ACTIVE', 'OVERDRAWN' etc.
  RIGHT: df['status_fmt'] = df['status'].map(fmt_dict).fillna('Other')
- Create a NEW column (e.g. status_label, status_color, status_display) for formatted output.
- Downstream logic (PROC FREQ, regression, WHERE clauses) must still use the ORIGINAL column.
""",
        FailureMode.COMPRESS_FUNCTION: """
CRITICAL COMPRESS FUNCTION RULES:
- SAS COMPRESS(str) — ONE argument: removes ALL characters that are not letters, digits,
  or underscore. Default removes spaces AND special characters.
  → import re; re.sub(r'[^a-zA-Z0-9_]', '', value)
- SAS COMPRESS(str, chars) — TWO arguments: removes ONLY the listed characters.
  → re.sub(f'[{re.escape(chars)}]', '', value)
  e.g. COMPRESS(x, '-') removes only hyphens → x.replace('-', '')
- SAS COMPRESS(str, chars, modifiers):
  'a' modifier — keep only alphabetic: re.sub(r'[^a-zA-Z]', '', value)
  'd' modifier — remove digits: re.sub(r'\d', '', value)
  'p' modifier — remove punctuation: re.sub(r'[^\w\s]', '', value)
- ALWAYS check how many arguments are in the SAS COMPRESS call before translating.
  str.strip() and str.replace(x,'') are NOT general COMPRESS equivalents.
""",
        FailureMode.PROC_REG_STEPWISE: """
CRITICAL PROC REG STEPWISE RULES:
- SAS PROC REG SELECTION=STEPWISE uses F-STATISTICS with p-value thresholds, NOT BIC/AIC.
  Default thresholds: SLE (entry) = 0.15, SLS (removal) = 0.15.
- EXACT algorithm — copy this pattern precisely:

    def stepwise_selection(X, y, sle=0.15, sls=0.15):
        import statsmodels.api as sm
        included = []
        while True:
            changed = False
            # Forward step: try adding each excluded variable
            excluded = [c for c in X.columns if c not in included]
            pvals = {}
            for col in excluded:
                model = sm.OLS(y, sm.add_constant(X[included + [col]])).fit()
                pvals[col] = model.pvalues[col]
            best = min(pvals, key=pvals.get) if pvals else None
            if best and pvals[best] <= sle:
                included.append(best)
                changed = True
            # Backward step: ONLY run after a successful forward addition (guard with 'if changed')
            # Running backward unconditionally can cause infinite oscillation.
            if changed and included:
                model = sm.OLS(y, sm.add_constant(X[included])).fit()
                worst = model.pvalues[included].idxmax()
                if model.pvalues[worst] >= sls:
                    included.remove(worst)
                    # Do NOT set changed=True here — SAS resolves in a single pass per iteration
            if not changed:
                break
        return included

- Do NOT use BIC, AIC, or sklearn for SAS PROC REG STEPWISE equivalence.
- For categorical predictors, use pd.get_dummies(); fit the FINAL model on the SAME
  dummy-encoded X used during selection (not formula API with string categories).
""",
    }
    return _RULES.get(mode, "")


def get_combined_failure_mode_rules(source_code: str) -> str:
    """Detect all failure modes and return their concatenated rules.

    Returns an empty string if no failure modes are detected.
    """
    modes = detect_all_failure_modes(source_code)
    if not modes:
        return ""
    sections = [get_failure_mode_rules(m) for m in modes]
    return "\n".join(s for s in sections if s)
