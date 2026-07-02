# ──────────────────────────────────────────────────────────────────────────────
# swing_strategy/backend.py
# Zone Detection + Breakout Logic for Swing Trading
# ──────────────────────────────────────────────────────────────────────────────

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone, timedelta, date
from supabase import create_client
from config import STOCKS_WATCHLIST

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

IST = timezone(timedelta(hours=5, minutes=30))

# Consolidation config
MIN_CONSOL_DAYS   = 5
MAX_CONSOL_DAYS   = 15
MAX_DAILY_RANGE   = 3.0     # % max range per day to qualify as consolidation
MIN_ZONE_WIDTH    = 1.5     # % minimum zone width
MAX_ZONE_WIDTH    = 4.0     # % maximum zone width

# Breakout config
BREAKOUT_BUFFER   = 0.3     # % above resistance for confirmed breakout
MIN_1H_VOL_RATIO  = 1.5     # 1H candle volume vs avg 1H volume
MIN_BODY_PCT      = 60.0    # % of candle range that must be body
BREAKOUT_START_H  = 10      # 10:00 AM IST — avoid opening spike
BREAKOUT_END_H    = 14      # 2:30 PM IST — avoid closing manipulation
BREAKOUT_END_M    = 30

# Zone score thresholds
STRONG_ZONE_SCORE = 7
MEDIUM_ZONE_SCORE = 5

# ──────────────────────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ──────────────────────────────────────────────────────────────────────────────

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 1 — FETCH DAILY DATA FROM SUPABASE
# ──────────────────────────────────────────────────────────────────────────────

