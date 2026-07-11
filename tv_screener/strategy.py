# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER — STRATEGY MODULE (CORE DECISION LOGIC ONLY)
#
#   1. Data Fetch (TradingView + yfinance)
#   2. POC (Point of Control) Calculation
#   3. Crossover Signal — CORE ENTRY (POC + EMA + Body% + Gap)
#
# This file answers ONE question: "Should this stock trigger a BUY signal?"
# Everything else (date helpers, market hours, EMA coil analysis, entry-candle
# confirmation, 5-day volume, sector/prev-high filters) lives in backend.py —
# those are supporting/analysis utilities, not the entry decision itself.
# ═══════════════════════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import pytz
import time
from tradingview_screener import Query
from tradingview_screener.column import col

from .backend import get_last_trading_day

IST = pytz.timezone("Asia/Kolkata")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: DATA FETCH — TRADINGVIEW + YFINANCE
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_tv_data():
    """
    Fetch top gainer stocks from TradingView Screener — the stock universe
    this strategy operates on.

    CRITERIA:
      - Market: India (NSE)
      - Market cap: > ₹41B — liquidity filter
      - Price: At or near 1-month high — momentum/strength filter
      - Sorted by % change (descending)

    Returns:
        tuple: (count, dataframe, error_message)
    """
    try:
        count, df = (Query()
            .select(
                'name', 'close', 'change', 'volume',
                'relative_volume', 'market_cap_basic', 'sector',
                'High.1M', 'high', 'open', 'close[1]', 'high[1]'
            )
            .set_markets('india')
            .where(
                col('market_cap_basic') > 41_000_000_000,
                col('exchange') == 'NSE',
                col('high') >= col('High.1M'),
            )
            .order_by('change', ascending=False)
            .limit(100)
            .get_scanner_data()
        )
        return count, df, None
    except Exception as e:
        return 0, pd.DataFrame(), str(e)


def clean_tv_data(df):
    """
    Clean and standardize TradingView screener output into strategy-ready columns.

    Returns:
        pd.DataFrame: [Symbol, Price, Chg, Volume, RelVol, MktCap, Sector]
                      (plus raw high/open/close[1]/high[1] retained for gap calc)
    """
    df = df.copy()
    df['change']           = df['change'].round(2)
    df['relative_volume']  = df['relative_volume'].round(2)
    df['market_cap_basic'] = (df['market_cap_basic'] / 1e9).round(1)
    df['name'] = df['ticker'].str.replace('NSE:', '', regex=False)
    df = df.drop(columns=['ticker'], errors='ignore')
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


def prepare_tv_data_for_processing(df):
    """
    Drop temporary TV columns after gap/prev-high calculations are done.

    Returns:
        pd.DataFrame: Ready-for-processing data
    """
    df = df.copy()
    df = df.drop(columns=['high', 'High.1M', 'open', 'close[1]', 'high[1]'], errors='ignore')
    return df


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: POC (POINT OF CONTROL) CALCULATION
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_poc_from_df(df_day, num_bins=50):
    """
    Calculate POC from a day's 5-minute candles using fixed-range volume
    profile (FRVP): distribute each candle's volume proportionally across
    the price bins it spans; the bin with max volume = POC.

    Args:
        df_day (pd.DataFrame): One day's OHLCV data (5min candles)
        num_bins (int): Number of price bins

    Returns:
        float: POC price, or None if invalid
    """
    price_min = df_day['Low'].min()
    price_max = df_day['High'].max()
    if price_max <= price_min:
        return None

    bins = np.linspace(price_min, price_max, num_bins + 1)
    bin_volumes = np.zeros(num_bins)

    for _, row in df_day.iterrows():
        low, high, vol = row['Low'], row['High'], row['Volume']
        if high == low:
            idx = np.digitize(low, bins) - 1
            idx = min(max(idx, 0), num_bins - 1)
            bin_volumes[idx] += vol
            continue
        for i in range(num_bins):
            bin_low, bin_high = bins[i], bins[i+1]
            overlap = min(high, bin_high) - max(low, bin_low)
            if overlap > 0:
                proportion = overlap / (high - low)
                bin_volumes[i] += vol * proportion

    bin_centers = (bins[:-1] + bins[1:]) / 2
    poc_idx = np.argmax(bin_volumes)
    return round(float(bin_centers[poc_idx]), 2)


