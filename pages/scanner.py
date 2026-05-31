import streamlit as st
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ══════════════════════════════════════════
#  EMBEDDED FLAT TERMINAL STYLING ENGINE
# ══════════════════════════════════════════
def apply_terminal_theme():
    st.markdown("""
        <style>
            .block-container {
                padding-top: 1rem !important;
                padding-bottom: 0rem !important;
                padding-left: 1.5rem !important;
                padding-right: 1.5rem !important;
            }
            div[data-testid="stVerticalBlock"] > div {
                margin-bottom: -0.3rem !important;
                padding-bottom: 0rem !important;
            }
            div[data-testid="stElementContainer"] div[class*="st-emotion-cache"] {
                gap: 0.35rem !important;
            }
            .compact-header {
                font-size: 14px; 
                font-weight: 700; 
                margin-top: 4px; 
                margin-bottom: 2px;
                color: #111111; 
                letter-spacing: 0.3px;
            }
        </style>
    """, unsafe_allow_html=True)

# --- Fallback Data Engine Setup ---
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# JSON Database Path Finder (Pointing to Root folder from pages/ directory)
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.json")

def load_selected_watchlist_stocks(bucket_name: str) -> list:
    """
    Reads directly from your existing watchlist database.
    Extracts only the symbols allocated to the target bucket.
    """
    if not os.path.exists(WATCHLIST_FILE):
        return []
    try:
        with open(WATCHLIST_FILE, "r") as f:
            db = json.load(f)
        target_key = f"watchlist_{bucket_name}"
        items = db.get(target_key, [])
        # Return unique list of symbols found in that specific watchlist
        return list(set([item["symbol"].upper().strip() for item in items if "symbol" in item]))
    except Exception as e:
        st.error(f"Error reading watchlist database: {e}")
        return []

# ══════════════════════════════════════════
#  PHASE 3: INTRADAY 9:15 CORE MATH ENGINE
# ══════════════════════════════════════════
def compute_ema(prices: pd.Series, period: int) -> float:
    if len(prices) < period: return None
    return float(prices.ewm(span=period, adjust=False).mean().iloc[-1])

def evaluate_intraday_915_setup(df_5min: pd.DataFrame, df_daily: pd.DataFrame) -> dict:
    if df_5min.empty or len(df_5min) < 1: return None
    
    # Isolate 9:15 AM Candle profile dimensions
    candle_915 = df_5min.iloc[0]
    c_open = float(candle_915['Open'])
    c_high = float(candle_915['High'])
    c_low = float(candle_915['Low'])
    c_close = float(candle_915['Close'])
    
    # Merge historical backdrop closes with today's rolling 5-min dataset for EMA compounding
    combined_closes = pd.concat([df_daily['Close'], df_5min['Close']]).reset_index(drop=True)
    
    ema20 = compute_ema(combined_closes, 20)
    ema200 = compute_ema(combined_closes, 200)
    
    if ema20 is None: return None
    
    current_ltp = float(df_5min['Close'].iloc[-1])
    current_vol = float(df_5min['Volume'].iloc[-1])
    
    abs_dist_pct = (abs(current_ltp - ema20) / ema20) * 100.0
    
    # EMA200 Proximity Flag matrix calculation (≤ 1.5% framework)
    is_ema200_prox = False
    if ema200 is not None:
        if ((abs(ema20 - ema200) / ema200) * 100.0) <= 1.5:
            is_ema200_prox = True

    # Body vs Wick Structural Filter Validation
    body_size = abs(c_close - c_open)
    total_wick_size = (c_high - c_low) - body_size
    body_gt_wick = body_size > total_wick_size
    
    is_above_ema20 = current_ltp > ema20
    is_green_candle = c_close > c_open
    
    # Signal Sorting Logic
    if is_above_ema20 and is_green_candle:
        signal, color, bg = "▲ STRONG BUY", "#00AA3B", "rgba(0,170,59,0.08)"
    elif is_above_ema20:
        signal, color, bg = "▲ BUY", "#00AA3B", "rgba(0,170,59,0.08)"
    elif not is_above_ema20 and not is_green_candle:
        signal, color, bg = "▼ STRONG SELL", "#D32F2F", "rgba(211,47,47,0.08)"
    else:
        signal, color, bg = "▼ SELL", "#D32F2F", "rgba(211,47,47,0.08)"
        
    # Scoring Algorithm
    score = 100.0 - (abs_dist_pct * 10.0)
    if body_gt_wick: score += 20.0
    if is_ema200_prox: score += 10.0
    confidence = int(min(100, max(0, round(score))))
    
    return {
        "ltp": current_ltp, "volume": current_vol, "ema20": ema20, "ema200": ema200,
        "abs_dist_pct": abs_dist_pct, "body_gt_wick": body_gt_wick, "is_proximate": is_ema200_prox,
        "signal": signal, "color": color, "bg": bg, "confidence": confidence
    }

