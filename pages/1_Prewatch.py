import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import math
from datetime import datetime

# ══════════════════════════════════════════
#  EXTERNAL MODULE & BACKEND INTEGRATION
# ══════════════════════════════════════════
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

# Import your master universe functions and structural settings
try:
    from stocks import STOCK_UNIVERSE, get_stock_token, get_stock_sector
except ImportError:
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
    def get_stock_sector(sym):
        return STOCK_UNIVERSE.get(sym, {}).get("sector", "GENERAL")
    def get_stock_token(sym):
        return STOCK_UNIVERSE.get(sym, {}).get("token", None)

# Path Resolution matching Tradesentry architecture
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.json")
WATCHLIST_NAMES = ["Today", "Yesterday", "New"]

# ══════════════════════════════════════════
#  OFFICIAL STORAGE ACCESS FUNCTIONS
# ══════════════════════════════════════════
def load_all_watchlist_data() -> dict:
    if not os.path.exists(WATCHLIST_FILE):
        return {f"watchlist_{n}": [] for n in WATCHLIST_NAMES}
    try:
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    except:
        return {f"watchlist_{n}": [] for n in WATCHLIST_NAMES}

def save_all_watchlist_data(data: dict):
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        st.error(f"Failed to sync directly with watchlist database: {e}")

# Initialize Session States for Multi-page synchronization
if "ts_prewatch" not in st.session_state:
    st.session_state.ts_prewatch = None
if "ts_prewatch_time" not in st.session_state:
    st.session_state.ts_prewatch_time = None

# ══════════════════════════════════════════
#  CORE INDICATORS & MATHEMATICS LOGIC
# ══════════════════════════════════════════
def calculate_ema(prices: list, period: int) -> float:
    if len(prices) < period:
        return None
    prices_series = pd.Series(prices).dropna()
    if len(prices_series) < period:
        return None
    ema = prices_series.ewm(span=period, adjust=False).mean()
    val = ema.iloc[-1]
    if pd.isna(val) or math.isnan(val):
        return None
    return float(val)

def calculate_volume_median(volumes: list) -> float:
    clean_vols = [v for v in volumes if v is not None and not pd.isna(v) and not math.isnan(v)]
    if len(clean_vols) < 5:
        return None
    val = np.median(clean_vols[-5:])
    if pd.isna(val) or math.isnan(val):
        return None
    return float(val)

def format_volume_indian(vol: float) -> str:
    if not vol or pd.isna(vol) or math.isnan(vol) or vol == 0: return "0"
    if vol >= 10000000: return f"{vol / 10000000:.1f}Cr"
    if vol >= 100000: return f"{vol / 100000:.1f}L"
    if vol >= 1000: return f"{vol / 1000:.1f}K"
    return str(int(vol))

def get_volume_strength(current_vol: float, median_vol: float) -> dict:
    if not median_vol or pd.isna(median_vol) or math.isnan(median_vol) or median_vol == 0:
        return {"label": "🔴 WEAK", "ratio": 1.0, "color": "#FF4B4B"}
    ratio = current_vol / median_vol
    if ratio > 2.0: return {"label": "🔥 EXPLOSIVE", "ratio": ratio, "color": "#FF9900"}
    if ratio > 1.5: return {"label": "🟢 STRONG", "ratio": ratio, "color": "#00AA3B"}
    if ratio > 1.0: return {"label": "🟡 BUILD", "ratio": ratio, "color": "#B36200"}
    return {"label": "🔴 WEAK", "ratio": ratio, "color": "#FF4B4B"}

def calculate_signals(ltp: float, ema20: float, close: float, open_p: float) -> dict:
    is_above = ltp > ema20
    is_green = close > open_p
    if is_above and is_green:
        return {"label": "▲ STRONG BUY", "color": "#00AA3B", "bg": "rgba(0,170,59,0.08)"}
    elif is_above:
        return {"label": "▲ BUY", "color": "#00AA3B", "bg": "rgba(0,170,59,0.08)"}
    elif not is_above and not is_green:
        return {"label": "▼ STRONG SELL", "color": "#D32F2F", "bg": "rgba(211,47,47,0.08)"}
    else:
        return {"label": "▼ SELL", "color": "#D32F2F", "bg": "rgba(211,47,47,0.08)"}

