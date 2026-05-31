import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import math
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ══════════════════════════════════════════
#  EMBEDDED STYLING ENGINE (No Styles.py Needed)
# ══════════════════════════════════════════
def apply_compact_theme_directly():
    """
    Applies custom CSS injects to reduce maximum vertical height leaks,
    tightens element margins, and forces extreme compact layouts.
    """
    st.markdown("""
        <style>
            /* Main container tight padding */
            .block-container {
                padding-top: 1rem !important;
                padding-bottom: 0rem !important;
                padding-left: 1.5rem !important;
                padding-right: 1.5rem !important;
            }
            
            /* Remove margins from custom streamlit metric headers & containers */
            div[data-testid="stVerticalBlock"] > div {
                margin-bottom: -0.25rem !important;
                padding-bottom: 0rem !important;
            }
            
            /* Compact padding inside border boxes */
            div[data-testid="stElementContainer"] div[class*="st-emotion-cache"] {
                gap: 0.4rem !important;
            }
            
            /* Force horizontal radio component to look flat and tight */
            div[data-testid="stRadio"] > div {
                gap: 10px !important;
                padding: 0px !important;
            }
            
            /* Custom utility classes for minimal rows */
            .compact-header {
                font-size: 13px; 
                font-weight: 700; 
                margin-top: 5px; 
                margin-bottom: 2px;
                color: #000000; 
                letter-spacing:0.3px;
            }
        </style>
    """, unsafe_allow_html=True)

# --- External Backup Dependency Engine ---
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# Import local universe if available, else fallback to standard structured dictionary
try:
    from stocks import STOCK_UNIVERSE, get_stock_token, get_stock_sector
except ImportError:
    STOCK_UNIVERSE = {
        "RELIANCE": {"sector": "NIFTY ENERGY", "token": "2885"},
        "TCS": {"sector": "NIFTY IT", "token": "11536"},
        "HEROMOTOCO": {"sector": "NIFTY AUTO", "token": "1348"},
        "JYOTICNC": {"sector": "NIFTY CAPITAL GOODS", "token": "19485"},
        "GMDC": {"sector": "NIFTY METALS", "token": "10174"},
        "WELCORP": {"sector": "NIFTY METALS", "token": "11369"}
    }
    def get_stock_sector(sym): return STOCK_UNIVERSE.get(sym, {}).get("sector", "GENERAL")
    def get_stock_token(sym): return STOCK_UNIVERSE.get(sym, {}).get("token", None)

# Database Management Definitions
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.json")
WATCHLIST_NAMES = ["Today", "Yesterday", "New"]

def load_watchlist_db() -> dict:
    if not os.path.exists(WATCHLIST_FILE): return {f"watchlist_{n}": [] for n in WATCHLIST_NAMES}
    try:
        with open(WATCHLIST_FILE, "r") as f: return json.load(f)
    except: return {f"watchlist_{n}": [] for n in WATCHLIST_NAMES}

def save_watchlist_db(data: dict):
    try:
        with open(WATCHLIST_FILE, "w") as f: json.dump(data, f, indent=2)
    except Exception as e: st.error(f"Sync error: {e}")

# Session Cache Initialization
if "intraday_scan_cache" not in st.session_state: st.session_state.intraday_scan_cache = None
if "last_scan_timestamp" not in st.session_state: st.session_state.last_scan_timestamp = None

# ══════════════════════════════════════════
#  MATHEMATICAL SCANNER MATHEMATICS ENGINE
# ══════════════════════════════════════════
def compute_ema_vector(prices: pd.Series, period: int) -> float:
    if len(prices) < period: return None
    return float(prices.ewm(span=period, adjust=False).mean().iloc[-1])

