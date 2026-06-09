# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — swing_core.py  v3.1
#  v3.1 FIXES:
#    - period="2y" → "10d" in _fetch_all_yf_bulk (50x less data)
#    - _load_all_from_db uses Range: 0-9999 header (bypasses Supabase 1000 row limit)
#
#  v3.0 ARCHITECTURE — Smart DB-first, zero redundant fetches:
#
#  ON SCAN:
#    1. Check if today's date exists for ANY one stock in swing_price_data
#    2. YES → load ALL data from DB (1 query) → build results instantly
#    3. NO  → fetch all from yfinance → save to DB → return results
#
#  ON REFRESH (market hours only):
#    - Always fetch live candle from yfinance (today's price keeps changing)
#    - Hist data unchanged (already in memory from scan)
#    - Save updated today row to DB async
#
#  KEY INSIGHT: All stocks are scanned together. If DB has today for stock A,
#  it has today for ALL stocks. So one date-check decides everything.
# ══════════════════════════════════════════════════════════════════════════════

import os, requests, yfinance as yf, statistics, time, threading
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — SUPABASE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_config():
    try:
        import streamlit as st
        return st.secrets["SUPABASE_URL"].rstrip("/"), st.secrets["SUPABASE_KEY"]
    except Exception:
        return os.environ.get("SUPABASE_URL", "").rstrip("/"), os.environ.get("SUPABASE_KEY", "")

def _get_user_id():
    try:
        import streamlit as st
        return st.session_state.get("user_id", "")
    except Exception:
        return ""

def _get_access_token():
    try:
        import streamlit as st
        return st.session_state.get("access_token", "")
    except Exception:
        return ""

def _headers():
    _, key = _get_config()
    token  = _get_access_token()
    return {
        "apikey":        key,
        "Authorization": f"Bearer {token or key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }

def _table_url():
    url, _ = _get_config()
    return f"{url}/rest/v1/swing_watchlist"

def _price_table_url():
    url, _ = _get_config()
    return f"{url}/rest/v1/swing_price_data"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — SWING STOCK CRUD
# ─────────────────────────────────────────────────────────────────────────────

def load_swing_stocks() -> list:
    try:
        uid = _get_user_id()
        if not uid:
            return []
        r = requests.get(
            _table_url(), headers=_headers(),
            params={"select": "*", "user_id": f"eq.{uid}", "order": "symbol.asc"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[swing_core] load error: {e}")
        return []

def add_swing_stock(symbol: str, screener_url: str = "", breakout_date=None, notes: str = "") -> dict:
    uid    = _get_user_id()
    if not uid:
        raise RuntimeError("Not logged in")
    symbol = symbol.upper().strip()
    if any(s["symbol"] == symbol for s in load_swing_stocks()):
        raise ValueError(f"{symbol} already in swing list")
    row = {
        "user_id":      uid,
        "symbol":       symbol,
        "screener_url": screener_url.strip() or f"https://www.screener.in/company/{symbol}/",
        "notes":        notes.strip(),
    }
    if breakout_date:
        row["breakout_date"] = str(breakout_date)
    r = requests.post(_table_url(), headers=_headers(), json=row, timeout=10)
    r.raise_for_status()
    d = r.json()
    return d[0] if isinstance(d, list) else d

def update_swing_stock(db_id: int, updates: dict):
    allowed = {"screener_url", "breakout_date", "notes", "symbol"}
    clean   = {k: v for k, v in updates.items() if k in allowed}
    if not clean:
        return
    r = requests.patch(
        f"{_table_url()}?id=eq.{db_id}",
        headers=_headers(), json=clean, timeout=10,
    )
    r.raise_for_status()
    return r.json()

def delete_swing_stock(db_id: int):
    r = requests.delete(f"{_table_url()}?id=eq.{db_id}", headers=_headers(), timeout=10)
    r.raise_for_status()

def bulk_add_swing_stocks(symbols: list) -> dict:
    uid      = _get_user_id()
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
            "user_id":      uid,
            "symbol":       sym,
            "screener_url": f"https://www.screener.in/company/{sym}/",
            "notes":        "",
        })
        added.append(sym)
    if rows:
        try:
            r = requests.post(_table_url(), headers=_headers(), json=rows, timeout=15)
            r.raise_for_status()
        except Exception:
            errors = added.copy()
            added  = []
    return {"added": added, "skipped": skipped, "errors": errors}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — FORMAT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def fmt_vol(v) -> str:
    if v is None:
        return "—"
    v = int(v)
    if v >= 10_000_000: return f"{v/10_000_000:.2f}Cr"
    if v >= 100_000:    return f"{v/100_000:.2f}L"
    if v >= 1_000:      return f"{v/1_000:.1f}K"
    return str(v)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — SIGNAL LOGIC
# ─────────────────────────────────────────────────────────────────────────────

def _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio) -> str:
    max_hist_vol = max(hist_volumes) if hist_volumes else 0
    if current_price > max_close and current_vol > max_hist_vol and vol_ratio >= 2.0:
        return "BLASTING"
    if current_price >= max_close * 0.995 and vol_ratio >= 1.5:
        return "READY"
    if current_price >= max_close * 0.92:
        return "WATCH"
    return ""

