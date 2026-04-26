"""Translation service — SAS→Python LLM translation logic.

Extracted from api.routes.conversions to keep route handlers free of LLM client code.
Fallback chain: Azure OpenAI → Nemotron (Ollama) → Groq (key rotation).
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path

_log = logging.getLogger("codara.translate")

# ── SAS conversion rules (system prompt) ─────────────────────────────────────

_SAS_CONVERSION_RULES = """
## SAS-to-Python Conversion Rules (MANDATORY)

### 1. LIBNAME References — Dot Notation
- `LIBNAME staging '/path/to/dir';` → IGNORE the LIBNAME declaration itself (no Python equivalent).
- When SAS references `libname.dataset` (e.g., `staging.merged`, `work.output`),
  ONLY use the part AFTER the dot as the DataFrame name.
  - `staging.merged` → `merged` (pandas DataFrame)
  - `work.temp_data` → `temp_data`
  - `sashelp.class` → `class_df` (add `_df` suffix to avoid Python keyword conflicts)
- Never create a variable or object named after the libname itself.

### 2. No-Op SAS Statements → `pass` or omit entirely
These SAS statements have NO Python equivalent. Convert them to a `pass` comment or omit:
- `TITLE` / `TITLE1` / `TITLE2` ... → `print('title text')` — SAS TITLE always produces visible output.
  NEVER convert TITLE to a comment. Use `print()` so the Python output matches SAS stdout.
- `FOOTNOTE` / `FOOTNOTE1` ... → `print('footnote text')` — same reason as TITLE.
- `OPTIONS` (e.g., `OPTIONS NOCENTER NODATE;`) → `# SAS OPTIONS: <ignored>`
- `GOPTIONS` → `# SAS GOPTIONS: <ignored>`
- `ODS` statements (e.g., `ODS HTML`, `ODS LISTING CLOSE`) → `# ODS: <ignored>`
- `DM` (display manager commands) → omit
- `%SYSEXEC` → omit (or `os.system()` if truly needed)
- `ENDSAS;` → omit
- `RUN;` → omit (implicit in Python)
- `QUIT;` → omit

### 3. Variable Naming & Case Sensitivity
- SAS variables are case-insensitive. Python is case-sensitive.
  → Use lowercase_snake_case for all variable names.
- If a SAS variable name is a Python keyword (e.g., `class`, `type`, `input`, `format`),
  append `_col` or `_var` → `class_col`, `type_var`, `input_col`.
- After loading any DataFrame, ALWAYS run `df.columns = df.columns.str.lower()` to normalize
  column names. SAS is case-insensitive; pandas is not. Without this, column access will fail.

### 4. Missing Values
- SAS missing numeric = `.` → Python `np.nan` / `pd.NA`
- SAS missing char = `' '` (blank) → Python `None` or `''`
- SAS comparison with missing: `. < 0` is TRUE in SAS → Use `pd.isna()` checks.
- `NMISS()` → `.isna().sum()`
- `CMISS()` → `.isna().sum()`

### 5. SAS Date Handling
- SAS dates are days since Jan 1, 1960.
- Do NOT manually offset by 3653 days — pandas handles epochs.
- `TODAY()` → `pd.Timestamp.today().normalize()`
- `MDY(m, d, y)` → `pd.Timestamp(year=y, month=m, day=d)`
- `INTNX('MONTH', date, n)` → `date + pd.DateOffset(months=n)`
- `INTCK('DAY', d1, d2)` → `(d2 - d1).days`
- `DATEPART(datetime)` → `datetime.normalize()` or `.dt.date`

### 6. DATA Step → pandas
- `DATA output; SET input;` → `output = input.copy()`
- `DATA output; SET input; WHERE condition;` → `output = input[condition].copy()`
- `DATA output; MERGE a b; BY key;` → `output = pd.merge(a, b, on='key', how='outer')`
- `RETAIN var init;` → Use `.cumsum()`, `.expanding()`, or explicit loop
- `FIRST.var / LAST.var` → Use `groupby().cumcount()` flags
- `OUTPUT;` → `rows.append(...)` then `pd.DataFrame(rows)`
- `IF ... THEN DELETE;` → `df = df[~condition]`
- `LENGTH var $50;` → `df['var'] = df['var'].astype(str)`
- `DATA output; SET a(IN=x) b(IN=y); BY key; IF x AND NOT y;` → anti-join:
  `output = a.merge(b[['key']], on='key', how='left', indicator=True); output = output[output['_merge']=='left_only'].drop('_merge', axis=1)`

### 6b. Data Type & Currency Pre-processing
- SAS informats automatically parse currency strings ($36,945) as numeric.
  Pandas does NOT. Before any numeric computation, strip `$` and `,` then cast:
  `df['col'] = pd.to_numeric(df['col'].astype(str).str.replace(r'[$,]', '', regex=True), errors='coerce')`
  Use raw strings `r'[$,]'` (not `'[$,]'`) to avoid SyntaxWarning in Python 3.12+.
