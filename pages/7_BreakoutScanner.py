"""
7_BreakoutScanner.py
Breakout Scanner — finds stocks breaking out of consolidation zones
Uses: yfinance (4H candles) + Supabase (volume filter) + Angel WS (live price)
"""

import os
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
import json
from supabase import create_client
import angel_ws
from angel_auth import angel_login
from config import STOCKS_WATCHLIST

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Breakout Scanner",
    page_icon="⚡",
    layout="wide"
)

# ─────────────────────────────────────────────────────────────
# SUPABASE CONFIG — apni keys yahan daalo
# ─────────────────────────────────────────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"



@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

# ─────────────────────────────────────────────────────────────
# TOKEN → NAME MAP  (from config.py)
# ─────────────────────────────────────────────────────────────
# { "2885": "RELIANCE", "1333": "HDFCBANK", ... }
TOKEN_TO_NAME = {
    token: name
    for name, token, kind in STOCKS_WATCHLIST
    if kind == "stock"
}

# { "RELIANCE": "2885", ... }
NAME_TO_TOKEN = {
    name: token
    for name, token, kind in STOCKS_WATCHLIST
    if kind == "stock"
}

# All stock symbols (NSE format for yfinance → append .NS)
ALL_STOCKS = [name for name, _, kind in STOCKS_WATCHLIST if kind == "stock"]

# ─────────────────────────────────────────────────────────────
# STYLES — Light Theme
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Hide footer & header ── */
footer { display: none !important; }
[data-testid="stHeader"] { display: none !important; }

