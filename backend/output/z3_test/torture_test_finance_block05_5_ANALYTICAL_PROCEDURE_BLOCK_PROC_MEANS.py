import pandas as pd

# Read source data (adjust file format as needed)
df = pd.read_parquet('staging/joined_master')

# PROC MEANS with CLASS variables: region, status
# Statistics: N, MEAN, STD, MIN, MAX
# OUTPUT: MEAN=avg_balance, SUM=total_regional_val
#
# NWAY behavior: pandas groupby on all CLASS vars = full cross-classification
# dropna=False: SAS CLASS includes missing as a group (pandas drops NaN by default)
summary_stats = df.groupby(['region', 'status'], dropna=False).agg(
    N=('total_balance', 'count'),
    avg_balance=('total_balance', 'mean'),
    total_regional_val=('total_balance', 'sum'),
    STD=('total_balance', 'std'),
    MIN=('total_balance', 'min'),
    MAX=('total_balance', 'max')
).reset_index()

# Write to output (SAS WORK library = temporary; adjust path as needed)
summary_stats.to_parquet('work/summary_stats.parquet', index=False)