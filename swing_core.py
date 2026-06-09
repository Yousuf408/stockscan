# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — swing_core.py  v3.0
#  v3.0: Auto rolling 5d snapshot in swing_watchlist table
#        First scan of day → fetch 5d OHLCV from yfinance + save to DB
#        Subsequent scans  → read hist from DB + fetch only live price/vol
#        No separate snapshot table, no manual button
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
    """Load all swing stocks for current user including stored d1-d5 history."""
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
    """Add multiple symbols at once. Returns {added, skipped, errors}."""
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
    """Format volume in Indian style: Cr / L / K."""
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

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5 — SNAPSHOT: READ / WRITE d1-d5 in swing_watchlist
# ─────────────────────────────────────────────────────────────────────────────

def _snap_is_fresh(stock: dict) -> bool:
    """Returns True if snap_updated_at is today's date."""
    updated = stock.get("snap_updated_at")
    if not updated:
        return False
    try:
        snap_date = datetime.fromisoformat(updated.replace("Z","+00:00")).date()
        return snap_date == date.today()
    except Exception:
        return False


def _extract_hist_from_db(stock: dict) -> dict | None:
    """
    Pull d1-d5 OHLCV from a swing_watchlist DB row.
    Returns dict with hist_* lists or None if incomplete.
    """
    try:
        opens, highs, lows, closes, volumes, dates = [], [], [], [], [], []
        for i in range(1, 6):
            d = stock.get(f"d{i}_date")
            o = stock.get(f"d{i}_open")
            h = stock.get(f"d{i}_high")
            l = stock.get(f"d{i}_low")
            c = stock.get(f"d{i}_close")
            v = stock.get(f"d{i}_volume")
            if not all([d, o, h, l, c, v]):
                return None
            opens.append(round(float(o), 2))
            highs.append(round(float(h), 2))
            lows.append(round(float(l), 2))
            closes.append(round(float(c), 2))
            volumes.append(int(v))
            # Format date for display
            try:
                dates.append(datetime.strptime(str(d), "%Y-%m-%d").strftime("%d %b"))
            except Exception:
                dates.append(str(d))
        return {
            "hist_opens":   opens,
            "hist_highs":   highs,
            "hist_lows":    lows,
            "hist_closes":  closes,
            "hist_volumes": volumes,
            "hist_dates":   dates,
        }
    except Exception:
        return None


def _save_hist_to_db(db_id: int, hist: dict, h: dict = None):
    """
    Save 5d OHLCV into d1-d5 columns of swing_watchlist.
    h = pre-built headers (required for thread safety — pass from main thread).
    """
    headers = h or _headers()
    row = {"snap_updated_at": datetime.utcnow().isoformat()}
    for i in range(5):
        idx = i + 1
        raw_date = hist["hist_dates"][i]
        try:
            parsed  = datetime.strptime(raw_date + f" {date.today().year}", "%d %b %Y")
            db_date = parsed.strftime("%Y-%m-%d")
        except Exception:
            db_date = None
        row[f"d{idx}_date"]   = db_date
        row[f"d{idx}_open"]   = hist["hist_opens"][i]
        row[f"d{idx}_high"]   = hist["hist_highs"][i]
        row[f"d{idx}_low"]    = hist["hist_lows"][i]
        row[f"d{idx}_close"]  = hist["hist_closes"][i]
        row[f"d{idx}_volume"] = hist["hist_volumes"][i]

    r = requests.patch(
        f"{_table_url()}?id=eq.{db_id}",
        headers=headers, json=row, timeout=10,
    )
    r.raise_for_status()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6 — YFINANCE FETCH
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_full(symbol: str) -> dict | None:
    """
    Fetch 5 historical days + today's live candle from yfinance.
    Used on first scan of the day (snapshot stale).
    period=7d covers weekends/holidays safely for 6 trading days.
    """
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="7d", interval="1d", auto_adjust=True)
        if df is None or len(df) < 6:
            return None
        df = df.dropna(subset=["Close", "Volume"])
        if len(df) < 6:
            return None

        hist = df.iloc[-6:-1]   # 5 historical completed days
        cur  = df.iloc[-1]      # today / current

        return {
            "hist_dates":   hist.index.strftime("%d %b").tolist(),
            "hist_opens":   [round(float(v), 2) for v in hist["Open"].tolist()],
            "hist_highs":   [round(float(v), 2) for v in hist["High"].tolist()],
            "hist_lows":    [round(float(v), 2) for v in hist["Low"].tolist()],
            "hist_closes":  [round(float(v), 2) for v in hist["Close"].tolist()],
            "hist_volumes": [int(v)             for v in hist["Volume"].tolist()],
            "current_price": round(float(cur["Close"]), 2),
            "current_open":  round(float(cur["Open"]),  2),
            "current_high":  round(float(cur["High"]),  2),
            "current_low":   round(float(cur["Low"]),   2),
            "current_vol":   int(cur["Volume"]),
            "current_date":  df.index[-1].strftime("%d %b"),
        }
    except Exception as e:
        print(f"[swing_core] _fetch_full {symbol}: {e}")
        return None


