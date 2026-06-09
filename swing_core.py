# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — swing_core.py  v2.1 (restored)
#  Simple yfinance only — no DB snapshot, no AngelOne
#  period=7d for fast fetch, median vol, 4 signals
# ══════════════════════════════════════════════════════════════════════════════

import os, requests, yfinance as yf, statistics, time
from datetime import date, datetime
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

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2 — SWING STOCK CRUD
# ─────────────────────────────────────────────────────────────────────────────

def load_swing_stocks() -> list:
    """Load all swing stocks for current user."""
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
    """Add a new stock to swing watchlist."""
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
    """Update breakout_date, screener_url, notes, or symbol."""
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
    """Delete a stock from swing watchlist."""
    r = requests.delete(f"{_table_url()}?id=eq.{db_id}", headers=_headers(), timeout=10)
    r.raise_for_status()


def bulk_add_swing_stocks(symbols: list) -> dict:
    """Add multiple symbols at once."""
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
    """Format volume Indian style: Cr / L / K."""
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
    """
    BLASTING : price > max_close AND current_vol > max_hist_vol AND ratio >= 2
    READY    : price >= max_close * 0.995 AND ratio >= 1.5
    WATCH    : price >= max_close * 0.92
    """
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


def _save_d6(db_id: int, live: dict):
    """
    Save today's live candle into d6 columns of swing_watchlist.
    Called after every scan and every refresh.
    Uses same _headers() as all other CRUD operations.
    """
    try:
        row = {
            "d6_date":   date.today().isoformat(),
            "d6_open":   live.get("current_open"),
            "d6_high":   live.get("current_high"),
            "d6_low":    live.get("current_low"),
            "d6_close":  live.get("current_price"),
            "d6_volume": live.get("current_vol"),
        }
        r = requests.patch(
            f"{_table_url()}?id=eq.{db_id}",
            headers=_headers(), json=row, timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[swing_core] d6 save failed id={db_id}: {e}")


def _save_d1_to_d5(db_id: int, result: dict):
    """
    Save 5 historical candles into d1-d5 columns of swing_watchlist.
    Called after every scan — rolls forward automatically each day
    since yfinance always returns the latest 5 completed trading days.
    Same _headers() method that works for D6.
    """
    try:
        hist_dates   = result.get("hist_dates",   [])
        hist_opens   = result.get("hist_opens",   [])
        hist_highs   = result.get("hist_highs",   [])
        hist_lows    = result.get("hist_lows",    [])
        hist_closes  = result.get("hist_closes",  [])
        hist_volumes = result.get("hist_volumes", [])

        if len(hist_closes) < 5:
            return

        row = {}
        for i in range(5):
            idx = i + 1
            raw_date = hist_dates[i] if i < len(hist_dates) else ""
            try:
                parsed  = datetime.strptime(raw_date + f" {date.today().year}", "%d %b %Y")
                db_date = parsed.strftime("%Y-%m-%d")
            except Exception:
                db_date = date.today().isoformat()
            row[f"d{idx}_date"]   = db_date
            row[f"d{idx}_open"]   = hist_opens[i]
            row[f"d{idx}_high"]   = hist_highs[i]
            row[f"d{idx}_low"]    = hist_lows[i]
            row[f"d{idx}_close"]  = hist_closes[i]
            row[f"d{idx}_volume"] = hist_volumes[i]

        r = requests.patch(
            f"{_table_url()}?id=eq.{db_id}",
            headers=_headers(), json=row, timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"[swing_core] d1-d5 save failed id={db_id}: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — YFINANCE FETCH
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_single(symbol: str) -> dict:
    """
    Fetch 5 historical days + today from yfinance.
    period=7d covers weekends/holidays safely for 6 trading days.
    """
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="7d", interval="1d", auto_adjust=True)
        if df is None or len(df) < 6:
            return {"symbol": symbol, "error": "Not enough data"}
        df = df.dropna(subset=["Close", "Volume"])
        if len(df) < 6:
            return {"symbol": symbol, "error": "Not enough clean data"}

        hist = df.iloc[-6:-1]   # 5 historical completed days
        cur  = df.iloc[-1]      # today / current

        hist_closes  = hist["Close"].tolist()
        hist_volumes = hist["Volume"].tolist()
        hist_opens   = hist["Open"].tolist()
        hist_highs   = hist["High"].tolist()
        hist_lows    = hist["Low"].tolist()
        hist_dates   = hist.index.strftime("%d %b").tolist()

        current_price = round(float(cur["Close"]), 2)
        current_open  = round(float(cur["Open"]),  2)
        current_high  = round(float(cur["High"]),  2)
        current_low   = round(float(cur["Low"]),   2)
        current_vol   = int(cur["Volume"])
        current_date  = df.index[-1].strftime("%d %b")

        max_close       = max(hist_closes)
        clean_vols      = [v for v in hist_volumes if v and v > 0]
        median_vol      = statistics.median(clean_vols) if clean_vols else 1
        vol_ratio       = round(current_vol / median_vol, 2) if median_vol > 0 else 0
        status          = _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio)
        vol_signal      = _vol_signal(vol_ratio)
        pct_vs_high     = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

        return {
            "symbol":        symbol,
            "error":         None,
            "hist_dates":    hist_dates,
            "hist_opens":    [round(float(v), 2) for v in hist_opens],
            "hist_highs":    [round(float(v), 2) for v in hist_highs],
            "hist_lows":     [round(float(v), 2) for v in hist_lows],
            "hist_closes":   [round(float(v), 2) for v in hist_closes],
            "hist_volumes":  [int(v)             for v in hist_volumes],
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
        }

    except Exception as e:
        return {"symbol": symbol, "error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — MARKET HOURS + LIVE REFRESH
# ─────────────────────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    """Returns True if current IST time is within market hours 9:15–15:30 Mon–Fri."""
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


def _fetch_live_single(symbol: str) -> dict:
    """
    Fetch ONLY today's live price + volume via yfinance period=2d.
    Lightweight — used for refresh during market hours.
    """
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="2d", interval="1d", auto_adjust=True)
        if df is None or len(df) < 1:
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


