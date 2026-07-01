"""
entry_verdict.py
-----------------
AI Trade-Entry Verdict Engine for SmartMoney Momentum Scanner.

Purpose: stop impulsive FOMO entries. Runs a 6-point Sr-Trader checklist
the moment a stock appears in the momentum tab, then asks Gemini to act
as a senior trader and give a direct BUY NOW / WAIT FOR PULLBACK / AVOID
call with a short reason.

Plug into renderer.py:
    from entry_verdict import get_entry_verdict
    verdict = get_entry_verdict(stock_data)   # see schema below
    # then render verdict["verdict"] / verdict["reason"] as a badge

Requires: pip install google-generativeai
Env var:  GEMINI_API_KEY  (add to Streamlit secrets — get one free at aistudio.google.com)
"""

import os
import time
import threading
from datetime import datetime
import google.generativeai as genai
import yfinance as yf

genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

MODEL = "gemini-2.5-flash"
_model = genai.GenerativeModel(MODEL)


# ---------------------------------------------------------------------
# Required input schema (fill whatever you have — missing fields are
# marked N/A in the checklist instead of breaking the function)
# ---------------------------------------------------------------------
# stock_data = {
#     "symbol": "VELJAN",
#     "signal_price": 1346.70,
#     "ltp": 1431.60,
#     "vol_ratio": 62.05,
#     "prev_day_move_pct": -1.58,
#     "phase": "STRONG BUILDING",
#     "phase_pct": 100,
#     "delivery_pct": 95.7,
#     "daily_ema20": 1400.0,   # daily-timeframe 20 EMA value
#     "ema5m_9": 1428.0,       # 5-min 9 EMA value
#     "ema5m_20": 1420.0,      # 5-min 20 EMA value
#     "ema5m_200": 1390.0,     # 5-min 200 EMA value
# }


def _pct_diff(a, b):
    if not b:
        return 0.0
    return round(((a - b) / b) * 100, 2)


def run_checklist(stock_data: dict) -> dict:
    """Fast rule-based pre-checks, no API call. Returns pass/fail + note per rule."""
    ltp = stock_data["ltp"]
    signal_price = stock_data["signal_price"]
    checks = {}

    # 1. Near 20 EMA on DAILY timeframe
    daily_ema20 = stock_data.get("daily_ema20")
    if daily_ema20:
        dist = _pct_diff(ltp, daily_ema20)
        checks["daily_20ema"] = {
            "pass": abs(dist) <= 2.0,
            "note": f"LTP is {dist:+.2f}% from daily 20 EMA",
        }
    else:
        checks["daily_20ema"] = {"pass": None, "note": "daily_ema20 not provided"}

    # 2. Yesterday delivery % — sanity check for intraday
    delivery = stock_data.get("delivery_pct")
    if delivery is not None:
        checks["delivery"] = {
            "pass": delivery >= 40,
            "note": f"Delivery % = {delivery}% ({'healthy' if delivery >= 40 else 'weak / speculative'})",
        }
    else:
        checks["delivery"] = {"pass": None, "note": "delivery_pct not provided"}

    # 3. Near 9 EMA on 5-min timeframe
    ema9 = stock_data.get("ema5m_9")
    if ema9:
        dist = _pct_diff(ltp, ema9)
        checks["ema9_5m"] = {
            "pass": abs(dist) <= 1.0,
            "note": f"LTP is {dist:+.2f}% from 5m 9 EMA",
        }
    else:
        checks["ema9_5m"] = {"pass": None, "note": "ema5m_9 not provided"}

    # 4. Above 200 EMA and 20 EMA on 5-min timeframe
    ema200 = stock_data.get("ema5m_200")
    ema20_5m = stock_data.get("ema5m_20")
    if ema200 and ema20_5m:
        checks["above_emas_5m"] = {
            "pass": ltp > ema200 and ltp > ema20_5m,
            "note": f"LTP {'above' if ltp > ema200 else 'BELOW'} 200EMA, "
                    f"{'above' if ltp > ema20_5m else 'BELOW'} 20EMA (5m)",
        }
    else:
        checks["above_emas_5m"] = {"pass": None, "note": "ema5m_200 / ema5m_20 not provided"}

    # 5. Volume ratio — potential to grow further
    vol_ratio = stock_data.get("vol_ratio", 0)
    checks["volume"] = {
        "pass": vol_ratio >= 3,
        "note": f"Vol ratio {vol_ratio}x "
                f"({'strong' if vol_ratio >= 10 else 'building' if vol_ratio >= 3 else 'weak'})",
    }

    # 6. Distance from signal price — chase check
    entry_dist = _pct_diff(ltp, signal_price)
    checks["entry_distance"] = {
        "pass": abs(entry_dist) <= 1.0,
        "note": f"LTP is {entry_dist:+.2f}% from signal price — "
                f"{'OK to enter' if abs(entry_dist) <= 1.0 else 'too far, WAIT for pullback'}",
    }

    return checks


