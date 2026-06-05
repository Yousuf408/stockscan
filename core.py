# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — core.py  v4.0
#  v4.0: Dynamic user watchlists (create/rename/delete)
# ══════════════════════════════════════════════════════════════════════════════

import os
import json
import requests
from datetime import date

DEFAULT_WATCHLIST_NAMES = ["Today", "Yesterday", "New"]
MAX_WATCHLISTS = 15

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

def _sb_delete(table: str, filter_str: str):
    url = f"{_table_url(table)}?{filter_str}"
    res = requests.delete(url, headers=_headers(), timeout=10)
    res.raise_for_status()

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: EMA
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
# SECTION 3: USER WATCHLISTS — dynamic tabs per user
# ─────────────────────────────────────────────────────────────────────────────

def get_user_watchlist_names() -> list:
    try:
        user_id = _get_user_id()
        if not user_id:
            return DEFAULT_WATCHLIST_NAMES
        rows = _sb_select("user_watchlists", {
            "user_id": f"eq.{user_id}",
            "order":   "position.asc",
        })
        if rows:
            return [r["name"] for r in rows]
        # First time — create defaults
        defaults = [
            {"user_id": user_id, "name": name, "position": i}
            for i, name in enumerate(DEFAULT_WATCHLIST_NAMES)
        ]
        _sb_insert("user_watchlists", defaults)
        return DEFAULT_WATCHLIST_NAMES
    except Exception as e:
        print(f"[get_user_watchlist_names] Error: {e}")
        return DEFAULT_WATCHLIST_NAMES

def create_user_watchlist(name: str) -> tuple:
    try:
        user_id = _get_user_id()
        if not user_id:
            return False, "Not logged in"
        existing = _sb_select("user_watchlists", {"user_id": f"eq.{user_id}"})
        if len(existing) >= MAX_WATCHLISTS:
            return False, f"Max {MAX_WATCHLISTS} watchlists allowed"
        names = [r["name"].lower() for r in existing]
        if name.strip().lower() in names:
            return False, "Watchlist name already exists"
        position = len(existing)
        _sb_insert("user_watchlists", [{"user_id": user_id, "name": name.strip(), "position": position}])
        return True, "Created"
    except Exception as e:
        return False, str(e)

def rename_user_watchlist(old_name: str, new_name: str) -> tuple:
    try:
        user_id = _get_user_id()
        if not user_id:
            return False, "Not logged in"
        rows = _sb_select("user_watchlists", {
            "user_id": f"eq.{user_id}",
            "name":    f"eq.{old_name}",
        })
        if not rows:
            return False, "Watchlist not found"
        # Check duplicate
        all_rows = _sb_select("user_watchlists", {"user_id": f"eq.{user_id}"})
        names = [r["name"].lower() for r in all_rows if r["name"] != old_name]
        if new_name.strip().lower() in names:
            return False, "Name already exists"
        row_id = rows[0]["id"]
        _sb_update("user_watchlists", f"id=eq.{row_id}", {"name": new_name.strip()})
        # Update stocks tab name
        _sb_update("watchlist", f"user_id=eq.{user_id}&tab=eq.{old_name}", {"tab": new_name.strip()})
        return True, "Renamed"
    except Exception as e:
        return False, str(e)

def delete_user_watchlist(name: str) -> tuple:
    try:
        user_id = _get_user_id()
        if not user_id:
            return False, "Not logged in"
        existing = _sb_select("user_watchlists", {"user_id": f"eq.{user_id}"})
        if len(existing) <= 1:
            return False, "Must keep at least 1 watchlist"
        _sb_delete("user_watchlists", f"user_id=eq.{user_id}&name=eq.{name}")
        _sb_delete("watchlist", f"user_id=eq.{user_id}&tab=eq.{name}")
        return True, "Deleted"
    except Exception as e:
        return False, str(e)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: ROW CONVERTERS
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
    user_id = _get_user_id() or None
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
# SECTION 5: WATCHLIST CRUD
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
            result = {}
            for row in rows:
                key = f"watchlist_{row.get('tab', '')}"
                if key not in result:
                    result[key] = []
                result[key].append(_row_to_stock(row))
            return result
    except Exception as e:
        return [] if tab else {}

def save_watchlist(data: dict):
    try:
        user_id         = _get_user_id() or None
        watchlist_names = get_user_watchlist_names()
        for tab in watchlist_names:
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
# SECTION 6: SCANNER RESULTS CRUD
# ─────────────────────────────────────────────────────────────────────────────

def _result_to_row(result: dict, watchlist_tab: str) -> dict:
    user_id = _get_user_id()
    et      = result.get("entry_target") or {}
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
    try:
        user_id = _get_user_id()
        if not user_id:
            return
        row = _result_to_row(result, watchlist_tab)
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
        print(f"[save_scanner_result] Error: {e}")

def clear_scanner_results(watchlist_tab: str):
    try:
        user_id = _get_user_id()
        if not user_id:
            return
        _sb_delete("scanner_results", f"user_id=eq.{user_id}&watchlist_tab=eq.{watchlist_tab}")
    except Exception as e:
        print(f"[clear_scanner_results] ERROR: {e}")

if __name__ == "__main__":
    dummy_closes  = [100+i for i in range(25)]
    dummy_candles = [["2024-01-01", 0, 0, 0, c, 0] for c in dummy_closes]
    print(f"EMA20 = {calc_ema(dummy_candles, 20):.4f}")
    print("core.py v4.0 ✅")
