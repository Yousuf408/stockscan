# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — swing_core.py  v4.1
#  v4.1: Added populate_status_history() — saves last 10 days status snapshot
#        to swing_status_history table. Called by "Populate History" button.
#        Nothing else changed from v4.0.
#
#  TABLES:
#    swing_watchlist      — master symbol list (user's tracked stocks)
#    swing_hist_data      — last 5 trading days OHLCV per symbol (no NULLs ever)
#    swing_live_data      — today's live price per symbol, one row, overwritten
#    swing_status_history — last 10 days status+vol snapshot per symbol
#
#  FLOW:
#    Page load             → load_from_db()            — reads both tables, instant, no yfinance
#    Sync 5D button        → sync_5d_history()         — fetch only MISSING days from yfinance
#    Refresh Live          → refresh_live()            — fetch today only, update swing_live_data
#    Populate History btn  → populate_status_history() — calc + save last 10 days snapshots
#
#  RULES:
#    - No NULLs ever saved to DB
#    - yfinance period="7d" max for hist/live — "15d" only for populate_history
#    - uid always captured in main thread before any daemon thread
#    - swing_hist_data keeps exactly last 5 trading days per symbol
#    - swing_live_data keeps exactly 1 row per symbol (upsert)
#    - swing_status_history keeps last 10 trading days per symbol
# ══════════════════════════════════════════════════════════════════════════════

import os, requests, yfinance as yf, statistics, threading
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — CONFIG & SUPABASE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

HIST_DAYS    = 5   # number of trading days to show in chart
HISTORY_DAYS = 10  # number of days to keep in swing_status_history

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

