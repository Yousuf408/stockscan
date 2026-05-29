import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# Initialize Session States for Multi-page synchronization
if "ts_prewatch" not in st.session_state:
    st.session_state.ts_prewatch = None
if "ts_prewatch_time" not in st.session_state:
    st.session_state.ts_prewatch_time = None
if "watchlist_data" not in st.session_state:
    st.session_state.watchlist_data = {}

# ─── NIFTY INDEX MATCHING STOCK UNIVERSE ───
STOCK_UNIVERSE = {
    "RELIANCE": {"sector": "NIFTY ENERGY"},
    "TCS": {"sector": "NIFTY IT"},
    "HDFCBANK": {"sector": "NIFTY BANK"},
    "HEROMOTOCO": {"sector": "NIFTY AUTO"},
    "JYOTICNC": {"sector": "NIFTY CAPITAL GOODS"},
    "GAIL": {"sector": "NIFTY ENERGY"},
    "GMDC": {"sector": "NIFTY METALS"},
    "TIPSMUSIC": {"sector": "NIFTY MEDIA"},
    "LANDMARK": {"sector": "NIFTY REALTY"},
    "CEATLTD": {"sector": "NIFTY AUTO"},
    "MUTHOOTFIN": {"sector": "NIFTY FINANCIAL SERVICES"},
    "KIRLOSENG": {"sector": "NIFTY CAPITAL GOODS"},
    "WHEELS": {"sector": "NIFTY AUTO"}
}

# ══════════════════════════════════════════
#  CORE INDICATORS & MATHEMATICS LOGIC
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

def format_volume_indian(vol: float) -> str:
    if not vol or vol == 0: return "0"
    if vol >= 10000000: return f"{vol / 10000000:.1f}Cr"
    if vol >= 100000: return f"{vol / 100000:.1f}L"
    if vol >= 1000: return f"{vol / 1000:.1f}K"
    return str(int(vol))

def get_volume_strength(current_vol: float, median_vol: float) -> dict:
    if not median_vol or median_vol == 0:
        return {"label": "🔴 Weak", "ratio": 0.0, "color": "#FF4B4B"}
    ratio = current_vol / median_vol
    if ratio > 2.0: return {"label": "🔥 Explosive", "ratio": ratio, "color": "#FFAA00"}
    if ratio > 1.5: return {"label": "🟢 Strong", "ratio": ratio, "color": "#00FF66"}
    if ratio > 1.0: return {"label": "🟡 Build", "ratio": ratio, "color": "#FFFF00"}
    return {"label": "🔴 Weak", "ratio": ratio, "color": "#FF4B4B"}

def calculate_signals(ltp: float, ema20: float, close: float, open_p: float) -> dict:
    is_above = ltp > ema20
    is_green = close > open_p
    if is_above and is_green:
        return {"label": "▲ STRONG BUY", "color": "#00CC66", "status": "buy", "bg": "rgba(0, 204, 102, 0.15)"}
    elif is_above:
        return {"label": "▲ BUY", "color": "#00CC66", "status": "buy", "bg": "rgba(0, 204, 102, 0.08)"}
    elif not is_above and not is_green:
        return {"label": "▼ STRONG SELL", "color": "#FF3333", "status": "sell", "bg": "rgba(255, 51, 51, 0.15)"}
    else:
        return {"label": "▼ SELL", "color": "#FF3333", "status": "sell", "bg": "rgba(255, 51, 51, 0.08)"}

def calculate_confidence(abs_dist: float, body_gt_wick: bool, abs_dist_200: float) -> int:
    score = 100 - (abs_dist / 5 * 60)
    if body_gt_wick: score += 20
    if abs_dist_200 is not None and abs_dist_200 < 5: score += 10
    return int(min(100, max(0, round(score))))

# ══════════════════════════════════════════
#  MOCK OHLC ENGINE (Replace with Live Feed)
# ══════════════════════════════════════════
def fetch_daily_candles(symbol: str) -> dict:
    np.random.seed(abs(hash(symbol)) % 10000)
    base_price = np.random.uniform(300, 2500)
    candles = []
    current_price = base_price
    for _ in range(250):
        open_p = current_price * np.random.uniform(0.98, 1.02)
        close = open_p * np.random.uniform(0.97, 1.03)
        high = max(open_p, close) * np.random.uniform(1.00, 1.02)
        low = min(open_p, close) * np.random.uniform(0.98, 1.00)
        volume = int(np.random.uniform(30000, 1500000))
        candles.append({"o": open_p, "h": high, "l": low, "c": close, "v": volume})
        current_price = close
    return {"ok": True, "candles": candles}

