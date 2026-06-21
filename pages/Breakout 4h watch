"""
breakout_4h_watch.py
Consolidation Watchlist logic:
  - scan_consolidating()  → find stocks in tight consolidation zone
  - check_live_alerts()   → check LTP vs zone high using Angel WS
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
        fetch_1h_and_4h_data,
    )
except ImportError:
    from breakout_4h_config import (
        MAX_CONSOLIDATION_PCT,
        CONSOLIDATION_LOOKBACK,
        PARALLEL_WORKERS,
    )
    from breakout_4h_data import (
        fetch_1h_and_4h_data,
    )

BREAKOUT_THRESHOLD = 1.02   # 2% above zone high = breakout
NEAR_ZONE_PCT      = 0.98   # within 2% of zone high = near zone


def _scan_single_stock(symbol: str) -> dict | None:
    """
    Check if stock is consolidating (range ≤ 12%).
    Returns zone info or None.
    """
    try:
        df_1h, df_4h = fetch_1h_and_4h_data(symbol)
        if df_1h is None or df_4h is None:
            return None
        if len(df_4h) < CONSOLIDATION_LOOKBACK + 1:
            return None

        lookback_4h = df_4h.iloc[-(CONSOLIDATION_LOOKBACK + 1):-1]
        current_4h  = df_4h.iloc[-1]

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

        return {
            "symbol"    : symbol,
            "con_high"  : round(float(con_high), 2),
            "con_low"   : round(float(con_low),  2),
            "range_pct" : round(float(range_pct), 2),
            "candles_4h": df_4h.tail(20).to_dict("records"),
        }

    except Exception as e:
        print(f"[watch] {symbol} error: {e}")
        return None


def scan_consolidating(
    all_stocks  : list,
    progress_cb = None,
    status_cb   = None,
) -> list:
    """
    Scan all stocks for consolidation.
    Returns list of consolidating stocks with zone info.
    """
    total     = len(all_stocks)
    results   = []
    completed = 0

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        future_to_symbol = {
            executor.submit(_scan_single_stock, symbol): symbol
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
                print(f"[watch] {symbol} future error: {e}")

    return results


def check_live_alerts(watchlist: list, ticks: dict, name_to_token: dict) -> list:
    """
    Check live LTP vs zone high for each stock in watchlist.
    Returns enriched list with status, ltp, proximity.
    """
    enriched = []

    for stock in watchlist:
        symbol   = stock["symbol"]
        token    = name_to_token.get(symbol)
        con_high = stock["con_high"]
        con_low  = stock["con_low"]

        # Get live LTP from Angel WS
        live_data = ticks.get(token, {}) if token else {}
        ltp       = live_data.get("ltp", None)

        if ltp is None or ltp <= 0:
            ltp = con_low  # fallback

        ltp = float(ltp)

        # Calculate proximity (0-100%)
        zone_range   = con_high - con_low
        if zone_range > 0:
            proximity_pct = min(100, max(0, (ltp - con_low) / zone_range * 100))
        else:
            proximity_pct = 50

        # % to breakout
        pct_to_breakout = (ltp - con_high) / con_high * 100

        # Status
        if ltp >= con_high * BREAKOUT_THRESHOLD:
            status = "broke_out"
        elif ltp >= con_high * NEAR_ZONE_PCT:
            status = "near_zone"
        else:
            status = "watching"

        enriched.append({
            **stock,
            "ltp"            : round(ltp, 2),
            "pct_to_breakout": round(pct_to_breakout, 2),
            "proximity_pct"  : round(proximity_pct, 1),
            "status"         : status,
        })

    # Sort: broke_out first, then near_zone, then by proximity desc
    order = {"broke_out": 0, "near_zone": 1, "watching": 2}
    enriched.sort(key=lambda x: (order[x["status"]], -x["proximity_pct"]))

    return enriched
