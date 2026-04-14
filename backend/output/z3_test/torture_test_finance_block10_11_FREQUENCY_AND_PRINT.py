import pandas as pd
import numpy as np

# Assuming 'final_monthly_report' and 'summary_stats' are DataFrames

def proc_freq(df):
    # PROC FREQ equivalent: region * status / NOCOL NOPERCENT
    freq_table = pd.crosstab(df['region'], df['status'])
    return freq_table

# Use the function
freq_result = proc_freq(final_monthly_report)
print(freq_result)


def proc_print_preview(df):
    # PROC PRINT equivalent: OBS=10
    preview = df.head(10)
    return preview

# Use the function
preview_result = proc_print_preview(summary_stats)
print(preview_result)