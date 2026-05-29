import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# Import your master dictionary universe from your file
try:
    from stocks import STOCK_UNIVERSE
except ImportError:
    # Safe structural fallback if file is temporarily disconnected
    STOCK_UNIVERSE = {
        "RELIANCE": {"sector": "NIFTY ENERGY"},
        "TCS": {"sector": "NIFTY IT"},
        "HEROMOTOCO": {"sector": "NIFTY AUTO"},
        "JYOTICNC": {"sector": "NIFTY CAPITAL GOODS"}
    }

# Initialize Session States for Multi-page synchronization
if "ts_prewatch" not in st.session_state:
    st.session_state.ts_prewatch = None
if "ts_prewatch_time" not in st.session_state:
    st.session_state.ts_prewatch_time = None
if "watchlist_data" not in st.session_state:
    st.session_state.watchlist_data = {}

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
        return {"label": "🔴 Weak", "ratio": 0.0}
    ratio = current_vol / median_vol
    if ratio > 2.0: return {"label": "🔥 Explosive", "ratio": ratio}
    if ratio > 1.5: return {"label": "🟢 Strong", "ratio": ratio}
    if ratio > 1.0: return {"label": "🟡 Build", "ratio": ratio}
    return {"label": "🔴 Weak", "ratio": ratio}

def calculate_signals(ltp: float, ema20: float, close: float, open_p: float) -> dict:
    is_above = ltp > ema20
    is_green = close > open_p
    if is_above and is_green:
        return {"label": "▲ STRONG BUY", "status": "buy"}
    elif is_above:
        return {"label": "▲ BUY", "status": "buy"}
    elif not is_above and not is_green:
        return {"label": "▼ STRONG SELL", "status": "sell"}
    else:
        return {"label": "▼ SELL", "status": "sell"}

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
        status_text.text(f"Scanning Data Engine from stocks.py: {sym} ({idx+1}/{len(all_stocks)})")
        
        res = fetch_daily_candles(sym)
        if res.get("ok") and len(res["candles"]) >= 5:
            candles = res["candles"]
            last_candle = candles[-1]
            volume = last_candle["v"]
            
            close_prices = [c["c"] for c in candles]
            ema20 = calculate_ema(close_prices, 20)
            ema200 = calculate_ema(close_prices, 200)
            
            if not ema20: continue
            ltp = last_candle["c"]
            
            dist_pct = ((ltp - ema20) / ema20) * 100
            abs_dist = abs(dist_pct)
            dist_200 = ((ltp - ema200) / ema200) * 100 if ema200 else None
            abs_dist_200 = abs(dist_200) if dist_200 is not None else None
            
            body = abs(last_candle["c"] - last_candle["o"])
            wick = (last_candle["h"] - last_candle["l"]) - body
            body_gt_wick = body > wick
            vol_median = calculate_volume_median([c["v"] for c in candles])
            
            results.append({
                "sym": sym, "sector": info.get("sector", "GENERAL SECTOR"), "ltp": ltp,
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

st.title("🛡️ TRADE SENTRY — Prewatch Scanner v6.0")

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
        f"**Last Scanned:** {st.session_state.ts_prewatch_time} | **Total Universe Scanned:** {len(st.session_state.ts_prewatch)} stocks"
    )
else:
    col_info.caption(f"Click Scan above to analyze the active stock catalog loaded from stocks.py ({len(STOCK_UNIVERSE)} records found).")

# ══════════════════════════════════════════
#  IN-PAGE TUNING & FILTERING MATRIX CONTROL PANEL
# ══════════════════════════════════════════
st.markdown("### 🎯 Refining Matrix Configuration")
with st.container(border=True):
    f_col1, f_col2, f_col3, f_col4 = st.columns(4)
    
    with f_col1:
        filter_price = st.number_input("Minimum Price (₹)", min_value=0.0, value=0.0, step=50.0)
        body_filter_on = st.toggle("Filter Body > Wick (💪 STRONG)", value=False)
        
    with f_col2:
        filter_volume = st.number_input("Minimum Volume Size", min_value=0.0, value=0.0, step=50000.0)
        
    with f_col3:
        filter_ema20 = st.number_input("Max Dist from EMA20 %", min_value=0.0, max_value=100.0, value=5.0, step=0.5)
        
    with f_col4:
        sort_strategy = st.radio("Sort Strategies Matrix:", ["Distance to EMA20", "Absolute Volume Size", "Confidence Score"], horizontal=False)

if st.session_state.ts_prewatch:
    # Processing Filtering Matrix Pipeline Engine
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
    st.markdown("---")
    with st.container(border=True):
        st.markdown("#### 📦 Batch Inject Watchlist Management Panel")
        w_col1, w_col2 = st.columns([4, 3])
        with w_col1:
            target_list_id = st.selectbox("Select Target Database Watchlist Bucket Location:", ["Today", "Yesterday", "New"])
        with w_col2:
            st.write(" ")  # Elegant native vertical layout separator spacing
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
    #  NATIVE STABLE METRIC CARDS PRESENTATION 
    # ══════════════════════════════════════════
    st.subheader(f"📊 Showing {len(processed_cards_list)} of {len(raw_data)} Scanned Securities Setup Options")
    
    if not processed_cards_list:
        st.info("No stock setups configured in this screen view bucket context frame matching your filters.")
    else:
        # Render clean containers using safe columns layout architecture
        cols_per_row = 3
        for i in range(0, len(processed_cards_list), cols_per_row):
            batch_chunk = processed_cards_list[i:i + cols_per_row]
            grid_cols = st.columns(cols_per_row)
            
            for index, stock in enumerate(batch_chunk):
                with grid_cols[index]:
                    with st.container(border=True):
                        # Header Row
                        header_left, header_right = st.columns([2, 1.2])
                        header_left.markdown(f"### {stock['sym']}")
                        header_left.caption(f"📁 {stock['sector']}")
                        header_right.button(stock['sig']['label'], key=f"sig_{stock['sym']}_{i}_{index}", disabled=True, use_container_width=True)
                        
                        # System Tags
                        badges = []
                        if stock["abs_dist"] <= 1.0:
                            badges.append("⭐ VERY NEAR")
                        if stock["body_gt_wick"]:
                            badges.append("💪 STRONG BODY")
                        
                        if badges:
                            st.markdown(f"**{' | '.join(badges)}**")
                        
                        st.markdown("---")
                        
                        # Market Metrics Grid
                        m_col1, m_col2 = st.columns(2)
                        m_col1.metric("CMP", f"₹{stock['ltp']:.2f}")
                        m_col1.metric("EMA20 Dist", f"{stock['dist_pct']:.2f}%")
                        
                        m_col2.metric("Volume", format_volume_indian(stock['volume']))
                        m_col2.metric("200EMA Dist", f"{stock['dist_200']:.1f}%" if stock['dist_200'] is not None else "—")
                        
                        # Vol strength status block
                        st.info(f"📊 Vol Strength: {stock['v_strength']['label']} ({stock['v_strength']['ratio']:.2f}x)")
                        
                        # Confidence indicator bar
                        st.progress(stock["confidence"] / 100, text=f"Setup Confidence: {stock['confidence']}%")
else:
    if st.session_state.ts_prewatch is None:
        st.warning("No prewatch matrix cache records found. Initialize database scan sequences by clicking 'SCAN DAILY EMA'.")
