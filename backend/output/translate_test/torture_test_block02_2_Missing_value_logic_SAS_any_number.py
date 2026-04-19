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
