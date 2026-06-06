import streamlit as st
import pandas as pd
import numpy as np
import os
import math
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ══════════════════════════════════════════
#  CORE ENGINE IMPORT
# ══════════════════════════════════════════
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core import calc_ema_from_series, load_watchlist, add_to_watchlist, insert_many_to_watchlist, get_user_watchlist_names
from styles import apply_styles, sidebar_brand, page_header

# ══════════════════════════════════════════
#  PAGE CONFIG — must be first st. call
# ══════════════════════════════════════════
st.set_page_config(
    page_title="Prewatch · TradeSentry",
    layout="wide",
    page_icon="🚀",
    initial_sidebar_state="expanded"
)

apply_styles()
sidebar_brand()
page_header("Prewatch", "Daily EMA Scanner")

# ══════════════════════════════════════════
#  EXTERNAL MODULE & BACKEND INTEGRATION
# ══════════════════════════════════════════
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    from stocks import STOCK_UNIVERSE, get_stock_token, get_stock_sector
except ImportError:
    STOCK_UNIVERSE = {
        "RELIANCE": {"sector": "NIFTY ENERGY", "token": "2885"},
        "TCS": {"sector": "NIFTY IT", "token": "11536"},
    }
    def get_stock_sector(sym): return STOCK_UNIVERSE.get(sym, {}).get("sector", "GENERAL")
    def get_stock_token(sym): return STOCK_UNIVERSE.get(sym, {}).get("token", None)

# ══════════════════════════════════════════
#  SESSION STATE
# ══════════════════════════════════════════
if "ts_prewatch" not in st.session_state: st.session_state.ts_prewatch = None
if "ts_prewatch_time" not in st.session_state: st.session_state.ts_prewatch_time = None

# ══════════════════════════════════════════
#  DYNAMIC WATCHLIST NAMES
# ══════════════════════════════════════════
try:
    WATCHLIST_NAMES = get_user_watchlist_names() if st.session_state.get("user_id") else ["Today", "Yesterday", "New"]
except Exception:
    WATCHLIST_NAMES = ["Today", "Yesterday", "New"]

# ══════════════════════════════════════════
#  CORE MATHEMATICS LOGIC
# ══════════════════════════════════════════

def calculate_volume_median(volumes: pd.Series) -> float:
    clean_vols = volumes.dropna().tail(5).tolist()
    if len(clean_vols) < 5: return None
    val = np.median(clean_vols)
    return None if (pd.isna(val) or math.isnan(val)) else float(val)

def format_volume_indian(vol: float) -> str:
    if not vol or pd.isna(vol) or math.isnan(vol) or vol == 0: return "0"
    if vol >= 10000000: return f"{vol / 10000000:.1f}Cr"
    if vol >= 100000: return f"{vol / 100000:.1f}L"
    if vol >= 1000: return f"{vol / 1000:.1f}K"
    return str(int(vol))

def get_volume_strength(current_vol: float, median_vol: float) -> dict:
    if not median_vol or median_vol == 0: return {"label": "🔴 WEAK", "ratio": 1.0, "color": "#FF4B4B"}
    ratio = current_vol / median_vol
    if ratio > 2.0: return {"label": "🔥 EXPLOSIVE", "ratio": ratio, "color": "#FF9900"}
    if ratio > 1.5: return {"label": "🟢 STRONG", "ratio": ratio, "color": "#00AA3B"}
    if ratio > 1.0: return {"label": "🟡 BUILD", "ratio": ratio, "color": "#B36200"}
    return {"label": "🔴 WEAK", "ratio": ratio, "color": "#FF4B4B"}

def calculate_signals(ltp: float, ema20: float, close: float, open_p: float) -> dict:
    is_above = ltp > ema20
    is_green = close > open_p
    if is_above and is_green: return {"label": "▲ STRONG BUY", "color": "#00AA3B", "bg": "rgba(0,170,59,0.08)"}
    elif is_above: return {"label": "▲ BUY", "color": "#00AA3B", "bg": "rgba(0,170,59,0.08)"}
    elif not is_above and not is_green: return {"label": "▼ STRONG SELL", "color": "#D32F2F", "bg": "rgba(211,47,47,0.08)"}
    else: return {"label": "▼ SELL", "color": "#D32F2F", "bg": "rgba(211,47,47,0.08)"}

