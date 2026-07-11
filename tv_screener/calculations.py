# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER CALCULATIONS MODULE
# POC, EMA Coil, Crossover signals, Candle analysis, 5-day volume median
# ═══════════════════════════════════════════════════════════════════════════════

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import pytz
import time

IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DATE & TIME HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def get_trading_day_before(date):
    """
    Given a date, find the last trading day before it (exclude weekends).
    Verify via yfinance that the day has data.
    
    Args:
        date (datetime.date): Reference date
    
    Returns:
        datetime.date: Last trading day before the given date
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
    # Fallback: just skip weekends without yfinance verify
    candidate = date - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def get_last_trading_day():
    """
    Get the last complete trading day (yesterday if market hasn't opened today, 
    or day-before-yesterday if market is not yet open today at 9:15).
    
    Returns:
        datetime.date: Last complete trading day
    """
    now = datetime.now(IST)
    today = now.date()
    # Agar market abhi khula nahi (9:15 AM se pehle), toh "aaj" ko bhi
    # "not yet trading" treat karo, ek din peeche shift karo
    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        today = today - timedelta(days=1)
    tv_ref = get_trading_day_before(today + timedelta(days=1))
    poc_date = get_trading_day_before(tv_ref)
    return poc_date


def get_current_ist_time():
    """Get current time in IST."""
    return datetime.now(IST)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: MARKET HOURS GATE
# ─────────────────────────────────────────────────────────────────────────────

def is_market_hours():
    """
    Check if current time is within market trading hours (9:15 AM - 3:30 PM IST).
    
    Returns:
        bool: True if market is open, False otherwise
    """
    now = datetime.now(IST)
    market_open  = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: POC (POINT OF CONTROL) CALCULATION
# ─────────────────────────────────────────────────────────────────────────────

def calculate_poc_from_df(df_day, num_bins=50):
    """
    Calculate POC (Point of Control) from a day's 5-minute candles using 
    fixed-range volume profile (FRPV) approach.
    
    High-volume levels get bins; volume distributed proportionally within 
    each candle's high-low range. Max volume bin center = POC.
    
    Args:
        df_day (pd.DataFrame): Day's OHLCV data (5min candles)
        num_bins (int): Number of price bins for volume profile
    
    Returns:
        float: POC price (rounded to 2 decimals), or None if invalid
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
            # Flat candle — assign to single bin
            idx = np.digitize(low, bins) - 1
            idx = min(max(idx, 0), num_bins - 1)
            bin_volumes[idx] += vol
            continue
        # Distribute volume proportionally across bins this candle spans
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
    """
    Single POC calculation attempt — fetch yesterday's complete 5min data.
    
    Args:
        symbol (str): Stock symbol (e.g., "RELIANCE")
        num_bins (int): Price bins for volume profile
    
    Returns:
        float: POC value, or None if fetch/calculation failed
    """
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
    Robust POC fetch with retry & stability check.
    
    yfinance historical data can shift slightly between fetches. Fetch twice,
    check if values match within tolerance. If not, retry up to max_attempts.
    Return last known value if max attempts exceeded.
    
    Args:
        symbol (str): Stock symbol
        num_bins (int): Price bins
        max_attempts (int): Max retries
        tolerance_pct (float): Acceptable variance % between consecutive fetches
    
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
                return current_val  # Values match — stable
        prev_val = current_val
        if attempt < max_attempts - 1:
            time.sleep(2)  # Wait before retry
    return prev_val  # Return last known value

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: EMA CONSOLIDATION (EMA COIL) CHECK
# ─────────────────────────────────────────────────────────────────────────────

