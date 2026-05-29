import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime

# ══════════════════════════════════════════
#  EXTERNAL MODULE & BACKEND INTEGRATION
# ══════════════════════════════════════════
try:
    import yfinance as tf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# Import your master dictionary universe containing your official tokens
try:
    from stocks import STOCK_UNIVERSE
except ImportError:
    # Fallback structure with placeholder Angel One tokens if file link breaks
    STOCK_UNIVERSE = {
        "RELIANCE": {"sector": "NIFTY ENERGY", "token": "2885"},
        "TCS": {"sector": "NIFTY IT", "token": "11536"},
        "HEROMOTOCO": {"sector": "NIFTY AUTO", "token": "1348"},
        "JYOTICNC": {"sector": "NIFTY CAPITAL GOODS", "token": "19485"},
        "GMDC": {"sector": "NIFTY METALS", "token": "10174"},
        "ADANIENT": {"sector": "NIFTY ENERGY", "token": "25"},
        "WELCORP": {"sector": "NIFTY METALS", "token": "11369"},
        "NAVINFLUOR": {"sector": "NIFTY CHEM", "token": "14144"}
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
        return {"label": "🔴 Weak", "ratio": 0.0, "color": "#FF4B4B"}
    ratio = current_vol / median_vol
    if ratio > 2.0: return {"label": "🔥 Explosive", "ratio": ratio, "color": "#FF9900"}
    if ratio > 1.5: return {"label": "🟢 Strong", "ratio": ratio, "color": "#00AA3B"}
    if ratio > 1.0: return {"label": "🟡 Build", "ratio": ratio, "color": "#B36200"}
    return {"label": "🔴 Weak", "ratio": ratio, "color": "#D32F2F"}

def calculate_signals(ltp: float, ema20: float, close: float, open_p: float) -> dict:
    is_above = ltp > ema20
    is_green = close > open_p
    if is_above and is_green:
        return {"label": "▲ STRONG BUY", "color": "#00AA3B", "bg": "rgba(0,170,59,0.1)", "status": "buy"}
    elif is_above:
        return {"label": "▲ BUY", "color": "#00AA3B", "bg": "rgba(0,170,59,0.1)", "status": "buy"}
    elif not is_above and not is_green:
        return {"label": "▼ STRONG SELL", "color": "#D32F2F", "bg": "rgba(211,47,47,0.1)", "status": "sell"}
    else:
        return {"label": "▼ SELL", "color": "#D32F2F", "bg": "rgba(211,47,47,0.1)", "status": "sell"}

def calculate_confidence(abs_dist: float, body_gt_wick: bool, abs_dist_200: float) -> int:
    score = 100 - (abs_dist / 5 * 60)
    if body_gt_wick: score += 20
    if abs_dist_200 is not None and abs_dist_200 < 5: score += 10
    return int(min(100, max(0, round(score))))

# ══════════════════════════════════════════
#  LIVE DATA CONNECTOR (ANGEL ONE + YFINANCE)
# ══════════════════════════════════════════
def fetch_daily_candles(symbol: str, info: dict) -> dict:
    """
    Attempts to pull data via live Angel One connection from app.py context.
    If unavailable, it transparently falls back to Yahoo Finance historical pipelines.
    """
    # ---- PIPELINE 1: TRY LIVE ANGEL ONE BACKEND ----
    if "smartApi" in globals() or hasattr(st, "session_state") and any("smartApi" in k for k in st.session_state.keys()):
        try:
            # Safely grab smartApi instance context
            api_obj = globals().get("smartApi") or st.session_state.get("smartApi")
            token = info.get("token")
            
            if api_obj and token:
                params = {
                    "exchange": "NSE",
                    "symboltoken": str(token),
                    "interval": "ONE_DAY",
                    "fromdate": (pd.Timestamp.now() - pd.Timedelta(days=365)).strftime("%Y-%m-%d %H:%M"),
                    "todate": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                }
                response = api_obj.getHistoricData(params)
                if response.get("status") and response.get("data"):
                    candles = []
                    for row in response["data"]:
                        # Angel One format: [Datetime, Open, High, Low, Close, Volume]
                        candles.append({
                            "o": float(row[1]), "h": float(row[2]),
                            "l": float(row[3]), "c": float(row[4]), "v": int(row[5])
                        })
                    return {"ok": True, "candles": candles, "source": "Angel One"}
        except Exception:
            pass # Suppress and bubble straight down to fallback engine

    # ---- PIPELINE 2: FALLBACK TO LIVE YAHOO FINANCE ----
    if YFINANCE_AVAILABLE:
        try:
            ns_ticker = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
            ticker_obj = tf.Ticker(ns_ticker)
            df = ticker_obj.history(period="1y", interval="1d")
            
            if not df.empty and len(df) >= 5:
                candles = []
                for idx, row in df.iterrows():
                    candles.append({
                        "o": float(row["Open"]), "h": float(row["High"]),
                        "l": float(row["Low"]), "c": float(row["Close"]), "v": int(row["Volume"])
                    })
                return {"ok": True, "candles": candles, "source": "Yahoo Finance"}
        except Exception as e:
            return {"ok": False, "error": f"Data connection dropped: {str(e)}"}
            
    return {"ok": False, "error": "No operational market data engine active."}

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
        status_text.text(f"Querying Core Feed for: {sym} ({idx+1}/{len(all_stocks)})")
        
        res = fetch_daily_candles(sym, info)
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
                "last_candle": last_candle, "source": res.get("source", "Live")
            })
                
    prog_bar.empty()
    status_text.empty()
    st.session_state.ts_prewatch = sorted(results, key=lambda x: x["abs_dist"])
    st.session_state.ts_prewatch_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

