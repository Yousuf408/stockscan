"""
11_ORBScanner.py
ORB (Opening Range Breakout) Scanner
- Tracks stocks breaking above yesterday's high in first 15 mins (9:15–9:30 IST)
- Conditions: gap < 1%, yesterday close > EMA20, open/LTP > yesterday high
- After 9:30: stops adding new stocks, keeps showing with live updates
"""

import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timezone, timedelta
from supabase import create_client

import angel_ws
from config import STOCKS_WATCHLIST

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG — must be first
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="ORB Scanner", page_icon="📈", layout="wide")
st.markdown("<style>header {visibility: hidden;} .block-container {padding-top: 1rem !important;}</style>", unsafe_allow_html=True)

# ── Auto-connect WebSocket ────────────────────────────────────
if not angel_ws.is_connected():
    if "orb_ws_init" not in st.session_state:
        st.session_state["orb_ws_init"] = True
        if "angel_auth" not in st.session_state:
            from angel_auth import angel_login
            st.session_state["angel_auth"] = angel_login()
        auth = st.session_state["angel_auth"]
        if auth:
            angel_ws.start_websocket(
                jwt_token  = auth["jwt_token"],
                api_key    = auth["api_key"],
                client_id  = auth["client_id"],
                feed_token = auth["feed_token"],
            )

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
SUPABASE_URL       = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY       = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"
IST                = timezone(timedelta(hours=5, minutes=30))
EMA_DISTANCE_LIMIT = 8.0
MAX_GAP_PCT        = 1.0

TOKEN_TO_NAME = {token: name for name, token, kind in STOCKS_WATCHLIST}
NAME_TO_TOKEN = {name: token for name, token, kind in STOCKS_WATCHLIST}

ORB_START_H, ORB_START_M = 9, 15
ORB_END_H,   ORB_END_M   = 9, 30

# ─────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────────────────────────────────────
# FETCH HISTORICAL DATA
# ─────────────────────────────────────────────────────────────
def fetch_orb_historical_data():
    supabase = get_supabase()
    all_dates = set()
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values").select("date").range(offset, offset + 999).execute()
        rows = resp.data
        if not rows: break
        for r in rows:
            if r.get("date"): all_dates.add(r["date"])
        if len(rows) < 1000: break
        offset += 1000

    if not all_dates: return None
    sorted_dates = sorted(all_dates, reverse=True)
    prev_date    = sorted_dates[1] if len(sorted_dates) > 1 else sorted_dates[0]
    last_5_dates = sorted_dates[1:6]

    prev_rows = []
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values").select("stock, high, ltp").eq("date", prev_date).range(offset, offset + 999).execute()
        rows = resp.data
        if not rows: break
        prev_rows.extend(rows)
        if len(rows) < 1000: break
        offset += 1000

    df_prev = pd.DataFrame(prev_rows)
    if not df_prev.empty:
        df_prev = df_prev.drop_duplicates(subset="stock", keep="first")
        df_prev["high"] = pd.to_numeric(df_prev["high"], errors="coerce")
        df_prev["ltp"]  = pd.to_numeric(df_prev["ltp"],  errors="coerce")
        df_prev = df_prev.rename(columns={"high": "yesterday_high", "ltp": "yesterday_close"})

    vol_rows = []
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values").select("stock, volume").in_("date", last_5_dates).gt("volume", 0).range(offset, offset + 999).execute()
        rows = resp.data
        if not rows: break
        vol_rows.extend(rows)
        if len(rows) < 1000: break
        offset += 1000

    df_median = pd.DataFrame()
    if vol_rows:
        df_vol = pd.DataFrame(vol_rows)
        df_vol["volume"] = pd.to_numeric(df_vol["volume"], errors="coerce")
        df_median = df_vol.groupby("stock")["volume"].median().reset_index()
        df_median = df_median.rename(columns={"volume": "median_vol"})

    return {"prev_date": prev_date, "df_prev": df_prev, "df_median": df_median}


