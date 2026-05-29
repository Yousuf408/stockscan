import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# Initialize Streamlit session states for persistent storage (Replaces chrome.storage.local)
if "ts_prewatch" not in st.session_state:
    st.session_state.ts_prewatch = None
if "ts_prewatch_time" not in st.session_state:
    st.session_state.ts_prewatch_time = None
if "watchlist_data" not in st.session_state:
    st.session_state.watchlist_data = {}

# Mock data for STOCK_UNIVERSE mapping (Replace with your actual import)
STOCK_UNIVERSE = {
    "RELIANCE": {"sector": "NIFTY ENERGY"},
    "TCS": {"sector": "NIFTY IT"},
    "HDFCBANK": {"sector": "NIFTY BANK"},
    "HEROMOTOCO": {"sector": "NIFTY AUTO"},
    "JYOTICNC": {"sector": "NIFTY CAPITAL GOODS"},
    "GAIL": {"sector": "NIFTY ENERGY"},
    "GMDC": {"sector": "NIFTY METALS"},
}

# ══════════════════════════════════════════
#  BACKEND MATHEMATICS & INDICATORS (Python Port)
# ══════════════════════════════════════════

def calculate_ema(prices: list, period: int) -> float:
    if len(prices) < period:
        return None
    prices_series = pd.Series(prices)
    ema = prices_series.ewm(span=period, adjust=False).mean()
    return float(ema.iloc[-1])

def calculate_volume_median(volumes: list) -> float:
    if len(volumes) < 5:
        return None
    return float(np.median(volumes[-5:]))

def get_volume_strength(current_vol: float, median_vol: float) -> dict:
    if not median_vol or median_vol == 0:
        return {"label": "🔴 Weak", "ratio": 0.0, "color": "red"}
    ratio = current_vol / median_vol
    if ratio > 2.0:
        return {"label": "🔥 Explosive", "ratio": ratio, "color": "orange"}
    elif ratio > 1.5:
        return {"label": "🟢 Strong", "ratio": ratio, "color": "green"}
    elif ratio > 1.0:
        return {"label": "🟡 Build", "ratio": ratio, "color": "blue"}
    return {"label": "🔴 Weak", "ratio": ratio, "color": "red"}

def calculate_signals(ltp: float, ema20: float, close: float, open_p: float) -> dict:
    is_above = ltp > ema20
    is_green = close > open_p
    
    if is_above and is_green:
        return {"label": "▲ STRONG BUY", "color": "green", "status": "buy"}
    elif is_above:
        return {"label": "▲ BUY", "color": "green", "status": "buy"}
    elif not is_above and not is_green:
        return {"label": "▼ STRONG SELL", "color": "red", "status": "sell"}
    else:
        return {"label": "▼ SELL", "color": "red", "status": "sell"}

def calculate_confidence(abs_dist: float, body_gt_wick: bool, abs_dist_200: float) -> int:
    score = 100 - (abs_dist / 5 * 60)
    if body_gt_wick:
        score += 20
    if abs_dist_200 is not None and abs_dist_200 < 5:
        score += 10
    return int(min(100, max(0, round(score))))

# ══════════════════════════════════════════
#  MOCK ENGINE: Data Fetcher replacement 
# ══════════════════════════════════════════
def fetch_daily_candles_mock(symbol: str) -> dict:
    """
    Simulated engine environment. Replace this framework with your live source 
    (e.g., yfinance, kiteconnect, or your Custom API adapter).
    """
    np.random.seed(abs(hash(symbol)) % 10000)
    base_price = np.random.uniform(250, 5500)
    
    candles = []
    current_price = base_price
    for _ in range(250): # Ensure ample room for historical 200 EMA operations
        open_p = current_price * np.random.uniform(0.98, 1.02)
        close = open_p * np.random.uniform(0.97, 1.03)
        high = max(open_p, close) * np.random.uniform(1.00, 1.02)
        low = min(open_p, close) * np.random.uniform(0.98, 1.00)
        volume = int(np.random.uniform(50000, 2500000))
        candles.append({"o": open_p, "h": high, "l": low, "c": close, "v": volume})
        current_price = close

    return {"ok": True, "candles": candles}

