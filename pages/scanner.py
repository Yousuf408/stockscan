# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — Python Streamlit Adaptation v1.7
#  INTRADAY MOMENTUM SCANNER — PHASE 3
#  Watchlist integration: reads from watchlist.json (same file as Watchlist page)
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import requests
import json
import os
import sys
import pytz
import time
from datetime import datetime, timedelta

# ── Import from stocks.py (same folder as this file) ──
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
try:
    from stocks import get_stock_token, get_stock_sector
except ImportError:
    # Graceful fallback if stocks.py not found
    def get_stock_token(sym): return None
    def get_stock_sector(sym): return "GENERAL"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: WATCHLIST FILE INTEGRATION
# Reads from the same watchlist.json that the Watchlist page writes to
# ─────────────────────────────────────────────────────────────────────────────

WATCHLIST_FILE  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.json")
WATCHLIST_NAMES = ["Today", "Yesterday", "New"]


def load_watchlist_stocks(tab: str) -> list:
    """
    Load stocks from watchlist.json for the given tab name.
    Returns a list of dicts with: symbol, token, sector
    """
    try:
        if not os.path.exists(WATCHLIST_FILE):
            st.warning(f"watchlist.json not found at: {WATCHLIST_FILE}")
            return []

        with open(WATCHLIST_FILE, "r") as f:
            data = json.load(f)

        raw = data.get(f"watchlist_{tab}", [])

        if not raw:
            return []

        stocks = []
        for s in raw:
            sym = s.get("symbol", "").strip().upper()
            if not sym:
                continue

            # Try token from watchlist entry first, else look up from stocks.py
            token = s.get("token") or get_stock_token(sym) or ""

            # Try sector from watchlist entry first, else look up from stocks.py
            sector = s.get("sector") or get_stock_sector(sym) or "GENERAL"

            stocks.append({
                "symbol": sym,
                "token":  str(token),
                "sector": sector,
                "exchange": s.get("exchange", "NS"),
            })

        return stocks

    except json.JSONDecodeError as e:
        st.error(f"watchlist.json is corrupted: {e}")
        return []
    except Exception as e:
        st.error(f"Watchlist load error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: SESSION STATE INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

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

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: DATE & TIME UTILITIES (IST BOUNDED)
# ─────────────────────────────────────────────────────────────────────────────

def get_ist_now():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

def get_ist_today_str():
    return get_ist_now().strftime('%Y-%m-%d')

def get_last_trading_day_str():
    dt = get_ist_now() - timedelta(days=1)
    while dt.weekday() >= 5:  # Skip Saturday (5) and Sunday (6)
        dt -= timedelta(days=1)
    return dt.strftime('%Y-%m-%d')

def is_market_open():
    now = get_ist_now()
    current_mins = now.hour * 60 + now.minute
    market_open_mins  = 9 * 60 + 15   # 09:15 AM
    market_close_mins = 15 * 60 + 30  # 03:30 PM
    return market_open_mins <= current_mins <= market_close_mins

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: NETWORK API PIPELINES & FALLBACK DATA STREAM
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch_candles_5min(symbol_token, symbol, angel_auth=None):
    """Fetches historical OHLCV data using Angel One or Fallback Yahoo API."""
    is_open = is_market_open()
    end_date_str   = get_ist_today_str() if is_open else get_last_trading_day_str()
    start_date     = get_ist_now() - timedelta(days=20)
    start_date_str = start_date.strftime('%Y-%m-%d')

    # Strip exchange suffixes
    clean_sym = symbol.split('-')[0].split('.')[0].strip()

    # --- Angel One API Pipeline ---
    if angel_auth and angel_auth.get("session"):
        try:
            url = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {angel_auth['session'].get('jwtToken')}",
                "X-UserType": "USER",
                "X-SourceID": "WEB",
                "X-PrivateKey": angel_auth['session'].get('apiKey'),
            }
            payload = {
                "exchange": "NSE",
                "symboltoken": str(symbol_token).strip(),
                "interval": "FIVE_MINUTE",
                "from": f"{start_date_str} 09:15",
                "to": (
                    f"{end_date_str} 15:30"
                    if not is_open
                    else f"{end_date_str} {get_ist_now().strftime('%H:%M')}"
                ),
            }
            res = requests.post(url, json=payload, headers=headers, timeout=7)
            if res.status_code == 200:
                data = res.json()
                if data.get("status") is True and isinstance(data.get("data"), list):
                    df = pd.DataFrame(data["data"])
                    if not df.empty and len(df.columns) >= 6:
                        df = df.iloc[:, :6]
                        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                        return df
        except Exception:
            pass  # Fall through to Yahoo

    # --- Yahoo Finance Fallback System ---
    return fetch_yahoo_fallback_candles(clean_sym)