def evaluate_915_candle_and_indicators(df_5min: pd.DataFrame, df_daily_backlog: pd.DataFrame) -> dict:
    """
    Natively replicates Section 3 from scanner.js (Phase 3 Engine).
    Calculates EMAs at the 9:15 benchmark reference index while checking 200 EMA proximity.
    """
    if df_5min.empty or len(df_5min) < 1: return None
    
    candle_915 = df_5min.iloc[0]
    c_open, c_high, c_low, c_close = float(candle_915['Open']), float(candle_915['High']), float(candle_915['Low']), float(candle_915['Close'])
    
    combined_closes = pd.concat([df_daily_backlog['Close'], df_5min['Close']]).reset_index(drop=True)
    
    ema20 = compute_ema_vector(combined_closes, 20)
    ema200 = compute_ema_vector(combined_closes, 200)
    
    if ema20 is None: return None
    
    current_ltp = float(df_5min['Close'].iloc[-1])
    current_vol = float(df_5min['Volume'].iloc[-1])
    
    abs_dist = abs(current_ltp - ema20)
    abs_dist_pct = (abs_dist / ema20) * 100.0
    
    is_ema200_proximate = False
    if ema200 is not None:
        prox_dist_pct = (abs(ema20 - ema200) / ema200) * 100.0
        if prox_dist_pct <= 1.5:
            is_ema200_proximate = True

    body_size = abs(c_close - c_open)
    total_wick_size = (c_high - c_low) - body_size
    body_gt_wick = body_size > total_wick_size
    
    is_above = current_ltp > ema20
    is_green = c_close > c_open
    
    if is_above and is_green:
        signal, color, bg_alpha = "▲ STRONG BUY", "#00AA3B", "rgba(0,170,59,0.08)"
    elif is_above:
        signal, color, bg_alpha = "▲ BUY", "#00AA3B", "rgba(0,170,59,0.08)"
    elif not is_above and not is_green:
        signal, color, bg_alpha = "▼ STRONG SELL", "#D32F2F", "rgba(211,47,47,0.08)"
    else:
        signal, color, bg_alpha = "▼ SELL", "#D32F2F", "rgba(211,47,47,0.08)"
        
    score = 100.0 - (abs_dist_pct * 10.0)
    if body_gt_wick: score += 20.0
    if is_ema200_proximate: score += 10.0
    confidence_score = int(min(100, max(0, round(score))))
    
    return {
        "ltp": current_ltp, "volume": current_vol, "ema20": ema20, "ema200": ema200,
        "abs_dist": abs_dist, "abs_dist_pct": abs_dist_pct, "body_gt_wick": body_gt_wick,
        "is_proximate": is_ema200_proximate, "signal": signal, "color": color, "bg": bg_alpha,
        "confidence": confidence_score, "open_915": c_open, "close_915": c_close
    }

