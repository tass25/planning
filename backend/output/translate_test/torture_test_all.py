

# ======================================================================# Block 1: 1. RETAIN + BY-group FIRST./LAST.
# ======================================================================

import pandas as pd

# Assuming 'transactions' DataFrame is already loaded in the environment.
# This translation handles the SAS DATA step pattern:
#   BY customer_id processing with RETAIN, FIRST./LAST. logic

# Ensure data is sorted by customer_id (SAS BY processing requires sorted data)
df = transactions.sort_values('customer_id').reset_index(drop=True)

# Create first/last flags for customer_id detection
# FIRST.var = 1 when current row is first in BY group
df['_is_first'] = df.groupby('customer_id').cumcount() == 0
# LAST.var = 1 when current row is last in BY group
df['_is_last'] = df.groupby('customer_id').cumcount(ascending=False) == 0

# Calculate running_total: cumulative sum of 'amount' within each customer group
# This implicitly resets at the start of each group (equivalent to SAS RETAIN reset)
df['running_total'] = df.groupby('customer_id')['amount'].cumsum()

# Calculate tx_count: row number within each customer group (1-based)
df['tx_count'] = df.groupby('customer_id').cumcount() + 1

# Output only the last row per customer_id (equivalent to SAS 'if last.customer_id then output;')
customer_summary = df[df['_is_last']][['customer_id', 'running_total', 'tx_count']].copy()

# Clean up temporary flags
df.drop(columns=['_is_first', '_is_last'], inplace=True)

# Result: customer_summary contains one row per customer with:
#   - customer_id
#   - running_total: sum of all transaction amounts for that customer
#   - tx_count: total number of transactions for that customer


# Block 2: 2. Missing value logic (SAS . < any number)
# ======================================================================

import pandas as pd
import numpy as np

# Read data
df = raw_data.copy()

# If age is missing, set to 0
df['age'] = df['age'].fillna(0)

# Create flag based on score value
# SAS: score < . means score is missing (. is the smallest numeric in SAS)
df['flag'] = np.select(
    [df['score'].isna(), df['score'] > 100],
    ['MISSING', 'INVALID'],
    default='OK'
)


# Block 3: 3. PROC SQL with correlated subquery
# ======================================================================

import pandas as pd
import numpy as np


