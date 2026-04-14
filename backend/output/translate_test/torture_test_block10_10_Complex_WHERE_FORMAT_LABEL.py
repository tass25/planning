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