# ══════════════════════════════════════════
#  HIGH INTENSITY MASSIVE COMPUTE SCANNER
# ══════════════════════════════════════════
def run_web_app_intraday_scan(watchlist_scope: str):
    results = []
    all_stocks = list(STOCK_UNIVERSE.items())
    
    status_msg = st.empty()
    status_msg.info(f"⚡ Processing active workers stream. Downloading 5-Min profiles for target {watchlist_scope} Watchlist...")
    
    api_obj = globals().get("smartApi") or st.session_state.get("smartApi")
    
    if api_obj:
        def fetch_and_evaluate_angel(symbol, info):
            try:
                token = info.get("token") or get_stock_token(symbol)
                params_5m = {
                    "exchange": "NSE", "symboltoken": str(token), "interval": "FIVE_MINUTE",
                    "fromdate": datetime.now().strftime("%Y-%m-%d 09:15"), "todate": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                params_daily = {
                    "exchange": "NSE", "symboltoken": str(token), "interval": "ONE_DAY",
                    "fromdate": (pd.Timestamp.now() - pd.Timedelta(days=50)).strftime("%Y-%m-%d %H:%M"),
                    "todate": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                }
                res_5m = api_obj.getHistoricData(params_5m)
                res_d = api_obj.getHistoricData(params_daily)
                
                if res_5m.get("status") and res_d.get("status"):
                    df_5m = pd.DataFrame(res_5m["data"], columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
                    df_d = pd.DataFrame(res_d["data"], columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
                    metrics = evaluate_915_candle_and_indicators(df_5m, df_d)
                    if metrics:
                        metrics["sym"] = symbol
                        metrics["sector"] = info.get("sector", "GENERAL")
                        return metrics
            except: pass
            return None

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(fetch_and_evaluate_angel, sym, inf) for sym, inf in all_stocks]
            for fut in as_completed(futures):
                res_block = fut.result()
                if res_block: results.append(res_block)
                
    elif YFINANCE_AVAILABLE:
        for sym, info in all_stocks:
            try:
                ticker = yf.Ticker(f"{sym}.NS")
                df_5m = ticker.history(period="1d", interval="5m")
                df_d = ticker.history(period="3mo", interval="1d")
                
                if not df_5m.empty and not df_d.empty:
                    df_5m = df_5m.reset_index().rename(columns={"Date": "Timestamp", "Datetime": "Timestamp"})
                    df_d = df_d.reset_index().rename(columns={"Date": "Timestamp"})
                    metrics = evaluate_915_candle_and_indicators(df_5m, df_d)
                    if metrics:
                        metrics["sym"] = sym
                        metrics["sector"] = info.get("sector", "GENERAL")
                        results.append(metrics)
            except: pass

    status_msg.empty()
    st.session_state.intraday_scan_cache = results
    st.session_state.last_scan_timestamp = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

# ══════════════════════════════════════════
#  UI INTERFACE PIPELINE RENDER ENGINE
# ══════════════════════════════════════════
st.set_page_config(layout="wide")
apply_compact_theme_directly() # Instantly apply from local file context without import leaks

col_btn1, col_btn2, col_watchlist_sel, col_info = st.columns([1.5, 1.5, 2.0, 4.0])
with col_btn1:
    target_scope = col_watchlist_sel.selectbox("Watchlist Target Scope Source:", ["Today", "Yesterday", "New"], label_visibility="collapsed")
    if st.button("🔴 RUN SCANNER", use_container_width=True, type="primary"):
        run_web_app_intraday_scan(target_scope)
with col_btn2:
    if st.button("🗑️ RESET ENGINE", use_container_width=True):
        st.session_state.intraday_scan_cache = None
        st.session_state.last_scan_timestamp = None
        st.rerun()

total_records = len(st.session_state.intraday_scan_cache) if st.session_state.intraday_scan_cache else 0
ts_str = st.session_state.last_scan_timestamp if st.session_state.last_scan_timestamp else "None"
col_info.markdown(
    f"<div style='padding-top: 6px; font-size: 13px; color: #444444;'>"
    f"⏳ <b>Engine Pulse Refresh:</b> <span style='color:#000000; font-weight:700;'>{ts_str}</span> | "
    f"🎯 <b>Active Stack Cache:</b> <span style='color:#000000; font-weight:700;'>{total_records} Securities Loaded</span>"
    f"</div>",
    unsafe_allow_html=True
)

st.markdown("<h3 class='compact-header'>⚙️ REFINEMENT OPTIONS</h3>", unsafe_allow_html=True)

with st.container(border=True):
    p1_col1, p1_col2, p1_col3 = st.columns([4.0, 4.0, 4.0])
    with p1_col1:
        filter_price = st.number_input("Minimum Price (₹)", min_value=0.0, value=0.0, step=50.0)
    with p1_col2:
        filter_gap_pct = st.number_input("EMA Gap % Max Constraint", min_value=0.0, max_value=100.0, value=2.5, step=0.1)
    with p1_col3:
        filter_volume = st.number_input("Volume Floor Boundary", min_value=0.0, value=0.0, step=10000.0)
        
    p2_col1, p2_col2 = st.columns([3.0, 9.0])
    with p2_col1:
        toggle_body_wick = st.toggle("Body > Wick Setup Only", value=False)
    with p2_col2:
        sorting_vector = st.radio(
            "Matrix Processing Order Strategy Vector Selector:",
            ["EMA20 Proximity Gap", "Absolute Volume Size", "Performance Confidence Score"],
            horizontal=True,
            label_visibility="collapsed"
        )

if st.session_state.intraday_scan_cache:
    working_dataset = st.session_state.intraday_scan_cache
    compiled_dataset = []
    
    for row in working_dataset:
        if filter_price and row["ltp"] < filter_price: continue
        if filter_volume and row["volume"] < filter_volume: continue
        if row["abs_dist_pct"] > filter_gap_pct: continue
        if toggle_body_wick and not row["body_gt_wick"]: continue
        compiled_dataset.append(row)

    unique_sectors = sorted(list(set([r["sector"] for r in compiled_dataset])))
    sector_tally = {}
    for r in compiled_dataset: sector_tally[r["sector"]] = sector_tally.get(r["sector"], 0) + 1
    
    pill_nodes = ["ALL SECTORS"] + [f"{s.replace('NIFTY ', '')} ({sector_tally.get(s, 0)})" for s in unique_sectors]
    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    selected_pill_node = st.pills("Active Sector Track:", pill_nodes, default="ALL SECTORS")
    
    if selected_pill_node != "ALL SECTORS":
        compiled_dataset = [x for x in compiled_dataset if x["sector"].replace('NIFTY ', '') in selected_pill_node]

    if sorting_vector == "EMA20 Proximity Gap":
        compiled_dataset.sort(key=lambda x: x["abs_dist_pct"])
    elif sorting_vector == "Absolute Volume Size":
        compiled_dataset.sort(key=lambda x: x["volume"], reverse=True)
    elif sorting_vector == "Performance Confidence Score":
        compiled_dataset.sort(key=lambda x: x["confidence"], reverse=True)

    with st.container(border=True):
        st.markdown("<h4 style='margin:0 0 8px 0; font-size:13px; color:#000000; font-weight:700;'>📦 Batch Inject Watchlist Management Panel</h4>", unsafe_allow_html=True)
        w_col1, w_col2 = st.columns([8, 4])
        with w_col1:
            target_inject_bucket = st.selectbox("Select Target Database Watchlist Bucket Location:", ["Today", "Yesterday", "New"], label_visibility="collapsed", key="injector_sel")
        with w_col2:
            if st.button("➕ INJECT SCRIPT MATCHES", use_container_width=True):
                if not compiled_dataset:
                    st.warning("No dynamic targets matched criteria vectors.")
                else:
                    db = load_watchlist_db()
                    target_key = f"watchlist_{target_inject_bucket}"
                    added_units = 0
                    
                    for unit in compiled_dataset:
                        clean_sym = unit['sym'].upper().strip()
                        trade_dir = "SELL" if "SELL" in unit["signal"] else "BUY"
                        
                        is_duplicate = any(x.get("symbol") == clean_sym and x.get("direction") == trade_dir for x in db[target_key])
                        if not is_duplicate:
                            db[target_key].append({
                                "symbol": clean_sym, "exchange": "NS", "direction": trade_dir, "entry": float(round(unit["ltp"])),
                                "sl": None, "target1": None, "target2": None, "note": "Dynamic Web Engine Stream Injection",
                                "sector": unit["sector"], "status": "WATCHING", "lastPrice": unit["ltp"], "added_at": datetime.now().isoformat()
                            })
                            added_units += 1
                    save_watchlist_db(db)
                    st.toast(f"⚡ Injected {added_units} items into target {target_inject_bucket} list module!", icon="🔥")

    st.markdown(f"<h3 style='font-size: 14px; font-weight: 700; margin-top: 15px; color: #000000;'>📊 Showing {len(compiled_dataset)} Matching Setups</h3>", unsafe_allow_html=True)
    
    for stock in compiled_dataset:
        with st.container(border=True):
            h_left, h_right = st.columns([8, 4])
            with h_left:
                badge_prox = f"<span style='background: rgba(255,153,0,0.1); color: #B36200; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 700; border: 1px solid rgba(255,153,0,0.25); margin-left:10px;'>⭐ EMA200 PROX ({stock['abs_dist_pct']:.2f}%)</span>" if stock["is_proximate"] else ""
                badge_body = f"<span style='background: rgba(0,170,0,0.1); color: #007A2B; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 700; border: 1px solid rgba(0,170,59,0.25); margin-left:10px;'>💪 CANDLE VALID</span>" if stock["body_gt_wick"] else ""
                st.markdown(f"<div style='display: flex; align-items: center; gap: 8px;'><span style='font-size: 17px; font-weight: 800; color: #111111;'>{stock['sym']}</span><span style='font-size: 13px; color: #787878;'>| &nbsp; 📁 {stock['sector'].replace('NIFTY ', '')}</span>{badge_prox}{badge_body}</div>", unsafe_allow_html=True)
            with h_right:
                st.markdown(f"<div style='text-align: right;'><span style='background: {stock['bg']}; color: {stock['color']}; font-size: 11px; font-weight: 800; padding: 3px 10px; border-radius: 4px; border: 1px solid {stock['color']}40;'>{stock['signal']}</span></div>", unsafe_allow_html=True)
            
            st.markdown("<div style='margin-top: 6px; border-bottom: 1px solid #f3f3f3;'></div>", unsafe_allow_html=True)
            m1, m2, m3, m4 = st.columns([3, 3, 3, 3])
            with m1:
                st.markdown(f"<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>CMP</p><p style='font-size:15px; font-weight:700; color:#111111; margin:1px 0;'>₹{stock['ltp']:.2f}</p>", unsafe_allow_html=True)
            with m2:
                st.markdown(f"<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>20 EMA REFERENCE</p><p style='font-size:15px; font-weight:700; color:#333333; margin:1px 0;'>₹{stock['ema20']:.2f}</p>", unsafe_allow_html=True)
            with m3:
                vol_str = f"{stock['volume']/100000:.1f}L" if stock['volume']>=100000 else f"{stock['volume']/1000:.1f}K"
                st.markdown(f"<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>CURRENT STREAM VOL</p><p style='font-size:15px; font-weight:700; color:#111111; margin:1px 0;'>{vol_str}</p>", unsafe_allow_html=True)
            with m4:
                st.markdown(f"<div style='display: flex; justify-content: space-between; margin-bottom:1px;'><span style='font-size:10px; color:#777777; font-weight:700;'>SCORE MATRIX:</span><span style='font-size:11px; font-weight:700; color:#00AA3B;'>{stock['confidence']}%</span></div>", unsafe_allow_html=True)
                st.progress(stock["confidence"] / 100)
else:
    st.warning("No dynamic streaming logs found in active storage matrix cache. Press 'RUN SCANNER' to initiate download cycles.")