- `INPUT(var, numfmt.)` / `INPUT(var, comma12.)` → same stripping + cast pattern.
- SAS `COMPRESS(var, '$,')` before numeric use → same stripping pattern.
- Never assume a numeric-looking column is actually numeric dtype in pandas — always check.

### 7. PROC Statements → pandas equivalents
- `PROC SORT DATA=ds; BY var;` → `ds = ds.sort_values('var', kind='mergesort')`
  ALWAYS use `kind='mergesort'` for stable sort — pandas default quicksort is unstable
  and may reorder equal-key rows differently than SAS.
- `PROC SORT NODUPKEY;` → `ds = ds.drop_duplicates(subset=['var']).sort_values('var', kind='mergesort')`
- `PROC SORT NODUP; BY _ALL_;` → `ds = ds.drop_duplicates()`
- `PROC SORT ... DUPOUT=dups;` → save removed duplicates: `dups = ds[ds.duplicated(subset=[...], keep='first')]`
- `PROC MEANS` with `CLASS` → use **named aggregation** to avoid fragile column rename lists:
  ```
  grouped = df.groupby([class_vars]).agg(
      AvgQty=('quantity', 'mean'),
      TotalQty=('quantity', 'sum'),
      AvgPrice=('price', 'mean'),
      TotalPrice=('price', 'sum'),
      ...
  )
  ```
  NEVER do `df.groupby().agg({...})` then rename columns by position — the rename list
  is fragile if SAS OUTPUT statement groups stats differently (all means first, then all sums).
  Named aggregation gives correct column names directly.
  **MANDATORY — grand-total row**: SAS PROC MEANS with CLASS ALWAYS outputs a grand-total
  observation (`_TYPE_=0`, `_FREQ_=N`) in addition to per-group rows. You MUST append it.
  This is NOT optional — downstream processes may depend on it. Full pattern:
  ```
  grouped = df.groupby([class_vars]).agg(AvgQty=('quantity', 'mean'), ...)
  # MANDATORY grand-total row (_TYPE_=0)
  totals = {col: df[src].agg(func) for col, (src, func) in agg_dict.items()}
  grand_total = pd.DataFrame([totals])
  grand_total['_TYPE_'] = 0
  grand_total['_FREQ_'] = len(df)
  result = pd.concat([grouped.reset_index(), grand_total], ignore_index=True)
  ```
  If you omit the grand-total row, the output is WRONG and will not match SAS.
  **NWAY keyword**: `PROC MEANS ... NWAY` → output ONLY the full cross-tabulation level.
  Do NOT generate subtotals or grand-total rows when NWAY is present.
  **WAYS n keyword**: `WAYS 2` → output only levels with exactly n active class variables.
  **_TYPE_ is a bitmask**: each CLASS variable = one bit. _TYPE_=0 is grand total,
  _TYPE_=1 is by last class var only, _TYPE_=3 is full cross-tab for 2 class vars.
  **_FREQ_** uses `.size()` (counts ALL rows including missing), NOT `.count()`.
  **std(ddof=1)**: SAS defaults to ddof=1 for standard deviation. pandas defaults to ddof=0.
  ALWAYS use `.std(ddof=1)` to match SAS.
  **maxdec=N**: display-only option → use `.round(N)` in Python.
  **WHERE filter**: apply BEFORE grouping, not after. SAS WHERE subsets input data first.
  **Multiple OUTPUT statements**: SAS allows multiple OUTPUT statements in one PROC MEANS,
  each creating a separate output dataset. Translate each as a separate aggregation.
- `PROC FREQ` → `pd.crosstab()` then **sort columns alphabetically by string value**.
  SAS PROC FREQ orders crosstab columns as alphabetically sorted strings.
  **CRITICAL**: `sorted(ct.columns)` does NOT work on Categorical columns — it sorts by
  category label order (e.g. Low→Medium→High), not alphabetically (High→Low→Medium).
  You MUST use `key=str` to force string-alphabetical sorting:
  ```
  ct = pd.crosstab(df['row_var'], df['col_var'])
  ct = ct.reindex(sorted(ct.columns, key=str), axis=1)
  ```
  WRONG: `ct.reindex(sorted(ct.columns), axis=1)`  — Categorical order, not alphabetical
  RIGHT: `ct.reindex(sorted(ct.columns, key=str), axis=1)` — true alphabetical like SAS
- `PROC PRINT` → `print(df.to_string(index=False))`. `NOOBS` option → `index=False`. `OBS=n` → `.head(n)`.
  `VAR col1 col2;` → select columns. `SUM col1 col2;` → append totals row.
  `FORMAT col1 dollar10.2;` → display-only formatting on print.
- `PROC REPORT` → group + aggregate + **format numbers**.
  Apply `format=comma10.` → `f"{val:,.0f}"`, `format=dollar12.2` → `f"${val:,.2f}"`.
  Use `.style.format(...)` or string formatting for display columns.
