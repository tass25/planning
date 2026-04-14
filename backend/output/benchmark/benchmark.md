# Codara  --  Model Benchmark

**Run:** 2026-04-12T22:10:03Z
**SAS file:** torture_test.sas  (10 blocks)
**Models:** minimax-m2.7:cloud, qwen3-coder-next:cloud, deepseek-v3.2:cloud, glm-5.1:cloud

---

## 1. Aggregate

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Success rate | 100% | 100% | 40% | 60% |
| Syntax valid | 100% | 100% | 40% | 60% |
| Mean confidence | 0.94 | 0.96 | 0.69 | 0.78 |
| Mean latency (s) | 12.8 | 4.7 | 61.7 | 14.9 |
| p95 latency (s) | 22.0 | 6.3 | 77.8 | 28.2 |
| Total time (s) | 128 | 47 | 617 | 149 |
| Prompt tokens (total) | 3,458 | 3,148 | 3,247 | 3,060 |
| Completion tokens | 7,831 | 2,266 | 16,610 | 14,113 |
| Total tokens | 11,289 | 5,414 | 19,857 | 17,173 |
| Mean tok/s | 64 | 46 | 27 | 92 |
| Z3 formally proved | 3/10 | 3/10 | 2/10 | 1/10 |
| Z3 counterexamples | 0/10 | 0/10 | 0/10 | 0/10 |
| Z3 unknown | 7/10 | 7/10 | 4/10 | 6/10 |

---

## 2. Block-by-Block

### Block 1: 1. RETAIN + BY-group FIRST./LAST.
Risk: HIGH | SAS lines: 12

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | PARTIAL | SUCCESS |
| Latency (s) | 16.2 | 4.9 | 77.8 | 12.8 |
| Prompt tokens | 361 | 316 | 325 | 308 |
| Compl. tokens | 864 | 266 | 2048 | 1134 |
| tok/s | 53 | 54 | 26 | 89 |
| Confidence | 0.95 | 0.95 | 0.50 | 1.00 |
| Python LOC | 9 | 12 | 0 | 11 |
| Syntax valid | yes | yes | NO:  | yes |
| Z3 result | unknown | unknown | skipped | unknown |
| Z3 pattern | conditional_assignment | conditional_assignment | - | conditional_assignment |
| Z3 lat (ms) | 47.0 | 0.0 | 0.0 | 0.0 |

### Block 2: 2. Missing value logic (SAS . < any number)
Risk: LOW | SAS lines: 7

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | PARTIAL | PARTIAL |
| Latency (s) | 9.3 | 3.8 | 76.3 | 20.9 |
| Prompt tokens | 329 | 299 | 305 | 289 |
| Compl. tokens | 719 | 153 | 2048 | 2048 |
| tok/s | 77 | 40 | 27 | 98 |
| Confidence | 0.95 | 1.00 | 0.50 | 0.50 |
| Python LOC | 15 | 9 | 0 | 0 |
| Syntax valid | yes | yes | NO:  | NO:  |
| Z3 result | unknown | unknown | skipped | skipped |
| Z3 pattern | boolean_filter | boolean_filter | - | - |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 3: 3. PROC SQL with correlated subquery
Risk: MOD | SAS lines: 14

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | SUCCESS | SUCCESS |
| Latency (s) | 10.9 | 4.1 | 33.1 | 12.0 |
| Prompt tokens | 389 | 333 | 347 | 325 |
| Compl. tokens | 974 | 174 | 822 | 1070 |
| tok/s | 90 | 43 | 25 | 89 |
| Confidence | 0.95 | 1.00 | 1.00 | 1.00 |
| Python LOC | 14 | 7 | 9 | 7 |
| Syntax valid | yes | yes | yes | yes |
| Z3 result | unknown | unknown | unknown | unknown |
| Z3 pattern | boolean_filter | boolean_filter | boolean_filter | boolean_filter |
| Z3 lat (ms) | 15.0 | 0.0 | 0.0 | 0.0 |