# ─────────────────────────────────────────────────────────────
# UNIFIED YFINANCE FETCH — EMA20 + EMA5m + Candles in ONE call
# Called once on page load, cached in session_state
# ─────────────────────────────────────────────────────────────
def fetch_all_stock_data(stock_names: list, today_opens: dict) -> dict:
    """
    Single yfinance batch fetch per interval.
    Returns: {symbol: {
        "ema20_status": str,
        "ema9": float, "ema9_pct": float,
        "ema200": float, "ema200_pct": float,
        "candles_5m":  [...],
        "candles_15m": [...],
        "ema9_pts":    [...],  # for chart
        "ema200_pts":  [...],  # for chart
        "ema9_pts_15m":   [...],
        "ema200_pts_15m": [...],
    }}
    """
    if not stock_names:
        return {}

    tickers = [f"{s}.NS" for s in stock_names]
    result  = {s: {} for s in stock_names}

    # ── 1. Daily data — EMA20 ─────────────────────────────────
    try:
        raw_daily = yf.download(tickers, period="60d", auto_adjust=True, progress=False, threads=True)
        close_daily = raw_daily["Close"] if "Close" in raw_daily.columns else None

        if close_daily is not None:
            for stock in stock_names:
                ticker = f"{stock}.NS"
                try:
                    series = (close_daily[ticker] if isinstance(close_daily, pd.DataFrame) else close_daily).dropna()
                    if len(series) >= 21:
                        ema_s   = series.ewm(span=20, adjust=False).mean()
                        yclose  = round(float(series.iloc[-2]), 2)
                        ema20   = round(float(ema_s.iloc[-2]),  2)
                        gap     = round(((yclose - ema20) / ema20) * 100, 2)
                        if yclose < ema20:
                            result[stock]["ema20_status"] = "❌ Below"
                        elif gap > EMA_DISTANCE_LIMIT:
                            result[stock]["ema20_status"] = f"❌ +{gap:.1f}%"
                        else:
                            result[stock]["ema20_status"] = f"✅ +{gap:.1f}%"
                    else:
                        result[stock]["ema20_status"] = "⚠️ N/A"
                except Exception:
                    result[stock]["ema20_status"] = "⚠️ N/A"
    except Exception:
        for s in stock_names:
            result[s]["ema20_status"] = "⚠️ N/A"

    # ── 2. 5min data — EMA9/200 values + candles for chart ────
    try:
        raw_5m = yf.download(tickers, period="5d", interval="5m", auto_adjust=True, progress=False, threads=True)
        needed = ["Open", "High", "Low", "Close", "Volume"]

        for stock in stock_names:
            ticker     = f"{stock}.NS"
            today_open = today_opens.get(stock, 0)
            try:
                if isinstance(raw_5m.columns, pd.MultiIndex):
                    df_s = raw_5m.xs(ticker, axis=1, level=1)[needed].dropna()
                else:
                    df_s = raw_5m[needed].dropna()

                if df_s.empty or len(df_s) < 9:
                    continue

                closes = df_s["Close"].tolist()

                # EMA values (with today open appended)
                if today_open > 0:
                    closes_ext  = pd.Series(closes + [today_open])
                    ema9_ext    = closes_ext.ewm(span=9,   adjust=False).mean()
                    result[stock]["ema9"]     = round(float(ema9_ext.iloc[-1]), 2)
                    result[stock]["ema9_pct"] = round(((today_open - result[stock]["ema9"]) / result[stock]["ema9"]) * 100, 2)
                    if len(closes_ext) >= 200:
                        ema200_ext = closes_ext.ewm(span=200, adjust=False).mean()
                        result[stock]["ema200"]     = round(float(ema200_ext.iloc[-1]), 2)
                        result[stock]["ema200_pct"] = round(((today_open - result[stock]["ema200"]) / result[stock]["ema200"]) * 100, 2)

                # Candles + EMA lines for chart
                candles, times, c_list = [], [], []
                for ts, r in df_s.iterrows():
                    try:
                        unix = int(ts.timestamp())
                    except Exception:
                        continue
                    candles.append({"time": unix, "open": round(float(r["Open"]),2),
                                    "high": round(float(r["High"]),2), "low": round(float(r["Low"]),2),
                                    "close": round(float(r["Close"]),2), "volume": round(float(r["Volume"]),0)})
                    times.append(unix)
                    c_list.append(float(r["Close"]))

                if candles:
                    cs       = pd.Series(c_list)
                    ema9_l   = cs.ewm(span=9,   adjust=False).mean().round(2).tolist()
                    ema200_l = cs.ewm(span=200, adjust=False).mean().round(2).tolist() if len(cs) >= 20 else []
                    result[stock]["candles_5m"]  = candles
                    result[stock]["ema9_pts"]    = [{"time": t, "value": v} for t, v in zip(times, ema9_l)]
                    result[stock]["ema200_pts"]  = [{"time": t, "value": v} for t, v in zip(times, ema200_l)] if ema200_l else []

            except Exception:
                continue
    except Exception:
        pass

    # ── 3. 15min data — candles only for chart ────────────────
    try:
        raw_15m = yf.download(tickers, period="30d", interval="15m", auto_adjust=True, progress=False, threads=True)

        for stock in stock_names:
            ticker = f"{stock}.NS"
            try:
                if isinstance(raw_15m.columns, pd.MultiIndex):
                    df_s = raw_15m.xs(ticker, axis=1, level=1)[needed].dropna()
                else:
                    df_s = raw_15m[needed].dropna()

                if df_s.empty: continue

                candles, times, c_list = [], [], []
                for ts, r in df_s.iterrows():
                    try:
                        unix = int(ts.timestamp())
                    except Exception:
                        continue
                    candles.append({"time": unix, "open": round(float(r["Open"]),2),
                                    "high": round(float(r["High"]),2), "low": round(float(r["Low"]),2),
                                    "close": round(float(r["Close"]),2), "volume": round(float(r["Volume"]),0)})
                    times.append(unix)
                    c_list.append(float(r["Close"]))

                if candles:
                    cs        = pd.Series(c_list)
                    ema9_l    = cs.ewm(span=9,   adjust=False).mean().round(2).tolist()
                    ema200_l  = cs.ewm(span=200, adjust=False).mean().round(2).tolist() if len(cs) >= 20 else []
                    result[stock]["candles_15m"]     = candles
                    result[stock]["ema9_pts_15m"]    = [{"time": t, "value": v} for t, v in zip(times, ema9_l)]
                    result[stock]["ema200_pts_15m"]  = [{"time": t, "value": v} for t, v in zip(times, ema200_l)] if ema200_l else []

            except Exception:
                continue
    except Exception:
        pass

    return result


def get_stock_data_cache(stock_names: list, today_opens: dict) -> dict:
    """Session-state cache — fetch only new stocks."""
    if "orb_stock_cache" not in st.session_state:
        st.session_state["orb_stock_cache"] = {}
    cache      = st.session_state["orb_stock_cache"]
    new_stocks = [s for s in stock_names if s not in cache]
    if new_stocks:
        fetched = fetch_all_stock_data(new_stocks, today_opens)
        cache.update(fetched)
        st.session_state["orb_stock_cache"] = cache
    return cache


# ─────────────────────────────────────────────────────────────
# ORB SUPABASE
# ─────────────────────────────────────────────────────────────
def fetch_orb_signals_from_supabase(today_str: str) -> dict:
    try:
        supabase = get_supabase()
        resp = supabase.table("orb") \
            .select("stock, signal_time, yesterday_high, today_open, gap_pct, signal_price, peak_ltp, ema20_status") \
            .eq("signal_date", today_str).execute()
        result = {}
        for row in resp.data:
            result[row["stock"]] = {
                "signal_time"   : row.get("signal_time", ""),
                "yesterday_high": row.get("yesterday_high", 0),
                "today_open"    : row.get("today_open", 0),
                "gap_pct"       : row.get("gap_pct", 0),
                "signal_price"  : row.get("signal_price", 0),
                "peak_ltp"      : row.get("peak_ltp", 0),
                "ema20_status"  : row.get("ema20_status", ""),
            }
        return result
    except Exception:
        return {}


def save_orb_signal_to_supabase(stock, today_str, signal_time, yesterday_high,
                                  today_open, gap_pct, signal_price, ema20_status,
                                  vol_ratio=0, ema200_5m=None, ema200_pct=None):
    try:
        supabase = get_supabase()
        row = {
            "stock": stock, "signal_date": today_str, "signal_time": signal_time,
            "yesterday_high": round(float(yesterday_high), 2), "today_open": round(float(today_open), 2),
            "gap_pct": round(float(gap_pct), 2), "signal_price": round(float(signal_price), 2),
            "peak_ltp": round(float(signal_price), 2), "ema20_status": ema20_status,
            "vol_ratio": round(float(vol_ratio), 2),
        }
        if ema200_5m  is not None: row["ema200_5m"]  = round(float(ema200_5m), 2)
        if ema200_pct is not None: row["ema200_pct"] = round(float(ema200_pct), 2)
        supabase.table("orb").upsert(row, on_conflict="stock,signal_date", ignore_duplicates=True).execute()
    except Exception:
        pass


def update_orb_peak_ltp(stock, today_str, new_peak):
    try:
        get_supabase().table("orb").update({"peak_ltp": round(float(new_peak), 2)}) \
            .eq("stock", stock).eq("signal_date", today_str).execute()
    except Exception:
        pass


