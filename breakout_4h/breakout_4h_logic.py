"""
breakout_4h_logic.py
Pure 4H logic — 7 checks:
  Check 1: Consolidation  → last 10 4H candles ≤ 12%
  Check 2: Breakout close → 4H close > conHigh
  Check 3: Body size      → 4H candle body ≥ 5%
  Check 4: Rel. Volume    → 4H vol ≥ 1.2x median of last 5 4H candles
  Check 5: Liquidity      → avg daily vol ≥ 500k (Supabase)
  Check 6: Market cap     → ≥ 10M
  Check 7: Price level    → within 10% of 20d/50d high
  Check 8: Trend          → close > SMA20 & SMA50
"""

import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from breakout_4h.breakout_4h_config import (
        MAX_CONSOLIDATION_PCT,
        CONSOLIDATION_LOOKBACK,
        PARALLEL_WORKERS,
    )
    from breakout_4h.breakout_4h_data import (
        fetch_avg_volumes,
        fetch_1h_and_4h_data,
        fetch_daily_data,
    )
except ImportError:
    from breakout_4h_config import (
        MAX_CONSOLIDATION_PCT,
        CONSOLIDATION_LOOKBACK,
        PARALLEL_WORKERS,
    )
    from breakout_4h_data import (
        fetch_avg_volumes,
        fetch_1h_and_4h_data,
        fetch_daily_data,
    )

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
MIN_BODY_PCT      = 5.0          # Check 3: body ≥ 5%
MIN_REL_VOL       = 1.2          # Check 4: rel vol ≥ 1.2x
MIN_AVG_DAILY_VOL = 500_000      # Check 5: liquidity
MIN_MARKET_CAP    = 10_000_000   # Check 6: market cap ≥ 10M
NEAR_HIGH_PCT     = 0.90         # Check 7: within 10% of high


# ─────────────────────────────────────────────────────────────
# 8 CHECKS — Pure 4H
# ─────────────────────────────────────────────────────────────
def run_checks(symbol, df_1h, df_4h, avg_vol_20d=0):

    if df_4h is None or len(df_4h) < CONSOLIDATION_LOOKBACK + 2:
        return None

    # ── Current + lookback 4H candles ──
    lookback_4h = df_4h.iloc[-(CONSOLIDATION_LOOKBACK + 1):-1]
    current_4h  = df_4h.iloc[-1]
    cur_open    = float(current_4h["open"])
    cur_close   = float(current_4h["close"])
    cur_high    = float(current_4h["high"])
    cur_low     = float(current_4h["low"])
    cur_volume  = float(current_4h["volume"])

    # ── CHECK 1: Consolidation ≤ 12% ──
    con_high = lookback_4h.apply(lambda r: max(r["open"], r["close"]), axis=1).max()
    con_low  = lookback_4h.apply(lambda r: min(r["open"], r["close"]), axis=1).min()

    if con_low <= 0:
        return None

    range_pct = (con_high - con_low) / con_low * 100
    if range_pct > MAX_CONSOLIDATION_PCT:
        return None

    # ── CHECK 2: Breakout — 4H close > conHigh ──
    if cur_close <= con_high:
        return None

    breakout_pct = (cur_close - con_high) / con_high * 100

    # ── CHECK 3: Body size ≥ 5% ──
    if cur_open <= 0:
        return None
    body_pct = abs(cur_close - cur_open) / cur_open * 100
    if body_pct < MIN_BODY_PCT:
        return None

    # ── CHECK 4: Rel. Volume — median of last 5 4H candles ──
    last_5_4h  = df_4h.iloc[-6:-1]
    if len(last_5_4h) < 3:
        return None

    median_vol = float(np.median(last_5_4h["volume"].values))
    if median_vol <= 0:
        return None

    rel_vol = cur_volume / median_vol
    if rel_vol < MIN_REL_VOL:
        return None

    # ── CHECK 5: Liquidity — avg daily vol ≥ 500k ──
    if avg_vol_20d < MIN_AVG_DAILY_VOL:
        return None

    # ── Fetch daily data for checks 6, 7, 8 ──
    daily_close, mktcap = fetch_daily_data(symbol)
    if daily_close is None or len(daily_close) < 50:
        return None

    # ── CHECK 6: Market cap ≥ 10M ──
    if mktcap < MIN_MARKET_CAP:
        return None

    # ── CHECK 7: Price within 10% of 20d or 50d high ──
    high_20d = max(daily_close[-20:]) if len(daily_close) >= 20 else max(daily_close)
    high_50d = max(daily_close[-50:]) if len(daily_close) >= 50 else max(daily_close)

    near_20d = cur_close >= high_20d * NEAR_HIGH_PCT
    near_50d = cur_close >= high_50d * NEAR_HIGH_PCT
    if not (near_20d or near_50d):
        return None

    pct_from_high = min(
        (cur_close - high_20d) / high_20d * 100,
        (cur_close - high_50d) / high_50d * 100,
    )

    # ── CHECK 8: Trend — close > SMA20 & SMA50 ──
    sma20 = float(np.mean(daily_close[-20:]))
    sma50 = float(np.mean(daily_close[-50:]))

    if cur_close <= sma20 or cur_close <= sma50:
        return None

    # ── ALL CHECKS PASSED ✅ ──
    return {
        "symbol"        : symbol,
        "price"         : round(cur_close,     2),
        "breakout_pct"  : round(breakout_pct,  2),
        "body_pct"      : round(body_pct,      2),
        "rel_vol"       : round(rel_vol,        2),
        "pct_from_high" : round(pct_from_high,  2),
        "con_high"      : round(con_high,       2),
        "con_low"       : round(con_low,        2),
        "range_pct"     : round(range_pct,      2),
        "sma20"         : round(sma20,           2),
        "sma50"         : round(sma50,           2),
        "avg_vol_20d"   : int(avg_vol_20d),
        "median_vol"    : int(median_vol),
        "candles_4h"    : df_4h.tail(20).to_dict("records"),
    }


# ─────────────────────────────────────────────────────────────
# SINGLE STOCK
# ─────────────────────────────────────────────────────────────
def _process_single_stock(symbol, avg_vol):
    try:
        df_1h, df_4h = fetch_1h_and_4h_data(symbol)
        if df_1h is None or df_4h is None:
            return None
        return run_checks(symbol, df_1h, df_4h, avg_vol)
    except Exception as e:
        print(f"[breakout_4h_logic] {symbol} error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# PARALLEL SCAN
# ─────────────────────────────────────────────────────────────
def run_scan(all_stocks, progress_cb=None, status_cb=None):
    """
    Step 1: Fetch avg volumes from Supabase (once)
    Step 2: Parallel scan all stocks
    """
    # Fetch avg volumes once
    avg_volumes = fetch_avg_volumes()

    total     = len(all_stocks)
    results   = []
    completed = 0

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
