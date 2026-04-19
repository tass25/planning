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