def _fetch_live_only(symbol: str) -> dict | None:
    """
    Fetch ONLY today's latest candle (price + volume).
    Used on subsequent scans when hist is already in DB.
    Much faster — minimal data.
    """
    try:
        df = yf.Ticker(f"{symbol}.NS").history(period="2d", interval="1d", auto_adjust=True)
        if df is None or len(df) < 1:
            return None
        cur = df.iloc[-1]
        return {
            "current_price": round(float(cur["Close"]), 2),
            "current_open":  round(float(cur["Open"]),  2),
            "current_high":  round(float(cur["High"]),  2),
            "current_low":   round(float(cur["Low"]),   2),
            "current_vol":   int(cur["Volume"]),
            "current_date":  df.index[-1].strftime("%d %b"),
        }
    except Exception as e:
        print(f"[swing_core] _fetch_live {symbol}: {e}")
        return None

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7 — PROCESS SINGLE STOCK
# ─────────────────────────────────────────────────────────────────────────────

def _process_stock(stock: dict, force_full: bool = False, h: dict = None) -> dict:
    """
    Process one stock.
    h = pre-built auth headers passed from main thread (thread-safe).
    - If snap is fresh: read hist from DB + fetch live only (fast)
    - Otherwise: fetch full 5d from yfinance + save to DB (first scan of day)
    """
    symbol = stock["symbol"]
    db_id  = stock["id"]
    fresh  = _snap_is_fresh(stock) and not force_full

    if fresh:
        # Fast path — read hist from DB
        hist = _extract_hist_from_db(stock)
        if hist:
            live = _fetch_live_only(symbol)
            if not live:
                return {"symbol": symbol, "error": "Live fetch failed"}
            source = "db"
        else:
            # DB has incomplete data — fall back to full fetch
            fresh = False

    if not fresh:
        # Full fetch from yfinance
        full = _fetch_full(symbol)
        if not full:
            return {"symbol": symbol, "error": "yfinance fetch failed"}
        hist = {k: full[k] for k in ["hist_dates","hist_opens","hist_highs",
                                      "hist_lows","hist_closes","hist_volumes"]}
        live = {k: full[k] for k in ["current_price","current_open","current_high",
                                      "current_low","current_vol","current_date"]}
        # Save hist to DB for next scan (pass headers — thread safe)
        try:
            _save_hist_to_db(db_id, hist, h=h)
        except Exception as e:
            print(f"[swing_core] save hist failed for {symbol}: {e}")
        source = "yf"

    # Calculate signals
    hist_closes  = hist["hist_closes"]
    hist_volumes = hist["hist_volumes"]
    current_price = live["current_price"]
    current_vol   = live["current_vol"]

    max_close       = max(hist_closes) if hist_closes else current_price
    clean_vols      = [v for v in hist_volumes if v and v > 0]
    median_vol      = statistics.median(clean_vols) if clean_vols else 1
    vol_ratio       = round(current_vol / median_vol, 2) if median_vol > 0 else 0
    status          = _calc_status(current_price, max_close, current_vol, hist_volumes, vol_ratio)
    vol_signal      = _vol_signal(vol_ratio)
    pct_vs_high     = round(((current_price - max_close) / max_close) * 100, 1) if max_close else 0

    return {
        "symbol":        symbol,
        "error":         None,
        "source":        source,   # "db" = fast, "yf" = full fetch
        # hist
        "hist_dates":    hist["hist_dates"],
        "hist_opens":    hist["hist_opens"],
        "hist_highs":    hist["hist_highs"],
        "hist_lows":     hist["hist_lows"],
        "hist_closes":   hist["hist_closes"],
        "hist_volumes":  hist["hist_volumes"],
        # live
        "current_date":  live["current_date"],
        "current_price": current_price,
        "current_open":  live["current_open"],
        "current_high":  live["current_high"],
        "current_low":   live["current_low"],
        "current_vol":   current_vol,
        # calculated
        "max_close":     round(max_close, 2),
        "median_vol":    int(median_vol),
        "vol_ratio":     vol_ratio,
        "vol_signal":    vol_signal,
        "pct_vs_high":   pct_vs_high,
        "status":        status,
        # meta
        "screener_url":  stock.get("screener_url", f"https://www.screener.in/company/{symbol}/"),
        "breakout_date": stock.get("breakout_date", ""),
        "notes":         stock.get("notes", ""),
        "db_id":         db_id,
    }

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8 — MAIN SCAN RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run_swing_scan(stocks: list, batch_size: int = 15, pause: float = 0.3):
    """
    Scan all stocks. Auto-detects whether to use DB cache or fetch fresh.
    - Stocks with fresh snapshot: batch_size=15, pause=0.3 (live only, fast)
    - Stocks needing full fetch:  batch_size=10, pause=0.5 (full yfinance, slower)

    IMPORTANT: auth headers captured ONCE in main thread before workers launch.
    st.session_state is not accessible inside ThreadPoolExecutor workers.
    """
    # Capture headers in main thread — workers cannot access st.session_state
    auth_h = _headers()

    # Split into fast (DB fresh) vs slow (needs full fetch)
    fresh_stocks = [s for s in stocks if _snap_is_fresh(s) and _extract_hist_from_db(s)]
    stale_stocks = [s for s in stocks if s not in fresh_stocks]

    results, errors = [], []

    def _run_batch(batch, bs, ps):
        batches = [batch[i:i+bs] for i in range(0, len(batch), bs)]
        for idx, b in enumerate(batches):
            with ThreadPoolExecutor(max_workers=bs) as ex:
                # Pass auth_h to every worker so DB saves work inside threads
                futures = {ex.submit(_process_stock, s, False, auth_h): s for s in b}
                for f in as_completed(futures):
                    d = f.result()
                    if not d.get("error"):
                        results.append(d)
                    else:
                        errors.append({"symbol": d["symbol"], "error": d["error"]})
            if idx < len(batches) - 1:
                time.sleep(ps)

    # Fast batch first (DB reads + live fetch only)
    if fresh_stocks:
        _run_batch(fresh_stocks, bs=15, ps=0.3)

    # Slow batch (full yfinance fetch + save to DB)
    if stale_stocks:
        _run_batch(stale_stocks, bs=10, ps=0.5)

    # Sort: BLASTING → READY → WATCH → rest
    priority = {"BLASTING": 0, "READY": 1, "WATCH": 2, "": 3}
    results.sort(key=lambda x: priority.get(x.get("status", ""), 3))

    return results, errors
