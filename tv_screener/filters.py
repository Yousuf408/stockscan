# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER FILTERS MODULE
# Gap filter, Sector filter, Previous High distance calculation
# ═══════════════════════════════════════════════════════════════════════════════

import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: GAP PERCENTAGE CALCULATION
# ─────────────────────────────────────────────────────────────────────────────

def calc_gap_pct(row):
    """
    Calculate opening gap % — (Open - PrevClose) / PrevClose * 100.
    
    Positive = gap up, Negative = gap down.
    Used to filter out stocks with excessive gap moves (>±2%).
    
    Args:
        row (pd.Series): Row from TV screener data
                        Must have 'open' and 'close[1]' columns
    
    Returns:
        float: Gap percentage, or 0 if calculation fails
    """
    try:
        open_price = float(row.get('open', 0) or 0)
        prev_close = float(row.get('close[1]', 0) or 0)  # close[1] = previous day close
        if prev_close == 0:
            return 0
        return ((open_price - prev_close) / prev_close) * 100
    except:
        return 0


def apply_gap_filter(df, max_gap_pct=2.0):
    """
    Filter out stocks with gap move > ±max_gap_pct.
    
    Removes stocks with excessive overnight gaps — focus on close-range moves.
    
    Args:
        df (pd.DataFrame): TV screener data with 'open' and 'close[1]' columns
        max_gap_pct (float): Max acceptable gap % (default 2.0)
    
    Returns:
        pd.DataFrame: Filtered dataframe
    """
    df = df.copy()
    df['_opening_gap'] = df.apply(calc_gap_pct, axis=1)
    df = df[df['_opening_gap'].abs() <= max_gap_pct]
    df = df.drop(columns=['_opening_gap'], errors='ignore')
    return df

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: PREVIOUS HIGH DISTANCE CALCULATION
# ─────────────────────────────────────────────────────────────────────────────

def calc_prev_high_dist(row):
    """
    Calculate distance from current price to previous day's high (as %).
    
    Positive = price above previous high (bullish), 
    Negative = below previous high (consolidating).
    
    Args:
        row (pd.Series): Row from TV screener data
                        Must have 'close' and 'high[1]' columns
    
    Returns:
        float: Distance % (rounded to 2 decimals), or None if calculation fails
    """
    try:
        price    = float(row.get('close', 0) or 0)
        prev_high = float(row.get('high[1]', 0) or 0)
        if prev_high == 0:
            return None
        return round(((price - prev_high) / prev_high) * 100, 2)
    except:
        return None


def get_prev_high_val(row):
    """
    Extract previous day's high value for display.
    
    Args:
        row (pd.Series): Row from TV screener data
                        Must have 'high[1]' column
    
    Returns:
        float: Previous high value, or None if invalid
    """
    try:
        v = float(row.get('high[1]', 0) or 0)
        return v if v > 0 else None
    except:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: SECTOR FILTER
# ─────────────────────────────────────────────────────────────────────────────

def apply_sector_filter(df, sector):
    """
    Filter dataframe by sector.
    
    Args:
        df (pd.DataFrame): Data with 'Sector' column
        sector (str): Sector to filter for (e.g., "Technology")
                     Pass 'All' to skip filter
    
    Returns:
        pd.DataFrame: Filtered dataframe (or original if sector='All')
    """
    if sector == 'All':
        return df
    return df[df['Sector'] == sector].copy()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: CROSSOVER FILTER
# ─────────────────────────────────────────────────────────────────────────────

def apply_crossover_filter(df, match_type="09:15"):
    """
    Filter to only rows where crossover signal matches expected type.
    
    Args:
        df (pd.DataFrame): Data with 'Crossover' column
        match_type (str): "09:15" for strict match, "09:20" for flexible, 
                         "" for no match
    
    Returns:
        pd.DataFrame: Filtered dataframe
    """
    return df[df['Crossover'] == match_type].copy()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: EMA COIL FILTER
# ─────────────────────────────────────────────────────────────────────────────

def apply_ema_coil_filter(df, min_threshold=70.0):
    """
    Filter to stocks with EMA coil percentage >= min_threshold.
    
    High consolidation % indicates tight EMA range.
    
    Args:
        df (pd.DataFrame): Data with 'EmaCoilPct' column
        min_threshold (float): Minimum EMA coil % (default 70)
    
    Returns:
        pd.DataFrame: Filtered dataframe
    """
    return df[df['EmaCoilPct'] >= min_threshold].copy()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: RELATIVE VOLUME FILTER
# ─────────────────────────────────────────────────────────────────────────────

def apply_relvol_filter(df, min_relvol=1.0):
    """
    Filter to stocks with relative volume (5D) >= min_relvol.
    
    Volume spike indicator — higher = more buying activity relative to baseline.
    
    Args:
        df (pd.DataFrame): Data with 'RelVol5D' column
        min_relvol (float): Minimum relative volume multiplier (default 1.0)
    
    Returns:
        pd.DataFrame: Filtered dataframe
    """
    return df[df['RelVol5D'] >= min_relvol].copy()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: BATCH FILTER APPLICATION
# ─────────────────────────────────────────────────────────────────────────────

def apply_all_filters(df, gap_pct=2.0, sector='All', crossover_match="09:15", 
                      ema_coil_min=None, relvol_min=None):
    """
    Apply all filters in sequence (pipeline pattern).
    
    Args:
        df (pd.DataFrame): Input data
        gap_pct (float): Max gap % filter
        sector (str): Sector filter ('All' = no filter)
        crossover_match (str): "09:15", "09:20", or "" for crossover filter
        ema_coil_min (float, optional): Min EMA coil % (None = skip)
        relvol_min (float, optional): Min RelVol5D (None = skip)
    
    Returns:
        pd.DataFrame: Fully filtered dataframe
    """
    df = df.copy()
    df = apply_gap_filter(df, max_gap_pct=gap_pct)
    df = apply_sector_filter(df, sector)
    df = apply_crossover_filter(df, match_type=crossover_match)
    if ema_coil_min is not None:
        df = apply_ema_coil_filter(df, min_threshold=ema_coil_min)
    if relvol_min is not None:
        df = apply_relvol_filter(df, min_relvol=relvol_min)
    return df