def calculate_confidence(abs_dist: float, body_gt_wick: bool, abs_dist_200: float) -> int:
    if pd.isna(abs_dist) or math.isnan(abs_dist):
        abs_dist = 0.0
        
    if hasattr(abs_dist, "iloc"):
        abs_dist = float(abs_dist.iloc[-1])
    else:
        abs_dist = float(abs_dist)
        
    if abs_dist_200 is not None:
        if pd.isna(abs_dist_200) or math.isnan(abs_dist_200) or hasattr(abs_dist_200, "dropna"):
            abs_dist_200 = None
        elif hasattr(abs_dist_200, "iloc"):
            abs_dist_200 = float(abs_dist_200.iloc[-1])
        else:
            abs_dist_200 = float(abs_dist_200)

    score = 100.0 - (abs_dist * 2.0)
    
    if body_gt_wick: 
        score += 20.0
    if abs_dist_200 is not None and abs_dist_200 < 50.0: 
        score += 10.0
        
    if pd.isna(score) or math.isnan(score):
        return 50
        
    return int(min(100, max(0, round(float(score)))))

# ══════════════════════════════════════════
#  LIVE DATA CONNECTOR (ANGEL ONE + YFINANCE)
# ══════════════════════════════════════════
def fetch_daily_candles(symbol: str, info: dict) -> dict:
    if "smartApi" in globals() or hasattr(st, "session_state") and any("smartApi" in k for k in st.session_state.keys()):
        try:
            api_obj = globals().get("smartApi") or st.session_state.get("smartApi")
            token = info.get("token") or get_stock_token(symbol)
            
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
                        candles.append({
                            "o": float(row[1]), "h": float(row[2]),
                            "l": float(row[3]), "c": float(row[4]), "v": int(row[5])
                        })
                    return {"ok": True, "candles": candles, "source": "Angel One", "live_price": float(candles[-1]["c"])}
        except Exception:
            pass

    if YFINANCE_AVAILABLE:
        try:
            ns_ticker = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
            ticker_obj = yf.Ticker(ns_ticker)
            df = ticker_obj.history(period="1y", interval="1d")
            
            # Extract bulletproof realtime live CMP directly from Yahoo Fast-Info Object API
            fallback_cmp = None
            try:
                fallback_cmp = ticker_obj.fast_info.get("lastPrice") or ticker_obj.fast_info.get("last_price")
            except:
                pass

            if not df.empty:
                # Store the absolute latest row price before dropping potential partial data
                if fallback_cmp is None or pd.isna(fallback_cmp) or math.isnan(fallback_cmp):
                    fallback_cmp = df["Close"].iloc[-1]
                
                # Drop rows where critical mathematical tracking structures are empty
                df = df.dropna(subset=["Open", "High", "Low", "Close"])
                
                candles = []
                for idx, row in df.iterrows():
                    candles.append({
                        "o": float(row["Open"]), "h": float(row["High"]),
                        "l": float(row["Low"]), "c": float(row["Close"]), "v": int(row["Volume"])
                    })
                return {"ok": True, "candles": candles, "source": "Yahoo Finance", "live_price": float(fallback_cmp)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
            
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
        status_text.text(f"Scanning Ticker Feed: {sym} ({idx+1}/{len(all_stocks)})")
        
        res = fetch_daily_candles(sym, info)
        if res.get("ok") and len(res["candles"]) >= 5:
            candles = res["candles"]
            last_candle = candles[-1]
            volume = last_candle["v"]
            
            # --- MANDATORY 1 LAKH LIQUIDITY CONDITIONAL BLOCK ---
            if volume < 100000 or pd.isna(volume) or math.isnan(volume): 
                continue
                
            close_prices = [c["c"] for c in candles]
            ema20 = calculate_ema(close_prices, 20)
            ema200 = calculate_ema(close_prices, 200)
            
            # Inject Verified Realtime Live Price Engine mapping directly to CMP
            ltp = res.get("live_price")
            if ltp is None or pd.isna(ltp) or math.isnan(ltp):
                ltp = last_candle["c"]
                
            if ltp is None or pd.isna(ltp) or math.isnan(ltp):
                continue
            ltp = float(ltp)
            
            if ema20 is None: continue
            
            dist_pct = float(ema20)  
            abs_dist = float(abs(ltp - ema20))  
            abs_dist_200 = float(abs(ltp - ema200)) if ema200 is not None else None
            
            body = abs(last_candle["c"] - last_candle["o"])
            wick = (last_candle["h"] - last_candle["l"]) - body
            body_gt_wick = bool(body > wick)
            vol_median = calculate_volume_median([c["v"] for c in candles])
            
            results.append({
                "sym": sym, "sector": info.get("sector", "GENERAL SECTOR"), "ltp": ltp,
                "ema20": ema20, "ema200": ema200, "dist_pct": dist_pct,
                "abs_dist": abs_dist, "abs_dist_200": abs_dist_200,
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

# Action Controls
col_btn1, col_btn2, col_info = st.columns([1.5, 1.5, 5])
with col_btn1:
    if st.button("🔍 SCAN DAILY EMA", use_container_width=True, type="primary"):
        run_prewatch_scan()
with col_btn2:
    if st.button("🗑️ CLEAR SCAN DATA", use_container_width=True):
        st.session_state.ts_prewatch = None
        st.session_state.ts_prewatch_time = None
        st.rerun()

# Scanned Metrics Information Bar
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
#  FILTER & REFINEMENT MATRIX PANEL
# ══════════════════════════════════════════
st.markdown("<h3 style='font-size: 14px; font-weight: 700; margin-top: 15px; color: #000000; letter-spacing:0.5px;'>⚙️ REFINEMENT OPTIONS</h3>", unsafe_allow_html=True)
with st.container(border=True):
    f_col1, f_col2, f_col3, f_col4 = st.columns(4)
    with f_col1:
        filter_price = st.number_input("Minimum Price (₹)", min_value=0.0, value=0.0, step=50.0)
        body_filter_on = st.toggle("Filter Body > Wick (💪 STRONG)", value=False)
    with f_col2:
        filter_volume = st.number_input("Minimum Volume Size", min_value=0.0, value=0.0, step=50000.0)
    with f_col3:
        filter_ema20 = st.number_input("Max Dist from EMA20 (₹ Gap)", min_value=0.0, max_value=5000.0, value=15.0, step=1.0)
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

    processed_cards_list = []
    for r in filtered_data:
        sig = calculate_signals(r["ltp"], r["ema20"], r["last_candle"]["c"], r["last_candle"]["o"])
        v_strength = get_volume_strength(r["volume"], r["vol_median"])
        conf = calculate_confidence(r["abs_dist"], r["body_gt_wick"], r["abs_dist_200"])
        processed_cards_list.append({**r, "sig": sig, "v_strength": v_strength, "confidence": conf})
        
    # ════════════════════════════════════════════════════════════════════════
    #  MODIFICATION BLOCK: DYNAMIC SECTOR PILLS WITH COUNT
    # ════════════════════════════════════════════════════════════════════════
    # 1. Create a list of available (prefixed) sectors from STOCK_UNIVERSE
    available_sectors = sorted(list(set([info.get("sector", "GENERAL SECTOR") for sym, info in STOCK_UNIVERSE.items()])))

    # 2. Calculate current processed counts per sector footpring
    sector_counts = {}
    for r in processed_cards_list:
        sector_counts[r["sector"]] = sector_counts.get(r["sector"], 0) + 1
        
    # 3. Prepare display mapping: Prefixed Name -> Display Label (for Pills)
    pill_options = ["ALL"]
    display_label_to_prefixed = {} # To reverse map pill selection to prefixed sector key
    for sector in available_sectors:
        clean_name = sector.replace('NIFTY ', '')
        # Get count, default to 0 if no stocks pass filters in that sector
        count = sector_counts.get(sector, 0)
        label = f"{clean_name} ({count})"
        pill_options.append(label)
        # Store prefixed name as key for reverse lookup
        display_label_to_prefixed[label] = sector
            
    # 4. Use official Streamlit Pills component for sector filtering matrix
    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    sector_selection_label = st.pills("Filter Matrix by Sector Footprint:", pill_options, default="ALL")
    
    # 5. Handle user selection and perform final filtering logic before display viewport engine
    if sector_selection_label != "ALL":
        prefixed_selected_sector = display_label_to_prefixed.get(sector_selection_label)
        if prefixed_selected_sector:
            processed_cards_list = [x for x in processed_cards_list if x["sector"] == prefixed_selected_sector]

    # ... remaining sorting logic and display matrix continue as before ...

    if sort_strategy == "Distance to EMA20":
        processed_cards_list.sort(key=lambda x: x["abs_dist"])
    elif sort_strategy == "Absolute Volume Size":
        processed_cards_list.sort(key=lambda x: x["volume"], reverse=True)
    elif sort_strategy == "Confidence Score":
        processed_cards_list.sort(key=lambda x: x["confidence"], reverse=True)

    # ════════════════════════════════════════════════════════════════════════
    #  WATCHLIST BATCH INJECTOR PANEL — SYNCED DIRECTLY WITH WATCHLIST.JSON
    # ════════════════════════════════════════════════════════════════════════
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<h4 style='margin:0 0 10px 0; font-size:13px; color:#000000; font-weight:700;'>📦 Batch Inject Watchlist Management Panel</h4>", unsafe_allow_html=True)
        w_col1, w_col2 = st.columns([5, 3])
        
        with w_col1:
            # Dropdown options exact aapke main page ke teen tabs se match karne ke liye
            target_list_id = st.selectbox(
                "Select Target Database Watchlist Bucket Location:", 
                ["Today", "Yesterday", "New"], 
                label_visibility="collapsed"
            )
        
        with w_col2:
            if st.button("➕ ADD STOCKS TO SELECTED WATCHLIST", use_container_width=True, type="secondary"):
                if not processed_cards_list:
                    st.warning("No processing stocks found matching parameters to add.")
                else:
                    # 1. Load data directly from Tradesentry storage architecture file
                    current_json_db = load_all_watchlist_data()
                    
                    # 2. Map structural keys exactly to your system format ("watchlist_Today", etc.)
                    db_target_key = f"watchlist_{target_list_id}"
                    if db_target_key not in current_json_db:
                        current_json_db[db_target_key] = []
                    
                    added_counter = 0
                    for item in processed_cards_list:
                        clean_sym = item['sym'].replace(".NS", "").replace(".BO", "").upper().strip()
                        trade_dir = "SELL" if "SELL" in item["sig"]["label"] else "BUY"
                        
                        # Duplicate check taaki ek hi stock baar-baar add na ho
                        already_present = any(
                            x.get("symbol") == clean_sym and 
                            x.get("exchange") == "NS" and 
                            x.get("direction") == trade_dir 
                            for x in current_json_db[db_target_key]
                        )
                        
                        if not already_present:
                            # Row format mapping for table rendering engine
                            raw_ltp = item.get("ltp", 0.0)
                            if pd.isna(raw_ltp) or math.isnan(raw_ltp):
                                parsed_entry = 0.0
                            else:
                                parsed_entry = float(round(raw_ltp))

                            current_json_db[db_target_key].append({
                                "symbol": clean_sym,
                                "exchange": "NS",
                                "direction": trade_dir,
                                "entry": parsed_entry,
                                "sl": None,
                                "target1": None,
                                "target2": None,
                                "note": "EMA 20 Automated Scan",
                                "sector": get_stock_sector(clean_sym),
                                "status": "WATCHING",
                                "lastPrice": None,
                                "added_at": datetime.now().isoformat()
                            })
                            added_counter += 1
                    
                    if added_counter > 0:
                        save_all_watchlist_data(current_json_db)
                        st.toast(f"⚡ Injected {added_counter} Stocks directly into '{target_list_id}' Watchlist file!", icon="✅")
                    else:
                        st.info("Selected setups are already active inside that watchlist container.")

    st.markdown(f"<h3 style='font-size: 14px; font-weight: 700; margin-top: 20px; color: #000000;'>📊 Showing {len(processed_cards_list)} of {len(raw_data)} Scanned Securities</h3>", unsafe_allow_html=True)
    
    if not processed_cards_list:
        st.info("No stock setups configured matching filters.")
    else:
        # ════════════════════════════════════════════════════════════════════════
        #  UI/UX VIEWPORT ENGINE — OPTION 3 DYNAMIC GREEN/RED VISUAL INJECTOR
        # ════════════════════════════════════════════════════════════════════════
        for stock in processed_cards_list:
            with st.container(border=True):
                # Header Metadata Strip Layout
                h_left, h_right = st.columns([8, 4])
                with h_left:
                    clean_sector = stock['sector'].replace('NIFTY ', '')
                    near_badge = f"<span style='background: rgba(255,153,0,0.1); color: #B36200; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 700; border: 1px solid rgba(255,153,0,0.25); margin-left:10px;'>⭐ NEAR</span>" if stock["abs_dist"] <= 5.0 else ""
                    strong_badge = f"<span style='background: rgba(0,170,59,0.1); color: #007A2B; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 700; border: 1px solid rgba(0,170,59,0.25); margin-left:10px;'>💪 STRG</span>" if stock["body_gt_wick"] else ""
                    
                    st.markdown(
                        f"""
                        <div style='display: flex; align-items: center; gap: 8px;'>
                            <span style='font-size: 18px; font-weight: 800; color: #111111;'>{stock['sym']}</span>
                            <span style='font-size: 14px; color: #888888; font-weight: 400; margin-left: 5px;'>| &nbsp; 📁 {clean_sector}</span>
                            {near_badge}
                            {strong_badge}
                        </div>
                        """, unsafe_allow_html=True
                    )
                with h_right:
                    st.markdown(
                        f"""
                        <div style='text-align: right;'>
                            <span style='background: {stock['sig']['bg']}; color: {stock['sig']['color']}; font-size: 11px; font-weight: 800; padding: 3px 10px; border-radius: 4px; border: 1px solid {stock['sig']['color']}40; letter-spacing: 0.5px;'>
                                {stock['sig']['label']}
                            </span>
                        </div>
                        """, unsafe_allow_html=True
                    )
                
                st.markdown("<div style='margin-top: 10px; border-bottom: 1px solid #f0f0f0;'></div>", unsafe_allow_html=True)
                
                # Five-Column Financial Metrics Visual Matrix
                m1, m2, m3, m4, m5 = st.columns([2, 2, 2, 2, 4])
                
                with m1:
                    st.markdown("<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>20 EMA PRICE</p>", unsafe_allow_html=True)
                    # --- OPTION 3 COLOR LOGIC ENGINE ---
                    if stock['ltp'] >= stock['ema20']:
                        ema20_color = "#00AA3B"  
                        ema20_arrow = "▲ "
                    else:
                        ema20_color = "#D32F2F"  
                        ema20_arrow = "▼ "
                    st.markdown(f"<p style='font-size:16px; font-weight:700; color:{ema20_color}; margin:2px 0 0 0;'>{ema20_arrow}₹{stock['ema20']:.2f}</p>", unsafe_allow_html=True)
                
                with m2:
                    st.markdown("<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>200 EMA PRICE</p>", unsafe_allow_html=True)
                    if stock['ema200'] is not None and not math.isnan(stock['ema200']):
                        m2_html = f"<span style='color: #111111;'>₹{stock['ema200']:.2f}</span>"
                    else:
                        m2_html = "<span style='color: #888888;'>No Data (New Stock)</span>"
                    st.markdown(f"<p style='font-size:16px; font-weight:700; margin:2px 0 0 0;'>{m2_html}</p>", unsafe_allow_html=True)
                
                with m3:
                    st.markdown("<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>CMP</p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='font-size:16px; font-weight:700; color:#111111; margin:2px 0 0 0;'>₹{stock['ltp']:.2f}</p>", unsafe_allow_html=True)
                
                with m4:
                    st.markdown("<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>VOLUME</p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='font-size:16px; font-weight:700; color:#111111; margin:2px 0 0 0;'>{format_volume_indian(stock['volume'])}</p>", unsafe_allow_html=True)
                
                with m5:
                    st.markdown(
                        f"""
                        <div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;'>
                            <span style='font-size: 10px; color: #777777; font-weight: 700;'>VOL MATRIX:</span>
                            <span style='font-size: 11px; color: {stock['v_strength']['color']}; font-weight: 700;'>{stock['v_strength']['label']} ({stock['v_strength']['ratio']:.1f}x)</span>
                        </div>
                        """, unsafe_allow_html=True
                    )
                    st.progress(stock["confidence"] / 100, text=f"Setup Confidence: {stock['confidence']}%")
else:
    if st.session_state.ts_prewatch is None:
        st.warning("No prewatch matrix cache records found. Initialize database scan sequences by clicking 'SCAN DAILY EMA'.")