- `PROC SQL; SELECT ... FROM ... ;` → direct pandas groupby/merge operations
- `PROC TRANSPOSE` → `df.pivot()` / `df.melt()`
- `PROC EXPORT` → `df.to_csv()` / `df.to_excel()`.
  `DELIMITER=';'` → `sep=';'`. `DBMS=XLSX` → `df.to_excel()`.
- `PROC IMPORT` → `pd.read_csv()` / `pd.read_excel()`. `GUESSINGROWS=MAX` → no equivalent needed.
- `PROC CONTENTS` → `df.info()` / `df.dtypes`
- `PROC REG` → `import statsmodels.api as sm` (at top of file) then `sm.OLS()`
- `PROC LOGISTIC` → `from sklearn.linear_model import LogisticRegression`
- `PROC UNIVARIATE` → full statistical analysis. Rules:
  - Without `NOPRINT`: produce ALL 7 sections: Moments, Basic Stats, Location Tests, Normality Tests, Quantiles, Extremes, Missing Values. Print each section.
  - With `NOPRINT`: compute stats silently, only produce OUTPUT OUT= dataset.
  - `OUTPUT OUT=ds mean=m std=s p1=p1 p5=p5 ...;` → one-row DataFrame with named stats.
  - `CLASS var;` → groupby(var).agg(...) for each group.
  - `WEIGHT var;` → all stats become weighted (weighted mean, weighted variance, etc.).
  - Use `.std(ddof=1)` — SAS defaults to ddof=1.
  - SAS Quantiles: use `np.percentile(method='inverted_cdf')` for closest match.
  - `HISTOGRAM var / normal;` → produces chart (see section 7b).
  - `NORMAL` keyword → add normality tests (Shapiro-Wilk).
- `PROC TABULATE` → `pd.pivot_table()` with margins
- `PROC COMPARE` → `df1.compare(df2)` or `pd.testing.assert_frame_equal()`
- `PROC APPEND BASE=a DATA=b;` → `a = pd.concat([a, b], ignore_index=True)`
- `PROC DATASETS; DELETE ds; RUN;` → `del ds` or omit
- `PROC PRINTTO LOG='file.log';` → redirect stdout: `import sys; sys.stdout = open('file.log', 'w')`

### 7b. SAS Chart Procedures → matplotlib/seaborn + PNG export
SAS chart PROCs (SGPLOT, SGPANEL, GPLOT, GCHART, SGSCATTER, UNIVARIATE HISTOGRAM) MUST produce
**visible chart files**. NEVER comment out chart code or skip it. Every SAS chart → a saved PNG.
Always use `import matplotlib.pyplot as plt` and optionally `import seaborn as sns` (at top of file).
After every chart, call `plt.savefig('chart_name.png', dpi=150, bbox_inches='tight')` then `plt.close()`.

#### PROC SGPLOT chart types:
- `VBAR var;` (no response=) → frequency count: `ax = df['var'].value_counts().plot.bar(); ax.bar_label(ax.containers[0])`
- `VBAR var / response=y datalabel;` → bars from column y: `ax = plt.bar(df['var'], df['y']); ax.bar_label(ax.containers[0])`
- `VBARPARM category=var response=y / datalabel;` → bars from PRE-AGGREGATED data (e.g. PROC FREQ output):
  `ax = plt.bar(df['var'], df['y']); for bar in ax: plt.text(bar.get_x()+bar.get_width()/2, bar.get_height(), f'{bar.get_height():.0f}', ha='center', va='bottom')`
- `HBAR var / response=y datalabel categoryorder=respdesc;` → horizontal bars sorted by response descending:
  `df_sorted = df.sort_values('y', ascending=True); plt.barh(df_sorted['var'], df_sorted['y'])`
- `SCATTER x=a y=b / group=g transparency=0.25;` → colored scatter:
  `for name, grp in df.groupby('g'): plt.scatter(grp['a'], grp['b'], label=name, alpha=0.75); plt.legend()`
- `REG x=a y=b / nomarkers;` → regression line overlay (no scatter points):
  `from numpy.polynomial.polynomial import polyfit; b, m = polyfit(df['a'], df['b'], 1); plt.plot(df['a'].sort_values(), m*df['a'].sort_values()+b, color='black')`
- `SCATTER + REG` combined → scatter with regression line overlay. Both in same figure.
- `SERIES x=a y=b;` → `plt.plot(df['a'], df['b'])`
- `HISTOGRAM var;` → `plt.hist(df['var'], bins='auto', edgecolor='black')`
- `DENSITY var;` → `sns.kdeplot(df['var'])`
- `HEATMAP x=a y=b;` → `sns.heatmap(...)`
- `BOXPLOT category=a response=b;` → `sns.boxplot(x='a', y='b', data=df)`
- `PIE category=a;` → `df['a'].value_counts().plot.pie(autopct='%1.1f%%')`

