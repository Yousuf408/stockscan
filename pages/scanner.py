# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — scanner.py  v2.3
#  Changes from v2.2:
#    - Full UI redesign: Variation B layout
#      • Header card with live Buy / Sell / Total counters
#      • Flat action-button row (Run scan · Refresh · Clear · Filters)
#      • Collapsible filter panel behind "Filters" button
#      • Compact sector pills
#      • Wider signal cards with score progress-bar
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

# ── Core engine import ──
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from core import calc_ema, load_watchlist, save_watchlist

# ── Import from stocks.py ──
try:
    from stocks import get_stock_token, get_stock_sector
except ImportError:
    def get_stock_token(sym): return None
    def get_stock_sector(sym): return "GENERAL"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: WATCHLIST FILE INTEGRATION
# ─────────────────────────────────────────────────────────────────────────────

WATCHLIST_NAMES = ["Today", "Yesterday", "New"]


def load_watchlist_stocks(tab: str) -> list:
    try:
        raw = load_watchlist(tab)
        if not raw:
            return []
        stocks = []
        for s in raw:
            sym = s.get("symbol", "").strip().upper()
            if not sym:
                continue
            sym    = sym.replace(".NS", "").replace(".BO", "").split("-")[0].split(".")[0].strip()
            token  = s.get("token")  or get_stock_token(sym)  or ""
            sector = s.get("sector") or get_stock_sector(sym) or "GENERAL"
            stocks.append({
                "symbol":   sym,
                "token":    str(token),
                "sector":   sector,
                "exchange": s.get("exchange", "NS"),
            })
        return stocks
    except Exception as e:
        st.error(f"Watchlist load error: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────

for _k, _v in [
    ("results",              []),
    ("is_scanning",          False),
    ("selected_watchlist",   "Today"),
    ("auto_refresh",         False),
    ("scan_log",             []),
    ("last_auto_refresh",    0),
    ("show_filters",         False),   # NEW — filter panel toggle
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: DATE & TIME
# ─────────────────────────────────────────────────────────────────────────────

IST = pytz.timezone("Asia/Kolkata")

def get_ist_now() -> datetime:
    return datetime.now(pytz.utc).astimezone(IST)

def get_ist_today_str() -> str:
    return get_ist_now().strftime("%Y-%m-%d")

def get_last_trading_day_str() -> str:
    dt = get_ist_now() - timedelta(days=1)
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")

def is_market_open() -> bool:
    now  = get_ist_now()
    mins = now.hour * 60 + now.minute
    return (9 * 60 + 15) <= mins <= (15 * 60 + 30)

def get_ist_time_now() -> str:
    return get_ist_now().strftime("%H:%M")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch_candles_5min(symbol_token: str, symbol: str, angel_auth=None):
    is_open    = is_market_open()
    end_date   = get_ist_today_str() if is_open else get_last_trading_day_str()
    start_date = (get_ist_now() - timedelta(days=20)).strftime("%Y-%m-%d")
    clean_sym  = symbol.split("-")[0].split(".")[0].strip()

    if angel_auth and angel_auth.get("session"):
        try:
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
                "from":        f"{start_date} 09:15",
                "to":          f"{end_date} 15:30" if not is_open else f"{end_date} {get_ist_time_now()}",
            }
            res = requests.post(
                "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData",
                json=payload, headers=headers, timeout=7,
            )
            if res.status_code == 200:
                data = res.json()
                if data.get("status") is True and isinstance(data.get("data"), list):
                    rows = []
                    for c in data["data"]:
                        if isinstance(c, list) and len(c) >= 6:
                            rows.append([str(c[0]), float(c[1]), float(c[2]),
                                         float(c[3]), float(c[4]), float(c[5])])
                    if rows:
                        return rows
        except Exception:
            pass

    return fetch_yahoo_fallback_candles(clean_sym)


def fetch_yahoo_fallback_candles(symbol: str):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?interval=5m&range=20d"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code != 200:
            return None

        result = res.json().get("chart", {}).get("result", [None])[0]
        if not result:
            return None

        timestamps = result.get("timestamp", [])
        quote      = result.get("indicators", {}).get("quote", [{}])[0]
        if not timestamps or not quote:
            return None

        rows = []
        for i, ts in enumerate(timestamps):
            o = quote.get("open",   [None])[i]
            h = quote.get("high",   [None])[i]
            l = quote.get("low",    [None])[i]
            c = quote.get("close",  [None])[i]
            v = quote.get("volume", [0])[i] or 0
            if None in (o, h, l, c):
                continue
            dt_ist = datetime.fromtimestamp(ts, tz=pytz.utc).astimezone(IST)
            ts_str = dt_ist.strftime("%Y-%m-%d %H:%M:%S")
            rows.append([ts_str, float(o), float(h), float(l), float(c), float(v)])

        return rows if rows else None
    except Exception:
        return None


@st.cache_data(ttl=1800)
def fetch_daily_prev_close(symbol: str):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS?interval=1d&range=10d"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        if res.status_code != 200:
            return None
        closes = (
            res.json()
            .get("chart", {}).get("result", [{}])[0]
            .get("indicators", {}).get("quote", [{}])[0]
            .get("close", [])
        )
        valid = [c for c in closes if c is not None]
        return valid[-2] if len(valid) >= 2 else None
    except Exception:
        return None

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: TECHNICAL INDICATORS
# ─────────────────────────────────────────────────────────────────────────────

def calc_vwap(candles: list):
    if not candles:
        return None

    last_ts      = str(candles[-1][0])
    session_date = last_ts.split(" ")[0]

    tpv_sum = vol_sum = 0.0
    session_count = 0

    for c in candles:
        ts_date = str(c[0]).split(" ")[0]
        if ts_date == session_date:
            h, l, close, vol = float(c[2]), float(c[3]), float(c[4]), float(c[5])
            tp       = (h + l + close) / 3
            tpv_sum += tp * vol
            vol_sum += vol
            session_count += 1

    if vol_sum == 0 or session_count == 0:
        for c in candles[-75:]:
            h, l, close, vol = float(c[2]), float(c[3]), float(c[4]), float(c[5])
            tp       = (h + l + close) / 3
            tpv_sum += tp * vol
            vol_sum += vol

    return tpv_sum / vol_sum if vol_sum > 0 else None

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5.9: FIND OPENING CANDLE
# ─────────────────────────────────────────────────────────────────────────────

def find_opening_candle_index(candles: list) -> int:
    if not candles:
        return -1

    target_date = get_ist_today_str() if is_market_open() else get_last_trading_day_str()

    for i, c in enumerate(candles):
        ts        = str(c[0])
        date_part = ts.split(" ")[0]
        time_part = ts.split(" ")[1] if " " in ts else ""
        if date_part == target_date and time_part.startswith("09:15"):
            return i

    return -1

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: SIGNAL LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def is_buy_signal(open_candle, ema20, vwap, ema200) -> bool:
    if None in (open_candle, ema20, vwap, ema200):
        return False
    high  = float(open_candle[2])
    low   = float(open_candle[3])
    close = float(open_candle[4])
    if low == 0:
        return False
    candle_range = ((high - low) / low) * 100
    if candle_range > 2.2: return False
    if ema200 >= ema20: return False
    pct_ema_gap = ((ema20 - ema200) / ema200) * 100
    if pct_ema_gap > 1.5: return False
    if close <= vwap: return False
    if close <= ema20: return False
    if close <= ema200: return False
    pct_from_ema20 = ((close - ema20) / ema20) * 100
    if pct_from_ema20 > 2.0: return False
    return True


def is_sell_signal(open_candle, ema20, vwap, ema200) -> bool:
    if None in (open_candle, ema20, vwap, ema200):
        return False
    high  = float(open_candle[2])
    low   = float(open_candle[3])
    close = float(open_candle[4])
    if low == 0:
        return False
    candle_range = ((high - low) / low) * 100
    if candle_range > 2.2: return False
    if ema200 <= ema20: return False
    pct_ema_gap = ((ema200 - ema20) / ema200) * 100
    if pct_ema_gap > 1.5: return False
    if close >= vwap: return False
    if close >= ema20: return False
    if close >= ema200: return False
    pct_from_ema20 = ((ema20 - close) / ema20) * 100
    if pct_from_ema20 > 2.0: return False
    return True


def calc_score(signal, ltp, volume, avg_volume, pct_change, ema200) -> float:
    score = 2
    if volume and avg_volume and volume > avg_volume * 1.2: score += 1
    change_val = float(pct_change or 0)
    if signal == "BUY"  and change_val >  0.5: score += 1
    elif signal == "SELL" and change_val < -0.5: score += 1
    if ema200 and ltp:
        pct = abs((ltp - ema200) / ema200 * 100)
        if pct <= 1.5:   score += 2
        elif pct <= 3.5: score += 1
    return min(score, 6)


def check_sl_hit(signal: str, candles: list, ema20_live: float) -> bool:
    """
    Returns True if last 2 consecutive candles closed on the wrong side of EMA20.
    BUY signal  → SL hit if last 2 closes < EMA20
    SELL signal → SL hit if last 2 closes > EMA20
    """
    if not signal or not ema20_live or not candles or len(candles) < 2:
        return False

    last_two_closes = [float(c[4]) for c in candles[-2:]]

    if signal == "BUY":
        return all(c < ema20_live for c in last_two_closes)
    if signal == "SELL":
        return all(c > ema20_live for c in last_two_closes)

    return False


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: ANALYSIS ENGINE
# ─────────────────────────────────────────────────────────────────────────────

MIN_CANDLES_TOTAL   = 800
MIN_CANDLES_AT_OPEN = 200


def analyze_stock(stock: dict, candles: list, is_refresh: bool = False):
    symbol = stock["symbol"]
    sector = stock["sector"]
    log    = st.session_state.scan_log

    if not candles:
        log.append(f"❌ {symbol}: No data returned")
        return None

    total = len(candles)
    if total < MIN_CANDLES_TOTAL:
        log.append(f"❌ {symbol}: Only {total} candles — need ≥ {MIN_CANDLES_TOTAL} (20 trading days)")
        return None

    ema20_live  = calc_ema(candles, 20)
    ema200_live = calc_ema(candles, 200)
    vwap_live   = calc_vwap(candles)

    if None in (ema20_live, ema200_live, vwap_live):
        log.append(f"❌ {symbol}: Could not compute live indicators")
        return None

    last_candle = candles[-1]
    ltp         = float(last_candle[4])
    last_vol    = float(last_candle[5])
    avg_vol     = sum(float(c[5]) for c in candles) / len(candles)
    prev_close  = fetch_daily_prev_close(symbol)
    pct_change  = ((ltp - prev_close) / prev_close * 100) if prev_close else 0.0

    # ── REFRESH PATH ──
    if is_refresh:
        for r in st.session_state.results:
            if r["symbol"] == symbol:
                sl_hit = check_sl_hit(r["signal"], candles, ema20_live)
                r.update({
                    "ltp":       round(ltp, 2),
                    "ema20":     round(ema20_live, 2),
                    "ema200":    round(ema200_live, 2),
                    "vwap":      round(vwap_live, 2),
                    "pctChange": round(pct_change, 2),
                    "sl_hit":    sl_hit,
                })
                if sl_hit:
                    log.append(f"🔴 {symbol}: SL Hit — 2 consecutive candles crossed EMA20")
                return r
        return None

    # ── INITIAL SCAN PATH ──
    opening_idx = find_opening_candle_index(candles)
    if opening_idx < 0:
        target = get_ist_today_str() if is_market_open() else get_last_trading_day_str()
        log.append(f"⚠️ {symbol}: No 9:15 candle found for {target}")
        return None

    open_candle     = candles[opening_idx]
    candles_at_open = candles[:opening_idx + 1]

    if len(candles_at_open) < MIN_CANDLES_AT_OPEN:
        log.append(
            f"⚠️ {symbol}: Only {len(candles_at_open)} candles before 9:15 — "
            f"need ≥ {MIN_CANDLES_AT_OPEN} for EMA200"
        )
        return None

    ema20_at_open  = calc_ema(candles_at_open, 20)
    ema200_at_open = calc_ema(candles_at_open, 200)
    vwap_at_open   = calc_vwap(candles_at_open)

    if None in (ema20_at_open, ema200_at_open, vwap_at_open):
        log.append(f"⚠️ {symbol}: Could not compute at-open indicators")
        return None

    log.append(
        f"📊 {symbol} @ 9:15 → "
        f"EMA200:{ema200_at_open:.2f} EMA20:{ema20_at_open:.2f} "
        f"VWAP:{vwap_at_open:.2f} Close:{float(open_candle[4]):.2f}"
    )

    signal = None
    if is_buy_signal(open_candle, ema20_at_open, vwap_at_open, ema200_at_open):
        signal = "BUY"
    elif is_sell_signal(open_candle, ema20_at_open, vwap_at_open, ema200_at_open):
        signal = "SELL"

    if not signal:
        reasons = []
        h, l, c = float(open_candle[2]), float(open_candle[3]), float(open_candle[4])
        rng = ((h - l) / l * 100) if l > 0 else 0
        if rng > 2.2:
            reasons.append(f"candle range {rng:.2f}% > 2.2%")
        if ema200_at_open and ema20_at_open:
            gap = abs(ema20_at_open - ema200_at_open) / ema200_at_open * 100
            if gap > 1.5:
                reasons.append(f"EMA gap {gap:.2f}% > 1.5%")
        if not reasons:
            reasons.append("price/VWAP/EMA directional conditions not met")
        log.append(f"— {symbol}: No signal — {', '.join(reasons)}")
        return None

    score = calc_score(signal, ltp, last_vol, avg_vol, pct_change, ema200_live)
    result = {
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
        "openPrice":  round(float(open_candle[1]), 2),
        "highPrice":  round(float(open_candle[2]), 2),
        "lowPrice":   round(float(open_candle[3]), 2),
        "closePrice": round(float(open_candle[4]), 2),
        "sl_hit":     False,
    }
    log.append(f"✅ {symbol}: {signal} | score={score:.1f} | ltp={ltp:.2f}")

    st.session_state.results = [x for x in st.session_state.results if x["symbol"] != symbol]
    st.session_state.results.append(result)
    return result


def run_full_scan(watchlist_stocks: list):
    if not watchlist_stocks:
        st.warning("No stocks in this watchlist. Add stocks from the Watchlist page first.")
        return

    st.session_state.is_scanning = True
    st.session_state.scan_log    = []
    progress_bar = st.progress(0, text="Initialising scan...")
    total        = len(watchlist_stocks)

    for i, stock in enumerate(watchlist_stocks):
        progress_bar.progress((i + 1) / total, text=f"Scanning {i+1}/{total}: {stock['symbol']}")
        candles = fetch_candles_5min(stock["token"], stock["symbol"])
        analyze_stock(stock, candles, is_refresh=False)

    if st.session_state.results:
        st.session_state.results.sort(
            key=lambda x: (0 if x["signal"] == "BUY" else 1, -x["score"])
        )

    progress_bar.empty()
    st.session_state.is_scanning = False


def run_refresh_scan(watchlist_stocks: list):
    if not st.session_state.results:
        return
    for r in st.session_state.results:
        matched = next((s for s in watchlist_stocks if s["symbol"] == r["symbol"]), None)
        if matched:
            candles = fetch_candles_5min(matched["token"], matched["symbol"])
            analyze_stock(matched, candles, is_refresh=True)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: UI  — Variation B
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Trade Sentry — Scanner", layout="wide")

from styles import apply_styles, sidebar_brand
apply_styles()
sidebar_brand()

# ── Global style overrides for Variation B ──
st.markdown("""
<style>
/* ── reset card gap ── */
div[data-testid="stVerticalBlock"] > div { gap: 0 !important; }

/* ── action buttons ── */
.ts-btn-row { display:flex; gap:8px; align-items:center; margin:12px 0 4px; }
.ts-btn {
    display:inline-flex; align-items:center; gap:6px;
    padding:7px 16px; border-radius:8px; font-size:13px; font-weight:600;
    cursor:pointer; border:1.5px solid #d0d0d0; background:#ffffff;
    color:#333333; text-decoration:none; white-space:nowrap;
    font-family: 'SF Pro Text', system-ui, sans-serif;
    transition: background 0.15s, border-color 0.15s;
}
.ts-btn:hover { background:#f5f5f5; border-color:#aaaaaa; }
.ts-btn-primary { background:#111111; color:#ffffff; border-color:#111111; }
.ts-btn-primary:hover { background:#333333; border-color:#333333; }
.ts-signals-pill {
    margin-left:auto; font-size:12px; font-weight:600;
    background:#f0f0f0; color:#555555; padding:6px 14px;
    border-radius:20px; white-space:nowrap;
}

/* ── header card ── */
.ts-header-card {
    background:#ffffff; border:1px solid #e8e8e8;
    border-radius:12px; padding:18px 24px;
    margin-bottom:4px;
}
.ts-header-title { font-size:22px; font-weight:700; color:#111111; margin:0; }
.ts-header-sub   { font-size:13px; color:#888888; margin:4px 0 0; }
.ts-counter-val { font-size:28px; font-weight:800; font-family:monospace; }
.ts-counter-lbl { font-size:11px; color:#aaaaaa; font-weight:500; margin-top:2px; }

/* ── sector pills override ── */
div[data-testid="stPills"] button {
    font-size:12px !important;
    padding:4px 12px !important;
    border-radius:20px !important;
    font-weight:600 !important;
}

/* ── signal card ── */
.ts-card {
    background:#ffffff; border:1px solid #ebebeb;
    border-left:4px solid #ebebeb;
    border-radius:10px; padding:8px 12px;
    margin-bottom:6px;
}
.ts-card-top {
    display:flex; justify-content:space-between;
    align-items:center; margin-bottom:6px;
}
.ts-card-left  { display:flex; align-items:center; gap:6px; }
.ts-card-right { display:flex; align-items:center; gap:8px; }
.ts-sym   { font-size:14px; font-weight:800; color:#111111; font-family:monospace; }
.ts-chip  {
    font-size:9px; background:#f3f3f3; color:#666666;
    padding:1px 6px; border-radius:3px; font-weight:600;
}
.ts-badge {
    font-size:10px; font-weight:700; padding:2px 8px;
    border-radius:5px; font-family:monospace;
}
.ts-badge-buy  { color:#1a9c4a; background:#e8f8ee; border:1px solid #a8dfc0; }
.ts-badge-sell { color:#c0392b; background:#fdecea; border:1px solid #f5b8b5; }
.ts-badge-slhit{ color:#d04a00; background:#fff1eb; border:1px solid #ffcdb3; }
.ts-price { font-size:13px; font-weight:700; color:#111111; font-family:monospace; }
.ts-pct   { font-size:12px; font-weight:700; margin-left:4px; }
.ts-meta  {
    font-size:12px; color:#888888; font-family:monospace;
    display:flex; gap:12px; align-items:center;
    margin-bottom:6px;
}
.ts-meta span { color:#444444; font-weight:600; }
/* ── score bar ── */
.ts-score-row {
    display:flex; align-items:center; gap:8px;
}
.ts-score-bar-bg {
    flex:1; height:4px; background:#eeeeee; border-radius:2px; overflow:hidden;
}
.ts-score-bar-fill {
    height:100%; border-radius:2px;
    transition: width 0.4s ease;
}
.ts-score-lbl {
    font-size:10px; font-weight:700; font-family:monospace;
    white-space:nowrap;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Watchlist selector will be in button row (see below)
# ─────────────────────────────────────────────────────────────────────────────

stocks_to_scan = load_watchlist_stocks(st.session_state.selected_watchlist)
mkt_open       = is_market_open()
mkt_label      = "Market open" if mkt_open else "Market closed"
ist_time_str   = get_ist_now().strftime("%I:%M %p IST").lstrip("0")

# ─────────────────────────────────────────────────────────────────────────────
# HEADER CARD — title + subtitle LEFT | counters RIGHT
# NOTE: Counters will be updated AFTER filters are applied (see below)
# ─────────────────────────────────────────────────────────────────────────────

# Placeholder - will be calculated after filters
buy_count   = 0
sell_count  = 0
sl_hit_count = 0
total_count = 0

# ─────────────────────────────────────────────────────────────────────────────
# COLLAPSIBLE FILTER PANEL (place before header so filters are available)
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.show_filters:
    with st.container(border=True):
        st.markdown("**⚙ Refine Filters**")
        col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
        with col_f1:  filter_sig       = st.selectbox("Signal",  ["ALL", "BUY", "SELL"], key="f_sig")
        with col_f2:  filter_min_vol   = st.text_input("VOL ≥",  value="",               key="f_vol")
        with col_f3:  filter_ema20     = st.text_input("EMA20 % from LTP ≤", value="",   key="f_e20")
        with col_f4:  filter_ema200    = st.text_input("EMA200 % from LTP ≤", value="",  key="f_e200")
        with col_f5:  filter_min_score = st.text_input("Score ≥", value="",              key="f_score")
        tog1, tog2, tog3 = st.columns(3)
        with tog1: toggle_body_wick = st.toggle("Body > Wick (≥50% of range)", key="f_bw")
        with tog2: toggle_hide_sl   = st.toggle("Hide SL Hit stocks",           key="f_sl", value=False)
        with tog3: auto_on          = st.checkbox("Auto-Refresh (5-min loops)", value=st.session_state.auto_refresh, key="f_ar")
        if auto_on != st.session_state.auto_refresh:
            st.session_state.auto_refresh = auto_on
else:
    filter_sig       = "ALL"
    filter_min_vol   = ""
    filter_ema20     = ""
    filter_ema200    = ""
    filter_min_score = ""
    toggle_body_wick = False
    toggle_hide_sl   = False

# ─────────────────────────────────────────────────────────────────────────────
# APPLY FILTERS
# ─────────────────────────────────────────────────────────────────────────────
view = list(st.session_state.results)

if filter_sig != "ALL":
    view = [r for r in view if r["signal"] == filter_sig]
if filter_min_vol.strip():
    try:    view = [r for r in view if r["volume"] >= float(filter_min_vol)]
    except: pass
if filter_ema20.strip():
    try:    view = [r for r in view if abs((r["ltp"]-r["ema20"])/r["ema20"]*100) <= float(filter_ema20)]
    except: pass
if filter_ema200.strip():
    try:    view = [r for r in view if abs((r["ltp"]-r["ema200"])/r["ema200"]*100) <= float(filter_ema200)]
    except: pass
if filter_min_score.strip():
    try:    view = [r for r in view if r["score"] >= float(filter_min_score)]
    except: pass
if toggle_body_wick:
    view = [
        r for r in view
        if (r["highPrice"] - r["lowPrice"]) > 0
        and abs(r["closePrice"] - r["openPrice"]) / (r["highPrice"] - r["lowPrice"]) >= 0.5
    ]
if toggle_hide_sl:
    view = [r for r in view if not r.get("sl_hit", False)]

# ─────────────────────────────────────────────────────────────────────────────
# CALCULATE HEADER COUNTS FROM FILTERED VIEW (after all filters applied)
# ─────────────────────────────────────────────────────────────────────────────
buy_count   = len([r for r in view if r["signal"] == "BUY"])
sell_count  = len([r for r in view if r["signal"] == "SELL"])
sl_hit_count = len([r for r in view if r.get("sl_hit", False)])
total_count = len(view)

# ─────────────────────────────────────────────────────────────────────────────
# REDRAW HEADER WITH UPDATED COUNTS — TOP OF PAGE
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="ts-header-card" style="display:flex;justify-content:space-between;align-items:flex-start;">
  
  <div style="flex:1;">
    <p class="ts-header-title">Momentum scanner</p>
    <p class="ts-header-sub">
      {st.session_state.selected_watchlist}
      &nbsp;·&nbsp; {len(stocks_to_scan)} stocks
      &nbsp;·&nbsp; {mkt_label}
      &nbsp;·&nbsp; {ist_time_str}
    </p>
  </div>

  <div style="display:flex;gap:35px;margin-top:2px;">
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#1a9c4a;font-size:28px;">{buy_count}</div>
      <div class="ts-counter-lbl">Buy</div>
    </div>
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#c0392b;font-size:28px;">{sell_count}</div>
      <div class="ts-counter-lbl">Sell</div>
    </div>
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#d04a00;font-size:28px;">{sl_hit_count}</div>
      <div class="ts-counter-lbl">SL Hit</div>
    </div>
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#111111;font-size:28px;">{total_count}</div>
      <div class="ts-counter-lbl">Total</div>
    </div>
  </div>

</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# ACTION BUTTON ROW — with watchlist selector (AFTER HEADER)
# ─────────────────────────────────────────────────────────────────────────────
btn_col1, btn_col2, btn_col3, btn_col4, btn_col5, btn_col6 = st.columns([1.2, 1.6, 1.6, 1.4, 1.4, 5])

with btn_col1:
    selected_wl = st.selectbox(
        "Watchlist",
        WATCHLIST_NAMES,
        index=WATCHLIST_NAMES.index(st.session_state.selected_watchlist),
        label_visibility="collapsed",
    )
    if selected_wl != st.session_state.selected_watchlist:
        st.session_state.selected_watchlist = selected_wl
        st.session_state.results            = []
        st.session_state.scan_log           = []
        st.rerun()

with btn_col2:
    scan_clicked    = st.button("▷  Run scan",   use_container_width=True,
                                 disabled=len(stocks_to_scan) == 0)
with btn_col3:
    refresh_clicked = st.button("↺  Refresh",    use_container_width=True,
                                 disabled=len(st.session_state.results) == 0)
with btn_col4:
    clear_clicked   = st.button("🗑  Clear",       use_container_width=True)
with btn_col5:
    filter_toggle   = st.button(
        ("✕ Filters" if st.session_state.show_filters else "⚙  Filters"),
        use_container_width=True,
    )
with btn_col6:
    sig_display     = len([r for r in st.session_state.results])
    wl_total        = len(stocks_to_scan)
    st.markdown(
        f'<div style="display:flex;align-items:center;height:38px;">'
        f'<span style="font-size:12px;font-weight:600;background:#f0f0f0;'
        f'color:#555;padding:5px 14px;border-radius:20px;">'
        f'{sig_display} / {wl_total} signals</span></div>',
        unsafe_allow_html=True,
    )

if filter_toggle:
    st.session_state.show_filters = not st.session_state.show_filters
    st.rerun()

if scan_clicked:
    run_full_scan(stocks_to_scan)
if refresh_clicked:
    run_refresh_scan(stocks_to_scan)
if clear_clicked:
    st.session_state.results   = []
    st.session_state.scan_log  = []
    st.session_state.show_filters = False
    st.success("Scanner cleared.")
sector_counts = {}
for r in view:
    sector_counts[r["sector"]] = sector_counts.get(r["sector"], 0) + 1

pill_options = ["All"]
display_label_to_sector = {}
for sector in all_sectors:
    clean = sector.replace("NIFTY ", "")
    label = f"{clean} ({sector_counts.get(sector, 0)})"
    pill_options.append(label)
    display_label_to_sector[label] = sector

selected_sector_label = st.pills("Sector", pill_options, default="All",
                                  label_visibility="collapsed")

if selected_sector_label and selected_sector_label != "All":
    mapped_sector = display_label_to_sector.get(selected_sector_label)
    if mapped_sector:
        view = [r for r in view if r["sector"] == mapped_sector]

# ─────────────────────────────────────────────────────────────────────────────
# SCAN LOG (debug)
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.scan_log:
    signals_found = [l for l in st.session_state.scan_log if l.startswith("✅")]
    with st.expander(
        f"🔍 Scan Log — {len(signals_found)} signals | "
        f"{len(st.session_state.scan_log) - len(signals_found)} skipped",
        expanded=(len(signals_found) == 0),
    ):
        for line in st.session_state.scan_log:
            st.markdown(line)

# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL CARDS  — Variation B layout
# ─────────────────────────────────────────────────────────────────────────────
if not view:
    if st.session_state.results:
        st.info("🔍 No signals match your current filters.")
    elif not st.session_state.scan_log:
        st.info("🔍 Run a scan to see results.")
else:
    sl_hit_count = len([r for r in st.session_state.results if r.get("sl_hit", False)])
    if sl_hit_count:
        st.markdown(
            f'<div style="font-size:12px;color:#d04a00;margin-bottom:6px;">'
            f'🔴 <b>{sl_hit_count}</b> SL Hit stock{"s" if sl_hit_count>1 else ""} in results</div>',
            unsafe_allow_html=True,
        )

    for item in view:
        is_sl_hit    = item.get("sl_hit", False)
        sym          = item["symbol"]
        sig          = item["signal"]
        sector_clean = item["sector"].replace("NIFTY ", "")
        ltp          = item["ltp"]
        pct          = item["pctChange"]
        ema20        = item["ema20"]
        vwap         = item["vwap"]
        ema200       = item["ema200"]
        score        = item["score"]
        mins_ago     = int((time.time() - item["timestamp"]) // 60)
        age_str      = "just now" if mins_ago < 1 else f"{mins_ago}m ago"

        # colours
        if is_sl_hit:
            border_clr   = "#e87040"
            badge_cls    = "ts-badge-slhit"
            badge_label  = "SL HIT"
            bar_color    = "#e87040"
            pct_clr      = "#d04a00"
        elif sig == "BUY":
            border_clr   = "#1a9c4a"
            badge_cls    = "ts-badge-buy"
            badge_label  = "BUY"
            bar_color    = "#1a9c4a"
            pct_clr      = "#1a9c4a" if pct >= 0 else "#c0392b"
        else:
            border_clr   = "#c0392b"
            badge_cls    = "ts-badge-sell"
            badge_label  = "SELL"
            bar_color    = "#c0392b"
            pct_clr      = "#1a9c4a" if pct >= 0 else "#c0392b"

        pct_sign = "+" if pct > 0 else ""
        bar_pct  = int((score / 6) * 100)

        st.markdown(f"""
<div class="ts-card" style="border-left-color:{border_clr};">

  <div class="ts-card-top">
    <div class="ts-card-left">
      <span class="ts-sym">{sym}</span>
      <span class="ts-chip">{sector_clean}</span>
      <span class="ts-badge {badge_cls}">{badge_label}</span>
    </div>
    <div class="ts-card-right">
      <span class="ts-price">₹{ltp:,.2f}</span>
      <span class="ts-pct" style="color:{pct_clr};">{pct_sign}{pct}%</span>
    </div>
  </div>

  <div class="ts-meta">
    <span>EMA20: <span>{ema20}</span></span>
    &nbsp;·&nbsp;
    <span>VWAP: <span style="color:#B36200;">{vwap}</span></span>
    &nbsp;·&nbsp;
    <span>EMA200: <span>{ema200}</span></span>
    &nbsp;·&nbsp;
    <span style="color:#bbbbbb;">{age_str}</span>
  </div>

  <div class="ts-score-row">
    <div class="ts-score-bar-bg">
      <div class="ts-score-bar-fill"
           style="width:{bar_pct}%;background:{bar_color};"></div>
    </div>
    <span class="ts-score-lbl" style="color:{bar_color};">{score}/6</span>
  </div>

</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# AUTO-REFRESH
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.auto_refresh:
    last = st.session_state.get("last_auto_refresh", 0)
    if time.time() - last >= 300:
        run_refresh_scan(stocks_to_scan)
        st.session_state.last_auto_refresh = time.time()
    time.sleep(5)
    st.rerun()
