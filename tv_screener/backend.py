# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER — BACKEND MODULE (SUPPORTING / ANALYSIS UTILITIES)
#
# Everything that supports the strategy but is NOT the core entry decision:
#   1. Date/Time & Market Hours Helpers
#   2. EMA Coil Check (separate consolidation analysis)
#   3. Entry Candle Signals (9:40 / 9:45 / 9:50 — post-entry confirmation)
#   4. 5-Day Median Volume (relative volume baseline)
#   5. Filters (Sector, Previous High, Crossover-result, EMA Coil, RelVol)
#
# The actual BUY decision logic (TV+yfinance fetch, POC, Crossover signal
# with EMA+Body%+Gap) lives in strategy.py — kept separate on purpose.
# ═══════════════════════════════════════════════════════════════════════════════

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import pytz

IST = pytz.timezone("Asia/Kolkata")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: DATE/TIME & MARKET HOURS HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_trading_day_before(date):
    """
    Given a date, find the last trading day before it (exclude weekends,
    verify via yfinance that the day actually has data).
    """
    candidate = date - timedelta(days=1)
    attempts = 0
    while attempts < 10:
        if candidate.weekday() >= 5:  # Saturday=5, Sunday=6
            candidate -= timedelta(days=1)
            attempts += 1
            continue
        try:
            test_df = yf.download("^NSEI", start=candidate, end=candidate + timedelta(days=1),
                                  interval="1d", progress=False, auto_adjust=True)
            if not test_df.empty:
                return candidate
        except:
            pass
        candidate -= timedelta(days=1)
        attempts += 1
    candidate = date - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def get_last_trading_day():
    """
    Get the last complete trading day — reference day used for POC / EMA
    Coil calculations (yesterday's data).
    """
    now = datetime.now(IST)
    today = now.date()
    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        today = today - timedelta(days=1)
    tv_ref = get_trading_day_before(today + timedelta(days=1))
    poc_date = get_trading_day_before(tv_ref)
    return poc_date


def get_current_ist_time():
    """Get current time in IST."""
    return datetime.now(IST)


