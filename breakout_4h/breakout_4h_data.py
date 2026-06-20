"""
breakout_4h_data.py
Data layer:
  - fetch_avg_volumes()     → Supabase avg daily volume
  - fetch_1h_data()         → yfinance 1h candles
  - fetch_1h_and_4h_data()  → returns both 1H + 4H aggregated
  - aggregate_to_4h()       → 1h → 4h aggregation
  - fetch_daily_data()      → daily OHLCV + market cap
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from supabase import create_client

from breakout_4h.breakout_4h_config import (
    SUPABASE_URL,
    SUPABASE_KEY,
    SUPABASE_TABLE,
    YFINANCE_1H_PERIOD,
    YFINANCE_DAILY_PERIOD,
)

# ─────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────────────────────
_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase


# ─────────────────────────────────────────────────────────────
# SECTION 1 — SUPABASE: AVG VOLUME
# ─────────────────────────────────────────────────────────────
def fetch_avg_volumes() -> dict:
    """
    Fetch average daily volume for all stocks from Supabase.
    Uses past data only (date < today), deduplicates, takes last 10 days.
    Returns: { "RELIANCE": 15000000, ... }
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        sb    = get_supabase()

        resp = sb.table(SUPABASE_TABLE) \
            .select("stock, volume, date") \
            .lt("date", today) \
            .order("date", desc=True) \
            .execute()

        if not resp.data:
            return {}

        df = pd.DataFrame(resp.data)
        df = df.drop_duplicates(subset=["stock", "date"], keep="first")
        df_sorted = df.sort_values("date", ascending=False)
        df_top10  = df_sorted.groupby("stock").head(10)
        avg_vol   = df_top10.groupby("stock")["volume"].mean().to_dict()
        return avg_vol

    except Exception as e:
        print(f"[breakout_4h_data] Supabase fetch error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# SECTION 2 — YFINANCE: FETCH 1H DATA
# ─────────────────────────────────────────────────────────────
def fetch_1h_data(symbol: str) -> pd.DataFrame | None:
    """
    Fetch 1h OHLCV data from yfinance for NSE stock.
    Strips timezone for consistent Plotly rendering.
    Returns cleaned DataFrame or None.
    """
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        df     = ticker.history(interval="1h", period=YFINANCE_1H_PERIOD)

        if df is None or df.empty or len(df) < 8:
            return None

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]

        # Strip timezone → consistent timestamps
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])
            if df["datetime"].dt.tz is not None:
                df["datetime"] = df["datetime"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)

        return df[["datetime", "open", "high", "low", "close", "volume"]]

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# SECTION 3 — AGGREGATE 1H → 4H CANDLES
# ─────────────────────────────────────────────────────────────
def aggregate_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate 1h candles into 4h candles.
    Every 4 consecutive 1h candles = 1 4h candle.
    Only complete groups of 4 kept.
    """
    candles = []
    rows    = df_1h.values.tolist()
    n       = len(rows)

    for i in range(0, n - (n % 4), 4):
        group = rows[i:i + 4]
        if len(group) < 4:
            break
        candles.append({
            "datetime": group[0][0],
            "open"    : group[0][1],
            "high"    : max(r[2] for r in group),
            "low"     : min(r[3] for r in group),
            "close"   : group[3][4],
            "volume"  : sum(r[5] for r in group),
        })

    return pd.DataFrame(candles)


# ─────────────────────────────────────────────────────────────
# SECTION 4 — FETCH BOTH 1H + 4H DATA TOGETHER
# ─────────────────────────────────────────────────────────────
def fetch_1h_and_4h_data(symbol: str):
    """
    Fetch 1H data and return both:
    - df_1h : raw 1H candles
    - df_4h : aggregated 4H candles
    Returns (df_1h, df_4h) or (None, None)
    """
    df_1h = fetch_1h_data(symbol)
    if df_1h is None or df_1h.empty:
        return None, None

    df_4h = aggregate_to_4h(df_1h)
    if df_4h.empty:
        return None, None

    return df_1h, df_4h


# ─────────────────────────────────────────────────────────────
# SECTION 5 — FETCH DAILY DATA (for checks 5,6,7,8)
# ─────────────────────────────────────────────────────────────
def fetch_daily_data(symbol: str):
    """
    Fetch daily OHLCV + market cap.
    Returns: (daily_close_array, market_cap) or (None, None)
    """
    try:
        ticker   = yf.Ticker(f"{symbol}.NS")
        df_daily = ticker.history(interval="1d", period=YFINANCE_DAILY_PERIOD)

        if df_daily is None or len(df_daily) < 50:
            return None, None

        daily_close = df_daily["Close"].values

        try:
            info   = ticker.fast_info
            mktcap = getattr(info, "market_cap", 0) or 0
        except Exception:
            mktcap = 0

        return daily_close, mktcap

    except Exception:
        return None, None
