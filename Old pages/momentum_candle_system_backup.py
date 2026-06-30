"""
momentum_candle_system_backup.py
═══════════════════════════════════════════════════════════════════
BACKUP — Unified Candle System (9 EMA + Phase + Vol Trend)
Removed from live app on 2026-06-30 due to performance concerns —
process_candles() was looping over every stock on every 5-second
fragment refresh, calculating EMA9 + phase detection per stock.
This was the source of continuous lag during live market hours.

Everything needed to bring this feature back is in this single file.
Nothing was deleted from momentum/backend.py — those functions are
still there and untouched. This file just preserves the INTEGRATION
code that was removed from pages/8_MomentumScanner.py and the
renderer.py table columns that displayed it.
═══════════════════════════════════════════════════════════════════

HOW TO RE-ACTIVATE (when ready):

1. In pages/8_MomentumScanner.py:
   - Add back the imports block (Section A below) to the
     `from momentum.backend import (...)` statement.
   - Add back the session-state + process_candles() function
     (Section B below) right after the EMA20 cache function.
   - Add back the process_candles() call inside scanner_table()
     (Section C below), right after `ema_cache = get_ema20_status(df)`.
   - Add back the 4 display column assignments (Section D below).

2. In momentum/renderer.py:
   - Add back the 3 <th> headers and matching <td> cells
     (Section E below) — table headers + symbol-name var usage.

3. Reboot the Streamlit app.

═══════════════════════════════════════════════════════════════════
SECTION A — Imports (add to momentum.backend import block)
═══════════════════════════════════════════════════════════════════
"""

IMPORTS_TO_ADD = """
    # ╔═══════════════════════════════════════════════════════════╗
    # ║  UNIFIED CANDLE SYSTEM SECTION START — imports            ║
    # ╚═══════════════════════════════════════════════════════════╝
    fetch_initial_candles_yahoo,
    build_ws_candle,
    append_candle_and_save,
    save_initial_candles_to_db,
    calculate_ema9_with_live,
    detect_phase_and_trend,
    update_phase_in_supabase,
    # ╔═══════════════════════════════════════════════════════════╗
    # ║  UNIFIED CANDLE SYSTEM SECTION END                        ║
    # ╚═══════════════════════════════════════════════════════════╝
"""

"""
═══════════════════════════════════════════════════════════════════
SECTION B — Session-state + process_candles() function
(Place this right after get_ema20_status() in 8_MomentumScanner.py)
═══════════════════════════════════════════════════════════════════
"""

