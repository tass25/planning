import pandas as pd
import numpy as np

# Define the format mapping dictionary (display-only - mirrors SAS VALUE $grade)
# Maps account status values to color labels
grade_color_map = {
    'OVERDRAWN': 'Red',
    'ACTIVE':    'Green',
    'DORMANT':   'Yellow'
}

# Create a NEW column for the formatted display values
# The original 'status' column is preserved for downstream logic (PROC FREQ, WHERE, etc.)
# .map() returns NaN for unmapped values, .fillna() handles SAS OTHER case
df['status_color'] = df['status'].map(grade_color_map).fillna('Gray')

# If downstream code needs to filter by color, use the new column:
# df[df['status_color'] == 'Red']   # equivalent to SAS WHERE status='OVERDRAWN'
# df[df['status_color'] == 'Green'] # equivalent to SAS WHERE status='ACTIVE'
