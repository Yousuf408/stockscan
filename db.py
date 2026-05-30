# ══════════════════════════════════════════
#  TRADESENTRY — db.py
#  Single-user persistent storage layer
#  Replaces: chrome.storage.local
#  Stack: st.session_state + JSON file + GitHub API commit
#
#  Drop-in usage:
#    from db import get_watchlist, set_watchlist, get_price_cache, set_price_cache
# ══════════════════════════════════════════

import streamlit as st
import json
import os
import requests
import base64
from datetime import datetime
import pytz

# ── FILE PATHS ────────────────────────────────────────────────────────────────
ROOT             = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_FILE   = os.path.join(ROOT, "watchlist.json")
PRICE_CACHE_FILE = os.path.join(ROOT, "price_cache.json")
WATCHLIST_NAMES  = ["Today", "Yesterday", "New"]

IST = pytz.timezone("Asia/Kolkata")

# ── DEFAULTS ─────────────────────────────────────────────────────────────────
def _default_watchlist() -> dict:
    return {f"watchlist_{n}": [] for n in WATCHLIST_NAMES}

def _default_price_cache() -> dict:
    return {
        "mode": "offline",
        "last_update": "",
        "stocks": {},
        "failures": 0,
        "circuit_broken": False
    }


# ══════════════════════════════════════════
#  GITHUB COMMIT HELPER
#  Commits a file back to your repo so it
#  survives Streamlit Cloud redeployment.
#  Requires in st.secrets:
#    GITHUB_TOKEN = "ghp_xxxx"
#    GITHUB_REPO  = "Yousuf408/stockscan"
#    GITHUB_BRANCH = "main"   (optional, default: main)
# ══════════════════════════════════════════

def _commit_to_github(filename: str, content: str, commit_message: str) -> bool:
    """
    Commits a file to GitHub repo via API.
    Returns True on success, False on failure.
    Silent fail — never crashes the app.
    """
    try:
        token  = st.secrets.get("GITHUB_TOKEN")
        repo   = st.secrets.get("GITHUB_REPO")
        branch = st.secrets.get("GITHUB_BRANCH", "main")

        if not token or not repo:
            # GitHub secrets not configured — skip commit silently
            return False

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }

        api_url = f"https://api.github.com/repos/{repo}/contents/{filename}"

        # Step 1 — get current file SHA (required for update)
        sha = None
        resp = requests.get(api_url, headers=headers, params={"ref": branch}, timeout=5)
        if resp.status_code == 200:
            sha = resp.json().get("sha")

        # Step 2 — push the updated file
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "branch":  branch,
        }
        if sha:
            payload["sha"] = sha  # required for updating existing file

        put_resp = requests.put(api_url, headers=headers, json=payload, timeout=10)
        success = put_resp.status_code in (200, 201)

        if success:
            print(f"[GitHub] ✅ Committed {filename}")
        else:
            print(f"[GitHub] ❌ Commit failed: {put_resp.status_code} {put_resp.text[:100]}")

        return success

    except Exception as e:
        print(f"[GitHub] Commit error (non-fatal): {e}")
        return False


# ══════════════════════════════════════════
#  WATCHLIST STORAGE
#  Replaces: chrome.storage.local (watchlist_*)
# ══════════════════════════════════════════

def _load_watchlist_from_file() -> dict:
    """Read watchlist.json from disk."""
    try:
        if os.path.exists(WATCHLIST_FILE):
            with open(WATCHLIST_FILE, "r") as f:
                data = json.load(f)
                # ensure all tabs exist
                for n in WATCHLIST_NAMES:
                    data.setdefault(f"watchlist_{n}", [])
                return data
    except Exception as e:
        print(f"[DB] watchlist read error: {e}")
    return _default_watchlist()

def _save_watchlist_to_file(data: dict):
    """Write watchlist.json to disk."""
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[DB] watchlist write error: {e}")

# ── PUBLIC API ────────────────────────────────────────────────────────────────

def get_watchlist(tab: str = None) -> dict | list:
    """
    Returns full watchlist dict, or a single tab's list if tab is specified.
    Uses session_state as cache — reads file only on first call per session.

    Replaces: chrome.storage.local.get(['watchlist_Today'], callback)
    """
    if "_wl_data" not in st.session_state:
        st.session_state["_wl_data"] = _load_watchlist_from_file()

    data = st.session_state["_wl_data"]

    if tab:
        return data.get(f"watchlist_{tab}", [])
    return data

