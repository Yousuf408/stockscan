"""
breakout_4h_data.py
Data layer:
  - fetch_1h_data()        → yfinance 1h candles
  - aggregate_to_4h()      → 1h → 4h aggregation
  - fetch_1h_and_4h_data() → returns both 1H + 4H
  - fetch_daily_data()     → daily close for SMA20/50
"""

import pandas as pd
import yfinance as yf
import numpy as np

from breakout_4h.breakout_4h_config import (
    YFINANCE_1H_PERIOD,
    YFINANCE_DAILY_PERIOD,
)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — FETCH 1H DATA
# ─────────────────────────────────────────────────────────────
def fetch_1h_data(symbol: str) -> pd.DataFrame | None:
    """
    Fetch 1h OHLCV from yfinance for NSE stock.
    Strips timezone for consistent rendering.
    """
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        df     = ticker.history(interval="1h", period=YFINANCE_1H_PERIOD)

        if df is None or df.empty or len(df) < 8:
            return None

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]

        # Strip timezone
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])
            if df["datetime"].dt.tz is not None:
                df["datetime"] = df["datetime"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)

        return df[["datetime", "open", "high", "low", "close", "volume"]]

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# SECTION 2 — AGGREGATE 1H → 4H
# ─────────────────────────────────────────────────────────────
def aggregate_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """
    Every 4 consecutive 1h candles = 1 4h candle.
    open   = first candle open
    high   = max of 4 highs
    low    = min of 4 lows
    close  = last candle close
    volume = sum of 4 volumes
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
# SECTION 3 — FETCH BOTH 1H + 4H
# ─────────────────────────────────────────────────────────────
def fetch_1h_and_4h_data(symbol: str):
    """
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
# SECTION 4 — FETCH DAILY DATA (for SMA20/50 only)
# ─────────────────────────────────────────────────────────────
def fetch_daily_data(symbol: str):
    """
    Fetch daily closing prices for SMA20 & SMA50.
    Returns: (daily_close_array, market_cap) or (None, None)
    """
    try:
        ticker   = yf.Ticker(f"{symbol}.NS")
        df_daily = ticker.history(interval="1d", period=YFINANCE_DAILY_PERIOD)

        if df_daily is None or len(df_daily) < 50:
            return None, None

        daily_close = df_daily["Close"].values

        try:
            mktcap = getattr(ticker.fast_info, "market_cap", 0) or 0
        except Exception:
            mktcap = 0

        return daily_close, mktcap

    except Exception:
        return None, None
