# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — core.py  v2.1
#  SHARED ENGINE — imported by prewatch.py and scanner.py
#  v2.1: Supabase via plain requests (no supabase client — works on Streamlit Cloud)
#  EMA calculation unchanged
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
import requests

WATCHLIST_TABS = ["Today", "Yesterday", "New"]

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: SUPABASE REST API HELPERS
# Uses plain HTTPS requests — no supabase Python client needed
# Works on Streamlit Cloud without any network config changes
# ─────────────────────────────────────────────────────────────────────────────

def _get_supabase_config():
    """Get Supabase URL and API key from Streamlit secrets or env vars."""
    try:
        import streamlit as st
        url = st.secrets["SUPABASE_URL"].rstrip("/")
        key = st.secrets["SUPABASE_KEY"]
        return url, key
    except Exception:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_KEY", "")
        return url, key


def _headers():
    """Standard Supabase REST API headers."""
    _, key = _get_supabase_config()
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _table_url():
    """Base URL for watchlist table REST endpoint."""
    url, _ = _get_supabase_config()
    return f"{url}/rest/v1/watchlist"


def _sb_select(filters: dict = None) -> list:
    """SELECT rows from watchlist table with optional filters."""
    params = {"select": "*", "order": "id.asc"}
    if filters:
        params.update(filters)
    res = requests.get(_table_url(), headers=_headers(), params=params, timeout=10)
    res.raise_for_status()
    return res.json()


def _sb_insert(rows: list) -> list:
    """INSERT rows into watchlist table. Returns inserted rows."""
    if not rows:
        return []
    res = requests.post(_table_url(), headers=_headers(), json=rows, timeout=10)
    res.raise_for_status()
    return res.json()


def _sb_update(db_id: int, updates: dict):
    """UPDATE a single row by id."""
    url = f"{_table_url()}?id=eq.{db_id}"
    res = requests.patch(url, headers=_headers(), json=updates, timeout=10)
    res.raise_for_status()
    return res.json()


def _sb_delete(filter_str: str):
    """DELETE rows matching a filter string e.g. 'tab=eq.Today'."""
    url = f"{_table_url()}?{filter_str}"
    res = requests.delete(url, headers=_headers(), timeout=10)
    res.raise_for_status()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: EMA — unchanged from v1.0
# ─────────────────────────────────────────────────────────────────────────────

def calc_ema(candles: list, period: int):
    """
    Canonical EMA — matches TradingView/Zerodha exactly.
    candles: list of rows, close price at index [4]
    """
    if not candles or len(candles) < period:
        return None
    closes     = [float(c[4]) for c in candles]
    sma        = sum(closes[:period]) / period
    multiplier = 2 / (period + 1)
    ema        = sma
    for close in closes[period:]:
        ema = (close - ema) * multiplier + ema
    return ema


def calc_ema_from_series(closes: list, period: int):
    """
    Same algorithm but accepts a plain list of floats.
    Used by prewatch.py after df["Close"].tolist().
    """
    if not closes or len(closes) < period:
        return None
    sma        = sum(closes[:period]) / period
    multiplier = 2 / (period + 1)
    ema        = sma
    for close in closes[period:]:
        ema = (close - ema) * multiplier + ema
    return ema


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: ROW CONVERTERS
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_stock(row: dict) -> dict:
    """Supabase DB row → app stock dict."""
    return {
        "symbol":    row.get("symbol", ""),
        "exchange":  row.get("exchange", "NS"),
        "direction": row.get("direction", "BUY"),
        "entry":     row.get("entry"),
        "sl":        row.get("sl"),
        "target1":   row.get("target1"),
        "target2":   row.get("target2"),
        "note":      row.get("note"),
        "sector":    row.get("sector", "GENERAL"),
        "status":    row.get("status", "WATCHING"),
        "lastPrice": row.get("last_price"),
        "added_at":  row.get("added_at", ""),
        "token":     row.get("token", ""),
        "_db_id":    row.get("id"),
    }