# ══════════════════════════════════════════
#  PIPELINE CORE EXECUTION SCANNERS
# ══════════════════════════════════════════
def run_prewatch_scan():
    results = []
    all_stocks = list(STOCK_UNIVERSE.items())
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, (sym, info) in enumerate(all_stocks):
        pct = int(((idx + 1) / len(all_stocks)) * 100)
        progress_bar.progress(pct)
        status_text.text(f"Scanning {sym}... ({idx+1}/{len(all_stocks)} stocks)")
        
        res = fetch_daily_candles_mock(sym)
        if res.get("ok") and len(res["candles"]) >= 5:
            candles = res["candles"]
            last_candle = candles[-1]
            volume = last_candle["v"]
            
            # EARLY FILTER: Skip if volume < 1L (100,000)
            if volume < 100000:
                continue
                
            close_prices = [c["c"] for c in candles]
            ema20 = calculate_ema(close_prices, 20)
            ema200 = calculate_ema(close_prices, 200)
            
            if not ema20:
                continue
                
            ltp = last_candle["c"]
            # Price Bound range filters
            if ltp < 300 or ltp > 6000:
                continue
                
            dist_pct = ((ltp - ema20) / ema20) * 100
            abs_dist = abs(dist_pct)
            
            dist_200 = ((ltp - ema200) / ema200) * 100 if ema200 else None
            abs_dist_200 = abs(dist_200) if dist_200 is not None else None
            
            body = abs(last_candle["c"] - last_candle["o"])
            wick = (last_candle["h"] - last_candle["l"]) - body
            body_gt_wick = body > wick
            
            vol_median = calculate_volume_median([c["v"] for c in candles])
            
            if abs_dist <= 5.0:
                results.append({
                    "sym": sym,
                    "sector": info["sector"],
                    "ltp": ltp,
                    "ema20": ema20,
                    "ema200": ema200,
                    "dist_pct": dist_pct,
                    "abs_dist": abs_dist,
                    "dist_200": dist_200,
                    "abs_dist_200": abs_dist_200,
                    "body_gt_wick": body_gt_wick,
                    "volume": volume,
                    "vol_median": vol_median,
                    "last_candle": last_candle
                })
                
    progress_bar.empty()
    status_text.empty()
    
    st.session_state.ts_prewatch = sorted(results, key=lambda x: x["abs_dist"])
    st.session_state.ts_prewatch_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

# ══════════════════════════════════════════
#  UI LAYOUT AND CONTROLS
# ══════════════════════════════════════════
st.set_page_config(layout="wide")
st.title("🛡️ TRADE SENTRY — Prewatch Scanner v6.0")

# Primary Scanner Action Strip
col_btn1, col_btn2, col_info = st.columns([1.5, 1.5, 5])
with col_btn1:
    if st.button("🔍 SCAN DAILY EMA", use_container_width=True, type="primary"):
        run_prewatch_scan()
with col_btn2:
    if st.button("🗑️ CLEAR SCAN DATA", use_container_width=True):
        st.session_state.ts_prewatch = None
        st.session_state.ts_prewatch_time = None
        st.rerun()

if st.session_state.ts_prewatch_time:
    col_info.caption(f"**Last Scanned:** {st.session_state.ts_prewatch_time} | **Total Matches:** {len(st.session_state.ts_prewatch)}")
else:
    col_info.info("Click SCAN DAILY EMA to start parsing institutional footprints.")

