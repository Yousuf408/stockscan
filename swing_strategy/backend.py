# ──────────────────────────────────────────────────────────────────────────────
# swing_strategy/backend.py
# Simple Consolidation Detection — 5 days, no over-engineering
# ──────────────────────────────────────────────────────────────────────────────

import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta, date
from supabase import create_client
from config import STOCKS_WATCHLIST

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────────────

SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

IST             = timezone(timedelta(hours=5, minutes=30))
MIN_CONSOL_DAYS = 5
MAX_DAILY_RANGE = 3.0   # % max (high-low)/low per day

STRONG_ZONE_SCORE = 5
MEDIUM_ZONE_SCORE = 3

# ──────────────────────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ──────────────────────────────────────────────────────────────────────────────

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 1 — BULK FETCH LAST 5 TRADING DAYS (ONE QUERY)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all_stocks_bulk() -> pd.DataFrame:
    """
    Fetch last 5 trading days EOD data for ALL stocks in one Supabase query.
    Returns DataFrame: stock, date, open, high, low, close, volume
    """
    try:
        supabase = get_supabase()

        # Step 1: Get last 5 distinct dates
        date_resp = supabase.table("websocket_stock_values") \
            .select("date") \
            .order("date", desc=True) \
            .limit(5000) \
            .execute()

        if not date_resp.data:
            return pd.DataFrame()

        all_dates    = sorted(set(r["date"] for r in date_resp.data), reverse=True)
        last_5_dates = all_dates[:5]

        if len(last_5_dates) < MIN_CONSOL_DAYS:
            return pd.DataFrame()

        # Step 2: Fetch all stock data for those dates
        all_rows = []
        offset   = 0

        while True:
            resp = supabase.table("websocket_stock_values") \
                .select("stock, date, open, high, low, ltp, volume, created_at") \
                .in_("date", last_5_dates) \
                .order("created_at", desc=True) \
                .range(offset, offset + 999) \
                .execute()

            rows = resp.data
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < 1000:
                break
            offset += 1000

        if not all_rows:
            return pd.DataFrame()

        # Step 3: Build DataFrame
        df = pd.DataFrame(all_rows)
        df = df.rename(columns={"ltp": "close"})

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["date"] = pd.to_datetime(df["date"])

        # Latest record per (stock, date) = EOD
        df = df.sort_values("created_at", ascending=False)
        df = df.drop_duplicates(subset=["stock", "date"], keep="first")
        df = df.drop(columns=["created_at"])

        df = df.dropna(subset=["close", "volume"])
        df = df[(df["close"] > 0) & (df["volume"] > 0)]

        # If high/low missing, derive from open/close
        df["high"] = df["high"].fillna(df[["open", "close"]].max(axis=1))
        df["low"]  = df["low"].fillna(df[["open", "close"]].min(axis=1))
        df["open"] = df["open"].fillna(df["close"])

        df = df.sort_values(["stock", "date"]).reset_index(drop=True)
        return df

    except Exception as e:
        return pd.DataFrame()

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 2 — CONSOLIDATION DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def detect_consolidation(stock_df: pd.DataFrame) -> dict:
    """
    5 days consolidation check:
    - Each day (high - low) / low * 100 < 3%
    - All 5 days must qualify
    - Resistance = max close of 5 days
    - Support    = min close of 5 days
    """
    if len(stock_df) < MIN_CONSOL_DAYS:
        return None

    df = stock_df.copy()

    # Day range check
    df["day_range_pct"] = ((df["high"] - df["low"]) / df["low"]) * 100

    qualifying = df[df["day_range_pct"] <= MAX_DAILY_RANGE]

    # All 5 days must be tight
    if len(qualifying) < MIN_CONSOL_DAYS:
        return None

    # Zone = simple max/min of closing prices
    resistance = round(float(qualifying["close"].max()), 2)
    support    = round(float(qualifying["close"].min()), 2)
    zone_high  = round(float(qualifying["high"].max()), 2)
    zone_low   = round(float(qualifying["low"].min()), 2)

    if support <= 0:
        return None

    zone_width_pct = round(((resistance - support) / support) * 100, 2)

    return {
        "consol_days"   : len(qualifying),
        "resistance"    : resistance,
        "support"       : support,
        "zone_high"     : zone_high,
        "zone_low"      : zone_low,
        "zone_width_pct": zone_width_pct,
        "consol_df"     : qualifying,
    }

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 3 — ZONE SCORE (simple, 0-10)
# ──────────────────────────────────────────────────────────────────────────────

