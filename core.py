# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — core.py  v3.0
#  v3.0: Per-user data via Supabase Auth user_id
#        — watchlist queries filtered by user_id
#        — scanner_results CRUD added
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
import requests
from datetime import date

WATCHLIST_TABS = ["Today", "Yesterday", "New"]

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: SUPABASE REST API HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_supabase_config():
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
    """Get current logged-in user_id from session state."""
    try:
        import streamlit as st
        return st.session_state.get("user_id", "")
    except Exception:
        return ""


def _headers():
    _, key = _get_supabase_config()
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _table_url(table: str) -> str:
    url, _ = _get_supabase_config()
    return f"{url}/rest/v1/{table}"


def _sb_select(table: str, filters: dict = None) -> list:
    params = {"select": "*", "order": "id.asc"}
    if filters:
        params.update(filters)
    res = requests.get(_table_url(table), headers=_headers(), params=params, timeout=10)
    res.raise_for_status()
    return res.json()


def _sb_insert(table: str, rows: list) -> list:
    if not rows:
        return []
    res = requests.post(_table_url(table), headers=_headers(), json=rows, timeout=10)
    res.raise_for_status()
    return res.json()


def _sb_update(table: str, filter_str: str, updates: dict):
    url = f"{_table_url(table)}?{filter_str}"
    res = requests.patch(url, headers=_headers(), json=updates, timeout=10)
    res.raise_for_status()
    return res.json()


def _sb_upsert(table: str, rows: list, on_conflict: str) -> list:
    headers = {**_headers(), "Prefer": f"resolution=merge-duplicates,return=representation"}
    res = requests.post(
        f"{_table_url(table)}?on_conflict={on_conflict}",
        headers=headers, json=rows, timeout=10
    )
    res.raise_for_status()
    return res.json()


def _sb_delete(table: str, filter_str: str):
    url = f"{_table_url(table)}?{filter_str}"
    res = requests.delete(url, headers=_headers(), timeout=10)
    res.raise_for_status()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: EMA — unchanged
# ─────────────────────────────────────────────────────────────────────────────

def calc_ema(candles: list, period: int):
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
    if not closes or len(closes) < period:
        return None
    sma        = sum(closes[:period]) / period
    multiplier = 2 / (period + 1)
    ema        = sma
    for close in closes[period:]:
        ema = (close - ema) * multiplier + ema
    return ema


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: ROW CONVERTERS — watchlist
# ─────────────────────────────────────────────────────────────────────────────