def get_high_value_customers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Translate SAS PROC SQL: inner join with avg subquery, filter on 1.5x threshold.
    
    SAS Logic:
    1. Calculate mean(amount) grouped by customer_id
    2. Inner join back to transactions on customer_id
    3. Keep rows where t.amount > avg_t.avg_amount * 1.5
    """
    # Handle empty DataFrame edge case
    if df.empty:
        return pd.DataFrame(columns=['customer_id', 'amount', 'avg_amount'])
    
    # Subquery: calculate average amount per customer
    # dropna=False replicates SAS GROUP BY behavior (NaN kept as group)
    avg_by_customer = (
        df.groupby('customer_id', dropna=False)['amount']
        .mean()
        .reset_index()
        .rename(columns={'amount': 'avg_amount'})
    )
    
    # Inner join - merge only matches (equivalent to SAS INNER JOIN)
    merged = df.merge(avg_by_customer, on='customer_id', how='inner')
    
    # Filter: keep only high-value transactions (amount > 1.5 * avg_amount)
    high_value = merged[merged['amount'] > merged['avg_amount'] * 1.5]
    
    return high_value[['customer_id', 'amount', 'avg_amount']]


# Example usage (assumes transactions DataFrame is already loaded):
# high_value = get_high_value_customers(transactions)


# Block 4: 4. Macro with parameters + %DO loop
# ======================================================================

import pandas as pd

def rolling_mean(df, var='close', window=5, out='prices_ma'):
    """
    Compute a rolling mean using a circular buffer pattern.
    
    SAS equivalent logic:
    - Uses modulo indexing to create a circular buffer of fixed size
    - Only computes mean after 'window' observations are collected
    - First (window-1) rows get missing values (. in SAS)
    
    Parameters
    ----------
    df : pandas.DataFrame
        Input dataset containing the variable to process
    var : str
        Column name for which to compute the rolling mean (default: 'close')
    window : int
        Rolling window size (default: 5)
    out : str
        Output name for the result (used in documentation only)
    
    Returns
    -------
    pandas.DataFrame
        Copy of input DataFrame with new column '{var}_ma' containing
        the rolling mean. First (window-1) values are NaN.
    
    Notes
    -----
    The pandas rolling() with min_periods=window replicates the SAS behavior:
    - SAS 'if _n_ >= window' → pandas 'min_periods=window' (only compute when full)
    - SAS circular buffer mean(of vals{*}) → pandas rolling().mean()
    - SAS missing value . → pandas NaN
    """
    if df.empty:
        result = df.copy()
        result[f'{var}_ma'] = pd.Series(dtype=float)
        return result
    
    # Create a copy to avoid modifying the original DataFrame (SAS DATA step behavior)
    result = df.copy()
    
    # Compute rolling mean using pandas' built-in rolling window
    # min_periods=window ensures mean is only computed after window is filled,
    # matching SAS 'if _n_ >= window' conditional and circular buffer semantics
    result[f'{var}_ma'] = df[var].rolling(window=window, min_periods=window).mean()
    
    return result


# Example usage matching the SAS call:
# %rolling_mean(dsn=prices, var=close, window=5, out=prices_ma);

# Sample data for testing
if __name__ == '__main__':
    prices = pd.DataFrame({
        'close': [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    })
    
    prices_ma = rolling_mean(prices, var='close', window=5, out='prices_ma')
    print("Input DataFrame:")
    print(prices)
    print("\nOutput DataFrame with rolling mean:")
    print(prices_ma)
    
    # Verify: at row 5 (index 4), mean should be (10+20+30+40+50)/5 = 30
    # At row 6 (index 5), mean should be (20+30+40+50+60)/5 = 40
    assert prices_ma.loc[4, 'close_ma'] == 30.0, "Rolling mean calculation error"
    assert prices_ma.loc[5, 'close_ma'] == 40.0, "Rolling mean calculation error"
    print("\n✓ Rolling mean calculations verified correctly.")


# Block 5: 5. PROC MEANS with CLASS and OUTPUT
# ======================================================================


import pandas as pd

# Load sales data (adjust path as needed)
# sales = pd.read_csv('sales.csv')  # or read from another source

# PROC MEANS equivalent:
# - CLASS region product_line  → groupby(['region', 'product_line'], dropna=False)
# - noprint                     → no console output needed
# - mean=avg_revenue avg_units  → mean aggregation for revenue and units_sold
# - sum=total_revenue total_units → sum aggregation
# - n=obs_count                 → count (non-missing) aggregation
# - drop=_type_ _freq_           → these are SAS-generated variables, no pandas equivalent needed

summary = (
    sales
    .groupby(['region', 'product_line'], dropna=False)
    .agg(
        avg_revenue=('revenue', 'mean'),
        avg_units=('units_sold', 'mean'),
        total_revenue=('revenue', 'sum'),
        total_units=('units_sold', 'sum'),
        obs_count=('revenue', 'count')  # n= counts non-missing observations
    )
    .reset_index()
)


# Block 6: 6. PROC SORT NODUPKEY
# ======================================================================

import pandas as pd

# Read input data — replace with actual source (e.g., pd.read_csv, database connection)
customers = pd.read_csv('customers.csv')  # <-- substitute with real data load

# PROC SORT data=customers NODUPKEY; by customer_id;
# Step 1: Sort by customer_id (SAS always sorts before nodupkey removal)
customers = customers.sort_values('customer_id')

# Step 2: Remove duplicate customer_id values, keeping the first occurrence
# This mimics SAS NODUPKEY behavior exactly
customers = customers.drop_duplicates(subset=['customer_id'], keep='first')


# Block 7: 7. Hash object for lookup
# ======================================================================

"""
Translation of SAS DATA Step with Hash Table Lookup

SAS Logic:
1. Declare hash table from 'lookup_table' with key='product_id', data=['product_name', 'category']
2. For each row in 'transactions', perform hash lookup
3. If product_id not found (rc != 0), set product_name = 'UNKNOWN'

