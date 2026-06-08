# ══════════════════════════════════════════════════════════════════════════════
#  TRADESENTRY — yfinance_fetch.py v3.0
#  Batch of 10 parallel fetch — reliable, no rate limit issues
#  No AngelOne fallback — keeps scan fast
# ══════════════════════════════════════════════════════════════════════════════

import time
import pytz
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

IST = pytz.timezone("Asia/Kolkata")

BATCH_SIZE  = 10    # fetch 10 stocks in parallel at a time
BATCH_PAUSE = 0.5   # seconds pause between batches


def fetch_candles_5min_yfinance(symbol: str, _log: list = None) -> list:
    """Single stock fetch from yfinance"""
    log = _log if _log is not None else []

    try:
        import yfinance as yf
    except ImportError:
        log.append(f"❌ [{symbol}] yfinance not installed")
        return None

    yf_symbol = f"{symbol}.NS"

    try:
        ticker = yf.Ticker(yf_symbol)
        data   = ticker.history(period="25d", interval="5m")

        if data is None or data.empty:
            log.append(f"⚠️ [{symbol}] No data from yfinance")
            return None

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
            log.append(f"⚠️ [{symbol}] 0 candles parsed")
            return None

        return rows

    except Exception as e:
        log.append(f"❌ [{symbol}] yfinance error: {e}")
        return None


def fetch_all_candles_parallel(watchlist_stocks: list, _log: list = None,
                                progress_callback=None) -> dict:
    """
    Fetch all stocks in batches of 10 parallel workers.
    More reliable than fetching all at once.
    Returns dict: { "SYMBOL": candles_list }
    """
    log         = _log if _log is not None else []
    candles_map = {}
    total       = len(watchlist_stocks)
    completed   = [0]
    failed      = []

    # Split into batches of 10
    batches = [
        watchlist_stocks[i:i + BATCH_SIZE]
        for i in range(0, total, BATCH_SIZE)
    ]

    log.append(f"📦 Fetching {total} stocks in {len(batches)} batches of {BATCH_SIZE}")

    for batch_num, batch in enumerate(batches):

        def fetch_one(stock):
            symbol  = stock["symbol"]
            candles = fetch_candles_5min_yfinance(symbol, _log=log)
            return symbol, candles

        with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
            futures = {executor.submit(fetch_one, s): s for s in batch}

            for future in as_completed(futures):
                symbol, candles = future.result()
                candles_map[symbol] = candles
                completed[0] += 1

                if candles is None:
                    failed.append(symbol)

                if progress_callback:
                    progress_callback(completed[0], total, symbol)

        # Pause between batches — gives yfinance breathing room
        if batch_num < len(batches) - 1:
            time.sleep(BATCH_PAUSE)

    fetched_count = len([v for v in candles_map.values() if v is not None])
    failed_count  = len(failed)

    if failed:
        log.append(f"⚠️ {failed_count} stocks failed yfinance: {', '.join(failed)}")

    return candles_map