def update_orb_ema200(stock, today_str, ema200_5m, ema200_pct):
    try:
        get_supabase().table("orb").update({
            "ema200_5m": round(float(ema200_5m), 2), "ema200_pct": round(float(ema200_pct), 2)
        }).eq("stock", stock).eq("signal_date", today_str).execute()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def get_vol_momentum(ratio: float) -> str:
    if ratio >= 3.0: return "🔥 Very Strong"
    if ratio >= 2.0: return "⚡ Strong"
    if ratio >= 1.5: return "👀 Building"
    if ratio >= 1.0: return "😐 Weak"
    return ""

def _short_vol(vol):
    if vol >= 1_000_000: return f"{vol/1_000_000:.2f}M"
    if vol >= 1_000:     return f"{vol/1_000:.1f}K"
    return str(int(vol))

def _ema_cell(status):
    if not status or status == "⏳": return '<span style="color:#94a3b8">⏳</span>'
    s = str(status)
    if s.startswith("✅"): return f'<span class="ema-pass">{s}</span>'
    if "Below" in s:       return f'<span class="ema-fail">{s}</span>'
    if s.startswith("❌"): return f'<span class="ema-ext">{s}</span>'
    return f'<span style="color:#94a3b8">{s}</span>'

def _ema5m_cell(val, pct):
    if val is None or pct is None: return '<span style="color:#94a3b8">⏳</span>'
    color = "#16a34a" if pct >= 0 else "#dc2626"
    icon  = "🟢" if pct >= 0 else "❌"
    sign  = "+" if pct >= 0 else ""
    return (f'<div class="num-primary">₹{float(val):,.2f}</div>'
            f'<div style="color:{color};font-weight:700;font-size:13px;">{icon} {sign}{pct:.1f}%</div>')

def _vol_badge(vm):
    if "Very Strong" in vm or "🔥" in vm: return '<span class="vol-badge vol-high">🔥 Very Strong</span>'
    if "Strong" in vm or "⚡" in vm:      return '<span class="vol-badge vol-med">⚡ Strong</span>'
    if "Building" in vm or "👀" in vm:    return '<span class="vol-badge vol-low">👀 Building</span>'
    return f'<span class="vol-badge vol-low">{vm}</span>'

def _move_color(val):
    if val >= 5.0: return "#16a34a"
    if val >= 2.0: return "#ca8a04"
    if val >= 0:   return "#64748b"
    return "#dc2626"

def _signal_price_html(price_str, move):
    positive = move >= 0
    w        = min(abs(move) * 10, 100)
    color    = _move_color(move)
    sign     = "+" if positive else ""
    fill     = "fill-green" if positive else "fill-red"
    return (f'<div class="sig-price-wrap">'
            f'<div class="sig-top-row"><span class="num-primary">{price_str}</span>'
            f'<span class="bar-pct" style="color:{color}">{sign}{move:.2f}%</span></div>'
            f'<div class="progress-bar"><div class="progress-fill {fill}" style="width:{w:.0f}%"></div></div>'
            f'</div>')

def _chg_html(val):
    cls  = "chg-pos" if val >= 0 else "chg-neg"
    sign = "▲" if val >= 0 else "▼"
    return f'<span class="{cls}">{sign} {abs(val):.2f}%</span>'