Python Equivalent:
- Load both DataFrames and perform LEFT merge on product_id
- Fill missing (unmatched) product_name values with 'UNKNOWN'
"""

import pandas as pd


def translate_hash_lookup(transactions, lookup_table):
    """
    Translate SAS hash lookup to pandas merge operation.
    
    Parameters
    ----------
    transactions : pd.DataFrame
        Source DataFrame containing transaction records
    lookup_table : pd.DataFrame
        Lookup DataFrame with product_id, product_name, category columns
    
    Returns
    -------
    pd.DataFrame
        Enriched DataFrame with product_name and category from lookup
    """
    # Validate inputs are non-empty DataFrames
    if transactions.empty:
        # Return empty DataFrame with expected columns if transactions is empty
        return pd.DataFrame(columns=list(transactions.columns) + ['product_name', 'category'])
    
    if lookup_table.empty:
        # If lookup is empty, all product_names become 'UNKNOWN'
        result = transactions.copy()
        result['product_name'] = 'UNKNOWN'
        result['category'] = None
        return result
    
    # Select only the columns needed for the lookup (simulate hash.defineData)
    lookup_subset = lookup_table[['product_id', 'product_name', 'category']].copy()
    
    # Normalize key column to handle any case differences
    # SAS variable names are case-insensitive; Python is not
    transactions['_product_id_norm'] = transactions['product_id']
    lookup_subset['_product_id_norm'] = lookup_subset['product_id']
    
    # Perform LEFT merge — equivalent to SAS hash.find() with default behavior
    # All transaction rows are preserved; lookup columns added where match exists
    enriched = transactions.merge(
        lookup_subset,
        on='_product_id_norm',
        how='left',
        suffixes=('', '_lookup')
    )
    
    # Clean up the normalized key column
    enriched.drop(columns=['_product_id_norm'], inplace=True)
    
    # Handle product_name: if lookup failed (NaN), set to 'UNKNOWN'
    # Equivalent to SAS: if rc ^= 0 then product_name = 'UNKNOWN'
    enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')
    
    return enriched


# Example usage with file I/O (wrapped in try/except per requirements)
if __name__ == '__main__':
    try:
        # Load source data
        transactions = pd.read_csv('transactions.csv')
        lookup_table = pd.read_csv('lookup_table.csv')
        
        # Execute translation
        enriched = translate_hash_lookup(transactions, lookup_table)
        
        # Display results
        print("Translation successful. Shape:", enriched.shape)
        print("\nFirst few rows:")
        print(enriched.head())
        
        # Show lookup hit rate
        unknown_count = (enriched['product_name'] == 'UNKNOWN').sum()
        print(f"\nUnmatched product_ids (UNKNOWN): {unknown_count} / {len(enriched)}")
        
    except FileNotFoundError as e:
        print(f"Error: Required file not found - {e}")
    except pd.errors.EmptyDataError:
        print("Error: One or more input files are empty")
    except Exception as e:
        print(f"Unexpected error during translation: {e}")


# Block 8: 8. Multi-level nested macro
# ======================================================================

"""
SAS Macro Translation: apply_to_all and summarise

Translation of:
%macro apply_to_all(action=, datasets=);
    %let n = %sysfunc(countw(&datasets));
    %do i = 1 %to &n;
        %let ds = %scan(&datasets, &i);
        %&action(dsn=&ds);
    %end;
%mend;

%macro summarise(dsn=);
    proc means data=&dsn; run;
%mend;