# ══════════════════════════════════════════
#  INTERFACE LAYOUT ENGINE
# ══════════════════════════════════════════
st.set_page_config(layout="wide")

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

# Scanned Counter Metric Setup
total_scanned_count = len(st.session_state.ts_prewatch) if st.session_state.ts_prewatch else 0
scan_time_str = st.session_state.ts_prewatch_time if st.session_state.ts_prewatch_time else "None"

col_info.markdown(
    f"<div style='padding-top: 6px; font-size: 13px; color: #444444;'>"
    f"⏳ <b>Last Scanned:</b> <span style='color:#000000; font-weight:700;'>{scan_time_str}</span> | "
    f"🎯 <b>Total Stocks Scanned:</b> <span style='color:#000000; font-weight:700;'>{total_scanned_count}</span>"
    f"</div>",
    unsafe_allow_html=True
)

# ══════════════════════════════════════════
#  TUNING & FILTERING MATRIX CONTROL PANEL
# ══════════════════════════════════════════
st.markdown("<h3 style='font-size: 15px; font-weight: 700; margin-top: 20px; color: #000000;'>⚙️ REFINEMENT OPTIONS</h3>", unsafe_allow_html=True)
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
    raw_data = st.session_state.ts_prewatch
    filtered_data = []
    
    for r in raw_data:
        if filter_price and r["ltp"] < filter_price: continue
        if filter_volume and r["volume"] < filter_volume: continue
        if r["abs_dist"] > filter_ema20: continue
        if body_filter_on and not r["body_gt_wick"]: continue
        filtered_data.append(r)

    # Filter Sector Configuration
    available_sectors = sorted(list(set([x["sector"] for x in filtered_data])))
    sector_selection = st.pills("Filter Matrix by Sector Footprint:", ["ALL"] + available_sectors, default="ALL")
    
    if sector_selection != "ALL":
        filtered_data = [x for x in filtered_data if x["sector"] == sector_selection]

    processed_cards_list = []
    for r in filtered_data:
        sig = calculate_signals(r["ltp"], r["ema20"], r["last_candle"]["c"], r["last_candle"]["o"])
        v_strength = get_volume_strength(r["volume"], r["vol_median"])
        conf = calculate_confidence(r["abs_dist"], r["body_gt_wick"], r["abs_dist_200"])
        processed_cards_list.append({**r, "sig": sig, "v_strength": v_strength, "confidence": conf})

    if sort_strategy == "Distance to EMA20":
        processed_cards_list.sort(key=lambda x: x["abs_dist"])
    elif sort_strategy == "Absolute Volume Size":
        processed_cards_list.sort(key=lambda x: x["volume"], reverse=True)
    elif sort_strategy == "Confidence Score":
        processed_cards_list.sort(key=lambda x: x["confidence"], reverse=True)

    # ══════════════════════════════════════════
    #  ACTION BANNER: WATCHLIST STORAGE ENGINE
    # ══════════════════════════════════════════
    st.markdown("<div style='margin-top:15px;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<h4 style='margin:0; font-size:15px; color:#000000;'>📦 Batch Inject Watchlist Management Panel</h4>", unsafe_allow_html=True)
        w_col1, w_col2 = st.columns([4, 3])
        with w_col1:
            target_list_id = st.selectbox("Select Target Database Watchlist Bucket Location:", ["Today", "Yesterday", "New"])
        with w_col2:
            st.markdown("<div style='margin-top:24px;'></div>", unsafe_allow_html=True)
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

    st.markdown(f"<h3 style='font-size: 15px; font-weight: 700; margin-top: 25px; color: #000000;'>📊 Showing {len(processed_cards_list)} of {len(raw_data)} Scanned Securities</h3>", unsafe_allow_html=True)
    
    if not processed_cards_list:
        st.info("No stock setups configured matching filters.")
    else:
        # ════════════════════════════════════════════════════════════════════════
        #  UI/UX VIEWPORT ENGINE - LIVE LIGHT MODE VISIBILITY MATRIX
        # ════════════════════════════════════════════════════════════════════════
        for stock in processed_cards_list:
            with st.container(border=True):
                head_left, head_right = st.columns([8, 4])
                
                with head_left:
                    clean_sector = stock['sector'].replace('NIFTY ', '')
                    
                    near_badge = ""
                    if stock["abs_dist"] <= 1.0:
                        near_badge = "<span style='background: rgba(255,153,0,0.12); color: #B36200; font-size: 11px; padding: 3px 8px; border-radius: 4px; font-weight: 700; border: 1px solid rgba(255,153,0,0.3); text-transform: uppercase; white-space: nowrap;'>⭐ Near</span>"
                        
                    strong_badge = ""
                    if stock["body_gt_wick"]:
                        strong_badge = "<span style='background: rgba(0,204,71,0.12); color: #007A2B; font-size: 11px; padding: 3px 8px; border-radius: 4px; font-weight: 700; border: 1px solid rgba(0,204,71,0.3); text-transform: uppercase; white-space: nowrap;'>💪 Strong Body</span>"
                    
                    badges_html = ""
                    if near_badge or strong_badge:
                        badges_html = f"<div style='display: flex; gap: 8px; align-items: center;'>{near_badge}{strong_badge}</div>"
                    
                    st.markdown(
                        f"""
                        <div style='display: flex; align-items: center; gap: 12px; width: 100%; max-width: 650px;'>
                            <div style='min-width: 130px;'>
                                <span style='font-size: 22px; font-weight: 800; color: #1E1E1E; letter-spacing: -0.3px;'>{stock['sym']}</span>
                            </div>
                            <span style='font-size: 18px; color: rgba(0,0,0,0.15); font-weight: 300;'>|</span>
                            <div style='min-width: 140px; display: flex; align-items: center;'>
                                <span style='font-size: 12px; color: #000000; font-weight: 700; letter-spacing: 0.3px; text-transform: uppercase;'>📁 {clean_sector}</span>
                            </div>
                            {badges_html}
                            <span style='font-size: 10px; color: #888888; background: #f1f1f1; padding: 1px 5px; border-radius:3px;'>{stock.get('source', 'Live')}</span>
                        </div>
                        """, unsafe_allow_html=True
                    )
                
                with head_right:
                    st.markdown(
                        f"""
                        <div style='text-align: right; padding-top: 4px;'>
                            <span style='background: {stock['sig']['bg']}; color: {stock['sig']['color']}; font-size: 11px; font-weight: 900; padding: 4px 12px; border-radius: 4px; border: 1px solid {stock['sig']['color']}33; letter-spacing: 0.5px;'>
                                {stock['sig']['label']}
                            </span>
                        </div>
                        """, unsafe_allow_html=True
                    )
                
                st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)
                m_col1, m_col2, m_col3, m_col4, vol_analysis_col = st.columns([2.0, 2.0, 2.0, 2.0, 4.0])
                
                with m_col1:
                    m1_color = "#00AA3B" if stock['dist_pct'] >= 0 else "#D32F2F"
                    m1_sign = "▲" if stock['dist_pct'] >= 0 else "▼"
                    st.markdown(f"<span style='font-size: 11px; color: #000000; font-weight: 700; letter-spacing: 0.3px;'>EMA20 DIST</span>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size: 20px; font-weight: 700; color: {m1_color}; margin-top: 2px;'>{m1_sign} {abs(stock['dist_pct']):.2f}%</div>", unsafe_allow_html=True)
                
                with m_col2:
                    dist_200_val = stock['dist_200']
                    if dist_200_val is not None:
                        m2_color = "#00AA3B" if dist_200_val >= 0 else "#D32F2F"
                        m2_sign = "▲" if dist_200_val >= 0 else "▼"
                        m2_html = f"<span style='color: {m2_color};'>{m2_sign} {abs(dist_200_val):.1f}%</span>"
                    else:
                        m2_html = "<span style='color: #888888;'>—</span>"
                        
                    st.markdown(f"<span style='font-size: 11px; color: #000000; font-weight: 700; letter-spacing: 0.3px;'>200EMA DIST</span>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size: 20px; font-weight: 700; margin-top: 2px;'>{m2_html}</div>", unsafe_allow_html=True)
                
                with m_col3:
                    st.markdown(f"<span style='font-size: 11px; color: #000000; font-weight: 700; letter-spacing: 0.3px;'>CMP</span>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size: 20px; font-weight: 700; color: #1E1E1E; margin-top: 2px;'>₹{stock['ltp']:.2f}</div>", unsafe_allow_html=True)
                
                with m_col4:
                    st.markdown(f"<span style='font-size: 11px; color: #000000; font-weight: 700; letter-spacing: 0.3px;'>VOLUME</span>", unsafe_allow_html=True)
                    st.markdown(f"<div style='font-size: 20px; font-weight: 700; color: #1E1E1E; margin-top: 2px;'>{format_volume_indian(stock['volume'])}</div>", unsafe_allow_html=True)
                
                with vol_analysis_col:
                    st.markdown(
                        f"""
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; padding-left: 10px;'>
                            <span style='font-size: 11px; color: #000000; font-weight: 700; text-transform: uppercase;'>Volume Strength</span>
                            <span style='font-size: 12px; color: {stock['v_strength']['color']}; font-weight: 700;'>{stock['v_strength']['label']} ({stock['v_strength']['ratio']:.1f}x)</span>
                        </div>
                        """, unsafe_allow_html=True
                    )
                    st.progress(stock["confidence"] / 100, text=f"Confidence: {stock['confidence']}%")            
else:
    if st.session_state.ts_prewatch is None:
        st.warning("No prewatch matrix cache records found. Initialize database scan sequences by clicking 'SCAN DAILY EMA'.")