# ─────────────────────────────────────────────────────────────
# HTML TABLE
# ─────────────────────────────────────────────────────────────
_ORB_STYLES = """
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  margin: 0 !important; padding: 0 !important; background: #f5f7fa !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
  color: #1a202c; font-size: 13px;
}
.filterbar {
  background: #fff; border-bottom: 1px solid #e2e8f0;
  padding: 8px 16px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.filter-label { font-size: 12px; font-weight: 700; color: #374151; }
.filter-count { background: #f1f5f9; border: 1px solid #e2e8f0; padding: 3px 8px; border-radius: 4px; font-size: 12px; color: #64748b; }
.filter-count b { color: #1a202c; }
select.filter-select {
  border: 1px solid #e2e8f0; background: #fff; padding: 6px 28px 6px 10px;
  border-radius: 6px; font-size: 13px; color: #374151; cursor: pointer;
  outline: none; appearance: none; height: 36px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center;
}
.filter-sep { width: 1px; height: 20px; background: #e2e8f0; }
.meta-info  { margin-left: auto; font-size: 13px; font-weight: 600; color: #0f172a; }
.table-wrap { padding: 12px 16px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; border: 1px solid #e2e8f0; overflow: hidden; }
thead tr { background: #fef9f0; }
th {
  padding: 10px 10px; text-align: left; font-size: 11px; font-weight: 800;
  color: #0f172a; border-bottom: 2px solid #fcd34d; white-space: nowrap;
  cursor: pointer; user-select: none; transition: background 0.15s;
  border-right: 1px solid #fde68a; text-transform: uppercase; letter-spacing: 0.4px;
}
th:last-child { border-right: none; }
th:hover { background: #fef3c7; }
th.active-col { background: #fde68a !important; }
th .sort-arrow { margin-left: 4px; font-size: 10px; opacity: 0.5; }
th.th-ema    { background: #f0fdf4; color: #166534; }
th.th-orb    { background: #fef3c7; color: #92400e; }
th.th-ema9   { background: #e0f2fe; color: #0369a1; }
th.th-ema200 { background: #fef9c3; color: #854d0e; }
th.th-sig    { background: #ede9fe; color: #5b21b6; }
th.th-risk   { background: #fee2e2; color: #991b1b; }
th.th-tgt    { background: #dcfce7; color: #166534; }
tbody tr.main-row { border-bottom: 1px solid #e2e8f0; cursor: pointer; transition: background 0.1s; border-left: 4px solid #e2e8f0; }
tbody tr.main-row:hover  { background: #f0f9ff; }
tbody tr.main-row.expanded { background: #f0f9ff; border-bottom: none; }
tbody tr.main-row:nth-child(even) { background: #f8fafc; }
tbody tr.main-row:nth-child(even):hover { background: #f0f9ff; }
tbody tr.main-row.vol-fire   { border-left: 4px solid #f59e0b; }
tbody tr.main-row.vol-strong { border-left: 4px solid #3b82f6; }
tbody tr.main-row.vol-build  { border-left: 4px solid #22c55e; }
td { padding: 9px 10px; vertical-align: middle; white-space: nowrap; border-right: 1px solid #e2e8f0; font-size: 13px; color: #374151; border-bottom: 1px solid #e2e8f0; }
td:last-child { border-right: none; }
td.active-col { background: #eff6ff; }
tr.expand-row td { padding: 0; border-bottom: 2px solid #3b82f6; }
.expand-panel { background: #f0f9ff; padding: 12px 16px; display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; }
.expand-card { background: #fff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 8px 10px; }
.expand-card .ec-label { font-size: 10px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.expand-card .ec-value { font-size: 14px; font-weight: 700; color: #1e3a5f; margin-top: 2px; }
.expand-card .ec-sub   { font-size: 10px; color: #94a3b8; margin-top: 1px; }
.stock-cell  { display: flex; align-items: center; gap: 8px; }
.expand-icon { width: 18px; height: 18px; border-radius: 4px; background: #e2e8f0; color: #64748b; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex-shrink: 0; transition: all 0.15s; }
tr.expanded .expand-icon { background: #3b82f6; color: #fff; }
.stock-name { font-weight: 700; font-size: 13px; color: #1e3a5f; }
.vol-badge  { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 700; }
.vol-high   { background: #fef3c7; color: #92400e; }
.vol-med    { background: #e0f2fe; color: #075985; }
.vol-low    { background: #f1f5f9; color: #64748b; }
.num-primary { font-size: 13px; font-weight: 700; color: #0f172a; }
.peak-val    { color: #7c3aed; font-weight: 700; font-size: 13px; }
.chg-pos     { color: #16a34a; font-weight: 600; font-size: 13px; }
.chg-neg     { color: #dc2626; font-weight: 600; font-size: 13px; }
.ema-pass    { color: #16a34a; font-weight: 600; font-size: 13px; }
.ema-fail    { color: #dc2626; font-weight: 600; font-size: 13px; }
.ema-ext     { color: #ea580c; font-weight: 600; font-size: 13px; }
.sig-price-wrap { display: flex; flex-direction: column; gap: 3px; min-width: 120px; }
.sig-top-row    { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.progress-bar   { width: 100%; height: 4px; background: #e2e8f0; border-radius: 3px; overflow: hidden; }
.progress-fill  { height: 100%; border-radius: 3px; transition: width 0.3s; }
.fill-green { background: #22c55e; }
.fill-red   { background: #ef4444; }
.bar-pct    { font-size: 12px; font-weight: 600; white-space: nowrap; }
.sl-val     { color: #dc2626; font-weight: 700; font-size: 13px; }
.tgt-val    { color: #16a34a; font-weight: 700; font-size: 13px; }
.copy-btn   { cursor: pointer; font-weight: 700; color: #1e3a5f; background: transparent; border: none; padding: 0; font-size: 13px; transition: color 0.2s; }
.copy-btn:hover  { color: #10b981; }
.copy-btn.copied { color: #10b981; }
.toast { position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); background: #0f172a; color: white; padding: 8px 20px; border-radius: 8px; font-size: 13px; z-index: 9999; opacity: 0; transition: opacity 0.3s; pointer-events: none; }
.toast.show { opacity: 1; }
::-webkit-scrollbar { height: 5px; width: 5px; }
::-webkit-scrollbar-track { background: #f1f5f9; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
</style>
<div id="orb-toast" class="toast">✅ Copied!</div>
<script>
var activeCol  = -1;
var lwcCharts  = {};

function copyORB(btn, sym) {
    navigator.clipboard.writeText(sym);
    btn.classList.add('copied'); btn.innerText = '✓ ' + sym;
    var t = document.getElementById('orb-toast'); t.classList.add('show');
    setTimeout(function(){ btn.classList.remove('copied'); btn.innerText = sym; t.classList.remove('show'); }, 1500);
}

function toggleRow(sym) {
    var mainRow = document.getElementById('orb-main-' + sym);
    var expRow  = document.getElementById('orb-exp-'  + sym);
    if (!expRow) return;
    var isOpen = expRow.style.display !== 'none';
    expRow.style.display = isOpen ? 'none' : 'table-row';
    mainRow.classList.toggle('expanded', !isOpen);
    var icon = mainRow.querySelector('.expand-icon');
    if (icon) icon.textContent = isOpen ? '+' : '−';
    if (!isOpen && !mainRow.dataset.chartLoaded) {
        mainRow.dataset.chartLoaded = 'true';
        loadLWC(sym, '5m');
    }
}

function loadLWC(sym, tf) {
    var container = document.getElementById('lwc-' + sym);
    if (!container) return;
    var data = tf === '15m' ? window['lwcData15m_' + sym] : window['lwcData5m_' + sym];
    if (!data || !data.candles || !data.candles.length) {
        container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#758696;font-size:13px;">⏳ No chart data</div>';
        return;
    }
    container.innerHTML = '';
    if (lwcCharts[sym]) { try { lwcCharts[sym].remove(); } catch(e){} delete lwcCharts[sym]; }

    var doRender = function() {
        var chart = LightweightCharts.createChart(container, {
            width : container.clientWidth || 900, height: 480,
            layout: { background: { type: 'solid', color: '#131722' }, textColor: '#d1d4dc', fontSize: 12 },
            grid  : { vertLines: { color: '#1e222d' }, horzLines: { color: '#1e222d' } },
            crosshair     : { mode: LightweightCharts.CrosshairMode.Normal,
                              vertLine: { color: '#758696', width: 1, style: 3, labelBackgroundColor: '#2a2e39' },
                              horzLine: { color: '#758696', width: 1, style: 3, labelBackgroundColor: '#2a2e39' } },
            rightPriceScale: { borderColor: '#2a2e39', scaleMargins: { top: 0.1, bottom: 0.25 } },
            timeScale      : { borderColor: '#2a2e39', timeVisible: true, secondsVisible: false, rightOffset: 5, barSpacing: 8 },
            handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
            handleScale : { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
        });
        lwcCharts[sym] = chart;

        var cs = chart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: '#26a69a', downColor: '#ef5350',
            borderUpColor: '#26a69a', borderDownColor: '#ef5350',
            wickUpColor: '#26a69a', wickDownColor: '#ef5350',
        });
        cs.setData(data.candles);

        var vs = chart.addSeries(LightweightCharts.HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol' });
        chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
        vs.setData(data.candles.map(function(c){ return { time: c.time, value: c.volume, color: c.close >= c.open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' }; }));

        if (data.ema9 && data.ema9.length) {
            var e9 = chart.addSeries(LightweightCharts.LineSeries, { color: '#ff9800', lineWidth: 2, title: 'EMA9', priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false });
            e9.setData(data.ema9);
        }
        if (data.ema200 && data.ema200.length) {
            var e200 = chart.addSeries(LightweightCharts.LineSeries, { color: '#2962ff', lineWidth: 2, title: 'EMA200', priceLineVisible: false, lastValueVisible: true, crosshairMarkerVisible: false });
            e200.setData(data.ema200);
        }
        chart.timeScale().fitContent();
        new ResizeObserver(function(){ chart.applyOptions({ width: container.clientWidth }); }).observe(container);

        // Zoom buttons
        var wrap = document.getElementById('lwc-wrap-' + sym);
        if (wrap && !wrap.dataset.zoomAdded) {
            wrap.dataset.zoomAdded = 'true';
            var zb = document.createElement('div');
            zb.style.cssText = 'display:flex;gap:4px;margin-top:6px;justify-content:flex-end;';
            var bs = 'padding:4px 10px;border-radius:4px;border:1px solid #2a2e39;background:#1e222d;color:#d1d4dc;font-size:12px;cursor:pointer;font-weight:600;';
            zb.innerHTML =
                '<button onclick="lwcZoom(\''+sym+'\',0.5)" style="'+bs+'">−</button>' +
                '<button onclick="lwcZoom(\''+sym+'\',2)"   style="'+bs+'">+</button>' +
                '<button onclick="lwcFit(\''+sym+'\')"      style="'+bs+'">⊞ Fit</button>' +
                '<button onclick="lwcScroll(\''+sym+'\',-5)" style="'+bs+'">‹</button>' +
                '<button onclick="lwcScroll(\''+sym+'\',5)"  style="'+bs+'">›</button>';
            wrap.appendChild(zb);
        }
    };

    if (typeof LightweightCharts !== 'undefined') { doRender(); }
    else {
        var sc = document.createElement('script');
        sc.src = 'https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js';
        sc.onload = doRender;
        document.head.appendChild(sc);
    }
}

function switchTF(sym, tf) {
    var b5  = document.getElementById('btn-5m-'  + sym);
    var b15 = document.getElementById('btn-15m-' + sym);
    var active   = 'padding:3px 10px;border-radius:4px;border:1px solid #2962ff;background:#2962ff;color:white;font-size:11px;font-weight:700;cursor:pointer;';
    var inactive = 'padding:3px 10px;border-radius:4px;border:1px solid #2a2e39;background:#1e222d;color:#d1d4dc;font-size:11px;font-weight:700;cursor:pointer;';
    if (b5)  b5.style.cssText  = tf === '5m'  ? active : inactive;
    if (b15) b15.style.cssText = tf === '15m' ? active : inactive;
    loadLWC(sym, tf);
}

function lwcZoom(sym, f) {
    var c = lwcCharts[sym]; if (!c) return;
    var r = c.timeScale().getVisibleRange(); if (!r) return;
    var mid = (r.from + r.to) / 2, half = (r.to - r.from) / 2 / f;
    c.timeScale().setVisibleRange({ from: mid - half, to: mid + half });
}
function lwcFit(sym)      { var c = lwcCharts[sym]; if (c) c.timeScale().fitContent(); }
function lwcScroll(sym,b) { var c = lwcCharts[sym]; if (c) c.timeScale().scrollToPosition(c.timeScale().scrollPosition() + b, false); }

function toggleColExpand(col) {
    document.querySelectorAll('th').forEach(function(t){ t.classList.remove('active-col'); });
    document.querySelectorAll('td').forEach(function(t){ t.classList.remove('active-col'); });
    if (activeCol === col) { activeCol = -1; return; }
    activeCol = col;
    document.querySelectorAll('th')[col].classList.add('active-col');
    document.querySelectorAll('tbody tr.main-row').forEach(function(row){
        var cells = row.querySelectorAll('td');
        if (cells[col]) cells[col].classList.add('active-col');
    });
}

function applyFilter() {
    var volVal    = document.getElementById('orbVolFilter').value.toLowerCase();
    var emaVal    = document.getElementById('orbEmaFilter').value;
    var ema200Val = document.getElementById('orbEma200Filter').value;
    // persist filter state across re-renders
    try {
        sessionStorage.setItem('orb_vol_filter',    volVal);
        sessionStorage.setItem('orb_ema_filter',    emaVal);
        sessionStorage.setItem('orb_ema200_filter', ema200Val);
    } catch(e) {}
    var count = 0;
    document.querySelectorAll('tbody tr.main-row').forEach(function(row){
        var show = true;
        if (volVal    && !(row.dataset.vol    || '').toLowerCase().includes(volVal)) show = false;
        if (emaVal === 'pass' && !(row.dataset.ema    || '').includes('✅'))          show = false;
        if (emaVal === 'fail' && !(row.dataset.ema    || '').includes('❌'))          show = false;
        if (ema200Val === 'above' && (row.dataset.ema200 || '') !== 'above')          show = false;
        if (ema200Val === 'below' && (row.dataset.ema200 || '') !== 'below')          show = false;
        row.style.display = show ? '' : 'none';
        var er = document.getElementById('orb-exp-' + row.dataset.sym);
        if (er) er.style.display = 'none';
        if (show) count++;
    });
    document.getElementById('orbMatchCount').textContent = count;
}

// Restore filter state on every render
(function restoreFilters() {
    try {
        var v   = sessionStorage.getItem('orb_vol_filter');
        var e   = sessionStorage.getItem('orb_ema_filter');
        var e2  = sessionStorage.getItem('orb_ema200_filter');
        var vEl  = document.getElementById('orbVolFilter');
        var eEl  = document.getElementById('orbEmaFilter');
        var e2El = document.getElementById('orbEma200Filter');
        if (v  && vEl)  vEl.value  = v;
        if (e  && eEl)  eEl.value  = e;
        if (e2 && e2El) e2El.value = e2;
        if ((v && v !== '') || (e && e !== '') || (e2 && e2 !== '')) {
            applyFilter();
        }
    } catch(err) {}
})();
</script>
"""


