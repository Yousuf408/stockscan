# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — swing_core.py  v4.1
#  Fixed: load_price_data_from_db added, all DB operations correct
# ══════════════════════════════════════════════════════════════════════════════

import os, requests, yfinance as yf, statistics, time
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
        return os.environ.get("SUPABASE_URL","").rstrip("/"), os.environ.get("SUPABASE_KEY","")

def _get_user_id():
    try:
        import streamlit as st
        return st.session_state.get("user_id","")
    except Exception:
        return ""

def _get_access_token():
    try:
        import streamlit as st
        return st.session_state.get("access_token","")
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
        rows = r.json()
        for row in rows:
            row["symbol"] = row["symbol"].lstrip("$").strip().upper()
        return rows
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
    if v is None: return "—"
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
# SECTION 5 — TRADING DAYS HELPER
# ─────────────────────────────────────────────────────────────────────────────

def get_last_n_trading_days(ref_date: date, n: int = 10) -> list:
    days = []
    d    = ref_date - timedelta(days=1)
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — PRICE DATA DB OPERATIONS
# ─────────────────────────────────────────────────────────────────────────────

def load_price_data_from_db(symbols: list, from_date: date, to_date: date) -> dict:
    """
    Load OHLCV from swing_price_data for date range.
    Uses list of tuples for params to allow duplicate keys (gte + lte).
    Returns {symbol: [rows sorted oldest first]}
    """
    try:
        uid = _get_user_id()
        if not uid or not symbols:
            return {}
        params = [
            ("select",     "symbol,trade_date,open,high,low,close,volume"),
            ("user_id",    f"eq.{uid}"),
            ("trade_date", f"gte.{from_date.isoformat()}"),
            ("trade_date", f"lte.{to_date.isoformat()}"),
            ("order",      "symbol.asc,trade_date.asc"),
        ]
        r = requests.get(
            _price_table_url(),
            headers=_headers(),
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        rows   = r.json()
        result = {}
        for row in rows:
            sym = row["symbol"]
            if sym not in result:
                result[sym] = []
            result[sym].append(row)
        return result
    except Exception as e:
        print(f"[swing_core] load_price_data error: {e}")
        return {}


def save_price_data_to_db(results: list):
    """
    Save OHLCV to swing_price_data. Saves hist (ISO dates) + today.
    Uses upsert. Called after threads complete — never inside workers.
    """
    uid = _get_user_id()
    if not uid:
        return
    hdrs = {**_headers(), "Prefer": "resolution=merge-duplicates"}
    rows = []

    for r in results:
        if r.get("error"):
            continue
        sym = r["symbol"]

        # Historical days — use all 10 ISO dates for DB save
        hist_iso_dates = r.get("all_hist_iso_dates") or r.get("hist_iso_dates", [])
        all_opens   = r.get("all_hist_opens",   r.get("hist_opens",   []))
        all_highs   = r.get("all_hist_highs",   r.get("hist_highs",   []))
        all_lows    = r.get("all_hist_lows",    r.get("hist_lows",    []))
        all_closes  = r.get("all_hist_closes",  r.get("hist_closes",  []))
        all_volumes = r.get("all_hist_volumes", r.get("hist_volumes", []))

        for i, iso_date in enumerate(hist_iso_dates):
            if i >= len(all_closes):
                break
            rows.append({
                "user_id":    uid, "symbol": sym,
                "trade_date": iso_date,
                "open":       all_opens[i]   if i < len(all_opens)   else None,
                "high":       all_highs[i]   if i < len(all_highs)   else None,
                "low":        all_lows[i]    if i < len(all_lows)    else None,
                "close":      all_closes[i],
                "volume":     all_volumes[i] if i < len(all_volumes) else None,
            })

        # Today's candle
        rows.append({
            "user_id":    uid, "symbol": sym,
            "trade_date": date.today().isoformat(),
            "open":   r.get("current_open"),
            "high":   r.get("current_high"),
            "low":    r.get("current_low"),
            "close":  r.get("current_price"),
            "volume": r.get("current_vol"),
        })

    if not rows:
        return

    # Parallel upsert in batches of 200
    url     = _price_table_url()
    batches = [rows[i:i+200] for i in range(0, len(rows), 200)]

    def _upload(batch):
        try:
            requests.post(url, headers=hdrs, json=batch, timeout=20).raise_for_status()
        except Exception as e:
            print(f"[swing_core] save batch error: {e}")

    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(_upload, batches))


