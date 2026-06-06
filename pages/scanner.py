# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — scanner.py  v2.4  (debug build)
#  Changes from v2.3:
#    - Added debug_opening_candle() function
#    - Called inside analyze_stock() right after find_opening_candle_index()
#    - Scan Log will now show full candle details + Entry/SL/T1 for every stock
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
from core import calc_ema, load_watchlist, save_watchlist, \
                 load_scanner_results, save_scanner_result, clear_scanner_results

# ── Import from stocks.py ──
try:
    from stocks import get_stock_token, get_stock_sector
except ImportError:
    def get_stock_token(sym): return None
    def get_stock_sector(sym): return "GENERAL"

# ── Auth — soft check only, scanner accessible to all ──
_user_logged_in = bool(st.session_state.get("user_id"))
def _auth_sign_in(email: str, password: str) -> dict:
    try:
        url = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL", "")).rstrip("/")
        key = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY", ""))
        res = requests.post(
            f"{url}/auth/v1/token?grant_type=password",
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=10,
        )
        return res.json()
    except Exception as e:
        return {"error": str(e)}

def _set_session(data: dict):
    user  = data.get("user") or {}
    uid   = user.get("id", "")
    email = user.get("email", "")
    token = data.get("access_token", "")
    st.session_state["user_id"]      = uid
    st.session_state["user_email"]   = email
    st.session_state["access_token"] = token
    # Save server-side session
    try:
        from auth import save_session
        session_token = save_session(token, uid, email)
        st.session_state["session_token"] = session_token
    except Exception as e:
        print(f"[scanner] Session save failed: {e}")

_user_logged_in = bool(st.session_state.get("user_id"))

# Load dynamic watchlist names from Supabase
try:
    from core import get_user_watchlist_names
    if st.session_state.get("user_id"):
        WATCHLIST_NAMES = get_user_watchlist_names()
    else:
        WATCHLIST_NAMES = ["Today", "Yesterday", "New"]
except Exception:
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
    ("show_filters",         False),
    ("db_results_loaded",    False),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

# ── Load today's results from Supabase on first page load — only if logged in ──
if not st.session_state["db_results_loaded"]:
    if st.session_state.get("user_id"):
        db_results = load_scanner_results(st.session_state["selected_watchlist"])
        if db_results:
            st.session_state["results"] = db_results
    st.session_state["db_results_loaded"] = True

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: DATE & TIME
# ─────────────────────────────────────────────────────────────────────────────

IST = pytz.timezone("Asia/Kolkata")

def get_ist_now() -> datetime:
    return datetime.now(pytz.utc).astimezone(IST)

def get_ist_today_str() -> str:
    return get_ist_now().strftime("%Y-%m-%d")

