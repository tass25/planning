"""seed_kb.py — Bootstrap the LanceDB Knowledge Base with verified SAS→Python pairs.

Inserts ~35 hand-crafted pairs covering all 8 Z3 verification patterns plus the
most common SAS constructs encountered in enterprise migration projects.
No LLM calls needed — embeddings are generated via NomicEmbedder (local CPU).

Usage:
    cd backend
    python scripts/kb/seed_kb.py            # append to existing KB
    python scripts/kb/seed_kb.py --clear    # wipe table and re-seed
    python scripts/kb/seed_kb.py --stats    # show coverage stats only
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
BACKEND_DIR = _HERE
while not (BACKEND_DIR / "partition").exists():
    BACKEND_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

import structlog
from dotenv import load_dotenv
load_dotenv(BACKEND_DIR.parent / ".env")

from partition.raptor.embedder import NomicEmbedder
from partition.kb.kb_writer import KBWriter

logger = structlog.get_logger()


# ── Seed pairs ────────────────────────────────────────────────────────────────
# Each dict: sas_code, python_code, category, complexity_tier, partition_type,
#            failure_mode (may be empty), notes

SEED_PAIRS = [

    # ── P1: Conditional assignment — IF/THEN/ELSE → np.select ────────────────
    {
        "category": "CONDITIONAL_ASSIGNMENT",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "CONDITIONAL_ASSIGNMENT",
        "sas_code": """\
DATA work.classified;
    SET raw.accounts;
    IF balance < 0 THEN status = 'OVERDRAWN';
    ELSE IF balance = 0 THEN status = 'EMPTY';
    ELSE status = 'ACTIVE';
RUN;""",
        "python_code": """\
import numpy as np
import pandas as pd

df = raw_accounts.copy()
df['status'] = np.select(
    [df['balance'] < 0, df['balance'] == 0],
    ['OVERDRAWN', 'EMPTY'],
    default='ACTIVE'
)""",
    },
    {
        "category": "CONDITIONAL_ASSIGNMENT",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "CONDITIONAL_ASSIGNMENT",
        "sas_code": """\
DATA work.risk_flags;
    SET raw.trades;
    IF amount > 100000 THEN risk_tier = 'HIGH';
    ELSE IF amount > 10000 THEN risk_tier = 'MEDIUM';
    ELSE risk_tier = 'LOW';
    IF amount < 0 THEN flag = 1;
    ELSE flag = 0;
RUN;""",
        "python_code": """\
import numpy as np
import pandas as pd

df = raw_trades.copy()
df['risk_tier'] = np.select(
    [df['amount'] > 100000, df['amount'] > 10000],
    ['HIGH', 'MEDIUM'],
    default='LOW'
)
df['flag'] = np.where(df['amount'] < 0, 1, 0)""",
    },
    {
        "category": "CONDITIONAL_ASSIGNMENT",
        "partition_type": "DATA_STEP",
        "complexity_tier": "MODERATE",
        "failure_mode": "CONDITIONAL_ASSIGNMENT",
        "sas_code": """\
DATA work.scored;
    SET raw.customers;
    IF age < 18 THEN age_group = 'MINOR';
    ELSE IF age < 35 THEN age_group = 'YOUNG_ADULT';
    ELSE IF age < 60 THEN age_group = 'ADULT';
    ELSE age_group = 'SENIOR';
    dormant_flag = (days_inactive > 365);
RUN;""",
        "python_code": """\
import numpy as np
import pandas as pd

df = raw_customers.copy()
df['age_group'] = np.select(
    [df['age'] < 18, df['age'] < 35, df['age'] < 60],
    ['MINOR', 'YOUNG_ADULT', 'ADULT'],
    default='SENIOR'
)
df['dormant_flag'] = (df['days_inactive'] > 365).astype(int)""",
    },

    # ── P2: Sort direction — BY ... DESCENDING ────────────────────────────────
    {
        "category": "SORT_DIRECTION",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "LOW",
        "failure_mode": "SORT_DIRECTION",
        "sas_code": """\
PROC SORT DATA=work.transactions;
    BY customer_id DESCENDING transaction_date;
RUN;""",
        "python_code": """\
import pandas as pd

