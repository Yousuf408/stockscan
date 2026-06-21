"""
breakout_4h_logic.py
8 checks with dynamic filters from UI.
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
# DEFAULT FILTERS — original prompt values
# ─────────────────────────────────────────────────────────────
DEFAULT_FILTERS = {
    "consol_pct"    : 12,           # Check 1: ≤ 12%
    "breakout_mult" : 1.02,         # Check 2: 2% above
    "body_pct"      : 5.0,          # Check 3: ≥ 5%
    "rel_vol"       : 1.5,          # Check 4: 1.5×
    "daily_vol"     : 500_000,      # Check 5: 500k
    "mktcap"        : 50_000_000,   # Check 6: 50M
    "near_high"     : 10,           # Check 7: within 10%
    "trend"         : "both",       # Check 8: SMA20 & SMA50
}


# ─────────────────────────────────────────────────────────────
# 8 CHECKS
# ─────────────────────────────────────────────────────────────
def run_checks(symbol, df_1h, df_4h, avg_vol_20d=0, filters=None):

    f = {**DEFAULT_FILTERS, **(filters or {})}

    if df_4h is None or len(df_4h) < CONSOLIDATION_LOOKBACK + 2:
        return None

    lookback_4h = df_4h.iloc[-(CONSOLIDATION_LOOKBACK + 1):-1]
    current_4h  = df_4h.iloc[-1]
    cur_open    = float(current_4h["open"])
    cur_close   = float(current_4h["close"])
    cur_high    = float(current_4h["high"])
    cur_low     = float(current_4h["low"])
    cur_volume  = float(current_4h["volume"])

    # ── CHECK 1: Consolidation ──
    con_high = lookback_4h.apply(lambda r: max(r["open"], r["close"]), axis=1).max()
    con_low  = lookback_4h.apply(lambda r: min(r["open"], r["close"]), axis=1).min()

    if con_low <= 0:
        return None

    range_pct = (con_high - con_low) / con_low * 100
    if range_pct > f["consol_pct"]:
        return None

    # ── CHECK 2: Breakout ──
    if cur_close < con_high * f["breakout_mult"]:
        return None

    breakout_pct = (cur_close - con_high) / con_high * 100

    # ── CHECK 3: Body size ──
    if cur_open <= 0:
        return None
    body_pct = abs(cur_close - cur_open) / cur_open * 100
    if body_pct < f["body_pct"]:
        return None

    # ── CHECK 4: Rel. Volume — avg of prior 10 4H candles ──
    prior_10_4h = df_4h.iloc[-11:-1]
    if len(prior_10_4h) < 5:
        return None

    avg_4h_vol = float(prior_10_4h["volume"].mean())
    if avg_4h_vol <= 0:
        return None

    rel_vol = cur_volume / avg_4h_vol
    if rel_vol < f["rel_vol"]:
        return None

    # ── CHECK 5: Liquidity ──
    if avg_vol_20d < f["daily_vol"]:
        return None

    # ── Daily data for checks 6, 7, 8 ──
    daily_close, mktcap = fetch_daily_data(symbol)
    if daily_close is None or len(daily_close) < 50:
        return None

    # ── CHECK 6: Market cap ──
    if mktcap < f["mktcap"]:
        return None

    # ── CHECK 7: Price near high ──
    near_pct = f["near_high"] / 100
    high_20d  = max(daily_close[-20:]) if len(daily_close) >= 20 else max(daily_close)
    high_50d  = max(daily_close[-50:]) if len(daily_close) >= 50 else max(daily_close)

    near_20d = cur_close >= high_20d * (1 - near_pct)
    near_50d = cur_close >= high_50d * (1 - near_pct)
    if not (near_20d or near_50d):
        return None

    pct_from_high = min(
        (cur_close - high_20d) / high_20d * 100,
        (cur_close - high_50d) / high_50d * 100,
    )

    # ── CHECK 8: Trend ──
    sma20 = float(np.mean(daily_close[-20:]))
    sma50 = float(np.mean(daily_close[-50:]))

    trend = f["trend"]
    if trend == "both":
        if cur_close <= sma20 or cur_close <= sma50:
            return None
    elif trend == "sma20":
        if cur_close <= sma20:
            return None
    elif trend == "sma50":
        if cur_close <= sma50:
            return None
    # "disable" = no check

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
        "avg_4h_vol"    : int(avg_4h_vol),
        "candles_4h"    : df_4h.tail(20).to_dict("records"),
    }


# ─────────────────────────────────────────────────────────────
# SINGLE STOCK
# ─────────────────────────────────────────────────────────────
def _process_single_stock(symbol, avg_vol, filters):
    try:
        df_1h, df_4h = fetch_1h_and_4h_data(symbol)
        if df_1h is None or df_4h is None:
            return None
        return run_checks(symbol, df_1h, df_4h, avg_vol, filters)
    except Exception as e:
        print(f"[breakout_4h_logic] {symbol} error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# PARALLEL SCAN
# ─────────────────────────────────────────────────────────────
def run_scan(all_stocks, progress_cb=None, status_cb=None, filters=None):
    avg_volumes = fetch_avg_volumes()

    total     = len(all_stocks)
    results   = []
    completed = 0

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        future_to_symbol = {
            executor.submit(
                _process_single_stock,
                symbol,
                avg_volumes.get(symbol, 0),
                filters,
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