def calculate_zone_score(stock_df: pd.DataFrame, consol_info: dict) -> int:
    """
    Simple score:
    +2 → All 5 days tight (range < 3%)
    +2 → Zone width < 3% (very tight consolidation)
    +2 → Volume declining (accumulation)
    +2 → Last close near resistance (ready to breakout)
    +2 → Today volume > yesterday (interest building)
    """
    score     = 0
    consol_df = consol_info["consol_df"]

    # +2 All 5 days qualify
    if consol_info["consol_days"] >= MIN_CONSOL_DAYS:
        score += 2

    # +2 Tight zone width
    w = consol_info["zone_width_pct"]
    if w <= 3.0:
        score += 2
    elif w <= 5.0:
        score += 1

    # +2 Volume declining (accumulation pattern)
    if len(consol_df) >= 3:
        mid        = len(consol_df) // 2
        first_vol  = consol_df["volume"].iloc[:mid].mean()
        second_vol = consol_df["volume"].iloc[mid:].mean()
        if first_vol > 0 and second_vol < first_vol * 0.85:
            score += 2
        elif first_vol > 0 and second_vol < first_vol:
            score += 1

    # +2 Last close near resistance
    last_close = float(consol_df["close"].iloc[-1])
    resistance = consol_info["resistance"]
    if resistance > 0:
        pct_from_res = ((resistance - last_close) / resistance) * 100
        if pct_from_res <= 1.0:
            score += 2
        elif pct_from_res <= 2.0:
            score += 1

    # +2 Today volume > yesterday
    if len(consol_df) >= 2:
        today_vol     = float(consol_df["volume"].iloc[-1])
        yesterday_vol = float(consol_df["volume"].iloc[-2])
        if yesterday_vol > 0 and today_vol > yesterday_vol * 1.2:
            score += 2
        elif yesterday_vol > 0 and today_vol > yesterday_vol:
            score += 1

    return min(score, 10)

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4 — DAILY VOLUME RATIO
# ──────────────────────────────────────────────────────────────────────────────

def calculate_daily_vol_ratio(stock_df: pd.DataFrame) -> float:
    if len(stock_df) < 2:
        return 0.0
    today_vol  = float(stock_df["volume"].iloc[-1])
    median_vol = float(stock_df["volume"].iloc[:-1].median())
    if median_vol <= 0:
        return 0.0
    return round(today_vol / median_vol, 2)

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 5 — MAIN SCANNER
# ──────────────────────────────────────────────────────────────────────────────

def run_swing_scan(min_score: int = STRONG_ZONE_SCORE) -> list:
    results   = []
    today_str = date.today().isoformat()
    supabase  = get_supabase()

    # ONE bulk fetch
    df_all = fetch_all_stocks_bulk()
    if df_all.empty:
        return []

    stock_names = {name for name, token, kind in STOCKS_WATCHLIST if kind != "index"}

    for stock, stock_df in df_all.groupby("stock"):
        if stock not in stock_names:
            continue

        try:
            stock_df = stock_df.sort_values("date").reset_index(drop=True)

            # Need exactly 5 days
            if len(stock_df) < MIN_CONSOL_DAYS:
                continue

            consol = detect_consolidation(stock_df)
            if not consol:
                continue

            score = calculate_zone_score(stock_df, consol)
            if score < min_score:
                continue

            vol_ratio_daily = calculate_daily_vol_ratio(stock_df)
            stoploss        = round(consol["zone_low"] * 0.995, 2)
            target          = round(consol["resistance"] * 1.10, 2)

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
                "entry_price"       : None,
                "stoploss"          : stoploss,
                "target"            : target,
                "breakout_time"     : None,
                "breakout_vol_ratio": None,
                "status"            : "WATCHING",
            }

            results.append(result)
            save_signal_to_supabase(result, supabase)

        except Exception:
            continue

    results.sort(key=lambda x: -x["zone_score"])
    return results

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 6 — SAVE TO SUPABASE
# ──────────────────────────────────────────────────────────────────────────────

def save_signal_to_supabase(signal: dict, supabase=None):
    try:
        if supabase is None:
            supabase = get_supabase()
        row = {k: v for k, v in signal.items() if k != "consol_df"}
        supabase.table("swing_breakout").upsert(
            row,
            on_conflict       = "stock,signal_date",
            ignore_duplicates = False
        ).execute()
    except Exception:
        pass

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 7 — FETCH SAVED SIGNALS
# ──────────────────────────────────────────────────────────────────────────────

def fetch_saved_signals(days_back: int = 7) -> list:
    try:
        supabase  = get_supabase()
        from_date = (date.today() - timedelta(days=days_back)).isoformat()
        resp = supabase.table("swing_breakout") \
            .select("*") \
            .gte("signal_date", from_date) \
            .order("signal_date", desc=True) \
            .execute()
        return resp.data or []
    except Exception:
        return []

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 8 — UPDATE SIGNAL STATUS
# ──────────────────────────────────────────────────────────────────────────────

def update_signal_status(stock: str, signal_date: str, status: str):
    try:
        supabase = get_supabase()
        supabase.table("swing_breakout") \
            .update({"status": status}) \
            .eq("stock", stock) \
            .eq("signal_date", signal_date) \
            .execute()
    except Exception:
        pass