def check_db_has_data(symbols: list, trading_days: list) -> bool:
    """Check if today's data exists for 80%+ of symbols."""
    try:
        uid = _get_user_id()
        if not uid or not symbols:
            return False
        today = date.today().isoformat()
        hdrs  = {**_headers(), "Prefer": "count=exact"}
        r = requests.get(
            _price_table_url(),
            headers=hdrs,
            params={"user_id": f"eq.{uid}", "trade_date": f"eq.{today}", "limit": "1"},
            timeout=10,
        )
        r.raise_for_status()
        cr = r.headers.get("Content-Range", "")
        count = int(cr.split("/")[-1]) if "/" in cr else len(r.json())
        return count >= len(symbols) * 0.8
    except Exception:
        return False

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — MARKET HOURS
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
# SECTION 8 — YFINANCE FETCH
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_single(symbol: str) -> dict:
    symbol = symbol.lstrip("$").strip().upper()
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="15d", interval="1d", auto_adjust=True)
        if df is None or len(df) < 2:
            return {"symbol": symbol, "error": "Not enough data"}
        df = df.dropna(subset=["Close", "Volume"])
        if len(df) < 2:
            return {"symbol": symbol, "error": "Not enough clean data"}

        hist = df.iloc[-11:-1] if len(df) >= 11 else df.iloc[:-1]
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

        max_close   = max(hist_closes) if hist_closes else current_price
        clean_vols  = [v for v in hist_volumes if v and v > 0]
        median_vol  = statistics.median(clean_vols) if clean_vols else 1
        vol_ratio   = round(current_vol / median_vol, 2) if median_vol > 0 else 0
        status      = _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio)
        vol_signal  = _vol_signal(vol_ratio)
        pct_vs_high = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

        # Use last 5 only for display — signals already calculated above on all 10
        disp_slice = slice(-5, None)

        return {
            "symbol": symbol, "error": None,
            "hist_dates":     hist_dates[disp_slice],
            "hist_iso_dates": hist_iso[disp_slice],
            "hist_opens":     [round(float(v), 2) for v in hist_opens[disp_slice]],
            "hist_highs":     [round(float(v), 2) for v in hist_highs[disp_slice]],
            "hist_lows":      [round(float(v), 2) for v in hist_lows[disp_slice]],
            "hist_closes":    [round(float(v), 2) for v in hist_closes[disp_slice]],
            "hist_volumes":   [int(v)             for v in hist_volumes[disp_slice]],
            # Keep full 10 for signal reference
            "all_hist_iso_dates": hist_iso,
            "all_hist_closes":    [round(float(v), 2) for v in hist_closes],
            "all_hist_volumes":   [int(v)             for v in hist_volumes],
            "current_date":   current_date,  "current_price": current_price,
            "current_open":   current_open,  "current_high":  current_high,
            "current_low":    current_low,   "current_vol":   current_vol,
            "max_close":  round(max_close, 2), "median_vol": int(median_vol),
            "vol_ratio":  vol_ratio, "vol_signal": vol_signal,
            "pct_vs_high": pct_vs_high, "status": status,
        }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}


