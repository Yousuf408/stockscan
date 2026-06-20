"""
breakout_4h_logic.py
Core screening logic:
  - Consolidation zone  → last 10 completed 4H candles
  - Breakout checks     → most recent completed 1H candle
  - Rel. Volume check   → current 1H vol ≥ 1.5× median of last 5 1H candles
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
    fetch_1h_and_4h_data,
    fetch_daily_data,
)


# ─────────────────────────────────────────────────────────────
# SECTION 1 — 8 CHECKS
# ─────────────────────────────────────────────────────────────
def run_8_checks(
    symbol     : str,
    df_1h      : pd.DataFrame,
    df_4h      : pd.DataFrame,
    avg_vol_20d: float
) -> dict | None:
    """
    8 breakout checks:
    Checks 1        → 4H candles (consolidation zone)
    Checks 2,3,4    → 1H candle  (breakout signal)
    Checks 5,6,7,8  → Daily data (filters)
    """

    # ── Validate data ──
    if df_4h is None or len(df_4h) < CONSOLIDATION_LOOKBACK + 1:
        return None
    if df_1h is None or len(df_1h) < 6:
        return None

    # ─────────────────────────────────────────────────────────
    # 4H DATA — Consolidation zone
    # ─────────────────────────────────────────────────────────
    lookback_4h = df_4h.iloc[-(CONSOLIDATION_LOOKBACK + 1):-1]  # last 10 completed 4H

    # ── CHECK 1: Consolidation range ≤ 12% ──
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
    # 1H DATA — Breakout signal
    # ─────────────────────────────────────────────────────────
    # Most recently completed 1H candle
    current_1h  = df_1h.iloc[-1]
    cur_open    = current_1h["open"]
    cur_close   = current_1h["close"]
    cur_volume  = current_1h["volume"]

    # Last 5 completed 1H candles (excluding current)
    last_5_1h   = df_1h.iloc[-6:-1]

    # ── CHECK 2: Breakout — 1H close ≥ conHigh × 1.02 ──
    if cur_close < con_high * MIN_BREAKOUT_ABOVE_ZONE:
        return None

    breakout_pct = (cur_close - con_high) / con_high * 100

    # ── CHECK 3: Body size — 1H candle body ≥ 5% ──
    if cur_open <= 0:
        return None
    body_pct = abs(cur_close - cur_open) / cur_open * 100
    if body_pct < MIN_BODY_PCT:
        return None

    # ── CHECK 4: Rel. Volume — 1H vol ≥ 1.5× median of last 5 1H candles ──
    if len(last_5_1h) < 3:
        return None
    median_5_vol = float(np.median(last_5_1h["volume"].values))
    if median_5_vol <= 0:
        return None
    rel_vol = cur_volume / median_5_vol
    if rel_vol < MIN_REL_VOL:
        return None

    # ── CHECK 5: Liquidity — avg daily volume ≥ 500k ──
    if avg_vol_20d < MIN_AVG_DAILY_VOL:
        return None

    # ─────────────────────────────────────────────────────────
    # DAILY DATA — Checks 6, 7, 8
    # ─────────────────────────────────────────────────────────
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
        "symbol"        : symbol,
        "price"         : round(float(cur_close),     2),
        "breakout_pct"  : round(float(breakout_pct),  2),
        "body_pct"      : round(float(body_pct),      2),
        "rel_vol"       : round(float(rel_vol),        2),
        "pct_from_high" : round(float(pct_from_high),  2),
        "con_high"      : round(float(con_high),       2),
        "con_low"       : round(float(con_low),        2),
        "range_pct"     : round(float(range_pct),      2),
        "sma20"         : round(float(sma20),           2),
        "sma50"         : round(float(sma50),           2),
        "avg_vol_20d"   : int(avg_vol_20d),
        "median_5_1h_vol": int(median_5_vol),
        # Chart data — last 20 4H candles
        "candles_4h"    : df_4h.tail(20).to_dict("records"),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 2 — SINGLE STOCK PROCESSOR
# ─────────────────────────────────────────────────────────────
def _process_single_stock(symbol: str, avg_vol: float) -> dict | None:
    """Fetch + aggregate + check one stock. Used by parallel executor."""
    try:
        df_1h, df_4h = fetch_1h_and_4h_data(symbol)
        if df_1h is None or df_4h is None:
            return None

        return run_8_checks(symbol, df_1h, df_4h, avg_vol)

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
    Parallel scan of all stocks.
    Consolidation = 4H | Breakout = 1H | Rel.Vol = median 5 1H candles
    Returns list of passing stocks sorted by rel_vol descending.
    """
    avg_volumes = fetch_avg_volumes()
    total       = len(all_stocks)
    results     = []
    completed   = 0

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:

        future_to_symbol = {
            executor.submit(
                _process_single_stock,
                symbol,
                avg_volumes.get(symbol, 0)
            ): symbol
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