# ══════════════════════════════════════════
#  HIGH-SPEED RUNTIME CONCURRENT LOADER
# ══════════════════════════════════════════
def run_live_terminal_scan(symbols_list: list):
    results = []
    if not symbols_list: return results
    
    status_placeholder = st.empty()
    status_placeholder.info(f"🚀 Streaming 5-Min multi-bars for {len(symbols_list)} target watchlist items...")
    
    # Check if active connection sequence object resides in memory
    api_obj = globals().get("smartApi") or st.session_state.get("smartApi")
    
    if api_obj:
        def fetch_angel(sym):
            try:
                # Local fallback check if token maps inside standard lists or use dynamic search
                params_5m = {
                    "exchange": "NSE", "symboltoken": str(sym), "interval": "FIVE_MINUTE",
                    "fromdate": datetime.now().strftime("%Y-%m-%d 09:15"), "todate": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                params_d = {
                    "exchange": "NSE", "symboltoken": str(sym), "interval": "ONE_DAY",
                    "fromdate": (pd.Timestamp.now() - pd.Timedelta(days=50)).strftime("%Y-%m-%d %H:%M"),
                    "todate": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                }
                res_5m = api_obj.getHistoricData(params_5m)
                res_d = api_obj.getHistoricData(params_d)
                if res_5m.get("status") and res_d.get("status"):
                    df_5m = pd.DataFrame(res_5m["data"], columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
                    df_d = pd.DataFrame(res_d["data"], columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
                    res = evaluate_intraday_915_setup(df_5m, df_d)
                    if res: res["sym"] = sym; return res
            except: pass
            return None

        with ThreadPoolExecutor(max_workers=5) as exec:
            futures = [exec.submit(fetch_angel, s) for s in symbols_list]
            for f in as_completed(futures):
                r = f.result()
                if r: results.append(r)
                
    elif YFINANCE_AVAILABLE:
        def fetch_yf(sym):
            try:
                t = yf.Ticker(f"{sym}.NS")
                df_5m = t.history(period="1d", interval="5m")
                df_d = t.history(period="3mo", interval="1d")
                if not df_5m.empty and not df_d.empty:
                    df_5m = df_5m.reset_index().rename(columns={"Date":"Timestamp", "Datetime":"Timestamp"})
                    df_d = df_d.reset_index().rename(columns={"Date":"Timestamp"})
                    res = evaluate_intraday_915_setup(df_5m, df_d)
                    if res: res["sym"] = sym; return res
            except: pass
            return None

        with ThreadPoolExecutor(max_workers=8) as exec:
            futures = [exec.submit(fetch_yf, s) for s in symbols_list]
            for f in as_completed(futures):
                r = f.result()
                if r: results.append(r)

    status_placeholder.empty()
    st.session_state.intraday_scan_cache = results
    st.session_state.last_scan_timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

# ══════════════════════════════════════════
#  DASHBOARD TERMINAL FRONTEND ENGINE VIEW
# ══════════════════════════════════════════
st.set_page_config(layout="wide")
apply_terminal_theme()

# Top Navigation and Control Bar
ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2.0, 1.5, 1.5, 5.0])

with ctrl_col1:
    selected_bucket = st.selectbox(
        "Active Watchlist Feed Source:",
        ["Today", "Yesterday", "New"],
        label_visibility="collapsed"
    )

# Load target stocks immediately to show context metrics
active_symbols = load_selected_watchlist_stocks(selected_bucket)

with ctrl_col2:
    if st.button("🔴 RUN INTRADAY SCAN", use_container_width=True, type="primary"):
        if active_symbols:
            run_live_terminal_scan(active_symbols)
        else:
            st.error("Selected Watchlist is completely empty!")

with ctrl_col3:
    if st.button("🗑️ RESET ENGINE", use_container_width=True):
        st.session_state.intraday_scan_cache = None
        st.session_state.last_scan_timestamp = None
        st.rerun()

# Real-time Pulse Strip Indicators
cache_count = len(st.session_state.intraday_scan_cache) if st.session_state.intraday_scan_cache else 0
last_ts = st.session_state.last_scan_timestamp if st.session_state.last_scan_timestamp else "None"
ctrl_col4.markdown(
    f"<div style='padding-top: 6px; font-size: 13px; color: #555555;'>"
    f"📋 <b>Watchlist Size:</b> <span style='color:#111111; font-weight:700;'>{len(active_symbols)} Items</span> | "
    f"⏱️ <b>Last Run:</b> <span style='color:#111111; font-weight:700;'>{last_ts}</span> | "
    f"⚡ <b>Monitored:</b> <span style='color:#111111; font-weight:700;'>{cache_count} Live Signals</span>"
    f"</div>",
    unsafe_allow_html=True
)

st.markdown("<h3 class='compact-header'>⚙️ INTRADAY FILTER ARCHITECTURE</h3>", unsafe_allow_html=True)

# Compact Filters Area
with st.container(border=True):
    f_col1, f_col2, f_col3, f_col4 = st.columns([3, 3, 3, 3])
    with f_col1:
        f_price = st.number_input("Price Floor (₹)", min_value=0.0, value=0.0, step=100.0)
    with f_col2:
        f_gap = st.number_input("Max 20EMA Gap %", min_value=0.0, max_value=50.0, value=3.0, step=0.2)
    with f_col3:
        f_vol = st.number_input("Min Session Vol", min_value=0.0, value=0.0, step=50000.0)
    with f_col4:
        f_valid_candle = st.toggle("Solid Candle Only (Body > Wick)", value=False)
        
    sort_strategy = st.radio(
        "Sorting Execution Order Array:",
        ["EMA20 Gap Proximity", "Volume Depth", "Confidence Matrix Score"],
        horizontal=True,
        label_visibility="collapsed"
    )

# --- PROCESS FILTER STACK & PRESENTATION ---
if st.session_state.intraday_scan_cache:
    raw_data = st.session_state.intraday_scan_cache
    filtered_data = []
    
    for row in raw_data:
        if f_price and row["ltp"] < f_price: continue
        if f_vol and row["volume"] < f_vol: continue
        if row["abs_dist_pct"] > f_gap: continue
        if f_valid_candle and not row["body_gt_wick"]: continue
        filtered_data.append(row)
        
    # Sorting Arrays Matrix Execution
    if sort_strategy == "EMA20 Gap Proximity":
        filtered_data.sort(key=lambda x: x["abs_dist_pct"])
    elif sort_strategy == "Volume Depth":
        filtered_data.sort(key=lambda x: x["volume"], reverse=True)
    elif sort_strategy == "Confidence Matrix Score":
        filtered_data.sort(key=lambda x: x["confidence"], reverse=True)

    st.markdown(f"<h3 style='font-size: 14px; font-weight: 700; margin-top: 12px; color:#111111;'>📊 Verified Intraday Signals ({len(filtered_data)})</h3>", unsafe_allow_html=True)
    
    # Render Tight Terminal Layout Cards
    for s_node in filtered_data:
        with st.container(border=True):
            h_l, h_r = st.columns([8, 4])
            with h_l:
                prox_badge = f"<span style='background: rgba(255,153,0,0.1); color: #B36200; font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 700; border: 1px solid rgba(255,153,0,0.2); margin-left:8px;'>⭐ EMA200 ALIGNED</span>" if s_node["is_proximate"] else ""
                candle_badge = f"<span style='background: rgba(0,170,0,0.1); color: #007A2B; font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 700; border: 1px solid rgba(0,170,59,0.2); margin-left:8px;'>💪 CONFIRMED CANDLE</span>" if s_node["body_gt_wick"] else ""
                st.markdown(f"<div style='display: flex; align-items: center;'><span style='font-size: 16px; font-weight: 800; color:#111111;'>{s_node['sym']}</span>{prox_badge}{candle_badge}</div>", unsafe_allow_html=True)
            with h_r:
                st.markdown(f"<div style='text-align: right;'><span style='background: {s_node['bg']}; color: {s_node['color']}; font-size: 11px; font-weight: 800; padding: 2px 8px; border-radius: 4px; border: 1px solid {s_node['color']}33;'>{s_node['signal']}</span></div>", unsafe_allow_html=True)
                
            st.markdown("<div style='margin-top: 4px; border-bottom: 1px solid #f6f6f6;'></div>", unsafe_allow_html=True)
            
            c1, c2, c3, c4 = st.columns([3, 3, 3, 3])
            with c1:
                st.markdown(f"<p style='font-size:10px; color:#666666; margin:0;'>LTP</p><p style='font-size:14px; font-weight:700; margin:0;'>₹{s_node['ltp']:.2f}</p>", unsafe_allow_html=True)
            with c2:
                st.markdown(f"<p style='font-size:10px; color:#666666; margin:0;'>20 EMA LINE</p><p style='font-size:14px; font-weight:700; color:#333333; margin:0;'>₹{s_node['ema20']:.2f}</p>", unsafe_allow_html=True)
            with c3:
                v_formatted = f"{s_node['volume']/100000:.1f}L" if s_node['volume'] >= 100000 else f"{s_node['volume']/1000:.1f}K"
                st.markdown(f"<p style='font-size:10px; color:#666666; margin:0;'>VOLUME</p><p style='font-size:14px; font-weight:700; margin:0;'>{v_formatted}</p>", unsafe_allow_html=True)
            with c4:
                st.markdown(f"<div style='display: flex; justify-content: space-between;'><span style='font-size:10px; color:#666666;'>CONFIDENCE</span><span style='font-size:10px; font-weight:700; color:#00AA3B;'>{s_node['confidence']}%</span></div>", unsafe_allow_html=True)
                st.progress(s_node["confidence"] / 100)
else:
    st.warning("No active streaming records found in cache memory. Pick a Watchlist and trigger 'RUN INTRADAY SCAN' above.")
