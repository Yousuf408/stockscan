# ══════════════════════════════════════════════════════════════════════════════
#   TRADE SENTRY — scanner.py   v2.9 (Stable)
#   Optimized for AngelOne 5-minute continuous historical streams.
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
    try:
        from auth import save_session
        session_token = save_session(token, uid, email)
        st.session_state["session_token"] = session_token
    except Exception as e:
        print(f"[scanner] Session save failed: {e}")

_user_logged_in = bool(st.session_state.get("user_id"))

try:
    from core import get_user_watchlist_names
    if st.session_state.get("user_id"):
        WATCHLIST_NAMES = get_user_watchlist_names()
    else:
        WATCHLIST_NAMES = ["Today", "Yesterday", "New"]
except Exception:
    WATCHLIST_NAMES = ["Today", "Yesterday", "New"]


# ─────────────────────────────────────────────────────────────────────────────
# ANGEL ONE AUTH
# ─────────────────────────────────────────────────────────────────────────────

def get_angel_auth() -> dict:
    jwt = st.session_state.get("angel_jwt")
    key = st.session_state.get("angel_api_key")
    if jwt and key:
        return {"session": {"jwtToken": jwt, "apiKey": key}}

    try:
        import pyotp
        from SmartApi import SmartConnect

        api_key     = st.secrets.get("API_KEY", "")
        client_code = st.secrets.get("CLIENT_CODE", "")
        password    = st.secrets.get("PASSWORD", "")
        totp_secret = st.secrets.get("TOTP_SECRET", "")

        if not all([api_key, client_code, password, totp_secret]):
            print("[AngelAuth] Secrets missing")
            return {}

        angel_obj    = SmartConnect(api_key=api_key)
        totp         = pyotp.TOTP(totp_secret).now()
        session_data = angel_obj.generateSession(client_code, password, totp)

        if session_data and session_data.get("status"):
            jwt = session_data["data"]["jwtToken"]
            st.session_state["angel_jwt"]     = jwt
            st.session_state["angel_api_key"] = api_key
            print("[AngelAuth] ✅ Login successful")
            return {"session": {"jwtToken": jwt, "apiKey": api_key}}
        else:
            print(f"[AngelAuth] ❌ Login failed: {session_data.get('message')}")
    except Exception as e:
        print(f"[AngelAuth] ❌ Exception: {e}")

    return {}


def _send_notification(symbol: str, alert_type: str, ltp: float, entry: float, signal: str):
    icons = {
        "NEAR_ENTRY":  "🔔",
        "ENTRY_HIT":   "✅",
        "T1_ACHIEVE":  "🎯",
        "SL_HIT":      "🛑",
    }
    icon  = icons.get(alert_type, "🔔")
    title = f"TradeSentry — {symbol}"
    body  = f"{icon} {alert_type.replace('_', ' ')} | {signal} | LTP: ₹{ltp} | Entry: ₹{entry}"

    st.components.v1.html(f"""
<script>
if ("Notification" in window && Notification.permission === "granted") {{
    new Notification("{title}", {{
        body: "{body}",
        icon: "https://img.icons8.com/color/48/000000/stock-market.png"
    }});
}}
</script>
""", height=0)

    try:
        from core import _sb_insert, _get_user_id
        _sb_insert("notifications", [{
            "user_id":    _get_user_id() or None,
            "symbol":     symbol,
            "signal":     signal,
            "alert_type": alert_type,
            "ltp":        ltp,
            "entry":      entry,
        }])
    except Exception as e:
        print(f"[notification] Save failed: {e}")


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

if not st.session_state["db_results_loaded"]:
    if st.session_state.get("user_id"):
        db_results = load_scanner_results(st.session_state["selected_watchlist"])
        if db_results:
            st.session_state["results"] = db_results
    st.session_state["db_results_loaded"] = True

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: DATE & TIME (v2.9 FIXES)
# ─────────────────────────────────────────────────────────────────────────────

IST = pytz.timezone("Asia/Kolkata")

def get_ist_now() -> datetime:
    return datetime.now(pytz.utc).astimezone(IST)

def get_ist_today_str() -> str:
    return get_ist_now().strftime("%Y-%m-%d")

