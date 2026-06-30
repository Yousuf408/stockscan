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
# ║  9 EMA + PHASE + VOL TREND — UNIFIED CANDLE SYSTEM            ║
# ║  Day start → Yahoo 8 closed OHLCV candles (baseline)          ║
# ║  Every 5min → WS candle appended → Yahoo dependency reduces   ║
# ║  All candles stored in DB (candles jsonb column)               ║
# ║  Page refresh → DB se candles → instant EMA9 + Phase          ║
# ╚═══════════════════════════════════════════════════════════════╝

EMA9_ENTRY_ZONE = 2.0
EMA9_WAIT_ZONE  = 4.0


def fetch_initial_candles_yahoo(stock_names: list) -> dict:
    """
    Fetch last 8 closed 5min OHLCV candles from Yahoo Finance.
    Used only when DB has no candles for a stock.
    Returns: { stock: [ {time,open,high,low,close,volume,source}, ... ] }
    """
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

    is_multi = isinstance(raw.columns, pd.MultiIndex)

    try:
        close_df  = raw["Close"]  if (is_multi and "Close"  in raw.columns.get_level_values(0)) or (not is_multi and "Close"  in raw.columns) else None
        open_df   = raw["Open"]   if (is_multi and "Open"   in raw.columns.get_level_values(0)) or (not is_multi and "Open"   in raw.columns) else None
        high_df   = raw["High"]   if (is_multi and "High"   in raw.columns.get_level_values(0)) or (not is_multi and "High"   in raw.columns) else None
        low_df    = raw["Low"]    if (is_multi and "Low"    in raw.columns.get_level_values(0)) or (not is_multi and "Low"    in raw.columns) else None
        volume_df = raw["Volume"] if (is_multi and "Volume" in raw.columns.get_level_values(0)) or (not is_multi and "Volume" in raw.columns) else None
    except Exception:
        return result

    if close_df is None:
        return result

    for stock in stock_names:
        ticker = f"{stock}.NS"
        try:
            if isinstance(close_df, pd.Series):
                c = close_df.dropna()
                o = open_df.dropna()   if open_df   is not None else c
                h = high_df.dropna()   if high_df   is not None else c
                l = low_df.dropna()    if low_df    is not None else c
                v = volume_df.dropna() if volume_df is not None else pd.Series([0]*len(c), index=c.index)
            else:
                if ticker not in close_df.columns:
                    result[stock] = None
                    continue
                c = close_df[ticker].dropna()
                o = open_df[ticker].dropna()   if open_df   is not None and ticker in open_df.columns   else c
                h = high_df[ticker].dropna()   if high_df   is not None and ticker in high_df.columns   else c
                l = low_df[ticker].dropna()    if low_df    is not None and ticker in low_df.columns    else c
                v = volume_df[ticker].dropna() if volume_df is not None and ticker in volume_df.columns else pd.Series([0]*len(c), index=c.index)

            if len(c) < 8:
                result[stock] = None
                continue

            # Last 8 CLOSED candles — skip current forming candle
            idx_list = list(c.iloc[-9:-1].index) if len(c) >= 9 else list(c.iloc[:-1].index)
            candles = []
            for idx in idx_list:
                t_str = str(idx)
                # Extract HH:MM from timestamp
                try:
                    t_str = pd.Timestamp(idx).strftime("%H:%M")
                except Exception:
                    t_str = str(idx)[-8:-3]
                candles.append({
                    "time"  : t_str,
                    "open"  : round(float(o.get(idx, c[idx])), 2),
                    "high"  : round(float(h.get(idx, c[idx])), 2),
                    "low"   : round(float(l.get(idx, c[idx])), 2),
                    "close" : round(float(c[idx]), 2),
                    "volume": round(float(v.get(idx, 0)), 0),
                    "source": "yahoo",
                })

            result[stock] = candles[-8:] if len(candles) >= 8 else (candles if candles else None)

        except Exception:
            result[stock] = None

    return result


def build_ws_candle(candle_time: str, ticks: list):
    """Build a single 5min candle from accumulated WS ticks."""
    if not ticks:
        return None
    ltps = [t["ltp"]    for t in ticks if t.get("ltp",    0) > 0]
    vols = [t["volume"] for t in ticks if t.get("volume", 0) > 0]
    if not ltps:
        return None
    return {
        "time"  : candle_time,
        "open"  : round(ltps[0],    2),
        "high"  : round(max(ltps),  2),
        "low"   : round(min(ltps),  2),
        "close" : round(ltps[-1],   2),
        "volume": round(vols[-1], 0) if vols else 0,
        "source": "websocket",
    }