def fetch_daily_data_supabase(stock: str, days: int = 20) -> pd.DataFrame:
    """
    Fetch last N days OHLCV for a stock from websocket_stock_values.
    Returns DataFrame with columns: date, open, high, low, ltp (close), volume
    Sorted oldest → newest.
    """
    try:
        supabase = get_supabase()

        # Get last N distinct dates
        date_resp = supabase.table("websocket_stock_values") \
            .select("date") \
            .eq("stock", stock) \
            .order("date", desc=True) \
            .limit(days) \
            .execute()

        if not date_resp.data:
            return pd.DataFrame()

        dates = [r["date"] for r in date_resp.data]

        # Fetch OHLCV for those dates — latest record per date (EOD)
        rows = []
        for d in dates:
            resp = supabase.table("websocket_stock_values") \
                .select("date, open, high, low, ltp, volume") \
                .eq("stock", stock) \
                .eq("date", d) \
                .order("created_at", desc=True) \
                .limit(1) \
                .execute()
            if resp.data:
                rows.append(resp.data[0])

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["date"]   = pd.to_datetime(df["date"])
        df["open"]   = pd.to_numeric(df["open"],   errors="coerce")
        df["high"]   = pd.to_numeric(df["high"],   errors="coerce")
        df["low"]    = pd.to_numeric(df["low"],    errors="coerce")
        df["close"]  = pd.to_numeric(df["ltp"],    errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close", "volume"])
        df = df[df["close"] > 0]
        df = df.sort_values("date").reset_index(drop=True)

        return df[["date", "open", "high", "low", "close", "volume"]]

    except Exception as e:
        return pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 2 — CONSOLIDATION DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def detect_consolidation(df: pd.DataFrame) -> dict:
    """
    Detect if stock is in consolidation zone.
    
    Rules:
    - Each day range (High-Low)/Low*100 < MAX_DAILY_RANGE (3%)
    - Minimum MIN_CONSOL_DAYS, Maximum MAX_CONSOL_DAYS
    - Count consecutive qualifying days from most recent backward
    
    Returns dict with consolidation info or None if not consolidating.
    """
    if df.empty or len(df) < MIN_CONSOL_DAYS:
        return None

    # Work backwards from most recent day
    consol_days = 0
    for i in range(len(df) - 1, -1, -1):
        row       = df.iloc[i]
        day_range = ((row["high"] - row["low"]) / row["low"]) * 100

        if day_range <= MAX_DAILY_RANGE:
            consol_days += 1
        else:
            break  # Consolidation broken — stop counting

        if consol_days >= MAX_CONSOL_DAYS:
            break

    if consol_days < MIN_CONSOL_DAYS:
        return None

    # Get the consolidation window
    consol_df = df.tail(consol_days).copy()

    # ── Zone based on CLOSING prices (body, not wick noise) ──
    resistance_raw = np.percentile(consol_df["close"], 90)
    support_raw    = np.percentile(consol_df["close"], 10)

    # Also check absolute high/low for reference
    abs_high = consol_df["high"].max()
    abs_low  = consol_df["low"].min()

    zone_width_pct = ((resistance_raw - support_raw) / support_raw) * 100

    # Zone width filter
    if zone_width_pct < MIN_ZONE_WIDTH or zone_width_pct > MAX_ZONE_WIDTH:
        return None

    return {
        "consol_days"   : consol_days,
        "resistance"    : round(resistance_raw, 2),
        "support"       : round(support_raw, 2),
        "zone_high"     : round(abs_high, 2),
        "zone_low"      : round(abs_low, 2),
        "zone_width_pct": round(zone_width_pct, 2),
        "consol_df"     : consol_df,
    }


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 3 — ZONE STRENGTH SCORE
# ──────────────────────────────────────────────────────────────────────────────

def calculate_zone_score(df: pd.DataFrame, consol_info: dict) -> int:
    """
    Score the zone quality from 0-10.
    
    +2 → Consolidation 8+ days
    +2 → Zone width 2-3% (tight sweet spot)
    +2 → Volume declining during consolidation (accumulation)
    +2 → Price near 52-week high (breakout potential)
    +1 → EMA20 > EMA50 (uptrend)
    +1 → Last candle close near resistance (coiling up)
    """
    score = 0
    consol_df = consol_info["consol_df"]

    # +2 — Consolidation length
    if consol_info["consol_days"] >= 8:
        score += 2
    elif consol_info["consol_days"] >= 5:
        score += 1

    # +2 — Zone width sweet spot (2-3%)
    w = consol_info["zone_width_pct"]
    if 2.0 <= w <= 3.0:
        score += 2
    elif 1.5 <= w <= 4.0:
        score += 1

    # +2 — Volume declining during consolidation (smart accumulation pattern)
    if len(consol_df) >= 3:
        first_half_vol = consol_df["volume"].iloc[:len(consol_df)//2].mean()
        second_half_vol = consol_df["volume"].iloc[len(consol_df)//2:].mean()
        if first_half_vol > 0 and second_half_vol < first_half_vol * 0.85:
            score += 2
        elif first_half_vol > 0 and second_half_vol < first_half_vol:
            score += 1

    # +2 — Price near 52-week high
    if len(df) >= 20:
        high_52w = df["high"].max()
        current  = consol_info["resistance"]
        if high_52w > 0:
            pct_from_high = ((high_52w - current) / high_52w) * 100
            if pct_from_high <= 10:
                score += 2
            elif pct_from_high <= 20:
                score += 1

    # +1 — EMA20 > EMA50
    if len(df) >= 50:
        ema20 = df["close"].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        if ema20 > ema50:
            score += 1

    # +1 — Last candle close near resistance (coiling up)
    last_close = consol_df["close"].iloc[-1]
    resistance = consol_info["resistance"]
    if resistance > 0:
        pct_from_res = ((resistance - last_close) / resistance) * 100
        if pct_from_res <= 1.0:
            score += 1

    return min(score, 10)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4 — FETCH 1H DATA FROM YFINANCE
# ──────────────────────────────────────────────────────────────────────────────

def fetch_1h_data(symbol: str) -> pd.DataFrame:
    """
    Fetch last 5 days of 1H OHLCV from yfinance.
    Converts symbol to NSE format (e.g. COHANCE → COHANCE.NS)
    """
    try:
        ticker = f"{symbol}.NS"
        df = yf.download(
            ticker,
            period   = "5d",
            interval = "1h",
            progress = False,
            auto_adjust = True,
        )

        if df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
        df = df.rename(columns={"datetime": "datetime", "index": "datetime"})

        # Ensure datetime column exists
        if "datetime" not in df.columns and "date" in df.columns:
            df = df.rename(columns={"date": "datetime"})

        df["datetime"] = pd.to_datetime(df["datetime"])

        # Convert to IST
        if df["datetime"].dt.tz is None:
            df["datetime"] = df["datetime"].dt.tz_localize("UTC").dt.tz_convert(IST)
        else:
            df["datetime"] = df["datetime"].dt.tz_convert(IST)

        df = df.dropna(subset=["open", "high", "low", "close", "volume"])
        df = df[df["close"] > 0]
        df = df.sort_values("datetime").reset_index(drop=True)

        return df[["datetime", "open", "high", "low", "close", "volume"]]

    except Exception as e:
        return pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 5 — BREAKOUT DETECTION ON 1H
# ──────────────────────────────────────────────────────────────────────────────

def detect_1h_breakout(df_1h: pd.DataFrame, resistance: float) -> dict:
    """
    Check if latest 1H candle is a valid breakout.
    
    Conditions:
    1. Candle CLOSE > resistance + BREAKOUT_BUFFER%
    2. Candle volume > 1.5x avg 1H volume (last 20 candles)
    3. Candle body > 60% of total range
    4. Time between 10:00 AM - 2:30 PM IST
    
    Returns breakout info dict or None.
    """
    if df_1h.empty or len(df_1h) < 5:
        return None

    # Latest candle
    latest = df_1h.iloc[-1]
    candle_time = latest["datetime"]

    # ── Time filter ──────────────────────────────────────────
    hour   = candle_time.hour
    minute = candle_time.minute

    time_ok = (
        (hour > BREAKOUT_START_H) or (hour == BREAKOUT_START_H and minute >= 0)
    ) and (
        (hour < BREAKOUT_END_H) or (hour == BREAKOUT_END_H and minute <= BREAKOUT_END_M)
    )

    if not time_ok:
        return None

    # ── Price breakout ───────────────────────────────────────
    breakout_level = resistance * (1 + BREAKOUT_BUFFER / 100)
    if latest["close"] <= breakout_level:
        return None

    # ── Volume check ─────────────────────────────────────────
    avg_vol_1h = df_1h["volume"].iloc[-20:].mean() if len(df_1h) >= 20 else df_1h["volume"].mean()
    if avg_vol_1h <= 0:
        return None

    vol_ratio_1h = latest["volume"] / avg_vol_1h
    if vol_ratio_1h < MIN_1H_VOL_RATIO:
        return None

    # ── Candle body quality ──────────────────────────────────
    candle_range = latest["high"] - latest["low"]
    if candle_range <= 0:
        return None

    body         = abs(latest["close"] - latest["open"])
    body_pct     = (body / candle_range) * 100

    if body_pct < MIN_BODY_PCT:
        return None

    return {
        "breakout_time"    : candle_time.strftime("%H:%M"),
        "breakout_price"   : round(float(latest["close"]), 2),
        "vol_ratio_1h"     : round(float(vol_ratio_1h), 2),
        "body_pct"         : round(float(body_pct), 2),
        "breakout_level"   : round(float(breakout_level), 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 6 — DAILY VOLUME RATIO
# ──────────────────────────────────────────────────────────────────────────────

def calculate_daily_vol_ratio(df: pd.DataFrame) -> float:
    """
    Compare today's volume vs median of last 5 days.
    """
    if len(df) < 2:
        return 0.0

    today_vol  = df["volume"].iloc[-1]
    median_vol = df["volume"].iloc[-6:-1].median() if len(df) >= 6 else df["volume"].iloc[:-1].median()

    if median_vol <= 0:
        return 0.0

    return round(today_vol / median_vol, 2)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 7 — MAIN SCANNER
# ──────────────────────────────────────────────────────────────────────────────

def run_swing_scan(min_score: int = STRONG_ZONE_SCORE) -> list:
    """
    Main scanner — runs through all stocks in STOCKS_WATCHLIST.
    
    For each stock:
    1. Fetch daily data from Supabase
    2. Detect consolidation
    3. Calculate zone score
    4. Fetch 1H data from yfinance
    5. Check for breakout
    6. Return results
    
    Returns list of dicts with signal info.
    """
    results    = []
    today_str  = date.today().isoformat()
    supabase   = get_supabase()

    stock_names = [name for name, token, kind in STOCKS_WATCHLIST if kind != "index"]

    for stock in stock_names:
        try:
            # ── Step 1: Daily data ───────────────────────────
            df_daily = fetch_daily_data_supabase(stock, days=20)
            if df_daily.empty or len(df_daily) < MIN_CONSOL_DAYS:
                continue

            # ── Step 2: Consolidation detection ─────────────
            consol = detect_consolidation(df_daily)
            if not consol:
                continue

            # ── Step 3: Zone score ───────────────────────────
            score = calculate_zone_score(df_daily, consol)
            if score < min_score:
                continue

            # ── Step 4: Daily vol ratio ──────────────────────
            vol_ratio_daily = calculate_daily_vol_ratio(df_daily)

            # ── Step 5: 1H breakout check ────────────────────
            df_1h    = fetch_1h_data(stock)
            breakout = detect_1h_breakout(df_1h, consol["resistance"]) if not df_1h.empty else None

            # ── Step 6: Entry/SL/Target ──────────────────────
            entry_price = breakout["breakout_price"] if breakout else None
            stoploss    = round(consol["zone_low"] * 0.995, 2) if entry_price else None
            target      = round(entry_price * 1.10, 2) if entry_price else None

            result = {
                "stock"             : stock,
                "signal_date"       : today_str,
                "consolidation_days": consol["consol_days"],
                "zone_high"         : consol["zone_high"],
                "zone_low"          : consol["zone_low"],
                "zone_width_pct"    : consol["zone_width_pct"],
                "zone_score"        : score,
                "resistance"        : consol["resistance"],
                "support"           : consol["support"],
                "vol_ratio_daily"   : vol_ratio_daily,
                "entry_price"       : entry_price,
                "stoploss"          : stoploss,
                "target"            : target,
                "breakout_time"     : breakout["breakout_time"] if breakout else None,
                "breakout_vol_ratio": breakout["vol_ratio_1h"] if breakout else None,
                "status"            : "TRIGGERED" if breakout else "WATCHING",
            }

            results.append(result)

            # ── Step 7: Save to Supabase ─────────────────────
            save_signal_to_supabase(result, supabase)

        except Exception as e:
            continue

    # Sort: TRIGGERED first, then by score
    results.sort(key=lambda x: (0 if x["status"] == "TRIGGERED" else 1, -x["zone_score"]))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 8 — SAVE TO SUPABASE
# ──────────────────────────────────────────────────────────────────────────────

def save_signal_to_supabase(signal: dict, supabase=None):
    """Save or update swing signal in swing_breakout table."""
    try:
        if supabase is None:
            supabase = get_supabase()

        row = {k: v for k, v in signal.items() if k != "consol_df"}
        supabase.table("swing_breakout").upsert(
            row,
            on_conflict="stock,signal_date",
            ignore_duplicates=False
        ).execute()

    except Exception as e:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 9 — FETCH SAVED SIGNALS
# ──────────────────────────────────────────────────────────────────────────────

def fetch_saved_signals(days_back: int = 7) -> list:
    """Fetch recent signals from swing_breakout table."""
    try:
        supabase  = get_supabase()
        from_date = (date.today() - timedelta(days=days_back)).isoformat()

        resp = supabase.table("swing_breakout") \
            .select("*") \
            .gte("signal_date", from_date) \
            .order("signal_date", desc=True) \
            .execute()

        return resp.data or []

    except Exception as e:
        return []


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 10 — UPDATE SIGNAL STATUS
# ──────────────────────────────────────────────────────────────────────────────

def update_signal_status(stock: str, signal_date: str, status: str):
    """Update status of a signal — WATCHING / TRIGGERED / EXITED."""
    try:
        supabase = get_supabase()
        supabase.table("swing_breakout") \
            .update({"status": status}) \
            .eq("stock", stock) \
            .eq("signal_date", signal_date) \
            .execute()
    except Exception as e:
        pass
