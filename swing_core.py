# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — swing_core.py  v1.0
#  Swing Scanner — DB CRUD + yfinance fetch + signal calculation
#  Table: swing_watchlist (user_id, symbol, screener_url, breakout_date, notes)
# ══════════════════════════════════════════════════════════════════════════════

import os
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: SUPABASE HELPERS (standalone — no dependency on core.py)
# ─────────────────────────────────────────────────────────────────────────────

def _get_config():
    try:
        import streamlit as st
        url = st.secrets["SUPABASE_URL"].rstrip("/")
        key = st.secrets["SUPABASE_KEY"]
        return url, key
    except Exception:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_KEY", "")
        return url, key

def _get_user_id() -> str:
    try:
        import streamlit as st
        return st.session_state.get("user_id", "")
    except Exception:
        return ""

def _get_access_token() -> str:
    try:
        import streamlit as st
        return st.session_state.get("access_token", "")
    except Exception:
        return ""

def _headers():
    _, key = _get_config()
    token  = _get_access_token()
    auth   = f"Bearer {token}" if token else f"Bearer {key}"
    return {
        "apikey":        key,
        "Authorization": auth,
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }

def _table_url() -> str:
    url, _ = _get_config()
    return f"{url}/rest/v1/swing_watchlist"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: SWING STOCK CRUD
# ─────────────────────────────────────────────────────────────────────────────

def load_swing_stocks() -> list:
    """Load all swing stocks for current user."""
    try:
        user_id = _get_user_id()
        if not user_id:
            return []
        res = requests.get(
            _table_url(),
            headers=_headers(),
            params={
                "select":  "*",
                "user_id": f"eq.{user_id}",
                "order":   "symbol.asc",
            },
            timeout=10,
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"[swing_core] load_swing_stocks error: {e}")
        return []


def add_swing_stock(symbol: str, screener_url: str = "", breakout_date=None, notes: str = "") -> dict:
    """Add a new stock to swing watchlist."""
    user_id = _get_user_id()
    if not user_id:
        raise RuntimeError("Not logged in")

    symbol = symbol.upper().strip()

    # Check duplicate
    existing = load_swing_stocks()
    if any(s["symbol"] == symbol for s in existing):
        raise ValueError(f"{symbol} already in swing list")

    row = {
        "user_id":      user_id,
        "symbol":       symbol,
        "screener_url": screener_url.strip() if screener_url else f"https://www.screener.in/company/{symbol}/",
        "notes":        notes.strip(),
    }
    if breakout_date:
        row["breakout_date"] = str(breakout_date)

    res = requests.post(
        _table_url(),
        headers=_headers(),
        json=row,
        timeout=10,
    )
    res.raise_for_status()
    data = res.json()
    return data[0] if isinstance(data, list) else data


def update_swing_stock(db_id: int, updates: dict):
    """Update fields of a swing stock."""
    allowed = {"screener_url", "breakout_date", "notes", "symbol"}
    clean   = {k: v for k, v in updates.items() if k in allowed}
    if not clean:
        return
    res = requests.patch(
        f"{_table_url()}?id=eq.{db_id}",
        headers=_headers(),
        json=clean,
        timeout=10,
    )
    res.raise_for_status()


def delete_swing_stock(db_id: int):
    """Delete a stock from swing watchlist."""
    res = requests.delete(
        f"{_table_url()}?id=eq.{db_id}",
        headers=_headers(),
        timeout=10,
    )
    res.raise_for_status()