def append_candle_and_save(supabase, stock: str, today_str: str,
                           existing_candles: list, new_candle: dict) -> list:
    """
    Append new WS candle → keep max 9 → save to DB.
    Returns updated candles list.
    """
    candles = list(existing_candles or [])
    candles.append(new_candle)
    if len(candles) > 9:
        candles = candles[-9:]
    try:
        supabase.table("momentum_signal_times") \
            .update({"candles": candles}) \
            .eq("stock", stock) \
            .eq("signal_date", today_str) \
            .execute()
    except Exception:
        pass
    return candles


def save_initial_candles_to_db(supabase, stock: str, today_str: str, candles: list):
    """Save Yahoo initial 8 candles to DB when signal first detected."""
    try:
        supabase.table("momentum_signal_times") \
            .update({"candles": candles}) \
            .eq("stock", stock) \
            .eq("signal_date", today_str) \
            .execute()
    except Exception:
        pass


def calculate_ema9_with_live(candles: list, live_ltp: float):
    """
    Calculate 9 EMA using stored candles + live LTP as 9th value.
    Works with any number of candles (1-8 historical + 1 live).
    """
    if not candles or live_ltp <= 0:
        return None

    closes      = [c["close"] for c in candles]
    series_9    = pd.Series(closes + [live_ltp])
    ema9_series = series_9.ewm(span=9, adjust=False).mean()
    ema9_value  = round(float(ema9_series.iloc[-1]), 2)

    if ema9_value == 0:
        return None

    distance = round(((live_ltp - ema9_value) / ema9_value) * 100, 2)

    if live_ltp < ema9_value:
        status = f"\U0001f4c9 {distance:.1f}%"
        signal = "Below EMA9"
    elif distance <= EMA9_ENTRY_ZONE:
        status = f"\u2705 +{distance:.1f}%"
        signal = "Entry Zone"
    elif distance <= EMA9_WAIT_ZONE:
        status = f"\u26a0\ufe0f +{distance:.1f}%"
        signal = "Wait - Pullback"
    else:
        status = f"\u274c +{distance:.1f}%"
        signal = "Extended - Avoid"

    return {
        "ema9"    : ema9_value,
        "distance": distance,
        "status"  : status,
        "signal"  : signal,
    }


def detect_phase_and_trend(candles: list) -> tuple:
    """
    Detect phase + vol_trend from last 2 completed candles.
    Works with both Yahoo and WS candles.

    3 phases:
      BUILDING  — Price up + Vol up   → Enter/Hold
      PULLBACK  — Vol down            → Wait/Tighten SL
      REVERSAL  — Price down + Vol up → Exit immediately
    """
    if len(candles) < 2:
        return "\u23f3 Forming", "\u2192 Stable"

    c1 = candles[-2]
    c2 = candles[-1]

    price_pct = ((c2["close"] - c1["close"]) / c1["close"] * 100) if c1["close"] > 0 else 0
    vol_pct   = ((c2["volume"] - c1["volume"]) / c1["volume"] * 100) if c1["volume"] > 0 else 0

    if vol_pct > 10:
        vol_trend = "\u2191 Increasing"
    elif vol_pct < -10:
        vol_trend = "\u2193 Decreasing"
    else:
        vol_trend = "\u2192 Stable"

    price_up   = price_pct >  0.3
    price_down = price_pct < -0.3
    vol_up     = vol_trend == "\u2191 Increasing"
    vol_down   = vol_trend == "\u2193 Decreasing"

    if price_down and vol_up:
        phase = "\U0001f534 REVERSAL"
    elif vol_down:
        phase = "\u26a0\ufe0f PULLBACK"
    elif price_up and vol_up:
        phase = "\U0001f680 BUILDING"
    else:
        phase = "\u26a0\ufe0f PULLBACK"

    return phase, vol_trend


def update_phase_in_supabase(supabase, stock: str, today_str: str,
                              phase: str, vol_trend: str):
    """Update phase + vol_trend in DB every 5 min."""
    try:
        supabase.table("momentum_signal_times") \
            .update({"phase": phase, "vol_trend": vol_trend}) \
            .eq("stock", stock) \
            .eq("signal_date", today_str) \
            .execute()
    except Exception:
        pass

# ╔═══════════════════════════════════════════════════════════════╗
# ║  9 EMA + PHASE + VOL TREND SECTION END                        ║
# ╚═══════════════════════════════════════════════════════════════╝



