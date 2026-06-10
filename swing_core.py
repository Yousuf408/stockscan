# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — swing_core.py  v4.0
#  Complete rewrite. Clean architecture.
#
#  TABLES:
#    swing_watchlist  — master symbol list (user's tracked stocks)
#    swing_hist_data  — last 5 trading days OHLCV per symbol (no NULLs ever)
#    swing_live_data  — today's live price per symbol, one row, overwritten
#
#  FLOW:
#    Page load      → load_from_db()     — reads both tables, instant, no yfinance
#    Sync 5D button → sync_5d_history()  — fetch only MISSING days from yfinance
#    Refresh Live   → refresh_live()     — fetch today only, update swing_live_data
#
#  RULES:
#    - No NULLs ever saved to DB
#    - yfinance period="7d" max — never "3mo"
#    - uid always captured in main thread before any daemon thread
#    - swing_hist_data keeps exactly last 5 trading days per symbol
#    - swing_live_data keeps exactly 1 row per symbol (upsert)
# ══════════════════════════════════════════════════════════════════════════════

import os, requests, yfinance as yf, statistics, threading
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CONFIG & SUPABASE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

HIST_DAYS = 5  # number of trading days to show in chart

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

def _url(table: str) -> str:
    url, _ = _get_config()
    return f"{url}/rest/v1/{table}"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — SWING WATCHLIST CRUD
# ─────────────────────────────────────────────────────────────────────────────

