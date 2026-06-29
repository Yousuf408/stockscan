"""
8_Observation.py
Consolidation Scanner — stocks sideways in last 5 days
Logic:
  - Data: Supabase websocket_stock_values
  - Last 5 days ltp (closing price) per stock
  - Each consecutive day change ≤ 2%
  - All 4 checks pass → consolidating ✅
  - Live LTP from Angel WS
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime
from supabase import create_client

import angel_ws
from angel_auth import angel_login
from config import STOCKS_WATCHLIST

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Observation",
    page_icon="👁️",
    layout="wide"
)
# ─────────────────────────────────────────────────────────────
# STYLES & SIDEBAR
# ─────────────────────────────────────────────────────────────
from styles import apply_styles, sidebar_brand, page_header
apply_styles()
sidebar_brand()

#----------------- END-------------------

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
SUPABASE_URL     = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY     = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"
TABLE_NAME       = "websocket_stock_values"
LOOKBACK_DAYS    = 5      # last 5 days
MAX_DAY_CHANGE   = 3.0    # max 3% consecutive day change
NEAR_HIGH_PCT    = 0.98   # within 2% of highest close = near high
BROKE_HIGH_PCT   = 1.006  # 0.6% above highest close = broke out

# ─────────────────────────────────────────────────────────────
# TOKEN MAP
# ─────────────────────────────────────────────────────────────
NAME_TO_TOKEN = {
    name: token
    for name, token, kind in STOCKS_WATCHLIST
    if kind == "stock"
}

# ─────────────────────────────────────────────────────────────
# SUPABASE CLIENT
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — FETCH ALL DATA FROM SUPABASE
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_all_stock_data() -> pd.DataFrame:
    """
    Fetch last 5 days data for all stocks from Supabase.
    Returns DataFrame with stock, date, ltp columns.
    """
    try:
        sb    = get_supabase()
        today = datetime.now().strftime("%Y-%m-%d")

        resp = sb.table(TABLE_NAME) \
            .select("stock, date, ltp") \
            .lt("date", today) \
            .order("date", desc=True) \
            .execute()

        if not resp.data:
            return pd.DataFrame()

        df = pd.DataFrame(resp.data)
        df["date"] = pd.to_datetime(df["date"])
        df["ltp"]  = pd.to_numeric(df["ltp"], errors="coerce")

        # Remove duplicates — keep latest per stock per date
        df = df.drop_duplicates(subset=["stock", "date"], keep="first")
        df = df.dropna(subset=["ltp"])

        return df

    except Exception as e:
        st.error(f"Supabase fetch error: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────
# SECTION 2 — CONSOLIDATION CHECK
# ─────────────────────────────────────────────────────────────
def is_consolidating(closes: list) -> bool:
    """
    Check if stock is consolidating (sideways):

    Check 1: Consecutive change ≤ 2% per day
    Check 2: First vs Last close ≤ 3% (no trend up or down)
    Check 3: Total range ≤ 6% (max high - min low of closes)
    """
    if len(closes) < LOOKBACK_DAYS:
        return False

    # CHECK 1: Consecutive change ≤ 2%
    for i in range(1, len(closes)):
        if closes[i-1] <= 0:
            return False
        day_change = abs(closes[i] - closes[i-1]) / closes[i-1] * 100
        if day_change > MAX_DAY_CHANGE:
            return False

    # CHECK 2: First vs Last ≤ 3% (no uptrend or downtrend)
    first = closes[0]
    last  = closes[-1]
    if first <= 0:
        return False
    trend_pct = abs(last - first) / first * 100
    if trend_pct > 2.0:
        return False

    # CHECK 3: Total range ≤ 6%
    high_c     = max(closes)
    low_c      = min(closes)
    range_pct  = (high_c - low_c) / low_c * 100 if low_c > 0 else 0
    if range_pct > 8.0:
        return False

    return True


# ─────────────────────────────────────────────────────────────
# SECTION 3 — SCAN ALL STOCKS
# ─────────────────────────────────────────────────────────────
def scan_consolidating_stocks(df_all: pd.DataFrame) -> list:
    """
    Scan all stocks from Supabase data.
    Returns list of consolidating stocks with price range.
    """
    results = []

    for stock, grp in df_all.groupby("stock"):
        # Last 5 days sorted ascending
        grp_sorted = grp.sort_values("date", ascending=True).tail(LOOKBACK_DAYS)

        if len(grp_sorted) < LOOKBACK_DAYS:
            continue

        closes = grp_sorted["ltp"].tolist()

        if not is_consolidating(closes):
            continue

        high_close = max(closes)
        low_close  = min(closes)
        range_pct  = (high_close - low_close) / low_close * 100 if low_close > 0 else 0

        results.append({
            "symbol"    : stock,
            "high_close": round(high_close, 2),
            "low_close" : round(low_close,  2),
            "range_pct" : round(range_pct,  2),
            "closes"    : closes,
            "last_close": closes[-1],
        })

    return results


# ─────────────────────────────────────────────────────────────
# SECTION 4 — ENRICH WITH LIVE LTP
# ─────────────────────────────────────────────────────────────
def enrich_with_ltp(watchlist: list, ticks: dict) -> list:
    """
    Add live LTP + status to each stock.
    Status vs high_close (highest of last 5 days):
      broke_out → LTP > high_close × 1.006
      near_high → LTP > high_close × 0.98
      watching  → LTP in range
      no_data   → WS disconnected
    """
    enriched = []

    for stock in watchlist:
        symbol     = stock["symbol"]
        token      = NAME_TO_TOKEN.get(symbol)
        high_close = stock.get("high_close", stock.get("con_high", 0))
        low_close  = stock.get("low_close",  stock.get("con_low",  0))

        live_data  = ticks.get(token, {}) if token else {}
        ltp        = live_data.get("ltp", None)

        if ltp is None or ltp <= 0:
            enriched.append({
                **stock,
                "ltp"           : None,
                "pct_to_high"   : None,
                "proximity_pct" : 0,
                "status"        : "no_data",
            })
            continue

        ltp = float(ltp)

        # Proximity 0-100%
        price_range = high_close - low_close
        proximity   = min(100, max(0, (ltp - low_close) / price_range * 100)) if price_range > 0 else 50

        # % to high close
        pct_to_high = (ltp - high_close) / high_close * 100

        # Status
        if ltp >= high_close * BROKE_HIGH_PCT:
            status = "broke_out"
        elif ltp >= high_close * NEAR_HIGH_PCT:
            status = "near_high"
        else:
            status = "watching"

        enriched.append({
            **stock,
            "ltp"          : round(ltp,         2),
            "pct_to_high"  : round(pct_to_high,  2),
            "proximity_pct": round(proximity,     1),
            "status"       : status,
        })

    # Sort: broke_out → near_high → watching → no_data
    order = {"broke_out": 0, "near_high": 1, "watching": 2, "no_data": 3}
    enriched.sort(key=lambda x: (order[x["status"]], -x["proximity_pct"]))
    return enriched


# ─────────────────────────────────────────────────────────────
# SECTION 5 — TABLE RENDER
# ─────────────────────────────────────────────────────────────
def render_table(enriched: list):
    if not enriched:
        st.info("📭 No consolidating stocks found.")
        return

    TH = "padding:8px 12px;text-align:left;font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;border-bottom:2px solid #e2e8f0;background:#f8fafc;white-space:nowrap;"
    TD = "padding:9px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;"

    rows_html = ""
    for s in enriched:
        sym        = s["symbol"]
        ltp        = s["ltp"]
        high_close = s.get("high_close", s.get("con_high", 0))
        low_close  = s.get("low_close",  s.get("con_low",  0))
        rng        = s.get("range_pct",  0)
        pth        = s.get("pct_to_high", s.get("pct_to_breakout", None))
        prox       = s.get("proximity_pct", 0)
        status     = s.get("status", "watching")
        closes     = s.get("closes", [])

        # Closes sparkline text
        closes_str = " → ".join([f"₹{c:,.0f}" for c in closes]) if closes else "—"

        if status == "no_data":
            row_bg  = "background:#f8fafc;"
            ltp_col = '<span style="color:#94a3b8;font-size:12px;">N/A (WS off)</span>'
            pth_col = '<span style="color:#94a3b8;">—</span>'
            badge   = '<span style="background:#f1f5f9;color:#94a3b8;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">No data</span>'
            bar_clr = "#e2e8f0"
        elif status == "broke_out":
            row_bg  = "background:#f0fdf4;"
            ltp_col = f'<span style="color:#059669;font-weight:700;">₹{ltp:,.2f}</span>'
            pth_col = f'<span style="color:#059669;font-weight:600;">+{pth:.1f}% above</span>'
            badge   = '<span style="background:#d1fae5;color:#059669;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Broke out!</span>'
            bar_clr = "#059669"
        elif status == "near_high":
            row_bg  = "background:#fff7ed;"
            ltp_col = f'<span style="color:#d97706;font-weight:700;">₹{ltp:,.2f}</span>'
            pth_col = f'<span style="color:#d97706;font-weight:600;">{pth:.1f}% to go</span>'
            badge   = '<span style="background:#fce7f3;color:#db2777;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Near high!</span>'
            bar_clr = "#f59e0b"
        else:
            row_bg  = "background:#ffffff;"
            ltp_col = f'₹{ltp:,.2f}' if ltp else "—"
            pth_col = f'{pth:.1f}% to go' if pth is not None else "—"
            badge   = '<span style="background:#fef3c7;color:#d97706;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Watching</span>'
            bar_clr = "#10b981"

        bar_w = int(min(100, max(5, prox)))

        rows_html += f"""
        <tr style="{row_bg}">
            <td style="{TD}font-weight:600;">{sym}</td>
            <td style="{TD}">{ltp_col}</td>
            <td style="{TD}">₹{high_close:,.2f}</td>
            <td style="{TD}">₹{low_close:,.2f}</td>
            <td style="{TD}">{rng:.1f}%</td>
            <td style="{TD};font-size:11px;color:#94a3b8;">{closes_str}</td>
            <td style="{TD}">{pth_col}</td>
            <td style="{TD}">
                <div style="width:80px;height:5px;background:#e2e8f0;border-radius:3px;overflow:hidden;display:inline-block;">
                    <div style="width:{bar_w}%;height:100%;background:{bar_clr};border-radius:3px;"></div>
                </div>
            </td>
            <td style="{TD}">{badge}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html><head>
    <style>
        body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
        table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    </style></head><body>
    <div style="overflow-x:auto;border-radius:10px;border:1px solid #e2e8f0;">
    <table>
        <thead><tr>
            <th style="{TH}">Ticker</th>
            <th style="{TH}">Live LTP</th>
            <th style="{TH}">5D High</th>
            <th style="{TH}">5D Low</th>
            <th style="{TH}">Range %</th>
            <th style="{TH}">Last 5 Closes</th>
            <th style="{TH}">% to High</th>
            <th style="{TH}">Proximity</th>
            <th style="{TH}">Status</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table></div></body></html>"""

    st.components.v1.html(html, height=min(len(enriched) * 48 + 55, 600), scrolling=True)


# ─────────────────────────────────────────────────────────────
# SECTION 6 — WEBSOCKET
# ─────────────────────────────────────────────────────────────
def ensure_websocket():
    if not angel_ws.is_connected():
        with st.spinner("Connecting to Angel One WebSocket..."):
            creds = angel_login()
            if creds:
                angel_ws.start_websocket(
                    creds["jwt_token"], creds["api_key"],
                    creds["client_id"], creds["feed_token"]
                )
                time.sleep(3)
            else:
                st.error("❌ Angel One login failed.")


# ─────────────────────────────────────────────────────────────
# SECTION 7 — MAIN UI
# ─────────────────────────────────────────────────────────────
def main():
    ws_connected = angel_ws.is_connected()
    ticks        = angel_ws.get_latest_ticks() if ws_connected else {}
    ticks_count  = len(ticks)
    built_time   = st.session_state.get("obs_built_time", "")

    ws_html = (
        f'<span style="display:inline-block;width:8px;height:8px;background:#10b981;border-radius:50%;margin-right:6px;animation:pulse 1.5s infinite;"></span>'
        f'<span style="color:#059669;font-size:12px;font-weight:500">Live · {ticks_count} ticks</span>'
        if ws_connected else
        '<span style="color:#dc2626;font-size:12px;">⚠️ WS disconnected</span>'
    )
    bt_html = f'<span style="color:#94a3b8;font-size:12px;">Built: {built_time}</span>' if built_time else ""

    # ── Header ──
    st.markdown(f"""
    <style>
    @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:0.3}} }}
    footer {{ display:none !important; }}
    [data-testid="stHeader"] {{ display:none !important; }}
    [data-testid="stMainBlockContainer"] {{ padding-top:1rem !important; }}
    div[data-testid="stButton"] > button {{
        background: linear-gradient(to right, #10b981, #14b8a6) !important;
        color: white !important; border: none !important;
        border-radius: 9999px !important; font-weight: 600 !important;
        font-size: 14px !important; width: 100%;
    }}
    .metric-row {{ display:flex; gap:12px; margin-bottom:20px; }}
    .metric-tile {{ background:#f0fdf4; border:1px solid #bbf7d0; border-radius:10px; padding:14px 18px; flex:1; text-align:center; }}
    .mv   {{ font-size:26px; font-weight:700; color:#059669; }}
    .mv-p {{ font-size:26px; font-weight:700; color:#db2777; }}
    .mv-a {{ font-size:26px; font-weight:700; color:#d97706; }}
    .ml   {{ font-size:12px; color:#64748b; margin-top:2px; }}
    .alert-box {{ display:flex; align-items:center; gap:12px; background:#fff7ed; border:1px solid #fed7aa; border-radius:10px; padding:12px 16px; margin-bottom:10px; font-size:13px; }}
    </style>
    <div style="display:flex;align-items:center;justify-content:space-between;
                padding:4px 0 10px 0;border-bottom:1px solid #e2e8f0;margin-bottom:14px;">
        <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:24px;font-weight:700;color:#0f172a;">👁️ Observation</span>
            <span style="font-size:12px;color:#94a3b8;">Daily consolidation · last 5 days · max 2% move</span>
        </div>
        <div style="display:flex;align-items:center;gap:20px;">{ws_html} &nbsp; {bt_html}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Buttons ──
    b1, b2, b3 = st.columns([1, 1, 4])
    with b1:
        scan_clicked = st.button("🔍 Scan Now", use_container_width=True, key="obs_scan")
    with b2:
        refresh_clicked = st.button("🔄 Refresh Live", use_container_width=True, key="obs_refresh")
    with b3:
        st.markdown(
            '<p style="color:#94a3b8;font-size:12px;margin-top:10px;">'
            'Supabase data · last 5 days · consecutive change ≤ 2%</p>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── Scan ──
    if scan_clicked:
        ensure_websocket()
        with st.spinner("Fetching data from Supabase..."):
            fetch_all_stock_data.clear()
            df_all  = fetch_all_stock_data()
        if df_all.empty:
            st.error("❌ No data from Supabase. Check connection.")
            return
        with st.spinner("Scanning for consolidating stocks..."):
            results = scan_consolidating_stocks(df_all)
        # Clear old cached results before saving new ones
        st.session_state.pop("obs_results", None)
        st.session_state["obs_results"]    = results
        st.session_state["obs_built_time"] = datetime.now().strftime("%d %b %Y, %I:%M %p")
        st.rerun()

    # ── Results ──
    results = st.session_state.get("obs_results", None)

    if results is None:
        st.markdown(f"""
        <div style="text-align:center;padding:60px 20px;color:#94a3b8;">
            <div style="font-size:40px;margin-bottom:12px;">👁️</div>
            <div style="font-size:15px;color:#475569;">
                Click <b style="color:#10b981">Scan Now</b> to find consolidating stocks.<br>
                <span style="font-size:12px;">Last 5 days from Supabase · consecutive change ≤ 2%</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Enrich with LTP ──
    ticks    = angel_ws.get_latest_ticks() if angel_ws.is_connected() else {}
    enriched = enrich_with_ltp(results, ticks)

    broke_out = [s for s in enriched if s["status"] == "broke_out"]
    near_high = [s for s in enriched if s["status"] == "near_high"]
    with_data = [s for s in enriched if s["status"] != "no_data"]
    avg_range = round(np.mean([s["range_pct"] for s in with_data]), 1) if with_data else 0

    # ── Alert banners ──
    for s in broke_out:
        st.markdown(f"""
        <div class="alert-box">
            <span style="font-size:20px;">🔔</span>
            <div>
                <strong>{s["symbol"]}</strong> consolidation tod di!
                LTP ₹{s["ltp"]:,.2f} &gt; 5D High ₹{s["high_close"]:,.0f}
                &nbsp;<span style="color:#059669;font-weight:600;">+{s["pct_to_high"]:.1f}% above</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Metrics ──
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-tile"><div class="mv">{len(enriched)}</div><div class="ml">Consolidating</div></div>
        <div class="metric-tile"><div class="mv-p">{len(near_high)}</div><div class="ml">Near 5D High</div></div>
        <div class="metric-tile"><div class="mv">{len(broke_out)}</div><div class="ml">Just Broke Out</div></div>
        <div class="metric-tile"><div class="mv-a">{avg_range}%</div><div class="ml">Avg Range</div></div>
    </div>
    """, unsafe_allow_html=True)

    if built_time:
        st.markdown(
            f'<p style="font-size:11px;color:#94a3b8;margin-bottom:8px;">'
            f'Scanned: {built_time} · {len(enriched)} stocks consolidating · sorted by proximity to 5D high</p>',
            unsafe_allow_html=True
        )

    st.markdown(
        '<p style="font-size:14px;font-weight:600;color:#0f172a;margin-bottom:8px;">📋 Consolidating Stocks</p>',
        unsafe_allow_html=True
    )
    render_table(enriched)

    st.markdown("---")
    st.markdown(
        '<p style="text-align:center;color:#94a3b8;font-size:12px;">'
        '⚠️ For educational and research purposes only. Not financial advice.</p>',
        unsafe_allow_html=True
    )


main()
