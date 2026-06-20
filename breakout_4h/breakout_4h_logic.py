"""
breakout_4h_logic.py
Core screening logic:
  - run_8_checks()  → all 8 breakout checks on one stock
  - run_scan()      → parallel scan of all stocks
"""

import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from breakout_4h.breakout_4h_config import (
    MAX_CONSOLIDATION_PCT,
    MIN_BREAKOUT_ABOVE_ZONE,
    MIN_BODY_PCT,
    MIN_REL_VOL,
    MIN_AVG_DAILY_VOL,
    MIN_MARKET_CAP,
    NEAR_HIGH_THRESHOLD,
    CONSOLIDATION_LOOKBACK,
    PARALLEL_WORKERS,
)
from breakout_4h.breakout_4h_data import (
    fetch_avg_volumes,
    fetch_1h_data,
    aggregate_to_4h,
    fetch_daily_data,
)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — 8 CHECKS
# ─────────────────────────────────────────────────────────────
def run_8_checks(symbol: str, df_4h: pd.DataFrame, avg_vol_20d: float) -> dict | None:
    """
    Run all 8 breakout checks on a stock's 4H candle data.
    Returns result dict if ALL 8 checks pass, else None.

    Checks:
    1. Consolidation range ≤ 12% over last 10 4H candles
    2. Current close ≥ consolidationHigh × 1.02 (breakout)
    3. Candle body size ≥ 5%
    4. Relative volume ≥ 1.5× avg of prior 10 4H candles
    5. Avg daily volume ≥ 500,000 (liquidity)
    6. Market cap ≥ 50M
    7. Price within 10% of 20d or 50d high
    8. Close > SMA20 and SMA50
    """
    if df_4h is None or len(df_4h) < CONSOLIDATION_LOOKBACK + 2:
        return None

    # ── Most recently completed 4H candle ──
    current  = df_4h.iloc[-1]
    lookback = df_4h.iloc[-(CONSOLIDATION_LOOKBACK + 1):-1]  # prior 10 candles

    cur_open   = current["open"]
    cur_close  = current["close"]
    cur_volume = current["volume"]

    # ── CHECK 1: Consolidation ≤ 12% ──
    con_high = lookback.apply(
        lambda r: max(r["open"], r["close"]), axis=1
    ).max()
    con_low  = lookback.apply(
        lambda r: min(r["open"], r["close"]), axis=1
    ).min()

    if con_low <= 0:
        return None

    range_pct = (con_high - con_low) / con_low * 100
    if range_pct > MAX_CONSOLIDATION_PCT:
        return None

    # ── CHECK 2: Breakout above zone ──
    if cur_close < con_high * MIN_BREAKOUT_ABOVE_ZONE:
        return None

    breakout_pct = (cur_close - con_high) / con_high * 100

    # ── CHECK 3: Candle body ≥ 5% ──
    if cur_open <= 0:
        return None
    body_pct = abs(cur_close - cur_open) / cur_open * 100
    if body_pct < MIN_BODY_PCT:
        return None

    # ── CHECK 4: Relative volume ≥ 1.5× ──
    avg_4h_vol = lookback["volume"].mean()
    if avg_4h_vol <= 0:
        return None
    rel_vol = cur_volume / avg_4h_vol
    if rel_vol < MIN_REL_VOL:
        return None

    # ── CHECK 5: Avg daily volume ≥ 500k ──
    if avg_vol_20d < MIN_AVG_DAILY_VOL:
        return None

    # ── Fetch daily data for checks 6, 7, 8 ──
    daily_close, mktcap = fetch_daily_data(symbol)
    if daily_close is None:
        return None

    # ── CHECK 6: Market cap ≥ 50M ──
    if mktcap < MIN_MARKET_CAP:
        return None

    # ── CHECK 7: Price within 10% of 20d or 50d high ──
    high_20d = max(daily_close[-20:]) if len(daily_close) >= 20 else max(daily_close)
    high_50d = max(daily_close[-50:]) if len(daily_close) >= 50 else max(daily_close)

    near_20d = cur_close >= high_20d * NEAR_HIGH_THRESHOLD
    near_50d = cur_close >= high_50d * NEAR_HIGH_THRESHOLD
    if not (near_20d or near_50d):
        return None

    pct_from_high = min(
        (cur_close - high_20d) / high_20d * 100,
        (cur_close - high_50d) / high_50d * 100
    )

    # ── CHECK 8: Close > SMA20 and SMA50 ──
    if len(daily_close) < 50:
        return None

    sma20 = float(np.mean(daily_close[-20:]))
    sma50 = float(np.mean(daily_close[-50:]))

    if cur_close <= sma20 or cur_close <= sma50:
        return None

    # ── ALL 8 CHECKS PASSED ✅ ──
    return {
        "symbol"       : symbol,
        "price"        : round(float(cur_close),    2),
        "breakout_pct" : round(float(breakout_pct), 2),
        "body_pct"     : round(float(body_pct),     2),
        "rel_vol"      : round(float(rel_vol),      2),
        "pct_from_high": round(float(pct_from_high),2),
        "con_high"     : round(float(con_high),     2),
        "con_low"      : round(float(con_low),      2),
        "range_pct"    : round(float(range_pct),    2),
        "sma20"        : round(float(sma20),        2),
        "sma50"        : round(float(sma50),        2),
        "avg_vol_20d"  : int(avg_vol_20d),
        "candles_4h"   : df_4h.tail(15).to_dict("records"),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 2 — SINGLE STOCK PROCESSOR
# ─────────────────────────────────────────────────────────────
def _process_single_stock(symbol: str, avg_vol: float) -> dict | None:
    """
    Fetch + aggregate + check one stock.
    Used by parallel executor.
    """
    try:
        df_1h = fetch_1h_data(symbol)
        if df_1h is None:
            return None

        df_4h = aggregate_to_4h(df_1h)
        if df_4h.empty:
            return None

        return run_8_checks(symbol, df_4h, avg_vol)

    except Exception as e:
        print(f"[breakout_4h_logic] {symbol} error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# SECTION 3 — PARALLEL SCAN
# ─────────────────────────────────────────────────────────────
def run_scan(
    all_stocks    : list,
    progress_cb   = None,
    status_cb     = None,
) -> list:
    """
    Parallel scan of all stocks using ThreadPoolExecutor.
    - all_stocks : list of NSE symbol strings
    - progress_cb: callable(current, total) for progress bar
    - status_cb  : callable(symbol) for status text
    Returns list of passing stocks sorted by rel_vol descending.

    Speed: ~20 parallel workers → 849 stocks in ~40-50 seconds
    """
    # Step 1: Fetch avg volumes from Supabase (once, fast)
    avg_volumes = fetch_avg_volumes()
    total       = len(all_stocks)
    results     = []
    completed   = 0

    # Step 2: Parallel fetch + check
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:

        # Submit all jobs
        future_to_symbol = {
            executor.submit(
                _process_single_stock,
                symbol,
                avg_volumes.get(symbol, 0)
            ): symbol
            for symbol in all_stocks
        }

        # Collect results as they complete
        for future in as_completed(future_to_symbol):
            symbol    = future_to_symbol[future]
            completed += 1

            # Progress callback
            if progress_cb:
                progress_cb(completed, total)

            # Status callback
            if status_cb:
                status_cb(symbol, completed, total)

            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                print(f"[breakout_4h_logic] {symbol} future error: {e}")

    # Step 3: Sort by relative volume descending
    results.sort(key=lambda x: x["rel_vol"], reverse=True)
    return results
