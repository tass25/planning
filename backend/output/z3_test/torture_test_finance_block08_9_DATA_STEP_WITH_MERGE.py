import pandas as pd
import numpy as np

# Assuming process_date is provided as a Python string variable (from SAS macro variable)
process_date = "&process_date"  # Replace with actual macro value source

# Load source DataFrames
joined_master = staging_joined_master.copy()
manual_adjustments = work_manual_adjustments.copy()

# Normalize column names to lowercase (SAS is case-insensitive, Python is NOT)
joined_master.columns = joined_master.columns.str.lower()
manual_adjustments.columns = manual_adjustments.columns.str.lower()

# Select only needed columns from adjustments (exclude extra columns to prevent Cartesian explosion)
adjustments_subset = manual_adjustments[['account_id', 'adjustment_amt']].copy()

# MERGE: pd.merge with indicator=True to track IN= variables
# how='left' + filter to left_only/both = SAS MERGE + IF a;
merged = pd.merge(
    joined_master,
    adjustments_subset,
    on='account_id',
    how='left',
    indicator=True
)

# IF a: keep all records from primary table (joined_master)
merged = merged[merged['_merge'].isin(['left_only', 'both'])].copy()

# IF b THEN: conditional update — only where manual_adjustments matched
# Vectorized: only update rows where _merge == 'both'
mask_b = merged['_merge'] == 'both'
merged.loc[mask_b, 'total_balance'] = (
    merged.loc[mask_b, 'total_balance'] + merged.loc[mask_b, 'adjustment_amt']
)

# Extract MONTH and YEAR from process_date macro variable
# SAS SUBSTR positions are 1-based; Python slicing is 0-based
# "%SUBSTR(&process_date, 3, 3)" -> characters at positions 3-5 -> indices [2:5]
# "%SUBSTR(&process_date, 6, 4)" -> characters at positions 6-9 -> indices [5:9]
merged['MONTH'] = process_date[2:5]
merged['YEAR'] = process_date[5:9]

# FORMAT status $grade.;
# CRITICAL FIX: SAS FORMAT is display-only and must NOT overwrite the original column.
# Create a NEW formatted column for display purposes only.
grade_format = {'A': 'Excellent', 'B': 'Good', 'C': 'Fair', 'D': 'Poor', 'F': 'Failing'}
# Note: Format mapping is illustrative; use actual $grade. format definition
merged['status_fmt'] = merged['status'].map(grade_format).fillna('Other')

# Clean up temporary merge indicator column
merged = merged.drop(columns=['_merge'])

# merged is now the equivalent of final.monthly_report