# ─────────────────────────────────────────────────────────────
# SIGNAL DATA — SUPABASE CRUD
# ─────────────────────────────────────────────────────────────
def fetch_signal_data_from_supabase(supabase, today_str: str) -> dict:
    try:
        resp = supabase.table("momentum_signal_times") \
            .select("stock, signal_time, signal_price, peak_ltp, phase, vol_trend, candles") \
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
                "candles"      : row.get("candles", None),
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
    prev2_date   = sorted_dates[2] if len(sorted_dates) > 2 else None
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

    # ── Day-before-yesterday close (for "Prev Day Move %" column) ──
    df_prev2 = pd.DataFrame()
    if prev2_date:
        prev2_rows = []
        offset = 0
        while True:
            resp = supabase.table("websocket_stock_values") \
                .select("stock, ltp") \
                .eq("date", prev2_date) \
                .order("created_at", desc=True) \
                .range(offset, offset + 999) \
                .execute()
            rows = resp.data
            if not rows:
                break
            prev2_rows.extend(rows)
            if len(rows) < 1000:
                break
            offset += 1000

        df_prev2 = pd.DataFrame(prev2_rows)
        if not df_prev2.empty:
            df_prev2 = df_prev2.drop_duplicates(subset="stock", keep="first")
            df_prev2 = df_prev2.rename(columns={"ltp": "day_before_close"})

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
        "prev2_date" : prev2_date,
        "df_target"  : df_target,
        "df_prev"    : df_prev,
        "df_prev2"   : df_prev2,
        "df_median"  : df_median,
    }


# ─────────────────────────────────────────────────────────────
# CORE SCAN LOGIC
# ─────────────────────────────────────────────────────────────
def run_momentum_scan(historical: dict, live_ticks: dict, token_to_name: dict) -> tuple:
    df_target = historical["df_target"]
    df_prev   = historical["df_prev"]
    df_median = historical["df_median"]
    df_prev2  = historical.get("df_prev2", pd.DataFrame())

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

    # ── Prev Day Move % — optional, left join so missing data doesn't drop rows ──
    if not df_prev2.empty:
        df = df.merge(df_prev2, on="stock", how="left")
    else:
        df["day_before_close"] = None

    for col in ["live_ltp", "live_open", "live_volume", "yesterday_close", "median_vol"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["day_before_close"] = pd.to_numeric(df["day_before_close"], errors="coerce")

    df = df.dropna(subset=["live_ltp", "live_open", "live_volume", "yesterday_close", "median_vol"])
    df = df[df["median_vol"] > 0]
    df = df[df["yesterday_close"] > 0]

    df["vol_ratio"]      = df["live_volume"] / df["median_vol"]
    df["gap_pct"]        = ((df["live_open"] - df["yesterday_close"]) / df["yesterday_close"] * 100)
    df["intraday_pct"]   = ((df["live_ltp"]  - df["live_open"]) / df["live_open"] * 100)
    df["chg_vs_prev"]    = ((df["live_ltp"]  - df["yesterday_close"]) / df["yesterday_close"] * 100)
    df["priority_score"] = (df["vol_ratio"] * 0.3 + df["intraday_pct"] * 0.7)

    # ── Prev Day Move % = (yesterday_close - day_before_close) / day_before_close ──
    df["prev_day_move_pct"] = ((df["yesterday_close"] - df["day_before_close"]) / df["day_before_close"] * 100)

    df = df[
        (df["vol_ratio"]    >= 1.5) &
        (df["intraday_pct"] >= 1.0) &
        (df["live_ltp"]     >  df["live_open"]) &
        (df["live_ltp"]     >  df["yesterday_close"]) &
        (df["live_open"]    >= df["yesterday_close"] * 0.99) &   # max gap down 1%
        (df["live_open"]    <= df["yesterday_close"] * 1.02)     # max gap up 2%
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
    df["prev_day_move_pct"] = df["prev_day_move_pct"].round(2)

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
    df["Prev Day Move %"] = df["prev_day_move_pct"].apply(
        lambda x: f"{x:+.2f}%" if pd.notna(x) else "-"
    )

    display_cols = [
        "Symbol", "Prev Close", "Open", "LTP", "Volume",
        "Gap %", "Chg vs Prev %",
        "Vol Ratio", "vol_momentum", "momentum_detection", "Score",
        "vol_ratio", "intraday_pct", "priority_score",
        "Prev Day Move %", "prev_day_move_pct",
    ]

    df = df[display_cols].rename(columns={
        "vol_momentum"      : "Vol Momentum",
        "momentum_detection": "Momentum",
    })

    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    return df, data_source
