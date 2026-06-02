# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — Python Streamlit Adaptation v1.8
#  INTRADAY MOMENTUM SCANNER
#  Watchlist integration: reads from watchlist.json (same file as Watchlist page)
#  FIXES v1.8:
#    - Sidebar stock list bug fixed (no longer renders in sidebar)
#    - Minimum candle count reduced from 800 → 50 (Yahoo only gives ~75/day)
#    - candles_at_open minimum reduced from 200 → 20 (realistic for 5min data)
#    - Opening candle search now also handles pre-market gap (searches closest to 9:15)
#    - Added debug expander to show why stocks were skipped during scan
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

# ── Import from stocks.py ──
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
try:
    from stocks import get_stock_token, get_stock_sector
except ImportError:
    def get_stock_token(sym): return None
    def get_stock_sector(sym): return "GENERAL"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: WATCHLIST FILE INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

WATCHLIST_FILE  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "watchlist.json")
WATCHLIST_NAMES = ["Today", "Yesterday", "New"]


def load_watchlist_stocks(tab: str) -> list:
    """Load stocks from watchlist.json for the given tab name."""
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
            token  = s.get("token")  or get_stock_token(sym)  or ""
            sector = s.get("sector") or get_stock_sector(sym) or "GENERAL"
            stocks.append({
                "symbol":   sym,
                "token":    str(token),
                "sector":   sector,
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
# SECTION 2: SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

for _k, _v in [
    ("results", []),
    ("is_scanning", False),
    ("selected_watchlist", "Today"),
    ("auto_refresh", False),
    ("scan_log", []),      # debug log: why stocks were skipped
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: DATE & TIME UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def get_ist_now():
    return datetime.now(pytz.timezone('Asia/Kolkata'))

def get_ist_today_str():
    return get_ist_now().strftime('%Y-%m-%d')

def get_last_trading_day_str():
    dt = get_ist_now() - timedelta(days=1)
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime('%Y-%m-%d')

def is_market_open():
    now  = get_ist_now()
    mins = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= mins <= (15 * 60 + 30)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch_candles_5min(symbol_token, symbol, angel_auth=None):
    """Fetch 5-min OHLCV: Angel One → Yahoo fallback."""
    is_open        = is_market_open()
    end_date_str   = get_ist_today_str() if is_open else get_last_trading_day_str()
    start_date_str = (get_ist_now() - timedelta(days=20)).strftime('%Y-%m-%d')
    clean_sym      = symbol.split('-')[0].split('.')[0].strip()

    # Angel One
    if angel_auth and angel_auth.get("session"):
        try:
            url = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
            headers = {
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {angel_auth['session'].get('jwtToken')}",
                "X-UserType":    "USER",
                "X-SourceID":    "WEB",
                "X-PrivateKey":  angel_auth['session'].get('apiKey'),
            }
            payload = {
                "exchange":    "NSE",
                "symboltoken": str(symbol_token).strip(),
                "interval":    "FIVE_MINUTE",
                "from":        f"{start_date_str} 09:15",
                "to":          f"{end_date_str} 15:30" if not is_open else f"{end_date_str} {get_ist_now().strftime('%H:%M')}",
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
            pass

    return fetch_yahoo_fallback_candles(clean_sym)


def fetch_yahoo_fallback_candles(symbol):
    """Yahoo Finance 5-min fallback. Returns up to ~60 days of 5-min data."""
    try:
        yahoo_symbol = f"{symbol}.NS"
        # Yahoo only gives 5m data for last 60 days; range=60d gives max history
        url     = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=5m&range=60d"
        headers = {"User-Agent": "Mozilla/5.0"}
        res     = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            return None

        json_data  = res.json()
        result     = json_data.get("chart", {}).get("result", [None])[0]
        if not result:
            return None

        timestamps = result.get("timestamp", [])
        quote      = result.get("indicators", {}).get("quote", [{}])[0]
        if not timestamps or not quote:
            return None

        formatted = []
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
                formatted.append([dt_str, float(o), float(h), float(l), float(c), float(v)])

        df = pd.DataFrame(formatted, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df if not df.empty else None
    except Exception:
        return None


@st.cache_data(ttl=1800)
def fetch_daily_prev_close(symbol):
    try:
        yahoo_symbol = f"{symbol.split('-')[0].split('.')[0].strip()}.NS"
        url     = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}?interval=1d&range=10d"
        headers = {"User-Agent": "Mozilla/5.0"}
        res     = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            closes = (
                res.json()
                .get("chart", {}).get("result", [{}])[0]
                .get("indicators", {}).get("quote", [{}])[0]
                .get("close", [])
            )
            valid = [c for c in closes if c is not None]
            if len(valid) >= 2:
                return valid[-2]
    except Exception:
        pass
    return None

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: TECHNICAL INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def calc_ema(series, period):
    if len(series) < period:
        return None
    return series.ewm(span=period, adjust=False).mean().iloc[-1]


def calc_vwap(df):
    """VWAP for current session only."""
    if df.empty:
        return None
    last_ts  = str(df['timestamp'].iloc[-1])
    sess_date = last_ts.split('T')[0] if 'T' in last_ts else last_ts.split(' ')[0]
    mask     = df['timestamp'].astype(str).str.startswith(sess_date)
    sess_df  = df[mask]
    if sess_df.empty:
        sess_df = df.iloc[-75:] if len(df) >= 75 else df
    tp      = (sess_df['high'] + sess_df['low'] + sess_df['close']) / 3
    vol_sum = sess_df['volume'].sum()
    return (tp * sess_df['volume']).sum() / vol_sum if vol_sum > 0 else None


def find_opening_candle_index(df, target_date_str):
    """
    Find the index of the 9:15 AM candle for target_date_str.
    Strategy:
      1. Exact match on 09:15 IST
      2. If not found, take the FIRST candle of that trading day
         (handles cases where Yahoo skips 9:15 and starts at 9:20 etc.)
    Returns (idx, open_row) or (-1, None)
    """
    if df.empty:
        return -1, None

    ts_col = df['timestamp'].astype(str)

    # Filter to target date
    day_mask = ts_col.str.startswith(target_date_str)
    day_df   = df[day_mask]

    if day_df.empty:
        return -1, None

    # Try exact 09:15 match (AngelOne: "09:15", Yahoo ISO: "T03:45")
    exact_mask = (
        ts_col.str.contains('09:15') |   # AngelOne format
        ts_col.str.contains('T03:45')    # Yahoo UTC→IST 09:15 = 03:45 UTC
    )
    exact_day = df[day_mask & exact_mask]

    if not exact_day.empty:
        idx = exact_day.index[0]
        return idx, df.loc[idx]

    # Fallback: first candle of that day (Yahoo sometimes starts at 9:20)
    idx = day_df.index[0]
    return idx, df.loc[idx]


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: SIGNAL LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def is_buy_signal(open_row, ema20, vwap, ema200):
    if None in (open_row, ema20, vwap, ema200): return False
    high, low, close = float(open_row['high']), float(open_row['low']), float(open_row['close'])
    if low == 0: return False
    if ((high - low) / low) * 100 > 2.2:              return False   # wide candle
    if ema200 >= ema20:                                return False   # wrong stack
    if ((ema20 - ema200) / ema200) * 100 > 1.5:       return False   # too extended
    if close <= vwap:                                  return False   # below vwap
    if close <= ema20:                                 return False   # below ema20
    if ((close - ema20) / ema20) * 100 > 2.0:         return False   # overextended
    return True


def is_sell_signal(open_row, ema20, vwap, ema200):
    if None in (open_row, ema20, vwap, ema200): return False
    high, low, close = float(open_row['high']), float(open_row['low']), float(open_row['close'])
    if low == 0: return False
    if ((high - low) / low) * 100 > 2.2:              return False
    if ema200 <= ema20:                                return False
    if ((ema200 - ema20) / ema200) * 100 > 1.5:       return False
    if close >= vwap:                                  return False
    if close >= ema20:                                 return False
    if ((ema20 - close) / ema20) * 100 > 2.0:         return False
    return True


def calc_score(signal, ltp, volume, avg_volume, pct_change, ema200):
    score = 2
    if volume and avg_volume and volume > avg_volume * 1.2:  score += 1
    change_val = float(pct_change or 0)
    if signal == "BUY"  and change_val >  0.5:               score += 1
    elif signal == "SELL" and change_val < -0.5:             score += 1
    if ema200 and ltp:
        pct = abs((ltp - ema200) / ema200 * 100)
        if pct <= 1.5:   score += 2
        elif pct <= 3.5: score += 1
    return min(score, 6)


def should_remove_stock(signal, latest_close, ema20_live):
    if not signal or not latest_close or not ema20_live: return False
    if signal == "BUY"  and latest_close < ema20_live:   return True
    if signal == "SELL" and latest_close > ema20_live:   return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: ANALYSIS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

# Minimum candles needed for EMA200 — Yahoo 5m gives ~75 candles/day
# 3 trading days × 75 = 225 candles to comfortably compute EMA200
MIN_CANDLES_TOTAL   = 50    # absolute minimum to even attempt analysis
MIN_CANDLES_AT_OPEN = 20    # minimum candles before 9:15 to compute EMAs
EMA_PERIOD_FAST     = 20
EMA_PERIOD_SLOW     = 200


def analyze_stock(stock, df_candles, is_refresh=False):
    symbol = stock['symbol']
    sector = stock['sector']
    log    = st.session_state.scan_log

    if df_candles is None or df_candles.empty:
        log.append(f"❌ {symbol}: No data returned from API")
        return None

    if len(df_candles) < MIN_CANDLES_TOTAL:
        log.append(f"❌ {symbol}: Too few candles ({len(df_candles)}) — need ≥ {MIN_CANDLES_TOTAL}")
        return None

    # Live indicators (current state)
    ema20_live  = calc_ema(df_candles['close'], EMA_PERIOD_FAST)
    ema200_live = calc_ema(df_candles['close'], EMA_PERIOD_SLOW)
    vwap_live   = calc_vwap(df_candles)

    if None in (ema20_live, ema200_live, vwap_live):
        log.append(f"❌ {symbol}: Could not compute indicators (ema20={ema20_live}, ema200={ema200_live}, vwap={vwap_live})")
        return None

    last_row   = df_candles.iloc[-1]
    ltp        = float(last_row['close'])
    last_vol   = float(last_row['volume'])
    prev_close = fetch_daily_prev_close(symbol)
    pct_change = ((ltp - prev_close) / prev_close * 100) if prev_close else 0.0
    avg_vol    = df_candles['volume'].mean()

    # ── REFRESH PATH ──
    if is_refresh:
        for r in st.session_state.results:
            if r['symbol'] == symbol:
                if should_remove_stock(r['signal'], ltp, ema20_live):
                    st.session_state.results = [x for x in st.session_state.results if x['symbol'] != symbol]
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

    # ── INITIAL SCAN PATH ──
    target_date = get_ist_today_str() if is_market_open() else get_last_trading_day_str()
    opening_idx, open_row = find_opening_candle_index(df_candles, target_date)

    if opening_idx < 0:
        log.append(f"⚠️ {symbol}: No candle found for {target_date} — data may be stale or weekend")
        return None

    candles_at_open = df_candles.iloc[:opening_idx + 1]

    if len(candles_at_open) < MIN_CANDLES_AT_OPEN:
        log.append(f"⚠️ {symbol}: Only {len(candles_at_open)} candles before open — need ≥ {MIN_CANDLES_AT_OPEN}")
        return None

    # Compute EMAs at opening candle (not live — at 9:15 snapshot)
    ema20_at_open  = calc_ema(candles_at_open['close'], EMA_PERIOD_FAST)
    ema200_at_open = calc_ema(candles_at_open['close'], EMA_PERIOD_SLOW)
    vwap_at_open   = calc_vwap(candles_at_open)

    if None in (ema20_at_open, ema200_at_open, vwap_at_open):
        log.append(
            f"⚠️ {symbol}: Indicator compute failed at open "
            f"(candles={len(candles_at_open)}, ema20={ema20_at_open}, ema200={ema200_at_open})"
        )
        return None

    signal = None
    if is_buy_signal(open_row, ema20_at_open, vwap_at_open, ema200_at_open):
        signal = "BUY"
    elif is_sell_signal(open_row, ema20_at_open, vwap_at_open, ema200_at_open):
        signal = "SELL"

    if not signal:
        # Log which specific condition failed for the first failing check
        reasons = []
        h, l, c = float(open_row['high']), float(open_row['low']), float(open_row['close'])
        rng = ((h - l) / l) * 100 if l > 0 else 0
        if rng > 2.2:
            reasons.append(f"candle range too wide ({rng:.2f}%)")
        if ema200_at_open and ema20_at_open:
            gap = abs((ema20_at_open - ema200_at_open) / ema200_at_open) * 100
            if gap > 1.5:
                reasons.append(f"EMA gap too wide ({gap:.2f}%)")
        if not reasons:
            reasons.append("price/VWAP/EMA directional conditions not met")
        log.append(f"— {symbol}: No signal — {', '.join(reasons)}")
        return None

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
    log.append(f"✅ {symbol}: {signal} signal | score={score} | ltp={ltp}")
    st.session_state.results = [x for x in st.session_state.results if x['symbol'] != symbol]
    st.session_state.results.append(result_obj)
    return result_obj


def run_full_scan(watchlist_stocks):
    if not watchlist_stocks:
        st.warning("No stocks in this watchlist. Add stocks via the Watchlist page first.")
        return

    st.session_state.is_scanning = True
    st.session_state.scan_log    = []   # reset debug log
    progress_bar = st.progress(0, text="Initializing scan...")
    total        = len(watchlist_stocks)

    for i, stock in enumerate(watchlist_stocks):
        progress_bar.progress((i + 1) / total, text=f"Scanning {i+1}/{total}: {stock['symbol']}")
        df = fetch_candles_5min(stock['token'], stock['symbol'])
        analyze_stock(stock, df, is_refresh=False)

    if st.session_state.results:
        st.session_state.results.sort(key=lambda x: (0 if x['signal'] == 'BUY' else 1, -x['score']))

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
# SECTION 8: UI
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Trade Sentry - Scanner", layout="wide")

# ── SIDEBAR: only the selector + summary count ──
st.sidebar.markdown("### 📋 Watchlist Source")
selected_wl = st.sidebar.selectbox(
    "Target Scanning Watchlist",
    WATCHLIST_NAMES,
    index=WATCHLIST_NAMES.index(st.session_state.selected_watchlist),
)
if selected_wl != st.session_state.selected_watchlist:
    st.session_state.selected_watchlist = selected_wl
    st.session_state.results            = []
    st.session_state.scan_log           = []
    st.rerun()

# Load stocks
stocks_to_scan = load_watchlist_stocks(st.session_state.selected_watchlist)

# Sidebar: just the count — NO per-stock list here
st.sidebar.markdown(
    f"**{len(stocks_to_scan)} stocks** loaded from "
    f"**{st.session_state.selected_watchlist}** watchlist"
)

# ── MAIN PAGE ──
st.markdown("## 🛡 Trade Sentry — Momentum Scanner")
st.markdown(
    f"Scanning **{st.session_state.selected_watchlist}** watchlist · "
    f"`{len(stocks_to_scan)}` stocks loaded"
)

# ── Loaded stocks list on MAIN page (not sidebar) ──
if stocks_to_scan:
    with st.expander(f"📋 View {len(stocks_to_scan)} loaded stocks", expanded=False):
        cols = st.columns(5)
        for i, s in enumerate(stocks_to_scan):
            cols[i % 5].markdown(f"`{s['symbol']}` — {s['sector']}")

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
        st.session_state.results  = []
        st.session_state.scan_log = []
        st.success("Scanner cleared.")
with col_ctrl4:
    auto_on = st.checkbox("Toggle Auto-Refresh (5-Min Loops)", value=st.session_state.auto_refresh)
    if auto_on != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto_on

if len(stocks_to_scan) == 0:
    st.info(
        f"⚠️ The **{st.session_state.selected_watchlist}** watchlist is empty. "
        "Add stocks from the Watchlist page first."
    )

# ── Filter Panel ──
st.write("### ⚙ REFINE CONFIGURATION FILTERS")
col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
with col_f1:  filter_sig       = st.selectbox("Signal Vector Type", ["ALL", "BUY", "SELL"])
with col_f2:  filter_min_vol   = st.text_input("Volume Threshold (≥)", value="")
with col_f3:  filter_ema20     = st.text_input("Max EMA20 Distance % (≤)", value="")
with col_f4:  filter_ema200    = st.text_input("Max EMA200 Distance % (≤)", value="")
with col_f5:  filter_min_score = st.text_input("Min Conviction Score (≥)", value="")
toggle_body_wick = st.toggle("Filter Strong Candles (Body > 50% of Range)")

# ── Filtering ──
processed_view_list = list(st.session_state.results)

all_sectors     = sorted(set(r['sector'] for r in processed_view_list))
selected_sector = st.radio("Sector Filter", ["ALL"] + all_sectors, horizontal=True)
if selected_sector != "ALL":
    processed_view_list = [r for r in processed_view_list if r['sector'] == selected_sector]

if filter_sig != "ALL":
    processed_view_list = [r for r in processed_view_list if r['signal'] == filter_sig]

if filter_min_vol.strip():
    try:    processed_view_list = [r for r in processed_view_list if r['volume'] >= float(filter_min_vol)]
    except: pass

if filter_ema20.strip():
    try:    processed_view_list = [r for r in processed_view_list if abs((r['ltp']-r['ema20'])/r['ema20']*100) <= float(filter_ema20)]
    except: pass

if filter_ema200.strip():
    try:    processed_view_list = [r for r in processed_view_list if abs((r['ltp']-r['ema200'])/r['ema200']*100) <= float(filter_ema200)]
    except: pass

if filter_min_score.strip():
    try:    processed_view_list = [r for r in processed_view_list if r['score'] >= float(filter_min_score)]
    except: pass

if toggle_body_wick:
    processed_view_list = [
        r for r in processed_view_list
        if (r['highPrice'] - r['lowPrice']) > 0
        and abs(r['closePrice'] - r['openPrice']) / (r['highPrice'] - r['lowPrice']) >= 0.5
    ]

# ── Results Count ──
st.write(f"#### 🎯 Actionable Targets: `{len(processed_view_list)}` / `{len(st.session_state.results)}` signals")

# ── Debug Log (shown after scan even if 0 results) ──
if st.session_state.scan_log:
    signals_found = [l for l in st.session_state.scan_log if l.startswith("✅")]
    skipped       = [l for l in st.session_state.scan_log if not l.startswith("✅")]
    with st.expander(
        f"🔍 Scan Debug Log — {len(signals_found)} signals found, {len(skipped)} skipped",
        expanded=(len(signals_found) == 0)   # auto-open if 0 results so user can see why
    ):
        for line in st.session_state.scan_log:
            st.markdown(line)

# ── Signal Cards ──
if not processed_view_list:
    if st.session_state.results:
        st.info("🔍 No signals match your current filters.")
    elif not st.session_state.scan_log:
        st.info("🔍 Run a scan to see results.")
else:
    for item in processed_view_list:
        accent     = "🟢 BUY" if item['signal'] == "BUY" else "🔴 SELL"
        border_clr = "#00e676" if item['signal'] == "BUY" else "#ff4444"
        pct_clr    = "#00e676" if item['pctChange'] >= 0 else "#ff4444"
        mins_ago   = int((time.time() - item['timestamp']) // 60)
        age_str    = "just now" if mins_ago < 1 else f"{mins_ago}m ago"

        with st.container():
            st.markdown(
                f"""<div style="border-left:5px solid {border_clr};background:#1a1a1a;
                               padding:12px;margin-bottom:10px;border-radius:4px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <span style="font-size:18px;font-weight:bold;color:#fff;font-family:monospace;">
                            {item['symbol']}
                            <span style="font-size:11px;background:#333;padding:2px 6px;
                                         border-radius:3px;color:#aaa;">{item['sector']}</span>
                        </span>
                        <span style="font-size:16px;font-weight:bold;color:{border_clr};
                                     font-family:monospace;">{accent}</span>
                    </div>
                    <hr style="margin:8px 0;border-color:#333;"/>
                    <div style="display:flex;justify-content:space-between;font-size:14px;">
                        <div>LTP: <b style="color:#fff;">₹{item['ltp']}</b>
                             <span style="color:{pct_clr};font-weight:bold;margin-left:8px;">{item['pctChange']}%</span>
                        </div>
                        <div style="color:#aaa;">
                            EMA20:<span style="color:#fff;"> {item['ema20']}</span> |
                            VWAP:<span style="color:#ffb300;"> {item['vwap']}</span> |
                            EMA200:<span style="color:#fff;"> {item['ema200']}</span>
                        </div>
                    </div>
                    <div style="display:flex;justify-content:space-between;font-size:11px;color:#666;margin-top:6px;">
                        <span>Signal: {age_str}</span>
                        <span style="color:{border_clr};font-weight:bold;">Score: {item['score']}/6.0</span>
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

# ── Auto-Refresh ──
if st.session_state.auto_refresh:
    time.sleep(300)
    run_refresh_scan(stocks_to_scan)
    st.rerun()