df = df.sort_values(
    ['customer_id', 'transaction_date'],
    ascending=[True, False]
)""",
    },
    {
        "category": "SORT_DIRECTION",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "LOW",
        "failure_mode": "SORT_DIRECTION",
        "sas_code": """\
PROC SORT DATA=staging.results OUT=work.top_results;
    BY region DESCENDING revenue DESCENDING units;
RUN;""",
        "python_code": """\
import pandas as pd

df = staging_results.sort_values(
    ['region', 'revenue', 'units'],
    ascending=[True, False, False]
)""",
    },
    {
        "category": "SORT_DIRECTION",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "LOW",
        "failure_mode": "SORT_DIRECTION",
        "sas_code": """\
PROC SORT DATA=work.employees NODUPKEY;
    BY department DESCENDING salary;
RUN;""",
        "python_code": """\
import pandas as pd

df = df.sort_values(
    ['department', 'salary'],
    ascending=[True, False]
).drop_duplicates(subset=['department', 'salary'])""",
    },

    # ── P3: PROC MEANS with CLASS → single groupby(dropna=False).agg ─────────
    {
        "category": "PROC_MEANS_GROUPBY",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "MODERATE",
        "failure_mode": "PROC_MEANS_OUTPUT",
        "sas_code": """\
PROC MEANS DATA=work.sales N MEAN STD MIN MAX;
    CLASS region product_line;
    VAR revenue;
    OUTPUT OUT=work.summary
        MEAN=avg_revenue
        SUM=total_revenue
        N=obs_count;
RUN;""",
        "python_code": """\
import pandas as pd

summary = (
    df.groupby(['region', 'product_line'], dropna=False)
    .agg(
        avg_revenue=('revenue', 'mean'),
        total_revenue=('revenue', 'sum'),
        obs_count=('revenue', 'count'),
    )
    .reset_index()
)""",
    },
    {
        "category": "PROC_MEANS_GROUPBY",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "MODERATE",
        "failure_mode": "PROC_MEANS_OUTPUT",
        "sas_code": """\
PROC MEANS DATA=raw.transactions NWAY MEAN STD;
    CLASS account_type status;
    VAR balance amount;
    OUTPUT OUT=work.stats
        MEAN=avg_balance avg_amount
        STD=std_balance std_amount;
RUN;""",
        "python_code": """\
import pandas as pd

stats = (
    df.groupby(['account_type', 'status'], dropna=False)
    .agg(
        avg_balance=('balance', 'mean'),
        avg_amount=('amount', 'mean'),
        std_balance=('balance', 'std'),
        std_amount=('amount', 'std'),
    )
    .reset_index()
)""",
    },

    # ── P4: Boolean filter — WHERE / IF numeric condition ─────────────────────
    {
        "category": "BOOLEAN_FILTER",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "BOOLEAN_FILTER",
        "sas_code": """\
DATA work.high_value;
    SET raw.transactions;
    WHERE amount > 5000;
RUN;""",
        "python_code": """\
import pandas as pd

df = raw_transactions[raw_transactions['amount'] > 5000].copy()""",
    },
    {
        "category": "BOOLEAN_FILTER",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "BOOLEAN_FILTER",
        "sas_code": """\
DATA work.recent_active;
    SET raw.customers;
    IF age >= 18 AND days_inactive <= 90;
RUN;""",
        "python_code": """\
import pandas as pd

df = raw_customers[
    (raw_customers['age'] >= 18) & (raw_customers['days_inactive'] <= 90)
].copy()""",
    },
    {
        "category": "BOOLEAN_FILTER",
        "partition_type": "SQL_BLOCK",
        "complexity_tier": "LOW",
        "failure_mode": "BOOLEAN_FILTER",
        "sas_code": """\
PROC SQL;
    CREATE TABLE work.filtered AS
    SELECT * FROM raw.ledger
    WHERE balance > 0 AND status = 'ACTIVE';
QUIT;""",
        "python_code": """\
import pandas as pd

df = raw_ledger[
    (raw_ledger['balance'] > 0) & (raw_ledger['status'] == 'ACTIVE')
].copy()""",
    },

    # ── P5: PROC FORMAT display-only ──────────────────────────────────────────
    {
        "category": "FORMAT_DISPLAY_ONLY",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "LOW",
        "failure_mode": "PROC_FORMAT",
        "sas_code": """\