# ══════════════════════════════════════════
#  SCAN OPERATIONS PIPELINE
# ══════════════════════════════════════════
def run_prewatch_scan():
    results = []
    all_stocks = list(STOCK_UNIVERSE.items())
    
    prog_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, (sym, info) in enumerate(all_stocks):
        prog_bar.progress(int(((idx + 1) / len(all_stocks)) * 100))
        status_text.text(f"Scanning Data Engine: {sym} ({idx+1}/{len(all_stocks)})")
        
        res = fetch_daily_candles(sym)
        if res.get("ok") and len(res["candles"]) >= 5:
            candles = res["candles"]
            last_candle = candles[-1]
            volume = last_candle["v"]
            
            # EARLY RECONNAISSANCE FILTER: Skip if volume < 1L
            if volume < 100000: continue
                
            close_prices = [c["c"] for c in candles]
            ema20 = calculate_ema(close_prices, 20)
            ema200 = calculate_ema(close_prices, 200)
            
            if not ema20: continue
            ltp = last_candle["c"]
            if ltp < 300 or ltp > 6000: continue
                
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
                    "sym": sym, "sector": info["sector"], "ltp": ltp,
                    "ema20": ema20, "ema200": ema200, "dist_pct": dist_pct,
                    "abs_dist": abs_dist, "dist_200": dist_200, "abs_dist_200": abs_dist_200,
                    "body_gt_wick": body_gt_wick, "volume": volume, "vol_median": vol_median,
                    "last_candle": last_candle
                })
                
    prog_bar.empty()
    status_text.empty()
    st.session_state.ts_prewatch = sorted(results, key=lambda x: x["abs_dist"])
    st.session_state.ts_prewatch_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

# ══════════════════════════════════════════
#  NATIVE COMPATIBLE INTERFACE GENERATION
# ══════════════════════════════════════════
st.set_page_config(layout="wide")

st.markdown(
    """
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:20px;">
        <h1 style="margin:0; font-weight:800; letter-spacing:-1px;">🛡️ TRADE SENTRY — Prewatch Scanner v6.0</h1>
    </div>
    """, unsafe_allowed_html=True
)

# Control Action Header Strip
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
    col_info.markdown(
        f"<div style='padding-top:6px; font-size:13px;'>⏳ <b>Last Scanned:</b> {st.session_state.ts_prewatch_time} | "
        f"🎯 <b>Total Matches:</b> {len(st.session_state.ts_prewatch)} stocks</div>", 
        unsafe_allowed_html=True
    )
else:
    col_info.caption("Click Scan above to calculate setups nearest to the 20 EMA on daily charts.")