def fetch_yahoo_fallback_candles(symbol):
    try:
        yahoo_symbol = f"{symbol}.NS"
        url     = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=5m&range=20d"
        headers = {"User-Agent": "Mozilla/5.0"}
        res     = requests.get(url, headers=headers, timeout=7)

        if res.status_code != 200:
            return None

        json_data = res.json()
        result    = json_data.get("chart", {}).get("result", [None])[0]
        if not result:
            return None

        timestamps = result.get("timestamp", [])
        quote      = result.get("indicators", {}).get("quote", [{}])[0]

        if not timestamps or not quote:
            return None

        formatted_candles = []
        for i in range(len(timestamps)):
            o = quote.get("open",   [None])[i]
            h = quote.get("high",   [None])[i]
            l = quote.get("low",    [None])[i]
            c = quote.get("close",  [None])[i]
            v = quote.get("volume", [0])[i] or 0

            if None not in (o, h, l, c):
                dt_str = (
                    datetime.fromtimestamp(timestamps[i], tz=pytz.utc)
                    .astimezone(pytz.timezone('Asia/Kolkata'))
                    .isoformat()
                )
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
        url     = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=10d"
        headers = {"User-Agent": "Mozilla/5.0"}
        res     = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            closes       = (
                res.json()
                .get("chart", {})
                .get("result", [{}])[0]
                .get("indicators", {})
                .get("quote", [{}])[0]
                .get("close", [])
            )
            valid_closes = [c for c in closes if c is not None]
            if len(valid_closes) >= 2:
                return valid_closes[-2]
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: TECHNICAL MATH CALCULATIONS
# ─────────────────────────────────────────────────────────────────────────────

def calc_ema(series, period):
    if len(series) < period:
        return None
    return series.ewm(span=period, adjust=False).mean().iloc[-1]


def calc_vwap(df):
    """Calculates VWAP restricted to the current active trading session."""
    if df.empty:
        return None

    last_ts              = str(df['timestamp'].iloc[-1])
    current_session_date = last_ts.split('T')[0] if 'T' in last_ts else last_ts.split(' ')[0]

    session_mask = df['timestamp'].str.startswith(current_session_date)
    session_df   = df[session_mask]

    if session_df.empty:
        session_df = df.iloc[-75:] if len(df) >= 75 else df

    typical_price = (session_df['high'] + session_df['low'] + session_df['close']) / 3
    tpv_sum       = (typical_price * session_df['volume']).sum()
    vol_sum       = session_df['volume'].sum()

    return tpv_sum / vol_sum if vol_sum > 0 else None


def find_opening_candle_index(df):
    if df.empty:
        return -1
    today_ist = get_ist_today_str() if is_market_open() else get_last_trading_day_str()

    for idx, row in df.iterrows():
        ts = str(row['timestamp'])
        if 'T' not in ts:
            # AngelOne format: "2024-01-15 09:15:00"
            if ts.split(' ')[0] == today_ist and ts.split(' ')[1].startswith('09:15'):
                return idx
        else:
            # Yahoo format: ISO string — 09:15 IST = 03:45 UTC
            if ts.split('T')[0] == today_ist and ts.split('T')[1].startswith('03:45'):
                return idx
    return -1

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: STRATEGY CONDITIONAL SIGNALS
# ─────────────────────────────────────────────────────────────────────────────

def is_buy_signal(open_row, ema20, vwap, ema200):
    if None in (open_row, ema20, vwap, ema200):
        return False
    high, low, close = open_row['high'], open_row['low'], open_row['close']

    candle_range = ((high - low) / low) * 100
    if candle_range > 2.2:
        return False

    if ema200 >= ema20:
        return False
    pct_ema_gap = ((ema20 - ema200) / ema200) * 100
    if pct_ema_gap > 1.5:
        return False

    if close <= vwap:
        return False
    if close <= ema20:
        return False

    pct_from_ema20 = ((close - ema20) / ema20) * 100
    if pct_from_ema20 > 2.0:
        return False

    return True