def _fetch_live_single(symbol: str) -> dict:
    symbol = symbol.lstrip("$").strip().upper()
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="2d", interval="1d", auto_adjust=True)
        if df is None or len(df) < 1:
            return {"symbol": symbol, "error": "No data"}
        cur = df.iloc[-1]
        return {
            "symbol": symbol, "error": None,
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
# SECTION 9 — BUILD RESULT FROM DB + LIVE
# ─────────────────────────────────────────────────────────────────────────────

def _build_result_from_db(symbol: str, db_rows: list, live: dict, meta: dict) -> dict:
    """
    All 10 rows for signal calculation.
    Last 5 rows for candle display only.
    """
    all_closes  = [round(float(r["close"]),  2) for r in db_rows]
    all_volumes = [int(r["volume"])              for r in db_rows]

    disp_rows    = db_rows[-5:]
    hist_dates   = [datetime.strptime(r["trade_date"], "%Y-%m-%d").strftime("%d %b") for r in disp_rows]
    hist_opens   = [round(float(r["open"]),   2) for r in disp_rows]
    hist_highs   = [round(float(r["high"]),   2) for r in disp_rows]
    hist_lows    = [round(float(r["low"]),    2) for r in disp_rows]
    hist_closes  = [round(float(r["close"]),  2) for r in disp_rows]
    hist_volumes = [int(r["volume"])              for r in disp_rows]

    current_price = live.get("current_price", 0)
    current_vol   = live.get("current_vol",   0)
    max_close     = max(all_closes)  if all_closes  else current_price
    clean_vols    = [v for v in all_volumes if v and v > 0]
    median_vol    = statistics.median(clean_vols) if clean_vols else 1
    vol_ratio     = round(current_vol / median_vol, 2) if median_vol > 0 else 0
    status        = _calc_status(current_price, max_close, current_vol, all_volumes, vol_ratio)
    vol_signal    = _vol_signal(vol_ratio)
    pct_vs_high   = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

    return {
        "symbol": symbol, "error": None,
        "hist_dates":    hist_dates,  "hist_opens":   hist_opens,
        "hist_highs":    hist_highs,  "hist_lows":    hist_lows,
        "hist_closes":   hist_closes, "hist_volumes": hist_volumes,
        "hist_iso_dates": [],  # not needed for DB path
        "current_date":  live.get("current_date", ""),
        "current_price": current_price,
        "current_open":  live.get("current_open",  0),
        "current_high":  live.get("current_high",  0),
        "current_low":   live.get("current_low",   0),
        "current_vol":   current_vol,
        "max_close":   round(max_close, 2), "median_vol":  int(median_vol),
        "vol_ratio":   vol_ratio,           "vol_signal":  vol_signal,
        "pct_vs_high": pct_vs_high,         "status":      status,
        "screener_url":  meta.get("screener_url", f"https://www.screener.in/company/{symbol}/"),
        "breakout_date": meta.get("breakout_date", ""),
        "notes":         meta.get("notes", ""),
        "db_id":         meta.get("id"),
        "source":        "db",
    }

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10 — MAIN SCAN RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_swing_scan(stocks: list, selected_date: date = None, batch_size: int = 25) -> tuple:
    if selected_date is None:
        selected_date = date.today()

    is_today     = (selected_date == date.today())
    trading_days = get_last_n_trading_days(selected_date, n=10)
    stock_meta   = {s["symbol"]: s for s in stocks}
    symbols      = [s["symbol"] for s in stocks]
    results, errors = [], []

    from_d  = trading_days[0]
    to_d    = trading_days[-1]
    db_data = load_price_data_from_db(symbols, from_d, to_d)
    has_db  = check_db_has_data(symbols, trading_days)

    if has_db and is_today:
        # FAST PATH — DB hist + live fetch only
        live_results = {}
        batches = [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]
        for batch in batches:
            with ThreadPoolExecutor(max_workers=batch_size) as ex:
                futures = {ex.submit(_fetch_live_single, sym): sym for sym in batch}
                for f in as_completed(futures):
                    d = f.result()
                    if not d.get("error"):
                        live_results[d["symbol"]] = d

        for sym in symbols:
            meta    = stock_meta.get(sym, {})
            db_rows = db_data.get(sym, [])
            live    = live_results.get(sym, {})
            if db_rows and live:
                results.append(_build_result_from_db(sym, db_rows, live, meta))
            else:
                errors.append({"symbol": sym, "error": "Missing DB or live data"})

        # Save today's live to DB outside threads
        save_price_data_to_db(results)

    elif not is_today and db_data:
        # PAST DATE PATH — all from DB
        for sym in symbols:
            meta    = stock_meta.get(sym, {})
            db_rows = db_data.get(sym, [])
            if not db_rows:
                errors.append({"symbol": sym, "error": "No data for selected date"})
                continue
            last_row = db_rows[-1]
            live = {
                "current_price": round(float(last_row["close"]), 2),
                "current_open":  round(float(last_row["open"]),  2),
                "current_high":  round(float(last_row["high"]),  2),
                "current_low":   round(float(last_row["low"]),   2),
                "current_vol":   int(last_row["volume"]),
                "current_date":  datetime.strptime(last_row["trade_date"], "%Y-%m-%d").strftime("%d %b"),
            }
            hist_rows = db_rows[:-1]
            if hist_rows:
                results.append(_build_result_from_db(sym, hist_rows, live, meta))
            else:
                errors.append({"symbol": sym, "error": "Insufficient history"})

    else:
        # FULL FETCH — no DB data
        batches = [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]
        for batch in batches:
            with ThreadPoolExecutor(max_workers=batch_size) as ex:
                futures = {ex.submit(_fetch_single, sym): sym for sym in batch}
                for f in as_completed(futures):
                    d   = f.result()
                    sym = d["symbol"]
                    if not d.get("error"):
                        m = stock_meta.get(sym, {})
                        d["screener_url"]  = m.get("screener_url", f"https://www.screener.in/company/{sym}/")
                        d["breakout_date"] = m.get("breakout_date", "")
                        d["notes"]         = m.get("notes", "")
                        d["db_id"]         = m.get("id")
                        d["source"]        = "yf"
                        results.append(d)
                    else:
                        errors.append({"symbol": sym, "error": d["error"]})

        # Save to DB after threads
        save_price_data_to_db(results)

    priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
    results.sort(key=lambda x: priority.get(x.get("status", ""), 3))
    return results, errors


def refresh_live_data(results: list, batch_size: int = 25) -> list:
    if not results:
        return results

    symbols    = [r["symbol"] for r in results]
    result_map = {r["symbol"]: r for r in results}
    live_data  = {}

    batches = [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]
    for batch in batches:
        with ThreadPoolExecutor(max_workers=batch_size) as ex:
            futures = {ex.submit(_fetch_live_single, sym): sym for sym in batch}
            for f in as_completed(futures):
                live = f.result()
                if not live.get("error"):
                    live_data[live["symbol"]] = live

    updated = []
    for r in results:
        sym  = r["symbol"]
        live = live_data.get(sym)
        if not live:
            updated.append(r)
            continue
        hist_closes  = r.get("hist_closes",  [])
        hist_volumes = r.get("hist_volumes", [])
        current_price = live["current_price"]
        current_vol   = live["current_vol"]
        max_close     = r.get("max_close", current_price)
        clean_vols    = [v for v in hist_volumes if v and v > 0]
        median_vol    = statistics.median(clean_vols) if clean_vols else 1
        vol_ratio     = round(current_vol / median_vol, 2) if median_vol > 0 else 0
        status        = _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio)
        vol_signal    = _vol_signal(vol_ratio)
        pct_vs_high   = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0
        updated.append({
            **r,
            "current_price": current_price, "current_open": live["current_open"],
            "current_high":  live["current_high"], "current_low": live["current_low"],
            "current_vol":   current_vol,   "current_date": live["current_date"],
            "vol_ratio": vol_ratio, "vol_signal": vol_signal,
            "pct_vs_high": pct_vs_high, "status": status, "median_vol": int(median_vol),
        })

    # Save today's updated data to DB
    save_price_data_to_db(updated)

    priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
    updated.sort(key=lambda x: priority.get(x.get("status", ""), 3))
    return updated
