# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — scanner.py  v2.1
#  Changes from v2.0:
#    - Sector radio → pills with per-sector signal count
#    - Card UI → white background (fields unchanged)
#    - Watchlist selector moved from sidebar to main page
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
    ("results",            []),
    ("is_scanning",        False),
    ("selected_watchlist", "Today"),
    ("auto_refresh",       False),
    ("scan_log",           []),
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
    if close <= ema200: return False   # price must be above EMA200 too
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
    if close >= ema200: return False   # price must be below EMA200 too
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


def should_remove_stock(signal, latest_close, ema20_live) -> bool:
    if not signal or not latest_close or not ema20_live:
        return False
    if signal == "BUY"  and latest_close < ema20_live: return True
    if signal == "SELL" and latest_close > ema20_live: return True
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

    if is_refresh:
        for r in st.session_state.results:
            if r["symbol"] == symbol:
                if should_remove_stock(r["signal"], ltp, ema20_live):
                    st.session_state.results = [x for x in st.session_state.results if x["symbol"] != symbol]
                    log.append(f"🗑 {symbol}: Removed — candle closed on wrong side of EMA20")
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
# SECTION 8: UI
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Trade Sentry — Scanner", layout="wide")

st.markdown("## 🛡 Trade Sentry — Momentum Scanner")

# ── Watchlist selector on main page (not sidebar) ──
wl_col1, wl_col2 = st.columns([3, 9])
with wl_col1:
    selected_wl = st.selectbox(
        "📋 Target Scanning Watchlist",
        WATCHLIST_NAMES,
        index=WATCHLIST_NAMES.index(st.session_state.selected_watchlist),
    )
if selected_wl != st.session_state.selected_watchlist:
    st.session_state.selected_watchlist = selected_wl
    st.session_state.results            = []
    st.session_state.scan_log           = []
    st.rerun()

stocks_to_scan = load_watchlist_stocks(st.session_state.selected_watchlist)

mkt_open  = is_market_open()
mkt_label = "🟢 Market Open" if mkt_open else "🔴 Market Closed"
st.markdown(
    f"Scanning **{st.session_state.selected_watchlist}** watchlist · "
    f"`{len(stocks_to_scan)}` stocks · {mkt_label} · {get_ist_now().strftime('%I:%M %p IST')}"
)

if stocks_to_scan:
    with st.expander(f"📋 {len(stocks_to_scan)} stocks loaded", expanded=False):
        cols = st.columns(5)
        for i, s in enumerate(stocks_to_scan):
            cols[i % 5].markdown(f"`{s['symbol']}` — {s['sector']}")

# ── Control buttons ──
col1, col2, col3, col4 = st.columns([2, 2, 2, 4])
with col1:
    scan_clicked = st.button("🚀 RUN FULL SCAN", use_container_width=True,
                              disabled=len(stocks_to_scan) == 0)
with col2:
    refresh_clicked = st.button("🔄 REFRESH METRICS", use_container_width=True,
                                 disabled=len(st.session_state.results) == 0)
with col3:
    clear_clicked = st.button("🧹 CLEAR RESULTS", use_container_width=True)
with col4:
    auto_on = st.checkbox("Toggle Auto-Refresh (5-Min Loops)",
                          value=st.session_state.auto_refresh)
    if auto_on != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto_on

if scan_clicked:
    run_full_scan(stocks_to_scan)
if refresh_clicked:
    run_refresh_scan(stocks_to_scan)
if clear_clicked:
    st.session_state.results  = []
    st.session_state.scan_log = []
    st.success("Scanner cleared.")

if len(stocks_to_scan) == 0:
    st.info(f"⚠️ **{st.session_state.selected_watchlist}** watchlist is empty. Add stocks from the Watchlist page.")

# ── REFINE FILTERS ──
st.write("### ⚙ REFINE CONFIGURATION FILTERS")
col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
with col_f1:  filter_sig       = st.selectbox("Signal", ["ALL", "BUY", "SELL"])
with col_f2:  filter_min_vol   = st.text_input("VOL ≥", value="")
with col_f3:  filter_ema20     = st.text_input("EMA20 %", value="")
with col_f4:  filter_ema200    = st.text_input("EMA200 %", value="")
with col_f5:  filter_min_score = st.text_input("SCORE ≥", value="")
toggle_body_wick = st.toggle("BODY > WICK (Body > 50% of Range)")

# ── Apply all filters except sector ──
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