def _vol_signal(ratio: float) -> str:
    if ratio > 2.0: return f"🔥 Explosive ({ratio})"
    if ratio > 1.5: return f"🟢 Strong ({ratio})"
    if ratio > 1.0: return f"🟡 Build ({ratio})"
    return f"🔴 Weak ({ratio})"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — MARKET HOURS
# ─────────────────────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    try:
        import pytz
        IST  = pytz.timezone("Asia/Kolkata")
        now  = datetime.now(pytz.utc).astimezone(IST)
        if now.weekday() >= 5:
            return False
        mins = now.hour * 60 + now.minute
        return (9 * 60 + 15) <= mins <= (15 * 60 + 30)
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — DB: CHECK IF LAST TRADING DAY DATA EXISTS
# ─────────────────────────────────────────────────────────────────────────────

def _get_last_trading_day() -> str:
    """
    Returns the last trading day (Mon-Fri) as YYYY-MM-DD string.
    - During market hours (9:15-15:30 on weekday) → today
    - Pre-market / post-market / weekend → most recent weekday
    """
    import pytz
    IST = pytz.timezone("Asia/Kolkata")
    now = datetime.now(pytz.utc).astimezone(IST)

    mins = now.hour * 60 + now.minute
    market_open_now = (now.weekday() < 5) and ((9 * 60 + 15) <= mins <= (15 * 60 + 30))

    if market_open_now:
        return now.date().isoformat()

    d = now.date()
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def db_has_last_trading_day(symbols: list) -> bool:
    """
    Check if ANY ONE symbol has the last trading day's date in swing_price_data.
    Single lightweight DB query.
    """
    if not symbols:
        return False
    try:
        uid          = _get_user_id()
        last_trd_day = _get_last_trading_day()
        first        = symbols[0]
        print(f"[swing_core] Checking DB for last trading day: {last_trd_day}")
        r = requests.get(
            _price_table_url(),
            headers=_headers(),
            params={
                "select":     "trade_date",
                "user_id":    f"eq.{uid}",
                "symbol":     f"eq.{first}",
                "trade_date": f"eq.{last_trd_day}",
                "limit":      "1",
            },
            timeout=8,
        )
        r.raise_for_status()
        found = len(r.json()) > 0
        print(f"[swing_core] DB has {last_trd_day}: {found}")
        return found
    except Exception as e:
        print(f"[swing_core] db_has_last_trading_day check failed: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — DB: LOAD ALL PRICE DATA (1 QUERY FOR ALL SYMBOLS)
# ── FIX v3.1: Range: 0-9999 header bypasses Supabase 1000 row default limit ──
# ─────────────────────────────────────────────────────────────────────────────

def _load_all_from_db(symbols: list) -> dict:
    """
    Load last 14 calendar days of OHLCV from swing_price_data for all symbols.
    Single query with Range header → returns {symbol: [rows oldest→newest]}.

    FIX v3.1: Supabase default limit is 1000 rows. With 850 stocks × 6 days
    = 5100 rows needed, the old code silently truncated after ~200 stocks,
    causing the rest to fall back to yfinance one by one (the slow path).
    Range: 0-9999 returns all rows in one shot — no pagination needed.
    """
    try:
        uid    = _get_user_id()
        from_d = (date.today() - timedelta(days=14)).isoformat()

        # Override Supabase default 1000 row limit — get all rows in one shot
        headers = {**_headers(), "Range-Unit": "items", "Range": "0-9999"}

        r = requests.get(
            _price_table_url(),
            headers=headers,
            params={
                "select":     "symbol,trade_date,open,high,low,close,volume",
                "user_id":    f"eq.{uid}",
                "trade_date": f"gte.{from_d}",
                "order":      "symbol.asc,trade_date.asc",
            },
            timeout=20,
        )
        r.raise_for_status()
        rows = r.json()

        result = {}
        for row in rows:
            sym = row["symbol"]
            if sym not in result:
                result[sym] = []
            if all(row.get(k) is not None for k in ["open", "high", "low", "close", "volume"]):
                result[sym].append(row)

        print(f"[swing_core] DB loaded {len(rows)} rows for {len(result)} symbols")
        return result

    except Exception as e:
        print(f"[swing_core] _load_all_from_db error: {e}")
        return {}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — DB: SAVE PRICE DATA (ASYNC, NON-BLOCKING)
# ─────────────────────────────────────────────────────────────────────────────

def _save_to_db_async(results: list):
    """
    Save today's OHLCV row to swing_price_data after refresh.
    Runs in background thread — never blocks the UI.
    """
    def _do_save():
        uid  = _get_user_id()
        hdrs = {**_headers(), "Prefer": "resolution=merge-duplicates"}
        rows = []

        today_str = date.today().isoformat()

        for r in results:
            if r.get("error"):
                continue
            sym = r["symbol"]
            rows.append({
                "user_id":    uid,
                "symbol":     sym,
                "trade_date": today_str,
                "open":       r.get("current_open"),
                "high":       r.get("current_high"),
                "low":        r.get("current_low"),
                "close":      r.get("current_price"),
                "volume":     r.get("current_vol"),
            })

        if not rows:
            return

        for i in range(0, len(rows), 200):
            batch = rows[i:i+200]
            try:
                resp = requests.post(
                    _price_table_url(),
                    headers=hdrs,
                    json=batch,
                    timeout=20,
                )
                resp.raise_for_status()
            except Exception as e:
                print(f"[swing_core] save_to_db batch {i}: {e}")

    threading.Thread(target=_do_save, daemon=True).start()


def _save_full_to_db_async(results: list):
    """
    Save ALL rows (5 hist + today) with proper ISO dates.
    Called after first-time yfinance fetch.
    """
    def _do_save():
        uid  = _get_user_id()
        hdrs = {**_headers(), "Prefer": "resolution=merge-duplicates"}
        rows = []

        today_str = date.today().isoformat()

        for r in results:
            if r.get("error"):
                continue
            sym = r["symbol"]

            hist_iso  = r.get("hist_iso_dates", [])
            hist_o    = r.get("hist_opens",   [])
            hist_h    = r.get("hist_highs",   [])
            hist_l    = r.get("hist_lows",    [])
            hist_c    = r.get("hist_closes",  [])
            hist_v    = r.get("hist_volumes", [])

            for i, iso_date in enumerate(hist_iso):
                if i < len(hist_c):
                    rows.append({
                        "user_id":    uid,
                        "symbol":     sym,
                        "trade_date": iso_date,
                        "open":       hist_o[i] if i < len(hist_o) else None,
                        "high":       hist_h[i] if i < len(hist_h) else None,
                        "low":        hist_l[i] if i < len(hist_l) else None,
                        "close":      hist_c[i],
                        "volume":     hist_v[i] if i < len(hist_v) else None,
                    })

            rows.append({
                "user_id":    uid,
                "symbol":     sym,
                "trade_date": today_str,
                "open":       r.get("current_open"),
                "high":       r.get("current_high"),
                "low":        r.get("current_low"),
                "close":      r.get("current_price"),
                "volume":     r.get("current_vol"),
            })

        if not rows:
            return

        for i in range(0, len(rows), 200):
            batch = rows[i:i+200]
            try:
                resp = requests.post(
                    _price_table_url(),
                    headers=hdrs,
                    json=batch,
                    timeout=20,
                )
                resp.raise_for_status()
            except Exception as e:
                print(f"[swing_core] save_full batch {i}: {e}")

    threading.Thread(target=_do_save, daemon=True).start()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9 — BUILD RESULT FROM DB ROWS
# ─────────────────────────────────────────────────────────────────────────────

def _build_from_db_rows(sym: str, all_rows: list, meta: dict) -> dict:
    """
    Build a full result dict from DB rows for one symbol.
    all_rows: sorted oldest→newest, includes today as last row.
    - last row  = today's candle  → current_* (purple candle)
    - prev rows = hist candles    → hist_* (grey/green/red candles)
    """
    if not all_rows:
        return None

    today_row = all_rows[-1]
    hist_rows = all_rows[:-1]

    disp_rows = hist_rows[-5:] if len(hist_rows) >= 5 else hist_rows

    all_closes  = [float(r["close"])  for r in hist_rows]
    all_volumes = [int(r["volume"])   for r in hist_rows]

    hist_dates   = [datetime.strptime(r["trade_date"], "%Y-%m-%d").strftime("%d %b") for r in disp_rows]
    hist_opens   = [round(float(r["open"]),   2) for r in disp_rows]
    hist_highs   = [round(float(r["high"]),   2) for r in disp_rows]
    hist_lows    = [round(float(r["low"]),    2) for r in disp_rows]
    hist_closes  = [round(float(r["close"]),  2) for r in disp_rows]
    hist_volumes = [int(r["volume"])              for r in disp_rows]

    current_price = round(float(today_row["close"]),  2)
    current_open  = round(float(today_row["open"]),   2)
    current_high  = round(float(today_row["high"]),   2)
    current_low   = round(float(today_row["low"]),    2)
    current_vol   = int(today_row["volume"])
    current_date  = datetime.strptime(today_row["trade_date"], "%Y-%m-%d").strftime("%d %b")

    max_close   = max(all_closes)  if all_closes  else current_price
    clean_vols  = [v for v in all_volumes if v and v > 0]
    median_vol  = statistics.median(clean_vols) if clean_vols else 1
    vol_ratio   = round(current_vol / median_vol, 2) if median_vol > 0 else 0
    status      = _calc_status(current_price, max_close, current_vol, all_volumes, vol_ratio)
    vol_signal  = _vol_signal(vol_ratio)
    pct_vs_high = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

    return {
        "symbol":        sym,
        "error":         None,
        "source":        "db",
        "hist_dates":    hist_dates,
        "hist_opens":    hist_opens,
        "hist_highs":    hist_highs,
        "hist_lows":     hist_lows,
        "hist_closes":   hist_closes,
        "hist_volumes":  hist_volumes,
        "current_date":  current_date,
        "current_price": current_price,
        "current_open":  current_open,
        "current_high":  current_high,
        "current_low":   current_low,
        "current_vol":   current_vol,
        "max_close":     round(max_close, 2),
        "median_vol":    int(median_vol),
        "vol_ratio":     vol_ratio,
        "vol_signal":    vol_signal,
        "pct_vs_high":   pct_vs_high,
        "status":        status,
        "screener_url":  meta.get("screener_url",  f"https://www.screener.in/company/{sym}/"),
        "breakout_date": meta.get("breakout_date", ""),
        "notes":         meta.get("notes",         ""),
        "db_id":         meta.get("id"),
    }

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — YFINANCE FETCH
# ── FIX v3.1: period="10d" instead of "2y" — 50x less data to download ──────
# ─────────────────────────────────────────────────────────────────────────────

def _build_result_from_df(symbol: str, df) -> dict:
    """
    Shared helper — builds the full result dict from a single-stock DataFrame.
    """
    hist = df.iloc[-6:-1]
    cur  = df.iloc[-1]

    hist_closes  = hist["Close"].tolist()
    hist_volumes = hist["Volume"].tolist()
    hist_opens   = hist["Open"].tolist()
    hist_highs   = hist["High"].tolist()
    hist_lows    = hist["Low"].tolist()
    hist_dates   = hist.index.strftime("%d %b").tolist()
    hist_iso     = hist.index.strftime("%Y-%m-%d").tolist()

    current_price = round(float(cur["Close"]), 2)
    current_open  = round(float(cur["Open"]),  2)
    current_high  = round(float(cur["High"]),  2)
    current_low   = round(float(cur["Low"]),   2)
    current_vol   = int(cur["Volume"])
    current_date  = df.index[-1].strftime("%d %b")

    max_close   = max(hist_closes)
    clean_vols  = [v for v in hist_volumes if v and v > 0]
    median_vol  = statistics.median(clean_vols) if clean_vols else 1
    vol_ratio   = round(current_vol / median_vol, 2) if median_vol > 0 else 0
    status      = _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio)
    vol_signal  = _vol_signal(vol_ratio)
    pct_vs_high = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

    return {
        "symbol":          symbol,
        "error":           None,
        "source":          "yfinance",
        "hist_dates":      hist_dates,
        "hist_iso_dates":  hist_iso,
        "hist_opens":      [round(float(v), 2) for v in hist_opens],
        "hist_highs":      [round(float(v), 2) for v in hist_highs],
        "hist_lows":       [round(float(v), 2) for v in hist_lows],
        "hist_closes":     [round(float(v), 2) for v in hist_closes],
        "hist_volumes":    [int(v)             for v in hist_volumes],
        "current_date":    current_date,
        "current_price":   current_price,
        "current_open":    current_open,
        "current_high":    current_high,
        "current_low":     current_low,
        "current_vol":     current_vol,
        "max_close":       round(max_close, 2),
        "median_vol":      int(median_vol),
        "vol_ratio":       vol_ratio,
        "vol_signal":      vol_signal,
        "pct_vs_high":     pct_vs_high,
        "status":          status,
    }


