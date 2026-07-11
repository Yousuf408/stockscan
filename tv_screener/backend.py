# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER BACKEND MODULE
# TradingView screener data fetch + orchestration logic
# ═══════════════════════════════════════════════════════════════════════════════

import pandas as pd
from tradingview_screener import Query
from tradingview_screener.column import col

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: TRADINGVIEW SCREENER DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_tv_data():
    """
    Fetch top gainer stocks from TradingView Screener.
    
    Criteria:
      - Market: India (NSE)
      - Market cap: > ₹41B (~$500M USD)
      - Price: At or near 1-month high
      - Sorted by % change (descending)
    
    Returns:
        tuple: (count, dataframe, error_message)
               - count (int): Number of stocks fetched
               - dataframe (pd.DataFrame): Screener results with columns:
                 [name, close, change, volume, relative_volume, market_cap_basic, 
                  sector, High.1M, high, open, close[1], high[1]]
               - error_message (str or None): Error string if fetch failed
    """
    try:
        count, df = (Query()
            .select(
                'name',                # Stock name
                'close',               # Current price
                'change',              # % change today
                'volume',              # Current volume
                'relative_volume',     # Relative volume (vs avg)
                'market_cap_basic',    # Market cap in currency units
                'sector',              # Sector classification
                'High.1M',             # 1-month high
                'high',                # Today's high
                'open',                # Today's open
                'close[1]',            # Yesterday's close
                'high[1]'              # Yesterday's high
            )
            .set_markets('india')      # NSE only
            .where(
                col('market_cap_basic') > 41_000_000_000,  # Mkt cap > ₹41B
                col('exchange') == 'NSE',
                col('high') >= col('High.1M'),             # At/near 1M high
            )
            .order_by('change', ascending=False)           # Sort by change desc
            .limit(100)                                     # Large buffer
            .get_scanner_data()
        )
        return count, df, None
    except Exception as e:
        return 0, pd.DataFrame(), str(e)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DATA CLEANING & PREPARATION
# ─────────────────────────────────────────────────────────────────────────────

def clean_tv_data(df):
    """
    Clean and standardize TradingView screener output.
    
    Operations:
      - Round numeric columns to appropriate decimals
      - Extract symbol from ticker format (NSE:RELIANCE → RELIANCE)
      - Convert market cap to billions
      - Standardize column names for downstream processing
    
    Args:
        df (pd.DataFrame): Raw TradingView screener data
    
    Returns:
        pd.DataFrame: Cleaned data with columns:
                      [Symbol, Price, Chg, Volume, RelVol, MktCap, Sector]
    """
    df = df.copy()
    
    # Round numerics
    df['change']           = df['change'].round(2)
    df['relative_volume']  = df['relative_volume'].round(2)
    df['market_cap_basic'] = (df['market_cap_basic'] / 1e9).round(1)
    
    # Extract symbol (NSE:RELIANCE → RELIANCE)
    df['name'] = df['ticker'].str.replace('NSE:', '', regex=False)
    df = df.drop(columns=['ticker'], errors='ignore')
    
    # Standardize column names
    df = df.rename(columns={
        'name'            : 'Symbol',
        'close'           : 'Price',
        'change'          : 'Chg',
        'volume'          : 'Volume',
        'relative_volume' : 'RelVol',
        'market_cap_basic': 'MktCap',
        'sector'          : 'Sector',
    })
    
    return df

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DATA ENRICHMENT
# ─────────────────────────────────────────────────────────────────────────────

def enrich_tv_data(df, gap_filter_applied=False, prev_high_dist=None, prev_high_val=None):
    """
    Add calculated fields to cleaned TV data (for display pipeline).
    
    Args:
        df (pd.DataFrame): Cleaned TV data
        gap_filter_applied (bool): Whether gap filter was already applied
        prev_high_dist (pd.Series, optional): Previous high distance %
        prev_high_val (pd.Series, optional): Previous high value
    
    Returns:
        pd.DataFrame: Data with added fields
    """
    df = df.copy()
    
    if prev_high_dist is not None:
        df['PrevHighDist'] = prev_high_dist
    if prev_high_val is not None:
        df['PrevHighVal'] = prev_high_val
    
    return df

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DATA PREPARATION FOR PROCESSING
# ─────────────────────────────────────────────────────────────────────────────

def prepare_tv_data_for_processing(df):
    """
    Prepare TV data for main processing pipeline.
    
    Removes temporary columns (open, close[1], high[1], high, High.1M)
    and ensures data consistency before calculations begin.
    
    Args:
        df (pd.DataFrame): TV data to prepare
    
    Returns:
        pd.DataFrame: Ready-for-processing data
    """
    df = df.copy()
    df = df.drop(columns=['high', 'High.1M', 'open', 'close[1]', 'high[1]'], errors='ignore')
    return df