PROC FORMAT;
    VALUE $risk_fmt
        'HIGH'   = 'Critical'
        'MEDIUM' = 'Warning'
        'LOW'    = 'OK'
        OTHER    = 'Unknown';
RUN;

DATA work.labeled;
    SET work.scored;
    FORMAT risk_tier $risk_fmt.;
RUN;""",
        "python_code": """\
import pandas as pd

risk_fmt = {
    'HIGH': 'Critical',
    'MEDIUM': 'Warning',
    'LOW': 'OK',
}
# FORMAT is display-only — create a new column, never overwrite original
df['risk_tier_fmt'] = df['risk_tier'].map(risk_fmt).fillna('Unknown')""",
    },
    {
        "category": "FORMAT_DISPLAY_ONLY",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "LOW",
        "failure_mode": "PROC_FORMAT",
        "sas_code": """\
PROC FORMAT;
    VALUE $status_label
        'ACTIVE'    = 'Green'
        'OVERDRAWN' = 'Red'
        'DORMANT'   = 'Yellow'
        OTHER       = 'Gray';
RUN;""",
        "python_code": """\
import pandas as pd

# PROC FORMAT: display-only mapping — always make a NEW column
status_label_map = {
    'ACTIVE': 'Green',
    'OVERDRAWN': 'Red',
    'DORMANT': 'Yellow',
}
df['status_label'] = df['status'].map(status_label_map).fillna('Gray')""",
    },

    # ── P6: LEFT JOIN — PROC SQL LEFT JOIN ────────────────────────────────────
    {
        "category": "LEFT_JOIN",
        "partition_type": "SQL_BLOCK",
        "complexity_tier": "MODERATE",
        "failure_mode": "MERGE_SEMANTICS",
        "sas_code": """\
PROC SQL;
    CREATE TABLE work.enriched AS
    SELECT a.*, b.region_name, b.manager
    FROM work.accounts AS a
    LEFT JOIN ref.region_map AS b
    ON a.region_code = b.code
    WHERE a.status = 'ACTIVE';
QUIT;""",
        "python_code": """\
import pandas as pd

# Normalize key column names before merge to avoid case mismatch
accounts = work_accounts.copy()
region_map = ref_region_map.copy()
accounts.columns = accounts.columns.str.lower()
region_map.columns = region_map.columns.str.lower()

enriched = pd.merge(
    accounts,
    region_map[['code', 'region_name', 'manager']],
    left_on='region_code',
    right_on='code',
    how='left'
)
enriched = enriched[enriched['status'] == 'ACTIVE']""",
    },
    {
        "category": "LEFT_JOIN",
        "partition_type": "SQL_BLOCK",
        "complexity_tier": "MODERATE",
        "failure_mode": "MERGE_SEMANTICS",
        "sas_code": """\
PROC SQL;
    CREATE TABLE staging.joined AS
    SELECT
        a.customer_id,
        a.balance,
        b.segment,
        SUM(a.balance) AS total_balance
    FROM staging.accounts AS a
    LEFT JOIN ref.segments AS b
    ON a.segment_code = b.code
    WHERE a.balance > 1000
    GROUP BY 1, 2, 3;
QUIT;""",
        "python_code": """\
import pandas as pd

accounts = staging_accounts.copy()
segments = ref_segments.copy()
accounts.columns = accounts.columns.str.lower()
segments.columns = segments.columns.str.lower()

merged = pd.merge(
    accounts,
    segments[['code', 'segment']],
    left_on='segment_code',
    right_on='code',
    how='left'
)
joined = (
    merged[merged['balance'] > 1000]
    .groupby(['customer_id', 'balance', 'segment'], dropna=False)
    .agg(total_balance=('balance', 'sum'))
    .reset_index()
)""",
    },
    {
        "category": "LEFT_JOIN",
        "partition_type": "SQL_BLOCK",
        "complexity_tier": "LOW",
        "failure_mode": "MERGE_SEMANTICS",
        "sas_code": """\