def render_orb_table(df, window_status="", prev_date="", tick_count=0,
                     stock_cache=None) -> str:
    rows_html = ""
    candle_js = ""
    total     = len(df)
    sc        = stock_cache or {}

    for _, row in df.iterrows():
        symbol        = str(row["Symbol"])
        signal_time   = str(row.get("Signal Time", "-"))
        ema_status    = row.get("EMA20 Status", "")
        yest_high     = row.get("Yesterday High", 0)
        today_open    = row.get("Today Open", 0)
        gap_pct_raw   = row.get("Gap %", "0%")
        vol_ratio_str = str(row.get("Vol Ratio", "0x"))
        ltp           = float(row.get("LTP", 0))
        signal_price  = row.get("Signal Price", None)
        peak_ltp      = row.get("High Since Signal", None)
        vol_mom       = str(row.get("Vol Momentum", ""))
        ema9_val      = row.get("EMA9", None)
        ema9_pct      = row.get("EMA9 Pct", None)
        ema200_val    = row.get("EMA200", None)
        ema200_pct    = row.get("EMA200 Pct", None)
        volume        = float(row.get("Volume", 0))

        try:    gap_float = float(str(gap_pct_raw).replace("%","").replace("+",""))
        except: gap_float = 0.0

        move_since = ((ltp - float(signal_price)) / float(signal_price)) * 100 if signal_price and float(signal_price) > 0 else 0.0

        if signal_price and peak_ltp and float(signal_price) > 0:
            pm = ((float(peak_ltp) - float(signal_price)) / float(signal_price)) * 100
            peak_move_str, peak_color = f"{pm:+.2f}%", _move_color(pm)
        else:
            peak_move_str, peak_color = "-", "#64748b"

        sp_str  = f"₹{float(signal_price):,.2f}" if signal_price else "-"
        pl_str  = f"₹{float(peak_ltp):,.2f}"    if peak_ltp     else "-"
        yh_str  = f"₹{float(yest_high):,.2f}"   if yest_high    else "-"
        to_str  = f"₹{float(today_open):,.2f}"  if today_open   else "-"
        sl_str  = yh_str
        vol_fmt = _short_vol(volume)

        if signal_price and yest_high and float(signal_price) > 0:
            risk = float(signal_price) - float(yest_high)
            tgt_str = f"₹{float(signal_price) + risk * 2:,.2f}" if risk > 0 else "-"
        else:
            tgt_str = "-"

        vol_cls = ("vol-fire" if "Very Strong" in vol_mom or "🔥" in vol_mom else
                   "vol-strong" if "Strong" in vol_mom or "⚡" in vol_mom else
                   "vol-build"  if "Building" in vol_mom or "👀" in vol_mom else "")

        ema200_flt = "above" if (ema200_val is not None and float(today_open) > float(ema200_val)) else "below"

        # Inject chart data as window vars
        sdata = sc.get(symbol, {})
        d5  = {"candles": sdata.get("candles_5m",  []),
               "ema9"   : sdata.get("ema9_pts",    []),
               "ema200" : sdata.get("ema200_pts",  [])}
        d15 = {"candles": sdata.get("candles_15m",    []),
               "ema9"   : sdata.get("ema9_pts_15m",   []),
               "ema200" : sdata.get("ema200_pts_15m", [])}
        candle_js += f"window.lwcData5m_{symbol}=  {json.dumps(d5)};\n"
        candle_js += f"window.lwcData15m_{symbol}= {json.dumps(d15)};\n"

        rows_html += f"""
        <tr class="main-row {vol_cls}" id="orb-main-{symbol}"
            data-sym="{symbol}" data-vol="{vol_mom.lower()}"
            data-ema="{ema_status}" data-ema200="{ema200_flt}"
            onclick="toggleRow('{symbol}')">
          <td><div class="stock-cell"><div class="expand-icon">+</div>
              <span class="stock-name"><button class="copy-btn"
                onclick="event.stopPropagation();copyORB(this,'{symbol}')">{symbol}</button></span>
          </div></td>
          <td><span style="font-weight:700;color:#0f172a;">{signal_time}</span></td>
          <td>{_ema_cell(ema_status)}</td>
          <td><span class="peak-val">{yh_str}</span></td>
          <td><span class="num-primary">{to_str}</span></td>
          <td>{_chg_html(gap_float)}</td>
          <td><span class="num-primary">{vol_ratio_str}</span></td>
          <td>{_vol_badge(vol_mom)}</td>
          <td>{_ema5m_cell(ema9_val, ema9_pct)}</td>
          <td>{_ema5m_cell(ema200_val, ema200_pct)}</td>
          <td>{_signal_price_html(sp_str, move_since)}</td>
          <td><span class="sl-val">{sl_str}</span></td>
          <td><span class="tgt-val">{tgt_str}</span></td>
          <td><span class="num-primary">₹{ltp:,.2f}</span></td>
          <td><span class="peak-val">{pl_str}</span></td>
          <td><span style="font-weight:700;color:{peak_color}">{peak_move_str}</span></td>
          <td><span class="num-primary">{vol_fmt}</span></td>
        </tr>
        <tr class="expand-row" id="orb-exp-{symbol}" style="display:none">
          <td colspan="17">
            <div class="expand-panel">
              <div class="expand-card"><div class="ec-label">Yesterday High</div><div class="ec-value" style="color:#7c3aed">{yh_str}</div><div class="ec-sub">ORB breakout level</div></div>
              <div class="expand-card"><div class="ec-label">Today Open</div><div class="ec-value">{to_str}</div><div class="ec-sub">Gap: {gap_pct_raw}</div></div>
              <div class="expand-card"><div class="ec-label">Signal Price</div><div class="ec-value" style="color:#2563eb">{sp_str}</div><div class="ec-sub">Entry trigger</div></div>
              <div class="expand-card"><div class="ec-label">High Since Signal</div><div class="ec-value" style="color:#7c3aed">{pl_str}</div><div class="ec-sub">Peak after signal</div></div>
              <div class="expand-card"><div class="ec-label">Peak Move %</div><div class="ec-value" style="color:{peak_color}">{peak_move_str}</div><div class="ec-sub">Max gain possible</div></div>
              <div class="expand-card"><div class="ec-label">Stop Loss</div><div class="ec-value" style="color:#dc2626">{sl_str}</div><div class="ec-sub">= Yesterday High</div></div>
              <div class="expand-card"><div class="ec-label">Target (2R)</div><div class="ec-value" style="color:#16a34a">{tgt_str}</div><div class="ec-sub">Risk × 2 reward</div></div>
              <div class="expand-card"><div class="ec-label">Vol Ratio</div><div class="ec-value">{vol_ratio_str}</div><div class="ec-sub">vs 5-day median</div></div>
              <div class="expand-card"><div class="ec-label">Signal Time</div><div class="ec-value">{signal_time}</div><div class="ec-sub">First detected</div></div>
              <div class="expand-card"><div class="ec-label">EMA20 Status</div><div class="ec-value">{_ema_cell(ema_status)}</div><div class="ec-sub">Distance from EMA</div></div>
              <div class="expand-card"><div class="ec-label">Volume</div><div class="ec-value">{vol_fmt}</div><div class="ec-sub">Current intraday</div></div>
            </div>
            <!-- Chart -->
            <div id="lwc-wrap-{symbol}" style="padding:12px 16px 16px;background:#131722;border-radius:0 0 8px 8px;">
              <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
                <span style="font-size:12px;font-weight:700;color:#d1d4dc;">NSE:{symbol}</span>
                <div style="display:flex;gap:4px;margin-left:4px;">
                  <button onclick="switchTF('{symbol}','5m')"  id="btn-5m-{symbol}"
                    style="padding:3px 10px;border-radius:4px;border:1px solid #2962ff;background:#2962ff;color:white;font-size:11px;font-weight:700;cursor:pointer;">5m</button>
                  <button onclick="switchTF('{symbol}','15m')" id="btn-15m-{symbol}"
                    style="padding:3px 10px;border-radius:4px;border:1px solid #2a2e39;background:#1e222d;color:#d1d4dc;font-size:11px;font-weight:700;cursor:pointer;">15m</button>
                </div>
                <span style="font-size:11px;color:#758696;margin-left:8px;">
                  EMA9 <span style="color:#ff9800;font-weight:700;">━</span>
                  &nbsp;EMA200 <span style="color:#2962ff;font-weight:700;">━</span>
                </span>
              </div>
              <div id="lwc-{symbol}" style="width:100%;height:480px;border-radius:6px;overflow:hidden;border:1px solid #2a2e39;background:#131722;"></div>
            </div>
          </td>
        </tr>"""

    meta = f"📅 {prev_date} &nbsp;|&nbsp; Ticks: {tick_count} &nbsp;|&nbsp; {window_status}"
    return (_ORB_STYLES
        + f"\n<script>\n{candle_js}\n</script>\n"
        + f"""
    <div class="filterbar">
      <span class="filter-label">ORB Scanner</span>
      <span class="filter-count"><b id="orbMatchCount">{total}</b> stocks</span>
      <div class="filter-sep"></div>
      <select class="filter-select" id="orbVolFilter" onchange="applyFilter()">
        <option value="">All Volume</option>
        <option value="very strong">🔥 Very Strong</option>
        <option value="strong">⚡ Strong</option>
        <option value="building">👀 Building</option>
      </select>
      <select class="filter-select" id="orbEmaFilter" onchange="applyFilter()">
        <option value="">All EMA20</option>
        <option value="pass">✅ EMA20 Pass</option>
        <option value="fail">❌ EMA20 Fail / Below</option>
      </select>
      <select class="filter-select" id="orbEma200Filter" onchange="applyFilter()">
        <option value="">All EMA200</option>
        <option value="above">🟢 Above EMA200</option>
        <option value="below">❌ Below EMA200</option>
      </select>
      <span class="meta-info">{meta}</span>
    </div>
    <div class="table-wrap"><table>
      <thead><tr>
        <th onclick="toggleColExpand(0)">Symbol <span class="sort-arrow">↕</span></th>
        <th onclick="toggleColExpand(1)">Signal Time <span class="sort-arrow">↕</span></th>
        <th class="th-ema"  onclick="toggleColExpand(2)">EMA20 Status <span class="sort-arrow">↕</span></th>
        <th class="th-orb"  onclick="toggleColExpand(3)">Yesterday High <span class="sort-arrow">↕</span></th>
        <th class="th-orb"  onclick="toggleColExpand(4)">Today Open <span class="sort-arrow">↕</span></th>
        <th onclick="toggleColExpand(5)">Gap % <span class="sort-arrow">↕</span></th>
        <th onclick="toggleColExpand(6)">Vol Ratio <span class="sort-arrow">↕</span></th>
        <th onclick="toggleColExpand(7)">Vol Momentum <span class="sort-arrow">↕</span></th>
        <th class="th-ema9"   onclick="toggleColExpand(8)">EMA9 (5m) <span class="sort-arrow">↕</span></th>
        <th class="th-ema200" onclick="toggleColExpand(9)">EMA200 (5m) <span class="sort-arrow">↕</span></th>
        <th class="th-sig"  onclick="toggleColExpand(10)">Signal Price <span class="sort-arrow">↕</span></th>
        <th class="th-risk" onclick="toggleColExpand(11)">SL <span class="sort-arrow">↕</span></th>
        <th class="th-tgt"  onclick="toggleColExpand(12)">Target <span class="sort-arrow">↕</span></th>
        <th onclick="toggleColExpand(13)">LTP <span class="sort-arrow">↕</span></th>
        <th class="th-sig" onclick="toggleColExpand(14)">High Since Signal <span class="sort-arrow">↕</span></th>
        <th class="th-sig" onclick="toggleColExpand(15)">Peak Move % <span class="sort-arrow">↕</span></th>
        <th onclick="toggleColExpand(16)">Volume <span class="sort-arrow">↕</span></th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table></div>""")


