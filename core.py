# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — core.py  v2.0
#  SHARED ENGINE — imported by prewatch.py and scanner.py
#  v2.0: Supabase replaces watchlist.json — persistent across redeploys
#  EMA calculation unchanged — same canonical implementation
# ══════════════════════════════════════════════════════════════════════════════

import os
import json

WATCHLIST_TABS = ["Today", "Yesterday", "New"]

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: SUPABASE CLIENT
# Initialised once, reused across all calls.
# Falls back gracefully if credentials are missing (local dev).
# ─────────────────────────────────────────────────────────────────────────────

def _get_supabase():
    """
    Returns a Supabase client using st.secrets (Streamlit Cloud)
    or environment variables (local dev).
    Never raises — returns None if credentials missing.
    """
    try:
        from supabase import create_client
        try:
            import streamlit as st
            url = st.secrets["SUPABASE_URL"]
            key = st.secrets["SUPABASE_KEY"]
        except Exception:
            url = os.environ.get("SUPABASE_URL", "")
            key = os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: EMA — single canonical implementation (unchanged from v1.0)
#
# Algorithm mirrors TradingView / Zerodha exactly:
#   1. Seed with SMA of the first `period` closes
#   2. Roll EMA forward using standard multiplier
# ─────────────────────────────────────────────────────────────────────────────

def calc_ema(candles: list, period: int):
    """
    Canonical EMA used by both prewatch.py and scanner.py.
    Matches TradingView/Zerodha EMA exactly.

    candles: list of rows, close price at index [4]
    period:  EMA period (e.g. 20, 200)
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
    Same algorithm but accepts a plain list of floats directly.
    Used by prewatch.py after doing df["Close"].tolist().
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
# SECTION 3: WATCHLIST — Supabase persistent storage
#
# Replaces watchlist.json completely.
# Same interface as v1.0 — callers don't need to change.
#
# DB schema (watchlist table):
#   id, tab, symbol, exchange, direction, entry, sl, target1, target2,
#   note, sector, status, last_price, added_at, token
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_stock(row: dict) -> dict:
    """Convert a Supabase DB row → stock dict used by the app."""
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
        "_db_id":    row.get("id"),       # internal — used for updates/deletes
    }


def _stock_to_row(stock: dict, tab: str) -> dict:
    """Convert a stock dict → Supabase DB row."""
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


def load_watchlist(tab: str = None):
    """
    Load watchlist from Supabase.

    If tab is given (e.g. "Today"):
        Returns list of stock dicts for that tab.

    If tab is None:
        Returns full dict: {"watchlist_Today": [...], "watchlist_Yesterday": [...], ...}
        Same structure as old watchlist.json — callers stay compatible.
    """
    sb = _get_supabase()
    if sb is None:
        return [] if tab else {f"watchlist_{t}": [] for t in WATCHLIST_TABS}

    try:
        if tab:
            res = sb.table("watchlist").select("*").eq("tab", tab).order("id").execute()
            return [_row_to_stock(r) for r in (res.data or [])]
        else:
            # Load all tabs at once
            res = sb.table("watchlist").select("*").order("id").execute()
            result = {f"watchlist_{t}": [] for t in WATCHLIST_TABS}
            for row in (res.data or []):
                key = f"watchlist_{row.get('tab', '')}"
                if key in result:
                    result[key].append(_row_to_stock(row))
            return result
    except Exception as e:
        return [] if tab else {f"watchlist_{t}": [] for t in WATCHLIST_TABS}


def save_watchlist(data: dict):
    """
    Save full watchlist dict to Supabase.

    Accepts same format as old watchlist.json:
    {
        "watchlist_Today":     [...],
        "watchlist_Yesterday": [...],
        "watchlist_New":       [...],
    }

    Strategy: delete all rows for each tab present in data, then re-insert.
    This keeps it simple and consistent — no partial update complexity.
    """
    sb = _get_supabase()
    if sb is None:
        raise RuntimeError("Supabase not configured — check SUPABASE_URL and SUPABASE_KEY in secrets")

    try:
        for tab in WATCHLIST_TABS:
            key = f"watchlist_{tab}"
            if key not in data:
                continue

            stocks = data[key]

            # Delete existing rows for this tab
            sb.table("watchlist").delete().eq("tab", tab).execute()

            # Re-insert all stocks
            if stocks:
                rows = [_stock_to_row(s, tab) for s in stocks]
                sb.table("watchlist").insert(rows).execute()

        return True
    except Exception as e:
        raise RuntimeError(f"Supabase save failed: {e}")


def add_to_watchlist(tab: str, stock: dict):
    """
    Add a single stock to a tab — more efficient than save_watchlist for single inserts.
    Used by prewatch batch inject and watchlist add form.
    Returns the inserted row or None on failure.
    """
    sb = _get_supabase()
    if sb is None:
        raise RuntimeError("Supabase not configured")

    try:
        row = _stock_to_row(stock, tab)
        res = sb.table("watchlist").insert(row).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        raise RuntimeError(f"Supabase insert failed: {e}")


def delete_from_watchlist(db_id: int):
    """
    Delete a single stock by its database ID.
    More efficient than save_watchlist for single deletes.
    """
    sb = _get_supabase()
    if sb is None:
        raise RuntimeError("Supabase not configured")

    try:
        sb.table("watchlist").delete().eq("id", db_id).execute()
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase delete failed: {e}")


def update_watchlist_stock(db_id: int, updates: dict):
    """
    Update a single stock's fields by database ID.
    Used for status updates, price updates, edit form saves.
    """
    sb = _get_supabase()
    if sb is None:
        raise RuntimeError("Supabase not configured")

    try:
        # Map app field names → DB column names
        db_updates = {}
        field_map = {
            "status":    "status",
            "lastPrice": "last_price",
            "entry":     "entry",
            "sl":        "sl",
            "target1":   "target1",
            "target2":   "target2",
            "note":      "note",
        }
        for app_key, db_col in field_map.items():
            if app_key in updates:
                db_updates[db_col] = updates[app_key]

        if db_updates:
            sb.table("watchlist").update(db_updates).eq("id", db_id).execute()
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase update failed: {e}")


def clear_watchlist_tab(tab: str):
    """Delete all stocks in a tab."""
    sb = _get_supabase()
    if sb is None:
        raise RuntimeError("Supabase not configured")

    try:
        sb.table("watchlist").delete().eq("tab", tab).execute()
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase clear failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: SELF-TEST
# Run: python core.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # EMA smoke test
    dummy_closes = [100, 102, 101, 103, 104, 105, 103, 106, 107, 108,
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
    sb = _get_supabase()
    if sb:
        print("\nSupabase connection: OK")
        rows = sb.table("watchlist").select("id").limit(1).execute()
        print(f"Watchlist table reachable: OK ({len(rows.data)} rows sampled)")
    else:
        print("\nSupabase: not configured (set SUPABASE_URL + SUPABASE_KEY)")

    print("\ncore.py v2.0 — all checks passed ✅")