def get_last_trading_day_str() -> str:
    """
    Returns the most recent COMPLETED or ACTIVE trading weekday as YYYY-MM-DD.
    Safely handles weekends and pre-market weekday queries.
    """
    dt = get_ist_now()
    
    # 1. Roll back weekend days
    if dt.weekday() == 5:    # Saturday
        dt -= timedelta(days=1)
    elif dt.weekday() == 6:  # Sunday
        dt -= timedelta(days=2)
        
    # 2. Check if it's a weekday but BEFORE market opening data is processed (9:15 AM)
    market_open_time = dt.replace(hour=9, minute=15, second=0, microsecond=0)
    if get_ist_now() < market_open_time:
        dt -= timedelta(days=1)
        # Handle secondary edge case if walking back lands on a weekend
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)

    return dt.strftime("%Y-%m-%d")

def is_market_open() -> bool:
    now  = get_ist_now()
    mins = now.hour * 60 + now.minute
    # True only between 9:15 AM and 3:30 PM on standard trading weekdays
    if now.weekday() >= 5:
        return False
    return (9 * 60 + 15) <= mins <= (15 * 60 + 30)

def get_ist_time_now() -> str:
    return get_ist_now().strftime("%H:%M")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_candles_5min(symbol_token: str, symbol: str, angel_auth=None):
    log      = st.session_state.get("scan_log", [])
    is_open  = is_market_open()
    end_date = get_ist_today_str() if is_open else get_last_trading_day_str()
    start_date = (get_ist_now() - timedelta(days=20)).strftime("%Y-%m-%d")

    if not angel_auth or not angel_auth.get("session"):
        log.append(f"❌ [{symbol}] No AngelOne session")
        return None

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
        log.append(f"🔍 [{symbol}] token={symbol_token} from={start_date} to={end_date}")
        
        res = requests.post(
            "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData",
            json=payload, headers=headers, timeout=7,
        )
        if res.status_code == 200:
            data = res.json()
            status = data.get("status")
            msg    = data.get("message", "")
            if status is True and isinstance(data.get("data"), list):
                rows = []
                for c in data["data"]:
                    if isinstance(c, list) and len(c) >= 6:
                        raw_ts        = str(c[0])
                        ts_normalized = raw_ts.replace("T", " ")[:19]
                        rows.append([ts_normalized, float(c[1]), float(c[2]),
                                     float(c[3]), float(c[4]), float(c[5])])
                if rows:
                    return rows
                log.append(f"   ⚠️ 0 rows in response")
            else:
                log.append(f"   ❌ API error — status={status} msg={msg}")
        else:
            log.append(f"   ❌ HTTP error {res.status_code}: {res.text[:100]}")
    except Exception as e:
        log.append(f"   ❌ Exception: {e}")

    return None


def fetch_daily_prev_close(symbol: str):
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


def debug_opening_candle(symbol: str, candles: list, opening_idx: int):
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

    entry_buy  = round(high, 2)
    sl_buy     = round(low, 2)
    target_buy = round(entry_buy + risk, 2)

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
    if not signal or ltp is None or sl_price is None:
        return False
    if signal == "BUY":
        return ltp <= sl_price
    if signal == "SELL":
        return ltp >= sl_price
    return False


def calc_entry_target(signal: str, f5_high: float, f5_low: float) -> dict:
    if not signal or f5_high is None or f5_low is None:
        return None

    if signal == "BUY":
        entry  = f5_high
        sl     = f5_low
        risk   = entry - sl
        target = entry + risk
    elif signal == "SELL":
        entry  = f5_low
        sl     = f5_high
        risk   = sl - entry
        target = entry - risk
    else:
        return None

    return {
        "entry":  round(entry,  2),
        "sl":     round(sl,     2),
        "target": round(target, 2),
        "risk":   round(risk,  2),
    }