def is_sell_signal(open_row, ema20, vwap, ema200):
    if None in (open_row, ema20, vwap, ema200):
        return False
    high, low, close = open_row['high'], open_row['low'], open_row['close']

    candle_range = ((high - low) / low) * 100
    if candle_range > 2.2:
        return False

    if ema200 <= ema20:
        return False
    pct_ema_gap = ((ema200 - ema20) / ema200) * 100
    if pct_ema_gap > 1.5:
        return False

    if close >= vwap:
        return False
    if close >= ema20:
        return False

    pct_from_ema20 = ((ema20 - close) / ema20) * 100
    if pct_from_ema20 > 2.0:
        return False

    return True


def calc_score(signal, ltp, volume, avg_volume, pct_change, ema200):
    score = 2
    if volume and avg_volume and volume > (avg_volume * 1.2):
        score += 1

    change_val = float(pct_change or 0)
    if signal == "BUY"  and change_val > 0.5:  score += 1
    elif signal == "SELL" and change_val < -0.5: score += 1

    if ema200 and ltp:
        pct_from_ema200 = abs((ltp - ema200) / ema200 * 100)
        if pct_from_ema200 <= 1.5:   score += 2
        elif pct_from_ema200 <= 3.5: score += 1

    return min(score, 6)


def should_remove_stock(signal, latest_close, ema20_live):
    """Triggers exit removal on candle CLOSE breaches."""
    if not signal or not latest_close or not ema20_live:
        return False
    if signal == "BUY"  and latest_close < ema20_live: return True
    if signal == "SELL" and latest_close > ema20_live: return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: PROCESSING ROUTINES
# ─────────────────────────────────────────────────────────────────────────────

def analyze_stock(stock, df_candles, is_refresh=False):
    symbol = stock['symbol']
    token  = stock['token']
    sector = stock['sector']

    if df_candles is None or len(df_candles) < 200:
        return None

    ema20_live   = calc_ema(df_candles['close'], 20)
    ema200_live  = calc_ema(df_candles['close'], 200)
    vwap_live    = calc_vwap(df_candles)

    if None in (ema20_live, ema200_live, vwap_live):
        return None

    last_row  = df_candles.iloc[-1]
    ltp       = float(last_row['close'])
    last_vol  = float(last_row['volume'])
    prev_close = fetch_daily_prev_close(symbol)
    pct_change = ((ltp - prev_close) / prev_close * 100) if prev_close else 0.0
    avg_vol    = df_candles['volume'].mean()

    # --- REFRESH PATHWAY ---
    if is_refresh:
        for r in st.session_state.results:
            if r['symbol'] == symbol:
                if should_remove_stock(r['signal'], ltp, ema20_live):
                    st.session_state.results = [
                        item for item in st.session_state.results if item['symbol'] != symbol
                    ]
                    return None
                r.update({
                    "ltp":       round(ltp, 2),
                    "ema20":     round(ema20_live, 2),
                    "ema200":    round(ema200_live, 2),
                    "vwap":      round(vwap_live, 2),
                    "pctChange": round(pct_change, 2),
                })
                return r
        return None

    # --- INITIAL SCAN PATHWAY ---
    opening_idx = find_opening_candle_index(df_candles)
    if opening_idx < 0:
        return None

    open_row        = df_candles.iloc[opening_idx]
    candles_at_open = df_candles.iloc[:opening_idx + 1]

    if len(candles_at_open) < 200:
        return None

    ema20_at_open   = calc_ema(candles_at_open['close'], 20)
    ema200_at_open  = calc_ema(candles_at_open['close'], 200)
    vwap_at_open    = calc_vwap(candles_at_open)

    signal = None
    if is_buy_signal(open_row, ema20_at_open, vwap_at_open, ema200_at_open):
        signal = "BUY"
    elif is_sell_signal(open_row, ema20_at_open, vwap_at_open, ema200_at_open):
        signal = "SELL"

    if signal:
        score = calc_score(signal, ltp, last_vol, avg_vol, pct_change, ema200_live)
        result_obj = {
            "symbol":     symbol,
            "sector":     sector or "GENERAL",
            "signal":     signal,
            "ltp":        round(ltp, 2),
            "ema20":      round(ema20_live, 2),
            "ema200":     round(ema200_live, 2),
            "vwap":       round(vwap_live, 2),
            "pctChange":  round(pct_change, 2),
            "score":      round(float(score), 1),
            "timestamp":  time.time(),
            "volume":     last_vol,
            "openPrice":  round(float(open_row['open']),  2),
            "highPrice":  round(float(open_row['high']),  2),
            "lowPrice":   round(float(open_row['low']),   2),
            "closePrice": round(float(open_row['close']), 2),
        }
        # Deduplicate before appending
        st.session_state.results = [
            item for item in st.session_state.results if item['symbol'] != symbol
        ]
        st.session_state.results.append(result_obj)
        return result_obj

    return None