VERDICT_PROMPT = """You are a senior NSE intraday trader mentoring a trader who has a habit of \
impulsively buying the moment a stock appears on his momentum scanner, without checking anything \
first. Your job is to stop bad entries.

Stock: {symbol}
Signal Price: {signal_price} | LTP: {ltp}
Phase: {phase} ({phase_pct}%)
Prev Day Move: {prev_day_move_pct}%

Checklist results:
{checklist_text}

Give a verdict as a blunt, experienced senior trader would. No hedging, no fluff. \
Respond in exactly this format:

VERDICT: <BUY NOW / WAIT FOR PULLBACK / AVOID>
CONFIDENCE: <Low/Medium/High>
REASON: <2-3 sentences, plain language, name the specific checks that matter most>
"""


def get_entry_verdict(stock_data: dict) -> dict:
    """Main entry point: rule checklist + Claude Sr-Trader verdict."""
    checks = run_checklist(stock_data)

    checklist_text = "\n".join(
        f"- {k}: {'PASS' if v['pass'] else 'FAIL' if v['pass'] is False else 'N/A'} — {v['note']}"
        for k, v in checks.items()
    )

    prompt = VERDICT_PROMPT.format(
        symbol=stock_data["symbol"],
        signal_price=stock_data["signal_price"],
        ltp=stock_data["ltp"],
        phase=stock_data.get("phase", "N/A"),
        phase_pct=stock_data.get("phase_pct", "N/A"),
        prev_day_move_pct=stock_data.get("prev_day_move_pct", "N/A"),
        checklist_text=checklist_text,
    )

    try:
        response = _model.generate_content(
            prompt,
            generation_config={"max_output_tokens": 300, "temperature": 0.4},
        )
        llm_text = response.text
    except Exception as e:
        llm_text = f"VERDICT: ERROR\nCONFIDENCE: Low\nREASON: AI call failed ({e})"

    verdict, confidence, reason = "UNKNOWN", "Low", llm_text
    for line in llm_text.splitlines():
        if line.startswith("VERDICT:"):
            verdict = line.replace("VERDICT:", "").strip()
        elif line.startswith("CONFIDENCE:"):
            confidence = line.replace("CONFIDENCE:", "").strip()
        elif line.startswith("REASON:"):
            reason = line.replace("REASON:", "").strip()

    return {
        "symbol": stock_data["symbol"],
        "verdict": verdict,
        "confidence": confidence,
        "reason": reason,
        "checks": checks,
        "checked_at": datetime.now().strftime("%H:%M:%S"),
    }