/* ── Scan button ── */
div[data-testid="stButton"] > button {
    background: linear-gradient(to right, #10b981, #14b8a6) !important;
    color: white !important;
    border: none !important;
    border-radius: 9999px !important;
    padding: 10px 28px !important;
    font-weight: 600 !important;
    font-size: 15px !important;
    width: 100%;
}
div[data-testid="stButton"] > button:hover {
    opacity: 0.88 !important;
}

/* ── Metric tiles ── */
.metric-row {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
}
.metric-tile {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 10px;
    padding: 14px 18px;
    flex: 1;
    text-align: center;
}
.metric-val {
    font-size: 26px;
    font-weight: 700;
    color: #059669;
}
.metric-lbl {
    font-size: 12px;
    color: #64748b;
    margin-top: 2px;
}

/* ── Table ── */
.results-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
.results-table th {
    background: #f8fafc;
    color: #64748b;
    padding: 10px 14px;
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 2px solid #e2e8f0;
    position: sticky;
    top: 0;
}
.results-table td {
    padding: 10px 14px;
    border-bottom: 1px solid #f1f5f9;
    color: #1e293b;
}
.results-table tr:hover td {
    background: #f0fdf4;
}
.ticker-badge {
    background: #d1fae5;
    color: #059669;
    padding: 3px 8px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 12px;
}
.up-text   { color: #059669; font-weight: 600; }
.down-text { color: #dc2626; font-weight: 600; }
.vol-badge {
    background: #fef3c7;
    color: #d97706;
    padding: 2px 8px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 12px;
}
.zone-txt { color: #94a3b8; font-size: 11px; }

/* ── Chart container ── */
.chart-wrap {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px;
    margin-top: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #94a3b8;
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-msg  { font-size: 15px; }

/* ── WS status dot ── */
.dot-live {
    display: inline-block;
    width: 8px; height: 8px;
    background: #10b981;
    border-radius: 50%;
    margin-right: 6px;
    animation: pulse 1.5s infinite;
}
@keyframes pulse {
    0%,100% { opacity: 1; }
    50%      { opacity: 0.3; }
}

/* ── Scanning text ── */
.scanning-text {
    color: #64748b;
    font-size: 13px;
    margin-top: 8px;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #f8fafc; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — WEBSOCKET AUTO-CONNECT
# ─────────────────────────────────────────────────────────────
def ensure_websocket():
    """Auto-connect WebSocket if not already running."""
    if not angel_ws.is_connected():
        with st.spinner("Connecting to Angel One WebSocket..."):
            creds = angel_login()
            if creds:
                angel_ws.start_websocket(
                    creds["jwt_token"],
                    creds["api_key"],
                    creds["client_id"],
                    creds["feed_token"]
                )
                time.sleep(3)  # Wait for connection
                return True
            else:
                st.error("❌ Angel One login failed. Live prices unavailable.")
                return False
    return True


# ─────────────────────────────────────────────────────────────
# SECTION 2 — SUPABASE: AVG VOLUME (last 10 days)
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def fetch_avg_volumes():
    """
    Fetch average daily volume for all stocks from Supabase.
    Uses last 10 days of past data (date < today).
    Returns: { "RELIANCE": 15000000, "HDFCBANK": 8000000, ... }
    """
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        resp = supabase.table("websocket_stock_values") \
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

        # Avg volume
        avg_vol = df_top10.groupby("stock")["volume"].mean().to_dict()
        return avg_vol

    except Exception as e:
        st.warning(f"Supabase fetch error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# SECTION 3 — YFINANCE: FETCH 1H DATA → BUILD 4H CANDLES
# ─────────────────────────────────────────────────────────────
def fetch_1h_data(symbol: str) -> pd.DataFrame | None:
    """Fetch 1-month 1h data from yfinance for NSE stock."""
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        df = ticker.history(interval="1h", period="1mo")
        if df is None or df.empty or len(df) < 4:
            return None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        return df[["datetime", "open", "high", "low", "close", "volume"]]
    except Exception:
        return None


def aggregate_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate 1h candles → 4h candles.
    Every 4 consecutive 1h candles = 1 4h candle.
    Only complete groups of 4 are kept.
    """
    candles = []
    rows    = df_1h.values.tolist()  # [datetime, open, high, low, close, volume]
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
# SECTION 4 — 8 CHECKS
# ─────────────────────────────────────────────────────────────
def run_8_checks(symbol: str, df_4h: pd.DataFrame, avg_vol_20d: float) -> dict | None:
    """
    Run all 8 breakout checks on a stock.
    Returns result dict if ALL checks pass, else None.
    """
    if df_4h is None or len(df_4h) < 12:
        return None

    # ── Most recently completed 4H candle ──
    current     = df_4h.iloc[-1]
    lookback    = df_4h.iloc[-11:-1]   # prior 10 completed 4H candles

    cur_open    = current["open"]
    cur_close   = current["close"]
    cur_high    = current["high"]
    cur_low     = current["low"]
    cur_volume  = current["volume"]

    # ── CHECK 1: Consolidation ≤ 12% ──
    con_high = lookback.apply(lambda r: max(r["open"], r["close"]), axis=1).max()
    con_low  = lookback.apply(lambda r: min(r["open"], r["close"]), axis=1).min()

    if con_low <= 0:
        return None

    range_pct = (con_high - con_low) / con_low * 100
    if range_pct > 12:
        return None

    # ── CHECK 2: Breakout above range (close ≥ conHigh × 1.02) ──
    if cur_close < con_high * 1.02:
        return None

    breakout_pct = (cur_close - con_high) / con_high * 100

    # ── CHECK 3: Breakout size ≥ 5% ──
    body_pct = abs(cur_close - cur_open) / cur_open * 100
    if body_pct < 5:
        return None

    # ── CHECK 4: Relative volume ≥ 1.5× avg of prior 10 candles ──
    avg_4h_vol = lookback["volume"].mean()
    if avg_4h_vol <= 0:
        return None
    rel_vol = cur_volume / avg_4h_vol
    if rel_vol < 1.5:
        return None

    # ── CHECK 5: Liquidity — avg daily volume ≥ 500,000 ──
    if avg_vol_20d < 500_000:
        return None

    # ── Fetch daily data for checks 6, 7, 8 ──
    try:
        ticker  = yf.Ticker(f"{symbol}.NS")
        df_daily = ticker.history(interval="1d", period="6mo")
        if df_daily is None or len(df_daily) < 50:
            return None
        daily_close = df_daily["Close"].values
    except Exception:
        return None

    # ── CHECK 6: Market cap ≥ 50M ──
    try:
        info   = ticker.fast_info
        mktcap = getattr(info, "market_cap", 0) or 0
        if mktcap < 50_000_000:
            return None
    except Exception:
        return None

    # ── CHECK 7: Price within 10% of 20d or 50d high ──
    high_20d = max(daily_close[-20:]) if len(daily_close) >= 20 else max(daily_close)
    high_50d = max(daily_close[-50:]) if len(daily_close) >= 50 else max(daily_close)

    near_20d = cur_close >= high_20d * 0.90
    near_50d = cur_close >= high_50d * 0.90
    if not (near_20d or near_50d):
        return None

    pct_from_high = min(
        (cur_close - high_20d) / high_20d * 100,
        (cur_close - high_50d) / high_50d * 100
    )

    # ── CHECK 8: Trend — close > SMA20 and SMA50 ──
    sma20 = np.mean(daily_close[-20:]) if len(daily_close) >= 20 else None
    sma50 = np.mean(daily_close[-50:]) if len(daily_close) >= 50 else None

    if sma20 is None or sma50 is None:
        return None
    if cur_close <= sma20 or cur_close <= sma50:
        return None

    # ── All 8 checks passed ✅ ──
    return {
        "symbol"        : symbol,
        "price"         : round(cur_close, 2),
        "breakout_pct"  : round(breakout_pct, 2),
        "body_pct"      : round(body_pct, 2),
        "rel_vol"       : round(rel_vol, 2),
        "pct_from_high" : round(pct_from_high, 2),
        "con_high"      : round(con_high, 2),
        "con_low"       : round(con_low, 2),
        "range_pct"     : round(range_pct, 2),
        "sma20"         : round(sma20, 2),
        "sma50"         : round(sma50, 2),
        "avg_vol_20d"   : int(avg_vol_20d),
        # Store 4H candles for chart
        "candles_4h"    : df_4h.tail(15).to_dict("records"),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 5 — MAIN SCAN FUNCTION
# ─────────────────────────────────────────────────────────────
def run_scan():
    """
    Full scan — runs 8 checks on all stocks in STOCKS_WATCHLIST.
    Returns list of passing stocks sorted by rel_vol descending.
    """
    avg_volumes = fetch_avg_volumes()
    results     = []
    total       = len(ALL_STOCKS)

    progress_bar = st.progress(0, text="Starting scan...")
    status_text  = st.empty()

    for i, symbol in enumerate(ALL_STOCKS):
        pct  = int((i + 1) / total * 100)
        progress_bar.progress(pct, text=f"Scanning {symbol} ({i+1}/{total})")
        status_text.markdown(
            f'<p class="scanning-text">⚡ Checking {symbol}...</p>',
            unsafe_allow_html=True
        )

        # Get avg volume from Supabase
        avg_vol = avg_volumes.get(symbol, 0)

        # Fetch 1h → build 4h
        df_1h = fetch_1h_data(symbol)
        if df_1h is None:
            continue

        df_4h = aggregate_to_4h(df_1h)
        if df_4h.empty:
            continue

        # Run 8 checks
        result = run_8_checks(symbol, df_4h, avg_vol)
        if result:
            results.append(result)

    progress_bar.empty()
    status_text.empty()

    # Sort by relative volume descending
    results.sort(key=lambda x: x["rel_vol"], reverse=True)
    return results


# ─────────────────────────────────────────────────────────────
# SECTION 6 — CHART (Lightweight Charts via HTML)
# ─────────────────────────────────────────────────────────────
def render_chart(result: dict):
    """Render 4H candlestick chart with consolidation band."""
    candles   = result["candles_4h"]
    con_high  = result["con_high"]
    con_low   = result["con_low"]
    symbol    = result["symbol"]

    # Prepare candle data for lightweight-charts
    chart_data = []
    for c in candles:
        try:
            dt = c["datetime"]
            if hasattr(dt, "timestamp"):
                ts = int(dt.timestamp())
            else:
                ts = int(pd.Timestamp(dt).timestamp())

            chart_data.append({
                "time" : ts,
                "open" : round(float(c["open"]),  2),
                "high" : round(float(c["high"]),  2),
                "low"  : round(float(c["low"]),   2),
                "close": round(float(c["close"]), 2),
            })
        except Exception:
            continue

    if not chart_data:
        st.warning("Chart data unavailable.")
        return

    # Breakout candle = last candle
    breakout_time = chart_data[-1]["time"]

    chart_json    = json.dumps(chart_data)
    con_high_json = json.dumps(con_high)
    con_low_json  = json.dumps(con_low)
    brk_time_json = json.dumps(breakout_time)

    html = f"""
    <div id="chart_{symbol}" style="width:100%;height:400px;background:#0f172a;border-radius:8px;"></div>
    <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    (function() {{
        var container = document.getElementById('chart_{symbol}');
        var chart = LightweightCharts.createChart(container, {{
            width:  container.clientWidth,
            height: 400,
            layout: {{
                background: {{ color: '#ffffff' }},
                textColor:  '#94a3b8',
            }},
            grid: {{
                vertLines:  {{ color: '#f1f5f9' }},
                horzLines:  {{ color: '#f1f5f9' }},
            }},
            crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
            rightPriceScale: {{ borderColor: '#e2e8f0' }},
            timeScale: {{
                borderColor:     '#334155',
                timeVisible:     true,
                secondsVisible:  false,
            }},
        }});

        var candleSeries = chart.addCandlestickSeries({{
            upColor:        '#10b981',
            downColor:      '#f87171',
            borderUpColor:  '#10b981',
            borderDownColor:'#f87171',
            wickUpColor:    '#10b981',
            wickDownColor:  '#f87171',
        }});

        var allCandles  = {chart_json};
        var conHigh     = {con_high_json};
        var conLow      = {con_low_json};
        var brkTime     = {brk_time_json};

        // Color breakout candle emerald
        var colored = allCandles.map(function(c) {{
            if (c.time === brkTime) {{
                return Object.assign({{}}, c, {{
                    color:       '#10b981',
                    borderColor: '#10b981',
                    wickColor:   '#10b981',
                }});
            }}
            return c;
        }});

        candleSeries.setData(colored);

        // Consolidation band — rose at 15% opacity
        var bandSeries = chart.addLineSeries({{
            color:       'rgba(244,63,94,0)',
            lineWidth:   0,
            priceLineVisible: false,
        }});

        // Upper band line
        var upperSeries = chart.addLineSeries({{
            color:           'rgba(244,63,94,0.6)',
            lineWidth:       1,
            lineStyle:       LightweightCharts.LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
        }});

        // Lower band line
        var lowerSeries = chart.addLineSeries({{
            color:           'rgba(244,63,94,0.6)',
            lineWidth:       1,
            lineStyle:       LightweightCharts.LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
        }});

        var times = allCandles.map(function(c) {{ return c.time; }});
        upperSeries.setData(times.map(function(t) {{ return {{ time: t, value: conHigh }}; }}));
        lowerSeries.setData(times.map(function(t) {{ return {{ time: t, value: conLow  }}; }}));

        // Price lines for con zone
        candleSeries.createPriceLine({{
            price:      conHigh,
            color:      'rgba(244,63,94,0.4)',
            lineWidth:  1,
            lineStyle:  LightweightCharts.LineStyle.Dotted,
            axisLabelVisible: true,
            title:      'Zone High',
        }});
        candleSeries.createPriceLine({{
            price:      conLow,
            color:      'rgba(244,63,94,0.4)',
            lineWidth:  1,
            lineStyle:  LightweightCharts.LineStyle.Dotted,
            axisLabelVisible: true,
            title:      'Zone Low',
        }});

        chart.timeScale().fitContent();

        // Responsive
        window.addEventListener('resize', function() {{
            chart.applyOptions({{ width: container.clientWidth }});
        }});
    }})();
    </script>
    """

    st.components.v1.html(html, height=420)


# ─────────────────────────────────────────────────────────────
# SECTION 7 — RESULTS TABLE
# ─────────────────────────────────────────────────────────────
def render_table(results: list, ticks: dict):
    """Render results table with live prices from Angel WS."""

    if not results:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">📭</div>
            <div class="empty-msg">No breakouts found — try scanning again.</div>
        </div>
        """, unsafe_allow_html=True)
        return

    rows_html = ""
    for r in results:
        symbol = r["symbol"]
        token  = NAME_TO_TOKEN.get(symbol)

        # Live price from WebSocket
        live_data  = ticks.get(token, {}) if token else {}
        live_price = live_data.get("ltp", r["price"])
        live_chg   = live_data.get("change_pct", 0)

        price_str = f"₹{live_price:,.2f}"
        chg_class = "up-text" if live_chg >= 0 else "down-text"
        chg_str   = f"+{live_chg:.2f}%" if live_chg >= 0 else f"{live_chg:.2f}%"

        brk_class = "up-text" if r["breakout_pct"] >= 0 else "down-text"
        high_class = "up-text" if r["pct_from_high"] >= -5 else "down-text"

        rows_html += f"""
        <tr>
            <td><span class="ticker-badge">{symbol}</span></td>
            <td>{price_str} <span class="{chg_class}" style="font-size:11px">{chg_str}</span></td>
            <td class="{brk_class}">+{r['breakout_pct']:.2f}%</td>
            <td class="up-text">{r['body_pct']:.2f}%</td>
            <td><span class="vol-badge">{r['rel_vol']:.1f}x</span></td>
            <td class="{high_class}">{r['pct_from_high']:.2f}%</td>
            <td style="color:#94a3b8;font-size:11px">
                Zone: ₹{r['con_low']:,.0f}–₹{r['con_high']:,.0f}
            </td>
        </tr>
        """

    table_html = f"""
    <div style="overflow-x:auto;border-radius:10px;border:1px solid #334155;">
    <table class="results-table">
        <thead>
            <tr>
                <th>Ticker</th>
                <th>Live Price</th>
                <th>Breakout %</th>
                <th>Body Size %</th>
                <th>Rel. Volume</th>
                <th>% from High</th>
                <th>Zone</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    </div>
    """
    st.markdown(table_html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# SECTION 8 — MAIN UI
# ─────────────────────────────────────────────────────────────
def main():
    # ── Header ──
    col_title, col_btn, col_time = st.columns([4, 1.5, 2])

    with col_title:
        st.markdown(
            '<h1 style="color:#0f172a;font-size:28px;font-weight:700;margin:0">⚡ Breakout Scanner</h1>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<p style="color:#64748b;font-size:13px;margin:0">4H consolidation breakouts · India NSE</p>',
            unsafe_allow_html=True
        )

    with col_time:
        last_scanned = st.session_state.get("last_scanned", None)
        if last_scanned:
            st.markdown(
                f'<p style="color:#64748b;font-size:12px;text-align:right;margin-top:14px">'
                f'Last scanned: {last_scanned}</p>',
                unsafe_allow_html=True
            )

    with col_btn:
        scan_clicked = st.button("🔍 Scan Now", use_container_width=True)

    st.markdown("---")

    # ── WebSocket status ──
    ws_connected = angel_ws.is_connected()
    ticks        = angel_ws.get_latest_ticks()
    ticks_count  = len(ticks)

    ws_col1, ws_col2 = st.columns([6, 2])
    with ws_col1:
        if ws_connected:
            st.markdown(
                f'<span class="dot-live"></span>'
                f'<span style="color:#059669;font-size:13px;font-weight:500">WebSocket Live · {ticks_count} stocks receiving ticks</span>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<span style="color:#dc2626;font-size:13px">⚠️ WebSocket disconnected — live prices unavailable</span>',
                unsafe_allow_html=True
            )

    # ── Scan logic ──
    if scan_clicked:
        ensure_websocket()

        with st.spinner(""):
            st.markdown(
                '<p class="scanning-text">⚡ Scanning all stocks for 4H breakouts...</p>',
                unsafe_allow_html=True
            )
            results = run_scan()

        st.session_state["scan_results"]  = results
        st.session_state["last_scanned"]  = datetime.now().strftime("%d %b %Y, %I:%M %p")
        st.rerun()

    # ── Results ──
    results = st.session_state.get("scan_results", None)
    ticks   = angel_ws.get_latest_ticks()

    if results is None:
        # Pre-scan state
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">🔍</div>
            <div class="empty-msg" style="color:#475569">
                Click <b style="color:#10b981">Scan Now</b> to find 4H breakout stocks.<br>
                <span style="font-size:12px;color:#94a3b8">Scans all {count} stocks from your watchlist.</span>
            </div>
        </div>
        """.replace("{count}", str(len(ALL_STOCKS))), unsafe_allow_html=True)
        return

    # ── Metric tiles ──
    passed  = len(results)
    total   = len(ALL_STOCKS)
    avg_rvol = round(np.mean([r["rel_vol"] for r in results]), 1) if results else 0
    top_rvol = round(max([r["rel_vol"] for r in results]), 1) if results else 0

    st.markdown(f"""
    <div class="metric-row">
        <div class="metric-tile">
            <div class="metric-val">{passed}</div>
            <div class="metric-lbl">Breakouts Found</div>
        </div>
        <div class="metric-tile">
            <div class="metric-val">{total}</div>
            <div class="metric-lbl">Stocks Scanned</div>
        </div>
        <div class="metric-tile">
            <div class="metric-val">{avg_rvol}x</div>
            <div class="metric-lbl">Avg Rel. Volume</div>
        </div>
        <div class="metric-tile">
            <div class="metric-val">{top_rvol}x</div>
            <div class="metric-lbl">Top Rel. Volume</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Table ──
    st.markdown(
        '<h3 style="color:#0f172a;font-size:16px;font-weight:600;margin-bottom:10px">📋 Breakout Stocks</h3>',
        unsafe_allow_html=True
    )
    render_table(results, ticks)

    # ── Chart section ──
    if results:
        st.markdown('<div style="margin-top:28px">', unsafe_allow_html=True)
        st.markdown(
            '<h3 style="color:#0f172a;font-size:16px;font-weight:600;margin-bottom:10px">📊 4H Candle Chart</h3>',
            unsafe_allow_html=True
        )

        symbols      = [r["symbol"] for r in results]
        selected_sym = st.selectbox(
            "Select stock to view chart",
            options=symbols,
            label_visibility="collapsed"
        )

        selected_result = next((r for r in results if r["symbol"] == selected_sym), None)
        if selected_result:
            # Chart stats
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Price",         f"₹{selected_result['price']:,.2f}")
            c2.metric("Breakout %",    f"+{selected_result['breakout_pct']:.2f}%")
            c3.metric("Rel. Volume",   f"{selected_result['rel_vol']:.1f}x")
            c4.metric("Zone Range %",  f"{selected_result['range_pct']:.2f}%")

            st.markdown('<div class="chart-wrap">', unsafe_allow_html=True)
            render_chart(selected_result)
            st.markdown("""
            <div style="display:flex;gap:20px;margin-top:10px;font-size:12px;color:#64748b">
                <span>🟩 Breakout candle</span>
                <span>🔴 Consolidation zone (dashed)</span>
                <span>⬜ 4H candles</span>
            </div>
            """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # ── Footer ──
    st.markdown("---")
    st.markdown(
        '<p style="text-align:center;color:#94a3b8;font-size:12px">'
        '⚠️ For educational and research purposes only. Not financial advice.'
        '</p>',
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
else:
    main()