def run_full_scan(watchlist_stocks):
    if not watchlist_stocks:
        st.warning("No stocks found in this watchlist tab. Add stocks via the Watchlist page first.")
        return

    st.session_state.is_scanning = True
    progress_bar = st.progress(0, text="Initializing scan...")
    processed    = 0
    total        = len(watchlist_stocks)

    for stock in watchlist_stocks:
        progress_bar.progress(processed / total, text=f"Scanning: {stock['symbol']}")
        df = fetch_candles_5min(stock['token'], stock['symbol'])
        analyze_stock(stock, df, is_refresh=False)
        processed += 1

    if st.session_state.results:
        st.session_state.results.sort(
            key=lambda x: (0 if x['signal'] == 'BUY' else 1, -x['score'])
        )

    progress_bar.empty()
    st.session_state.is_scanning = False


def run_refresh_scan(watchlist_stocks):
    if not st.session_state.results:
        return
    for r in st.session_state.results:
        matched = next((s for s in watchlist_stocks if s['symbol'] == r['symbol']), None)
        if matched:
            df = fetch_candles_5min(matched['token'], matched['symbol'])
            analyze_stock(matched, df, is_refresh=True)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: STREAMLIT UI
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Trade Sentry - Scanner Dashboard", layout="wide")

# ── SIDEBAR: Watchlist Tab Selector ──
st.sidebar.markdown("### 📋 Watchlist Source")
selected_wl = st.sidebar.selectbox(
    "Target Scanning Watchlist",
    WATCHLIST_NAMES,
    index=WATCHLIST_NAMES.index(st.session_state.selected_watchlist),
)

# If user switches tab → clear old results and reload
if selected_wl != st.session_state.selected_watchlist:
    st.session_state.selected_watchlist = selected_wl
    st.session_state.results = []
    st.rerun()

# ── Load stocks from watchlist.json for the selected tab ──
stocks_to_scan = load_watchlist_stocks(st.session_state.selected_watchlist)

# ── Sidebar: show loaded stocks summary ──
st.sidebar.markdown(f"**{len(stocks_to_scan)} stocks** loaded from `{st.session_state.selected_watchlist}` watchlist")
if stocks_to_scan:
    with st.sidebar.expander("View loaded stocks"):
        for s in stocks_to_scan:
            st.sidebar.markdown(f"• `{s['symbol']}` — {s['sector']}")

# ── Main Title ──
st.markdown("## 🛡 Trade Sentry — Momentum Scanner")
st.markdown(
    f"Scanning **{st.session_state.selected_watchlist}** watchlist · "
    f"`{len(stocks_to_scan)}` stocks loaded"
)

# ── Control Strip ──
col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([2, 2, 2, 4])
with col_ctrl1:
    if st.button("🚀 RUN FULL SCAN", use_container_width=True, disabled=len(stocks_to_scan) == 0):
        run_full_scan(stocks_to_scan)
with col_ctrl2:
    if st.button("🔄 REFRESH METRICS", use_container_width=True, disabled=len(st.session_state.results) == 0):
        run_refresh_scan(stocks_to_scan)
with col_ctrl3:
    if st.button("🧹 CLEAR RESULTS", use_container_width=True):
        st.session_state.results = []
        st.success("Scanner cleared.")
with col_ctrl4:
    auto_on = st.checkbox("Toggle Auto-Refresh (5-Min Loops)", value=st.session_state.auto_refresh)
    if auto_on != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto_on

# ── Empty watchlist warning ──
if len(stocks_to_scan) == 0:
    st.info(
        f"⚠️ The **{st.session_state.selected_watchlist}** watchlist is empty. "
        "Add stocks from the **Watchlist** page first, then come back to scan."
    )

# ── Filter Panel ──
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

