"""
momentum/delivery.py
Fetches NSE Delivery % from the official daily MTO archive file.
Mirrors the working Google Apps Script logic — same URL, same parsing.

Source: https://archives.nseindia.com/archives/equities/mto/MTO_DDMMYYYY.DAT
This is NSE's static archive server (not the protected nseindia.com API),
so it does NOT need cookies / session handling like nseindia.com does.
"""

import requests
from datetime import datetime, timedelta
from functools import lru_cache

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

MTO_BASE_URL = "https://archives.nseindia.com/archives/equities/mto/MTO_{dd}{mm}{yyyy}.DAT"


def _build_url(date_obj: datetime) -> str:
    return MTO_BASE_URL.format(
        dd=f"{date_obj.day:02d}",
        mm=f"{date_obj.month:02d}",
        yyyy=date_obj.year,
    )


def fetch_delivery_pct_for_date(date_obj: datetime, timeout: int = 10) -> dict:
    """
    Fetch delivery % for ALL NSE stocks for a single date.
    Returns: { "SYMBOL": "63.45", ... }   (string, as NSE provides it)
    Returns {} on holiday / weekend / file-not-found / network error.
    """
    url = _build_url(date_obj)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return {}
        delivery_map = {}
        for line in resp.text.splitlines():
            row = line.strip()
            if not row.startswith("20,"):
                continue
            parts = row.split(",")
            if len(parts) < 7:
                continue
            symbol = parts[2].strip().upper()
            delivery_pct = parts[6].strip()
            delivery_map[symbol] = delivery_pct
        return delivery_map
    except Exception:
        return {}


@lru_cache(maxsize=8)
def _cached_fetch(date_str: str) -> tuple:
    """Internal cache wrapper — lru_cache needs hashable args."""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    result = fetch_delivery_pct_for_date(d)
    return tuple(result.items())  # tuple so it's hashable/cacheable


def get_delivery_pct_map(date_obj: datetime = None) -> dict:
    """
    Public function — cached per date (process lifetime).
    If date_obj is None, uses yesterday (since today's EOD data
    isn't published by NSE until after market close + processing).
    """
    if date_obj is None:
        date_obj = datetime.now() - timedelta(days=1)
    date_str = date_obj.strftime("%Y-%m-%d")
    return dict(_cached_fetch(date_str))


def get_latest_available_delivery_pct(max_lookback_days: int = 5) -> tuple:
    """
    Walks backward from yesterday until it finds a valid trading-day file
    (skips weekends/holidays automatically since those files won't exist).
    Returns: (delivery_map: dict, date_used: datetime | None)
    """
    for back in range(1, max_lookback_days + 1):
        d = datetime.now() - timedelta(days=back)
        m = get_delivery_pct_map(d)
        if m:
            return m, d
    return {}, None