def set_watchlist(tab: str, stocks: list, commit: bool = True):
    """
    Saves a tab's stock list.
    1. Updates session_state (instant)
    2. Writes to disk (fast)
    3. Commits to GitHub (background, ~1-2s, non-blocking for UI)

    Replaces: chrome.storage.local.set({ watchlist_Today: [...] }, callback)
    """
    # 1. Session state
    if "_wl_data" not in st.session_state:
        st.session_state["_wl_data"] = _load_watchlist_from_file()

    st.session_state["_wl_data"][f"watchlist_{tab}"] = stocks

    # 2. Disk
    _save_watchlist_to_file(st.session_state["_wl_data"])

    # 3. GitHub commit (only on meaningful changes, not every price update)
    if commit:
        content = json.dumps(st.session_state["_wl_data"], indent=2)
        _commit_to_github(
            filename="watchlist.json",
            content=content,
            commit_message=f"[TradeSentry] Update watchlist_{tab} — {datetime.now(IST).strftime('%d %b %H:%M IST')}"
        )

def add_stock(tab: str, stock: dict):
    """Add a stock to a watchlist tab."""
    stocks = get_watchlist(tab)
    stocks.append(stock)
    set_watchlist(tab, stocks, commit=True)

def remove_stock(tab: str, index: int):
    """Remove a stock by index from a watchlist tab."""
    stocks = get_watchlist(tab)
    if 0 <= index < len(stocks):
        stocks.pop(index)
        set_watchlist(tab, stocks, commit=True)

def update_stock(tab: str, index: int, updates: dict):
    """Update fields on a specific stock."""
    stocks = get_watchlist(tab)
    if 0 <= index < len(stocks):
        stocks[index].update(updates)
        set_watchlist(tab, stocks, commit=True)

def get_all_watchlist_stocks() -> list:
    """
    Returns all unique stocks across all tabs.
    Used by app.py streamer to know what to fetch prices for.
    """
    data = get_watchlist()
    all_stocks = []
    seen = set()
    for tab in WATCHLIST_NAMES:
        for s in data.get(f"watchlist_{tab}", []):
            key = (s.get("symbol"), s.get("exchange", "NS"))
            if key not in seen:
                seen.add(key)
                all_stocks.append(s)
    return all_stocks


# ══════════════════════════════════════════
#  PRICE CACHE STORAGE
#  Replaces: price_cache.json read/write
# ══════════════════════════════════════════

def _load_cache_from_file() -> dict:
    try:
        if os.path.exists(PRICE_CACHE_FILE):
            with open(PRICE_CACHE_FILE, "r") as f:
                data = json.load(f)
                data.setdefault("failures", 0)
                data.setdefault("circuit_broken", False)
                return data
    except Exception as e:
        print(f"[DB] price cache read error: {e}")
    return _default_price_cache()

def _save_cache_to_file(data: dict):
    try:
        with open(PRICE_CACHE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[DB] price cache write error: {e}")

# ── PUBLIC API ────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    """
    Load price cache. Uses in-process dict for thread safety
    (app.py streamer thread writes, Streamlit UI thread reads).
    Replaces: load_cache() in app.py
    """
    return _load_cache_from_file()

def save_cache(cache: dict):
    """Replaces: save_cache() in app.py"""
    _save_cache_to_file(cache)

def update_price(symbol: str, exchange: str, price: float, source: str):
    """
    Update a single stock's price in cache.
    Auto-sets mode badge from source.
    Replaces: update_price() in app.py
    """
    cache = load_cache()

    cache["stocks"][symbol] = {
        "price":    price,
        "source":   source,
        "time":     datetime.now(IST).strftime("%H:%M:%S IST"),
        "exchange": exchange
    }
    cache["last_update"] = datetime.now(IST).strftime("%H:%M:%S IST")

    # Auto-set mode from actual source — drives the UI badge
    source_to_mode = {
        "websocket": "websocket",
        "http":      "http_polling",
        "yfinance":  "yfinance",
    }
    if source in source_to_mode:
        cache["mode"] = source_to_mode[source]

    save_cache(cache)

def force_set_mode(mode: str):
    """Replaces: force_set_mode() in app.py"""
    cache = load_cache()
    cache["mode"] = mode
    save_cache(cache)

def increment_failure_count() -> int:
    """
    Only call this after a REAL failure, not on attempt.
    Replaces: increment_failure_count() in app.py
    """
    cache = load_cache()
    current_fails = cache.get("failures", 0) + 1
    cache["failures"] = current_fails
    if current_fails >= 2:
        cache["circuit_broken"] = True
        cache["mode"] = "http_polling"
        print("🚨 [Circuit Breaker] 2 failures — switching to HTTP to prevent API ban")
    save_cache(cache)
    return current_fails

def reset_failure_count():
    """Replaces: reset_failure_count() in app.py"""
    cache = load_cache()
    cache["failures"] = 0
    cache["circuit_broken"] = False
    save_cache(cache)

def get_price(symbol: str) -> dict | None:
    """Get cached price data for a symbol. Used by 3_Watchlist.py"""
    cache = load_cache()
    return cache.get("stocks", {}).get(symbol)
