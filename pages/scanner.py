import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import pytz
import time

# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — Python Streamlit Adaptation v1.6
#  INTRADAY MOMENTUM SCANNER — PHASE 3 (9:15 EMA Stack Order Fix)
# ══════════════════════════════════════════════════════════════════════════════

# Ensure your script initializes default state parameters safely inside session memory
if "results" not in st.session_state:
    st.session_state.results = []
if "is_scanning" not in st.session_state:
    st.session_state.is_scanning = False
if "selected_watchlist" not in st.session_state:
    st.session_state.selected_watchlist = "Today"
if "active_sector" not in st.session_state:
    st.session_state.active_sector = "ALL"
if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False

# Mock Stock Universe Registry (Replace this dictionary with your loaded global dataset if needed)
STOCK_UNIVERSE = {
    "GAIL": {"token": "317", "sector": "NIFTY ENERGY"},
    "GMDC": {"token": "10022", "sector": "NIFTY METALS"},
    "RELIANCE": {"token": "2885", "sector": "NIFTY ENERGY"},
    "JYOTICNC": {"token": "19231", "sector": "NIFTY CAPITAL GOODS"},
    "HEROMOTOCO": {"token": "1342", "sector": "NIFTY AUTO"}
}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: DATE & TIME UTILITIES (IST BOUNDED)
# ─────────────────────────────────────────────────────────────────────────────

def get_ist_now():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

def get_ist_today_str():
    return get_ist_now().strftime('%Y-%m-%d')

def get_last_trading_day_str():
    dt = get_ist_now() - timedelta(days=1)
    while dt.weekday() >= 5: # Skip Saturday (5) and Sunday (6)
        dt -= timedelta(days=1)
    return dt.strftime('%Y-%m-%d')

def is_market_open():
    now = get_ist_now()
    current_mins = now.hour * 60 + now.minute
    market_open_mins = 9 * 60 + 15   # 09:15 AM
    market_close_mins = 15 * 60 + 30 # 03:30 PM
    return market_open_mins <= current_mins <= market_close_mins

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: NETWORK API PIPELINES & FALLBACK DATA STREAM
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch_candles_5min(symbol_token, symbol, angel_auth=None):
    """Fetches historical OHLCV data using Angel One or Fallback Yahoo API."""
    is_open = is_market_open()
    end_date_str = get_ist_today_str() if is_open else get_last_trading_day_str()
    
    # 20 Calendar days lookback requirement
    start_date = get_ist_now() - timedelta(days=20)
    start_date_str = start_date.strftime('%Y-%m-%d')
    
    # Clean symbol mappings to match extensions
    clean_symbol = symbol.split('-')[0].split('.')[0].strip()
    
    # --- Angel One API Pipeline ---
    if angel_auth and angel_auth.get("session"):
        try:
            url = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {angel_auth['session'].get('jwtToken')}",
                "X-UserType": "USER",
                "X-SourceID": "WEB",
                "X-PrivateKey": angel_auth['session'].get('apiKey')
            }
            payload = {
                "exchange": "NSE",
                "symboltoken": str(symbol_token).trim(),
                "interval": "FIVE_MINUTE",
                "from": f"{start_date_str} 09:15",
                "to": f"{end_date_str} 15:30" if not is_open else f"{end_date_str} {get_ist_now().strftime('%H:%M')}"
            }
            res = requests.post(url, json=payload, headers=headers, timeout=7)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") is True and isinstance(data.get("data"), list):
                    # Wrap to pandas matching original data layout
                    df = pd.DataFrame(data["data"])
                    if not df.empty and len(df.columns) >= 6:
                        df = df.iloc[:, :6]
                        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                        return df
        except Exception:
            pass # Gracefully slide into fallback engine on network dropping errors
            
    # --- Yahoo Finance Fallback System ---
    return fetch_yahoo_fallback_candles(clean_symbol)