#### PROC UNIVARIATE with HISTOGRAM:
- `PROC UNIVARIATE; HISTOGRAM var / normal;` → histogram with normal curve overlay:
  ```
  fig, ax = plt.subplots()
  n, bins, patches = ax.hist(df['var'].dropna(), bins='auto', density=True, edgecolor='black')
  from scipy.stats import norm
  mu, sigma = df['var'].mean(), df['var'].std(ddof=1)
  x = np.linspace(bins[0], bins[-1], 100)
  ax.plot(x, norm.pdf(x, mu, sigma), 'r-', linewidth=2)
  plt.savefig('histogram_var.png', dpi=150, bbox_inches='tight')
  plt.close()
  ```

#### PROC SGPANEL:
- `PROC SGPANEL; PANELBY var;` → `g = sns.FacetGrid(df, col='var'); g.map(...); plt.savefig(...)`

#### Legacy chart PROCs:
- `PROC GPLOT; PLOT y*x;` → `plt.plot(df['x'], df['y'])`
- `PROC GCHART; VBAR var;` → same as SGPLOT VBAR
- `PROC SGSCATTER; PLOT y*x;` → `plt.scatter(df['x'], df['y'])`
- `PROC CORR; WITH; PLOTS` → `sns.heatmap(df.corr(), annot=True)`

#### ODS GRAPHICS pattern (all chart cases follow this):
```sas
ods listing gpath="&output_dir";
ods graphics on / reset imagename="chart_name" imagefmt=png;
/* PROC SGPLOT or PROC UNIVARIATE */
ods graphics off;
```
→ The `imagename=` value should be used as the PNG file name in `plt.savefig()`.

