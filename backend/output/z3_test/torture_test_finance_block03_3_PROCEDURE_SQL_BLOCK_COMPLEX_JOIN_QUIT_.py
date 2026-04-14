
import pandas as pd

# Define threshold (macro variable from SAS)
threshold = 1000  # Replace with actual value or pass as parameter

# Read source tables with error handling
try:
    df_accounts = pd.read_parquet('staging/cleaned_accounts.parquet')
except Exception as e:
    raise FileNotFoundError(f"Failed to read staging.cleaned_accounts: {e}")

try:
    df_region_map = pd.read_parquet('raw_src/region_map.parquet')
except Exception as e:
    raise FileNotFoundError(f"Failed to read raw_src.region_map: {e}")

# Normalize column names to lowercase for consistent matching
# (SAS is case-insensitive; pandas is not)
df_accounts.columns = df_accounts.columns.str.lower()
df_region_map.columns = df_region_map.columns.str.lower()

# Perform LEFT JOIN equivalent using pd.merge
# NOTE: indicator=True NOT used here (only for DATA STEP MERGE per translation rules)
merged_df = pd.merge(
    df_accounts,
    df_region_map,
    left_on='region_code',
    right_on='code',
    how='left'
)

# WHERE clause: filter rows where balance > threshold
# Handle edge case: if column is not numeric, coerce or raise error
if 'balance' not in merged_df.columns:
    raise KeyError("Column 'balance' not found in merged DataFrame")

filtered_df = merged_df[merged_df['balance'] > threshold].copy()

# GROUP BY: account_id, status, region, manager_id with SUM(balance) as total_balance
# dropna=False preserves NaN as a group (matching SAS GROUP BY behavior)
grouped = filtered_df.groupby(
    ['account_id', 'status', 'region', 'manager_id'],
    dropna=False,
    as_index=False
).agg(total_balance=('balance', 'sum'))

# ORDER BY total_balance DESC
result = grouped.sort_values('total_balance', ascending=False).reset_index(drop=True)

# Write output with error handling
try:
    result.to_parquet('staging/joined_master.parquet', index=False)
except Exception as e:
    raise IOError(f"Failed to write staging.joined_master: {e}")

print(f"Successfully created staging.joined_master with {len(result)} rows")