def check_exit_or_sl_hit(signal: str, ltp: float, entry: float, target: float,
                          sl_price: float, candles: list, ema20_live: float,
                          t1_already_achieved: bool = False,
                          exit_already_triggered: bool = False) -> dict:
    if not signal or ltp is None or entry is None or target is None or sl_price is None:
        return {"status": "ACTIVE", "triggered": False}

    if exit_already_triggered:
        return {"status": "EXIT", "triggered": True}

    if t1_already_achieved:
        if candles and len(candles) >= 1:
            last_close = float(candles[-1][4])
            if signal == "BUY"  and last_close < ema20_live:
                return {"status": "EXIT", "triggered": True}
            if signal == "SELL" and last_close > ema20_live:
                return {"status": "EXIT", "triggered": True}
        return {"status": "T1_ACHIEVE", "triggered": True}

    if signal == "BUY"  and ltp >= target:
        return {"status": "T1_ACHIEVE", "triggered": True}
    if signal == "SELL" and ltp <= target:
        return {"status": "T1_ACHIEVE", "triggered": True}

    if signal == "BUY"  and ltp <= sl_price:
        return {"status": "SL_HIT", "triggered": True}
    if signal == "SELL" and ltp >= sl_price:
        return {"status": "SL_HIT", "triggered": True}

    return {"status": "ACTIVE", "triggered": False}


def check_historical_status(signal: str, candles_from_open: list,
                             target: float, sl_price: float,
                             trading_date: str,
                             f5_entry_price: float = None) -> str:
    if not candles_from_open or not signal or not target or not sl_price:
        return "ACTIVE"

    candles_to_check = [
        c for c in candles_from_open[1:]
        if str(c[0]).split(" ")[0] == trading_date
    ]

    if not candles_to_check:
        return "ACTIVE"

    if f5_entry_price is not None:
        entry_price = f5_entry_price
    else:
        entry_price = float(candles_from_open[0][2]) if signal == "BUY" else float(candles_from_open[0][3])

    entry_hit = any(
        float(c[2]) >= entry_price if signal == "BUY" else float(c[3]) <= entry_price
        for c in candles_to_check
    )

    if not entry_hit:
        last_ltp = float(candles_to_check[-1][4])
        pct_from_entry = abs(last_ltp - entry_price) / entry_price * 100
        if pct_from_entry <= 0.5:
            return "NEAR_ENTRY"
        return "NO_ENTRY"

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

                if current_status in ("T1_ACHIEVE", "SL_HIT"):
                    r.update({
                        "ltp":       round(ltp, 2),
                        "ema20":     round(ema20_live, 2),
                        "ema200":    round(ema200_live, 2),
                        "vwap":      round(vwap_live, 2),
                        "pctChange": round(pct_change, 2),
                    })
                    return r

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

                if new_status != current_status:
                    entry_price = et.get("entry", 0)
                    if new_status == "NEAR_ENTRY":
                        _send_notification(symbol, "NEAR_ENTRY", round(ltp,2), entry_price, signal)
                    elif new_status == "ACTIVE" and current_status == "NEAR_ENTRY":
                        _send_notification(symbol, "ENTRY_HIT", round(ltp,2), entry_price, signal)
                    elif new_status == "T1_ACHIEVE":
                        _send_notification(symbol, "T1_ACHIEVE", round(ltp,2), entry_price, signal)
                    elif new_status == "SL_HIT":
                        _send_notification(symbol, "SL_HIT", round(ltp,2), entry_price, signal)

                return r
        return None

    # ── INITIAL SCAN PATH ──
    opening_idx = find_opening_candle_index(candles)

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
        return None

    # Extract boundaries
    f5_high = float(open_candle[2])
    f5_low  = float(open_candle[3])

    et = calc_entry_target(signal, f5_high, f5_low)
    if not et:
        return None

    trading_date = get_ist_today_str() if is_market_open() else get_last_trading_day_str()
    candles_from_open = candles[opening_idx:]
    
    status = check_historical_status(
        signal, candles_from_open, 
        et["target"], et["sl"], trading_date, 
        f5_entry_price=et["entry"]
    )

    score = calc_score(signal, ltp, last_vol, avg_vol, pct_change, ema200_live)

    return {
        "symbol":       symbol,
        "sector":       sector,
        "signal":       signal,
        "ltp":          round(ltp, 2),
        "ema20":        round(ema20_live, 2),
        "ema200":       round(ema200_live, 2),
        "vwap":         round(vwap_live, 2),
        "pctChange":    round(pct_change, 2),
        "score":        score,
        "entry_target": et,
        "sl_hit":       status == "SL_HIT",
        "exit_status":  status,
        "t1_achieved":  status == "T1_ACHIEVE",
        "timestamp":    datetime.now(IST).strftime("%H:%M:%S"),
    }
