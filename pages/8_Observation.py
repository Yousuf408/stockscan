"""
8_Observation.py
Daily Zone Scanner — finds stocks consolidating on daily timeframe
Logic:
  - Last 5 completed daily candles
  - Zone High = max of body highs (open/close)
  - Zone Low  = min of body lows  (open/close)
  - Range% ≤ 12% = consolidating
  - Live LTP from Angel WS
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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
# CONSTANTS
# ─────────────────────────────────────────────────────────────
DAILY_LOOKBACK   = 5      # last 5 completed daily candles
MAX_RANGE_PCT    = 12.0   # max consolidation range %
PARALLEL_WORKERS = 20     # parallel fetch workers
NEAR_ZONE_PCT    = 0.98   # within 2% of zone high = near
BREAKOUT_PCT     = 1.006  # 0.6% above zone high = broke out

# ─────────────────────────────────────────────────────────────
# TOKEN MAPS
# ─────────────────────────────────────────────────────────────
NAME_TO_TOKEN = {
    name: token
    for name, token, kind in STOCKS_WATCHLIST
    if kind == "stock"
}
ALL_STOCKS = [name for name, _, kind in STOCKS_WATCHLIST if kind == "stock"]

# ─────────────────────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
footer { display: none !important; }
[data-testid="stHeader"] { display: none !important; }
[data-testid="stMainBlockContainer"] { padding-top: 1rem !important; }

div[data-testid="stButton"] > button {
    background: linear-gradient(to right, #10b981, #14b8a6) !important;
    color: white !important; border: none !important;
    border-radius: 9999px !important; font-weight: 600 !important;
    font-size: 14px !important; width: 100%;
}
div[data-testid="stButton"] > button:hover { opacity: 0.88 !important; }

.metric-row { display: flex; gap: 12px; margin-bottom: 20px; }
.metric-tile {
    background: #f0fdf4; border: 1px solid #bbf7d0;
    border-radius: 10px; padding: 14px 18px; flex: 1; text-align: center;
}
.metric-val       { font-size: 26px; font-weight: 700; color: #059669; }
.metric-val-pink  { font-size: 26px; font-weight: 700; color: #db2777; }
.metric-val-amber { font-size: 26px; font-weight: 700; color: #d97706; }
.metric-lbl { font-size: 12px; color: #64748b; margin-top: 2px; }

.dot-live {
    display: inline-block; width: 8px; height: 8px;
    background: #10b981; border-radius: 50%;
    margin-right: 6px; animation: pulse 1.5s infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

.alert-box {
    display: flex; align-items: center; gap: 12px;
    background: #fff7ed; border: 1px solid #fed7aa;
    border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;
    font-size: 13px;
}

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #f8fafc; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — DATA FETCH
# ─────────────────────────────────────────────────────────────
def fetch_daily_candles(symbol: str) -> pd.DataFrame | None:
    """
    Fetch daily OHLCV from yfinance.
    Returns last 5 completed daily candles.
    """
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        df     = ticker.history(interval="1d", period="1mo")

        if df is None or df.empty or len(df) < DAILY_LOOKBACK + 1:
            return None

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]

        # Strip timezone
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            if hasattr(df["date"].dt, "tz") and df["date"].dt.tz is not None:
                df["date"] = df["date"].dt.tz_localize(None)

        # Last 5 completed candles (exclude today if market open)
        df = df.iloc[-(DAILY_LOOKBACK + 1):-1]
        return df[["date", "open", "high", "low", "close", "volume"]]

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# SECTION 2 — ZONE CALCULATION
# ─────────────────────────────────────────────────────────────
def find_zone(df: pd.DataFrame) -> dict | None:
    """
    Find consolidation zone from daily candles.
    Zone High = max of body highs  (max of open/close per candle)
    Zone Low  = min of body lows   (min of open/close per candle)
    Only body used — wicks ignored.
    """
    if df is None or len(df) < DAILY_LOOKBACK:
        return None

    con_high = df.apply(lambda r: max(r["open"], r["close"]), axis=1).max()
    con_low  = df.apply(lambda r: min(r["open"], r["close"]), axis=1).min()

    if con_low <= 0:
        return None

    range_pct = (con_high - con_low) / con_low * 100

    if range_pct > MAX_RANGE_PCT:
        return None

    return {
        "con_high" : round(float(con_high), 2),
        "con_low"  : round(float(con_low),  2),
        "range_pct": round(float(range_pct), 2),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 3 — SINGLE STOCK SCAN
# ─────────────────────────────────────────────────────────────
def scan_single(symbol: str) -> dict | None:
    """Fetch + zone for one stock."""
    try:
        df   = fetch_daily_candles(symbol)
        zone = find_zone(df)

        if zone is None:
            return None

        return {
            "symbol"   : symbol,
            "con_high" : zone["con_high"],
            "con_low"  : zone["con_low"],
            "range_pct": zone["range_pct"],
        }
    except Exception as e:
        print(f"[observation] {symbol} error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# SECTION 4 — PARALLEL SCAN
# ─────────────────────────────────────────────────────────────
def run_observation_scan(
    all_stocks  : list,
    progress_cb = None,
    status_cb   = None,
) -> list:
    """
    Scan all stocks for daily consolidation zones.
    Returns list of consolidating stocks.
    """
    total     = len(all_stocks)
    results   = []
    completed = 0

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        future_to_symbol = {
            executor.submit(scan_single, symbol): symbol
            for symbol in all_stocks
        }

        for future in as_completed(future_to_symbol):
            symbol     = future_to_symbol[future]
            completed += 1

            if progress_cb:
                progress_cb(completed, total)
            if status_cb:
                status_cb(symbol, completed, total)

            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                print(f"[observation] {symbol} future error: {e}")

    return results


# ─────────────────────────────────────────────────────────────
# SECTION 5 — LIVE LTP CHECK
# ─────────────────────────────────────────────────────────────
def enrich_with_ltp(watchlist: list, ticks: dict) -> list:
    """
    Add live LTP + status to each stock.
    Status:
      broke_out → LTP > Zone High × 1.006
      near_zone → LTP > Zone High × 0.98
      watching  → LTP in zone
      no_data   → WS disconnected
    """
    enriched = []

    for stock in watchlist:
        symbol   = stock["symbol"]
        token    = NAME_TO_TOKEN.get(symbol)
        con_high = stock["con_high"]
        con_low  = stock["con_low"]

        live_data = ticks.get(token, {}) if token else {}
        ltp       = live_data.get("ltp", None)

        if ltp is None or ltp <= 0:
            enriched.append({
                **stock,
                "ltp"            : None,
                "pct_to_breakout": None,
                "proximity_pct"  : 0,
                "status"         : "no_data",
            })
            continue

        ltp = float(ltp)

        # Proximity 0-100%
        zone_range = con_high - con_low
        proximity  = min(100, max(0, (ltp - con_low) / zone_range * 100)) if zone_range > 0 else 50

        # % to zone high
        pct_to_zone = (ltp - con_high) / con_high * 100

        # Status
        if ltp >= con_high * BREAKOUT_PCT:
            status = "broke_out"
        elif ltp >= con_high * NEAR_ZONE_PCT:
            status = "near_zone"
        else:
            status = "watching"

        enriched.append({
            **stock,
            "ltp"            : round(ltp, 2),
            "pct_to_breakout": round(pct_to_zone, 2),
            "proximity_pct"  : round(proximity, 1),
            "status"         : status,
        })

    # Sort: broke_out → near_zone → watching → no_data
    order = {"broke_out": 0, "near_zone": 1, "watching": 2, "no_data": 3}
    enriched.sort(key=lambda x: (order[x["status"]], -x["proximity_pct"]))
    return enriched


# ─────────────────────────────────────────────────────────────
# SECTION 6 — TABLE RENDER
# ─────────────────────────────────────────────────────────────
def render_table(enriched: list):
    if not enriched:
        st.info("📭 No consolidating stocks found.")
        return

    TH = "padding:8px 12px;text-align:left;font-size:11px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;border-bottom:2px solid #e2e8f0;background:#f8fafc;white-space:nowrap;"
    TD = "padding:9px 12px;border-bottom:1px solid #f1f5f9;font-size:13px;"

    rows_html = ""
    for s in enriched:
        sym      = s["symbol"]
        ltp      = s["ltp"]
        con_high = s["con_high"]
        con_low  = s["con_low"]
        rng      = s["range_pct"]
        ptb      = s["pct_to_breakout"]
        prox     = s["proximity_pct"]
        status   = s["status"]

        if status == "no_data":
            row_bg  = "background:#f8fafc;"
            ltp_col = '<span style="color:#94a3b8;font-size:12px;">N/A (WS off)</span>'
            ptb_col = '<span style="color:#94a3b8;">—</span>'
            badge   = '<span style="background:#f1f5f9;color:#94a3b8;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">No data</span>'
            bar_clr = "#e2e8f0"
        elif status == "broke_out":
            row_bg  = "background:#f0fdf4;"
            ltp_col = f'<span style="color:#059669;font-weight:700;">₹{ltp:,.2f}</span>'
            ptb_col = f'<span style="color:#059669;font-weight:600;">+{ptb:.1f}% above</span>'
            badge   = '<span style="background:#d1fae5;color:#059669;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Broke out!</span>'
            bar_clr = "#059669"
        elif status == "near_zone":
            row_bg  = "background:#fff7ed;"
            ltp_col = f'<span style="color:#d97706;font-weight:700;">₹{ltp:,.2f}</span>'
            ptb_col = f'<span style="color:#d97706;font-weight:600;">{ptb:.1f}% to go</span>'
            badge   = '<span style="background:#fce7f3;color:#db2777;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Near zone!</span>'
            bar_clr = "#f59e0b"
        else:
            row_bg  = "background:#ffffff;"
            ltp_col = f'₹{ltp:,.2f}'
            ptb_col = f'{ptb:.1f}% to go'
            badge   = ('<span style="background:#e0f2fe;color:#0284c7;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Tight</span>'
                       if rng <= 6 else
                       '<span style="background:#fef3c7;color:#d97706;padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">Watching</span>')
            bar_clr = "#10b981"

        bar_w = int(min(100, max(5, prox)))
        rows_html += f"""
        <tr style="{row_bg}">
            <td style="{TD}font-weight:600;">{sym}</td>
            <td style="{TD}">{ltp_col}</td>
            <td style="{TD}">₹{con_high:,.0f}</td>
            <td style="{TD}">₹{con_low:,.0f}</td>
            <td style="{TD}">{rng:.1f}%</td>
            <td style="{TD}">{ptb_col}</td>
            <td style="{TD}">
                <div style="width:80px;height:5px;background:#e2e8f0;border-radius:3px;overflow:hidden;display:inline-block;">
                    <div style="width:{bar_w}%;height:100%;background:{bar_clr};border-radius:3px;"></div>
                </div>
            </td>
            <td style="{TD}">{badge}</td>
        </tr>"""

    html = f"""<!DOCTYPE html><html><head>
    <style>
        body{{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
        table{{ width:100%; border-collapse:collapse; font-size:13px; }}
    </style></head><body>
    <div style="overflow-x:auto;border-radius:10px;border:1px solid #e2e8f0;">
    <table>
        <thead><tr>
            <th style="{TH}">Ticker</th>
            <th style="{TH}">LTP</th>
            <th style="{TH}">Zone High</th>
            <th style="{TH}">Zone Low</th>
            <th style="{TH}">Range %</th>
            <th style="{TH}">% to Zone High</th>
            <th style="{TH}">Proximity</th>
            <th style="{TH}">Status</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
    </table></div></body></html>"""

    st.components.v1.html(html, height=min(len(enriched) * 48 + 55, 600), scrolling=True)


# ─────────────────────────────────────────────────────────────
# SECTION 7 — WEBSOCKET
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
# SECTION 8 — MAIN UI
# ─────────────────────────────────────────────────────────────
def main():
    ws_connected = angel_ws.is_connected()
    ticks        = angel_ws.get_latest_ticks() if ws_connected else {}
    ticks_count  = len(ticks)
    built_time   = st.session_state.get("obs_built_time", "")

    # WS badge
    ws_html = (
        f'<span class="dot-live"></span><span style="color:#059669;font-size:12px;font-weight:500">Live · {ticks_count} ticks</span>'
        if ws_connected else
        '<span style="color:#dc2626;font-size:12px;">⚠️ WS disconnected</span>'
    )
    bt_html = f'<span style="color:#94a3b8;font-size:12px;">Built: {built_time}</span>' if built_time else ""

    # ── Header ──
    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;
                padding:4px 0 10px 0;border-bottom:1px solid #e2e8f0;margin-bottom:14px;">
        <div style="display:flex;align-items:center;gap:10px;">
            <span style="font-size:24px;font-weight:700;color:#0f172a;">👁️ Observation</span>
            <span style="font-size:12px;color:#94a3b8;">Daily consolidation zones · India NSE</span>
        </div>
        <div style="display:flex;align-items:center;gap:20px;">{ws_html} &nbsp; {bt_html}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Buttons ──
    b1, b2, b3 = st.columns([1, 1, 4])
    with b1:
        scan_clicked = st.button("🔍 Build Zones", use_container_width=True, key="obs_scan")
    with b2:
        refresh_clicked = st.button("🔄 Refresh Live", use_container_width=True, key="obs_refresh")
    with b3:
        st.markdown(
            f'<p style="color:#94a3b8;font-size:12px;margin-top:10px;">'
            f'Last 5 daily candles · Range ≤ {MAX_RANGE_PCT}% · {len(ALL_STOCKS)} stocks</p>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── Scan ──
    if scan_clicked:
        ensure_websocket()
        pb     = st.progress(0, text="Building daily zones...")
        st_txt = st.empty()

        def on_prog(d, t): pb.progress(int(d/t*100), text=f"Scanning... {d}/{t}")
        def on_stat(sym, d, t): st_txt.caption(f"⚡ Checking {sym} ({d}/{t})")

        results = run_observation_scan(ALL_STOCKS, on_prog, on_stat)
        pb.empty(); st_txt.empty()

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
                Click <b style="color:#10b981">Build Zones</b> to find daily consolidation zones.<br>
                <span style="font-size:12px;">Scans all {len(ALL_STOCKS)} stocks · last 5 daily candles.</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Enrich with LTP ──
    ticks    = angel_ws.get_latest_ticks() if angel_ws.is_connected() else {}
    enriched = enrich_with_ltp(results, ticks)

    broke_out = [s for s in enriched if s["status"] == "broke_out"]
    near_zone = [s for s in enriched if s["status"] == "near_zone"]
    with_data = [s for s in enriched if s["status"] != "no_data"]
    avg_range = round(np.mean([s["range_pct"] for s in with_data]), 1) if with_data else 0

    # ── Alert banners ──
    for s in broke_out:
        st.markdown(f"""
        <div class="alert-box">
            <span style="font-size:20px;">🔔</span>
            <div>
                <strong>{s["symbol"]}</strong> ne daily zone toda!
                LTP ₹{s["ltp"]:,.2f} &gt; Zone High ₹{s["con_high"]:,.0f}
                &nbsp;<span style="color:#059669;font-weight:600;">+{s["pct_to_breakout"]:.1f}% above zone</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── Metrics ──
    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-tile">
            <div class="metric-val">{len(enriched)}</div>
            <div class="metric-lbl">Consolidating</div>
        </div>
        <div class="metric-tile">
            <div class="metric-val-pink">{len(near_zone)}</div>
            <div class="metric-lbl">Near Zone High</div>
        </div>
        <div class="metric-tile">
            <div class="metric-val">{len(broke_out)}</div>
            <div class="metric-lbl">Above Zone</div>
        </div>
        <div class="metric-tile">
            <div class="metric-val-amber">{avg_range}%</div>
            <div class="metric-lbl">Avg Zone Range</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if built_time:
        st.markdown(
            f'<p style="font-size:11px;color:#94a3b8;margin-bottom:8px;">'
            f'Built: {built_time} · {len(enriched)} stocks · sorted by proximity to Zone High</p>',
            unsafe_allow_html=True
        )

    st.markdown(
        '<p style="font-size:14px;font-weight:600;color:#0f172a;margin-bottom:8px;">📋 Daily Consolidation Zones</p>',
        unsafe_allow_html=True
    )
    render_table(enriched)

    # ── Footer ──
    st.markdown("---")
    st.markdown(
        '<p style="text-align:center;color:#94a3b8;font-size:12px;">'
        '⚠️ For educational and research purposes only. Not financial advice.</p>',
        unsafe_allow_html=True
    )


main()