def fetch_yahoo_fallback_candles(symbol):
    try:
        yahoo_symbol = f"{symbol}.NS"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=5m&range=20d"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=7)
        if res.status_code != 200:
            return None
            
        json_data = res.json()
        result = json_data.get("chart", {}).get("result", [None])[0]
        if not result:
            return None
            
        timestamps = result.get("timestamp", [])
        quote = result.get("indicators", {}).get("quote", [{}])[0]
        
        if not timestamps or not quote:
            return None
            
        formatted_candles = []
        for i in range(len(timestamps)):
            o = quote.get("open", [None])[i]
            h = quote.get("high", [None])[i]
            l = quote.get("low", [None])[i]
            c = quote.get("close", [None])[i]
            v = quote.get("volume", [0])[i] or 0
            
            if None not in (o, h, l, c):
                # ISO conversion matching JS date format output parameters
                dt_str = datetime.fromtimestamp(timestamps[i], tz=pytz.utc).astimezone(pytz.timezone('Asia/Kolkata')).isoformat()
                formatted_candles.append([dt_str, float(o), float(h), float(l), float(c), float(v)])
                
        df = pd.DataFrame(formatted_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df if not df.empty else None
    except Exception:
        return None

@st.cache_data(ttl=1800)
def fetch_daily_prev_close(symbol):
    """Gets yesterday's daily close using native Yahoo historical datasets."""
    try:
        yahoo_symbol = f"{symbol.split('-')[0].split('.')[0].strip()}.NS"
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=10d"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            closes = res.json().get("chart", {}).get("result", [{}])[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
            valid_closes = [c for c in closes if c is not None]
            if len(valid_closes) >= 2:
                return valid_closes[-2] # Return actual completed previous day close
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: TECHNICAL MATH CALCULATIONS & MATRIX LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def calc_ema(series, period):
    if len(series) < period:
        return None
    return series.ewm(span=period, adjust=False).mean().iloc[-1]

def calc_vwap(df):
    """Calculates exact VWAP restricted explicitly inside current active trading session boundary."""
    if df.empty:
        return None
        
    last_ts = str(df['timestamp'].iloc[-1])
    current_session_date = last_ts.split('T')[0] if 'T' in last_ts else last_ts.split(' ')[0]
    
    # Mask dataset to current day array boundaries only
    session_mask = df['timestamp'].str.startswith(current_session_date)
    session_df = df[session_mask]
    
    if session_df.empty:
        # Fallback processing match route for JS sliced boundary block array indexes
        session_df = df.suffix(-75) if len(df) >= 75 else df
        
    typical_price = (session_df['high'] + session_df['low'] + session_df['close']) / 3
    tpv_sum = (typical_price * session_df['volume']).sum()
    vol_sum = session_df['volume'].sum()
    
    return tpv_sum / vol_sum if vol_sum > 0 else None


def find_opening_candle_index(df):
    if df.empty:
        return -1
    today_ist = get_ist_today_str() if is_market_open() else get_last_trading_day_str()
    
    for idx, row in df.iterrows():
        ts = str(row['timestamp'])
        if 'T' not in ts:
            # AngelOne formatting path check
            if ts.split(' ')[0] == today_ist and ts.split(' ')[1].startswith('09:15'):
                return idx
        else:
            # Yahoo formatting conversion path check (09:15 IST translates directly to 03:45 UTC strings)
            if ts.split('T')[0] == today_ist and ts.split('T')[1].startswith('03:45'):
                return idx
    return -1

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: STRATEGY CONDITIONAL SIGNALS
# ─────────────────────────────────────────────────────────────────────────────

def is_buy_signal(open_row, ema20, vwap, ema200):
    if None in (open_row, ema20, vwap, ema200): return False
    
    high, low, close = open_row['high'], open_row['low'], open_row['close']
    
    # Candle Range Cap Check
    candle_range = ((high - low) / low) * 100
    if candle_range > 2.2: return False
    
    # EMA Stack Ordering & Proximity Gap Constraint Check
    if ema200 >= ema20: return False
    pct_ema_gap = ((ema20 - ema200) / ema200) * 100
    if pct_ema_gap > 1.5: return False
    
    # Directional Intraday Confirms
    if close <= vwap: return False
    if close <= ema20: return False
    
    # Avoid Overextended Entry Lines
    pct_from_ema20 = ((close - ema20) / ema20) * 100
    if pct_from_ema20 > 2.0: return False
    
    return True


def is_sell_signal(open_row, ema20, vwap, ema200):
    if None in (open_row, ema20, vwap, ema200): return False
    
    high, low, close = open_row['high'], open_row['low'], open_row['close']
    
    # Candle Range Cap Check
    candle_range = ((high - low) / low) * 100
    if candle_range > 2.2: return False
    
    # EMA Stack Ordering & Proximity Gap Constraint Check
    if ema200 <= ema20: return False
    pct_ema_gap = ((ema200 - ema20) / ema200) * 100
    if pct_ema_gap > 1.5: return False
    
    # Directional Intraday Confirms
    if close >= vwap: return False
    if close >= ema20: return False
    
    # Avoid Overextended Entry Lines
    pct_from_ema20 = ((ema20 - close) / ema20) * 100
    if pct_from_ema20 > 2.0: return False
    
    return True


def calc_score(signal, ltp, volume, avg_volume, pct_change, ema200):
    score = 2
    if volume and avg_volume and volume > (avg_volume * 1.2):
        score += 1
    
    change_val = float(pct_change or 0)
    if signal == "BUY" and change_val > 0.5: score += 1
    elif signal == "SELL" and change_val < -0.5: score += 1
        
    if ema200 and ltp:
        pct_from_ema200 = abs((ltp - ema200) / ema200 * 100)
        if pct_from_ema200 <= 1.5: score += 2
        elif pct_from_ema200 <= 3.5: score += 1
        
    return min(score, 6)


def should_remove_stock(signal, latest_close, ema20_live):
    """Triggers exit removals exclusively on Candle CLOSE breaches."""
    if not signal or not latest_close or not ema20_live: return False
    if signal == "BUY" and latest_close < ema20_live: return True
    if signal == "SELL" and latest_close > ema20_live: return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: PROCESSING ROUTINES
# ─────────────────────────────────────────────────────────────────────────────

def analyze_stock(stock, df_candles, is_refresh=False):
    symbol, token, sector = stock['symbol'], stock['token'], stock['sector']
    
    if df_candles is None or len(df_candles) < 800:
        return None

    # Calculate LIVE metrics parameters
    ema20_live = calc_ema(df_candles['close'], 20)
    ema200_live = calc_ema(df_candles['close'], 200)
    vwap_live = calc_vwap(df_candles)
    
    if None in (ema20_live, ema200_live, vwap_live): return None
    
    last_row = df_candles.iloc[-1]
    ltp = float(last_row['close'])
    last_vol = float(last_row['volume'])
    
    prev_close = fetch_daily_prev_close(symbol)
    pct_change = ((ltp - prev_close) / prev_close * 100) if prev_close else 0.0
    
    avg_vol = df_candles['volume'].mean()
    
    # --- REFRESH EVALUATION ENGINE PATHWAY ---
    if is_refresh:
        for r in st.session_state.results:
            if r['symbol'] == symbol:
                if should_remove_stock(r['signal'], ltp, ema20_live):
                    st.session_state.results = [item for item in st.session_state.results if item['symbol'] != symbol]
                    return None
                r.update({
                    "ltp": round(ltp, 2),
                    "ema20": round(ema20_live, 2),
                    "ema200": round(ema200_live, 2),
                    "vwap": round(vwap_live, 2),
                    "pctChange": round(pct_change, 2)
                })
                return r
        return None

    # --- INITIAL SCAN EVALUATION ENGINE PATHWAY ---
    opening_idx = find_opening_candle_index(df_candles)
    if opening_idx < 0: return None
    
    open_row = df_candles.iloc[opening_idx]
    candles_at_open = df_candles.iloc[:opening_idx + 1]
    
    if len(candles_at_open) < 200: return None
    
    ema20_at_open = calc_ema(candles_at_open['close'], 20)
    ema200_at_open = calc_ema(candles_at_open['close'], 200)
    vwap_at_open = calc_vwap(candles_at_open)
    
    signal = None
    if is_buy_signal(open_row, ema20_at_open, vwap_at_open, ema200_at_open):
        signal = "BUY"
    elif is_sell_signal(open_row, ema20_at_open, vwap_at_open, ema200_at_open):
        signal = "SELL"
        
    if signal:
        score = calc_score(signal, ltp, last_vol, avg_vol, pct_change, ema200_live)
        result_obj = {
            "symbol": symbol,
            "sector": sector or "GENERAL",
            "signal": signal,
            "ltp": round(ltp, 2),
            "ema20": round(ema20_live, 2),
            "ema200": round(ema200_live, 2),
            "vwap": round(vwap_live, 2),
            "pctChange": round(pct_change, 2),
            "score": round(float(score), 1),
            "timestamp": time.time(),
            "volume": last_vol,
            "openPrice": round(float(open_row['open']), 2),
            "highPrice": round(float(open_row['high']), 2),
            "lowPrice": round(float(open_row['low']), 2),
            "closePrice": round(float(open_row['close']), 2),
        }
        
        # Merge scan updates to avoid duplicates
        st.session_state.results = [item for item in st.session_state.results if item['symbol'] != symbol]
        st.session_state.results.append(result_obj)
        return result_obj
        
    return None


def run_full_scan(watchlist_stocks):
    st.session_state.is_scanning = True
    progress_bar = st.progress(0, text="Initializing setup...")
    
    processed = 0
    total = len(watchlist_stocks)
    
    for stock in watchlist_stocks:
        progress_bar.progress(processed / total, text=f"Scanning target: {stock['symbol']}")
        df = fetch_candles_5min(stock['token'], stock['symbol'])
        analyze_stock(stock, df, is_refresh=False)
        processed += 1
        
    # Apply primary layout ordering schema parameters
    if st.session_state.results:
        st.session_state.results.sort(
            key=lambda x: (0 if x['signal'] == 'BUY' else 1, -x['score'])
        )
        
    progress_bar.empty()
    st.session_state.is_scanning = False


def run_refresh_scan(watchlist_stocks):
    if not st.session_state.results: return
    for r in st.session_state.results:
        matched = next((s for s in watchlist_stocks if s['symbol'] == r['symbol']), None)
        if matched:
            df = fetch_candles_5min(matched['token'], matched['symbol'])
            analyze_stock(matched, df, is_refresh=True)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: STREAMLIT UI RENDER ENVIRONMENT
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Trade Sentry - Scanner Dashboard", layout="wide")
st.title("🛡️ TRADE SENTRY — SCANNER ENGINE")

# Watchlist Definition Resolvers
watchlist_options = ["Today", "Yesterday", "New"]
selected_wl = st.sidebar.selectbox("Target Scanning Watchlist", watchlist_options, index=0)
st.session_state.selected_watchlist = selected_wl

# Prepare localized watchlist items lists arrays matching user summaries configurations
stocks_to_scan = [
    {"symbol": sym, "token": data["token"], "sector": data["sector"]}
    for sym, data in STOCK_UNIVERSE.items()
]

# Control Strip Setup
col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([2, 2, 2, 4])
with col_ctrl1:
    if st.button("🚀 RUN FULL SCAN", use_container_width=True):
        run_full_scan(stocks_to_scan)
with col_ctrl2:
    if st.button("🔄 REFRESH METRICS", use_container_width=True):
        run_refresh_scan(stocks_to_scan)
with col_ctrl3:
    if st.button("🧹 CLEAR ACTION RESULTS", use_container_width=True):
        st.session_state.results = []
        st.success("Scanner boards wiped down successfully.")
with col_ctrl4:
    # Handle auto refresh tracking setup metrics internally inside Streamlit rerun rules
    auto_on = st.checkbox("Toggle Auto-Refresh (5-Min Loops)")
    if auto_on != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto_on

# ⚙ REFINE FILTER SELECTION CONTROL PANEL
st.write("### ⚙ REFINE CONFIGURATION FILTERS")
col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)