PROC SQL;
    CREATE TABLE work.final AS
    SELECT a.id, a.name, b.score
    FROM work.employees AS a
    LEFT JOIN work.scores AS b
    ON a.id = b.employee_id
    ORDER BY b.score DESC;
QUIT;""",
        "python_code": """\
import pandas as pd

employees = work_employees.copy()
scores = work_scores.copy()

final = pd.merge(
    employees[['id', 'name']],
    scores[['employee_id', 'score']],
    left_on='id',
    right_on='employee_id',
    how='left'
).sort_values('score', ascending=False)""",
    },

    # ── P7: DATA MERGE with IN= ───────────────────────────────────────────────
    {
        "category": "MERGE_INDICATOR",
        "partition_type": "DATA_STEP",
        "complexity_tier": "MODERATE",
        "failure_mode": "MERGE_SEMANTICS",
        "sas_code": """\
DATA work.report;
    MERGE work.master (IN=a)
          work.adjustments (IN=b);
    BY account_id;
    IF a;
    IF b THEN balance = balance + adjustment_amt;
RUN;""",
        "python_code": """\
import pandas as pd

master = work_master.copy()
adjustments = work_adjustments.copy()
master.columns = master.columns.str.lower()
adjustments.columns = adjustments.columns.str.lower()

merged = pd.merge(
    master,
    adjustments[['account_id', 'adjustment_amt']],
    on='account_id',
    how='left',
    indicator=True
)
# IF a: keep only records from master (left_only + both)
merged = merged[merged['_merge'].isin(['left_only', 'both'])].copy()
# Apply adjustment where IN=b (matched records)
merged.loc[merged['_merge'] == 'both', 'balance'] = (
    merged.loc[merged['_merge'] == 'both', 'balance']
    + merged.loc[merged['_merge'] == 'both', 'adjustment_amt']
)
merged = merged.drop(columns=['_merge'])""",
    },
    {
        "category": "MERGE_INDICATOR",
        "partition_type": "DATA_STEP",
        "complexity_tier": "MODERATE",
        "failure_mode": "MERGE_SEMANTICS",
        "sas_code": """\
DATA final.monthly_report;
    MERGE staging.base (IN=a)
          staging.corrections (IN=b);
    BY transaction_id;
    IF a;
    corrected = (b = 1);
RUN;""",
        "python_code": """\
import pandas as pd

base = staging_base.copy()
corrections = staging_corrections.copy()
base.columns = base.columns.str.lower()
corrections.columns = corrections.columns.str.lower()

merged = pd.merge(
    base,
    corrections[['transaction_id']],
    on='transaction_id',
    how='left',
    indicator=True
)
merged = merged[merged['_merge'].isin(['left_only', 'both'])].copy()
merged['corrected'] = (merged['_merge'] == 'both').astype(int)
merged = merged.drop(columns=['_merge'])""",
    },

    # ── P8: PROC REG STEPWISE ─────────────────────────────────────────────────
    {
        "category": "STEPWISE_REGRESSION",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "HIGH",
        "failure_mode": "PROC_REG_STEPWISE",
        "sas_code": """\
PROC REG DATA=work.model_data;
    MODEL revenue = age income region_code / SELECTION=STEPWISE;
    TITLE 'Revenue Prediction Model';
RUN;""",
        "python_code": """\
import pandas as pd
import statsmodels.api as sm

SLE = 0.15  # significance level to enter
SLS = 0.15  # significance level to stay

X = df[['age', 'income', 'region_code']].copy()
y = df['revenue']

# Forward-backward stepwise using F-statistic p-value thresholds
candidates = list(X.columns)
selected = []

# Forward step
changed = True
while changed:
    changed = False
    best_pval = SLE
    best_feat = None
    for feat in candidates:
        if feat not in selected:
            test_cols = selected + [feat]
            model = sm.OLS(y, sm.add_constant(X[test_cols])).fit()
            pval = model.pvalues.get(feat, 1.0)
            if pval < best_pval:
                best_pval = pval
                best_feat = feat
    if best_feat:
        selected.append(best_feat)
        changed = True

    # Backward step — MUST be guarded by `if changed:` to avoid infinite loop
    if changed:
        back_changed = True
        while back_changed:
            back_changed = False
            if len(selected) > 1:
                model = sm.OLS(y, sm.add_constant(X[selected])).fit()
                worst = model.pvalues[selected].idxmax()
                if model.pvalues[worst] > SLS:
                    selected.remove(worst)
                    back_changed = True