def is_market_hours():
    """
    Check if current time is within market trading hours (9:15 AM - 3:30 PM IST).
    Used to gate live re-calculation (avoid wasted API calls after close).
    """
    now = datetime.now(IST)
    market_open  = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: EMA CONSOLIDATION ("EMA COIL") CHECK — SEPARATE ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def get_ema_consolidation_pct(symbol, ema_span=20, tolerance_pct=0.5):
    """
    Calculate % of yesterday's candles where Close is within ±tolerance_pct
    of the 20 EMA — indicates a tight consolidation/coil phase.

    This is a supporting analysis metric (displayed alongside the entry
    signal) — NOT part of the core crossover entry decision itself.

    Fetches 2 days (day-before + yesterday) to warm up the EMA, then only
    measures % on yesterday's candles.

    Returns:
        float: Percentage (0-100), or None if failed
    """
    try:
        last_day = get_last_trading_day()
        day_before = get_trading_day_before(last_day)
        ticker = symbol + ".NS"
        df = yf.download(ticker, start=day_before, end=last_day + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.between_time("09:15", "15:30")
        if df.empty:
            return None

        df['EMA'] = df['Close'].ewm(span=ema_span, adjust=False).mean()

        df_yesterday = df[df.index.date == last_day]
        if df_yesterday.empty:
            return None

        diff_pct = ((df_yesterday['Close'] - df_yesterday['EMA']).abs() / df_yesterday['EMA']) * 100
        near_ema_count = (diff_pct <= tolerance_pct).sum()
        total_count = len(df_yesterday)
        if total_count == 0:
            return None
        return round((near_ema_count / total_count) * 100, 1)
    except:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: ENTRY CANDLE SIGNALS (9:40 / 9:45 / 9:50 — POST-ENTRY CONFIRMATION)
# ═══════════════════════════════════════════════════════════════════════════════

def get_candle_signal(symbol, candle_time_str):
    """
    Check if a specific candle is bullish (Close > Open).
    Standalone — no POC/EMA dependency, pure candle color check.
    Used AFTER entry to visually confirm continuation, not part of the
    core buy decision.

    Returns:
        str: "green" if bullish, "" if bearish/missing
    """
    try:
        today = datetime.now(IST).date()
        ticker = symbol + ".NS"
        df = yf.download(ticker, start=today, end=today + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return ""
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        df_candle = df.between_time(candle_time_str, candle_time_str)
        if df_candle.empty:
            return ""
        row = df_candle.iloc[0]
        open_  = float(row['Open'].values[0] if hasattr(row['Open'], 'values') else row['Open'])
        close_ = float(row['Close'].values[0] if hasattr(row['Close'], 'values') else row['Close'])
        return "green" if close_ > open_ else ""
    except:
        return ""


def get_all_candle_signals(symbol):
    """
    OPTIMIZED: Fetch all three entry-confirmation candles (9:40, 9:45, 9:50)
    in ONE yfinance call instead of three separate calls (3x speedup).

    Returns:
        dict: {"09:40": "green"/"", "09:45": "green"/"", "09:50": "green"/""}
    """
    result = {"09:40": "", "09:45": "", "09:50": ""}
    try:
        today = datetime.now(IST).date()
        ticker = symbol + ".NS"
        df = yf.download(ticker, start=today, end=today + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return result
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)

        for candle_time_str in ["09:40", "09:45", "09:50"]:
            df_candle = df.between_time(candle_time_str, candle_time_str)
            if df_candle.empty:
                continue
            row = df_candle.iloc[0]
            open_  = float(row['Open'].values[0] if hasattr(row['Open'], 'values') else row['Open'])
            close_ = float(row['Close'].values[0] if hasattr(row['Close'], 'values') else row['Close'])
            result[candle_time_str] = "green" if close_ > open_ else ""
        return result
    except:
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: 5-DAY MEDIAN VOLUME (RELATIVE VOLUME BASELINE)
# ═══════════════════════════════════════════════════════════════════════════════

def get_5day_median_volume(symbol, days=5):
    """
    Calculate 5-day median daily volume — baseline for relative volume
    display (separate analysis metric, not part of core entry decision).

    Excludes today's incomplete data (Close = NaN while market is open).
    Median (not average) is used since it's outlier-resistant.

    Returns:
        float: Median volume, or None if fetch failed
    """
    try:
        ticker = symbol + ".NS"
        df = yf.download(ticker, period="15d", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.dropna(subset=['Close'])
        if df.empty:
            return None
        last_n = df['Volume'].tail(days)
        if last_n.empty:
            return None
        return round(float(last_n.median()), 0)
    except:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: FILTERS — SECTOR, PREVIOUS HIGH, CROSSOVER-RESULT, EMA COIL, RELVOL
# ═══════════════════════════════════════════════════════════════════════════════

def calc_prev_high_dist(row):
    """
    Calculate distance from current price to previous day's high (as %).
    Positive = trading above previous high (bullish breakout),
    Negative = still below previous high (consolidating).

    Args:
        row (pd.Series): Must have 'close' and 'high[1]' columns

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
    """Extract previous day's high value for display."""
    try:
        v = float(row.get('high[1]', 0) or 0)
        return v if v > 0 else None
    except:
        return None


def apply_sector_filter(df, sector):
    """
    Filter dataframe by sector (dropdown selection in UI).

    Args:
        df (pd.DataFrame): Data with 'Sector' column
        sector (str): Sector to filter for, or 'All' to skip filter

    Returns:
        pd.DataFrame: Filtered dataframe
    """
    if sector == 'All':
        return df
    return df[df['Sector'] == sector].copy()


def apply_crossover_filter(df, match_type="09:15"):
    """
    Filter to rows where the (already-calculated) crossover result matches
    the expected type. This just SELECTS rows based on strategy.py's output
    — it does not calculate the signal itself.

    Args:
        df (pd.DataFrame): Data with 'Crossover' column
        match_type (str): "09:15" (strict) / "09:20" (flexible) / "" (no match)

    Returns:
        pd.DataFrame: Filtered dataframe
    """
    return df[df['Crossover'] == match_type].copy()


def apply_ema_coil_filter(df, min_threshold=70.0):
    """
    Optional filter: only stocks with EMA coil % >= min_threshold
    (tight consolidation before the move).

    Args:
        df (pd.DataFrame): Data with 'EmaCoilPct' column
        min_threshold (float): Minimum EMA coil % (default 70)

    Returns:
        pd.DataFrame: Filtered dataframe
    """
    return df[df['EmaCoilPct'] >= min_threshold].copy()


def apply_relvol_filter(df, min_relvol=1.0):
    """
    Optional filter: only stocks with relative volume (5D) >= min_relvol.

    Args:
        df (pd.DataFrame): Data with 'RelVol5D' column
        min_relvol (float): Minimum relative volume multiplier (default 1.0)

    Returns:
        pd.DataFrame: Filtered dataframe
    """
    return df[df['RelVol5D'] >= min_relvol].copy()


def apply_all_filters(df, sector='All', crossover_match="09:15",
                      ema_coil_min=None, relvol_min=None):
    """
    Apply sector/crossover/ema-coil/relvol filters in sequence.
    NOTE: Gap filter is applied separately in strategy.py (it's part of
    the core entry decision, not a supporting filter).

    Args:
        df (pd.DataFrame): Input data
        sector (str): Sector filter ('All' = no filter)
        crossover_match (str): "09:15", "09:20", or "" for crossover filter
        ema_coil_min (float, optional): Min EMA coil % (None = skip)
        relvol_min (float, optional): Min RelVol5D (None = skip)

    Returns:
        pd.DataFrame: Filtered dataframe
    """
    df = df.copy()
    df = apply_sector_filter(df, sector)
    df = apply_crossover_filter(df, match_type=crossover_match)
    if ema_coil_min is not None:
        df = apply_ema_coil_filter(df, min_threshold=ema_coil_min)
    if relvol_min is not None:
        df = apply_relvol_filter(df, min_relvol=relvol_min)
    return df