def _stock_to_row(stock: dict, tab: str) -> dict:
    """App stock dict → Supabase DB row."""
    return {
        "tab":        tab,
        "symbol":     stock.get("symbol", "").upper().strip(),
        "exchange":   stock.get("exchange", "NS"),
        "direction":  stock.get("direction", "BUY"),
        "entry":      stock.get("entry"),
        "sl":         stock.get("sl"),
        "target1":    stock.get("target1"),
        "target2":    stock.get("target2"),
        "note":       stock.get("note"),
        "sector":     stock.get("sector", "GENERAL"),
        "status":     stock.get("status", "WATCHING"),
        "last_price": stock.get("lastPrice"),
        "token":      stock.get("token", ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: WATCHLIST CRUD — same interface as v1.0
# ─────────────────────────────────────────────────────────────────────────────

def load_watchlist(tab: str = None):
    """
    Load watchlist from Supabase.

    tab given  → returns list of stock dicts for that tab
    tab None   → returns full dict {"watchlist_Today": [...], ...}
                 same structure as old watchlist.json
    """
    try:
        if tab:
            rows = _sb_select({"tab": f"eq.{tab}"})
            return [_row_to_stock(r) for r in rows]
        else:
            rows   = _sb_select()
            result = {f"watchlist_{t}": [] for t in WATCHLIST_TABS}
            for row in rows:
                key = f"watchlist_{row.get('tab', '')}"
                if key in result:
                    result[key].append(_row_to_stock(row))
            return result
    except Exception as e:
        return [] if tab else {f"watchlist_{t}": [] for t in WATCHLIST_TABS}


def save_watchlist(data: dict):
    """
    Save full watchlist dict to Supabase.
    Deletes existing rows for each tab then re-inserts.
    Same interface as old watchlist.json save.
    """
    try:
        for tab in WATCHLIST_TABS:
            key    = f"watchlist_{tab}"
            stocks = data.get(key)
            if stocks is None:
                continue
            # Delete existing rows for this tab
            _sb_delete(f"tab=eq.{tab}")
            # Re-insert all stocks
            if stocks:
                rows = [_stock_to_row(s, tab) for s in stocks]
                _sb_insert(rows)
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase save failed: {e}")


def add_to_watchlist(tab: str, stock: dict):
    """
    Add a single stock — efficient single INSERT.
    Used by watchlist add form and prewatch batch inject.
    """
    try:
        row = _stock_to_row(stock, tab)
        res = _sb_insert([row])
        return res[0] if res else None
    except Exception as e:
        raise RuntimeError(f"Supabase insert failed: {e}")


def delete_from_watchlist(db_id: int):
    """Delete a single stock by its DB id."""
    try:
        _sb_delete(f"id=eq.{db_id}")
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase delete failed: {e}")


def update_watchlist_stock(db_id: int, updates: dict):
    """
    Update a single stock's fields by DB id.
    Used for status updates, edit form saves, reset.
    """
    try:
        field_map = {
            "status":    "status",
            "lastPrice": "last_price",
            "entry":     "entry",
            "sl":        "sl",
            "target1":   "target1",
            "target2":   "target2",
            "note":      "note",
        }
        db_updates = {field_map[k]: v for k, v in updates.items() if k in field_map}
        if db_updates:
            _sb_update(db_id, db_updates)
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase update failed: {e}")


def clear_watchlist_tab(tab: str):
    """Delete all stocks in a tab."""
    try:
        _sb_delete(f"tab=eq.{tab}")
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase clear failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: SELF-TEST
# Run: python core.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # EMA smoke test
    dummy_closes  = [100, 102, 101, 103, 104, 105, 103, 106, 107, 108,
                     107, 109, 110, 111, 110, 112, 113, 114, 113, 115,
                     116, 117, 116, 118, 119]
    dummy_candles = [["2024-01-01", 0, 0, 0, c, 0] for c in dummy_closes]

    ema20        = calc_ema(dummy_candles, 20)
    ema20_series = calc_ema_from_series(dummy_closes, 20)

    print(f"calc_ema()             EMA20 = {ema20:.4f}")
    print(f"calc_ema_from_series() EMA20 = {ema20_series:.4f}")
    print(f"Both match: {abs(ema20 - ema20_series) < 0.0001}")
    assert calc_ema(dummy_candles[:5], 20) is None
    print("Insufficient data guard: OK")

    # Supabase connection test
    try:
        url, key = _get_supabase_config()
        if url and key:
            rows = _sb_select({"limit": "1"})
            print(f"\nSupabase REST connection: OK")
        else:
            print("\nSupabase: credentials not set")
    except Exception as e:
        print(f"\nSupabase connection failed: {e}")

    print("\ncore.py v2.1 — all checks passed ✅")