def get_ema_consolidation_pct(symbol, ema_span=20, tolerance_pct=0.5):
    """
    Calculate % of candles where Close is within ±tolerance_pct of EMA.
    
    Indicates consolidation/coil phase. Fetch 2 days (yesterday + day-before)
    to warm up EMA, then calculate % only for yesterday's candles.
    
    Args:
        symbol (str): Stock symbol
        ema_span (int): EMA period (default 20)
        tolerance_pct (float): Acceptable distance from EMA (%)
    
    Returns:
        float: Percentage (0-100) of candles within EMA tolerance, or None if failed
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

        # Calculate EMA across full 2-day period (warm-up)
        df['EMA'] = df['Close'].ewm(span=ema_span, adjust=False).mean()

        # Filter to only yesterday's candles for % calculation
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

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: CROSSOVER SIGNAL (9EMA CROSS 20EMA + POC CHECK)
# ─────────────────────────────────────────────────────────────────────────────

def get_crossover_signal(symbol, poc_value, fast_span=9, slow_span=20):
    """
    Detect 9EMA → 20EMA bullish crossover with POC confirmation.
    
    Two-candle check:
      A) 9:15 candle (CLOSED):
         - 9EMA was below 20EMA yesterday
         - 9EMA now above 20EMA at 9:15 close
         - Close > POC
         - Candle body >= 70% of (High - Low) [strong directional, not doji]
      
      B) 9:20 candle (ANY data, may still be forming):
         - Same EMA/POC conditions (no body check)
    
    Once match found, returns candle time ("09:15" or "09:20"). 
    Session cache makes it permanent (no re-check on refresh).
    
    Args:
        symbol (str): Stock symbol
        poc_value (float): Yesterday's POC
        fast_span (int): Fast EMA period (default 9)
        slow_span (int): Slow EMA period (default 20)
    
    Returns:
        str: "09:15" if strict match, "09:20" if flexible match, "" if no match
    """
    try:
        if poc_value is None:
            return ""

        last_day = get_last_trading_day()
        today = datetime.now(IST).date()
        ticker = symbol + ".NS"
        # Fetch yesterday + today for EMA continuity
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
            return ""  # Already above yesterday — no crossover

        def check_candle(candle_time_str, require_body_check=False, min_body_pct=70):
            """
            Check if a specific candle meets crossover conditions.
            
            Args:
                candle_time_str (str): Time in "HH:MM" format (e.g., "09:15")
                require_body_check (bool): If True, enforce body % >= min_body_pct
                min_body_pct (float): Min body % threshold
            
            Returns:
                bool: True if conditions met, False otherwise
            """
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
                candle_range = high_ - low_
                if candle_range <= 0:
                    return False  # Doji/flat — can't calculate body %
                body_pct = abs(close_ - open_) / candle_range * 100
                if body_pct < min_body_pct:
                    return False

            return True

        # Check 9:15 candle (strict: body check required)
        if check_candle("09:15", require_body_check=True):
            return "09:15"

        # Check 9:20 candle (flexible: no body check)
        if check_candle("09:20", require_body_check=False):
            return "09:20"

        return ""
    except:
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: CANDLE ENTRY SIGNALS (9:40, 9:45, 9:50)
# ─────────────────────────────────────────────────────────────────────────────

def get_candle_signal(symbol, candle_time_str):
    """
    Check if a specific candle is bullish (Close > Open).
    
    Standalone check — no POC/EMA dependency, pure candle analysis.
    
    Args:
        symbol (str): Stock symbol
        candle_time_str (str): Time in "HH:MM" format (e.g., "09:40")
    
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
    Optimized: Fetch all three candle signals (9:40, 9:45, 9:50) in ONE yfinance call.
    
    Instead of calling yfinance 3 times (one per candle), fetch full day once,
    then extract all three candles. 3x speedup.
    
    Args:
        symbol (str): Stock symbol
    
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

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: 5-DAY MEDIAN VOLUME
# ─────────────────────────────────────────────────────────────────────────────

def get_5day_median_volume(symbol, days=5):
    """
    Calculate 5-day median volume baseline (for relative volume calculation).
    
    Fetch last 15 days of daily data, remove today's incomplete data 
    (Close = NaN if market still open), take median of last 5 complete days.
    Median is outlier-resistant vs. average.
    
    Args:
        symbol (str): Stock symbol
        days (int): Number of complete days to use (default 5)
    
    Returns:
        float: Median volume, or None if fetch failed
    """
    try:
        ticker = symbol + ".NS"
        df = yf.download(ticker, period="15d", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        # Drop today's incomplete row (if market still open, Close = NaN)
        df = df.dropna(subset=['Close'])
        if df.empty:
            return None
        last_n = df['Volume'].tail(days)
        if last_n.empty:
            return None
        return round(float(last_n.median()), 0)
    except:
        return None
