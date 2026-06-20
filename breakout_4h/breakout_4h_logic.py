"""
breakout_4h_logic.py
4 checks only:
  Check 1: Consolidation  → last 10 completed 4H candles ≤ 12%
  Check 2: Breakout close → 1H close > conHigh
  Check 3: Rel. Volume    → 1H vol ≥ 1.2x median of last 5 1H candles
  Check 4: Trend          → 1H close > SMA20 & SMA50 (daily)
"""

import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from breakout_4h.breakout_4h_config import (
    MAX_CONSOLIDATION_PCT,
    CONSOLIDATION_LOOKBACK,
    PARALLEL_WORKERS,
)
from breakout_4h.breakout_4h_data import (
    fetch_1h_and_4h_data,
    fetch_daily_data,
)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
MIN_REL_VOL       = 1.2   # 1H vol ≥ 1.2x median
VOL_MEDIAN_WINDOW = 5     # last 5 1H candles


# ─────────────────────────────────────────────────────────────
# SECTION 1 — 4 CHECKS
# ─────────────────────────────────────────────────────────────
def run_checks(
    symbol : str,
    df_1h  : pd.DataFrame,
    df_4h  : pd.DataFrame,
) -> dict | None:
    """
    4 checks:
    Check 1 → 4H consolidation zone ≤ 12%
    Check 2 → 1H close > conHigh (breakout)
    Check 3 → 1H vol ≥ 1.2x median of last 5 1H candles
    Check 4 → 1H close > SMA20 & SMA50 (daily)
    """

    # ── Validate ──
    if df_4h is None or len(df_4h) < CONSOLIDATION_LOOKBACK + 1:
        return None
    if df_1h is None or len(df_1h) < 6:
        return None

    # ─────────────────────────────────────────────────────────
    # CHECK 1 — Consolidation zone (4H)
    # Last 10 completed 4H candles
    # ─────────────────────────────────────────────────────────
    lookback_4h = df_4h.iloc[-(CONSOLIDATION_LOOKBACK + 1):-1]

    con_high = lookback_4h.apply(
        lambda r: max(r["open"], r["close"]), axis=1
    ).max()
    con_low  = lookback_4h.apply(
        lambda r: min(r["open"], r["close"]), axis=1
    ).min()

    if con_low <= 0:
        return None

    range_pct = (con_high - con_low) / con_low * 100
    if range_pct > MAX_CONSOLIDATION_PCT:
        return None

    # ─────────────────────────────────────────────────────────
    # CHECK 2 — Breakout close (1H)
    # Current 1H close > conHigh
    # ─────────────────────────────────────────────────────────
    current_1h = df_1h.iloc[-1]
    cur_close  = float(current_1h["close"])
    cur_open   = float(current_1h["open"])
    cur_volume = float(current_1h["volume"])

    if cur_close <= con_high:
        return None

    breakout_pct = (cur_close - con_high) / con_high * 100

    # ─────────────────────────────────────────────────────────
    # CHECK 3 — Relative Volume (1H)
    # Current 1H vol ≥ 1.2x median of last 5 1H candles
    # ─────────────────────────────────────────────────────────
    last_5_1h    = df_1h.iloc[-6:-1]
    if len(last_5_1h) < 3:
        return None

    median_vol = float(np.median(last_5_1h["volume"].values))
    if median_vol <= 0:
        return None

    rel_vol = cur_volume / median_vol
    if rel_vol < MIN_REL_VOL:
        return None

    # ─────────────────────────────────────────────────────────
    # CHECK 4 — Trend (Daily SMA)
    # 1H close > SMA20 & SMA50
    # ─────────────────────────────────────────────────────────
    daily_close, _ = fetch_daily_data(symbol)
    if daily_close is None or len(daily_close) < 50:
        return None

    sma20 = float(np.mean(daily_close[-20:]))
    sma50 = float(np.mean(daily_close[-50:]))

    if cur_close <= sma20 or cur_close <= sma50:
        return None

    # ── ALL 4 CHECKS PASSED ✅ ──
    body_pct = abs(cur_close - cur_open) / cur_open * 100 if cur_open > 0 else 0

    return {
        "symbol"       : symbol,
        "price"        : round(cur_close,     2),
        "breakout_pct" : round(breakout_pct,  2),
        "body_pct"     : round(body_pct,      2),
        "rel_vol"      : round(rel_vol,        2),
        "con_high"     : round(con_high,       2),
        "con_low"      : round(con_low,        2),
        "range_pct"    : round(range_pct,      2),
        "sma20"        : round(sma20,           2),
        "sma50"        : round(sma50,           2),
        "median_vol"   : int(median_vol),
        "candles_4h"   : df_4h.tail(20).to_dict("records"),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 2 — SINGLE STOCK PROCESSOR
# ─────────────────────────────────────────────────────────────
def _process_single_stock(symbol: str) -> dict | None:
    """Fetch + aggregate + check one stock."""
    try:
        df_1h, df_4h = fetch_1h_and_4h_data(symbol)
        if df_1h is None or df_4h is None:
            return None
        return run_checks(symbol, df_1h, df_4h)
    except Exception as e:
        print(f"[breakout_4h_logic] {symbol} error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# SECTION 3 — PARALLEL SCAN
# ─────────────────────────────────────────────────────────────
def run_scan(
    all_stocks  : list,
    progress_cb = None,
    status_cb   = None,
) -> list:
    """
    Parallel scan — 4 checks only.
    Returns list sorted by rel_vol descending.
    """
    total     = len(all_stocks)
    results   = []
    completed = 0

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:

        future_to_symbol = {
            executor.submit(_process_single_stock, symbol): symbol
            for symbol in all_stocks
        }

        for future in as_completed(future_to_symbol):
            symbol     = future_to_symbol[future]
            completed += 1

            if progress_cb:
                progress_cb(completed, total)
            if status_cb:
                status_cb(symbol, completed, total)

            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                print(f"[breakout_4h_logic] {symbol} future error: {e}")

    results.sort(key=lambda x: x["rel_vol"], reverse=True)
    return results
