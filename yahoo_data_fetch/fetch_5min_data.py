"""
fetch_5min_data.py
-------------------
Fetches 5-minute interval historical OHLCV data from Yahoo Finance
for every stock listed in stocks.txt, and saves one CSV per stock
inside the output/ folder.

WHY THIS EXISTS
----------------
TradeSentry's momentum scanner computes vol_ratio using a FULL-DAY
median volume as the baseline, compared against a CUMULATIVE volume
that is still building up in the first hour of trading. This causes
signals to fire late (after price has already moved 3-5%+).

To fix this properly, we need a "typical cumulative volume by time
of day" baseline -- e.g. "by 9:35 AM, this stock usually has traded
X shares over the last N days". That requires historical 5-min
candle data, which Yahoo Finance provides for the last ~60 days.

This script downloads that raw 5-min data so it can be used offline
to build the time-of-day baseline and backtest whether it actually
reduces signal lag (compare against the current 5-day full-day-median
approach).

USAGE
-----
    pip install -r requirements.txt
    python fetch_5min_data.py

Optional flags:
    python fetch_5min_data.py --period 60d --interval 5m --sleep 1.5

OUTPUT
------
    output/<STOCK>.csv          -- one file per stock, raw 5-min OHLCV
    output/_fetch_summary.csv   -- success/failure log for every symbol
    output/_combined_daily_cumvol.csv
                                 -- convenience file: cumulative volume
                                    per stock per date per 5-min bucket
                                    (this is the actual input needed for
                                    the time-of-day baseline analysis)

NOTES
-----
- Yahoo Finance only retains 5-minute interval data for ~60 calendar
  days. You will NOT get data older than that -- this is a Yahoo
  limitation, not a bug in this script.
- NSE stocks are suffixed with ".NS" automatically. If a symbol fails
  because it's actually a BSE-only listing, check _fetch_summary.csv
  and manually retry with ".BO" suffix for those specific symbols.
- The script sleeps between requests to avoid Yahoo rate-limiting.
  With ~250 stocks and a 1.2s sleep, expect this to take ~6-8 minutes.
- Re-running the script skips stocks that already have a CSV in
  output/, so you can safely resume after an interruption.
"""

import argparse
import sys
import time
import random
from pathlib import Path

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    print("yfinance not installed. Run: pip install -r requirements.txt")
    sys.exit(1)


STOCKS_FILE = Path("stocks.txt")
OUTPUT_DIR = Path("output")
SUMMARY_FILE = OUTPUT_DIR / "_fetch_summary.csv"
COMBINED_FILE = OUTPUT_DIR / "_combined_daily_cumvol.csv"

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5


def load_stock_list(path: Path) -> list:
    if not path.exists():
        print(f"ERROR: {path} not found. Put stocks.txt next to this script.")
        sys.exit(1)
    with open(path, "r") as f:
        stocks = [line.strip() for line in f if line.strip()]
    return stocks


def fetch_one_stock(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """
    Fetch 5-min data for a single NSE stock with retries.
    Returns an empty DataFrame if all retries fail.
    """
    ticker = f"{symbol}.NS"
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval)
            if df is not None and not df.empty:
                df = df.reset_index()
                # yfinance names the datetime column "Datetime" for intraday data
                dt_col = "Datetime" if "Datetime" in df.columns else df.columns[0]
                df = df.rename(columns={dt_col: "datetime"})
                df["stock"] = symbol
                return df
            else:
                last_error = "empty response"
        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    print(f"  FAILED: {symbol} -> {last_error}")
    return pd.DataFrame()


def build_cumulative_volume(df: pd.DataFrame) -> pd.DataFrame:
    """
    Given raw 5-min OHLCV for one stock, adds:
      - date (calendar date)
      - time (HH:MM, IST as returned by Yahoo for .NS tickers)
      - cum_volume (running total volume for that trading day)
    This is the format needed to build a "typical volume by time
    of day" baseline later.
    """
    if df.empty:
        return df

    out = df.copy()
    out["datetime"] = pd.to_datetime(out["datetime"])
    out["date"] = out["datetime"].dt.date
    out["time"] = out["datetime"].dt.strftime("%H:%M")
    out = out.sort_values(["date", "datetime"])
    out["cum_volume"] = out.groupby("date")["Volume"].cumsum()

    return out[["stock", "date", "time", "Open", "High", "Low", "Close", "Volume", "cum_volume"]]


def main():
    parser = argparse.ArgumentParser(description="Fetch 5-min Yahoo Finance data for TradeSentry backtesting")
    parser.add_argument("--period", default="60d", help="How far back to fetch (Yahoo max for 5m data is 60d)")
    parser.add_argument("--interval", default="5m", help="Candle interval (default 5m)")
    parser.add_argument("--sleep", type=float, default=1.2, help="Seconds to sleep between requests")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    stocks = load_stock_list(STOCKS_FILE)
    print(f"Loaded {len(stocks)} stocks from {STOCKS_FILE}")

    summary_rows = []
    combined_frames = []

    for i, symbol in enumerate(stocks, start=1):
        out_path = OUTPUT_DIR / f"{symbol}.csv"

        if out_path.exists():
            print(f"[{i}/{len(stocks)}] {symbol} -> already fetched, skipping")
            existing = pd.read_csv(out_path)
            combined_frames.append(existing)
            summary_rows.append({"stock": symbol, "status": "skipped_existing", "rows": len(existing)})
            continue

        print(f"[{i}/{len(stocks)}] Fetching {symbol}...")
        raw = fetch_one_stock(symbol, args.period, args.interval)

        if raw.empty:
            summary_rows.append({"stock": symbol, "status": "failed", "rows": 0})
            continue

        processed = build_cumulative_volume(raw)
        processed.to_csv(out_path, index=False)
        combined_frames.append(processed)
        summary_rows.append({"stock": symbol, "status": "success", "rows": len(processed)})

        # polite delay + small jitter to avoid Yahoo rate-limiting
        time.sleep(args.sleep + random.uniform(0, 0.5))

    # Write summary
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(SUMMARY_FILE, index=False)

    ok = (summary_df["status"].isin(["success", "skipped_existing"])).sum()
    failed = (summary_df["status"] == "failed").sum()
    print(f"\nDone. {ok}/{len(stocks)} succeeded, {failed} failed.")
    print(f"Summary saved to: {SUMMARY_FILE}")

    # Write combined file (useful for the baseline-building step later)
    if combined_frames:
        combined = pd.concat(combined_frames, ignore_index=True)
        combined.to_csv(COMBINED_FILE, index=False)
        print(f"Combined file saved to: {COMBINED_FILE} ({len(combined)} rows)")

    if failed:
        print("\nFailed symbols (check if they need .BO suffix instead of .NS):")
        print(summary_df[summary_df["status"] == "failed"]["stock"].tolist())


if __name__ == "__main__":
    main()