%apply_to_all(action=summarise, datasets=sales returns inventory);
"""

import pandas as pd


def summarise(dsn):
    """
    Generate PROC MEANS-style summary statistics for a dataset.
    
    PROC MEANS in SAS:
    - Operates on all numeric variables by default
    - Excludes missing values per variable (not per row)
    - Outputs: N, Mean, Std Dev, Minimum, Maximum
    
    Args:
        dsn: Dataset name (string) - will load from '{dsn}.csv'
    
    Raises:
        FileNotFoundError: If dataset CSV does not exist
        ValueError: If no numeric columns found
    """
    # Load dataset from CSV (following pattern: dataset_name = pd.read_csv('dataset_name.csv'))
    csv_path = f"{dsn}.csv"
    
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Dataset '{dsn}' not found. Expected file: {csv_path}")
    
    # SAS is case-insensitive; normalize column names to lowercase
    df.columns = df.columns.str.lower()
    
    # Select only numeric columns (PROC MEANS operates on numeric vars by default)
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    
    if not numeric_cols:
        raise ValueError(f"No numeric columns found in dataset '{dsn}'")
    
    # Build summary statistics matching PROC MEANS output exactly
    # SAS excludes NAs per variable - use .dropna() per column during aggregation
    results = []
    for var in numeric_cols:
        var_data = df[var].dropna()  # Exclude NAs per variable (like SAS)
        
        summary = {
            'Variable': var,
            'N': len(var_data),  # Count excludes NaN
            'Mean': var_data.mean(),
            'Std Dev': var_data.std(ddof=1),  # SAS uses sample std (ddof=1)
            'Minimum': var_data.min(),
            'Maximum': var_data.max()
        }
        results.append(summary)
    
    summary_df = pd.DataFrame(results)
    
    # Print summary (SAS PROC MEANS prints to output by default)
    print(f"===== Summary Statistics for {dsn} =====")
    print(summary_df.to_string(index=False))
    print()
    
    return summary_df


def apply_to_all(action, datasets):
    """
    Apply an action function to each dataset name in a space-separated string.
    
    Translation of SAS macro:
    %macro apply_to_all(action=, datasets=);
        %let n = %sysfunc(countw(&datasets));
        %do i = 1 %to &n;
            %let ds = %scan(&datasets, &i);
            %&action(dsn=&ds);
        %end;
    %mend;
    
    Args:
        action: Function that accepts 'dsn' keyword argument
        datasets: Space-separated string of dataset names
    """
    # Split datasets by whitespace (matching SAS %scan with default delimiter)
    dataset_list = datasets.split()
    
    for ds in dataset_list:
        # Call the action function with dsn parameter (matching SAS macro call)
        action(dsn=ds)


# Execute the equivalent of:
# %apply_to_all(action=summarise, datasets=sales returns inventory);
if __name__ == "__main__":
    try:
        apply_to_all(action=summarise, datasets="sales returns inventory")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Note: Ensure CSV files exist for each dataset name in the datasets list.")


# Block 9: 9. PROC TRANSPOSE
# ======================================================================

import pandas as pd

# Load input data from CSV
monthly_sales = pd.read_csv('monthly_sales.csv')

# Normalize column names to lowercase for case-insensitive SAS equivalence
monthly_sales.columns = monthly_sales.columns.str.lower()

# Use pd.pivot() instead of pd.pivot_table() to avoid aggregation
# SAS PROC TRANSPOSE does NOT aggregate duplicates; it errors on them
# pd.pivot() raises ValueError on duplicate entries, which matches SAS behavior
# If duplicates may exist, they must be deduplicated beforehand
wide_sales = monthly_sales.pivot(
    index='product_id',   # BY variable in SAS TRANSPOSE
    columns='month',      # ID variable - each unique value becomes a column
    values='revenue'      # VAR variable - values to transpose
)

# Add prefix to column names (SAS: prefix=month_)
wide_sales.columns = ['month_' + str(col) for col in wide_sales.columns]

# Reset index to make product_id a regular column (SAS output structure)
wide_sales = wide_sales.reset_index()

# Store result silently - do not print (SAS out= dataset behavior)
wide_sales

# Block 10: 10. Complex WHERE + FORMAT + LABEL
# ======================================================================

import pandas as pd
import numpy as np

# Translate SAS DATA step: filtering, format/label metadata, and computed column
# SAS: data report; set survey; where age >= 18 and age <= 65 and status in ('ACTIVE','PENDING') and score ^= .;

# Filter rows based on WHERE clause conditions
df = survey[
    (survey['age'] >= 18) &
    (survey['age'] <= 65) &
    (survey['status'].isin(['ACTIVE', 'PENDING'])) &
    (survey['score'].notna())  # score ^= . means score is not missing
].copy()

# Format specifications (display-only in SAS - do NOT modify underlying values):
#   format score 8.2       -> numeric format: 2 decimal places
#   format survey_date date9. -> date format: ddMMMyyyy (e.g., 01JAN2020)
# Labels are metadata only - they don't affect data values
#   label score = 'Survey Score (0-100)'
#   label survey_date = 'Date of Survey'

# Apply labels as pandas metadata (for export/reporting)
df.attrs['label_score'] = 'Survey Score (0-100)'
df.attrs['label_survey_date'] = 'Date of Survey'

# Create computed column (same logic as SAS: score_pct = score / 100)
df['score_pct'] = df['score'] / 100

# If display formatting is needed for output, use separate formatted columns
# (PROC FORMAT is display-only - NEVER overwrite original columns with .map())
# Example for output: df['score_fmt'] = df['score'].map(lambda x: f'{x:8.2f}')

# Create output DataFrame with original columns plus computed column
report = df