### Block 4: 4. Macro with parameters + %DO loop
Risk: MOD | SAS lines: 14

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | PARTIAL | PARTIAL |
| Latency (s) | 22.0 | 6.3 | 75.9 | 19.0 |
| Prompt tokens | 378 | 369 | 380 | 361 |
| Compl. tokens | 1080 | 399 | 2048 | 2048 |
| tok/s | 49 | 64 | 27 | 108 |
| Confidence | 0.95 | 0.95 | 0.50 | 0.50 |
| Python LOC | 19 | 20 | 2 | 0 |
| Syntax valid | yes | yes | NO: line 2: unterminated string literal (det | NO:  |
| Z3 result | unknown | unknown | unknown | skipped |
| Z3 pattern | conditional_assignment | conditional_assignment | conditional_assignment | - |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 5: 5. PROC MEANS with CLASS and OUTPUT
Risk: LOW | SAS lines: 8

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | PARTIAL | PARTIAL |
| Latency (s) | 13.3 | 4.5 | 76.4 | 13.9 |
| Prompt tokens | 335 | 302 | 315 | 294 |
| Compl. tokens | 817 | 184 | 2048 | 2048 |
| tok/s | 61 | 41 | 27 | 148 |
| Confidence | 0.95 | 1.00 | 0.50 | 0.50 |
| Python LOC | 15 | 10 | 0 | 0 |
| Syntax valid | yes | yes | NO:  | NO:  |
| Z3 result | PROVED | PROVED | skipped | skipped |
| Z3 pattern | proc_means_groupby | proc_means_groupby | - | - |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 6: 6. PROC SORT NODUPKEY
Risk: LOW | SAS lines: 3

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | SUCCESS | SUCCESS |
| Latency (s) | 4.4 | 3.2 | 34.5 | 4.3 |
| Prompt tokens | 280 | 260 | 267 | 252 |
| Compl. tokens | 215 | 73 | 897 | 212 |
| tok/s | 49 | 23 | 26 | 49 |
| Confidence | 1.00 | 1.00 | 1.00 | 1.00 |
| Python LOC | 1 | 1 | 3 | 3 |
| Syntax valid | yes | yes | yes | yes |
| Z3 result | PROVED | PROVED | PROVED | PROVED |
| Z3 pattern | sort_nodupkey | sort_nodupkey | sort_nodupkey | sort_nodupkey |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 7: 7. Hash object for lookup
Risk: HIGH | SAS lines: 11

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | SUCCESS | SUCCESS |
| Latency (s) | 15.0 | 4.7 | 36.5 | 4.6 |
| Prompt tokens | 366 | 320 | 333 | 312 |
| Compl. tokens | 884 | 186 | 968 | 283 |
| tok/s | 59 | 40 | 27 | 61 |
| Confidence | 0.95 | 0.95 | 0.95 | 0.95 |
| Python LOC | 10 | 9 | 19 | 11 |
| Syntax valid | yes | yes | yes | yes |
| Z3 result | unknown | unknown | PROVED | unknown |
| Z3 pattern | conditional_assignment | conditional_assignment | conditional_assignment | conditional_assignment |
| Z3 lat (ms) | 16.0 | 0.0 | 0.0 | 0.0 |

### Block 8: 8. Multi-level nested macro
Risk: MOD | SAS lines: 11

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | PARTIAL | SUCCESS |
| Latency (s) | 9.4 | 5.5 | 72.8 | 12.7 |
| Prompt tokens | 386 | 344 | 356 | 336 |
| Compl. tokens | 838 | 278 | 2048 | 1535 |
| tok/s | 89 | 50 | 28 | 121 |
| Confidence | 0.85 | 0.85 | 0.50 | 0.90 |
| Python LOC | 17 | 18 | 2 | 10 |
| Syntax valid | yes | yes | NO: line 2: unterminated string literal (det | yes |
| Z3 result | unknown | unknown | unknown | unknown |
| Z3 pattern | proc_means_groupby | proc_means_groupby | proc_means_groupby | proc_means_groupby |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 9: 9. PROC TRANSPOSE
Risk: LOW | SAS lines: 5

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | SUCCESS | SUCCESS |
| Latency (s) | 10.7 | 4.7 | 59.6 | 20.2 |
| Prompt tokens | 300 | 273 | 282 | 265 |
| Compl. tokens | 666 | 232 | 1635 | 1687 |
| tok/s | 62 | 49 | 27 | 84 |
| Confidence | 0.95 | 1.00 | 0.95 | 0.95 |
| Python LOC | 10 | 12 | 7 | 9 |
| Syntax valid | yes | yes | yes | yes |
| Z3 result | unknown | unknown | unknown | unknown |
| Z3 pattern | - | - | - | - |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 10: 10. Complex WHERE + FORMAT + LABEL
Risk: LOW | SAS lines: 11

| Metric | minimax | qwen3 | deepseek-v3.2 | glm-5.1 |
|--------|----|----|----|----|
| Status | SUCCESS | SUCCESS | PARTIAL | PARTIAL |
| Latency (s) | 16.4 | 5.6 | 74.3 | 28.2 |
| Prompt tokens | 334 | 332 | 337 | 318 |
| Compl. tokens | 774 | 321 | 2048 | 2048 |
| tok/s | 47 | 58 | 28 | 73 |
| Confidence | 0.95 | 0.95 | 0.50 | 0.50 |
| Python LOC | 16 | 18 | 0 | 8 |
| Syntax valid | yes | yes | NO:  | NO: line 8: unterminated string literal (det |
| Z3 result | PROVED | PROVED | skipped | unknown |
| Z3 pattern | boolean_filter | boolean_filter | - | boolean_filter |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

---

## 3. Translation snippets (first 12 lines)

### Block 1: 1. RETAIN + BY-group FIRST./LAST.

**minimax**
```python
import pandas as pd

# Ensure data is sorted by customer_id (required for groupby)
df = transactions.sort_values('customer_id')

# Group by customer_id: aggregate to get final totals per customer
# dropna=False mirrors SAS behavior for BY-group processing with missing values
customer_summary = df.groupby('customer_id', dropna=False).agg(
    running_total=('amount', 'sum'),  # equivalent to RETAIN running_total + amount
    tx_count=('amount', 'count')       # equivalent to RETAIN tx_count + 1
).reset_index()
```

**qwen3**
```python
import pandas as pd
import numpy as np

# Group by customer_id and compute cumulative sum of amount and count of transactions
# Only keep the last row per customer (equivalent to output on last.customer_id)
customer_summary = transactions.groupby('customer_id', dropna=False).agg(
    running_total=('amount', 'cumsum'),  # cumulative sum
    tx_count=('amount', 'cumcount')      # 0-indexed cumcount; add 1 to match SAS 1-indexed count
).reset_index()

# Adjust tx_count to be 1-indexed (SAS counts start at 1)
customer_summary['tx_count'] = customer_summary['tx_count'] + 1
```

**deepseek-v3.2**
```python
# PARTIAL: empty python_code after parse
```

**glm-5.1**
```python
import pandas as pd

# SAS 'by' + 'retain' + 'if last.x then output' is an idiom for groupby aggregation.
# 'running_total + amount' accumulates the sum, 'tx_count + 1' accumulates the row count.
customer_summary = (
    transactions.groupby('customer_id', dropna=False)
    .agg(
        running_total=('amount', 'sum'),
        tx_count=('amount', 'size')  # 'size' counts all rows per group, matching the SAS +1 logic
    )
    .reset_index()
)
```

### Block 2: 2. Missing value logic (SAS . < any number)

**minimax**
```python
import pandas as pd
import numpy as np

# Copy to avoid modifying raw_data
cleaned = raw_data.copy()

# If age is missing, fill with 0
cleaned['age'] = cleaned['age'].fillna(0)

# Create flag based on score conditions (SAS: . = missing, treated as smallest value)
cleaned['flag'] = np.select(
    condlist=[
# ... 3 more lines
```

**qwen3**
```python
import pandas as pd
import numpy as np

cleaned = raw_data.copy()
cleaned['age'] = cleaned['age'].fillna(0)  # Replace missing age with 0
cleaned['flag'] = np.select(
    [cleaned['score'].isna(), cleaned['score'] > 100],
    ['MISSING', 'INVALID'],
    default='OK'
)
```

**deepseek-v3.2**
```python
# PARTIAL: empty python_code after parse
```

**glm-5.1**
```python
# PARTIAL: empty python_code after parse
```

### Block 3: 3. PROC SQL with correlated subquery

**minimax**
```python
import pandas as pd

# Compute average amount per customer from transactions
avg_amounts = transactions.groupby('customer_id', as_index=False)['amount'].mean()
avg_amounts.rename(columns={'amount': 'avg_amount'}, inplace=True)

# Inner join with aggregated averages (SAS semantics preserved)
high_value = pd.merge(
    transactions,
    avg_amounts,
    on='customer_id',
    how='inner'
# ... 2 more lines
```

**qwen3**
```python
import pandas as pd
import numpy as np

# Compute average amount per customer
avg_df = transactions.groupby('customer_id', dropna=False)['amount'].mean().reset_index(name='avg_amount')

# Merge with original transactions and filter
high_value = pd.merge(transactions, avg_df, on='customer_id', how='inner')
high_value = high_value[high_value['amount'] > high_value['avg_amount'] * 1.5].reset_index(drop=True)
```

**deepseek-v3.2**
```python
import pandas as pd

# Compute average amount per customer
avg_amounts = transactions.groupby('customer_id')['amount'].mean().reset_index()
avg_amounts.columns = ['customer_id', 'avg_amount']

# Inner join with original transactions and filter
high_value = pd.merge(transactions, avg_amounts, on='customer_id', how='inner')
high_value = high_value[high_value['amount'] > high_value['avg_amount'] * 1.5]

# Select required columns
high_value = high_value[['customer_id', 'amount', 'avg_amount']]
```

**glm-5.1**
```python
import pandas as pd

# Calculate average amount per customer (subquery equivalent)
avg_t = transactions.groupby('customer_id', as_index=False).agg(avg_amount=('amount', 'mean'))

# Inner join transactions with average amounts
merged = pd.merge(transactions, avg_t, on='customer_id', how='inner')

# Filter where amount > 1.5 * avg_amount and select columns
high_value = merged.loc[merged['amount'] > merged['avg_amount'] * 1.5, ['customer_id', 'amount', 'avg_amount']]
```

### Block 4: 4. Macro with parameters + %DO loop

**minimax**
```python
import pandas as pd

def rolling_mean(df, var='close', window=5, out=None):
    """
    Compute rolling mean using a circular buffer approach.
    Equivalent to the SAS %rolling_mean macro.
    
    Args:
        df: Input DataFrame
        var: Variable name for which to compute rolling mean
        window: Rolling window size (default: 5)
        out: Optional output DataFrame name (for compatibility)
# ... 7 more lines
```

**qwen3**
```python
import pandas as pd
import numpy as np

# Assuming 'prices' is a pandas DataFrame with at least a 'close' column
# The SAS macro computes a rolling mean over a fixed-size window using a circular buffer
# Here we replicate it using pandas' rolling (but note: SAS uses a fixed-size sliding window, not expanding)

# Load data (assuming 'prices' DataFrame already exists)
# prices = pd.read_csv('prices.csv')  # Uncomment if loading from file

# Ensure 'close' column exists
if 'close' not in prices.columns:
# ... 8 more lines
```

**deepseek-v3.2**
```python
{
  "python_code": "import pandas as pd\nimport numpy as np\n\n# Replicate SAS rolling mean macro with circular buffer\n# Note: This implementation uses pandas rolling window for efficiency\n# but maintains the same
```

**glm-5.1**
```python
# PARTIAL: empty python_code after parse
```

### Block 5: 5. PROC MEANS with CLASS and OUTPUT

**minimax**
```python
import pandas as pd

# Equivalent to: proc means data=sales; class region product_line; var revenue units_sold;
# SAS _type_ and _freq_ columns are metadata and not produced by pandas groupby
summary = (
    sales
    .groupby(['region', 'product_line'], dropna=False)
    .agg(
        avg_revenue=('revenue', 'mean'),
        total_revenue=('revenue', 'sum'),
        obs_count=('revenue', 'count'),
        avg_units=('units_sold', 'mean'),
# ... 3 more lines
```

**qwen3**
```python
import pandas as pd
import numpy as np

# Assuming 'sales' is a pandas DataFrame
summary = sales.groupby(['region', 'product_line'], dropna=False).agg(
    avg_revenue=('revenue', 'mean'),
    avg_units=('units_sold', 'mean'),
    total_revenue=('revenue', 'sum'),
    total_units=('units_sold', 'sum'),
    obs_count=('revenue', 'count')  # count non-null values in revenue column
).reset_index()
```

**deepseek-v3.2**
```python
# PARTIAL: empty python_code after parse
```

**glm-5.1**
```python
# PARTIAL: empty python_code after parse
```

### Block 6: 6. PROC SORT NODUPKEY

**minimax**
```python
customers = customers.sort_values('customer_id').drop_duplicates(subset=['customer_id'])
```

**qwen3**
```python
customers = customers.sort_values('customer_id').drop_duplicates(subset=['customer_id'])
```

**deepseek-v3.2**
```python
import pandas as pd

# PROC SORT NODUPKEY: sort and remove duplicates by key
customers = customers.sort_values(by='customer_id').drop_duplicates(subset='customer_id')
```

**glm-5.1**
```python
import pandas as pd

# PROC SORT NODUPKEY: sort by variable(s) and drop duplicate keys
customers = customers.sort_values(by=['customer_id']).drop_duplicates(subset=['customer_id'])
```

### Block 7: 7. Hash object for lookup

**minimax**
```python
import pandas as pd

# Merge transactions with lookup_table on product_id (left join)
# This mimics the SAS hash lookup behavior
enriched = transactions.merge(
    lookup_table[['product_id', 'product_name', 'category']],
    on='product_id',
    how='left'
)

# If product_name is not found (rc ^= 0 in SAS), set to 'UNKNOWN'
enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')
```

**qwen3**
```python
import pandas as pd
import numpy as np

# Load lookup table and transactions
lookup_table = pd.read_csv('lookup_table.csv')  # or however it's loaded
transactions = pd.read_csv('transactions.csv')  # or however it's loaded

# Merge lookup table on product_id (left join)
enriched = transactions.merge(lookup_table[['product_id', 'product_name', 'category']], on='product_id', how='left')

# Replace missing product_name with 'UNKNOWN'
enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')
```

**deepseek-v3.2**
```python
import pandas as pd
import numpy as np

# Load datasets (assuming they exist as DataFrames)
# lookup_table = pd.read_csv('lookup_table.csv')  # Example if reading from file
# transactions = pd.read_csv('transactions.csv')

# Perform hash join equivalent: left join on product_id
enriched = pd.merge(
    transactions,
    lookup_table[['product_id', 'product_name', 'category']],
    on='product_id',
# ... 7 more lines
```

**glm-5.1**
```python
import pandas as pd
import numpy as np

# SAS hash object lookup -> pandas left merge
enriched = pd.merge(
    transactions,
    lookup_table[['product_id', 'product_name', 'category']],
    on='product_id',
    how='left'
)

# If rc ^= 0 (key not found in hash), set product_name to 'UNKNOWN'
```

### Block 8: 8. Multi-level nested macro

**minimax**
```python
import pandas as pd

# Macro equivalent: apply_to_all(action=, datasets=)
def apply_to_all(action, datasets_str):
    """Apply action function to each space-separated dataset name."""
    datasets = datasets_str.split()
    for ds in datasets:
        action(dsn=ds)

# Macro equivalent: summarise(dsn=)
def summarise(dsn):
    """Run descriptive statistics on a dataset (equivalent to PROC MEANS)."""
# ... 5 more lines
```

**qwen3**
```python
import pandas as pd

# Simulate applying a function to multiple datasets
# Since actual SAS datasets aren't available, we assume they're loaded as DataFrames
# e.g., sales, returns, inventory = pd.read_sas(...), etc.

def summarise(df):
    # Equivalent to PROC MEANS: compute descriptive statistics
    return df.describe()

def apply_to_all(action, datasets):
    # action: function to apply to each dataset
# ... 6 more lines
```

**deepseek-v3.2**
```python
{
  "python_code": "import pandas as pd\nimport numpy as np\n\n# Define function to apply to multiple datasets\ndef apply_to_all(action, datasets):\n    \"\"\"Apply given function to list of dataset names\"\"\"\n    for ds in datasets:\n        action(dsn=ds)\n\n# Define summary function\ndef summarise(dsn):\n    \"\"\"Print summary statistics for given DataFrame name\"\"\"\n
```

**glm-5.1**
```python
import pandas as pd

def summarise(df):
    # Equivalent to PROC MEANS without CLASS or VAR statements
    print(df.describe())

def apply_to_all(action, datasets):
    # SAS macro loop over space-separated names translates to a Python for-loop over a list
    for ds in datasets:
        action(ds)

# Example usage (assuming sales, returns, inventory are DataFrames):
```

### Block 9: 9. PROC TRANSPOSE

**minimax**
```python
import pandas as pd

# PROC TRANSPOSE equivalent: pivot from long to wide format
# by product_id  -> index (rows)
# id month       -> columns (with prefix added)
# var revenue    -> values
wide_sales = monthly_sales.pivot(index='product_id', columns='month', values='revenue')

# Add prefix to column names (SAS prefix=month_)
wide_sales.columns = 'month_' + wide_sales.columns.astype(str)

# Reset index so product_id becomes a column (similar to SAS output structure)
```

**qwen3**
```python
import pandas as pd
import numpy as np

# Assuming 'monthly_sales' is a DataFrame with columns: product_id, month, revenue
# Reshape from long to wide format using pivot_table (similar to PROC TRANSPOSE)
wide_sales = monthly_sales.pivot_table(
    index='product_id',
    columns='month',
    values='revenue',
    aggfunc='first'  # assuming unique revenue per product_id-month; use 'mean' or custom if duplicates exist
).reset_index()

```

**deepseek-v3.2**
```python
import pandas as pd

# Transpose long to wide format (PROC TRANSPOSE equivalent)
wide_sales = monthly_sales.pivot(
    index='product_id',  # BY variable
    columns='month',     # ID variable for column names
    values='revenue'     # VAR variable to transpose
).add_prefix('month_').reset_index()  # Add prefix and reset index to match SAS output structure
```

**glm-5.1**
```python
import pandas as pd

# PROC TRANSPOSE: pivot from long to wide, applying PREFIX to new columns
wide_sales = (
    monthly_sales
    .pivot_table(index='product_id', columns='month', values='revenue', aggfunc='first')
    .rename(columns=lambda c: f'month_{c}')
    .rename_axis(columns=None)
    .reset_index()
)
```

### Block 10: 10. Complex WHERE + FORMAT + LABEL

**minimax**
```python
import pandas as pd
import numpy as np

# Filter: age 18-65, status in ('ACTIVE','PENDING'), score not missing
report = survey[
    (survey['age'] >= 18) &
    (survey['age'] <= 65) &
    (survey['status'].isin(['ACTIVE', 'PENDING'])) &
    (survey['score'].notna())  # score ^= . means not missing
].copy()

# Create derived column
# ... 4 more lines
```

**qwen3**
```python
import pandas as pd
import numpy as np

# Filter rows and compute derived columns
report = survey[
    (survey['age'] >= 18) &
    (survey['age'] <= 65) &
    (survey['status'].isin(['ACTIVE', 'PENDING'])) &
    (survey['score'].notna())
].copy()

# Format score as float with 2 decimal places (no change to data, just display)
# ... 6 more lines
```

**deepseek-v3.2**
```python
# PARTIAL: empty python_code after parse
```

**glm-5.1**
```python
{
  "python_code": "import pandas as pd\nimport numpy as np\n\n# Apply WHERE clause filtering\nmask = (\n    survey['age'].between(18, 65) &\n    survey['status'].isin(['ACTIVE', 'PENDING']) &\n    survey['score'].notna()  # score ^= . means score is not missing\n)\nreport = survey.loc[mask].copy()\n\n# SAS formats control display; pandas doesn't have a direct equivalent.\n# We round the column to mimic the 8.2 format display.\nreport['score'] = report['score'].round(2)\n\n# Ensure survey_date is a datetime object to mimic SAS date formatting\nreport['survey_date'] = pd.to_datetime(report['survey_date'], errors='coerce')\n\n# SAS labels are metadata for reporting; pandas doesn't have a built-in label system\n# separate from column names. They are noted here for reference:\n# score = 'Survey Score (0-100)'\n# survey_date = 'Date of Survey'\n\n# New column calculation\nreport['score_pct'] = report['score'] / 100",
  "imports_detected": [
    "import pandas as pd",
    "import numpy as np"
  ],
  "confidence": 0.95,
  "notes": "SAS formats and labels do not have direct pandas equivalents; rounding and datetime conversion are used to approximate format behavior
```