def fetch_poc_once(symbol, num_bins=50):
    """Single POC fetch attempt — yesterday's complete 5min data."""
    try:
        last_day = get_last_trading_day()
        ticker = symbol + ".NS"
        df = yf.download(ticker, start=last_day, end=last_day + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        df = df.between_time("09:15", "15:30")
        if df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return calculate_poc_from_df(df, num_bins=num_bins)
    except:
        return None


def get_yesterday_poc(symbol, num_bins=50, max_attempts=3, tolerance_pct=0.5):
    """
    Robust POC fetch with retry & stability check — yfinance data can shift
    slightly between fetches. Accept only if two consecutive fetches match
    within tolerance_pct; retry up to max_attempts otherwise.

    Returns:
        float: Stable POC value, or None if all fetches failed
    """
    prev_val = None
    for attempt in range(max_attempts):
        current_val = fetch_poc_once(symbol, num_bins=num_bins)
        if current_val is None:
            return None
        if prev_val is not None:
            diff_pct = abs(current_val - prev_val) / prev_val * 100 if prev_val else 0
            if diff_pct <= tolerance_pct:
                return current_val
        prev_val = current_val
        if attempt < max_attempts - 1:
            time.sleep(2)
    return prev_val


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: CROSSOVER SIGNAL — CORE ENTRY (POC + EMA + BODY% + GAP)
# ═══════════════════════════════════════════════════════════════════════════════

def calc_candle_body_pct(open_, high_, low_, close_):
    """
    Candle body size as % of its total High-Low range.
    Body % = |Close - Open| / (High - Low) * 100

    High body % (>=70%) = strong directional candle (not a doji).

    Returns:
        float: Body percentage (0-100), or None if candle is flat (High==Low)
    """
    candle_range = high_ - low_
    if candle_range <= 0:
        return None
    return abs(close_ - open_) / candle_range * 100


def calc_gap_pct(row):
    """
    Opening gap % — (Open - PrevClose) / PrevClose * 100.
    Positive = gap up, Negative = gap down.

    Args:
        row (pd.Series): Must have 'open' and 'close[1]' columns

    Returns:
        float: Gap percentage, or 0 if calculation fails
    """
    try:
        open_price = float(row.get('open', 0) or 0)
        prev_close = float(row.get('close[1]', 0) or 0)
        if prev_close == 0:
            return 0
        return ((open_price - prev_close) / prev_close) * 100
    except:
        return 0


def apply_gap_filter(df, max_gap_pct=2.0):
    """
    STRATEGY RULE: Reject stocks with overnight gap > ±2%.
    Part of the core entry decision — excessive gaps are excluded upfront.

    Args:
        df (pd.DataFrame): TV data with 'open' and 'close[1]' columns
        max_gap_pct (float): Max acceptable gap % (default 2.0)

    Returns:
        pd.DataFrame: Filtered dataframe
    """
    df = df.copy()
    df['_opening_gap'] = df.apply(calc_gap_pct, axis=1)
    df = df[df['_opening_gap'].abs() <= max_gap_pct]
    df = df.drop(columns=['_opening_gap'], errors='ignore')
    return df


def get_crossover_signal(symbol, poc_value, fast_span=9, slow_span=20, min_body_pct=70):
    """
    THE CORE ENTRY SIGNAL of this strategy.

    Detects a 9EMA -> 20EMA bullish crossover, confirmed by price trading
    above yesterday's POC, checked at two candles:

      A) 9:15 candle (CLOSED, STRICT):
         - 9EMA was BELOW 20EMA yesterday
         - 9EMA is now ABOVE 20EMA at 9:15 close
         - 9:15 candle Close > yesterday's POC
         - Candle body >= min_body_pct% of (High - Low)

      B) 9:20 candle (flexible — closed or still forming):
         - Same EMA + POC conditions, NO body-check

    Args:
        symbol (str): Stock symbol
        poc_value (float): Yesterday's POC (from get_yesterday_poc)
        fast_span (int): Fast EMA period (default 9)
        slow_span (int): Slow EMA period (default 20)
        min_body_pct (float): Min body % for 9:15 strict match (default 70)

    Returns:
        str: "09:15" (strict) / "09:20" (flexible) / "" (no match)
    """
    try:
        if poc_value is None:
            return ""

        last_day = get_last_trading_day()
        today = datetime.now(IST).date()
        ticker = symbol + ".NS"
        df = yf.download(ticker, start=last_day, end=today + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return ""
        df.index = pd.to_datetime(df.index)
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        df = df.between_time("09:15", "15:30")
        if df.empty:
            return ""

        df['EMA_fast'] = df['Close'].ewm(span=fast_span, adjust=False).mean()
        df['EMA_slow'] = df['Close'].ewm(span=slow_span, adjust=False).mean()

        df_yesterday = df[df.index.date == last_day]
        df_today     = df[df.index.date == today]

        if df_yesterday.empty or df_today.empty:
            return ""

        yesterday_last_fast = df_yesterday['EMA_fast'].iloc[-1]
        yesterday_last_slow = df_yesterday['EMA_slow'].iloc[-1]
        was_below = yesterday_last_fast < yesterday_last_slow

        if not was_below:
            return ""

        def check_candle(candle_time_str, require_body_check=False):
            df_candle = df_today.between_time(candle_time_str, candle_time_str)
            if df_candle.empty:
                return False
            row = df_candle.iloc[0]
            open_  = float(row['Open'])
            high_  = float(row['High'])
            low_   = float(row['Low'])
            close_ = float(row['Close'])
            fast_  = float(row['EMA_fast'])
            slow_  = float(row['EMA_slow'])

            basic_ok = (fast_ > slow_) and (close_ > poc_value)
            if not basic_ok:
                return False

            if require_body_check:
                body_pct = calc_candle_body_pct(open_, high_, low_, close_)
                if body_pct is None or body_pct < min_body_pct:
                    return False

            return True

        if check_candle("09:15", require_body_check=True):
            return "09:15"

        if check_candle("09:20", require_body_check=False):
            return "09:20"

        return ""
    except:
        return ""