# Final model
final_model = sm.OLS(y, sm.add_constant(X[selected])).fit()
print(final_model.summary())""",
    },
    {
        "category": "STEPWISE_REGRESSION",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "HIGH",
        "failure_mode": "PROC_REG_STEPWISE",
        "sas_code": """\
PROC REG DATA=staging.finance_data;
    MODEL total_balance = region_code manager_id / SELECTION=STEPWISE SLE=0.05 SLS=0.05;
    OUTPUT OUT=work.predictions PREDICTED=yhat RESIDUAL=resid;
RUN;""",
        "python_code": """\
import pandas as pd
import numpy as np
import statsmodels.api as sm

SLE = 0.05
SLS = 0.05

X = df[['region_code', 'manager_id']].copy()
y = df['total_balance']

candidates = list(X.columns)
selected = []

changed = True
while changed:
    changed = False
    best_pval = SLE
    best_feat = None
    for feat in [f for f in candidates if f not in selected]:
        model = sm.OLS(y, sm.add_constant(X[selected + [feat]])).fit()
        pval = model.pvalues.get(feat, 1.0)
        if pval < best_pval:
            best_pval = pval
            best_feat = feat
    if best_feat:
        selected.append(best_feat)
        changed = True

    if changed:
        back_changed = True
        while back_changed:
            back_changed = False
            if len(selected) > 1:
                model = sm.OLS(y, sm.add_constant(X[selected])).fit()
                worst = model.pvalues[selected].idxmax()
                if model.pvalues[worst] > SLS:
                    selected.remove(worst)
                    back_changed = True

final = sm.OLS(y, sm.add_constant(X[selected])).fit()
df['yhat'] = final.fittedvalues
df['resid'] = final.resid""",
    },

    # ── RETAIN accumulator ────────────────────────────────────────────────────
    {
        "category": "RETAIN_ACCUMULATOR",
        "partition_type": "DATA_STEP",
        "complexity_tier": "HIGH",
        "failure_mode": "",
        "sas_code": """\
DATA work.customer_totals;
    SET raw.transactions;
    BY customer_id;
    RETAIN running_total 0 tx_count 0;
    IF FIRST.customer_id THEN DO;
        running_total = 0;
        tx_count = 0;
    END;
    running_total + amount;
    tx_count + 1;
    IF LAST.customer_id THEN OUTPUT;
RUN;""",
        "python_code": """\
import pandas as pd

df_sorted = raw_transactions.sort_values('customer_id')
result = (
    df_sorted.groupby('customer_id', sort=False)
    .agg(
        running_total=('amount', 'sum'),
        tx_count=('amount', 'count'),
    )
    .reset_index()
)""",
    },
    {
        "category": "RETAIN_ACCUMULATOR",
        "partition_type": "DATA_STEP",
        "complexity_tier": "HIGH",
        "failure_mode": "",
        "sas_code": """\
DATA work.dept_summary;
    SET raw.payroll;
    BY department;
    RETAIN dept_total 0 headcount 0;
    IF FIRST.department THEN DO;
        dept_total = 0;
        headcount = 0;
    END;
    dept_total + salary;
    headcount + 1;
    avg_salary = dept_total / headcount;
    IF LAST.department THEN OUTPUT;
RUN;""",
        "python_code": """\
import pandas as pd

result = (
    raw_payroll.groupby('department', sort=True)
    .agg(
        dept_total=('salary', 'sum'),
        headcount=('salary', 'count'),
    )
    .assign(avg_salary=lambda d: d['dept_total'] / d['headcount'])
    .reset_index()
)""",
    },

    # ── String manipulation ────────────────────────────────────────────────────
    {
        "category": "STRING_MANIPULATION",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "COMPRESS_FUNCTION",
        "sas_code": """\
DATA work.cleaned;
    SET raw.contacts;
    customer_name = UPCASE(STRIP(name));
    account_id = COMPRESS(account_id, '-');
    email_clean = LOWCASE(STRIP(email));