#### Chart options:
- `datalabel` → `ax.bar_label(container, padding=3)` — print values on bars
- `dataskin=matte` → `alpha=0.85, edgecolor='none'` (approximate)
- `categoryorder=respdesc` → sort bars by descending response before plotting
- `discreteorder=data` → preserve the data order (don't re-sort alphabetically)
- `GROUP=var` → `hue='var'` in seaborn, or loop-and-color in matplotlib + legend
- `transparency=0.25` → `alpha=0.75` (SAS transparency is opposite of matplotlib alpha)
- `/ nomarkers` on REG → draw regression line only, no point markers
- `/ normal` on HISTOGRAM → overlay `scipy.stats.norm.pdf()` curve
- `XAXIS LABEL='text'` → `plt.xlabel('text')`
- `YAXIS LABEL='text'` → `plt.ylabel('text')`
- TITLE before a chart → `plt.title('title text')` (AND `print('title text')`)
- WHERE= → filter the DataFrame before plotting: `df_sub = df[condition]`
- Multiple plots in one PROC → multiple `plt.savefig()` calls (one per plot statement)
- Chart file names: use the `imagename=` from ODS GRAPHICS, or descriptive name + `.png`
- ALWAYS call `plt.close()` after `plt.savefig()` to avoid memory leaks
- Macro-generated charts (e.g. `%freq_chart` called 3 times) → produce one PNG per call
- `PROC FORMAT` with numeric ranges → `pd.cut()` with **`right=False`**.
  SAS numeric value ranges like `low-1000='Low' 1000-3000='Medium'` are LEFT-EXCLUSIVE
  (the boundary value belongs to the NEXT range). So `1000` → 'Medium', not 'Low'.
  In pandas: `pd.cut(df['col'], bins=[...], labels=[...], right=False, include_lowest=True)`.
  NEVER use `right=True` for SAS format ranges — it flips the boundary assignment.

### 8. Macro Variables
- `%LET var = value;` → `var = 'value'` (or appropriate type)
- `&var` / `&var.` references → Use the Python variable directly (f-string if in text)
- `%MACRO name(...); ... %MEND;` → `def name(...):` — ONLY if the macro is called more than once.
  If called once, expand it inline as top-level statements (no `def`).
- `%IF ... %THEN ... %ELSE ...` → standard Python `if/else`
- `%DO ... %END` → `for` loop
- `%INCLUDE 'file.sas';` → `exec(open('file.py').read())` or `import module`
- `CALL SYMPUT('var', value);` → `var = value` (SAS macro variable → Python variable)
- `%PUT &var;` → `print(var)`
- `RSUBMIT; ... ENDRSUBMIT;` → execute the enclosed code as-is (remote submit = no-op in Python)
- `SWORK.dataset` → same as `WORK.dataset` (remote work library)

### 8b. Enterprise / Database Connectivity
- `LIBNAME lib TERADATA schema=SCHEMA server='srv' user=u pwd=p;` → set up database connection:
  `import teradatasql; conn = teradatasql.connect(host='srv', user='u', password='p')`
- `LIBNAME lib ORACLE path=... user=u pwd=p;` → `import cx_Oracle; conn = cx_Oracle.connect('u/p@path')`
- `SET lib.table (WHERE=(...) KEEP=col1 col2)` with database libname → `pd.read_sql("SELECT col1, col2 FROM schema.table WHERE ...", conn)`
- `PROC SQL; CREATE TABLE x AS SELECT ... FROM lib.table;` with database libname → `pd.read_sql(sql, conn)`
- SAS `DATE()` / `TODAY()` → `datetime.date.today()` or `pd.Timestamp.now()`
- SAS date literal `'01jan2021'd` → `pd.Timestamp('2021-01-01')` or `datetime.datetime(2021, 1, 1)`
- `PROC SURVEYSELECT DATA=ds OUT=samp METHOD=SRS SAMPSIZE=n; STRATA vars / ALLOC=PROPORTIONAL;` →
  stratified sampling: `df.groupby(strata_vars, group_keys=False).apply(lambda x: x.sample(frac=n/len(df)))`
- `PROC EXPORT ... DELIMITER=";";` → `df.to_csv(path, sep=';', index=False)`

### 12. NO Unnecessary `def` Functions
- **Script-level SAS code MUST translate to top-level Python statements** — NOT wrapped in `def main()`,
  `def run()`, `def process()`, or any function. SAS is a script; Python output must also be a script.
- **For IF/ELIF value-mapping chains** (enum code → label), use a dict + `.map()`:
    WRONG: `def map_status(v): if v=='1': return 'Active'; ...` then `df['col'].apply(map_status)`
    RIGHT: `df['status'] = df['STATUS'].map({'1': 'Active', '2': 'Inactive'}).fillna('ERREUR')`
- **For numeric range binning**, use `np.select()` or `pd.cut()`:
    WRONG: `def categorize(v): if v <= 1000: return '[>0;1000]'; ...` then `.apply(categorize)`
    RIGHT: `df['cat'] = np.select([df['v']<=1000, df['v']<=7000], ['[>0;1000]','[>1000;7000]'], default='ERREUR')`
         — or: `df['cat'] = pd.cut(df['v'], bins=[0,1000,7000,float('inf')], labels=['[>0;1000]','[>1000;7000]','>7000'], right=True)`
- **`def` is ONLY correct for** a `%MACRO` called 2+ times. Everything else: top-level statements.

### 9. SAS Functions → Python/pandas
- `INPUT(var, numfmt.)` → `pd.to_numeric(var)`
- `PUT(var, charfmt.)` → `str(var)` or `.astype(str)`
- `SUBSTR(str, pos, len)` → `str[pos-1:pos-1+len]` (SAS is 1-indexed!)
- `SCAN(str, n, delim)` → `str.split(delim)[n-1]`
- `COMPRESS(str)` → `str.replace(' ', '')`
- `STRIP(str)` / `TRIM(str)` → `str.strip()`
- `UPCASE(str)` → `str.upper()`
- `LOWCASE(str)` → `str.lower()`
- `PROPCASE(str)` → `str.title()`
- `CATX(delim, ...)` → `delim.join([...])`
- `CATS(...)` → `''.join([str(x).strip() for x in [...]])`
- `SUM(a, b, ...)` → `np.nansum([a, b, ...])` (SAS SUM ignores missing!)
- `MEAN(a, b)` → `np.nanmean([a, b])`
- `MIN(a, b)` / `MAX(a, b)` → `np.nanmin()` / `np.nanmax()`
- `LAG(var)` → `df['var'].shift(1)`
- `LAG2(var)` → `df['var'].shift(2)`
- `ABS(x)` → `abs(x)`
- `ROUND(x, r)` → `round(x, -int(np.log10(r)))` or custom
- `INT(x)` → `int(x)` or `np.floor(x)`
- `LOG(x)` → `np.log(x)`
- `EXP(x)` → `np.exp(x)`

### 10. SAS Formats & Informats → Ignore or Comment
- `FORMAT var date9.;` → `# FORMAT: date9. applied to var`
- `INFORMAT var ...;` → Ignore (informats are read-time only)
- `LABEL var = 'description';` → `# LABEL: var = 'description'` (comment only)
- `ATTRIB` statements → comment only

### 11. Output Delivery
- `PROC EXPORT DATA=ds OUTFILE='file.csv' DBMS=CSV;` → `ds.to_csv('file.csv', index=False)`
- `FILE 'output.txt';` / `PUT ...;` → `with open('output.txt', 'w') as f: f.write(...)`
"""


def _strip_markdown_fences(code: str) -> str:
    """Remove markdown code fences if the LLM wraps the output."""
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        lines = lines[1:]  # remove opening fence line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)
    return code


def _auto_repair(code: str) -> str:
    """Fix common LLM output syntax errors that prevent compile().

    Catches placeholder tokens, stray arrows, broken brackets, and other
    patterns that LLMs inject instead of real Python.
    """
    # [←NULL_ equivalent] / [← ... ] / [→ ... ] — LLM annotation brackets
    code = re.sub(r"\[←[^\]]*\]", "None", code)
    code = re.sub(r"\[→[^\]]*\]", "None", code)

    # <PLACEHOLDER>, <<FILL>>, «...» — angle-bracket placeholders
    code = re.sub(r"<<[^>]*>>", "None", code)
    code = re.sub(r"«[^»]*»", "None", code)

    # ... (rest of code) / ... (remaining logic) — ellipsis placeholders
    code = re.sub(r"#\s*\.\.\.\s*\(.*?\)", "pass", code)
    code = re.sub(r"^\s*\.\.\.\s*\(.*?\)\s*$", "    pass", code, flags=re.MULTILINE)

    # Bare `...` on a line (Ellipsis literal is valid Python but usually a stub)
    # Only replace if inside a function/class body (preceded by def/class)

    # Remove stray SAS semicolons at end of lines
    code = re.sub(r";\s*$", "", code, flags=re.MULTILINE)

    # Fix common `pd.merge` issues: ensure how= parameter is valid
    code = re.sub(r"how\s*=\s*['\"]inner_left['\"]", "how='left'", code)
    code = re.sub(r"how\s*=\s*['\"]outer_left['\"]", "how='left'", code)

    # Ensure charts save to PNG, not just plt.show()
    # Replace plt.show() with plt.savefig() + plt.close() if no savefig nearby
    if "plt.show()" in code and "plt.savefig(" not in code:
        _chart_n = [0]

        def _replace_show(m):
            _chart_n[0] += 1
            indent = m.group(1)
            return (
                f"{indent}plt.savefig('chart_{_chart_n[0]}.png', dpi=150, bbox_inches='tight')\n"
                f"{indent}plt.close()"
            )

        code = re.sub(r"^(\s*)plt\.show\(\)", _replace_show, code, flags=re.MULTILINE)

    # Fix PROC FREQ crosstab column sorting: sorted(X.columns) on Categoricals
    # sorts by label order, not alphabetically. Force string-based sort.
    code = re.sub(
        r"sorted\((\w+)\.columns\)",
        r"sorted(\1.columns.astype(str))",
        code,
    )
    code = re.sub(
        r"sorted\((\w+)\.columns,\s*key\s*=\s*str\)",
        r"sorted(\1.columns.astype(str))",
        code,
    )

    # Convert # TITLE: / # FOOTNOTE: comments to print() calls
    # SAS TITLE/FOOTNOTE produce visible output — comments are wrong
    code = re.sub(
        r"^(\s*)#\s*TITLE\d*:\s*(.+)$",
        r'\1print("\2")',
        code,
        flags=re.MULTILINE,
    )
    code = re.sub(
        r"^(\s*)#\s*FOOTNOTE\d*:\s*(.+)$",
        r'\1print("\2")',
        code,
        flags=re.MULTILINE,
    )

    # Remove lines that are just LLM commentary (not comments)
    lines = code.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Note:") or stripped.startswith("NOTE:"):
            cleaned.append(f"# {stripped}")
        elif stripped.startswith("/*") or stripped.endswith("*/"):
            cleaned.append(f"# {stripped}")
        else:
            cleaned.append(line)
    code = "\n".join(cleaned)

    return code


def translate_sas_to_python(sas_code: str) -> str:
    """Translate SAS code to Python via Nemotron (primary) with Azure/Groq fallbacks.

    Uses the PromptManager Jinja2 templates when available, falls back to the
    comprehensive rules-based system prompt otherwise.
    Returns translated Python code, or a stub comment if no LLM is configured.

    Fallback chain: Nemotron (Ollama) → Azure OpenAI → Groq (key rotation) → stub.
    """
    from config.constants import (
        AZURE_MAX_COMPLETION_TOKENS,
        GROQ_MAX_TOKENS,
        LLM_TRANSLATION_TEMPERATURE,
    )
    from config.settings import settings

    # Ensure backend package is on sys.path for partition imports
    pkg_root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    # Detect failure modes for smarter prompts
    failure_guidance = ""
    try:
        from partition.translation.failure_mode_detector import (
            detect_failure_mode,
            get_failure_mode_rules,
        )

        fm = detect_failure_mode(sas_code)
        if fm:
            failure_guidance = get_failure_mode_rules(fm)
    except Exception:
        pass

    target_label = "Python (pandas)"

    # Try to use the PromptManager with Jinja2 templates
    rendered_prompt = None
    try:
        from partition.prompts import PromptManager

        pm = PromptManager()
        rendered_prompt = pm.render(
            "translation_static",
            target_label=target_label,
            partition_type="FULL_FILE",
            risk_level="MODERATE",
            complexity=0.5,
            sas_code=sas_code,
            failure_mode_rules=failure_guidance,
            kb_examples=[],
        )
    except Exception:
        pass

    system_prompt = (
        f"You are an expert SAS-to-{target_label} code translator.\n\n"
        "## #1 GOAL: EXACT OUTPUT EQUIVALENCE\n"
        "The Python script MUST produce THE EXACT SAME OUTPUT as the SAS program.\n"
        "- Same DataFrame values, same rows, same columns, same ordering.\n"
        "- If SAS writes a CSV, the Python CSV must have identical content.\n"
        "- If SAS prints a table with FORMAT dollar12.2, the Python print must show '$3,306.00' — not '3306.0'.\n"
        "- If PROC MEANS has a CLASS statement, the Python MUST include a grand-total row (_TYPE_=0, _FREQ_=N). "
        "This row is ALWAYS present in SAS output. Omitting it means the output does NOT match SAS.\n"
        "- If PROC FORMAT assigns value 1000 to 'Medium', the Python must assign 1000 to 'Medium' — not 'Low'.\n"
        "- PROC FREQ crosstab columns must be sorted alphabetically BY STRING (`sorted(cols, key=str)`), "
        "not by Categorical label order. SAS: High|Low|Medium. Wrong: Low|Medium|High.\n"
        "- Every printed line, every exported file, every DataFrame shape must match SAS output exactly.\n"
        "THIS IS THE SINGLE MOST IMPORTANT RULE. All other rules serve this goal.\n\n"
        f"{_SAS_CONVERSION_RULES}\n\n"
        "Return ONLY valid, executable Python code. No explanations, no markdown fences, no commentary.\n\n"
        "CRITICAL RULES:\n"
        "- You MUST translate EVERY section, macro, data step, and proc in the SAS code.\n"
        "- NEVER use placeholders like '# ... (rest of the code remains the same)' or '# TODO'.\n"
        "- NEVER skip, abbreviate, or summarize any part of the code.\n"
        "- If the SAS code has 14 sections, your Python output MUST have all 14 sections fully implemented.\n"
        "- DO NOT wrap output in `def main()`, `def run()`, or any function — produce a flat script.\n"
        "- DO NOT use `def` helper functions for IF/ELIF value-mapping; use dict+`.map()` or `np.select()` instead.\n"
        "- `def` is ONLY acceptable when translating a `%MACRO` that is called more than once.\n"
        "- Translate ALL macros to Python functions with complete logic (only if called 2+ times; otherwise inline).\n"
        "- Translate ALL PROC SQL to pandas operations or raw SQL equivalents.\n"
        "- Translate ALL DATA steps to pandas DataFrame operations.\n"
        "- The output must be a complete, runnable Python script — no stubs, no omissions.\n\n"
        "SYNTAX RULES (MANDATORY):\n"
        "- NEVER output placeholder tokens like [←NULL_ equivalent], [→...], <<FILL>>, or any bracket notation that is not valid Python.\n"
        "- For SAS missing values (.), ALWAYS use `np.nan` — never invent placeholder syntax.\n"
        "- For SAS MERGE with `IF a;`, use `pd.merge(a, b, on=key, how='left')` — this keeps all rows from `a` (both matched and left_only).\n"
        "- Every variable you reference MUST be defined earlier in the script. Do not reference columns that don't exist.\n"
        "- After PROC MEANS / PROC SUMMARY, the output column for SUM is named with the original variable name by default, not 'sum'.\n"
        "- After `pd.merge()` with `indicator=True`, `_merge` values are 'both', 'left_only', 'right_only' — use them correctly.\n"
        "- The output MUST pass `compile(code, '<translated>', 'exec')` without SyntaxError.\n\n"
        "SEMANTIC RULES (MANDATORY):\n"
        "- EXECUTION ORDER: SAS runs top-to-bottom. If a macro is DEFINED early but CALLED later, "
        "the `def` must appear before any code that uses its output. If step N references a DataFrame "
        "populated by step M (where M > N), you MUST reorder: call the function/step that populates it FIRST, "
        "then run the step that consumes it. Produce correct execution order even if the SAS source has a latent ordering bug.\n"
        "- COLUMN CONSISTENCY: In PROC SQL SELECT, note exactly which columns are selected. "
        "Downstream steps (PROC REG, DATA steps) may ONLY reference columns that exist in the output. "
        "If the SAS code references a column not in the SELECT list, add it to the SELECT or use the correct column name.\n"
        "- PROC REG / MODEL: The variable names in MODEL must match actual columns in the input DataFrame. "
        "If the PROC SQL selected `region` (not `region_code`), use `region` in the MODEL statement. "
        "Encode categorical columns with `pd.factorize()` or `.cat.codes` before using in regression.\n"
        "- FORMAT is display-only in SAS. Apply FORMAT mapping (e.g. `status_fmt`) ONCE, at the final step "
        "where the DataFrame is used — never in multiple steps.\n"
        "- DATE PARSING: Prefer named datetime methods over substring slicing. "
        "Instead of `process_date[2:5]` use `ts.strftime('%b').upper()` and `str(ts.year)`. "
        "This avoids off-by-one errors if the day field is single-digit.\n\n"
        "CODE QUALITY RULES (MANDATORY):\n"
        "- ALL IMPORTS AT THE TOP: Every `import` statement must be at the top of the file. "
        "NEVER put `import` inside a loop, inside a function, or inside a conditional. "
        "This includes `import statsmodels.api as sm`, `from sklearn...`, etc.\n"
        "- ONLY IMPORT WHAT YOU USE: Do not import modules that are never referenced in the code. "
        "If you don't use `re`, don't import it. If you don't use `scipy`, don't import it.\n"
        "- NO REDUNDANT FILTERS: When using `pd.merge(..., how='left')`, the result already contains "
        "only left-side rows (plus matches). Do NOT add a redundant `.isin(['both', 'left_only'])` filter — "
        "it's always True and adds confusion. Just use `how='left'` and drop the `_merge` column after.\n"
        "- NO DEAD CODE: Do not include variables that are assigned but never used. "
        "Do not include conditional branches that can never execute.\n"
        "- USE DIRECT COLUMN ACCESS: Use `df['col']` not `df.get('col')` when you know the column exists. "
        "Use `df.get('col')` only when the column might not exist and you want None fallback.\n"
        "- NEVER SWALLOW EXCEPTIONS SILENTLY: Never use bare `except: pass` or `except Exception: pass` "
        "around file I/O (CSV export, file writes). If the SAS code has `PROC EXPORT` or `FILE` output, "
        "the Python must propagate the error or at minimum print a warning: "
        "`except Exception as e: print(f'Export failed: {e}')`. Silent `except: pass` hides bugs.\n"
        "- PROC FREQ COLUMN ORDER: When using `pd.crosstab()`, always sort the result columns "
        "alphabetically by STRING value with `ct = ct.reindex(sorted(ct.columns, key=str), axis=1)`. "
        "NEVER use `sorted(ct.columns)` without `key=str` — on Categorical columns it sorts by "
        "category order (Low→Medium→High), not alphabetically (High→Low→Medium) like SAS."
    )

    if failure_guidance:
        system_prompt += f"\n\n## Detected Failure Mode\n{failure_guidance}"

    user_prompt = rendered_prompt or (
        f"Convert this SAS code to {target_label}:\n```sas\n{sas_code}\n```"
    )

    # --- Try Azure OpenAI (primary) ---
    azure_key = settings.azure_openai_api_key
    azure_endpoint = settings.azure_openai_endpoint
    if azure_key and azure_endpoint:
        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=azure_key,
                api_version=settings.azure_openai_api_version,
            )
            resp = client.chat.completions.create(
                model=settings.azure_openai_deployment_mini,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=LLM_TRANSLATION_TEMPERATURE,
                max_completion_tokens=AZURE_MAX_COMPLETION_TOKENS,
            )
            code = resp.choices[0].message.content or ""
            code = _strip_markdown_fences(code).strip()
            code = _auto_repair(code)
            return code
        except Exception as exc:
            _log.warning("azure_openai_failed type=%s error=%s", type(exc).__name__, exc)

    # --- Try Nemotron via Ollama (fallback 1) ---
    if settings.ollama_base_url:
        try:
            from openai import OpenAI

            nem_client = OpenAI(
                api_key=settings.ollama_api_key or "ollama",
                base_url=settings.ollama_base_url,
            )
            resp = nem_client.chat.completions.create(
                model=settings.ollama_model or "nemotron-3-super:cloud",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=LLM_TRANSLATION_TEMPERATURE,
                max_tokens=AZURE_MAX_COMPLETION_TOKENS,
            )
            code = resp.choices[0].message.content or ""
            code = _strip_markdown_fences(code).strip()
            code = _auto_repair(code)
            return code
        except Exception as exc:
            _log.warning("nemotron_failed type=%s error=%s", type(exc).__name__, exc)

    # --- Try Groq (fallback 2, key rotation: GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3) ---
    try:
        from partition.utils.llm_clients import get_all_groq_keys

        groq_keys = get_all_groq_keys()
    except Exception:
        groq_keys = [
            k
            for k in [
                settings.groq_api_key,
                settings.groq_api_key_2,
                settings.groq_api_key_3,
            ]
            if k
        ]

    last_groq_exc = None
    for groq_key in groq_keys:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
            resp = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=LLM_TRANSLATION_TEMPERATURE,
                max_tokens=GROQ_MAX_TOKENS,
            )
            code = resp.choices[0].message.content or ""
            code = _strip_markdown_fences(code).strip()
            code = _auto_repair(code)
            return code
        except Exception as exc:
            err_str = str(exc).lower()
            if "rate_limit" in err_str or "429" in err_str or "tokens per day" in err_str:
                _log.warning("groq_key_rate_limited error=%s", str(exc)[:120])
                last_groq_exc = exc
                continue
            _log.warning("groq_failed type=%s error=%s", type(exc).__name__, exc)
            last_groq_exc = exc
            break

    if last_groq_exc:
        _log.warning("groq_all_keys_exhausted error=%s", str(last_groq_exc)[:120])

    # --- No LLM available ---
    _log.error("all_llm_providers_failed sas_len=%d", len(sas_code))
    commented = "\n".join(f"# {line}" for line in sas_code.split("\n"))
    return (
        "# TRANSLATION UNAVAILABLE — no LLM API key configured\n"
        "# Configure AZURE_OPENAI_API_KEY or GROQ_API_KEY in .env\n"
        "#\n"
        "# Original SAS code:\n" + commented
    )
