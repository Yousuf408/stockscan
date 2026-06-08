# ══════════════════════════════════════════════════════════════════════════════
#  TRADESENTRY — yfinance_fetch.py v4.0
#  Batch of 10 parallel fetch
#  Shows failed stocks with exact reasons in scan log
#  No verbose per-stock success logs — clean output
# ══════════════════════════════════════════════════════════════════════════════

import time
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed

IST = pytz.timezone("Asia/Kolkata")

BATCH_SIZE  = 10
BATCH_PAUSE = 0.5


def fetch_candles_5min_yfinance(symbol: str, _log: list = None) -> tuple:
    """
    Returns (candles, reason)
    reason is None on success, error string on failure
    """
    try:
        import yfinance as yf
    except ImportError:
        return None, "yfinance not installed"

    yf_symbol = f"{symbol}.NS"

    try:
        ticker = yf.Ticker(yf_symbol)
        data   = ticker.history(period="25d", interval="5m")

        if data is None or data.empty:
            return None, "Symbol not found on NSE or delisted"

        rows = []
        for ts, row in data.iterrows():
            try:
                if ts.tzinfo is None:
                    ts_ist = pytz.utc.localize(ts).astimezone(IST)
                else:
                    ts_ist = ts.astimezone(IST)

                rows.append([
                    ts_ist.strftime("%Y-%m-%d %H:%M:%S"),
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row["Volume"]),
                ])
            except Exception:
                continue

        if not rows:
            return None, "Data returned but 0 valid candles parsed"

        return rows, None

    except Exception as e:
        return None, f"{str(e)[:80]}"


def fetch_all_candles_parallel(watchlist_stocks: list, _log: list = None,
                                progress_callback=None) -> dict:
    """
    Fetch all stocks in batches of 10.
    Logs only summary + failed stocks with reasons.
    """
    log         = _log if _log is not None else []
    candles_map = {}
    total       = len(watchlist_stocks)
    completed   = [0]
    failed_map  = {}   # { symbol: reason }

    batches = [
        watchlist_stocks[i:i + BATCH_SIZE]
        for i in range(0, total, BATCH_SIZE)
    ]

    for batch_num, batch in enumerate(batches):

        def fetch_one(stock):
            symbol          = stock["symbol"]
            candles, reason = fetch_candles_5min_yfinance(symbol, _log=[])
            return symbol, candles, reason

        with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            futures = {executor.submit(fetch_one, s): s for s in batch}

            for future in as_completed(futures):
                symbol, candles, reason = future.result()
                candles_map[symbol] = candles
                completed[0] += 1

                if candles is None:
                    failed_map[symbol] = reason

                if progress_callback:
                    progress_callback(completed[0], total, symbol)

        if batch_num < len(batches) - 1:
            time.sleep(BATCH_PAUSE)

    # ── Clean summary log ─────────────────────────────────────────────────────
    fetched_count = total - len(failed_map)
    log.append(f"✅ yfinance fetch complete — {fetched_count}/{total} stocks fetched")

    if failed_map:
        log.append(f"⚠️ {len(failed_map)} stocks could not be fetched:")
        for symbol, reason in failed_map.items():
            log.append(f"   ❌ {symbol} — {reason}")

    return candles_map