RUN;""",
        "python_code": """\
import pandas as pd
import re

df = raw_contacts.copy()
df['customer_name'] = df['name'].str.strip().str.upper()
# COMPRESS(x, '-') removes only '-' characters
df['account_id'] = df['account_id'].astype(str).str.replace('-', '', regex=False)
df['email_clean'] = df['email'].str.strip().str.lower()""",
    },
    {
        "category": "STRING_MANIPULATION",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "COMPRESS_FUNCTION",
        "sas_code": """\
DATA work.normalized;
    SET raw.ids;
    /* COMPRESS with no second arg removes ALL non-alphanumeric */
    clean_id = COMPRESS(raw_id);
    padded = PUT(seq_num, Z5.);
RUN;""",
        "python_code": """\
import pandas as pd
import re

df = raw_ids.copy()
# COMPRESS(x) with no 2nd arg removes ALL non-alphanumeric characters
df['clean_id'] = df['raw_id'].astype(str).apply(
    lambda x: re.sub(r'[^a-zA-Z0-9]', '', x)
)
df['padded'] = df['seq_num'].apply(lambda x: str(int(x)).zfill(5))""",
    },

    # ── Date arithmetic ───────────────────────────────────────────────────────
    {
        "category": "DATE_ARITHMETIC",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "",
        "sas_code": """\
DATA work.age_calc;
    SET raw.customers;
    days_since_active = TODAY() - last_transaction_dt;
    IF days_since_active > 365 THEN account_type = 'DORMANT';
    ELSE account_type = 'CURRENT';
RUN;""",
        "python_code": """\
import pandas as pd
import numpy as np
from datetime import date

df = raw_customers.copy()
today = pd.Timestamp(date.today())
df['last_transaction_dt'] = pd.to_datetime(df['last_transaction_dt'])
df['days_since_active'] = (today - df['last_transaction_dt']).dt.days
df['account_type'] = np.where(df['days_since_active'] > 365, 'DORMANT', 'CURRENT')""",
    },
    {
        "category": "DATE_ARITHMETIC",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "",
        "sas_code": """\
DATA work.tenure;
    SET raw.employees;
    tenure_days = TODAY() - hire_date;
    tenure_years = INT(tenure_days / 365.25);
    is_senior = (tenure_years >= 5);
RUN;""",
        "python_code": """\
import pandas as pd
import numpy as np
from datetime import date

df = raw_employees.copy()
today = pd.Timestamp(date.today())
df['hire_date'] = pd.to_datetime(df['hire_date'])
df['tenure_days'] = (today - df['hire_date']).dt.days
df['tenure_years'] = (df['tenure_days'] / 365.25).astype(int)
df['is_senior'] = (df['tenure_years'] >= 5).astype(int)""",
    },

    # ── PROC FREQ cross-tabulation ─────────────────────────────────────────────
    {
        "category": "PROC_FREQ",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "LOW",
        "failure_mode": "",
        "sas_code": """\
PROC FREQ DATA=work.monthly_report;
    TABLES region * status / NOCOL NOPERCENT;
RUN;""",
        "python_code": """\
import pandas as pd

# PROC FREQ NOCOL NOPERCENT = counts only, no percentages
freq_table = pd.crosstab(
    df['region'],
    df['status'],
    dropna=False   # SAS FREQ treats missing as a valid category
)
print(freq_table)""",
    },

    # ── PROC EXPORT ───────────────────────────────────────────────────────────
    {
        "category": "PROC_EXPORT",
        "partition_type": "PROC_BLOCK",
        "complexity_tier": "LOW",
        "failure_mode": "",
        "sas_code": """\
PROC EXPORT DATA=final.report
    OUTFILE="/output/results.csv"
    DBMS=CSV REPLACE;
RUN;""",
        "python_code": """\
import pandas as pd

try:
    df.to_csv('/output/results.csv', index=False)
except IOError as e:
    raise IOError(f"Failed to write CSV output: {e}")""",
    },

    # ── Inline DATALINES ─────────────────────────────────────────────────────
    {
        "category": "DATALINES",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "",
        "sas_code": """\