def _fetch_all_yf_bulk(symbols: list) -> dict:
    """
    FAST PATH — single yf.download() call for ALL symbols at once.

    FIX v3.1: period changed from "2y" to "10d"
    Old: 850 stocks × 2 years  = ~425,000 rows downloaded
    New: 850 stocks × 10 days  = ~8,500 rows downloaded  (50x less data)
    We only need 6 trading days so 10 calendar days is more than enough.
    """
    import pandas as pd

    tickers    = [f"{sym}.NS" for sym in symbols]
    ticker_str = " ".join(tickers)
    sym_map    = {f"{sym}.NS": sym for sym in symbols}
    results    = {}

    try:
        print(f"[swing_core] yf.download bulk — {len(symbols)} stocks (period=10d)")
        data = yf.download(
            tickers      = ticker_str,
            period       = "10d",        # FIX v3.1: was "2y" — 50x less data
            interval     = "1d",
            group_by     = "ticker",
            auto_adjust  = False,
            progress     = False,
        )

        if data is None or data.empty:
            print("[swing_core] yf.download returned empty — falling back to per-stock")
            return {sym: {"symbol": sym, "error": "Bulk download empty"} for sym in symbols}

        for ticker, sym in sym_map.items():
            try:
                if ticker in data.columns.levels[0]:
                    df_stock = data[ticker].copy()
                else:
                    results[sym] = {"symbol": sym, "error": "Ticker not in bulk data"}
                    continue

                df_stock = df_stock.dropna(subset=["Close", "Volume"])

                if len(df_stock) < 6:
                    results[sym] = {"symbol": sym, "error": f"Only {len(df_stock)} rows"}
                    continue

                results[sym] = _build_result_from_df(sym, df_stock)

            except Exception as e:
                results[sym] = {"symbol": sym, "error": f"Parse error: {e}"}

    except Exception as e:
        print(f"[swing_core] yf.download failed: {e} — will fallback per-stock")
        return {sym: {"symbol": sym, "error": f"Bulk failed: {e}"} for sym in symbols}

    return results