def calculate_confidence(abs_dist_pct: float, body_gt_wick: bool, abs_dist_200: float) -> int:
    score = 100.0 - (float(abs_dist_pct) * 10.0)
    if body_gt_wick: score += 20.0
    if abs_dist_200 is not None and abs_dist_200 < 50.0: score += 10.0
    return int(min(100, max(0, round(score))))

# ══════════════════════════════════════════
#  HIGH SPEED LIGHTNING ENGINE PIPELINE
# ══════════════════════════════════════════
def run_fast_prewatch_scan():
    results = []
    all_stocks = list(STOCK_UNIVERSE.items())

    status_text = st.empty()
    status_text.text("⚡ Activating High-Speed Engine Batch Downloads...")

    api_obj = globals().get("smartApi") or st.session_state.get("smartApi")

    if api_obj:
        status_text.text("🔌 Processing Parallel Worker Streams (Angel One)...")
        def fetch_angel_data(symbol, info):
            try:
                token = info.get("token") or get_stock_token(symbol)
                if token:
                    params = {
                        "exchange": "NSE", "symboltoken": str(token), "interval": "ONE_DAY",
                        "fromdate": (pd.Timestamp.now() - pd.Timedelta(days=365)).strftime("%Y-%m-%d %H:%M"),
                        "todate": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
                    }
                    res = api_obj.getHistoricData(params)
                    if res.get("status") and res.get("data"):
                        df_stock = pd.DataFrame(res["data"], columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
                        for col in ["Open", "High", "Low", "Close", "Volume"]:
                            df_stock[col] = pd.to_numeric(df_stock[col], errors='coerce')
                        return symbol, df_stock, df_stock["Close"].iloc[-1]
            except: pass
            return symbol, None, None

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(fetch_angel_data, sym, info) for sym, info in all_stocks]
            for fut in as_completed(futures):
                sym, df_stock, live_p = fut.result()
                if df_stock is not None and len(df_stock) >= 5:
                    process_individual_dataframe(sym, df_stock, live_p, results)

    elif YFINANCE_AVAILABLE:
        try:
            ticker_map = {f"{sym}.NS": sym for sym, _ in all_stocks}
            ticker_space_string = " ".join(ticker_map.keys())
            bulk_df = yf.download(ticker_space_string, period="2y", interval="1d", group_by='ticker', auto_adjust=False, progress=False)
            for ns_ticker, sym in ticker_map.items():
                if ns_ticker in bulk_df.columns.levels[0]:
                    df_stock = bulk_df[ns_ticker].dropna(subset=["Close"])
                    if not df_stock.empty and len(df_stock) >= 5:
                        try: live_p = float(df_stock["Close"].iloc[-1])
                        except: live_p = None
                        process_individual_dataframe(sym, df_stock, live_p, results)
        except Exception as e:
            st.error(f"Bulk download runtime failure: {e}")

    status_text.empty()
    st.session_state.ts_prewatch = sorted(results, key=lambda x: x["abs_dist_pct"])
    st.session_state.ts_prewatch_time = datetime.now().strftime("%d-%m-%Y %H:%M:%S")


def process_individual_dataframe(sym, df_stock, live_price, results_list):
    last_row = df_stock.iloc[-1]
    volume = float(last_row["Volume"])

    if volume < 100000 or pd.isna(volume) or math.isnan(volume): return

    closes = df_stock["Close"].tolist()
    ema20  = calc_ema_from_series(closes, 20)
    ema200 = calc_ema_from_series(closes, 200)

    if ema20 is None: return

    ltp = live_price if (live_price is not None and not pd.isna(live_price)) else float(last_row["Close"])

    abs_dist     = float(abs(ltp - ema20))
    abs_dist_pct = float((abs_dist / ema20) * 100.0)
    abs_dist_200 = float(abs(ltp - ema200)) if ema200 is not None else None

    body         = abs(float(last_row["Close"]) - float(last_row["Open"]))
    wick         = (float(last_row["High"]) - float(last_row["Low"])) - body
    body_gt_wick = bool(body > wick)
    vol_median   = calculate_volume_median(df_stock["Volume"])

    results_list.append({
        "sym": sym, "sector": STOCK_UNIVERSE.get(sym, {}).get("sector", "GENERAL SECTOR"), "ltp": ltp,
        "ema20": ema20, "ema200": ema200, "abs_dist_pct": abs_dist_pct, "abs_dist": abs_dist, "abs_dist_200": abs_dist_200,
        "body_gt_wick": body_gt_wick, "volume": volume, "vol_median": vol_median,
        "last_candle": {"o": float(last_row["Open"]), "h": float(last_row["High"]), "l": float(last_row["Low"]), "c": float(last_row["Close"])},
    })