def bulk_add_swing_stocks(symbols: list) -> dict:
    """Add multiple symbols at once. Returns {added: [], skipped: [], errors: []}"""
    user_id  = _get_user_id()
    existing = {s["symbol"] for s in load_swing_stocks()}
    added, skipped, errors = [], [], []

    rows = []
    for sym in symbols:
        sym = sym.upper().strip()
        if not sym:
            continue
        if sym in existing:
            skipped.append(sym)
            continue
        rows.append({
            "user_id":      user_id,
            "symbol":       sym,
            "screener_url": f"https://www.screener.in/company/{sym}/",
            "notes":        "",
        })
        added.append(sym)

    if rows:
        try:
            res = requests.post(
                _table_url(),
                headers=_headers(),
                json=rows,
                timeout=15,
            )
            res.raise_for_status()
        except Exception as e:
            errors = added.copy()
            added  = []

    return {"added": added, "skipped": skipped, "errors": errors}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: YFINANCE DATA FETCH
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_single_stock(symbol: str) -> dict | None:
    """Fetch last 5 days + today's data for one stock via yfinance."""
    try:
        ticker = yf.Ticker(f"{symbol}.NS")

        # Fetch last 15 trading days to ensure we get 5 clean closes + today
        df = ticker.history(period="15d", interval="1d", auto_adjust=True)
        if df is None or len(df) < 3:
            return {"symbol": symbol, "error": "Insufficient data"}

        df = df.dropna(subset=["Close", "Volume"])

        # Last 5 completed candles (excluding today if market open)
        closes     = df["Close"].iloc[-6:-1].tolist()   # 5 closes
        volumes    = df["Volume"].iloc[-6:-1].tolist()  # 5 volumes
        close_dates = df.index[-6:-1].strftime("%d-%b").tolist()

        # Today / latest candle
        today_row   = df.iloc[-1]
        current_price = round(float(today_row["Close"]), 2)
        today_open    = round(float(today_row["Open"]),  2)
        today_high    = round(float(today_row["High"]),  2)
        today_low     = round(float(today_row["Low"]),   2)
        current_vol   = int(today_row["Volume"])

        # Calculations
        max_close    = max(closes) if closes else current_price
        avg_vol_3d   = sum(volumes[-3:]) / 3 if len(volumes) >= 3 else (sum(volumes) / len(volumes) if volumes else 1)
        vol_ratio    = round(current_vol / avg_vol_3d, 2) if avg_vol_3d > 0 else 0

        # Status logic (from your Google Sheet formula)
        status = _calc_status(current_price, max_close, current_vol, volumes, vol_ratio)

        # Volume signal label
        vol_signal = _vol_signal(vol_ratio)

        return {
            "symbol":        symbol,
            "closes":        [round(c, 2) for c in closes],
            "close_dates":   close_dates,
            "current_price": current_price,
            "today_open":    today_open,
            "today_high":    today_high,
            "today_low":     today_low,
            "current_vol":   current_vol,
            "avg_vol_3d":    int(avg_vol_3d),
            "vol_ratio":     vol_ratio,
            "vol_signal":    vol_signal,
            "max_close":     round(max_close, 2),
            "status":        status,
            "error":         None,
        }

    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio) -> str:
    """
    Exact logic from Google Sheet formula:
    BLASTING : price > max_close  AND current_vol > max(hist_vol) AND vol_ratio >= 2
    READY    : price >= max_close * 0.995  AND vol_ratio >= 1.5
    WATCH    : price >= max_close * 0.92
    else     : ""
    """
    max_hist_vol = max(hist_volumes) if hist_volumes else 0

    if (current_price > max_close
            and current_vol > max_hist_vol
            and vol_ratio >= 2.0):
        return "BLASTING"
    elif (current_price >= max_close * 0.995
            and vol_ratio >= 1.5):
        return "READY"
    elif current_price >= max_close * 0.92:
        return "WATCH"
    else:
        return ""


def _vol_signal(vol_ratio: float) -> str:
    if vol_ratio >= 1.5:
        return f"🟢 Strong ({vol_ratio})"
    elif vol_ratio >= 1.0:
        return f"🟡 Build ({vol_ratio})"
    else:
        return f"🔴 Weak ({vol_ratio})"


def run_swing_scan(stocks: list, batch_size: int = 10, pause: float = 0.5) -> list:
    """
    Scan all swing stocks in parallel batches.
    stocks: list of dicts from load_swing_stocks()
    Returns list of result dicts sorted by status priority.
    """
    symbols    = [s["symbol"] for s in stocks]
    stock_meta = {s["symbol"]: s for s in stocks}
    results    = []
    errors     = []

    total   = len(symbols)
    batches = [symbols[i:i+batch_size] for i in range(0, total, batch_size)]

    for batch_idx, batch in enumerate(batches):
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {executor.submit(_fetch_single_stock, sym): sym for sym in batch}
            for future in as_completed(futures):
                sym  = futures[future]
                data = future.result()
                if data and not data.get("error"):
                    # Merge DB meta (screener_url, breakout_date, notes, id)
                    meta = stock_meta.get(sym, {})
                    data["screener_url"]  = meta.get("screener_url", f"https://www.screener.in/company/{sym}/")
                    data["breakout_date"] = meta.get("breakout_date", "")
                    data["notes"]         = meta.get("notes", "")
                    data["db_id"]         = meta.get("id")
                    results.append(data)
                else:
                    err = data.get("error", "Unknown") if data else "No data"
                    errors.append({"symbol": sym, "error": err})

        if batch_idx < len(batches) - 1:
            time.sleep(pause)

    # Sort: BLASTING → READY → WATCH → rest
    priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
    results.sort(key=lambda x: priority.get(x.get("status", ""), 3))

    return results, errors