SECTION_B_CODE = '''
# ╔═══════════════════════════════════════════════════════════════╗
# ║  UNIFIED CANDLE SYSTEM — SESSION STATE                        ║
# ║  candle_cache: { stock: [candle1...candle9] } in RAM          ║
# ║  DB (candles jsonb) = persistent across page refresh           ║
# ║  Flow:                                                         ║
# ║  1. Signal detected → Yahoo 8 candles → background thread     ║
# ║  2. Every 5 min → WS candle built → append DB + RAM           ║
# ║  3. Every 5 sec → live LTP + candles → EMA9 + Phase           ║
# ║  4. Page refresh → DB candles → instant restore                ║
# ╚═══════════════════════════════════════════════════════════════╝

import threading

def get_candle_cache() -> dict:
    """Get or init candle cache from session state."""
    if "candle_cache" not in st.session_state:
        st.session_state["candle_cache"] = {}
    return st.session_state["candle_cache"]


def _yahoo_fetch_worker(stocks: list, supabase, today_str: str, candle_cache: dict):
    """
    Background thread — fetch Yahoo candles without blocking fragment.
    Writes directly into candle_cache (shared dict reference).
    """
    try:
        yahoo_data = fetch_initial_candles_yahoo(stocks)
        for stock, candles in yahoo_data.items():
            if candles:
                candle_cache[stock] = candles
                save_initial_candles_to_db(supabase, stock, today_str, candles)
    except Exception:
        pass


def process_candles(supabase, df, signal_data: dict,
                    live_ticks: dict, token_to_name: dict,
                    today_str: str) -> tuple:
    """
    Unified function — handles candles, EMA9, Phase, Vol Trend.
    Yahoo fetch runs in background thread — no blur/block.

    Returns:
      ema9_results  : { stock: { ema9, distance, status, signal } }
      phase_results : { stock: { phase, vol_trend } }

    ⚠️ PERFORMANCE NOTE: This loops over every stock in `df` on
    every fragment refresh (run_every=5). For 90+ stocks this is
    90+ EMA calculations + 90+ phase detections every 5 seconds.
    If re-enabling, consider:
      - Only run for stocks visible after filters (client-side
        filtering currently means backend has no visibility into
        what's filtered — would need filter state synced back).
      - Increase run_every for this specific computation block
        (e.g. only recompute every 3rd fragment cycle = ~15s).
      - Vectorize with pandas instead of the per-symbol Python loop.
    """
    from datetime import datetime as dt

    now          = dt.now(IST)
    current_slot = (now.minute // 5) * 5
    slot_str     = now.strftime(f"%H:{current_slot:02d}")

    # ── Init slot tracking ────────────────────────────────────
    if "candle_slot"         not in st.session_state:
        st.session_state["candle_slot"]         = -1
    if "tick_buffer"         not in st.session_state:
        st.session_state["tick_buffer"]         = {}
    if "yahoo_fetching"      not in st.session_state:
        st.session_state["yahoo_fetching"]      = set()

    candle_cache  = get_candle_cache()
    name_to_token = {v: k for k, v in token_to_name.items()}
    do_ws_candle  = st.session_state["candle_slot"] != current_slot

    # ── Step 1: On new 5min slot → build WS candle + append ──
    if do_ws_candle:
        prev_buffer = st.session_state["tick_buffer"]
        for stock, ticks in prev_buffer.items():
            if stock not in candle_cache:
                continue
            new_candle = build_ws_candle(slot_str, ticks)
            if new_candle:
                candle_cache[stock] = append_candle_and_save(
                    supabase, stock, today_str,
                    candle_cache[stock], new_candle
                )
        st.session_state["tick_buffer"] = {}
        st.session_state["candle_slot"] = current_slot

    # ── Step 2: Accumulate current ticks ──────────────────────
    for token, tick in live_ticks.items():
        stock  = token_to_name.get(token)
        if not stock:
            continue
        ltp    = float(tick.get("ltp",    0))
        volume = float(tick.get("volume", 0))
        if ltp <= 0:
            continue
        buf = st.session_state["tick_buffer"].get(stock, [])
        buf.append({"ltp": ltp, "volume": volume})
        st.session_state["tick_buffer"][stock] = buf

    # ── Step 3: For each scan stock — ensure candles exist ────
    stocks  = df["Symbol"].tolist()
    missing = [s for s in stocks if s not in candle_cache]

    if missing:
        # Try DB first (page refresh case) — instant, no network call
        for stock in missing:
            sig        = signal_data.get(stock, {})
            db_candles = sig.get("candles", None)
            if db_candles and len(db_candles) >= 2:
                candle_cache[stock] = db_candles

        # Still missing → background thread (no blur!)
        still_missing = [
            s for s in missing
            if s not in candle_cache
            and s not in st.session_state["yahoo_fetching"]
        ]
        if still_missing:
            # Mark as fetching so we don't spawn duplicate threads
            st.session_state["yahoo_fetching"].update(still_missing)
            t = threading.Thread(
                target = _yahoo_fetch_worker,
                args   = (still_missing, supabase, today_str, candle_cache),
                daemon = True,
            )
            t.start()
            # Clean up fetching set after thread completes
            def _cleanup(stocks_to_clean=still_missing):
                t.join()
                for s in stocks_to_clean:
                    st.session_state["yahoo_fetching"].discard(s)
            threading.Thread(target=_cleanup, daemon=True).start()

    # ── Step 4: Calculate EMA9 + Phase for all stocks ─────────
    ema9_results  = {}
    phase_results = {}
    do_phase_update = do_ws_candle

    for symbol in stocks:
        candles  = candle_cache.get(symbol, [])
        token    = name_to_token.get(symbol)
        live_ltp = 0.0
        if token and token in live_ticks:
            live_ltp = float(live_ticks[token].get("ltp", 0))

        # ── EMA9 ──────────────────────────────────────────────
        if candles and live_ltp > 0:
            ema9_data = calculate_ema9_with_live(candles, live_ltp)
            ema9_results[symbol] = ema9_data if ema9_data else {
                "ema9": None, "distance": None, "status": "⚠️ N/A", "signal": ""
            }
        else:
            ema9_results[symbol] = {
                "ema9": None, "distance": None,
                "status": "⏳" if not candles else "⚠️ N/A", "signal": ""
            }

        # ── Phase + Vol Trend ──────────────────────────────────
        if len(candles) >= 2:
            phase, vol_trend = detect_phase_and_trend(candles)
            phase_results[symbol] = {"phase": phase, "vol_trend": vol_trend}
            if do_phase_update and symbol in signal_data:
                try:
                    update_phase_in_supabase(
                        supabase, symbol, today_str, phase, vol_trend
                    )
                except Exception:
                    pass
        else:
            sig = signal_data.get(symbol, {})
            phase_results[symbol] = {
                "phase"    : sig.get("phase",     "⏳ Forming"),
                "vol_trend": sig.get("vol_trend", "→ Stable"),
            }

    return ema9_results, phase_results

# ╔═══════════════════════════════════════════════════════════════╗
# ║  UNIFIED CANDLE SYSTEM SECTION END                            ║
# ╚═══════════════════════════════════════════════════════════════╝
'''