# ══════════════════════════════════════════
#  INTERFACE LAYOUT ENGINE
# ══════════════════════════════════════════

col_btn1, col_btn2, col_info = st.columns([1.5, 1.5, 5])
with col_btn1:
    if st.button("🚀 FAST SCAN DAILY EMA", use_container_width=True, type="primary"):
        run_fast_prewatch_scan()
with col_btn2:
    if st.button("🗑️ CLEAR SCAN DATA", use_container_width=True):
        st.session_state.ts_prewatch = None
        st.session_state.ts_prewatch_time = None
        st.rerun()

total_scanned_count = len(st.session_state.ts_prewatch) if st.session_state.ts_prewatch else 0
scan_time_str = st.session_state.ts_prewatch_time if st.session_state.ts_prewatch_time else "None"

col_info.markdown(
    f"<div style='padding-top: 6px; font-size: 13px; color: #444444;'>"
    f"⏳ <b>Last Scanned:</b> <span style='color:#000000; font-weight:700;'>{scan_time_str}</span> | "
    f"🎯 <b>Total Stocks Filtered:</b> <span style='color:#000000; font-weight:700;'>{total_scanned_count}</span>"
    f"</div>",
    unsafe_allow_html=True
)

st.markdown("<h3 style='font-size: 13px; font-weight: 700; margin-top: 15px; color: #000000; letter-spacing:0.5px;'>⚙️ REFINEMENT OPTIONS</h3>", unsafe_allow_html=True)

with st.container(border=True):
    p1_col1, p1_col2, p1_col3 = st.columns([4.0, 4.0, 4.0])
    with p1_col1:
        filter_price = st.number_input("Minimum Price (₹)", min_value=0.0, value=0.0, step=50.0)
    with p1_col2:
        filter_ema20_pct = st.number_input("EMA Gap % (Max Dist)", min_value=0.0, max_value=100.0, value=2.0, step=0.1)
    with p1_col3:
        filter_volume = st.number_input("Volume Size (Min Limit)", min_value=0.0, value=0.0, step=50000.0)

    p2_col1, p2_col2 = st.columns([3.0, 9.0])
    with p2_col1:
        body_filter_on = st.toggle("Body > Wick Setup Only", value=False)
    with p2_col2:
        sort_strategy = st.radio(
            "Matrix Evaluation Strategy Vector:",
            ["EMA20", "Absolute Volume Size", "Confidence Score"],
            horizontal=True,
            label_visibility="collapsed"
        )