if st.session_state.ts_prewatch:
    # Sidebar Filters Panel
    st.sidebar.header("🎯 Scanner Tuning Filters")
    filter_price = st.sidebar.number_input("Minimum Price (CMP)", min_value=0.0, value=0.0, step=50.0)
    filter_volume = st.sidebar.number_input("Minimum Volume", min_value=0.0, value=0.0, step=50000.0)
    filter_ema20 = st.sidebar.number_input("Max Max Dist from EMA20 %", min_value=0.0, max_value=5.0, value=5.0, step=0.1)
    filter_ema200 = st.sidebar.number_input("Max Dist from EMA200 %", min_value=0.0, value=100.0, step=1.0)
    body_filter_on = st.sidebar.toggle("Filter Body > Wick (💪 STRONG)", value=True)
    
    # Global Sorting Matrix Configuration
    sort_strategy = st.sidebar.radio("Sort Output Metrics By:", ["Distance to EMA20", "Absolute Volume Size", "Confidence Score"])

    # Processing UI Filtering Actions Engine
    raw_data = st.session_state.ts_prewatch
    filtered_data = []
    
    for r in raw_data:
        if filter_price and r["ltp"] < filter_price: continue
        if filter_volume and r["volume"] < filter_volume: continue
        if r["abs_dist"] > filter_ema20: continue
        if r["abs_dist_200"] is not None and r["abs_dist_200"] > filter_ema200: continue
        if body_filter_on and not r["body_gt_wick"]: continue
        filtered_data.append(r)

    # Sector Filter Horizontal UI Chips Allocation
    available_sectors = sorted(list(set([x["sector"] for x in filtered_data])))
    sector_selection = st.pills("Filter Matrix by Sector Footprint:", ["ALL"] + available_sectors, default="ALL")
    
    if sector_selection != "ALL":
        filtered_data = [x for x in filtered_data if x["sector"] == sector_selection]

    # Dynamic Post-Filter Metric Processor Setup
    processed_cards_list = []
    for r in filtered_data:
        sig = calculate_signals(r["ltp"], r["ema20"], r["last_candle"]["c"], r["last_candle"]["o"])
        v_strength = get_volume_strength(r["volume"], r["vol_median"])
        conf = calculate_confidence(r["abs_dist"], r["body_gt_wick"], r["abs_dist_200"])
        
        processed_cards_list.append({**r, "sig": sig, "v_strength": v_strength, "confidence": conf})

    # Sort Output Selection Handler
    if sort_strategy == "Distance to EMA20":
        processed_cards_list.sort(key=lambda x: x["abs_dist"])
    elif sort_strategy == "Absolute Volume Size":
        processed_cards_list.sort(key=lambda x: x["volume"], reverse=True)
    elif sort_strategy == "Confidence Score":
        processed_cards_list.sort(key=lambda x: x["confidence"], reverse=True)

    # ══════════════════════════════════════════
    #  ACTION BANNER: SAVE CANDIDATES TO WATCHLIST
    # ══════════════════════════════════════════
    st.markdown("---")
    with st.expander("📦 Portfolio Watchlist Actions Batch Operations Panel", expanded=True):
        w_col1, w_col2 = st.columns([2, 2])
        with w_col1:
            target_list_id = st.selectbox("Choose Target Watchlist Bucket", ["ALPHA", "BETA", "SCALPS", "SWINGS"])
        with w_col2:
            st.markdown("<div style='padding-top:24px;'></div>", unsafe_allowed_html=True)
            if st.button("🚀 INJECT FILTERED SELECTIONS TO LIVE ENGINE", use_container_width=True, type="secondary"):
                if not processed_cards_list:
                    st.warning("Empty stack setup frame array elements processed.")
                else:
                    if target_list_id not in st.session_state.watchlist_data:
                        st.session_state.watchlist_data[target_list_id] = []
                        
                    added_counter = 0
                    for item in processed_cards_list:
                        clean_sym = f"{item['sym']}.NS" if "." not in item['sym'] else item['sym']
                        trade_dir = "SELL" if item["sig"]["status"] == "sell" else "BUY"
                        
                        # Duplication safe checks logic tracking
                        already_present = any(
                            x["symbol"] == clean_sym and x["direction"] == trade_dir 
                            for x in st.session_state.watchlist_data[target_list_id]
                        )
                        
                        if not already_present:
                            st.session_state.watchlist_data[target_list_id].append({
                                "symbol": clean_sym,
                                "direction": trade_dir,
                                "exchange": "NS",
                                "sector": item["sector"],
                                "status": "WATCHING",
                                "entry": None, "sl": None, "target1": None, "target2": None
                            })
                            added_counter += 1
                            
                    st.toast(f"✅ Embedded {added_counter} Trading Targets into Watchlist Cluster [{target_list_id}]!", icon="⚡")

    # ══════════════════════════════════════════
    #  METRIC UI CARDS GRID PRESENTATION 
    # ══════════════════════════════════════════
    if not processed_cards_list:
        st.info("No structural equity setups matched current parameters inside this scope pipeline layout framing.")
    else:
        # Generate clean grid rows matching standard browser viewport distribution
        cols_per_row = 3
        for i in range(0, len(processed_cards_list), cols_per_row):
            batch_chunk = processed_cards_list[i:i + cols_per_row]
            grid_cols = st.columns(cols_per_row)
            
            for index, stock in enumerate(batch_chunk):
                with grid_cols[index]:
                    # Format dynamic display titles
                    badges_text = " ⭐ NEAR" if stock["abs_dist"] <= 1.0 else ""
                    badges_text += " 💪 STRONG" if stock["body_gt_wick"] else ""
                    
                    # Native Streamlit metrics layout construction 
                    st.markdown(
                        f"""
                        <div style="border: 1px solid rgba(49, 51, 63, 0.2); border-left: 5px solid {stock['sig']['color']}; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                            <h4 style='margin:0;'>{stock['sym']} <span style='font-size:12px; color:gray;'>| {stock['sector']}</span></h4>
                            <p style='margin:2px 0; font-size:11px; color:#FF4B4B; font-weight:bold;'>{badges_text}</p>
                            <hr style='margin:8px 0;'>
                            <table style='width:100%; font-size:12px; text-align:left;'>
                                <tr><td><b>Signal:</b></td><td style='color:{stock['sig']['color']}; font-weight:bold;'>{stock['sig']['label']}</td></tr>
                                <tr><td><b>CMP:</b></td><td>₹{stock['ltp']:.2f}</td></tr>
                                <tr><td><b>EMA20 Dist:</b></td><td>{stock['dist_pct']:.2f}%</td></tr>
                                <tr><td><b>EMA200 Dist:</b></td><td>{f"{stock['dist_200']:.2f}%" if stock['dist_200'] is not None else '—'}</td></tr>
                                <tr><td><b>Vol Strength:</b></td><td>{stock['v_strength']['label']} ({stock['v_strength']['ratio']:.2f}x)</td></tr>
                            </table>
                        </div>
                        """, 
                        unsafe_allowed_html=True
                    )
                    st.progress(stock["confidence"] / 100, text=f"Setup Confidence: {stock['confidence']}%")
else:
    st.warning("No pre-watch cache elements identified inside runtime instances container frames.")