"""
═══════════════════════════════════════════════════════════════════
SECTION C — process_candles() call inside scanner_table()
(Place right after `ema_cache = get_ema20_status(df)`)
═══════════════════════════════════════════════════════════════════
"""

SECTION_C_CODE = '''
    # ╔═══════════════════════════════════════════════════════════╗
    # ║  UNIFIED CANDLE SYSTEM — EMA9 + Phase + Vol Trend         ║
    # ╚═══════════════════════════════════════════════════════════╝
    ema9_cache, phase_cache = process_candles(
        supabase      = supabase,
        df            = df,
        signal_data   = signal_data,
        live_ticks    = angel_ws.latest_ticks,
        token_to_name = TOKEN_TO_NAME,
        today_str     = today,
    )
    # ╔═══════════════════════════════════════════════════════════╗
    # ║  UNIFIED CANDLE SYSTEM SECTION END                        ║
    # ╚═══════════════════════════════════════════════════════════╝
'''

"""
═══════════════════════════════════════════════════════════════════
SECTION D — Display column assignments
(Place alongside the other df["..."] = ... lines)
═══════════════════════════════════════════════════════════════════
"""

SECTION_D_CODE = '''
    df["EMA9 5min"]  = df["Symbol"].apply(lambda s: ema9_cache.get(s, {}).get("status", "⏳"))
    df["EMA9 Value"] = df["Symbol"].apply(lambda s: ema9_cache.get(s, {}).get("ema9", None))
    df["Phase"]      = df["Symbol"].apply(lambda s: phase_cache.get(s, {}).get("phase", "⏳ Forming"))
    df["Vol Trend"]  = df["Symbol"].apply(lambda s: phase_cache.get(s, {}).get("vol_trend", "→ Stable"))
'''

"""
═══════════════════════════════════════════════════════════════════
SECTION E — renderer.py table columns (headers + cells)
═══════════════════════════════════════════════════════════════════
Add back these <th> in the thead (after "EMA20 Status"):

    <th onclick="tsColHighlight(6)">9 EMA 5min</th>
    <th onclick="tsColHighlight(7)">Phase</th>
    <th onclick="tsColHighlight(8)">Vol Trend</th>

  (Remember to renumber tsColHighlight() indices for any columns
   that come after these three, since removing them shifts indices.)

Add back these <td> in the row loop (after the EMA20 <td>):

    <td>{_ema9_cell(str(row.get('EMA9 5min', '⏳')), row.get('EMA9 Value', None))}</td>
    <td>{_phase_cell(str(row.get('Phase', '⏳ Forming')))}</td>
    <td>{_vol_trend_cell(str(row.get('Vol Trend', '→ Stable')))}</td>

The helper functions _ema9_cell(), _phase_cell(), _vol_trend_cell()
were NOT removed from renderer.py — they're still defined there,
just unused. So this is the only renderer change needed.
═══════════════════════════════════════════════════════════════════
"""