# ─────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────

# ── Historical data — once ────────────────────────────────────
if "orb_historical" not in st.session_state:
    with st.spinner("Loading historical data..."):
        hist = fetch_orb_historical_data()
        if hist:
            st.session_state["orb_historical"] = hist
        else:
            st.error("❌ No data found in websocket_stock_values")
            st.stop()

historical = st.session_state["orb_historical"]

# ── Tracked stocks — once per day ─────────────────────────────
today_str = datetime.now(IST).strftime("%Y-%m-%d")
if "orb_tracked" not in st.session_state or st.session_state.get("orb_tracked_date") != today_str:
    loaded = fetch_orb_signals_from_supabase(today_str)
    st.session_state["orb_tracked"]      = loaded
    st.session_state["orb_tracked_date"] = today_str

# ── Stock data cache (EMA + candles) — once, outside fragment ─
if st.session_state["orb_tracked"]:
    _today_opens = {s: float(d.get("today_open", 0)) for s, d in st.session_state["orb_tracked"].items()}
    get_stock_data_cache(list(st.session_state["orb_tracked"].keys()), _today_opens)

# ── Top bar ───────────────────────────────────────────────────
col1, col2 = st.columns([5, 1])
with col1:
    ws_status = "🟢 Live" if angel_ws.is_connected() else "🔴 Disconnected"
    now_ist   = datetime.now(IST)
    orb_end   = now_ist.replace(hour=ORB_END_H,   minute=ORB_END_M,   second=0, microsecond=0)
    orb_start = now_ist.replace(hour=ORB_START_H, minute=ORB_START_M, second=0, microsecond=0)
    if now_ist < orb_start:
        window_status = "⏳ Waiting for market open (9:15)"
    elif now_ist <= orb_end:
        window_status = f"🟢 ORB Window Active — {int((orb_end - now_ist).total_seconds() / 60)} min left"
    else:
        window_status = "🔒 ORB Window Closed (9:30 passed)"
    st.markdown(f"📈 **ORB Scanner** &nbsp;|&nbsp; 📅 {historical['prev_date']} &nbsp;|&nbsp; WS: {ws_status} &nbsp;|&nbsp; {window_status}", unsafe_allow_html=True)
