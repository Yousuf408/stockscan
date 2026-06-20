"""
breakout_4h_data.py
Data layer:
  - fetch_avg_volumes()  → Supabase avg daily volume per stock
  - fetch_1h_data()      → yfinance 1h candles
  - aggregate_to_4h()    → 1h → 4h candle aggregation
"""

import pandas as pd
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
# SUPABASE CLIENT (module-level singleton)
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
    Returns: { "RELIANCE": 15000000, "HDFCBANK": 8000000, ... }
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

        # Remove duplicates — keep latest per stock per date
        df = df.drop_duplicates(subset=["stock", "date"], keep="first")

        # Last 10 days per stock
        df_sorted = df.sort_values("date", ascending=False)
        df_top10  = df_sorted.groupby("stock").head(10)

        # Average volume per stock
        avg_vol = df_top10.groupby("stock")["volume"].mean().to_dict()
        return avg_vol

    except Exception as e:
        print(f"[breakout_4h_data] Supabase fetch error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# SECTION 2 — YFINANCE: FETCH 1H DATA
# ─────────────────────────────────────────────────────────────
def fetch_1h_data(symbol: str) -> pd.DataFrame | None:
    """
    Fetch 1h OHLCV data from yfinance for an NSE stock.
    Returns cleaned DataFrame or None if fetch fails.
    """
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        df     = ticker.history(interval="1h", period=YFINANCE_1H_PERIOD)

        if df is None or df.empty or len(df) < 4:
            return None

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        return df[["datetime", "open", "high", "low", "close", "volume"]]

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# SECTION 3 — AGGREGATE 1H → 4H CANDLES
# ─────────────────────────────────────────────────────────────
def aggregate_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate 1h candles into 4h candles.
    Every 4 consecutive 1h candles = 1 4h candle:
      open   = first candle's open
      high   = max of all 4 highs
      low    = min of all 4 lows
      close  = last candle's close
      volume = sum of all 4 volumes
    Only complete groups of 4 are kept.
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
# SECTION 4 — FETCH DAILY DATA (for checks 6,7,8)
# ─────────────────────────────────────────────────────────────
def fetch_daily_data(symbol: str):
    """
    Fetch daily OHLCV + market cap for checks 6, 7, 8.
    Returns: (daily_close_array, market_cap) or (None, None)
    """
    try:
        ticker   = yf.Ticker(f"{symbol}.NS")
        df_daily = ticker.history(interval="1d", period=YFINANCE_DAILY_PERIOD)

        if df_daily is None or len(df_daily) < 50:
            return None, None

        daily_close = df_daily["Close"].values

        # Market cap
        try:
            info   = ticker.fast_info
            mktcap = getattr(info, "market_cap", 0) or 0
        except Exception:
            mktcap = 0

        return daily_close, mktcap

    except Exception:
        return None, None
