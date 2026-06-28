"""
momentum/backend.py
Pure backend logic extracted from 8_MomentumScanner.py.
No Streamlit. No HTML. No session_state.
Supabase client is passed in as argument — caller owns caching.
"""

import pandas as pd
import yfinance as yf
from datetime import timezone, timedelta
from supabase import create_client

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
SUPABASE_URL       = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY       = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"
IST                = timezone(timedelta(hours=5, minutes=30))
EMA_DISTANCE_LIMIT = 8.0


def get_supabase_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ─────────────────────────────────────────────────────────────
# EMA20
# ─────────────────────────────────────────────────────────────
def fetch_ema20_for_stocks(stock_names: list) -> dict:
    result = {}
    if not stock_names:
        return result

    tickers = [f"{s}.NS" for s in stock_names]
    try:
        raw = yf.download(
            tickers,
            period="60d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception:
        return result

    if "Close" not in raw.columns and not isinstance(raw.columns, pd.MultiIndex):
        return result

    close_col  = raw["Close"]
    close_data = {}

    if isinstance(close_col, pd.Series):
        close_data[tickers[0]] = close_col
    else:
        for ticker in tickers:
            if ticker in close_col.columns:
                close_data[ticker] = close_col[ticker]

    for stock in stock_names:
        ticker = f"{stock}.NS"
        if ticker not in close_data:
            result[stock] = {"ema20": None, "gap": None, "status": "⚠️ N/A"}
            continue

        series = close_data[ticker].dropna()
        if len(series) < 21:
            result[stock] = {"ema20": None, "gap": None, "status": "⚠️ N/A"}
            continue

        ema_series      = series.ewm(span=20, adjust=False).mean()
        yesterday_close = round(float(series.iloc[-2]), 2)
        ema20_yesterday = round(float(ema_series.iloc[-2]), 2)
        gap             = round(((yesterday_close - ema20_yesterday) / ema20_yesterday) * 100, 2)

        if yesterday_close < ema20_yesterday:
            status = "❌ Below"
        elif gap > EMA_DISTANCE_LIMIT:
            status = f"❌ +{gap:.1f}%"
        else:
            status = f"✅ +{gap:.1f}%"

        result[stock] = {"ema20": ema20_yesterday, "gap": gap, "status": status}

    return result


# ╔═══════════════════════════════════════════════════════════════╗
# ║  9 EMA (5MIN) SECTION START — HYBRID: Yahoo(8) + WS(1)        ║
# ╚═══════════════════════════════════════════════════════════════╝

EMA9_ENTRY_ZONE = 2.0
EMA9_WAIT_ZONE  = 4.0


def fetch_ema9_candles(stock_names: list) -> dict:
    result = {}
    if not stock_names:
        return result

    tickers = [f"{s}.NS" for s in stock_names]

    try:
        raw = yf.download(
            tickers,
            period      = "1d",
            interval    = "5m",
            auto_adjust = False,
            progress    = False,
            threads     = True,
        )
    except Exception:
        return result

    if raw.empty:
        return result

    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            return result
        close_col = raw["Close"]
    else:
        if "Close" not in raw.columns:
            return result
        close_col = raw["Close"]

    close_data = {}
    if isinstance(close_col, pd.Series):
        close_data[tickers[0]] = close_col
    else:
        for ticker in tickers:
            if ticker in close_col.columns:
                close_data[ticker] = close_col[ticker]

    for stock in stock_names:
        ticker = f"{stock}.NS"
        if ticker not in close_data:
            result[stock] = None
            continue

        series = close_data[ticker].dropna()

        if len(series) < 8:
            result[stock] = None
            continue

        last_8 = list(series.iloc[-9:-1].values)
        if len(last_8) < 8:
            last_8 = list(series.iloc[:-1].tail(8).values)

        result[stock] = last_8

    return result


def calculate_ema9_with_live(candles_8: list, live_ltp: float):
    if not candles_8 or len(candles_8) < 8 or live_ltp <= 0:
        return None

    series_9    = pd.Series(candles_8 + [live_ltp])
    ema9_series = series_9.ewm(span=9, adjust=False).mean()
    ema9_value  = round(float(ema9_series.iloc[-1]), 2)

    if ema9_value == 0:
        return None

    distance = round(((live_ltp - ema9_value) / ema9_value) * 100, 2)

    if live_ltp < ema9_value:
        status = f"📉 {distance:.1f}%"
        signal = "Below EMA9"
    elif distance <= EMA9_ENTRY_ZONE:
        status = f"✅ +{distance:.1f}%"
        signal = "Entry Zone"
    elif distance <= EMA9_WAIT_ZONE:
        status = f"⚠️ +{distance:.1f}%"
        signal = "Wait - Pullback"
    else:
        status = f"❌ +{distance:.1f}%"
        signal = "Extended - Avoid"

    return {
        "ema9"    : ema9_value,
        "distance": distance,
        "status"  : status,
        "signal"  : signal,
    }

# ╔═══════════════════════════════════════════════════════════════╗
# ║  9 EMA (5MIN) SECTION END                                     ║
# ╚═══════════════════════════════════════════════════════════════╝


# ╔═══════════════════════════════════════════════════════════════╗
# ║  PHASE & VOL TREND SECTION START                              ║
# ╚═══════════════════════════════════════════════════════════════╝

def build_candle(stock: str, candle_time: str, ticks: list):
    """Build a 5min OHLC candle from accumulated ticks."""
    if not ticks:
        return None
    ltps = [t["ltp"]    for t in ticks if t.get("ltp",    0) > 0]
    vols = [t["volume"] for t in ticks if t.get("volume", 0) > 0]
    if not ltps:
        return None
    return {
        "time"  : candle_time,
        "open"  : ltps[0],
        "high"  : max(ltps),
        "low"   : min(ltps),
        "close" : ltps[-1],
        "volume": vols[-1] if vols else 0,  # cumulative — use last tick
    }


def detect_phase_and_trend(candles: list) -> tuple:
    """
    3 phases — intraday trader friendly:
      🚀 BUILDING  — Price up + Vol up   → Enter/Hold
      ⚠️ PULLBACK  — Vol down            → Wait/Tighten SL
      🔴 REVERSAL  — Price down + Vol up → Exit immediately
    Returns: (phase: str, vol_trend: str)
    """
    if len(candles) < 2:
        return "⏳ Forming", "→ Stable"

    c1 = candles[-2]
    c2 = candles[-1]

    price_pct = ((c2["close"] - c1["close"]) / c1["close"] * 100) if c1["close"] > 0 else 0
    vol_pct   = ((c2["volume"] - c1["volume"]) / c1["volume"] * 100) if c1["volume"] > 0 else 0

    # Vol Trend
    if vol_pct > 10:
        vol_trend = "↑ Increasing"
    elif vol_pct < -10:
        vol_trend = "↓ Decreasing"
    else:
        vol_trend = "→ Stable"

    price_up   = price_pct >  0.3
    price_down = price_pct < -0.3
    vol_up     = vol_trend == "↑ Increasing"
    vol_down   = vol_trend == "↓ Decreasing"

    # 3 phases only
    if price_down and vol_up:
        phase = "🔴 REVERSAL"    # Strong sellers — exit
    elif vol_down:
        phase = "⚠️ PULLBACK"    # Volume fading — wait/tighten SL
    elif price_up and vol_up:
        phase = "🚀 BUILDING"    # Price + Vol both up — enter/hold
    else:
        phase = "⚠️ PULLBACK"    # Default conservative

    return phase, vol_trend


def update_phase_in_supabase(supabase, stock: str, today_str: str,
                              phase: str, vol_trend: str):
    """Update phase + vol_trend in momentum_signal_times every 5 min."""
    try:
        supabase.table("momentum_signal_times") \
            .update({"phase": phase, "vol_trend": vol_trend}) \
            .eq("stock", stock) \
            .eq("signal_date", today_str) \
            .execute()
    except Exception:
        pass

# ╔═══════════════════════════════════════════════════════════════╗
# ║  PHASE & VOL TREND SECTION END                                ║
# ╚═══════════════════════════════════════════════════════════════╝


# ─────────────────────────────────────────────────────────────
# SIGNAL DATA — SUPABASE CRUD
# ─────────────────────────────────────────────────────────────
def fetch_signal_data_from_supabase(supabase, today_str: str) -> dict:
    try:
        resp = supabase.table("momentum_signal_times") \
            .select("stock, signal_time, signal_price, peak_ltp, phase, vol_trend") \
            .eq("signal_date", today_str) \
            .execute()
        result = {}
        for row in resp.data:
            result[row["stock"]] = {
                "signal_time"  : row.get("signal_time", ""),
                "signal_price" : row.get("signal_price", None),
                "peak_ltp"     : row.get("peak_ltp", None),
                "phase"        : row.get("phase", None),
                "vol_trend"    : row.get("vol_trend", None),
            }
        return result
    except Exception:
        return {}


def save_signal_to_supabase(supabase, stock, today_str, signal_time,
                             vol_ratio, intraday_pct, vol_momentum,
                             momentum, score, signal_price):
    try:
        supabase.table("momentum_signal_times").upsert({
            "stock"        : stock,
            "signal_date"  : today_str,
            "signal_time"  : signal_time,
            "vol_ratio"    : round(float(vol_ratio), 2),
            "intraday_pct" : round(float(intraday_pct), 2),
            "vol_momentum" : vol_momentum,
            "momentum"     : momentum,
            "score"        : round(float(score), 2),
            "signal_price" : round(float(signal_price), 2),
            "peak_ltp"     : round(float(signal_price), 2),
        }, on_conflict="stock,signal_date", ignore_duplicates=True).execute()
    except Exception:
        pass


def update_peak_ltp_in_supabase(supabase, stock, today_str, new_peak_ltp):
    try:
        supabase.table("momentum_signal_times") \
            .update({"peak_ltp": round(float(new_peak_ltp), 2)}) \
            .eq("stock", stock) \
            .eq("signal_date", today_str) \
            .execute()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# FETCH HISTORICAL DATA
# ─────────────────────────────────────────────────────────────
def fetch_historical_data(supabase):
    all_dates = set()
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values") \
            .select("date") \
            .range(offset, offset + 999) \
            .execute()
        rows = resp.data
        if not rows:
            break
        for r in rows:
            if r.get("date"):
                all_dates.add(r["date"])
        if len(rows) < 1000:
            break
        offset += 1000

    if not all_dates:
        return None

    sorted_dates = sorted(all_dates, reverse=True)
    target_date  = sorted_dates[0]
    prev_date    = sorted_dates[1] if len(sorted_dates) > 1 else None
    last_5_dates = sorted_dates[1:6]

    target_rows = []
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values") \
            .select("stock, ltp, open, volume") \
            .eq("date", target_date) \
            .order("created_at", desc=True) \
            .range(offset, offset + 999) \
            .execute()
        rows = resp.data
        if not rows:
            break
        target_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000

    df_target = pd.DataFrame(target_rows)
    if not df_target.empty:
        df_target = df_target.drop_duplicates(subset="stock", keep="first")
        df_target = df_target.rename(columns={
            "ltp"   : "live_ltp",
            "open"  : "live_open",
            "volume": "live_volume",
        })

    df_prev = pd.DataFrame()
    if prev_date:
        prev_rows = []
        offset = 0
        while True:
            resp = supabase.table("websocket_stock_values") \
                .select("stock, ltp") \
                .eq("date", prev_date) \
                .order("created_at", desc=True) \
                .range(offset, offset + 999) \
                .execute()
            rows = resp.data
            if not rows:
                break
            prev_rows.extend(rows)
            if len(rows) < 1000:
                break
            offset += 1000

        df_prev = pd.DataFrame(prev_rows)
        if not df_prev.empty:
            df_prev = df_prev.drop_duplicates(subset="stock", keep="first")
            df_prev = df_prev.rename(columns={"ltp": "yesterday_close"})

    df_median = pd.DataFrame()
    if last_5_dates:
        vol_rows = []
        offset = 0
        while True:
            resp = supabase.table("websocket_stock_values") \
                .select("stock, volume") \
                .in_("date", last_5_dates) \
                .gt("volume", 0) \
                .range(offset, offset + 999) \
                .execute()
            rows = resp.data
            if not rows:
                break
            vol_rows.extend(rows)
            if len(rows) < 1000:
                break
            offset += 1000

        if vol_rows:
            df_vol    = pd.DataFrame(vol_rows)
            df_vol["volume"] = pd.to_numeric(df_vol["volume"], errors="coerce")
            df_median = df_vol.groupby("stock")["volume"].median().reset_index()
            df_median = df_median.rename(columns={"volume": "median_vol"})

    return {
        "target_date": target_date,
        "prev_date"  : prev_date,
        "df_target"  : df_target,
        "df_prev"    : df_prev,
        "df_median"  : df_median,
    }


# ─────────────────────────────────────────────────────────────
# CORE SCAN LOGIC
# ─────────────────────────────────────────────────────────────
def run_momentum_scan(historical: dict, live_ticks: dict, token_to_name: dict) -> tuple:
    df_target = historical["df_target"]
    df_prev   = historical["df_prev"]
    df_median = historical["df_median"]

    if live_ticks:
        rows = []
        for token, tick in live_ticks.items():
            name = token_to_name.get(token)
            if not name:
                continue
            rows.append({
                "stock"      : name,
                "live_ltp"   : tick.get("ltp", 0),
                "live_open"  : tick.get("open", 0),
                "live_volume": tick.get("volume", 0),
            })
        df_live     = pd.DataFrame(rows)
        data_source = "🟢 Live WebSocket"
    else:
        df_live     = df_target.copy() if not df_target.empty else pd.DataFrame()
        data_source = "🟡 Supabase (Market Closed)"

    if df_live.empty or df_prev.empty or df_median.empty:
        return pd.DataFrame(), data_source

    df = df_live.merge(df_prev,  on="stock", how="inner")
    df = df.merge(df_median,     on="stock", how="inner")

    for col in ["live_ltp", "live_open", "live_volume", "yesterday_close", "median_vol"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["live_ltp", "live_open", "live_volume", "yesterday_close", "median_vol"])
    df = df[df["median_vol"] > 0]
    df = df[df["yesterday_close"] > 0]

    df["vol_ratio"]      = df["live_volume"] / df["median_vol"]
    df["gap_pct"]        = ((df["live_open"] - df["yesterday_close"]) / df["yesterday_close"] * 100)
    df["intraday_pct"]   = ((df["live_ltp"]  - df["live_open"]) / df["live_open"] * 100)
    df["chg_vs_prev"]    = ((df["live_ltp"]  - df["yesterday_close"]) / df["yesterday_close"] * 100)
    df["priority_score"] = (df["vol_ratio"] * 0.3 + df["intraday_pct"] * 0.7)

    df = df[
        (df["vol_ratio"]    >= 1.5) &
        (df["intraday_pct"] >= 1.0) &
        (df["live_ltp"]     >  df["live_open"]) &
        (df["live_ltp"]     >  df["yesterday_close"]) &
        (df["live_open"]    >= df["yesterday_close"] * 0.99) &
        (df["live_open"]    <= df["yesterday_close"] * 1.01)
    ]

    if df.empty:
        return pd.DataFrame(), data_source

    def vol_momentum(r):
        if r >= 3.0: return "🔥 Very Strong"
        if r >= 2.0: return "⚡ Strong"
        if r >= 1.5: return "👀 Building"
        return ""

    def momentum_detection(v, i, g):
        if v >= 2.5 and i >= 1.5 and g <= 0.5: return "🚀 STRONG BUILDING"
        if v >= 2.0 and i >= 0.8:               return "📈 BUILDING"
        if v >= 1.5 and 0 <= i <= 0.7:          return "➡️ STABLE"
        if v >= 1.5 and i < 0:                  return "⚠️ COOLING"
        return "❌ WEAK"

    df["vol_momentum"]       = df["vol_ratio"].apply(vol_momentum)
    df["momentum_detection"] = df.apply(
        lambda x: momentum_detection(x["vol_ratio"], x["intraday_pct"], x["gap_pct"]), axis=1
    )

    df["vol_ratio"]      = df["vol_ratio"].round(2)
    df["gap_pct"]        = df["gap_pct"].round(2)
    df["intraday_pct"]   = df["intraday_pct"].round(2)
    df["chg_vs_prev"]    = df["chg_vs_prev"].round(2)
    df["priority_score"] = df["priority_score"].round(2)

    df = df.rename(columns={
        "stock"          : "Symbol",
        "yesterday_close": "Prev Close",
        "live_open"      : "Open",
        "live_ltp"       : "LTP",
        "live_volume"    : "Volume",
    })

    df["Gap %"]         = df["gap_pct"].apply(lambda x: f"{x:+.2f}%")
    df["Chg vs Prev %"] = df["chg_vs_prev"].apply(lambda x: f"{x:+.2f}%")
    df["Vol Ratio"]     = df["vol_ratio"].apply(lambda x: f"{x:.2f}x")
    df["Score"]         = df["priority_score"]

    display_cols = [
        "Symbol", "Prev Close", "Open", "LTP", "Volume",
        "Gap %", "Chg vs Prev %",
        "Vol Ratio", "vol_momentum", "momentum_detection", "Score",
        "vol_ratio", "intraday_pct", "priority_score",
    ]

    df = df[display_cols].rename(columns={
        "vol_momentum"      : "Vol Momentum",
        "momentum_detection": "Momentum",
    })

    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    return df, data_source