with col2:
    if st.button("🔄 Reload", use_container_width=True):
        for k in ["orb_historical","orb_tracked","orb_tracked_date",
                  "orb_stock_cache","orb_ema200_updated","orb_ema_pending"]:
            st.session_state.pop(k, None)
        st.rerun()

st.divider()

# ─────────────────────────────────────────────────────────────
# FRAGMENT — only live tick logic, no yfinance
# ─────────────────────────────────────────────────────────────
@st.fragment(run_every=5)
def orb_scanner_table():
    now_ist   = datetime.now(IST)
    orb_start = now_ist.replace(hour=ORB_START_H, minute=ORB_START_M, second=0, microsecond=0)
    orb_end   = now_ist.replace(hour=ORB_END_H,   minute=ORB_END_M,   second=0, microsecond=0)
    in_window = orb_start <= now_ist <= orb_end
    now_str   = now_ist.strftime("%H:%M:%S")

    live_ticks  = angel_ws.latest_ticks
    df_prev     = st.session_state["orb_historical"]["df_prev"]
    df_median   = st.session_state["orb_historical"]["df_median"]
    orb_tracked = st.session_state["orb_tracked"]
    stock_cache = st.session_state.get("orb_stock_cache", {})

    st.caption(f"Last updated: {now_str} | Ticks: {len(live_ticks)} | Tracked: {len(orb_tracked)} stocks")

    # ── Scan for new stocks ───────────────────────────────────
    if live_ticks:
        new_found = False
        for token, tick in live_ticks.items():
            symbol = TOKEN_TO_NAME.get(token)
            if not symbol or symbol in orb_tracked: continue

            live_ltp    = float(tick.get("ltp",    0))
            today_open  = float(tick.get("open",   0))
            live_volume = float(tick.get("volume", 0))
            if live_ltp <= 0 or today_open <= 0: continue

            prev_row = df_prev[df_prev["stock"] == symbol]
            if prev_row.empty: continue
            yest_high  = float(prev_row["yesterday_high"].values[0])
            yest_close = float(prev_row["yesterday_close"].values[0])
            if yest_high <= 0 or yest_close <= 0: continue

            gap_pct = ((today_open - yest_close) / yest_close) * 100
            if abs(gap_pct) >= MAX_GAP_PCT: continue
            if not (today_open > yest_high or live_ltp > yest_high): continue

            med_row    = df_median[df_median["stock"] == symbol]
            median_vol = float(med_row["median_vol"].values[0]) if not med_row.empty else 0
            if median_vol <= 0: continue
            vol_ratio_val = live_volume / median_vol
            if vol_ratio_val < 1.0: continue

            # EMA20 check from cache
            sdata      = stock_cache.get(symbol, {})
            ema_status = sdata.get("ema20_status", "")
            if not ema_status.startswith("✅"): continue

            ema200_v   = sdata.get("ema200")
            ema200_p   = sdata.get("ema200_pct")
            save_orb_signal_to_supabase(
                stock=symbol, today_str=today_str, signal_time=now_str,
                yesterday_high=yest_high, today_open=today_open, gap_pct=gap_pct,
                signal_price=live_ltp, ema20_status=ema_status,
                vol_ratio=vol_ratio_val, ema200_5m=ema200_v, ema200_pct=ema200_p,
            )
            orb_tracked[symbol] = {
                "signal_time": now_str, "signal_price": live_ltp, "peak_ltp": live_ltp,
                "yesterday_high": yest_high, "yesterday_close": yest_close,
                "today_open": today_open, "gap_pct": round(gap_pct, 2), "median_vol": median_vol,
            }
            new_found = True

        if new_found:
            st.session_state["orb_tracked"] = orb_tracked
            # Fetch data for newly added stocks
            _opens = {s: float(d.get("today_open", 0)) for s, d in orb_tracked.items()}
            get_stock_data_cache(list(orb_tracked.keys()), _opens)
            stock_cache = st.session_state.get("orb_stock_cache", {})

    if not orb_tracked:
        st.info("⏳ Scanning... No breakout stocks found yet." if in_window else "No stocks tracked today.")
        return

    # ── Update peak_ltp ───────────────────────────────────────
    if live_ticks:
        for token, tick in live_ticks.items():
            symbol = TOKEN_TO_NAME.get(token)
            if symbol not in orb_tracked: continue
            ltp = float(tick.get("ltp", 0))
            if ltp > orb_tracked[symbol].get("peak_ltp", 0):
                update_orb_peak_ltp(symbol, today_str, ltp)
                orb_tracked[symbol]["peak_ltp"] = ltp
        st.session_state["orb_tracked"] = orb_tracked

    # ── Update Supabase EMA200 — once per stock ───────────────
    if "orb_ema200_updated" not in st.session_state:
        st.session_state["orb_ema200_updated"] = set()
    for symbol in orb_tracked:
        if symbol in st.session_state["orb_ema200_updated"]: continue
        sdata = stock_cache.get(symbol, {})
        ev, ep = sdata.get("ema200"), sdata.get("ema200_pct")
        if ev is not None and ep is not None:
            update_orb_ema200(symbol, today_str, ev, ep)
            st.session_state["orb_ema200_updated"].add(symbol)

    # ── Build display DataFrame ───────────────────────────────
    rows = []
    for symbol, data in orb_tracked.items():
        token      = NAME_TO_TOKEN.get(symbol)
        live_ltp   = float(live_ticks.get(token, {}).get("ltp",    data["signal_price"])) if token else data["signal_price"]
        live_vol   = float(live_ticks.get(token, {}).get("volume", 0)) if token else 0
        median_vol = data.get("median_vol", 0)
        if median_vol == 0:
            med_row    = df_median[df_median["stock"] == symbol]
            median_vol = float(med_row["median_vol"].values[0]) if not med_row.empty else 0
        vr = round(live_vol / median_vol, 2) if median_vol > 0 else 0

        sdata = stock_cache.get(symbol, {})
        rows.append({
            "Symbol"           : symbol,
            "Signal Time"      : data["signal_time"],
            "Yesterday High"   : data["yesterday_high"],
            "Today Open"       : data["today_open"],
            "Gap %"            : f"{data['gap_pct']:+.2f}%",
            "Vol Ratio"        : f"{vr:.2f}x",
            "Vol Momentum"     : get_vol_momentum(vr),
            "Signal Price"     : data["signal_price"],
            "LTP"              : live_ltp,
            "High Since Signal": data["peak_ltp"],
            "Volume"           : live_vol,
            "EMA20 Status"     : sdata.get("ema20_status", "⏳"),
            "EMA9"             : sdata.get("ema9"),
            "EMA9 Pct"         : sdata.get("ema9_pct"),
            "EMA200"           : sdata.get("ema200"),
            "EMA200 Pct"       : sdata.get("ema200_pct"),
        })

    df_display = pd.DataFrame(rows)
    df_display["vr_num"] = df_display["Vol Ratio"].apply(lambda x: float(str(x).replace("x","")) if x else 0)
    df_display = df_display.sort_values("vr_num", ascending=False).drop(columns=["vr_num"]).reset_index(drop=True)

    now2 = datetime.now(IST)
    if now2 < now2.replace(hour=ORB_START_H, minute=ORB_START_M, second=0, microsecond=0):
        win_label = "⏳ Pre-market"
    elif now2 <= now2.replace(hour=ORB_END_H, minute=ORB_END_M, second=0, microsecond=0):
        win_label = "🟢 ORB Active"
    else:
        win_label = "🔒 ORB Closed"

    html = render_orb_table(
        df            = df_display,
        window_status = win_label,
        prev_date     = historical["prev_date"],
        tick_count    = len(live_ticks),
        stock_cache   = stock_cache,
    )
    st.components.v1.html(html, height=min(900, 160 + len(df_display) * 50), scrolling=True)


orb_scanner_table()