# ── Filter Evaluation Engine ──
processed_view_list = list(st.session_state.results)

# Sector filter
all_sectors     = sorted(list(set(r['sector'] for r in processed_view_list)))
selected_sector = st.radio("Sector Filter", ["ALL"] + all_sectors, horizontal=True)
if selected_sector != "ALL":
    processed_view_list = [r for r in processed_view_list if r['sector'] == selected_sector]

# Signal filter
if filter_sig != "ALL":
    processed_view_list = [r for r in processed_view_list if r['signal'] == filter_sig]

# Volume filter
if filter_min_vol.strip():
    try:
        processed_view_list = [r for r in processed_view_list if r['volume'] >= float(filter_min_vol)]
    except ValueError:
        pass

# EMA20 distance filter
if filter_ema20.strip():
    try:
        processed_view_list = [
            r for r in processed_view_list
            if abs((r['ltp'] - r['ema20']) / r['ema20'] * 100) <= float(filter_ema20)
        ]
    except ValueError:
        pass

# EMA200 distance filter
if filter_ema200.strip():
    try:
        processed_view_list = [
            r for r in processed_view_list
            if abs((r['ltp'] - r['ema200']) / r['ema200'] * 100) <= float(filter_ema200)
        ]
    except ValueError:
        pass

# Min score filter
if filter_min_score.strip():
    try:
        processed_view_list = [r for r in processed_view_list if r['score'] >= float(filter_min_score)]
    except ValueError:
        pass

# Body/wick filter
if toggle_body_wick:
    valid_body_setups = []
    for r in processed_view_list:
        body        = abs(r['closePrice'] - r['openPrice'])
        total_range = r['highPrice'] - r['lowPrice']
        if total_range > 0 and (body / total_range) >= 0.5:
            valid_body_setups.append(r)
    processed_view_list = valid_body_setups

# ── Results Display ──
st.write(
    f"#### 🎯 Actionable Targets: "
    f"`{len(processed_view_list)}` / `{len(st.session_state.results)}` signals"
)

if not processed_view_list:
    if st.session_state.results:
        st.info("🔍 No signals match your current filters.")
    else:
        st.info("🔍 Run a scan to see results.")
else:
    for item in processed_view_list:
        accent    = "🟢 BUY" if item['signal'] == "BUY" else "🔴 SELL"
        border_clr = "#00e676" if item['signal'] == "BUY" else "#ff4444"
        pct_clr    = "#00e676" if item['pctChange'] >= 0 else "#ff4444"

        mins_ago = int((time.time() - item['timestamp']) // 60)
        age_str  = "just now" if mins_ago < 1 else f"{mins_ago}m ago"

        with st.container():
            st.markdown(
                f"""
                <div style="border-left: 5px solid {border_clr}; background-color: #1a1a1a;
                            padding: 12px; margin-bottom: 10px; border-radius: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 18px; font-weight: bold; color: #ffffff; font-family: monospace;">
                            {item['symbol']}
                            <span style="font-size: 11px; background-color:#333; padding:2px 6px;
                                         border-radius:3px; color:#aaa;">{item['sector']}</span>
                        </span>
                        <span style="font-size: 16px; font-weight: bold; color: {border_clr};
                                     font-family: monospace;">{accent}</span>
                    </div>
                    <hr style="margin: 8px 0; border-color: #333;"/>
                    <div style="display: flex; justify-content: space-between; align-items: center; font-size: 14px;">
                        <div>
                            LTP: <span style="font-weight: bold; color:#ffffff;">₹{item['ltp']}</span>
                            <span style="color:{pct_clr}; font-weight:bold; margin-left:8px;">{item['pctChange']}%</span>
                        </div>
                        <div style="color: #aaa;">
                            EMA20: <span style="color:#fff;">{item['ema20']}</span> |
                            VWAP: <span style="color:#ffb300;">{item['vwap']}</span> |
                            EMA200: <span style="color:#fff;">{item['ema200']}</span>
                        </div>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center;
                                font-size: 11px; color: #666; margin-top: 6px;">
                        <span>Signal Generated: {age_str}</span>
                        <span style="color:{border_clr}; font-weight:bold;">
                            Matrix Conviction Score: {item['score']}/6.0
                        </span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# ── Auto-Refresh Loop ──
if st.session_state.auto_refresh:
    time.sleep(300)
    run_refresh_scan(stocks_to_scan)
    st.rerun()