def _fetch_single_yf(symbol: str) -> dict:
    """
    Fallback — fetch one stock individually.
    Used when bulk download fails for a specific stock.
    """
    symbol = symbol.lstrip("$").strip().upper()
    try:
        df = yf.Ticker(f"{symbol}.NS").history(
            period="15d", interval="1d", auto_adjust=True
        )
        if df is None or df.empty:
            return {"symbol": symbol, "error": "No data from yfinance"}

        df = df.dropna(subset=["Close", "Volume"])

        if len(df) < 6:
            return {"symbol": symbol, "error": f"Only {len(df)} trading days available"}

        return _build_result_from_df(symbol, df)

    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def _fetch_live_single(symbol: str) -> dict:
    """Fetch only today's live candle — used for refresh."""
    symbol = symbol.lstrip("$").strip().upper()
    try:
        df = yf.Ticker(f"{symbol}.NS").history(
            period="2d", interval="1d", auto_adjust=True
        )
        if df is None or df.empty:
            return {"symbol": symbol, "error": "No data"}
        cur = df.iloc[-1]
        return {
            "symbol":        symbol,
            "error":         None,
            "current_price": round(float(cur["Close"]), 2),
            "current_open":  round(float(cur["Open"]),  2),
            "current_high":  round(float(cur["High"]),  2),
            "current_low":   round(float(cur["Low"]),   2),
            "current_vol":   int(cur["Volume"]),
            "current_date":  df.index[-1].strftime("%d %b"),
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 11 — MAIN SCAN RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_swing_scan(stocks: list, batch_size: int = 25) -> tuple:
    """
    Smart scan — DB-first when last trading day data exists, yfinance otherwise.

    FLOW:
      1. Find last trading day (e.g. Wednesday 2AM → Tuesday)
      2. Check if DB has that date for first symbol (1 fast query)
      3a. IN DB     → load ALL symbols from DB (1 query) → instant results
      3b. NOT IN DB → fetch all from yfinance → save to DB async
    """
    stock_meta = {s["symbol"]: s for s in stocks}
    symbols    = [s["symbol"] for s in stocks]
    results, errors = [], []

    # ── STEP 1: Check DB for last trading day (one lightweight query) ─────────
    if db_has_last_trading_day(symbols):
        print(f"[swing_core] DB hit — loading all {len(symbols)} stocks from DB")
        all_db_rows = _load_all_from_db(symbols)

        for sym in symbols:
            rows = all_db_rows.get(sym, [])
            if len(rows) >= 2:
                meta   = stock_meta.get(sym, {})
                result = _build_from_db_rows(sym, rows, meta)
                if result:
                    results.append(result)
                else:
                    errors.append({"symbol": sym, "error": "DB build failed"})
            else:
                errors.append({"symbol": sym, "error": f"Only {len(rows)} DB rows"})

        priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
        results.sort(key=lambda x: priority.get(x.get("status", ""), 3))
        return results, errors

    # ── STEP 2: DB miss — fetch from yfinance, then save async ───────────────
    print(f"[swing_core] DB miss — bulk yf.download for {len(symbols)} stocks")
    bulk = _fetch_all_yf_bulk(symbols)

    fallback_syms = []
    for sym in symbols:
        d = bulk.get(sym, {"symbol": sym, "error": "Not in bulk result"})
        if not d.get("error"):
            m = stock_meta.get(sym, {})
            d["screener_url"]  = m.get("screener_url",  f"https://www.screener.in/company/{sym}/")
            d["breakout_date"] = m.get("breakout_date", "")
            d["notes"]         = m.get("notes",         "")
            d["db_id"]         = m.get("id")
            results.append(d)
        else:
            fallback_syms.append(sym)

    # Per-stock fallback only for bulk failures (should be rare)
    if fallback_syms:
        print(f"[swing_core] fallback per-stock for {len(fallback_syms)} stocks")
        with ThreadPoolExecutor(max_workers=min(25, len(fallback_syms))) as ex:
            futures = {ex.submit(_fetch_single_yf, sym): sym for sym in fallback_syms}
            for f in as_completed(futures):
                d   = f.result()
                sym = d["symbol"]
                if not d.get("error"):
                    m = stock_meta.get(sym, {})
                    d["screener_url"]  = m.get("screener_url",  f"https://www.screener.in/company/{sym}/")
                    d["breakout_date"] = m.get("breakout_date", "")
                    d["notes"]         = m.get("notes",         "")
                    d["db_id"]         = m.get("id")
                    results.append(d)
                else:
                    errors.append({"symbol": sym, "error": d["error"]})

    # Save to DB async so NEXT scan loads instantly from DB
    _save_full_to_db_async(results)

    priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
    results.sort(key=lambda x: priority.get(x.get("status", ""), 3))
    return results, errors

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 12 — REFRESH LIVE DATA
# ─────────────────────────────────────────────────────────────────────────────

def refresh_live_data(results: list, batch_size: int = 25) -> list:
    """
    Refresh only today's live price + volume from yfinance.
    Hist data stays unchanged (already correct from scan).
    Saves updated today row to DB async.
    """
    if not results:
        return results

    symbols    = [r["symbol"] for r in results]
    result_map = {r["symbol"]: r for r in results}
    batches    = [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]
    updated    = {}

    for batch in batches:
        with ThreadPoolExecutor(max_workers=batch_size) as ex:
            futures = {ex.submit(_fetch_live_single, sym): sym for sym in batch}
            for f in as_completed(futures):
                live = f.result()
                sym  = live["symbol"]
                if live.get("error"):
                    continue

                old           = result_map.get(sym, {})
                hist_volumes  = old.get("hist_volumes", [])
                current_price = live["current_price"]
                current_vol   = live["current_vol"]
                max_close     = old.get("max_close", current_price)
                clean_vols    = [v for v in hist_volumes if v and v > 0]
                median_vol    = statistics.median(clean_vols) if clean_vols else 1
                vol_ratio     = round(current_vol / median_vol, 2) if median_vol > 0 else 0
                status        = _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio)
                vol_signal    = _vol_signal(vol_ratio)
                pct_vs_high   = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

                updated[sym] = {
                    **old,
                    "current_price": current_price,
                    "current_open":  live["current_open"],
                    "current_high":  live["current_high"],
                    "current_low":   live["current_low"],
                    "current_vol":   current_vol,
                    "current_date":  live["current_date"],
                    "vol_ratio":     vol_ratio,
                    "vol_signal":    vol_signal,
                    "pct_vs_high":   pct_vs_high,
                    "status":        status,
                    "median_vol":    int(median_vol),
                }

    # Save updated today rows to DB async
    _save_to_db_async(list(updated.values()))

    final = [updated.get(r["symbol"], r) for r in results]
    priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
    final.sort(key=lambda x: priority.get(x.get("status", ""), 3))
    return final