with col_f1:
    filter_sig = st.selectbox("Signal Vector Type", ["ALL", "BUY", "SELL"])
with col_f2:
    filter_min_vol = st.text_input("Volume Threshold (≥)", value="")
with col_f3:
    filter_ema20 = st.text_input("Max EMA20 Distance % (≤)", value="")
with col_f4:
    filter_ema200 = st.text_input("Max EMA200 Distance % (≤)", value="")
with col_f5:
    filter_min_score = st.text_input("Min Conviction Score (≥)", value="")

toggle_body_wick = st.toggle("Filter Strong Candles (Body > 50% of Range)")

# --- FILTER EVALUATION ENGINE PIPELINE ---
processed_view_list = list(st.session_state.results)

# 1. Sector Processing
all_sectors = sorted(list(set(r['sector'] for r in processed_view_list)))
selected_sector = st.radio("Sector Filter Chips", ["ALL"] + all_sectors, horizontal=True)

if selected_sector != "ALL":
    processed_view_list = [r for r in processed_view_list if r['sector'] == selected_sector]

# 2. Refine Metrics Slicing Block
if filter_sig != "ALL":
    processed_view_list = [r for r in processed_view_list if r['signal'] == filter_sig]

if filter_min_vol.strip():
    processed_view_list = [r for r in processed_view_list if r['volume'] >= float(filter_min_vol)]