def refresh_live_data(results: list, batch_size: int = 15, pause: float = 0.3) -> list:
    """
    Refresh only today's price + volume for all stocks in current results.
    Keeps 5d historical data (hist_*) and all other fields unchanged.
    Recalculates signals with new live data.
    Returns updated results list.
    """
    if not results:
        return results

    symbols    = [r["symbol"] for r in results]
    result_map = {r["symbol"]: r for r in results}
    batches    = [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]
    updated    = {}

    for idx, batch in enumerate(batches):
        with ThreadPoolExecutor(max_workers=batch_size) as ex:
            futures = {ex.submit(_fetch_live_single, sym): sym for sym in batch}
            for f in as_completed(futures):
                live = f.result()
                sym  = live["symbol"]
                if live.get("error"):
                    continue  # keep existing data if fetch fails

                old = result_map.get(sym, {})

                # Recalculate signals with new live data
                hist_closes  = old.get("hist_closes", [])
                hist_volumes = old.get("hist_volumes", [])
                current_price = live["current_price"]
                current_vol   = live["current_vol"]
                max_close     = old.get("max_close", current_price)
                clean_vols    = [v for v in hist_volumes if v and v > 0]
                median_vol    = statistics.median(clean_vols) if clean_vols else 1
                vol_ratio     = round(current_vol / median_vol, 2) if median_vol > 0 else 0
                status        = _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio)
                vol_signal    = _vol_signal(vol_ratio)
                pct_vs_high   = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

                # Merge — update live fields only, keep hist unchanged
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
                # Save today's candle to d6
                db_id = old.get("db_id")
                if db_id:
                    _save_d6(db_id, live)

        if idx < len(batches) - 1:
            time.sleep(pause)

    # Return results with updates applied, preserving original order
    final = []
    for r in results:
        sym = r["symbol"]
        final.append(updated.get(sym, r))

    priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
    final.sort(key=lambda x: priority.get(x.get("status", ""), 3))
    return final

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — MAIN SCAN RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_swing_scan(stocks: list, batch_size: int = 10, pause: float = 0.5):
    """
    Scan all stocks via yfinance in parallel batches.
    Returns (results, errors).
    """
    stock_meta      = {s["symbol"]: s for s in stocks}
    results, errors = [], []
    symbols         = [s["symbol"] for s in stocks]
    batches         = [symbols[i:i+batch_size] for i in range(0, len(symbols), batch_size)]

    for idx, batch in enumerate(batches):
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
                    results.append(d)
                    # Save d1-d5 hist + d6 today to DB
                    if m.get("id"):
                        _save_d1_to_d5(m["id"], d)
                        _save_d6(m["id"], d)
                else:
                    errors.append({"symbol": sym, "error": d["error"]})
        if idx < len(batches) - 1:
            time.sleep(pause)

    priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
    results.sort(key=lambda x: priority.get(x.get("status", ""), 3))
    return results, errors