if st.session_state.ts_prewatch:
    raw_data = st.session_state.ts_prewatch
    filtered_data = []

    for r in raw_data:
        if filter_price and r["ltp"] < filter_price: continue
        if filter_volume and r["volume"] < filter_volume: continue
        if r["abs_dist_pct"] > filter_ema20_pct: continue
        if body_filter_on and not r["body_gt_wick"]: continue
        filtered_data.append(r)

    processed_cards_list = []
    for r in filtered_data:
        sig        = calculate_signals(r["ltp"], r["ema20"], r["last_candle"]["c"], r["last_candle"]["o"])
        v_strength = get_volume_strength(r["volume"], r["vol_median"])
        conf       = calculate_confidence(r["abs_dist_pct"], r["body_gt_wick"], r["abs_dist_200"])
        processed_cards_list.append({**r, "sig": sig, "v_strength": v_strength, "confidence": conf})

    available_sectors = sorted(list(set([info.get("sector", "GENERAL SECTOR") for sym, info in STOCK_UNIVERSE.items()])))
    sector_counts = {}
    for r in processed_cards_list:
        sector_counts[r["sector"]] = sector_counts.get(r["sector"], 0) + 1

    pill_options = ["ALL"]
    display_label_to_prefixed = {}
    for sector in available_sectors:
        clean_name = sector.replace('NIFTY ', '')
        label = f"{clean_name} ({sector_counts.get(sector, 0)})"
        pill_options.append(label)
        display_label_to_prefixed[label] = sector

    st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
    sector_selection_label = st.pills("Filter Matrix by Sector Footprint:", pill_options, default="ALL")

    if sector_selection_label != "ALL":
        prefixed_selected_sector = display_label_to_prefixed.get(sector_selection_label)
        if prefixed_selected_sector:
            processed_cards_list = [x for x in processed_cards_list if x["sector"] == prefixed_selected_sector]

    if sort_strategy == "EMA20": processed_cards_list.sort(key=lambda x: x["abs_dist_pct"])
    elif sort_strategy == "Absolute Volume Size": processed_cards_list.sort(key=lambda x: x["volume"], reverse=True)
    elif sort_strategy == "Confidence Score": processed_cards_list.sort(key=lambda x: x["confidence"], reverse=True)

    # ══════════════════════════════════════════
    #  BATCH WATCHLIST PANEL
    # ══════════════════════════════════════════
    with st.container(border=True):
        st.markdown("<h4 style='margin:0 0 10px 0; font-size:13px; color:#000000; font-weight:700;'>📦 Batch Inject Watchlist Management Panel</h4>", unsafe_allow_html=True)
        w_col1, w_col2 = st.columns([5, 3])
        with w_col1:
            target_list_id = st.selectbox(
                "Select Target Watchlist:",
                WATCHLIST_NAMES,
                label_visibility="collapsed"
            )
        with w_col2:
            if st.button("➕ ADD STOCKS TO SELECTED WATCHLIST", use_container_width=True, type="secondary"):
                if not processed_cards_list:
                    st.warning("No processing stocks found matching parameters to add.")
                else:
                    existing      = load_watchlist(target_list_id)
                    existing_keys = set(
                        (x.get("symbol"), x.get("exchange"), x.get("direction"))
                        for x in existing
                    )
                    new_stocks_to_insert = []
                    for item in processed_cards_list:
                        clean_sym  = item['sym'].replace(".NS", "").replace(".BO", "").upper().strip()
                        trade_dir  = "SELL" if "SELL" in item["sig"]["label"] else "BUY"
                        if (clean_sym, "NS", trade_dir) in existing_keys:
                            continue
                        raw_ltp      = item.get("ltp", 0.0)
                        parsed_entry = 0.0 if (pd.isna(raw_ltp) or math.isnan(raw_ltp)) else float(round(raw_ltp))
                        new_stocks_to_insert.append({
                            "symbol":    clean_sym,
                            "exchange":  "NS",
                            "direction": trade_dir,
                            "entry":     parsed_entry,
                            "sl":        None,
                            "target1":   None,
                            "target2":   None,
                            "note":      "EMA 20 Automated Scan",
                            "sector":    get_stock_sector(clean_sym),
                            "status":    "WATCHING",
                            "lastPrice": None,
                            "added_at":  datetime.now().isoformat(),
                            "token":     get_stock_token(clean_sym) or "",  # ← FIX v1.1
                        })
                    if new_stocks_to_insert:
                        try:
                            with st.spinner(f"Saving {len(new_stocks_to_insert)} stocks..."):
                                insert_many_to_watchlist(target_list_id, new_stocks_to_insert)
                            st.toast(f"⚡ Injected {len(new_stocks_to_insert)} stocks into '{target_list_id}'!", icon="✅")
                        except Exception as e:
                            st.error(f"Batch save failed: {e}")
                    else:
                        st.info("All stocks already exist in that watchlist.")

    st.markdown(f"<h3 style='font-size: 14px; font-weight: 700; margin-top: 20px; color: #000000;'>📊 Showing {len(processed_cards_list)} of {len(raw_data)} Scanned Securities</h3>", unsafe_allow_html=True)

    if not processed_cards_list:
        st.info("No stock setups configured matching filters.")
    else:
        for stock in processed_cards_list:
            with st.container(border=True):
                h_left, h_right = st.columns([8, 4])
                with h_left:
                    clean_sector = stock['sector'].replace('NIFTY ', '')
                    near_badge   = f"<span style='background: rgba(255,153,0,0.1); color: #B36200; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 700; border: 1px solid rgba(255,153,0,0.25); margin-left:10px;'>⭐ NEAR ({stock['abs_dist_pct']:.2f}%)</span>" if stock["abs_dist_pct"] <= 0.5 else ""
                    strong_badge = f"<span style='background: rgba(0,170,0,0.1); color: #007A2B; font-size: 11px; padding: 2px 8px; border-radius: 4px; font-weight: 700; border: 1px solid rgba(0,170,59,0.25); margin-left:10px;'>💪 STRG</span>" if stock["body_gt_wick"] else ""
                    st.markdown(f"<div style='display: flex; align-items: center; gap: 8px;'><span style='font-size: 18px; font-weight: 800; color: #111111;'>{stock['sym']}</span><span style='font-size: 14px; color: #888888; font-weight: 400; margin-left: 5px;'>| &nbsp; 📁 {clean_sector}</span>{near_badge}{strong_badge}</div>", unsafe_allow_html=True)
                with h_right:
                    st.markdown(f"<div style='text-align: right;'><span style='background: {stock['sig']['bg']}; color: {stock['sig']['color']}; font-size: 11px; font-weight: 800; padding: 3px 10px; border-radius: 4px; border: 1px solid {stock['sig']['color']}40;'>{stock['sig']['label']}</span></div>", unsafe_allow_html=True)

                st.markdown("<div style='margin-top: 10px; border-bottom: 1px solid #f0f0f0;'></div>", unsafe_allow_html=True)
                m1, m2, m3, m4, m5 = st.columns([2, 2, 2, 2, 4])

                with m1:
                    ema20_color, ema20_arrow = ("#00AA3B", "▲ ") if stock['ltp'] >= stock['ema20'] else ("#D32F2F", "▼ ")
                    st.markdown(f"<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>20 EMA PRICE (Gap: ₹{stock['abs_dist']:.2f})</p><p style='font-size:16px; font-weight:700; color:{ema20_color}; margin:2px 0 0 0;'>{ema20_arrow}₹{stock['ema20']:.2f}</p>", unsafe_allow_html=True)
                with m2:
                    m2_html = f"<span style='color: #111111;'>₹{stock['ema200']:.2f}</span>" if (stock['ema200'] is not None and not math.isnan(stock['ema200'])) else "<span style='color: #888888;'>No Data</span>"
                    st.markdown(f"<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>200 EMA PRICE</p><p style='font-size:16px; font-weight:700; margin:2px 0 0 0;'>{m2_html}</p>", unsafe_allow_html=True)
                with m3:
                    st.markdown(f"<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>CMP</p><p style='font-size:16px; font-weight:700; color:#111111; margin:2px 0 0 0;'>₹{stock['ltp']:.2f}</p>", unsafe_allow_html=True)
                with m4:
                    st.markdown(f"<p style='font-size:10px; color:#777777; font-weight:700; margin:0;'>VOLUME</p><p style='font-size:16px; font-weight:700; color:#111111; margin:2px 0 0 0;'>{format_volume_indian(stock['volume'])}</p>", unsafe_allow_html=True)
                with m5:
                    st.markdown(f"<div style='display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;'><span style='font-size: 10px; color: #777777; font-weight: 700;'>VOL MATRIX:</span><span style='font-size: 11px; color: {stock['v_strength']['color']}; font-weight: 700;'>{stock['v_strength']['label']} ({stock['v_strength']['ratio']:.1f}x)</span></div>", unsafe_allow_html=True)
                    st.progress(stock["confidence"] / 100, text=f"Setup Confidence: {stock['confidence']}%")
else:
    if st.session_state.ts_prewatch is None:
        st.warning("No prewatch matrix cache records found. Initialize database scan sequences by clicking 'FAST SCAN DAILY EMA'.")