def get_last_trading_day_str() -> str:
    """
    Returns the most recent trading day as YYYY-MM-DD.
    
    KEY FIX: If today is a weekday (Mon-Fri), return TODAY — the market
    just closed but we still want today's 9:15 candle, not yesterday's.
    Only go back to a previous day if today is Saturday or Sunday.
    """
    dt = get_ist_now()
    # Today is a weekday — market ran today, return today's date
    if dt.weekday() < 5:
        return dt.strftime("%Y-%m-%d")
    # Today is weekend — walk back to last Friday
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
                            # Normalize timestamp — AngelOne returns ISO format
                            # e.g. "2026-06-05T09:15:00+05:30" → "2026-06-05 09:15:00"
                            raw_ts = str(c[0])
                            ts_normalized = raw_ts.replace("T", " ")[:19]
                            rows.append([ts_normalized, float(c[1]), float(c[2]),
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
# SECTION 5.10: DEBUG — OPENING CANDLE INSPECTOR
# ─────────────────────────────────────────────────────────────────────────────

def debug_opening_candle(symbol: str, candles: list, opening_idx: int):
    """
    Logs full details of the detected 9:15 opening candle and the
    Entry / SL / T1 values that will be used for this stock.

    Called inside analyze_stock() right after find_opening_candle_index().
    Results appear in the Scan Log expander on the scanner page.
    """
    log = st.session_state.get("scan_log", [])

    if opening_idx < 0:
        log.append(f"🐛 DEBUG [{symbol}] — opening_idx = -1  (no 9:15 candle found)")
        return

    open_candle = candles[opening_idx]

    ts    = open_candle[0]
    o     = float(open_candle[1])
    high  = float(open_candle[2])
    low   = float(open_candle[3])
    close = float(open_candle[4])
    vol   = float(open_candle[5])

    risk             = round(high - low, 2)
    candle_range_pct = round((risk / low * 100) if low > 0 else 0, 3)

    # BUY scenario
    entry_buy  = round(high, 2)
    sl_buy     = round(low, 2)
    target_buy = round(entry_buy + risk, 2)

    # SELL scenario
    entry_sell  = round(low, 2)
    sl_sell     = round(high, 2)
    target_sell = round(entry_sell - risk, 2)

    log.append("━" * 55)
    log.append(f"🐛 DEBUG [{symbol}]  opening_idx={opening_idx}")
    log.append(f"   Timestamp   : {ts}")
    log.append(f"   O={o}  H={high}  L={low}  C={close}  Vol={vol:,.0f}")
    log.append(f"   Candle range: {risk}  ({candle_range_pct}%)")
    log.append(f"   ── BUY scenario ──────────────────")
    log.append(f"      Entry  = HIGH        = {entry_buy}")
    log.append(f"      SL     = LOW         = {sl_buy}")
    log.append(f"      Risk   = H - L       = {risk}")
    log.append(f"      T1     = {entry_buy} + {risk} = {target_buy}")
    log.append(f"   ── SELL scenario ─────────────────")
    log.append(f"      Entry  = LOW         = {entry_sell}")
    log.append(f"      SL     = HIGH        = {sl_sell}")
    log.append(f"      Risk   = H - L       = {risk}")
    log.append(f"      T1     = {entry_sell} - {risk} = {target_sell}")
    log.append(f"   ── Candles around opening_idx ────")

    start = max(0, opening_idx - 2)
    end   = min(len(candles), opening_idx + 3)
    for i in range(start, end):
        c      = candles[i]
        marker = "  ◀ OPENING CANDLE" if i == opening_idx else ""
        log.append(
            f"   [{i:>4}] {c[0]}  "
            f"O={float(c[1]):.2f}  H={float(c[2]):.2f}  "
            f"L={float(c[3]):.2f}  C={float(c[4]):.2f}"
            f"{marker}"
        )
    log.append("━" * 55)

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


def check_sl_hit(signal: str, ltp: float, sl_price: float) -> bool:
    """
    NEW — Price based SL hit.
    Triggers only if LTP actually crosses the SL price level.

    BUY  → SL hit if LTP <= sl_price  (Low of 9:15 candle)
    SELL → SL hit if LTP >= sl_price  (High of 9:15 candle)
    """
    if not signal or ltp is None or sl_price is None:
        return False
    if signal == "BUY":
        return ltp <= sl_price
    if signal == "SELL":
        return ltp >= sl_price
    return False


def calc_entry_target(signal: str, opening_candle: list) -> dict:
    """
    Calculate entry price and 1:1 target for BUY/SELL signals.

    BUY:  Entry = HIGH, SL = LOW,  Target = Entry + (Entry - SL)
    SELL: Entry = LOW,  SL = HIGH, Target = Entry - (SL - Entry)

    Returns: {entry, sl, target, risk}
    """
    if not signal or not opening_candle:
        return None

    high = float(opening_candle[2])
    low  = float(opening_candle[3])

    if signal == "BUY":
        entry  = high
        sl     = low
        risk   = entry - sl
        target = entry + risk
    elif signal == "SELL":
        entry  = low
        sl     = high
        risk   = sl - entry
        target = entry - risk
    else:
        return None

    return {
        "entry":  round(entry,  2),
        "sl":     round(sl,     2),
        "target": round(target, 2),
        "risk":   round(risk,   2),
    }


def check_exit_or_sl_hit(signal: str, ltp: float, entry: float, target: float,
                          sl_price: float, candles: list, ema20_live: float,
                          t1_already_achieved: bool = False,
                          exit_already_triggered: bool = False) -> dict:
    """
    Full trade status engine. Returns one of 5 statuses:

    ACTIVE       — trade is live, nothing triggered yet
    SL_HIT       — LTP crossed the SL price (Low for BUY / High for SELL)
                   only checked BEFORE T1 is achieved
    T1_ACHIEVE   — LTP hit the 1:1 target, locked forever
    EXIT         — after T1 is achieved, last candle closed on wrong side of EMA20
                   BUY  → last candle close < EMA20
                   SELL → last candle close > EMA20
                   Once EXIT triggers it is also locked forever

    Priority order: EXIT > T1_ACHIEVE > SL_HIT > ACTIVE
    SL is NEVER checked after T1 is achieved.
    EXIT is ONLY checked after T1 is achieved.
    """
    if not signal or ltp is None or entry is None or target is None or sl_price is None:
        return {"status": "ACTIVE", "triggered": False}

    # ── 1. EXIT already triggered — lock it forever ──
    if exit_already_triggered:
        return {"status": "EXIT", "triggered": True}

    # ── 2. T1 already achieved — now watch for EXIT via EMA20 candle close ──
    if t1_already_achieved:
        if candles and len(candles) >= 1:
            last_close = float(candles[-1][4])
            if signal == "BUY"  and last_close < ema20_live:
                return {"status": "EXIT", "triggered": True}
            if signal == "SELL" and last_close > ema20_live:
                return {"status": "EXIT", "triggered": True}
        # T1 achieved but EXIT not yet triggered — keep as T1_ACHIEVE
        return {"status": "T1_ACHIEVE", "triggered": True}

    # ── 3. Check if T1 target is hit NOW using LTP ──
    if signal == "BUY"  and ltp >= target:
        return {"status": "T1_ACHIEVE", "triggered": True}
    if signal == "SELL" and ltp <= target:
        return {"status": "T1_ACHIEVE", "triggered": True}

    # ── 4. SL price hit — only before T1 ──
    if signal == "BUY"  and ltp <= sl_price:
        return {"status": "SL_HIT", "triggered": True}
    if signal == "SELL" and ltp >= sl_price:
        return {"status": "SL_HIT", "triggered": True}

    return {"status": "ACTIVE", "triggered": False}


def check_historical_status(signal: str, candles_from_open: list,
                             target: float, sl_price: float,
                             trading_date: str) -> str:
    if not candles_from_open or not signal or not target or not sl_price:
        return "ACTIVE"

    candles_to_check = [
        c for c in candles_from_open[1:]
        if str(c[0]).split(" ")[0] == trading_date
    ]

    if not candles_to_check:
        return "ACTIVE"

    # Entry price = High of 9:15 candle (BUY) or Low of 9:15 candle (SELL)
    entry_price = float(candles_from_open[0][2]) if signal == "BUY" else float(candles_from_open[0][3])

    # Check if entry was ever triggered
    entry_hit = any(
        float(c[2]) >= entry_price if signal == "BUY" else float(c[3]) <= entry_price
        for c in candles_to_check
    )

    if not entry_hit:
        # Check if LTP is within 0.5% of entry price — NEAR_ENTRY
        last_ltp = float(candles_to_check[-1][4])
        pct_from_entry = abs(last_ltp - entry_price) / entry_price * 100
        if pct_from_entry <= 0.5:
            return "NEAR_ENTRY"
        return "NO_ENTRY"

    # Entry triggered — now check T1 and SL candle by candle
    for c in candles_to_check:
        high = float(c[2])
        low  = float(c[3])

        if signal == "BUY"  and high >= target: return "T1_ACHIEVE"
        if signal == "SELL" and low  <= target: return "T1_ACHIEVE"
        if signal == "BUY"  and low  <= sl_price: return "SL_HIT"
        if signal == "SELL" and high >= sl_price: return "SL_HIT"

    return "ACTIVE"


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
                signal   = r.get("signal")
                et       = r.get("entry_target") or {}
                sl_price = et.get("sl")
                t1_val   = et.get("target")

                current_status = r.get("exit_status", "ACTIVE")

                # T1_ACHIEVE and SL_HIT are locked forever — only update prices
                if current_status in ("T1_ACHIEVE", "SL_HIT"):
                    r.update({
                        "ltp":       round(ltp, 2),
                        "ema20":     round(ema20_live, 2),
                        "ema200":    round(ema200_live, 2),
                        "vwap":      round(vwap_live, 2),
                        "pctChange": round(pct_change, 2),
                    })
                    return r

                # Re-run full historical check — same logic as initial scan
                opening_idx = find_opening_candle_index(candles)
                if opening_idx >= 0:
                    trading_date     = get_last_trading_day_str() if not is_market_open() else get_ist_today_str()
                    candles_from_open = candles[opening_idx:]
                    new_status = check_historical_status(
                        signal, candles_from_open,
                        t1_val, sl_price, trading_date
                    )
                else:
                    new_status = current_status

                r.update({
                    "ltp":         round(ltp, 2),
                    "ema20":       round(ema20_live, 2),
                    "ema200":      round(ema200_live, 2),
                    "vwap":        round(vwap_live, 2),
                    "pctChange":   round(pct_change, 2),
                    "sl_hit":      new_status == "SL_HIT",
                    "exit_status": new_status,
                    "t1_achieved": new_status == "T1_ACHIEVE",
                })
                return r
        return None

    # ── INITIAL SCAN PATH ──
    opening_idx = find_opening_candle_index(candles)

    # ── DEBUG: log opening candle details for every stock ──
    debug_opening_candle(symbol, candles, opening_idx)

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

    # Calculate entry and target prices
    entry_target = calc_entry_target(signal, open_candle)

    # Log entry/target clearly for verification
    if entry_target:
        log.append(
            f"🎯 {symbol} {signal} — "
            f"Entry={entry_target['entry']}  "
            f"SL={entry_target['sl']}  "
            f"Risk={entry_target['risk']}  "
            f"T1={entry_target['target']}"
        )

    # ── All candles from 9:15 onwards — same day only ──
    candles_from_open = candles[opening_idx:]
    trading_date      = get_last_trading_day_str() if not is_market_open() else get_ist_today_str()

    # Historical status — scans entire day's candles to find T1/SL
    historical_status = check_historical_status(
        signal,
        candles_from_open,
        entry_target["target"] if entry_target else None,
        entry_target["sl"]     if entry_target else None,
        trading_date,
    )

    sl_hit_now  = historical_status == "SL_HIT"
    t1_achieved = historical_status in ("T1_ACHIEVE", "EXIT")

    result = {
        "symbol":       symbol,
        "sector":       sector or "GENERAL",
        "signal":       signal,
        "ltp":          round(ltp, 2),
        "ema20":        round(ema20_live, 2),
        "ema200":       round(ema200_live, 2),
        "vwap":         round(vwap_live, 2),
        "pctChange":    round(pct_change, 2),
        "score":        round(float(score), 1),
        "timestamp":    time.time(),
        "volume":       last_vol,
        "openPrice":    round(float(open_candle[1]), 2),
        "highPrice":    round(float(open_candle[2]), 2),
        "lowPrice":     round(float(open_candle[3]), 2),
        "closePrice":   round(float(open_candle[4]), 2),
        "sl_hit":       sl_hit_now,
        "entry_target": entry_target,
        "exit_status":  historical_status,
        "t1_achieved":  t1_achieved,
    }
    log.append(f"✅ {symbol}: {signal} | score={score:.1f} | ltp={ltp:.2f}")

    st.session_state.results = [x for x in st.session_state.results if x["symbol"] != symbol]
    st.session_state.results.append(result)
    # Persist to Supabase only if logged in
    if st.session_state.get("user_id"):
        save_scanner_result(result, st.session_state.get("selected_watchlist", "Today"))
    return result


def run_full_scan(watchlist_stocks: list):
    if not watchlist_stocks:
        st.warning("No stocks in this watchlist. Add stocks from the Watchlist page first.")
        return

    import concurrent.futures

    BATCH_SIZE  = 5
    BATCH_WAIT  = 0.5   # seconds between batches

    st.session_state.is_scanning = True
    st.session_state.scan_log    = []
    total        = len(watchlist_stocks)
    progress_bar = st.progress(0, text="Initialising scan...")

    # ── Step 1: Fetch all candles in parallel batches ──
    candles_map = {}   # symbol → candles

    def fetch_one(stock):
        try:
            candles = fetch_candles_5min(stock["token"], stock["symbol"])
            return stock["symbol"], candles
        except Exception:
            return stock["symbol"], None

    batches     = [watchlist_stocks[i:i+BATCH_SIZE]
                   for i in range(0, total, BATCH_SIZE)]
    fetched     = 0

    for batch in batches:
        with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            futures = {executor.submit(fetch_one, s): s for s in batch}
            for future in concurrent.futures.as_completed(futures):
                symbol, candles = future.result()
                candles_map[symbol] = candles
                fetched += 1
                progress_bar.progress(
                    fetched / total / 2,   # first half = fetching
                    text=f"Fetching {fetched}/{total}: {symbol}"
                )
        time.sleep(BATCH_WAIT)

    # ── Step 2: Analyze sequentially (session_state not thread-safe) ──
    for i, stock in enumerate(watchlist_stocks):
        candles = candles_map.get(stock["symbol"])
        progress_bar.progress(
            0.5 + (i + 1) / total / 2,   # second half = analyzing
            text=f"Analyzing {i+1}/{total}: {stock['symbol']}"
        )
        analyze_stock(stock, candles, is_refresh=False)

    if st.session_state.results:
        status_order = {"T1_ACHIEVE": 0, "ACTIVE": 1, "NEAR_ENTRY": 2, "NO_ENTRY": 3, "SL_HIT": 4}
        st.session_state.results.sort(
            key=lambda x: (
                status_order.get(x.get("exit_status", "ACTIVE"), 1),
                0 if x["signal"] == "BUY" else 1,
                -x["score"]
            )
        )

    progress_bar.empty()
    st.session_state.is_scanning = False

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

st.markdown("""
<style>
div[data-testid="stVerticalBlock"] > div { gap: 0 !important; }

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

.ts-header-card {
    background:#ffffff; border:1px solid #e8e8e8;
    border-radius:12px; padding:18px 24px;
    margin-bottom:4px;
}
.ts-header-title { font-size:22px; font-weight:700; color:#111111; margin:0; }
.ts-header-sub   { font-size:13px; color:#888888; margin:4px 0 0; }
.ts-counter-val { font-size:28px; font-weight:800; font-family:monospace; }
.ts-counter-lbl { font-size:11px; color:#aaaaaa; font-weight:500; margin-top:2px; }

div[data-testid="stPills"] button {
    font-size:12px !important;
    padding:4px 12px !important;
    border-radius:20px !important;
    font-weight:600 !important;
}

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
.ts-badge-buy       { color:#1a9c4a; background:#e8f8ee; border:1px solid #a8dfc0; }
.ts-badge-sell      { color:#c0392b; background:#fdecea; border:1px solid #f5b8b5; }
.ts-badge-t1achieve { color:#27ae60; background:#d5f4e6; border:1px solid #82d5b3; }
.ts-badge-slhit     { color:#d04a00; background:#fff1eb; border:1px solid #ffcdb3; }
.ts-badge-exit      { color:#6c3fc5; background:#f0eaff; border:1px solid #c4a8f5; }
.ts-badge-noentry   { color:#888888; background:#f5f5f5; border:1px solid #cccccc; }
.ts-badge-nearentry { color:#b36200; background:#fff8ec; border:1px solid #ffd599; }
.ts-price { font-size:13px; font-weight:700; color:#111111; font-family:monospace; }
.ts-pct   { font-size:12px; font-weight:700; margin-left:4px; }
.ts-meta  {
    font-size:12px; color:#888888; font-family:monospace;
    display:flex; gap:12px; align-items:center;
    margin-bottom:4px;
}
.ts-meta span { color:#444444; font-weight:600; }
.ts-entry-row {
    font-size:11px; font-family:monospace; color:#888888;
    display:flex; gap:14px; align-items:center;
    margin-bottom:6px;
}
.ts-entry-row span { font-weight:700; }
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
# RESERVE SPACE FOR HEADER
# ─────────────────────────────────────────────────────────────────────────────
header_container = st.container()

stocks_to_scan = load_watchlist_stocks(st.session_state.selected_watchlist)
mkt_open       = is_market_open()
mkt_label      = "Market open" if mkt_open else "Market closed"
ist_time_str   = get_ist_now().strftime("%I:%M %p IST").lstrip("0")

# ─────────────────────────────────────────────────────────────────────────────
# INITIALIZE FILTER VARIABLES
# ─────────────────────────────────────────────────────────────────────────────
filter_sig       = "ALL"
filter_min_vol   = ""
filter_ema20     = ""
filter_ema200    = ""
filter_min_score = ""
toggle_body_wick = False
toggle_hide_sl   = False

view = list(st.session_state.results)

# ─────────────────────────────────────────────────────────────────────────────
# ACTION BUTTON ROW
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
        st.session_state.db_results_loaded  = False
        st.rerun()

with btn_col2:
    scan_clicked    = st.button("▷  Run scan",  use_container_width=True,
                                 disabled=len(stocks_to_scan) == 0)
with btn_col3:
    refresh_clicked = st.button("↺  Refresh",   use_container_width=True,
                                 disabled=len(st.session_state.results) == 0)
with btn_col4:
    clear_clicked   = st.button("🗑  Clear",      use_container_width=True)
with btn_col5:
    filter_toggle   = st.button(
        ("✕ Filters" if st.session_state.show_filters else "⚙  Filters"),
        use_container_width=True,
    )
with btn_col6:
    sig_display = len(st.session_state.results)
    wl_total    = len(stocks_to_scan)
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
    if st.session_state.get("user_id"):
        clear_scanner_results(st.session_state.selected_watchlist)
    st.session_state.results      = []
    st.session_state.scan_log     = []
    st.session_state.show_filters = False
    st.success("Scanner cleared.")

# ── Login banner — shown only when not logged in ──
if not _user_logged_in:
    with st.container(border=True):
        col_msg, col_btn = st.columns([5, 1])
        with col_msg:
            st.markdown(
                '🔒 **Results are not being saved.** Login to save scan results permanently and access them anytime.',
                unsafe_allow_html=False
            )
        with col_btn:
            show_login = st.button("Login", key="banner_login_btn", type="primary", use_container_width=True)

        if show_login:
            st.session_state["show_inline_login"] = not st.session_state.get("show_inline_login", False)

        if st.session_state.get("show_inline_login", False):
            with st.form("inline_login_form"):
                il_email = st.text_input("Email",    placeholder="you@email.com")
                il_pass  = st.text_input("Password", placeholder="••••••••", type="password")
                col_s, col_c = st.columns(2)
                with col_s: il_submit = st.form_submit_button("Login",  use_container_width=True, type="primary")
                with col_c: il_cancel = st.form_submit_button("Cancel", use_container_width=True)

            if il_cancel:
                st.session_state["show_inline_login"] = False
                st.rerun()

            if il_submit:
                if not il_email or not il_pass:
                    st.error("Enter email and password.")
                else:
                    with st.spinner("Signing in..."):
                        data = _auth_sign_in(il_email.strip(), il_pass.strip())
                    if data.get("access_token"):
                        _set_session(data)
                        session_token = st.session_state.get("session_token", "")
                        if session_token:
                            st.query_params["s"] = session_token
                        st.session_state["show_inline_login"] = False
                        st.session_state["db_results_loaded"] = False
                        st.success("Logged in! Results will now be saved.")
                        st.rerun()
                    else:
                        msg = data.get("error_description") or data.get("msg") or "Login failed."
                        st.error(msg)

# ─────────────────────────────────────────────────────────────────────────────
# COLLAPSIBLE FILTER PANEL
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

# ─────────────────────────────────────────────────────────────────────────────
# APPLY ALL FILTERS
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
# CALCULATE COUNTS AFTER FILTERS
# ─────────────────────────────────────────────────────────────────────────────
buy_count        = len([r for r in view if r["signal"] == "BUY"  and r.get("exit_status", "ACTIVE") == "ACTIVE"])
sell_count       = len([r for r in view if r["signal"] == "SELL" and r.get("exit_status", "ACTIVE") == "ACTIVE"])
t1_achieve_count = len([r for r in view if r.get("exit_status", "ACTIVE") == "T1_ACHIEVE"])
sl_hit_count     = len([r for r in view if r.get("exit_status", "ACTIVE") == "SL_HIT"])
no_entry_count   = len([r for r in view if r.get("exit_status", "ACTIVE") in ("NO_ENTRY", "NEAR_ENTRY")])
total_count      = len(view)

# ─────────────────────────────────────────────────────────────────────────────
# FILL HEADER WITH CORRECT COUNTS
# ─────────────────────────────────────────────────────────────────────────────
with header_container:
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

  <div style="display:flex;gap:30px;margin-top:2px;">
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#1a9c4a;">{buy_count}</div>
      <div class="ts-counter-lbl">Buy</div>
    </div>
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#c0392b;">{sell_count}</div>
      <div class="ts-counter-lbl">Sell</div>
    </div>
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#27ae60;">{t1_achieve_count}</div>
      <div class="ts-counter-lbl">T1 Achieve</div>
    </div>
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#d04a00;">{sl_hit_count}</div>
      <div class="ts-counter-lbl">SL Hit</div>
    </div>
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#888888;">{no_entry_count}</div>
      <div class="ts-counter-lbl">No Entry</div>
    </div>
    <div style="text-align:center;">
      <div class="ts-counter-val" style="color:#111111;">{total_count}</div>
      <div class="ts-counter-lbl">Total</div>
    </div>
  </div>

</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SECTOR PILLS
# ─────────────────────────────────────────────────────────────────────────────
all_sectors  = sorted(set(r["sector"] for r in view))
sector_counts = {}
for r in view:
    sector_counts[r["sector"]] = sector_counts.get(r["sector"], 0) + 1

pill_options           = ["All"]
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
# SCAN LOG
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
# SIGNAL CARDS  — Variation B
# ─────────────────────────────────────────────────────────────────────────────
if not view:
    if st.session_state.results:
        st.info("🔍 No signals match your current filters.")
    elif not st.session_state.scan_log:
        st.info("🔍 Run a scan to see results.")
else:
    sl_hit_display = len([r for r in st.session_state.results if r.get("sl_hit", False)])
    if sl_hit_display:
        st.markdown(
            f'<div style="font-size:12px;color:#d04a00;margin-bottom:6px;">'
            f'🔴 <b>{sl_hit_display}</b> SL Hit stock{"s" if sl_hit_display>1 else ""} in results</div>',
            unsafe_allow_html=True,
        )

    for item in view:
        sym          = item["symbol"]
        sig          = item["signal"]
        exit_status  = item.get("exit_status", "ACTIVE")
        sector_clean = item["sector"].replace("NIFTY ", "")
        ltp          = item["ltp"]
        pct          = item["pctChange"]
        ema20        = item["ema20"]
        vwap         = item["vwap"]
        ema200       = item["ema200"]
        score        = item["score"]
        entry_target = item.get("entry_target") or {}
        mins_ago     = int((time.time() - item["timestamp"]) // 60)
        age_str      = "just now" if mins_ago < 1 else f"{mins_ago}m ago"

        entry_val  = entry_target.get("entry",  "—")
        sl_val     = entry_target.get("sl",     "—")
        t1_val     = entry_target.get("target", "—")
        risk_val   = entry_target.get("risk",   "—")

        if exit_status == "T1_ACHIEVE":
            border_clr  = "#27ae60"
            badge_cls   = "ts-badge-t1achieve"
            badge_label = "T1 Achieve ✅"
            bar_color   = "#27ae60"
            pct_clr     = "#27ae60" if pct >= 0 else "#c0392b"
        elif exit_status == "SL_HIT":
            border_clr  = "#e87040"
            badge_cls   = "ts-badge-slhit"
            badge_label = "SL HIT ✕"
            bar_color   = "#e87040"
            pct_clr     = "#d04a00"
        elif exit_status == "NEAR_ENTRY":
            border_clr  = "#e6a020"
            badge_cls   = "ts-badge-nearentry"
            badge_label = "Near Entry 🔔"
            bar_color   = "#e6a020"
            pct_clr     = "#b36200"
        elif exit_status == "NO_ENTRY":
            border_clr  = "#cccccc"
            badge_cls   = "ts-badge-noentry"
            badge_label = "No Entry"
            bar_color   = "#aaaaaa"
            pct_clr     = "#888888"
        elif sig == "BUY":
            border_clr  = "#1a9c4a"
            badge_cls   = "ts-badge-buy"
            badge_label = "BUY"
            bar_color   = "#1a9c4a"
            pct_clr     = "#1a9c4a" if pct >= 0 else "#c0392b"
        else:
            border_clr  = "#c0392b"
            badge_cls   = "ts-badge-sell"
            badge_label = "SELL"
            bar_color   = "#c0392b"
            pct_clr     = "#1a9c4a" if pct >= 0 else "#c0392b"

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

  <div class="ts-entry-row">
    Entry: <span>₹{entry_val}</span>
    &nbsp;·&nbsp;
    SL: <span style="color:#d04a00;">₹{sl_val}</span>
    &nbsp;·&nbsp;
    T1: <span style="color:#1a7f4a;">₹{t1_val}</span>
    &nbsp;·&nbsp;
    Risk: <span>₹{risk_val}</span>
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