if st.session_state.ts_prewatch:
    # Sidebar Filters (Tuning Metrics Panel)
    st.sidebar.header("🎯 Tuning & Filtering Matrix")
    filter_price = st.sidebar.number_input("Minimum Price (₹)", min_value=0.0, value=0.0, step=50.0)
    filter_volume = st.sidebar.number_input("Minimum Volume Size", min_value=0.0, value=0.0, step=50000.0)
    filter_ema20 = st.sidebar.number_input("Max Dist from EMA20 %", min_value=0.0, max_value=5.0, value=5.0, step=0.1)
    body_filter_on = st.sidebar.toggle("Filter Body > Wick (💪 STRONG)", value=True)
    
    sort_strategy = st.sidebar.radio("Sort Strategies Matrix:", ["Distance to EMA20", "Absolute Volume Size", "Confidence Score"])

    # Processing UI Filtering Pipeline Engine
    raw_data = st.session_state.ts_prewatch
    filtered_data = []
    
    for r in raw_data:
        if filter_price and r["ltp"] < filter_price: continue
        if filter_volume and r["volume"] < filter_volume: continue
        if r["abs_dist"] > filter_ema20: continue
        if body_filter_on and not r["body_gt_wick"]: continue
        filtered_data.append(r)

    # Sector Horizontal Navigation Distribution Selection
    available_sectors = sorted(list(set([x["sector"] for x in filtered_data])))
    sector_selection = st.pills("Filter Matrix by Sector Footprint:", ["ALL"] + available_sectors, default="ALL")
    
    if sector_selection != "ALL":
        filtered_data = [x for x in filtered_data if x["sector"] == sector_selection]

    # Structural Enrichment Setup Conversion Loop
    processed_cards_list = []
    for r in filtered_data:
        sig = calculate_signals(r["ltp"], r["ema20"], r["last_candle"]["c"], r["last_candle"]["o"])
        v_strength = get_volume_strength(r["volume"], r["vol_median"])
        conf = calculate_confidence(r["abs_dist"], r["body_gt_wick"], r["abs_dist_200"])
        processed_cards_list.append({**r, "sig": sig, "v_strength": v_strength, "confidence": conf})

    # Sort Operations Executer
    if sort_strategy == "Distance to EMA20":
        processed_cards_list.sort(key=lambda x: x["abs_dist"])
    elif sort_strategy == "Absolute Volume Size":
        processed_cards_list.sort(key=lambda x: x["volume"], reverse=True)
    elif sort_strategy == "Confidence Score":
        processed_cards_list.sort(key=lambda x: x["confidence"], reverse=True)

    # ══════════════════════════════════════════
    #  ACTION BANNER: WATCHLIST STORAGE ENGINE
    # ══════════════════════════════════════════
    st.markdown("<br>", unsafe_allowed_html=True)
    with st.container(border=True):
        st.markdown("<h4 style='margin-top:0;'>📦 Batch Inject Watchlist Management Panel</h4>", unsafe_allowed_html=True)
        w_col1, w_col2 = st.columns([4, 3])
        with w_col1:
            target_list_id = st.selectbox("Select Target Database Watchlist Bucket Location:", ["Today", "Yesterday", "New"])
        with w_col2:
            # Replaced bad padding element with native clean Streamlit button alignment architecture
            if st.button("➕ ADD STOCKS TO SELECTED WATCHLIST", use_container_width=True, type="secondary"):
                if not processed_cards_list:
                    st.warning("No processing stocks found matching parameters to add.")
                else:
                    if target_list_id not in st.session_state.watchlist_data:
                        st.session_state.watchlist_data[target_list_id] = []
                    
                    added_counter = 0
                    for item in processed_cards_list:
                        clean_sym = f"{item['sym']}.NS" if "." not in item['sym'] else item['sym']
                        trade_dir = "SELL" if item["sig"]["status"] == "sell" else "BUY"
                        
                        already_present = any(x["symbol"] == clean_sym and x["direction"] == trade_dir for x in st.session_state.watchlist_data[target_list_id])
                        if not already_present:
                            st.session_state.watchlist_data[target_list_id].append({
                                "symbol": clean_sym, "direction": trade_dir, "exchange": "NS",
                                "sector": item["sector"], "status": "WATCHING"
                            })
                            added_counter += 1
                    st.toast(f"✅ Injected {added_counter} Trade Targets to Watchlist Matrix bucket [{target_list_id}]!", icon="⚡")

    # ══════════════════════════════════════════
    #  ADAPTIVE SYSTEM STYLE CARDS LAYOUT DESIGN
    # ══════════════════════════════════════════
    st.markdown(f"### 📊 Showing {len(processed_cards_list)} of {len(raw_data)} Scanned Securities Setup Options")
    
    if not processed_cards_list:
        st.info("No stock setups configured in this screen view bucket context frame.")
    else:
        # Display structures dynamically inside balanced 3-Column viewport wrappers
        cols_per_row = 3
        for i in range(0, len(processed_cards_list), cols_per_row):
            batch_chunk = processed_cards_list[i:i + cols_per_row]
            grid_cols = st.columns(cols_per_row)
            
            for index, stock in enumerate(batch_chunk):
                with grid_cols[index]:
                    # Build Dynamic Inline Badges
                    badge_str = "⭐ VERY NEAR" if stock["abs_dist"] <= 1.0 else ""
                    if stock["body_gt_wick"]:
                        badge_str += " | 💪 STRONG BODY" if badge_str else "💪 STRONG BODY"
                    
                    # Native-adaptive styled component container logic
                    st.markdown(
                        f"""
                        <div style="
                            padding: 18px; 
                            border-radius: 10px; 
                            border: 1px solid rgba(128, 128, 128, 0.25); 
                            background-color: {stock['sig']['bg']};
                            margin-bottom: 5px;
                            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
                        ">
                            <div style="display:flex; justify-content:between; align-items:flex-start; width:100%;">
                                <div style="flex-grow:1;">
                                    <h3 style="margin:0; font-size:18px; font-weight:700; letter-spacing:-0.5px;">{stock['sym']}</h3>
                                    <span style="font-size:11px; color:gray; font-weight:600; text-transform:uppercase;">{stock['sector']}</span>
                                </div>
                                <div style="
                                    background: {stock['sig']['color']}; 
                                    color: #000; 
                                    padding: 4px 8px; 
                                    border-radius: 4px; 
                                    font-size: 11px; 
                                    font-weight: 800;
                                    text-align: right;
                                ">
                                    {stock['sig']['label']}
                                </div>
                            </div>
                            <div style="margin: 6px 0; font-size:11px; color:#FF8800; font-weight:bold;">
                                {badge_str if badge_str else '• NORMAL SETUP DISTANCE'}
                            </div>
                            <hr style="margin:10px 0; opacity:0.15;">
                            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; font-size:13px; margin-bottom:10px;">
                                <div><span style="color:gray;">EMA20 Dist:</span> <b style="color:{stock['sig']['color']}">{stock['dist_pct']:.2f}%</b></div>
                                <div><span style="color:gray;">200EMA:</span> <b>{f"{stock['dist_200']:.1f}%" if stock['dist_200'] is not None else '—'}</b></div>
                                <div><span style="color:gray;">CMP:</span> <b>₹{stock['ltp']:.2f}</b></div>
                                <div><span style="color:gray;">Volume:</span> <b>{format_volume_indian(stock['volume'])}</b></div>
                            </div>
                            <div style="font-size:12px; padding:6px 8px; background:rgba(128,128,128,0.08); border-radius:4px; margin-bottom:8px;">
                                <span style="color:gray;">Vol Strength:</span> <b style="color:{stock['v_strength']['color']}">{stock['v_strength']['label']} ({stock['v_strength']['ratio']:.2f}x)</b>
                            </div>
                        </div>
                        """, 
                        unsafe_allowed_html=True
                    )
                    # Confidence slider metric bar
                    st.progress(stock["confidence"] / 100, text=f"Setup Confidence Rank: {stock['confidence']}%")
else:
    st.warning("No prewatch matrix cache records found. Initialize database scan sequences.")