def render_verdict_badge(verdict_result: dict) -> str:
    """Returns an HTML pill badge matching renderer.py's existing pill style
    (bg/color/border, like _phase_cell). Handles CHECKING/ERROR states too."""
    v = verdict_result["verdict"].upper()
    styles = {
        "BUY NOW":            ("#f0fdf4", "#15803d", "#bbf7d0", "🚀"),
        "WAIT FOR PULLBACK":  ("#fffbeb", "#b45309", "#fde68a", "⚠️"),
        "AVOID":              ("#fff1f2", "#be123c", "#fecdd3", "🔴"),
        "CHECKING":           ("#f1f5f9", "#64748b", "#e2e8f0", "⏳"),
        "ERROR":              ("#f1f5f9", "#94a3b8", "#e2e8f0", "⚪"),
    }
    bg, color, border, icon = styles.get(v, ("#f1f5f9", "#64748b", "#e2e8f0", "⚪"))
    reason = verdict_result.get("reason", "")
    return (
        f'<div style="display:flex;flex-direction:column;gap:4px;min-width:150px;max-width:220px">'
        f'  <span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;'
        f'         border-radius:6px;font-size:12px;font-weight:700;white-space:nowrap;'
        f'         background:{bg};color:{color};border:1px solid {border};width:fit-content">'
        f'    {icon} {v}</span>'
        f'  <div style="font-size:11px;color:#94a3b8;white-space:normal;line-height:1.3">{reason}</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------
# Non-blocking background cache/queue
# ---------------------------------------------------------------------
# renderer.py must ONLY call queue_or_get_verdict() from the row loop.
# It reads a cache and returns instantly (never calls the LLM inline).
# A daemon thread does the actual Claude call in the background, so a
# slow/failed API call can never hang the Streamlit page render.
#
# IMPORTANT: the background thread never touches st.session_state
# (same rule you already use for the Yahoo-fetch daemon threads).
# ---------------------------------------------------------------------

_verdict_cache = {}
_pending = set()
_cache_lock = threading.Lock()
CACHE_TTL_SECONDS = 180  # re-check a stock at most every 3 min (or when signal_price changes)


def _fetch_5m_emas(symbol: str) -> dict:
    """
    Fetches 5-min candles from Yahoo Finance and computes EMA9, EMA20, EMA200
    on the 5-min timeframe. ONLY called from the background thread — never
    call this from the Streamlit render loop directly (same rule as your
    existing candle system: yfinance stays outside @st.fragment).
    """
    try:
        ticker = f"{symbol}.NS"
        data = yf.download(ticker, period="5d", interval="5m", progress=False)
        if data is None or data.empty or len(data) < 10:
            return {"ema5m_9": None, "ema5m_20": None, "ema5m_200": None}

        close = data["Close"]
        if hasattr(close, "columns"):  # yfinance sometimes returns a DataFrame for single ticker
            close = close.iloc[:, 0]

        ema9 = close.ewm(span=9, adjust=False).mean().iloc[-1]
        ema20 = close.ewm(span=20, adjust=False).mean().iloc[-1]
        # 200-period EMA needs ~200 5-min candles (~3 trading days); if fewer
        # are available, fall back to the longest EMA the data actually supports.
        span_200 = min(len(close), 200)
        ema200 = close.ewm(span=span_200, adjust=False).mean().iloc[-1]

        return {
            "ema5m_9": float(ema9),
            "ema5m_20": float(ema20),
            "ema5m_200": float(ema200),
        }
    except Exception:
        return {"ema5m_9": None, "ema5m_20": None, "ema5m_200": None}


def _cache_key(symbol, signal_price):
    return f"{symbol}:{signal_price}"


def _compute_and_store(stock_data: dict):
    key = _cache_key(stock_data["symbol"], stock_data["signal_price"])
    try:
        # Pull the 5-min EMAs from Yahoo Finance here (background thread only).
        # daily_ema20 is expected to already be present in stock_data (from your DB).
        yahoo_emas = _fetch_5m_emas(stock_data["symbol"])
        merged = {**stock_data, **yahoo_emas}

        result = get_entry_verdict(merged)
        result["_ts"] = time.time()
        with _cache_lock:
            _verdict_cache[key] = result
    except Exception as e:
        with _cache_lock:
            _verdict_cache[key] = {
                "symbol": stock_data["symbol"],
                "verdict": "ERROR",
                "confidence": "Low",
                "reason": f"Verdict engine failed: {e}",
                "checks": {},
                "checked_at": datetime.now().strftime("%H:%M:%S"),
                "_ts": time.time(),
            }
    finally:
        with _cache_lock:
            _pending.discard(key)


def queue_or_get_verdict(stock_data: dict) -> dict:
    """
    Call this from renderer.py inside the row loop. NON-BLOCKING —
    returns a cached verdict instantly, or a 'CHECKING' placeholder while
    a background daemon thread computes it. Never calls the LLM inline,
    so the Streamlit page never hangs waiting on the AI.
    """
    key = _cache_key(stock_data["symbol"], stock_data["signal_price"])

    with _cache_lock:
        cached = _verdict_cache.get(key)
        is_pending = key in _pending

    if cached and (time.time() - cached.get("_ts", 0)) < CACHE_TTL_SECONDS:
        return cached

    if not is_pending:
        with _cache_lock:
            _pending.add(key)
        threading.Thread(target=_compute_and_store, args=(stock_data,), daemon=True).start()

    return {
        "symbol": stock_data["symbol"],
        "verdict": "CHECKING",
        "confidence": "—",
        "reason": "AI is reviewing this entry...",
        "checks": {},
        "checked_at": "",
    }