DATA work.manual_entries;
    INPUT id $ amount type $;
    DATALINES;
    A001 100.00 CREDIT
    A002 -25.50 DEBIT
    A003 500.00 BONUS
    ;
RUN;""",
        "python_code": """\
import pandas as pd
import io

data = \"\"\"id,amount,type
A001,100.00,CREDIT
A002,-25.50,DEBIT
A003,500.00,BONUS\"\"\"

df = pd.read_csv(io.StringIO(data))
df['amount'] = df['amount'].astype(float)""",
    },

    # ── Missing value handling ────────────────────────────────────────────────
    {
        "category": "MISSING_VALUES",
        "partition_type": "DATA_STEP",
        "complexity_tier": "LOW",
        "failure_mode": "",
        "sas_code": """\
DATA work.cleaned;
    SET raw.data;
    IF age = . THEN age = 0;
    IF score < . THEN flag = 'MISSING';
    ELSE IF score > 100 THEN flag = 'INVALID';
    ELSE flag = 'OK';
RUN;""",
        "python_code": """\
import pandas as pd
import numpy as np

df = raw_data.copy()
df['age'] = df['age'].fillna(0)
# SAS: score < . means score is missing (. is the smallest numeric in SAS)
df['flag'] = np.select(
    [df['score'].isna(), df['score'] > 100],
    ['MISSING', 'INVALID'],
    default='OK'
)""",
    },
]


# ── Main ──────────────────────────────────────────────────────────────────────

def build_record(pair: dict, embedder: NomicEmbedder) -> dict:
    """Embed a SAS→Python pair and return a KB record dict."""
    # Embed SAS code as the query text (matches how retrieval works)
    embedding = embedder.embed(pair["sas_code"])

    return {
        "example_id":          str(uuid.uuid4()),
        "sas_code":            pair["sas_code"],
        "python_code":         pair["python_code"],
        "embedding":           embedding,
        "partition_type":      pair["partition_type"],
        "complexity_tier":     pair["complexity_tier"],
        "target_runtime":      "python",
        "verified":            True,
        "source":              "seed_hand_crafted",
        "failure_mode":        pair.get("failure_mode", ""),
        "verification_method": "manual_review",
        "verification_score":  1.0,
        "category":            pair["category"],
        "version":             1,
        "superseded_by":       "",
        "created_at":          datetime.now(timezone.utc).isoformat(),
        "issues_text":         "",  # hand-crafted pairs have no issue list
    }


def main(args: argparse.Namespace) -> None:
    db_path = str(BACKEND_DIR / "data" / "lancedb")
    writer = KBWriter(db_path=db_path)

    if args.stats:
        stats = writer.coverage_stats()
        if not stats:
            print("KB is empty.")
            return
        total = sum(stats.values())
        print(f"\nKB coverage ({total} total pairs):")
        for cat, count in sorted(stats.items(), key=lambda x: -x[1]):
            bar = "█" * min(count, 40)
            print(f"  {cat:<35} {bar} {count}")
        return

    if args.clear:
        import lancedb
        db = lancedb.connect(db_path)
        if writer.TABLE_NAME in db.table_names():
            db.drop_table(writer.TABLE_NAME)
            print(f"Cleared table '{writer.TABLE_NAME}'.")

    print(f"\nLoading NomicEmbedder (768-dim, CPU)...")
    embedder = NomicEmbedder()

    print(f"Embedding {len(SEED_PAIRS)} pairs...")
    records = []
    for i, pair in enumerate(SEED_PAIRS, 1):
        rec = build_record(pair, embedder)
        records.append(rec)
        print(f"  [{i:02d}/{len(SEED_PAIRS)}] {pair['category']:<30} {pair['partition_type']}")

    inserted = writer.insert_pairs(records)
    total = writer.count()
    print(f"\nInserted {inserted} pairs. KB total: {total}")

    stats = writer.coverage_stats()
    print("\nCoverage by category:")
    for cat, count in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {cat:<35} {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Codara Knowledge Base")
    parser.add_argument("--clear",  action="store_true", help="Drop and recreate the table")
    parser.add_argument("--stats",  action="store_true", help="Show coverage stats and exit")
    main(parser.parse_args())
