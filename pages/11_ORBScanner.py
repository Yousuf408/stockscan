"""
11_ORBScanner.py
ORB (Opening Range Breakout) Scanner
- Tracks stocks breaking above yesterday's high in first 15 mins (9:15–9:30 IST)
- Conditions: gap < 1%, yesterday close > EMA20, open/LTP > yesterday high
- After 9:30: stops adding new stocks, keeps showing with live updates
"""

import sys
import os
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
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="ORB Scanner", page_icon="📈", layout="wide")

# ─────────────────────────────────────────────────────────────
# STYLES & SIDEBAR
# ─────────────────────────────────────────────────────────────
from styles import apply_styles, sidebar_brand, page_header
apply_styles()
sidebar_brand("ORBScanner")

# ── Auto-connect WebSocket — standalone, no Momentum dependency
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
st.markdown("<style>header {visibility: hidden;}</style>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
SUPABASE_URL       = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY       = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"
IST                = timezone(timedelta(hours=5, minutes=30))
EMA_DISTANCE_LIMIT = 8.0
MAX_GAP_PCT        = 1.0   # ignore stocks with gap > 1%

TOKEN_TO_NAME = {token: name for name, token, kind in STOCKS_WATCHLIST}
NAME_TO_TOKEN = {name: token for name, token, kind in STOCKS_WATCHLIST}

# ORB window: 9:15 to 9:30 IST
ORB_START_H, ORB_START_M = 9, 15
ORB_END_H,   ORB_END_M   = 9, 30

# ─────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# ─────────────────────────────────────────────────────────────
# FETCH HISTORICAL DATA — YESTERDAY HIGH, CLOSE, MEDIAN VOL
# ─────────────────────────────────────────────────────────────
def fetch_orb_historical_data():
    supabase = get_supabase()

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
    prev_date    = sorted_dates[1] if len(sorted_dates) > 1 else sorted_dates[0]
    last_5_dates = sorted_dates[1:6]

    prev_rows = []
    offset = 0
    while True:
        resp = supabase.table("websocket_stock_values") \
            .select("stock, high, ltp") \
            .eq("date", prev_date) \
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
        df_prev["high"] = pd.to_numeric(df_prev["high"], errors="coerce")
        df_prev["ltp"]  = pd.to_numeric(df_prev["ltp"],  errors="coerce")
        df_prev = df_prev.rename(columns={
            "high" : "yesterday_high",
            "ltp"  : "yesterday_close",
        })

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

    df_median = pd.DataFrame()
    if vol_rows:
        df_vol = pd.DataFrame(vol_rows)
        df_vol["volume"] = pd.to_numeric(df_vol["volume"], errors="coerce")
        df_median = df_vol.groupby("stock")["volume"].median().reset_index()
        df_median = df_median.rename(columns={"volume": "median_vol"})

    return {
        "prev_date" : prev_date,
        "df_prev"   : df_prev,
        "df_median" : df_median,
    }

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


def get_ema20_cache(stock_names: list) -> dict:
    if "orb_ema20_cache" not in st.session_state:
        st.session_state["orb_ema20_cache"] = {}

    cache      = st.session_state["orb_ema20_cache"]
    new_stocks = [s for s in stock_names if s not in cache]

    if new_stocks:
        fetched = fetch_ema20_for_stocks(new_stocks)
        cache.update(fetched)
        st.session_state["orb_ema20_cache"] = cache

    return cache

# ─────────────────────────────────────────────────────────────
# EMA9 + EMA200 ON 5-MIN — HYBRID (yfinance + WebSocket open)
# ─────────────────────────────────────────────────────────────
def fetch_ema5m_for_stocks(stock_names: list, today_opens: dict) -> dict:
    result = {}
    if not stock_names:
        return result

    tickers = [f"{s}.NS" for s in stock_names]
    try:
        raw = yf.download(
            tickers,
            period="5d",
            interval="5m",
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
        ticker     = f"{stock}.NS"
        today_open = today_opens.get(stock, 0)

        if ticker not in close_data or today_open <= 0:
            result[stock] = None
            continue

        series = close_data[ticker].dropna()
        if len(series) < 9:
            result[stock] = None
            continue

        series_with_open = pd.concat([
            series,
            pd.Series([today_open])
        ], ignore_index=True)

        ema9_series = series_with_open.ewm(span=9, adjust=False).mean()
        ema9_val    = round(float(ema9_series.iloc[-1]), 2)
        ema9_pct    = round(((today_open - ema9_val) / ema9_val) * 100, 2)

        if len(series_with_open) >= 200:
            ema200_series = series_with_open.ewm(span=200, adjust=False).mean()
            ema200_val    = round(float(ema200_series.iloc[-1]), 2)
            ema200_pct    = round(((today_open - ema200_val) / ema200_val) * 100, 2)
        else:
            ema200_val = None
            ema200_pct = None

        result[stock] = {
            "ema9"      : ema9_val,
            "ema9_pct"  : ema9_pct,
            "ema200"    : ema200_val,
            "ema200_pct": ema200_pct,
        }

    return result


def get_ema5m_cache(stock_names: list, today_opens: dict) -> dict:
    if "orb_ema5m_cache" not in st.session_state:
        st.session_state["orb_ema5m_cache"] = {}

    cache      = st.session_state["orb_ema5m_cache"]
    new_stocks = [s for s in stock_names if s not in cache]

    if new_stocks:
        fetched = fetch_ema5m_for_stocks(new_stocks, today_opens)
        cache.update(fetched)
        st.session_state["orb_ema5m_cache"] = cache

    return cache


# ─────────────────────────────────────────────────────────────
# ORB SUPABASE — SAVE & FETCH
# ─────────────────────────────────────────────────────────────
def fetch_orb_signals_from_supabase(today_str: str) -> dict:
    try:
        supabase = get_supabase()
        resp = supabase.table("orb") \
            .select("stock, signal_time, yesterday_high, today_open, gap_pct, signal_price, peak_ltp, ema20_status") \
            .eq("signal_date", today_str) \
            .execute()
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


def save_orb_signal_to_supabase(stock: str, today_str: str, signal_time: str,
                                  yesterday_high: float, today_open: float,
                                  gap_pct: float, signal_price: float,
                                  ema20_status: str, vol_ratio: float = 0,
                                  ema200_5m: float = None, ema200_pct: float = None):
    try:
        supabase = get_supabase()
        row = {
            "stock"         : stock,
            "signal_date"   : today_str,
            "signal_time"   : signal_time,
            "yesterday_high": round(float(yesterday_high), 2),
            "today_open"    : round(float(today_open), 2),
            "gap_pct"       : round(float(gap_pct), 2),
            "signal_price"  : round(float(signal_price), 2),
            "peak_ltp"      : round(float(signal_price), 2),
            "ema20_status"  : ema20_status,
            "vol_ratio"     : round(float(vol_ratio), 2),
        }
        if ema200_5m  is not None: row["ema200_5m"]  = round(float(ema200_5m), 2)
        if ema200_pct is not None: row["ema200_pct"] = round(float(ema200_pct), 2)
        supabase.table("orb").upsert(row, on_conflict="stock,signal_date", ignore_duplicates=True).execute()
    except Exception:
        pass


def update_orb_peak_ltp(stock: str, today_str: str, new_peak: float):
    try:
        supabase = get_supabase()
        supabase.table("orb") \
            .update({"peak_ltp": round(float(new_peak), 2)}) \
            .eq("stock", stock) \
            .eq("signal_date", today_str) \
            .execute()
    except Exception:
        pass


def update_orb_ema200(stock: str, today_str: str, ema200_5m: float, ema200_pct: float):
    try:
        supabase = get_supabase()
        supabase.table("orb") \
            .update({
                "ema200_5m" : round(float(ema200_5m),  2),
                "ema200_pct": round(float(ema200_pct), 2),
            }) \
            .eq("stock", stock) \
            .eq("signal_date", today_str) \
            .execute()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# VOL MOMENTUM HELPER
# ─────────────────────────────────────────────────────────────
def get_vol_momentum(ratio: float) -> str:
    if ratio >= 3.0: return "🔥 Very Strong"
    if ratio >= 2.0: return "⚡ Strong"
    if ratio >= 1.5: return "👀 Building"
    if ratio >= 1.0: return "😐 Weak"
    return ""


# ─────────────────────────────────────────────────────────────
# HTML TABLE HELPERS
# ─────────────────────────────────────────────────────────────
def _short_vol(vol: float) -> str:
    if vol >= 1_000_000:
        return f"{vol/1_000_000:.2f}M"
    if vol >= 1_000:
        return f"{vol/1_000:.1f}K"
    return str(int(vol))


def _ema_cell(status) -> str:
    if not status or status == "⏳":
        return '<span style="color:#94a3b8">⏳</span>'
    s = str(status)
    if s.startswith("✅"):
        return f'<span class="ema-pass">{s}</span>'
    if "Below" in s:
        return f'<span class="ema-fail">{s}</span>'
    if s.startswith("❌"):
        return f'<span class="ema-ext">{s}</span>'
    return f'<span style="color:#94a3b8">{s}</span>'


def _ema5m_cell(val, pct) -> str:
    if val is None or pct is None:
        return '<span style="color:#94a3b8">⏳</span>'
    positive = pct >= 0
    color    = "#16a34a" if positive else "#dc2626"
    icon     = "🟢" if positive else "❌"
    sign     = "+" if positive else ""
    val_html = f'<div class="num-primary">₹{float(val):,.2f}</div>'
    pct_html = f'<div style="color:{color};font-weight:700;font-size:13px;">{icon} {sign}{pct:.1f}%</div>'
    return f'{val_html}{pct_html}'


def _vol_badge(vm: str) -> str:
    if "Very Strong" in vm or "🔥" in vm:
        return '<span class="vol-badge vol-high">🔥 Very Strong</span>'
    if "Strong" in vm or "⚡" in vm:
        return '<span class="vol-badge vol-med">⚡ Strong</span>'
    if "Building" in vm or "👀" in vm:
        return '<span class="vol-badge vol-low">👀 Building</span>'
    return f'<span class="vol-badge vol-low">{vm}</span>'


def _move_color(val: float) -> str:
    if val >= 5.0: return "#16a34a"
    if val >= 2.0: return "#ca8a04"
    if val >= 0:   return "#64748b"
    return "#dc2626"


def _signal_price_html(signal_price_str: str, move_since: float) -> str:
    positive = move_since >= 0
    w        = min(abs(move_since) * 10, 100)
    fill_cls = "fill-green" if positive else "fill-red"
    color    = _move_color(move_since)
    sign     = "+" if positive else ""
    pct_str  = f"{sign}{move_since:.2f}%"
    return (
        f'<div class="sig-price-wrap">'
        f'  <div class="sig-top-row">'
        f'    <span class="num-primary">{signal_price_str}</span>'
        f'    <span class="bar-pct" style="color:{color}">{pct_str}</span>'
        f'  </div>'
        f'  <div class="progress-bar">'
        f'    <div class="progress-fill {fill_cls}" style="width:{w:.0f}%"></div>'
        f'  </div>'
        f'</div>'
    )


def _chg_html(val: float) -> str:
    cls  = "chg-pos" if val >= 0 else "chg-neg"
    sign = "▲" if val >= 0 else "▼"
    return f'<span class="{cls}">{sign} {abs(val):.2f}%</span>'


# ── CHANGE 2: LTP cell with % change vs prev close ────────────
def _ltp_cell(ltp: float, prev_close: float) -> str:
    ltp_str = f"₹{ltp:,.2f}"
    if prev_close and prev_close > 0:
        chg = ((ltp - prev_close) / prev_close) * 100
        return f'<div class="ltp-val">{ltp_str}</div>{_chg_html(chg)}'
    return f'<div class="ltp-val">{ltp_str}</div>'


# ─────────────────────────────────────────────────────────────
# CSS + JS
# ─────────────────────────────────────────────────────────────
_ORB_STYLES = """
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  margin: 0 !important; padding: 0 !important;
  background: #f5f7fa !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
  color: #1a202c; font-size: 13px;
}

/* ── FILTER BAR ── */
.filterbar {
  background: #fff; border-bottom: 1px solid #e2e8f0;
  padding: 8px 16px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.filter-label { font-size: 12px; font-weight: 700; color: #374151; }
.filter-count {
  background: #f1f5f9; border: 1px solid #e2e8f0;
  padding: 3px 8px; border-radius: 4px; font-size: 12px; color: #64748b;
}
.filter-count b { color: #1a202c; }
.filter-sep { width: 1px; height: 20px; background: #e2e8f0; }
.meta-info { margin-left: auto; font-size: 13px; font-weight: 600; color: #0f172a; }

/* ── CHANGE 3: Custom dropdown (replaces native select) ── */
.cdd-wrap { position: relative; display: inline-block; }
.cdd-btn  {
  display: flex; align-items: center; gap: 6px; padding: 6px 12px;
  border-radius: 6px; border: 1px solid #e2e8f0; background: #fff;
  color: #374151; font-size: 13px; font-weight: 600; cursor: pointer;
  white-space: nowrap; min-width: 130px; justify-content: space-between;
}
.cdd-btn:hover  { background: #f8fafc; border-color: #cbd5e1; }
.cdd-btn.active { border-color: #3b82f6; background: #eff6ff; color: #1d4ed8; }
.cdd-arrow { font-size: 10px; color: #94a3b8; transition: transform 0.15s; }
.cdd-btn.open .cdd-arrow { transform: rotate(180deg); }
.cdd-menu {
  display: none; position: absolute; top: calc(100% + 4px); left: 0;
  background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12); z-index: 9999;
  min-width: 170px; padding: 4px 0;
}
.cdd-menu.open { display: block; }
.cdd-item { padding: 8px 14px; font-size: 13px; color: #374151; cursor: pointer; white-space: nowrap; }
.cdd-item:hover    { background: #f0f9ff; color: #0369a1; }
.cdd-item.selected { background: #eff6ff; color: #1d4ed8; font-weight: 700; }

/* ── TABLE WRAP ── */
.table-wrap { padding: 12px 16px; overflow-x: auto; }
table {
  width: 100%; border-collapse: collapse; background: #fff;
  border-radius: 10px; border: 1px solid #e2e8f0; overflow: hidden;
}

/* ── HEADER ── */
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
th.active-col .sort-arrow { opacity: 1; }
th.th-ema    { background: #f0fdf4; color: #166534; }
th.th-orb    { background: #fef3c7; color: #92400e; }
th.th-ema9   { background: #e0f2fe; color: #0369a1; }
th.th-ema200 { background: #fef9c3; color: #854d0e; }
th.th-sig    { background: #ede9fe; color: #5b21b6; }
th.th-risk   { background: #fee2e2; color: #991b1b; }
th.th-tgt    { background: #dcfce7; color: #166534; }

/* ── ROWS ── */
tbody tr.main-row {
  border-bottom: 1px solid #e2e8f0;
  cursor: pointer; transition: background 0.1s;
  border-left: 4px solid #e2e8f0;
}
tbody tr.main-row:hover { background: #f0f9ff; }
tbody tr.main-row.expanded { background: #f0f9ff; border-bottom: none; }
tbody tr.main-row:nth-child(even) { background: #f8fafc; }
tbody tr.main-row:nth-child(even):hover { background: #f0f9ff; }

/* left border by vol momentum */
tbody tr.main-row.vol-fire   { border-left: 4px solid #f59e0b; }
tbody tr.main-row.vol-strong { border-left: 4px solid #3b82f6; }
tbody tr.main-row.vol-build  { border-left: 4px solid #22c55e; }

td {
  padding: 9px 10px; vertical-align: middle; white-space: nowrap;
  border-right: 1px solid #e2e8f0; font-size: 13px; color: #374151;
  border-bottom: 1px solid #e2e8f0;
}
td:last-child { border-right: none; }
td.active-col { background: #eff6ff; }

/* ── EXPAND ROW ── */
tr.expand-row td { padding: 0; border-bottom: 2px solid #3b82f6; }
.expand-panel {
  background: #f0f9ff; padding: 12px 16px;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px;
}
.expand-card {
  background: #fff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 8px 10px;
}
.expand-card .ec-label {
  font-size: 10px; color: #64748b; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.5px;
}
.expand-card .ec-value { font-size: 14px; font-weight: 700; color: #1e3a5f; margin-top: 2px; }
.expand-card .ec-sub   { font-size: 10px; color: #94a3b8; margin-top: 1px; }

/* ── STOCK CELL ── */
.stock-cell { display: flex; align-items: center; gap: 8px; }
.expand-icon {
  width: 18px; height: 18px; border-radius: 4px;
  background: #e2e8f0; color: #64748b;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; flex-shrink: 0; transition: all 0.15s;
}
tr.expanded .expand-icon { background: #3b82f6; color: #fff; }
.stock-name { font-weight: 700; font-size: 13px; color: #1e3a5f; }

/* ── BADGES ── */
.vol-badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 700; }
.vol-high  { background: #fef3c7; color: #92400e; }
.vol-med   { background: #e0f2fe; color: #075985; }
.vol-low   { background: #f1f5f9; color: #64748b; }

/* ── NUMBERS ── */
.num-primary { font-size: 13px; font-weight: 700; color: #0f172a; }
.ltp-val     { font-size: 13px; font-weight: 700; color: #0f172a; }
.peak-val    { color: #7c3aed; font-weight: 700; font-size: 13px; }
.chg-pos     { color: #16a34a; font-weight: 600; font-size: 13px; }
.chg-neg     { color: #dc2626; font-weight: 600; font-size: 13px; }
.ema-pass    { color: #16a34a; font-weight: 600; font-size: 13px; }
.ema-fail    { color: #dc2626; font-weight: 600; font-size: 13px; }
.ema-ext     { color: #ea580c; font-weight: 600; font-size: 13px; }

/* ── SIGNAL PRICE CELL ── */
.sig-price-wrap { display: flex; flex-direction: column; gap: 3px; min-width: 120px; }
.sig-top-row    { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.progress-bar   { width: 100%; height: 4px; background: #e2e8f0; border-radius: 3px; overflow: hidden; }
.progress-fill  { height: 100%; border-radius: 3px; transition: width 0.3s; }
.fill-green { background: #22c55e; }
.fill-red   { background: #ef4444; }
.bar-pct    { font-size: 12px; font-weight: 600; white-space: nowrap; }

/* ── COPY BUTTON ── */
.copy-btn {
  cursor: pointer; font-weight: 700; color: #1e3a5f;
  background: transparent; border: none; padding: 0;
  font-size: 13px; transition: color 0.2s;
}
.copy-btn:hover  { color: #10b981; }
.copy-btn.copied { color: #10b981; }

/* ── RISK / TARGET ── */
.sl-val  { color: #dc2626; font-weight: 700; font-size: 13px; }
.tgt-val { color: #16a34a; font-weight: 700; font-size: 13px; }

/* ── TOAST ── */
.toast {
  position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
  background: #0f172a; color: white; padding: 8px 20px;
  border-radius: 8px; font-size: 13px; z-index: 9999;
  opacity: 0; transition: opacity 0.3s; pointer-events: none;
}
.toast.show { opacity: 1; }

/* ── SCROLLBAR ── */
::-webkit-scrollbar { height: 5px; width: 5px; }
::-webkit-scrollbar-track { background: #f1f5f9; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
</style>

<div id="orb-toast" class="toast">✅ Copied!</div>

<script>
var activeCol = -1;

function copyORB(btn, symbol) {
    navigator.clipboard.writeText(symbol);
    btn.classList.add('copied');
    btn.innerText = '✓ ' + symbol;
    var t = document.getElementById('orb-toast');
    t.classList.add('show');
    setTimeout(function() {
        btn.classList.remove('copied');
        btn.innerText = symbol;
        t.classList.remove('show');
    }, 1500);
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
}

function toggleColExpand(col) {
    document.querySelectorAll('th').forEach(function(th) { th.classList.remove('active-col'); });
    document.querySelectorAll('td').forEach(function(td) { td.classList.remove('active-col'); });
    if (activeCol === col) { activeCol = -1; return; }
    activeCol = col;
    document.querySelectorAll('th')[col].classList.add('active-col');
    document.querySelectorAll('tbody tr.main-row').forEach(function(row) {
        var cells = row.querySelectorAll('td');
        if (cells[col]) cells[col].classList.add('active-col');
    });
}

/* ── CHANGE 3: Custom dropdown JS ── */
function toggleCDD(id) {
    var menu = document.getElementById('cdd-' + id + '-menu');
    var btn  = document.getElementById('cdd-' + id + '-btn');
    ['vol','ema','ema200'].forEach(function(k) {
        if (k !== id) {
            var m = document.getElementById('cdd-' + k + '-menu');
            var b = document.getElementById('cdd-' + k + '-btn');
            if (m) m.classList.remove('open');
            if (b) b.classList.remove('open');
        }
    });
    if (menu) menu.classList.toggle('open');
    if (btn)  btn.classList.toggle('open');
}

function setCDD(id, value, label) {
    var inputId = id === 'vol' ? 'orbVolFilter' : id === 'ema' ? 'orbEmaFilter' : 'orbEma200Filter';
    var input   = document.getElementById(inputId);
    if (input) input.value = value;
    var btn = document.getElementById('cdd-' + id + '-btn');
    if (btn) {
        btn.innerHTML = label + ' <span class="cdd-arrow">▾</span>';
        if (value !== '') btn.classList.add('active'); else btn.classList.remove('active');
        btn.classList.remove('open');
    }
    var menu = document.getElementById('cdd-' + id + '-menu');
    if (menu) {
        menu.querySelectorAll('.cdd-item').forEach(function(item) {
            item.classList.toggle('selected', item.textContent.trim() === label.trim());
        });
        menu.classList.remove('open');
    }
    applyFilter();
    try {
        sessionStorage.setItem('orb_cdd_' + id + '_val',   value);
        sessionStorage.setItem('orb_cdd_' + id + '_label', label);
    } catch(e) {}
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('.cdd-wrap')) {
        ['vol','ema','ema200'].forEach(function(k) {
            var m = document.getElementById('cdd-' + k + '-menu');
            var b = document.getElementById('cdd-' + k + '-btn');
            if (m) m.classList.remove('open');
            if (b) b.classList.remove('open');
        });
    }
});

function applyFilter() {
    var volVal    = document.getElementById('orbVolFilter').value.toLowerCase();
    var emaVal    = document.getElementById('orbEmaFilter').value;
    var ema200Val = document.getElementById('orbEma200Filter').value;
    var rows      = document.querySelectorAll('tbody tr.main-row');
    var count     = 0;
    rows.forEach(function(row) {
        var vol    = (row.dataset.vol    || '').toLowerCase();
        var ema    = (row.dataset.ema    || '');
        var ema200 = (row.dataset.ema200 || '');
        var show   = true;
        if (volVal && !vol.includes(volVal))                show = false;
        if (emaVal === 'pass' && !ema.includes('✅'))        show = false;
        if (emaVal === 'fail' && !ema.includes('❌'))        show = false;
        if (ema200Val === 'above' && ema200 !== 'above')     show = false;
        if (ema200Val === 'below' && ema200 !== 'below')     show = false;
        row.style.display = show ? '' : 'none';
        var expRow = document.getElementById('orb-exp-' + row.dataset.sym);
        if (expRow) expRow.style.display = 'none';
        if (show) count++;
    });
    document.getElementById('orbMatchCount').textContent = count;
}

/* Restore filter state after every 5s re-render */
(function restoreFilters() {
    try {
        [['vol','orbVolFilter'],['ema','orbEmaFilter'],['ema200','orbEma200Filter']].forEach(function(pair) {
            var id    = pair[0];
            var val   = sessionStorage.getItem('orb_cdd_' + id + '_val');
            var label = sessionStorage.getItem('orb_cdd_' + id + '_label');
            if (val !== null && label !== null && val !== '') setCDD(id, val, label);
        });
    } catch(e) {}
})();
</script>
"""


# ─────────────────────────────────────────────────────────────
# RENDER TABLE
# ─────────────────────────────────────────────────────────────
def render_orb_table(df: pd.DataFrame, window_status: str = "", prev_date: str = "", tick_count: int = 0) -> str:
    rows_html = ""
    total     = len(df)

    for _, row in df.iterrows():
        symbol        = str(row["Symbol"])
        signal_time   = str(row.get("Signal Time", "-"))
        ema_status    = row.get("EMA20 Status", "")
        yest_high     = row.get("Yesterday High", 0)
        today_open    = row.get("Today Open", 0)
        prev_close    = row.get("Prev Close", 0)
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

        if signal_price and float(signal_price) > 0:
            move_since = ((ltp - float(signal_price)) / float(signal_price)) * 100
        else:
            move_since = 0.0

        if signal_price and peak_ltp and float(signal_price) > 0:
            peak_move     = ((float(peak_ltp) - float(signal_price)) / float(signal_price)) * 100
            peak_move_str = f"{peak_move:+.2f}%"
            peak_color    = _move_color(peak_move)
        else:
            peak_move_str = "-"
            peak_color    = "#64748b"

        sp_str  = f"₹{float(signal_price):,.2f}" if signal_price else "-"
        pl_str  = f"₹{float(peak_ltp):,.2f}"    if peak_ltp     else "-"
        yh_str  = f"₹{float(yest_high):,.2f}"   if yest_high    else "-"
        to_str  = f"₹{float(today_open):,.2f}"  if today_open   else "-"
        sl_str  = yh_str
        vol_fmt = _short_vol(volume)

        if signal_price and yest_high and float(signal_price) > 0:
            risk = float(signal_price) - float(yest_high)
            if risk > 0:
                target_val = float(signal_price) + (risk * 2)
                target_str = f"₹{target_val:,.2f}"
            else:
                target_str = "-"
        else:
            target_str = "-"

        vol_cls = ("vol-fire"   if "Very Strong" in vol_mom or "🔥" in vol_mom else
                   "vol-strong" if "Strong"      in vol_mom or "⚡" in vol_mom else
                   "vol-build"  if "Building"    in vol_mom or "👀" in vol_mom else "")

        ema200_filter_val = "above" if (ema200_val is not None and float(today_open) > float(ema200_val)) else "below"

        # CHANGE 1: New column order
        # Symbol | Signal Time | EMA20 | Yesterday High | Today Open | Gap% |
        # LTP (with %chg) | Vol Ratio | Vol Momentum |
        # EMA9(5m) | EMA200(5m) | Signal Price | SL | Target |
        # High Since Signal | Peak Move% | Volume
        rows_html += f"""
        <tr class="main-row {vol_cls}" id="orb-main-{symbol}"
            data-sym="{symbol}"
            data-vol="{vol_mom.lower()}"
            data-ema="{ema_status}"
            data-ema200="{ema200_filter_val}"
            onclick="toggleRow('{symbol}')">
            <td>
                <div class="stock-cell">
                    <div class="expand-icon">+</div>
                    <span class="stock-name">
                        <button class="copy-btn"
                            onclick="event.stopPropagation();copyORB(this,'{symbol}')">{symbol}</button>
                    </span>
                </div>
            </td>
            <td><span style="font-weight:700;color:#0f172a;">{signal_time}</span></td>
            <td><span class="peak-val">{yh_str}</span></td>
            <td><span class="num-primary">{to_str}</span></td>
            <td>{_chg_html(gap_float)}</td>
            <td>{_ltp_cell(ltp, float(prev_close) if prev_close else 0)}</td>
            <td><span class="num-primary">{vol_ratio_str}</span></td>
            <td>{_vol_badge(vol_mom)}</td>
            <td>{_ema_cell(ema_status)}</td>
            <td>{_ema5m_cell(ema9_val, ema9_pct)}</td>
            <td>{_ema5m_cell(ema200_val, ema200_pct)}</td>
            <td>{_signal_price_html(sp_str, move_since)}</td>
            <td><span class="sl-val">{sl_str}</span></td>
            <td><span class="tgt-val">{target_str}</span></td>
            <td><span class="peak-val">{pl_str}</span></td>
            <td><span style="font-weight:700;color:{peak_color}">{peak_move_str}</span></td>
            <td><span class="num-primary">{vol_fmt}</span></td>
        </tr>
        <tr class="expand-row" id="orb-exp-{symbol}" style="display:none">
            <td colspan="17">
                <div class="expand-panel">
                    <div class="expand-card">
                        <div class="ec-label">Yesterday High</div>
                        <div class="ec-value" style="color:#7c3aed">{yh_str}</div>
                        <div class="ec-sub">ORB breakout level</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">Today Open</div>
                        <div class="ec-value">{to_str}</div>
                        <div class="ec-sub">Gap: {gap_pct_raw}</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">Signal Price</div>
                        <div class="ec-value" style="color:#2563eb">{sp_str}</div>
                        <div class="ec-sub">Entry trigger</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">High Since Signal</div>
                        <div class="ec-value" style="color:#7c3aed">{pl_str}</div>
                        <div class="ec-sub">Peak after signal</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">Peak Move %</div>
                        <div class="ec-value" style="color:{peak_color}">{peak_move_str}</div>
                        <div class="ec-sub">Max gain possible</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">Stop Loss</div>
                        <div class="ec-value" style="color:#dc2626">{sl_str}</div>
                        <div class="ec-sub">= Yesterday High</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">Target (2R)</div>
                        <div class="ec-value" style="color:#16a34a">{target_str}</div>
                        <div class="ec-sub">Risk × 2 reward</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">Vol Ratio</div>
                        <div class="ec-value">{vol_ratio_str}</div>
                        <div class="ec-sub">vs 5-day median</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">Signal Time</div>
                        <div class="ec-value">{signal_time}</div>
                        <div class="ec-sub">First detected</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">EMA20 Status</div>
                        <div class="ec-value">{_ema_cell(ema_status)}</div>
                        <div class="ec-sub">Distance from EMA</div>
                    </div>
                    <div class="expand-card">
                        <div class="ec-label">Volume</div>
                        <div class="ec-value">{vol_fmt}</div>
                        <div class="ec-sub">Current intraday</div>
                    </div>
                </div>
            </td>
        </tr>"""

    meta = f"📅 {prev_date} &nbsp;|&nbsp; Ticks: {tick_count} &nbsp;|&nbsp; {window_status}"

    html = _ORB_STYLES + f"""
    <div class="filterbar">
        <span class="filter-label">ORB Scanner</span>
        <span class="filter-count"><b id="orbMatchCount">{total}</b> stocks</span>
        <div class="filter-sep"></div>

        <div class="cdd-wrap" id="cdd-vol">
            <button class="cdd-btn" onclick="toggleCDD('vol')" id="cdd-vol-btn">All Volume <span class="cdd-arrow">▾</span></button>
            <div class="cdd-menu" id="cdd-vol-menu">
                <div class="cdd-item" onclick="setCDD('vol','','All Volume')">All Volume</div>
                <div class="cdd-item" onclick="setCDD('vol','very strong','🔥 Very Strong')">🔥 Very Strong</div>
                <div class="cdd-item" onclick="setCDD('vol','strong','⚡ Strong')">⚡ Strong</div>
                <div class="cdd-item" onclick="setCDD('vol','building','👀 Building')">👀 Building</div>
            </div>
            <input type="hidden" id="orbVolFilter" value="">
        </div>

        <div class="cdd-wrap" id="cdd-ema">
            <button class="cdd-btn" onclick="toggleCDD('ema')" id="cdd-ema-btn">All EMA20 <span class="cdd-arrow">▾</span></button>
            <div class="cdd-menu" id="cdd-ema-menu">
                <div class="cdd-item" onclick="setCDD('ema','','All EMA20')">All EMA20</div>
                <div class="cdd-item" onclick="setCDD('ema','pass','✅ EMA20 Pass')">✅ EMA20 Pass</div>
                <div class="cdd-item" onclick="setCDD('ema','fail','❌ EMA20 Fail')">❌ EMA20 Fail</div>
            </div>
            <input type="hidden" id="orbEmaFilter" value="">
        </div>

        <div class="cdd-wrap" id="cdd-ema200">
            <button class="cdd-btn" onclick="toggleCDD('ema200')" id="cdd-ema200-btn">All EMA200 <span class="cdd-arrow">▾</span></button>
            <div class="cdd-menu" id="cdd-ema200-menu">
                <div class="cdd-item" onclick="setCDD('ema200','','All EMA200')">All EMA200</div>
                <div class="cdd-item" onclick="setCDD('ema200','above','🟢 Above EMA200')">🟢 Above EMA200</div>
                <div class="cdd-item" onclick="setCDD('ema200','below','❌ Below EMA200')">❌ Below EMA200</div>
            </div>
            <input type="hidden" id="orbEma200Filter" value="">
        </div>

        <span class="meta-info">{meta}</span>
    </div>

    <div class="table-wrap">
    <table>
        <thead>
            <tr>
                <th onclick="toggleColExpand(0)">Symbol <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(1)">Signal Time <span class="sort-arrow">↕</span></th>
                <th class="th-orb"  onclick="toggleColExpand(2)">Yesterday High <span class="sort-arrow">↕</span></th>
                <th class="th-orb"  onclick="toggleColExpand(3)">Today Open <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(4)">Gap % <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(5)">LTP <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(6)">Vol Ratio <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(7)">Vol Momentum <span class="sort-arrow">↕</span></th>
                <th class="th-ema"  onclick="toggleColExpand(8)">EMA20 Status <span class="sort-arrow">↕</span></th>
                <th class="th-ema9"   onclick="toggleColExpand(9)">EMA9 (5m) <span class="sort-arrow">↕</span></th>
                <th class="th-ema200" onclick="toggleColExpand(10)">EMA200 (5m) <span class="sort-arrow">↕</span></th>
                <th class="th-sig"  onclick="toggleColExpand(11)">Signal Price <span class="sort-arrow">↕</span></th>
                <th class="th-risk" onclick="toggleColExpand(12)">SL <span class="sort-arrow">↕</span></th>
                <th class="th-tgt"  onclick="toggleColExpand(13)">Target <span class="sort-arrow">↕</span></th>
                <th class="th-sig"  onclick="toggleColExpand(14)">High Since Signal <span class="sort-arrow">↕</span></th>
                <th class="th-sig"  onclick="toggleColExpand(15)">Peak Move % <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(16)">Volume <span class="sort-arrow">↕</span></th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    </div>
    """
    return html


# ─────────────────────────────────────────────────────────────
# MAIN PAGE
# ─────────────────────────────────────────────────────────────
st.markdown("""
    <style>.block-container {padding-top: 1rem !important;}</style>
""", unsafe_allow_html=True)

if "orb_historical" not in st.session_state:
    with st.spinner("Loading historical data..."):
        hist = fetch_orb_historical_data()
        if hist:
            st.session_state["orb_historical"] = hist
        else:
            st.error("❌ No data found in websocket_stock_values")
            st.stop()

historical = st.session_state["orb_historical"]

today_str = datetime.now(IST).strftime("%Y-%m-%d")
if (
    "orb_tracked" not in st.session_state or
    st.session_state.get("orb_tracked_date") != today_str
):
    loaded = fetch_orb_signals_from_supabase(today_str)
    st.session_state["orb_tracked"]      = loaded
    st.session_state["orb_tracked_date"] = today_str

col1, col2 = st.columns([5, 1])
with col1:
    ws_status = "🟢 Live" if angel_ws.is_connected() else "🔴 Disconnected"
    now_ist   = datetime.now(IST)
    orb_end   = now_ist.replace(hour=ORB_END_H, minute=ORB_END_M, second=0, microsecond=0)
    orb_start = now_ist.replace(hour=ORB_START_H, minute=ORB_START_M, second=0, microsecond=0)
    if now_ist < orb_start:
        window_status = "⏳ Waiting for market open (9:15)"
    elif now_ist <= orb_end:
        mins_left = int((orb_end - now_ist).total_seconds() / 60)
        window_status = f"🟢 ORB Window Active — {mins_left} min left"
    else:
        window_status = "🔒 ORB Window Closed (9:30 passed)"
    st.markdown(
        f"📈 **ORB Scanner** &nbsp;|&nbsp; 📅 {historical['prev_date']} &nbsp;|&nbsp; "
        f"WS: {ws_status} &nbsp;|&nbsp; {window_status}",
        unsafe_allow_html=True
    )
with col2:
    if st.button("🔄 Reload", use_container_width=True):
        for key in ["orb_historical", "orb_tracked", "orb_tracked_date",
                    "orb_ema20_cache", "orb_ema5m_cache", "orb_ema200_updated"]:
            st.session_state.pop(key, None)
        st.rerun()

st.divider()


# ─────────────────────────────────────────────────────────────
# AUTO-REFRESH FRAGMENT
# ─────────────────────────────────────────────────────────────
@st.fragment(run_every=5)
def orb_scanner_table():
    now_ist   = datetime.now(IST)
    orb_start = now_ist.replace(hour=ORB_START_H, minute=ORB_START_M, second=0, microsecond=0)
    orb_end   = now_ist.replace(hour=ORB_END_H,   minute=ORB_END_M,   second=0, microsecond=0)
    in_window = orb_start <= now_ist <= orb_end

    now_str       = now_ist.strftime("%H:%M:%S")
    live_ticks    = angel_ws.latest_ticks
    df_prev       = st.session_state["orb_historical"]["df_prev"]
    df_median     = st.session_state["orb_historical"]["df_median"]
    orb_tracked   = st.session_state["orb_tracked"]

    st.caption(
        f"Last updated: {now_str} | Ticks: {len(live_ticks)} | "
        f"Tracked: {len(orb_tracked)} stocks"
    )

    # ── Batch fetch EMA for pending stocks ───────────────────
    pending = st.session_state.get("orb_ema_pending", set())
    if pending:
        get_ema20_cache(list(pending))
        st.session_state["orb_ema_pending"] = set()

    # ── Scan for new stocks ───────────────────────────────────
    if live_ticks:
        for token, tick in live_ticks.items():
            symbol = TOKEN_TO_NAME.get(token)
            if not symbol or symbol in orb_tracked:
                continue

            live_ltp    = float(tick.get("ltp",    0))
            today_open  = float(tick.get("open",   0))
            live_volume = float(tick.get("volume", 0))

            if live_ltp <= 0 or today_open <= 0:
                continue

            prev_row = df_prev[df_prev["stock"] == symbol]
            if prev_row.empty:
                continue

            yest_high  = float(prev_row["yesterday_high"].values[0])
            yest_close = float(prev_row["yesterday_close"].values[0])

            if yest_high <= 0 or yest_close <= 0:
                continue

            gap_pct = ((today_open - yest_close) / yest_close) * 100
            if abs(gap_pct) >= MAX_GAP_PCT:
                continue

            if not (today_open > yest_high or live_ltp > yest_high):
                continue

            med_row    = df_median[df_median["stock"] == symbol]
            median_vol = float(med_row["median_vol"].values[0]) if not med_row.empty else 0
            if median_vol <= 0:
                continue
            vol_ratio_val = live_volume / median_vol
            if vol_ratio_val < 1.0:
                continue

            ema_cache_check = st.session_state.get("orb_ema20_cache", {})
            if symbol in ema_cache_check:
                ema_status = ema_cache_check[symbol].get("status", "")
                if not ema_status.startswith("✅"):
                    continue
            else:
                if "orb_ema_pending" not in st.session_state:
                    st.session_state["orb_ema_pending"] = set()
                st.session_state["orb_ema_pending"].add(symbol)
                continue

            today_date   = datetime.now(IST).strftime("%Y-%m-%d")
            ema5m_data   = st.session_state.get("orb_ema5m_cache", {}).get(symbol)
            ema200_val   = ema5m_data.get("ema200",     None) if ema5m_data else None
            ema200_pct_v = ema5m_data.get("ema200_pct", None) if ema5m_data else None

            save_orb_signal_to_supabase(
                stock          = symbol,
                today_str      = today_date,
                signal_time    = now_str,
                yesterday_high = yest_high,
                today_open     = today_open,
                gap_pct        = gap_pct,
                signal_price   = live_ltp,
                ema20_status   = ema_status,
                vol_ratio      = vol_ratio_val,
                ema200_5m      = ema200_val,
                ema200_pct     = ema200_pct_v,
            )
            orb_tracked[symbol] = {
                "signal_time"    : now_str,
                "signal_price"   : live_ltp,
                "peak_ltp"       : live_ltp,
                "yesterday_high" : yest_high,
                "yesterday_close": yest_close,
                "today_open"     : today_open,
                "gap_pct"        : round(gap_pct, 2),
                "median_vol"     : median_vol,
            }

        st.session_state["orb_tracked"] = orb_tracked

    if not orb_tracked:
        if in_window:
            st.info("⏳ Scanning... No breakout stocks found yet.")
        else:
            st.info("No stocks were tracked during the ORB window today.")
        return

    # ── Update peak_ltp ───────────────────────────────────────
    if live_ticks:
        for token, tick in live_ticks.items():
            symbol = TOKEN_TO_NAME.get(token)
            if symbol not in orb_tracked:
                continue
            ltp = float(tick.get("ltp", 0))
            if ltp > orb_tracked[symbol].get("peak_ltp", 0):
                update_orb_peak_ltp(symbol, datetime.now(IST).strftime("%Y-%m-%d"), ltp)
                orb_tracked[symbol]["peak_ltp"] = ltp
        st.session_state["orb_tracked"] = orb_tracked

    # ── Build display DataFrame ───────────────────────────────
    rows = []
    for symbol, data in orb_tracked.items():
        token = NAME_TO_TOKEN.get(symbol)
        live_ltp    = float(live_ticks.get(token, {}).get("ltp",    data["signal_price"])) if token else data["signal_price"]
        live_volume = float(live_ticks.get(token, {}).get("volume", 0)) if token else 0
        median_vol  = data.get("median_vol", 0)
        if median_vol == 0:
            med_row    = df_median[df_median["stock"] == symbol]
            median_vol = float(med_row["median_vol"].values[0]) if not med_row.empty else 0
        vol_ratio_num = round(live_volume / median_vol, 2) if median_vol > 0 else 0

        rows.append({
            "Symbol"           : symbol,
            "Signal Time"      : data["signal_time"],
            "Yesterday High"   : data["yesterday_high"],
            "Today Open"       : data["today_open"],
            "Prev Close"       : data.get("yesterday_close", 0),
            "Gap %"            : f"{data['gap_pct']:+.2f}%",
            "Vol Ratio"        : f"{vol_ratio_num:.2f}x",
            "Vol Momentum"     : get_vol_momentum(vol_ratio_num),
            "Signal Price"     : data["signal_price"],
            "LTP"              : live_ltp,
            "High Since Signal": data["peak_ltp"],
            "Volume"           : live_volume,
        })

    df_display = pd.DataFrame(rows)

    # ── EMA20 ─────────────────────────────────────────────────
    ema_cache = get_ema20_cache(list(orb_tracked.keys()))
    df_display["EMA20 Status"] = df_display["Symbol"].apply(
        lambda s: ema_cache.get(s, {}).get("status", "⏳")
    )

    # ── EMA9 + EMA200 (5m) ────────────────────────────────────
    today_opens = {
        s: float(data.get("today_open", 0))
        for s, data in orb_tracked.items()
    }
    ema5m_cache = get_ema5m_cache(list(orb_tracked.keys()), today_opens)

    # ── Update Supabase with EMA200 — once per stock ──────────
    if "orb_ema200_updated" not in st.session_state:
        st.session_state["orb_ema200_updated"] = set()
    today_date = datetime.now(IST).strftime("%Y-%m-%d")

    for symbol, data in ema5m_cache.items():
        if symbol in st.session_state["orb_ema200_updated"]:
            continue
        if not data:
            continue
        ema200_v = data.get("ema200")
        ema200_p = data.get("ema200_pct")
        if ema200_v is not None and ema200_p is not None:
            update_orb_ema200(symbol, today_date, ema200_v, ema200_p)
            st.session_state["orb_ema200_updated"].add(symbol)

    df_display["EMA9"]       = df_display["Symbol"].apply(lambda s: ema5m_cache.get(s, {}).get("ema9",       None) if ema5m_cache.get(s) else None)
    df_display["EMA9 Pct"]   = df_display["Symbol"].apply(lambda s: ema5m_cache.get(s, {}).get("ema9_pct",  None) if ema5m_cache.get(s) else None)
    df_display["EMA200"]     = df_display["Symbol"].apply(lambda s: ema5m_cache.get(s, {}).get("ema200",     None) if ema5m_cache.get(s) else None)
    df_display["EMA200 Pct"] = df_display["Symbol"].apply(lambda s: ema5m_cache.get(s, {}).get("ema200_pct", None) if ema5m_cache.get(s) else None)

    # ── Sort by Vol Ratio descending ──────────────────────────
    df_display["vol_ratio_num"] = df_display["Vol Ratio"].apply(
        lambda x: float(str(x).replace("x", "")) if x else 0
    )
    df_display = df_display.sort_values("vol_ratio_num", ascending=False) \
                            .drop(columns=["vol_ratio_num"]) \
                            .reset_index(drop=True)

    # ── Window label for filter bar ───────────────────────────
    now_ist2   = datetime.now(IST)
    orb_start2 = now_ist2.replace(hour=ORB_START_H, minute=ORB_START_M, second=0, microsecond=0)
    orb_end2   = now_ist2.replace(hour=ORB_END_H,   minute=ORB_END_M,   second=0, microsecond=0)
    if now_ist2 < orb_start2:
        win_label = "⏳ Pre-market"
    elif now_ist2 <= orb_end2:
        win_label = "🟢 ORB Active"
    else:
        win_label = "🔒 ORB Closed"

    html = render_orb_table(
        df            = df_display,
        window_status = win_label,
        prev_date     = st.session_state["orb_historical"]["prev_date"],
        tick_count    = len(live_ticks),
    )

    st.components.v1.html(
        html,
        height    = min(900, 160 + len(df_display) * 50),
        scrolling = True,
    )


orb_scanner_table()