if filter_ema20.strip():
    processed_view_list = [
        r for r in processed_view_list 
        if abs((r['ltp'] - r['ema20']) / r['ema20'] * 100) <= float(filter_ema20)
    ]

if filter_ema200.strip():
    processed_view_list = [
        r for r in processed_view_list 
        if abs((r['ltp'] - r['ema200']) / r['ema200'] * 100) <= float(filter_ema200)
    ]

if filter_min_score.strip():
    processed_view_list = [r for r in processed_view_list if r['score'] >= float(filter_min_score)]

if toggle_body_wick:
    valid_body_setups = []
    for r in processed_view_list:
        body = abs(r['closePrice'] - r['openPrice'])
        total_range = r['highPrice'] - r['lowPrice']
        if total_range > 0 and (body / total_range) >= 0.5:
            valid_body_setups.append(r)
    processed_view_list = valid_body_setups

# ─────────────────────────────────────────────────────────────────────────────
# CARDS DISPLAY GRID PRINTING LAYOUT AREA
# ─────────────────────────────────────────────────────────────────────────────
st.write(f"#### 🎯 Actionable Targets Located: `{len(processed_view_list)}` / `{len(st.session_state.results)}` records.")

if not processed_view_list:
    st.info("🔍 No actionable strategy patterns match your criteria currently.")