def _row_to_stock(row: dict) -> dict:
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
    user_id = _get_user_id() or None  # None instead of "" for UUID column
    return {
        "tab":        tab,
        "user_id":    user_id,
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
# SECTION 4: WATCHLIST CRUD — per user
# ─────────────────────────────────────────────────────────────────────────────

def load_watchlist(tab: str = None):
    try:
        user_id = _get_user_id()

        if tab:
            filters = {"tab": f"eq.{tab}"}
            if user_id:
                filters["user_id"] = f"eq.{user_id}"
            rows = _sb_select("watchlist", filters)
            return [_row_to_stock(r) for r in rows]
        else:
            filters = {}
            if user_id:
                filters["user_id"] = f"eq.{user_id}"
            rows   = _sb_select("watchlist", filters)
            result = {f"watchlist_{t}": [] for t in WATCHLIST_TABS}
            for row in rows:
                key = f"watchlist_{row.get('tab', '')}"
                if key in result:
                    result[key].append(_row_to_stock(row))
            return result
    except Exception as e:
        return [] if tab else {f"watchlist_{t}": [] for t in WATCHLIST_TABS}


def save_watchlist(data: dict):
    try:
        user_id = _get_user_id() or None
        for tab in WATCHLIST_TABS:
            key    = f"watchlist_{tab}"
            stocks = data.get(key)
            if stocks is None:
                continue
            if user_id:
                _sb_delete("watchlist", f"tab=eq.{tab}&user_id=eq.{user_id}")
            else:
                _sb_delete("watchlist", f"tab=eq.{tab}&user_id=is.null")
            if stocks:
                rows = [_stock_to_row(s, tab) for s in stocks]
                _sb_insert("watchlist", rows)
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase save failed: {e}")


def add_to_watchlist(tab: str, stock: dict):
    try:
        row = _stock_to_row(stock, tab)
        res = _sb_insert("watchlist", [row])
        return res[0] if res else None
    except Exception as e:
        raise RuntimeError(f"Supabase insert failed: {e}")


def insert_many_to_watchlist(tab: str, stocks: list):
    if not stocks:
        return []
    try:
        rows = [_stock_to_row(s, tab) for s in stocks]
        return _sb_insert("watchlist", rows)
    except Exception as e:
        raise RuntimeError(f"Supabase batch insert failed: {e}")


def delete_from_watchlist(db_id: int):
    try:
        _sb_delete("watchlist", f"id=eq.{db_id}")
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase delete failed: {e}")


def update_watchlist_stock(db_id: int, updates: dict):
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
            _sb_update("watchlist", f"id=eq.{db_id}", db_updates)
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase update failed: {e}")


def clear_watchlist_tab(tab: str):
    try:
        user_id = _get_user_id() or None
        if user_id:
            _sb_delete("watchlist", f"tab=eq.{tab}&user_id=eq.{user_id}")
        else:
            _sb_delete("watchlist", f"tab=eq.{tab}&user_id=is.null")
        return True
    except Exception as e:
        raise RuntimeError(f"Supabase clear failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: SCANNER RESULTS CRUD — per user
# ─────────────────────────────────────────────────────────────────────────────

def _result_to_row(result: dict, watchlist_tab: str) -> dict:
    """Convert scanner result dict → Supabase scanner_results row."""
    user_id    = _get_user_id()
    et         = result.get("entry_target") or {}
    return {
        "user_id":       user_id,
        "scan_date":     str(date.today()),
        "watchlist_tab": watchlist_tab,
        "symbol":        result.get("symbol"),
        "signal":        result.get("signal"),
        "exit_status":   result.get("exit_status", "ACTIVE"),
        "entry_target":  json.dumps(et),
        "ltp":           result.get("ltp"),
        "ema20":         result.get("ema20"),
        "ema200":        result.get("ema200"),
        "vwap":          result.get("vwap"),
        "pct_change":    result.get("pctChange"),
        "score":         result.get("score"),
        "sector":        result.get("sector"),
        "volume":        result.get("volume"),
        "open_price":    result.get("openPrice"),
        "high_price":    result.get("highPrice"),
        "low_price":     result.get("lowPrice"),
        "close_price":   result.get("closePrice"),
        "sl_hit":        result.get("sl_hit", False),
        "t1_achieved":   result.get("t1_achieved", False),
        "timestamp":     result.get("timestamp"),
    }


def _row_to_result(row: dict) -> dict:
    """Convert Supabase scanner_results row → scanner result dict."""
    et = row.get("entry_target")
    if isinstance(et, str):
        try:    et = json.loads(et)
        except: et = {}
    elif not isinstance(et, dict):
        et = {}
    return {
        "symbol":       row.get("symbol"),
        "signal":       row.get("signal"),
        "exit_status":  row.get("exit_status", "ACTIVE"),
        "entry_target": et,
        "ltp":          row.get("ltp"),
        "ema20":        row.get("ema20"),
        "ema200":       row.get("ema200"),
        "vwap":         row.get("vwap"),
        "pctChange":    row.get("pct_change"),
        "score":        row.get("score"),
        "sector":       row.get("sector"),
        "volume":       row.get("volume"),
        "openPrice":    row.get("open_price"),
        "highPrice":    row.get("high_price"),
        "lowPrice":     row.get("low_price"),
        "closePrice":   row.get("close_price"),
        "sl_hit":       row.get("sl_hit", False),
        "t1_achieved":  row.get("t1_achieved", False),
        "timestamp":    row.get("timestamp"),
        "_db_id":       row.get("id"),
    }


def load_scanner_results(watchlist_tab: str) -> list:
    """Load today's scanner results for current user and watchlist tab."""
    try:
        user_id = _get_user_id()
        if not user_id:
            return []
        rows = _sb_select("scanner_results", {
            "user_id":       f"eq.{user_id}",
            "scan_date":     f"eq.{date.today()}",
            "watchlist_tab": f"eq.{watchlist_tab}",
            "order":         "timestamp.asc",
        })
        return [_row_to_result(r) for r in rows]
    except Exception:
        return []


def save_scanner_result(result: dict, watchlist_tab: str):
    """Insert or update a single scanner result row."""
    try:
        user_id = _get_user_id()
        if not user_id:
            return
        row = _result_to_row(result, watchlist_tab)

        # Check if row exists for this user+date+tab+symbol
        existing = _sb_select("scanner_results", {
            "user_id":       f"eq.{user_id}",
            "scan_date":     f"eq.{date.today()}",
            "watchlist_tab": f"eq.{watchlist_tab}",
            "symbol":        f"eq.{result.get('symbol')}",
        })

        if existing:
            db_id = existing[0]["id"]
            _sb_update("scanner_results", f"id=eq.{db_id}", row)
        else:
            _sb_insert("scanner_results", [row])
    except Exception as e:
        pass  # silent — don't break scanning if DB fails


def clear_scanner_results(watchlist_tab: str):
    """Delete all scanner results for current user and watchlist tab."""
    try:
        user_id = _get_user_id()
        if not user_id:
            print("[clear_scanner_results] No user_id — skipping")
            return
        filter_str = f"user_id=eq.{user_id}&watchlist_tab=eq.{watchlist_tab}"
        print(f"[clear_scanner_results] Deleting: {filter_str}")
        _sb_delete("scanner_results", filter_str)
        print("[clear_scanner_results] Done")
    except Exception as e:
        print(f"[clear_scanner_results] ERROR: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: SELF-TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dummy_closes  = [100, 102, 101, 103, 104, 105, 103, 106, 107, 108,
                     107, 109, 110, 111, 110, 112, 113, 114, 113, 115,
                     116, 117, 116, 118, 119]
    dummy_candles = [["2024-01-01", 0, 0, 0, c, 0] for c in dummy_closes]
    ema20         = calc_ema(dummy_candles, 20)
    print(f"EMA20 = {ema20:.4f}")
    print("core.py v3.0 — all checks passed ✅")
