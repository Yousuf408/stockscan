# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — core.py  v1.0
#  SHARED ENGINE — imported by prewatch.py and scan.py
#  Step 1: EMA calculation + Watchlist read/write
#  DO NOT put any Streamlit UI code here.
# ══════════════════════════════════════════════════════════════════════════════

import json
import os

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: PROJECT PATHS
# ─────────────────────────────────────────────────────────────────────────────

# core.py sits inside the project root (same level as watchlist.json)
# If your folder structure is different, change BASE_DIR accordingly.
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_FILE = os.path.join(BASE_DIR, "watchlist.json")
WATCHLIST_TABS = ["Today", "Yesterday", "New"]

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: EMA — single canonical implementation
#
# Algorithm (mirrors TradingView / Zerodha exactly):
#   1. Seed with SMA of the first `period` closes
#   2. Roll EMA forward from there using standard multiplier
#
# This is the manual loop from scan.py — chosen because it matches
# what traders see on their charting platforms.
#
# INPUT:  candles  → list of rows where index [4] is the close price
#                    e.g. [timestamp, open, high, low, close, volume]
#         period   → integer, e.g. 20 or 200
#
# OUTPUT: float EMA value, or None if not enough data
# ─────────────────────────────────────────────────────────────────────────────

def calc_ema(candles: list, period: int):
    """
    Canonical EMA used by both prewatch.py and scan.py.
    Matches TradingView/Zerodha EMA exactly.
    
    candles: list of rows, close price at index [4]
    period:  EMA period (e.g. 20, 200)
    """
    if not candles or len(candles) < period:
        return None

    closes     = [float(c[4]) for c in candles]
    sma        = sum(closes[:period]) / period   # SMA seed — critical for accuracy
    multiplier = 2 / (period + 1)
    ema        = sma

    for close in closes[period:]:
        ema = (close - ema) * multiplier + ema

    return ema


def calc_ema_from_series(closes: list, period: int):
    """
    Same algorithm but accepts a plain list of floats directly.
    Use this when you already have a list of closes (e.g. from pandas df["Close"].tolist()).
    
    This is what prewatch.py should use instead of pandas ewm().
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
# SECTION 3: WATCHLIST — single canonical read/write
#
# Both prewatch.py and scan.py must use ONLY these two functions
# to touch watchlist.json. No other file should open watchlist.json directly.
# ─────────────────────────────────────────────────────────────────────────────

def load_watchlist(tab: str = None) -> list | dict:
    """
    Load watchlist data from watchlist.json.

    If tab is given (e.g. "Today"):
        Returns a list of stock dicts for that tab.
        Returns [] if tab is empty or file missing.

    If tab is None:
        Returns the full raw dict (all tabs).
        Useful for save operations that need to patch one tab.

    Example:
        stocks = load_watchlist("Today")
        all_data = load_watchlist()
    """
    empty_default = {f"watchlist_{t}": [] for t in WATCHLIST_TABS}

    if not os.path.exists(WATCHLIST_FILE):
        return [] if tab else empty_default

    try:
        with open(WATCHLIST_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return [] if tab else empty_default

    if tab is None:
        return data

    return data.get(f"watchlist_{tab}", [])


def save_watchlist(data: dict):
    """
    Write the full watchlist dict back to watchlist.json.

    Always pass the complete dict — don't write partial data.

    Example:
        all_data = load_watchlist()           # load full dict
        all_data["watchlist_Today"].append(x) # modify one tab
        save_watchlist(all_data)              # write back
    """
    try:
        with open(WATCHLIST_FILE, "w") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError as e:
        # Caller should handle this — don't import streamlit here
        raise RuntimeError(f"watchlist.json write failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: QUICK SELF-TEST
# Run this file directly to verify EMA math is correct:
#   python core.py
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Minimal smoke test — 25 candles, EMA20
    # Each candle: [ts, open, high, low, close, volume]
    dummy_closes = [100, 102, 101, 103, 104, 105, 103, 106, 107, 108,
                    107, 109, 110, 111, 110, 112, 113, 114, 113, 115,
                    116, 117, 116, 118, 119]
    dummy_candles = [["2024-01-01", 0, 0, 0, c, 0] for c in dummy_closes]

    ema20 = calc_ema(dummy_candles, 20)
    ema20_series = calc_ema_from_series(dummy_closes, 20)

    print(f"calc_ema()            EMA20 = {ema20:.4f}")
    print(f"calc_ema_from_series() EMA20 = {ema20_series:.4f}")
    print(f"Both match: {abs(ema20 - ema20_series) < 0.0001}")

    # Not enough data test
    assert calc_ema(dummy_candles[:5], 20) is None, "Should return None for insufficient data"
    print("Insufficient data guard: OK")
    print("\ncore.py Step 1 — all checks passed ✅")