def load_swing_stocks() -> list:
    try:
        uid = _get_user_id()
        if not uid:
            return []
        r = requests.get(
            _url("swing_watchlist"),
            headers=_headers(),
            params={"select": "*", "user_id": f"eq.{uid}", "order": "symbol.asc"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[swing_core] load_swing_stocks error: {e}")
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
    r = requests.post(_url("swing_watchlist"), headers=_headers(), json=row, timeout=10)
    r.raise_for_status()
    d = r.json()
    return d[0] if isinstance(d, list) else d

def update_swing_stock(db_id: int, updates: dict):
    allowed = {"screener_url", "breakout_date", "notes", "symbol"}
    clean   = {k: v for k, v in updates.items() if k in allowed}
    if not clean:
        return
    r = requests.patch(
        f"{_url('swing_watchlist')}?id=eq.{db_id}",
        headers=_headers(), json=clean, timeout=10,
    )
    r.raise_for_status()
    return r.json()

def delete_swing_stock(db_id: int):
    r = requests.delete(
        f"{_url('swing_watchlist')}?id=eq.{db_id}",
        headers=_headers(), timeout=10,
    )
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
            r = requests.post(_url("swing_watchlist"), headers=_headers(), json=rows, timeout=15)
            r.raise_for_status()
        except Exception:
            errors = added.copy()
            added  = []
    return {"added": added, "skipped": skipped, "errors": errors}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3 — HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def fmt_vol(v) -> str:
    if v is None:
        return "—"
    v = int(v)
    if v >= 10_000_000: return f"{v/10_000_000:.2f}Cr"
    if v >= 100_000:    return f"{v/100_000:.2f}L"
    if v >= 1_000:      return f"{v/1_000:.1f}K"
    return str(v)

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

def _last_n_trading_days(n: int) -> list:
    """
    Returns last N trading days (Mon-Fri) as date objects, most recent last.
    Looks back up to 30 calendar days to find N trading days.
    """
    import pytz
    IST  = pytz.timezone("Asia/Kolkata")
    now  = datetime.now(pytz.utc).astimezone(IST)
    today = now.date()

    days = []
    d    = today
    while len(days) < n:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d -= timedelta(days=1)

    return list(reversed(days))  # oldest first

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

def _build_result(sym: str, hist_rows: list, live_row: dict, meta: dict) -> dict:
    """
    Build a single result dict from hist DB rows + live DB row + watchlist meta.
    hist_rows : list of dicts from swing_hist_data, sorted oldest→newest, max 5
    live_row  : dict from swing_live_data (today's price), or None
    meta      : dict from swing_watchlist (screener_url, breakout_date, notes, id)
    """
    if not hist_rows:
        return None

    # Hist fields
    hist_dates   = [datetime.strptime(r["trade_date"], "%Y-%m-%d").strftime("%d %b") for r in hist_rows]
    hist_opens   = [round(float(r["open"]),   2) for r in hist_rows]
    hist_highs   = [round(float(r["high"]),   2) for r in hist_rows]
    hist_lows    = [round(float(r["low"]),    2) for r in hist_rows]
    hist_closes  = [round(float(r["close"]),  2) for r in hist_rows]
    hist_volumes = [int(r["volume"])              for r in hist_rows]

    # Live fields — fallback to last hist row if no live data
    if live_row:
        current_price = round(float(live_row["close"]), 2)
        current_open  = round(float(live_row["open"]),  2)
        current_high  = round(float(live_row["high"]),  2)
        current_low   = round(float(live_row["low"]),   2)
        current_vol   = int(live_row["volume"])
        current_date  = datetime.strptime(live_row["trade_date"], "%Y-%m-%d").strftime("%d %b")
    else:
        # No live data — use last hist row as current
        last          = hist_rows[-1]
        current_price = round(float(last["close"]), 2)
        current_open  = round(float(last["open"]),  2)
        current_high  = round(float(last["high"]),  2)
        current_low   = round(float(last["low"]),   2)
        current_vol   = int(last["volume"])
        current_date  = datetime.strptime(last["trade_date"], "%Y-%m-%d").strftime("%d %b")

    max_close   = max(hist_closes) if hist_closes else current_price
    clean_vols  = [v for v in hist_volumes if v and v > 0]
    median_vol  = statistics.median(clean_vols) if clean_vols else 1
    vol_ratio   = round(current_vol / median_vol, 2) if median_vol > 0 else 0
    status      = _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio)
    vol_signal  = _vol_signal(vol_ratio)
    pct_vs_high = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

    return {
        "symbol":        sym,
        "error":         None,
        # hist
        "hist_dates":    hist_dates,
        "hist_opens":    hist_opens,
        "hist_highs":    hist_highs,
        "hist_lows":     hist_lows,
        "hist_closes":   hist_closes,
        "hist_volumes":  hist_volumes,
        # live
        "current_date":  current_date,
        "current_price": current_price,
        "current_open":  current_open,
        "current_high":  current_high,
        "current_low":   current_low,
        "current_vol":   current_vol,
        # signals
        "max_close":     round(max_close, 2),
        "median_vol":    int(median_vol),
        "vol_ratio":     vol_ratio,
        "vol_signal":    vol_signal,
        "pct_vs_high":   pct_vs_high,
        "status":        status,
        # meta
        "screener_url":  meta.get("screener_url",  f"https://www.screener.in/company/{sym}/"),
        "breakout_date": meta.get("breakout_date", ""),
        "notes":         meta.get("notes",         ""),
        "db_id":         meta.get("id"),
    }

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4 — PAGE LOAD: READ FROM DB (NO YFINANCE)
# ─────────────────────────────────────────────────────────────────────────────

def load_from_db() -> tuple:
    """
    Page load function. Reads swing_hist_data + swing_live_data.
    No yfinance. Returns (results, errors) in ~1 second.

    Returns whatever is in DB — even if symbol has only 1-2 hist rows.
    Symbols with zero hist rows are skipped silently.
    """
    stocks = load_swing_stocks()
    if not stocks:
        return [], []

    uid       = _get_user_id()
    meta_map  = {s["symbol"]: s for s in stocks}
    symbols   = [s["symbol"] for s in stocks]
    results, errors = [], []

    # ── Query 1: swing_hist_data — last 10 calendar days covers 5+ trading days ──
    from_d = (date.today() - timedelta(days=14)).isoformat()
    try:
        r = requests.get(
            _url("swing_hist_data"),
            headers={**_headers(), "Range-Unit": "items", "Range": "0-9999"},
            params={
                "select":     "symbol,trade_date,open,high,low,close,volume",
                "user_id":    f"eq.{uid}",
                "trade_date": f"gte.{from_d}",
                "order":      "symbol.asc,trade_date.asc",
            },
            timeout=15,
        )
        r.raise_for_status()
        hist_rows = r.json()
    except Exception as e:
        print(f"[swing_core] load_from_db hist query error: {e}")
        return [], [{"symbol": "ALL", "error": f"DB hist read failed: {e}"}]

    # Group hist rows by symbol — take last HIST_DAYS rows
    hist_map = {}
    for row in hist_rows:
        sym = row["symbol"]
        if sym not in hist_map:
            hist_map[sym] = []
        hist_map[sym].append(row)
    for sym in hist_map:
        hist_map[sym] = sorted(hist_map[sym], key=lambda x: x["trade_date"])[-HIST_DAYS:]

    # ── Query 2: swing_live_data — one row per symbol ──
    live_map = {}
    try:
        r = requests.get(
            _url("swing_live_data"),
            headers={**_headers(), "Range-Unit": "items", "Range": "0-9999"},
            params={
                "select":  "symbol,trade_date,open,high,low,close,volume",
                "user_id": f"eq.{uid}",
            },
            timeout=15,
        )
        r.raise_for_status()
        for row in r.json():
            live_map[row["symbol"]] = row
    except Exception as e:
        print(f"[swing_core] load_from_db live query error: {e}")
        # Non-fatal — continue without live data

    # ── Build results ──
    for sym in symbols:
        hist = hist_map.get(sym, [])
        if not hist:
            # No hist data yet — skip, will appear after Sync 5D
            continue
        live   = live_map.get(sym)
        meta   = meta_map.get(sym, {})
        result = _build_result(sym, hist, live, meta)
        if result:
            results.append(result)

    # Sort by status priority
    priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
    results.sort(key=lambda x: priority.get(x.get("status", ""), 3))

    print(f"[swing_core] load_from_db — {len(results)} symbols loaded from DB")
    return results, errors

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — SYNC 5D HISTORY
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_yf_bulk(symbols: list, period: str = "7d") -> dict:
    """
    Bulk yfinance download for given symbols.
    Returns dict: {symbol: DataFrame row list} or {symbol: error}
    Chunked at 200 tickers per batch.
    """
    import pandas as pd

    sym_map     = {f"{s}.NS": s for s in symbols}
    all_tickers = list(sym_map.keys())
    results     = {}
    chunks      = [all_tickers[i:i+200] for i in range(0, len(all_tickers), 200)]

    print(f"[swing_core] yf.download {len(symbols)} symbols in {len(chunks)} chunks, period={period}")

    for idx, chunk in enumerate(chunks):
        try:
            print(f"[swing_core] chunk {idx+1}/{len(chunks)} — {len(chunk)} tickers")
            data = yf.download(
                tickers     = " ".join(chunk),
                period      = period,
                interval    = "1d",
                group_by    = "ticker",
                auto_adjust = True,
                progress    = False,
            )

            if data is None or data.empty:
                for ticker in chunk:
                    results[sym_map[ticker]] = {"error": "Empty response"}
                continue

            for ticker in chunk:
                sym = sym_map[ticker]
                try:
                    df = data.copy() if len(chunk) == 1 else (
                        data[ticker].copy() if ticker in data.columns.get_level_values(0) else None
                    )
                    if df is None:
                        results[sym] = {"error": "Ticker not in response"}
                        continue

                    df = df.dropna(subset=["Close", "Volume"])
                    if df.empty:
                        results[sym] = {"error": "No valid rows after dropna"}
                        continue

                    results[sym] = {"df": df}

                except Exception as e:
                    results[sym] = {"error": f"Parse error: {e}"}

        except Exception as e:
            for ticker in chunk:
                results[sym_map[ticker]] = {"error": f"Chunk failed: {e}"}

    return results


def sync_5d_history() -> dict:
    """
    Smart sync — fetches only MISSING trading days from yfinance.

    Steps:
    1. Load existing dates from swing_hist_data per symbol
    2. Calculate last HIST_DAYS trading days
    3. Find which dates are missing per symbol
    4. Fetch only missing data from yfinance (period="7d")
    5. Save new complete OHLCV rows to swing_hist_data (no NULLs)
    6. Delete rows older than last HIST_DAYS trading days per symbol
    """
    uid    = _get_user_id()  # capture in main thread
    stocks = load_swing_stocks()
    if not stocks:
        return {"synced": 0, "skipped": 0, "errors": []}

    symbols          = [s["symbol"] for s in stocks]
    required_days    = _last_n_trading_days(HIST_DAYS)  # last 5 trading days as date objects
    required_iso     = {d.isoformat() for d in required_days}

    # ── Step 1: Load existing dates from DB ──
    from_d = (min(required_days) - timedelta(days=1)).isoformat()
    existing_map = {}  # {symbol: set of existing iso date strings}
    try:
        r = requests.get(
            _url("swing_hist_data"),
            headers={**_headers(), "Range-Unit": "items", "Range": "0-9999"},
            params={
                "select":     "symbol,trade_date",
                "user_id":    f"eq.{uid}",
                "trade_date": f"gte.{from_d}",
            },
            timeout=15,
        )
        r.raise_for_status()
        for row in r.json():
            sym = row["symbol"]
            if sym not in existing_map:
                existing_map[sym] = set()
            existing_map[sym].add(row["trade_date"])
    except Exception as e:
        print(f"[swing_core] sync_5d existing dates query error: {e}")

    # ── Step 2: Find symbols that need fetching ──
    need_fetch = []  # symbols with at least one missing day
    skip_count = 0
    for sym in symbols:
        existing = existing_map.get(sym, set())
        missing  = required_iso - existing
        if missing:
            need_fetch.append(sym)
        else:
            skip_count += 1

    print(f"[swing_core] sync_5d — {len(need_fetch)} need fetch, {skip_count} already complete")

    if not need_fetch:
        return {"synced": 0, "skipped": skip_count, "errors": []}

    # ── Step 3: Fetch from yfinance ──
    bulk    = _fetch_yf_bulk(need_fetch, period="7d")
    errors  = []
    to_save = []  # list of complete OHLCV row dicts

    for sym in need_fetch:
        res = bulk.get(sym, {"error": "Not in bulk result"})
        if "error" in res:
            errors.append({"symbol": sym, "error": res["error"]})
            continue

        df = res["df"]

        # Build rows for each required trading day
        for req_date in required_days:
            iso = req_date.isoformat()
            # Find matching row in df
            matching = df[df.index.date == req_date] if not df.empty else None
            if matching is None or matching.empty:
                continue  # that day not in yfinance data (holiday etc)

            row_data = matching.iloc[0]

            # Skip if any OHLCV is null/zero — enforce no NULLs rule
            o = float(row_data["Open"])
            h = float(row_data["High"])
            l = float(row_data["Low"])
            c = float(row_data["Close"])
            v = int(row_data["Volume"])

            if not all([o, h, l, c, v]):
                continue

            to_save.append({
                "user_id":    uid,
                "symbol":     sym,
                "trade_date": iso,
                "open":       round(o, 2),
                "high":       round(h, 2),
                "low":        round(l, 2),
                "close":      round(c, 2),
                "volume":     v,
            })

    # ── Step 4: Save to swing_hist_data (upsert) ──
    synced = 0
    if to_save:
        hdrs = {**_headers(), "Prefer": "resolution=merge-duplicates"}
        for i in range(0, len(to_save), 200):
            batch = to_save[i:i+200]
            try:
                resp = requests.post(
                    _url("swing_hist_data"),
                    headers=hdrs,
                    json=batch,
                    timeout=20,
                )
                resp.raise_for_status()
                synced += len(batch)
                print(f"[swing_core] sync_5d saved batch {i} — {len(batch)} rows")
            except Exception as e:
                print(f"[swing_core] sync_5d save error batch {i}: {e}")
                errors.append({"symbol": "batch", "error": str(e)})

    # ── Step 5: Delete old rows beyond HIST_DAYS per symbol ──
    # Delete anything older than the oldest required trading day
    oldest_required = min(required_days).isoformat()

    def _delete_old():
        try:
            resp = requests.delete(
                _url("swing_hist_data"),
                headers=_headers(),
                params={
                    "user_id":    f"eq.{uid}",
                    "trade_date": f"lt.{oldest_required}",
                },
                timeout=15,
            )
            resp.raise_for_status()
            print(f"[swing_core] sync_5d deleted rows older than {oldest_required}")
        except Exception as e:
            print(f"[swing_core] sync_5d delete old rows error: {e}")

    threading.Thread(target=_delete_old, daemon=True).start()

    print(f"[swing_core] sync_5d complete — {synced} rows saved, {len(errors)} errors")
    return {"synced": synced, "skipped": skip_count, "errors": errors}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — REFRESH LIVE
# ─────────────────────────────────────────────────────────────────────────────

def refresh_live() -> dict:
    """
    Fetch today's live OHLCV from yfinance for all symbols.
    Saves/overwrites one row per symbol in swing_live_data.
    Returns (results, errors) after updating DB.
    """
    uid    = _get_user_id()  # capture in main thread
    stocks = load_swing_stocks()
    if not stocks:
        return {"updated": 0, "errors": []}

    symbols = [s["symbol"] for s in stocks]

    # Fetch today + yesterday (period="2d") — today's candle only
    bulk   = _fetch_yf_bulk(symbols, period="2d")
    errors = []
    to_save = []

    today = date.today()

    for sym in symbols:
        res = bulk.get(sym, {"error": "Not in bulk result"})
        if "error" in res:
            errors.append({"symbol": sym, "error": res["error"]})
            continue

        df = res["df"]
        if df.empty:
            errors.append({"symbol": sym, "error": "Empty df"})
            continue

        # Always take the last row — most recent available candle
        row_data   = df.iloc[-1]
        trade_date = df.index[-1].date().isoformat()

        o = float(row_data["Open"])
        h = float(row_data["High"])
        l = float(row_data["Low"])
        c = float(row_data["Close"])
        v = int(row_data["Volume"])

        if not all([o, h, l, c, v]):
            errors.append({"symbol": sym, "error": "Incomplete OHLCV from yfinance"})
            continue

        to_save.append({
            "user_id":    uid,
            "symbol":     sym,
            "trade_date": trade_date,
            "open":       round(o, 2),
            "high":       round(h, 2),
            "low":        round(l, 2),
            "close":      round(c, 2),
            "volume":     v,
        })

    # Upsert into swing_live_data — unique on (user_id, symbol)
    updated = 0
    if to_save:
        hdrs = {**_headers(), "Prefer": "resolution=merge-duplicates"}
        for i in range(0, len(to_save), 200):
            batch = to_save[i:i+200]
            try:
                resp = requests.post(
                    _url("swing_live_data"),
                    headers=hdrs,
                    json=batch,
                    timeout=20,
                )
                resp.raise_for_status()
                updated += len(batch)
                print(f"[swing_core] refresh_live saved batch {i} — {len(batch)} rows")
            except Exception as e:
                print(f"[swing_core] refresh_live save error batch {i}: {e}")
                errors.append({"symbol": "batch", "error": str(e)})

    print(f"[swing_core] refresh_live complete — {updated} updated, {len(errors)} errors")
    return {"updated": updated, "errors": errors}