else:
    # Render interactive grid layout dynamically matching extension views cards framework setup
    for item in processed_view_list:
        accent = "🟢 BUY" if item['signal'] == "BUY" else "🔴 SELL"
        border_clr = "#00e676" if item['signal'] == "BUY" else "#ff4444"
        pct_clr = "#00e676" if item['pctChange'] >= 0 else "#ff4444"
        
        mins_ago = int((time.time() - item['timestamp']) // 60)
        age_str = "just now" if mins_ago < 1 else f"{mins_ago}m ago"

        # Inject styling elements natively around containers via markdown boundaries blocks wrappers
        with st.container():
            st.markdown(
                f"""
                <div style="border-left: 5px solid {border_clr}; background-color: #1a1a1a; padding: 12px; margin-bottom: 10px; border-radius: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 18px; font-weight: bold; color: #ffffff; font-family: monospace;">{item['symbol']} 
                            <span style="font-size: 11px; background-color:#333; padding:2px 6px; border-radius:3px; color:#aaa;">{item['sector']}</span>
                        </span>
                        <span style="font-size: 16px; font-weight: bold; color: {border_clr}; font-family: monospace;">{accent}</span>
                    </div>
                    <hr style="margin: 8px 0; border-color: #333;"/>
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 14px;">
                        <div>LTP: <span style="font-weight: bold; color:#ffffff;">₹{item['ltp']}</span> <span style="color:{pct_clr}; font-weight:bold; margin-left:8px;">{item['pctChange']}%</span></div>
                        <div style="color: #aaa;">EMA20: <span style="color:#fff;">{item['ema20']}</span> | VWAP: <span style="color:#ffb300;">{item['vwap']}</span> | EMA200: <span style="color:#fff;">{item['ema200']}</span></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: #666; margin-top: 6px;">
                        <span>Signal Generated: {age_str}</span>
                        <span style="color:{border_clr}; font-weight:bold;">Matrix Conviction Score: {item['score']}/6.0</span>
                    </div>
                </div>
                """, 
                unsafe_allow_html=True
            )

# Streamlit looping thread trigger handler logic
if st.session_state.auto_refresh:
    time.sleep(300)
    run_refresh_scan(stocks_to_scan)
    st.rerun()