def _fetch_all_rows(table: str, uid: str, extra_params: dict) -> list:
    """
    Paginate through Supabase 1000-row hard limit.
    Fetches all rows in batches of 1000 until exhausted.
    """
    all_rows = []
    offset   = 0
    limit    = 1000
    while True:
        r = requests.get(
            _url(table),
            headers={**_headers(), "Range-Unit": "items", "Range": f"{offset}-{offset+limit-1}"},
            params={"user_id": f"eq.{uid}", **extra_params},
            timeout=20,
        )
        r.raise_for_status()
        batch = r.json()
        all_rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return all_rows

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
    Normally starts from yesterday — today belongs in swing_live_data, not hist.
    EXCEPTION: if today is a weekday AND market has closed (after 3:30 PM IST),
    include today so same-day Sync 5D captures the completed day's data.
    """
    import pytz
    IST   = pytz.timezone("Asia/Kolkata")
    now   = datetime.now(pytz.utc).astimezone(IST)
    today = now.date()

    # Include today in hist only if: weekday + after 3:30 PM IST
    after_close = (now.hour > 15) or (now.hour == 15 and now.minute >= 30)
    market_closed_today = (today.weekday() < 5) and after_close

    days = []
    # Start from today if market closed, else from yesterday
    d = today if market_closed_today else today - timedelta(days=1)
    while len(days) < n:
        if d.weekday() < 5:
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

    hist_dates   = [datetime.strptime(r["trade_date"], "%Y-%m-%d").strftime("%d %b") for r in hist_rows]
    hist_opens   = [round(float(r["open"]),   2) for r in hist_rows]
    hist_highs   = [round(float(r["high"]),   2) for r in hist_rows]
    hist_lows    = [round(float(r["low"]),    2) for r in hist_rows]
    hist_closes  = [round(float(r["close"]),  2) for r in hist_rows]
    hist_volumes = [int(r["volume"])              for r in hist_rows]

    if live_row:
        current_price = round(float(live_row["close"]), 2)
        current_open  = round(float(live_row["open"]),  2)
        current_high  = round(float(live_row["high"]),  2)
        current_low   = round(float(live_row["low"]),   2)
        current_vol   = int(live_row["volume"])
        current_date  = datetime.strptime(live_row["trade_date"], "%Y-%m-%d").strftime("%d %b")
    else:
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
# SECTION 4 — PAGE LOAD: READ FROM DB (NO YFINANCE)
# ─────────────────────────────────────────────────────────────────────────────

def load_from_db() -> tuple:
    """
    Page load function. Reads swing_hist_data + swing_live_data.
    No yfinance. Returns (results, errors) in ~1 second.
    """
    stocks = load_swing_stocks()
    if not stocks:
        return [], []

    uid       = _get_user_id()
    meta_map  = {s["symbol"]: s for s in stocks}
    symbols   = [s["symbol"] for s in stocks]
    results, errors = [], []

    from_d = (date.today() - timedelta(days=14)).isoformat()
    try:
        hist_rows = _fetch_all_rows("swing_hist_data", uid, {
            "select":     "symbol,trade_date,open,high,low,close,volume",
            "trade_date": f"gte.{from_d}",
            "order":      "symbol.asc,trade_date.asc",
        })
        print(f"[swing_core] load_from_db — fetched {len(hist_rows)} hist rows")
    except Exception as e:
        print(f"[swing_core] load_from_db hist query error: {e}")
        return [], [{"symbol": "ALL", "error": f"DB hist read failed: {e}"}]

    hist_map = {}
    for row in hist_rows:
        sym = row["symbol"]
        if sym not in hist_map:
            hist_map[sym] = []
        hist_map[sym].append(row)
    for sym in hist_map:
        hist_map[sym] = sorted(hist_map[sym], key=lambda x: x["trade_date"])[-HIST_DAYS:]

    live_map = {}
    try:
        live_rows = _fetch_all_rows("swing_live_data", uid, {
            "select": "symbol,trade_date,open,high,low,close,volume",
        })
        for row in live_rows:
            live_map[row["symbol"]] = row
        print(f"[swing_core] load_from_db — fetched {len(live_rows)} live rows")
    except Exception as e:
        print(f"[swing_core] load_from_db live query error: {e}")

    for sym in symbols:
        hist = hist_map.get(sym, [])
        if not hist:
            continue
        live   = live_map.get(sym)
        meta   = meta_map.get(sym, {})
        result = _build_result(sym, hist, live, meta)
        if result:
            results.append(result)

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
    Saves to swing_hist_data. Deletes rows older than HIST_DAYS.
    """
    uid    = _get_user_id()
    stocks = load_swing_stocks()
    if not stocks:
        return {"synced": 0, "skipped": 0, "errors": []}

    symbols       = [s["symbol"] for s in stocks]
    required_days = _last_n_trading_days(HIST_DAYS)
    required_iso  = {d.isoformat() for d in required_days}

    from_d = (min(required_days) - timedelta(days=1)).isoformat()
    existing_map = {}
    try:
        existing_rows = _fetch_all_rows("swing_hist_data", uid, {
            "select":     "symbol,trade_date",
            "trade_date": f"gte.{from_d}",
        })
        for row in existing_rows:
            sym = row["symbol"]
            if sym not in existing_map:
                existing_map[sym] = set()
            existing_map[sym].add(row["trade_date"])
        print(f"[swing_core] sync_5d — found {len(existing_map)} symbols in DB")
    except Exception as e:
        print(f"[swing_core] sync_5d existing dates query error: {e}")

    need_fetch = []
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

    bulk    = _fetch_yf_bulk(need_fetch, period="7d")
    errors  = []
    to_save = []

    for sym in need_fetch:
        res = bulk.get(sym, {"error": "Not in bulk result"})
        if "error" in res:
            errors.append({"symbol": sym, "error": res["error"]})
            continue

        df = res["df"]

        for req_date in required_days:
            iso      = req_date.isoformat()
            matching = df[df.index.date == req_date] if not df.empty else None
            if matching is None or matching.empty:
                continue

            row_data = matching.iloc[0]
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
    """
    uid    = _get_user_id()
    stocks = load_swing_stocks()
    if not stocks:
        return {"updated": 0, "errors": []}

    symbols = [s["symbol"] for s in stocks]
    bulk    = _fetch_yf_bulk(symbols, period="2d")
    errors  = []
    to_save = []

    for sym in symbols:
        res = bulk.get(sym, {"error": "Not in bulk result"})
        if "error" in res:
            errors.append({"symbol": sym, "error": res["error"]})
            continue

        df = res["df"]
        if df.empty:
            errors.append({"symbol": sym, "error": "Empty df"})
            continue

        row_data   = df.iloc[-1]
        trade_date = df.index[-1].date().isoformat()

        o = float(row_data["Open"])
        h = float(row_data["High"])
        l = float(row_data["Low"])
        c = float(row_data["Close"])
        v = int(row_data["Volume"])

        if not all([o, h, l, c]):
            errors.append({"symbol": sym, "error": "Incomplete OHLCV from yfinance"})
            continue

        if v == 0:
            v = 1  # placeholder — live intraday volume may be 0 mid-day

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

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — POPULATE STATUS HISTORY  ← NEW in v4.1
# ─────────────────────────────────────────────────────────────────────────────

def populate_status_history() -> dict:
    """
    v4.1: Populate swing_status_history with last HISTORY_DAYS (10) trading days.

    For each symbol × each day:
      - Use 5-row context window ending on that day to calculate median_vol
      - Calculate vol_ratio, vol_signal, status using same logic as _build_result()
      - Save to swing_status_history (upsert — safe to run multiple times)
    Delete rows older than HISTORY_DAYS trading days.

    Returns: {"saved": int, "errors": list}
    """
    uid    = _get_user_id()  # capture in main thread
    stocks = load_swing_stocks()
    if not stocks:
        return {"saved": 0, "errors": []}

    symbols       = [s["symbol"] for s in stocks]
    required_days = _last_n_trading_days(HISTORY_DAYS)  # last 10 trading days

    print(f"[swing_core] populate_history — {len(symbols)} symbols, {HISTORY_DAYS} days")

    # period="15d" guarantees 10 trading days (covers 2 weekends + holidays)
    bulk    = _fetch_yf_bulk(symbols, period="15d")
    errors  = []
    to_save = []

    for sym in symbols:
        res = bulk.get(sym, {"error": "Not in bulk result"})
        if "error" in res:
            errors.append({"symbol": sym, "error": res["error"]})
            continue

        df = res["df"]
        if df.empty:
            errors.append({"symbol": sym, "error": "Empty df"})
            continue

        for req_date in required_days:
            matching = df[df.index.date == req_date] if not df.empty else None
            if matching is None or matching.empty:
                continue  # holiday or no data for this day

            row_data = matching.iloc[0]
            c = float(row_data["Close"])
            v = int(row_data["Volume"])

            if not c or not v:
                continue

            # Context: up to 5 rows ending on req_date for median/status calc
            df_before = df[df.index.date <= req_date]
            if len(df_before) < 2:
                continue

            context    = df_before.tail(5)
            ctx_closes = [float(x) for x in context["Close"].tolist()]
            ctx_vols   = [int(x)   for x in context["Volume"].tolist()]

            max_close  = max(ctx_closes) if ctx_closes else c
            clean_vols = [x for x in ctx_vols if x > 0]
            median_vol = statistics.median(clean_vols) if clean_vols else 1
            vol_ratio  = round(v / median_vol, 2) if median_vol > 0 else 0
            vs         = _vol_signal(vol_ratio)
            st         = _calc_status(c, max_close, v, ctx_vols, vol_ratio)

            # Strip ratio from vol_signal for clean DB storage e.g. "🔥 Explosive"
            vs_clean = vs.split("(")[0].strip()

            to_save.append({
                "user_id":    uid,
                "symbol":     sym,
                "trade_date": req_date.isoformat(),
                "close":      round(c, 2),
                "volume":     v,
                "vol_ratio":  vol_ratio,
                "vol_signal": vs_clean,
                "status":     st if st else "NONE",
            })

    # Upsert to swing_status_history
    saved = 0
    if to_save:
        hdrs = {**_headers(), "Prefer": "resolution=merge-duplicates"}
        for i in range(0, len(to_save), 200):
            batch = to_save[i:i+200]
            try:
                resp = requests.post(
                    _url("swing_status_history"),
                    headers=hdrs,
                    json=batch,
                    timeout=20,
                )
                resp.raise_for_status()
                saved += len(batch)
                print(f"[swing_core] populate_history saved batch {i} — {len(batch)} rows")
            except Exception as e:
                print(f"[swing_core] populate_history save error batch {i}: {e}")
                errors.append({"symbol": "batch", "error": str(e)})

    # Delete rows older than HISTORY_DAYS in background
    oldest = min(required_days).isoformat()

    def _delete_old_history():
        try:
            resp = requests.delete(
                _url("swing_status_history"),
                headers=_headers(),
                params={
                    "user_id":    f"eq.{uid}",
                    "trade_date": f"lt.{oldest}",
                },
                timeout=15,
            )
            resp.raise_for_status()
            print(f"[swing_core] populate_history deleted rows older than {oldest}")
        except Exception as e:
            print(f"[swing_core] populate_history delete error: {e}")

    threading.Thread(target=_delete_old_history, daemon=True).start()

    print(f"[swing_core] populate_history complete — {saved} rows saved, {len(errors)} errors")
    return {"saved": saved, "errors": errors}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — INTRADAY WATCH  ← NEW in v4.2
# ─────────────────────────────────────────────────────────────────────────────

def get_intraday_watch() -> list:
    """
    v4.2: Fetch last 8 trading days from swing_status_history +
          today's live signal from swing_live_data.

    Returns list of dicts per symbol:
    {
        symbol        : str
        days          : [ {date, date_label, status, vol_signal, vol_ratio}, ... ]  ← 8 days oldest→newest
        live_signal   : str   ← today's vol_signal from swing_live_data
        live_price    : float ← today's close from swing_live_data
        high_8d       : float ← max close in last 8 days from swing_status_history
        pct_vs_high   : float ← (live_price - high_8d) / high_8d * 100
        consec_weak   : int   ← max consecutive WATCH+Weak days in last 8 days
        min_vol       : int   ← min daily volume in last 8 days
    }
    Sorted: most recent Explosive/Strong first, then by consec_weak desc.
    """
    uid = _get_user_id()
    if not uid:
        return []

    # ── Query 1: last 8 trading days from swing_status_history ──
    required_days = _last_n_trading_days(8)
    from_d        = min(required_days).isoformat()

    try:
        hist_rows = _fetch_all_rows("swing_status_history", uid, {
            "select":     "symbol,trade_date,close,volume,vol_ratio,vol_signal,status",
            "trade_date": f"gte.{from_d}",
            "order":      "symbol.asc,trade_date.asc",
        })
        print(f"[swing_core] intraday_watch — fetched {len(hist_rows)} history rows")
    except Exception as e:
        print(f"[swing_core] intraday_watch history query error: {e}")
        return []

    # ── Query 2: today's live data from swing_live_data ──
    live_map = {}
    try:
        live_rows = _fetch_all_rows("swing_live_data", uid, {
            "select": "symbol,close,volume,trade_date",
        })
        for row in live_rows:
            live_map[row["symbol"]] = row
    except Exception as e:
        print(f"[swing_core] intraday_watch live query error: {e}")

    # ── Group history rows by symbol ──
    sym_map = {}
    for row in hist_rows:
        sym = row["symbol"]
        if sym not in sym_map:
            sym_map[sym] = []
        sym_map[sym].append(row)

    results = []

    for sym, rows in sym_map.items():
        # Sort oldest → newest, take last 8
        rows = sorted(rows, key=lambda x: x["trade_date"])[-8:]

        # Build day entries
        days = []
        for r in rows:
            # Clean vol_signal — strip emoji for logic, keep for display
            vs_raw   = r.get("vol_signal", "")
            vs_clean = vs_raw.split("(")[0].strip()  # "🔴 Weak" etc

            days.append({
                "date":       r["trade_date"],
                "date_label": datetime.strptime(r["trade_date"], "%Y-%m-%d").strftime("%d%b"),
                "status":     r.get("status", "NONE"),
                "vol_signal": vs_clean,
                "vol_ratio":  float(r.get("vol_ratio", 0)),
                "close":      float(r.get("close", 0)),
                "volume":     int(r.get("volume", 0)),
            })

        if not days:
            continue

        # ── Calculate metrics ──
        # 8-day high close
        high_8d = max(d["close"] for d in days)

        # Live price + signal
        live_row    = live_map.get(sym)
        live_price  = float(live_row["close"])  if live_row else days[-1]["close"]
        live_vol    = int(live_row["volume"])    if live_row else 0
        live_signal    = ""
        live_vol_ratio = 0.0
        live_status    = "WATCH"
        if live_row and live_vol:
            hist_vols    = [d["volume"] for d in days if d["volume"] > 0]
            median_vol   = statistics.median(hist_vols) if hist_vols else 1
            live_ratio   = round(live_vol / median_vol, 2)
            live_vol_ratio = live_ratio
            vs           = _vol_signal(live_ratio)
            live_signal  = vs.split("(")[0].strip()
            hist_closes  = [d["close"] for d in days]
            max_close    = max(hist_closes) if hist_closes else live_price
            max_hist_vol = max([d["volume"] for d in days if d["volume"] > 0], default=1)
            if live_price > max_close and live_vol > max_hist_vol and live_ratio >= 2.0:
                live_status = "BLASTING"
            elif live_price >= max_close * 0.995 and live_ratio >= 1.5:
                live_status = "READY"
            elif live_price >= max_close * 0.92:
                live_status = "WATCH"
            else:
                live_status = "NONE"
        else:
            live_signal    = days[-1]["vol_signal"]
            live_vol_ratio = days[-1]["vol_ratio"]
            live_status    = days[-1]["status"]

        # % vs 8-day high
        pct_vs_high = round(((live_price - high_8d) / high_8d) * 100, 1) if high_8d else 0

        # Max consecutive WATCH+Weak streak
        consec_weak = 0
        current_streak = 0
        for d in days:
            if d["status"] == "WATCH" and "Weak" in d["vol_signal"]:
                current_streak += 1
                consec_weak = max(consec_weak, current_streak)
            else:
                current_streak = 0

        # Min volume in last 8 days
        vols    = [d["volume"] for d in days if d["volume"] > 0]
        min_vol = min(vols) if vols else 0

        results.append({
            "symbol":        sym,
            "days":          days,
            "live_signal":   live_signal,
            "live_status":   live_status,
            "live_vol_ratio": live_vol_ratio,
            "live_price":    live_price,
            "high_8d":       high_8d,
            "pct_vs_high":   pct_vs_high,
            "consec_weak":   consec_weak,
            "min_vol":       min_vol,
        })

    # ── Sort: recent Explosive/Strong first, then consec_weak desc ──
    def _sort_key(r):
        last_sig   = r["days"][-1]["vol_signal"] if r["days"] else ""
        sig_rank   = 0 if "Explosive" in last_sig else (1 if "Strong" in last_sig else 2)
        return (sig_rank, -r["consec_weak"])

    results.sort(key=_sort_key)

    print(f"[swing_core] intraday_watch — {len(results)} symbols processed")
    return results