# ──────────────────────────────────────────────────────────────────────────────
# swing_strategy/backend.py
# Zone Detection — Bulk Fetch (5 days), No 1H breakout (coming later)
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

IST = timezone(timedelta(hours=5, minutes=30))

MIN_CONSOL_DAYS = 5
MAX_DAILY_RANGE = 3.0
MIN_ZONE_WIDTH  = 1.5
MAX_ZONE_WIDTH  = 4.0

STRONG_ZONE_SCORE = 5
MEDIUM_ZONE_SCORE = 3

# ──────────────────────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ──────────────────────────────────────────────────────────────────────────────

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 1 — BULK FETCH LAST 5 DAYS (ALL STOCKS, ONE QUERY)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all_stocks_bulk() -> pd.DataFrame:
    """
    Single Supabase query — fetch last 5 trading days EOD data for ALL stocks.
    Returns DataFrame: stock, date, open, high, low, close, volume
    """
    try:
        supabase = get_supabase()

        # Step 1: Get last 5 distinct trading dates
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

        # Step 2: Fetch all stocks for those 5 dates in batches
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

        # Keep latest record per (stock, date) = EOD value
        df = df.sort_values("created_at", ascending=False)
        df = df.drop_duplicates(subset=["stock", "date"], keep="first")
        df = df.drop(columns=["created_at"])

        df = df.dropna(subset=["open", "high", "low", "close", "volume"])
        df = df[(df["close"] > 0) & (df["volume"] > 0)]
        df = df.sort_values(["stock", "date"]).reset_index(drop=True)

        return df

    except Exception as e:
        return pd.DataFrame()


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 2 — CONSOLIDATION DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def detect_consolidation(stock_df: pd.DataFrame) -> dict:
    """
    Check if stock has been consolidating for all 5 days.
    Each day: (High-Low)/Low*100 < 3%
    Zone width: 1.5% - 4%
    Zone based on closing prices (body, not wicks)
    """
    if stock_df.empty or len(stock_df) < MIN_CONSOL_DAYS:
        return None

    stock_df = stock_df.copy()
    stock_df["day_range_pct"] = ((stock_df["high"] - stock_df["low"]) / stock_df["low"]) * 100

    qualifying = stock_df[stock_df["day_range_pct"] <= MAX_DAILY_RANGE]

    if len(qualifying) < MIN_CONSOL_DAYS:
        return None

    consol_df  = qualifying.copy()
    resistance = round(float(np.percentile(consol_df["close"], 90)), 2)
    support    = round(float(np.percentile(consol_df["close"], 10)), 2)
    zone_high  = round(float(consol_df["high"].max()), 2)
    zone_low   = round(float(consol_df["low"].min()), 2)

    if support <= 0:
        return None

    zone_width_pct = round(((resistance - support) / support) * 100, 2)

    if zone_width_pct < MIN_ZONE_WIDTH or zone_width_pct > MAX_ZONE_WIDTH:
        return None

    return {
        "consol_days"   : len(consol_df),
        "resistance"    : resistance,
        "support"       : support,
        "zone_high"     : zone_high,
        "zone_low"      : zone_low,
        "zone_width_pct": zone_width_pct,
        "consol_df"     : consol_df,
    }


# ──────────────────────────────────────────────────────────────────────────────
# SECTION 3 — ZONE STRENGTH SCORE
# ──────────────────────────────────────────────────────────────────────────────

def calculate_zone_score(stock_df: pd.DataFrame, consol_info: dict) -> int:
    """
    Score 0-10:
    +2 → All 5 days qualify
    +2 → Zone width 2-3% sweet spot
    +2 → Volume declining (accumulation)
    +2 → Last close near resistance (coiling up)
    +2 → Today volume > yesterday (interest building)
    """
    score     = 0
    consol_df = consol_info["consol_df"]

    # +2 All 5 days qualify
    if consol_info["consol_days"] >= MIN_CONSOL_DAYS:
        score += 2

    # +2 Zone width sweet spot
    w = consol_info["zone_width_pct"]
    if 2.0 <= w <= 3.0:
        score += 2
    elif 1.5 <= w <= 4.0:
        score += 1

    # +2 Volume declining
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
        if pct_from_res <= 0.5:
            score += 2
        elif pct_from_res <= 1.5:
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
    """Today's volume vs median of previous 4 days."""
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
    """
    1. ONE Supabase bulk fetch — all stocks 5 days
    2. groupby stock → consolidation check locally
    3. Zone score filter
    4. Save + return results
    """
    results   = []
    today_str = date.today().isoformat()
    supabase  = get_supabase()

    df_all = fetch_all_stocks_bulk()
    if df_all.empty:
        return []

    stock_names = {name for name, token, kind in STOCKS_WATCHLIST if kind != "index"}

    for stock, stock_df in df_all.groupby("stock"):
        if stock not in stock_names:
            continue

        try:
            stock_df = stock_df.sort_values("date").reset_index(drop=True)

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