# ── SECTOR PILLS with per-sector signal count ──
all_sectors = sorted(set(r["sector"] for r in view))
sector_counts = {}
for r in view:
    sector_counts[r["sector"]] = sector_counts.get(r["sector"], 0) + 1

pill_options = ["ALL"]
display_label_to_sector = {}
for sector in all_sectors:
    clean = sector.replace("NIFTY ", "")
    label = f"{clean} ({sector_counts.get(sector, 0)})"
    pill_options.append(label)
    display_label_to_sector[label] = sector

selected_sector_label = st.pills("Sector", pill_options, default="ALL")

if selected_sector_label and selected_sector_label != "ALL":
    mapped_sector = display_label_to_sector.get(selected_sector_label)
    if mapped_sector:
        view = [r for r in view if r["sector"] == mapped_sector]

# ── Results summary ──
st.markdown(
    f"#### 🎯 N: `{len(view)}` / `{len(st.session_state.results)}` signals  "
    f"· WL: **{st.session_state.selected_watchlist}**"
)

# ── Debug log ──
if st.session_state.scan_log:
    signals_found = [l for l in st.session_state.scan_log if l.startswith("✅")]
    with st.expander(
        f"🔍 Scan Log — {len(signals_found)} signals | "
        f"{len(st.session_state.scan_log) - len(signals_found)} skipped",
        expanded=(len(signals_found) == 0),
    ):
        for line in st.session_state.scan_log:
            st.markdown(line)

# ── Signal cards — WHITE background, same fields ──
if not view:
    if st.session_state.results:
        st.info("🔍 No signals match your current filters.")
    elif not st.session_state.scan_log:
        st.info("🔍 Run a scan to see results.")
else:
    for item in view:
        signal_clr = "#00AA3B" if item["signal"] == "BUY" else "#D32F2F"
        border_clr = "#00AA3B" if item["signal"] == "BUY" else "#D32F2F"
        pct_clr    = "#00AA3B" if item["pctChange"] >= 0 else "#D32F2F"
        mins_ago   = int((time.time() - item["timestamp"]) // 60)
        age_str    = "just now" if mins_ago < 1 else f"{mins_ago}m ago"

        st.markdown(
            f"""<div style="border-left:4px solid {border_clr};
                           background:#ffffff;
                           border:1px solid #e8e8e8;
                           border-left:4px solid {border_clr};
                           padding:10px 14px;
                           margin-bottom:10px;
                           border-radius:6px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div style="display:flex;align-items:center;gap:8px;">
                        <span style="font-size:15px;font-weight:800;color:#111111;font-family:monospace;">{item['symbol']}</span>
                        <span style="font-size:10px;background:#f2f2f2;padding:2px 7px;border-radius:3px;
                                     color:#555555;font-weight:600;">{item['sector'].replace('NIFTY ','')}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="font-size:10px;color:#999999;font-family:monospace;">{age_str}</span>
                        <span style="font-size:12px;font-weight:800;color:{signal_clr};
                                     background:{signal_clr}15;padding:2px 10px;
                                     border-radius:4px;border:1px solid {signal_clr}40;
                                     font-family:monospace;">{item['signal']}</span>
                    </div>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;
                            background:#f8f8f8;padding:6px 8px;border-radius:4px;
                            margin-top:8px;">
                    <div style="font-size:13px;color:#111111;">
                        LTP: <b style="font-family:monospace;">&#8377;{item['ltp']}</b>
                        <span style="color:{pct_clr};font-weight:700;margin-left:6px;">{item['pctChange']}%</span>
                    </div>
                    <div style="font-size:11px;color:#666666;font-family:monospace;">
                        EMA20: <span style="color:#333333;">{item['ema20']}</span> &nbsp;|&nbsp;
                        VWAP: <span style="color:#B36200;">{item['vwap']}</span> &nbsp;|&nbsp;
                        EMA200: <span style="color:#333333;">{item['ema200']}</span>
                    </div>
                </div>
                <div style="display:flex;justify-content:space-between;font-size:10px;
                            color:#999999;margin-top:6px;">
                    <span>Matrix Conviction Score</span>
                    <span style="color:{signal_clr};font-weight:700;font-family:monospace;">{item['score']}/6</span>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

# ── Auto-Refresh ──
if st.session_state.auto_refresh:
    time.sleep(300)
    run_refresh_scan(stocks_to_scan)
    st.rerun()
