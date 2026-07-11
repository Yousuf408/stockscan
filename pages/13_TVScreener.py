import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import pytz
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from supabase import create_client

# ─────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TV Screener · TradeSentry",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────────────────────
# STYLES & SIDEBAR
# ─────────────────────────────────────────────────────────────
from styles import apply_styles, sidebar_brand
apply_styles()
sidebar_brand("TVScreener")

st.markdown("""
<style>
.block-container { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; }
div[data-testid="stSelectbox"] { margin-top: 0 !important; margin-bottom: 0 !important; }
div[data-testid="stButton"] button { padding: 4px 12px !important; font-size: 12px !important; height: 32px !important; }
div[data-testid="stVerticalBlock"] { gap: 0.3rem !important; }
</style>
""", unsafe_allow_html=True)

IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────────────────────
# SUPABASE CLIENT — same project/keys jo Momentum/Breakout Scanner
# mein use ho rahe hain
# ─────────────────────────────────────────────────────────────
SUPABASE_URL = "https://atyqkbrmrosnoczktsmm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImF0eXFrYnJtcm9zbm9jemt0c21tIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1NjI4ODcsImV4cCI6MjA5NjEzODg4N30.f-vn85HGFfPMUNeyJLccZSIVTKvZGXp1Ty5Hw08pFsU"

@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()

# ─────────────────────────────────────────────────────────────
# MARKET HOURS GATE — 9:15 AM - 3:30 PM IST
# Jaisa Momentum Scanner mein hai: naya calculation/save sirf
# market-hours ke andar, market band hone pe poori tarah read-only.
# ─────────────────────────────────────────────────────────────
def is_market_hours():
    now = datetime.now(IST)
    market_open  = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= now <= market_close

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def get_trading_day_before(date):
    candidate = date - timedelta(days=1)
    attempts = 0
    while attempts < 10:
        if candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
            attempts += 1
            continue
        try:
            test_df = yf.download("^NSEI", start=candidate, end=candidate + timedelta(days=1),
                                  interval="1d", progress=False, auto_adjust=True)
            if not test_df.empty:
                return candidate
        except:
            pass
        candidate -= timedelta(days=1)
        attempts += 1
    candidate = date - timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate

def get_last_trading_day():
    now = datetime.now(IST)
    today = now.date()
    # Market abhi khula nahi (9:15 AM se pehle) — toh "aaj" ko bhi
    # "not yet trading" treat karo, ek din peeche shift karo
    if now.hour < 9 or (now.hour == 9 and now.minute < 15):
        today = today - timedelta(days=1)
    tv_ref = get_trading_day_before(today + timedelta(days=1))
    poc_date = get_trading_day_before(tv_ref)
    return poc_date

def get_current_ist_time():
    return datetime.now(IST)

# ─────────────────────────────────────────────────────────────
# SUPABASE CACHE — read/write for tv_screener_cache table
# Persistent version of session_state cache: (symbol + calc_date)
# → poc/prev_high/ema/vol5d/crossover, survives across app restarts.
# ─────────────────────────────────────────────────────────────
def supabase_get_cached_row(symbol, calc_date):
    """
    Supabase se ek row fetch karo agar (symbol, calc_date) already save hai.
    Returns dict, ya None agar nahi mila.
    """
    try:
        result = (supabase.table("tv_screener_cache")
                  .select("poc_value, prev_high_val, ema_coil_pct, vol5d_median, crossover_status")
                  .eq("symbol", symbol)
                  .eq("calc_date", calc_date.isoformat())
                  .limit(1)
                  .execute())
        if result.data and len(result.data) > 0:
            return result.data[0]
        return None
    except:
        return None


def supabase_get_all_for_date(calc_date):
    """
    Saare stocks ka data ek saath fetch karo ek calc_date ke liye —
    market-band read-only mode mein use hota hai (poori table ek
    hi Supabase call mein mil jati hai, per-symbol calls nahi).
    Returns dict: {symbol: {poc_value, prev_high_val, ema_coil_pct,
                             vol5d_median, crossover_status}, ...}
    """
    try:
        result = (supabase.table("tv_screener_cache")
                  .select("symbol, poc_value, prev_high_val, ema_coil_pct, vol5d_median, crossover_status")
                  .eq("calc_date", calc_date.isoformat())
                  .execute())
        if result.data:
            return {row['symbol']: row for row in result.data}
        return {}
    except:
        return {}


def supabase_save_row(symbol, signal_date, calc_date, poc_value=None, prev_high_val=None,
                       ema_coil_pct=None, vol5d_median=None, crossover_status=None):
    """
    (symbol, calc_date) ke liye row upsert karo — agar already hai toh
    update, warna naya insert. Ab hamesha call hoti hai (market-hours-
    gate hata diya gaya hai), chahe market khula ho ya band.

    IMPORTANT: Supabase ka upsert() poori row REPLACE karta hai un
    columns ke liye jo payload mein missing hain (merge nahi karta
    apne-aap) — isliye pehle EXISTING row fetch karke merge karte
    hain, taaki partial-save se dusre fields accidentally NULL na
    ho jayein.
    """
    try:
        # Pehle existing row fetch karo (agar hai) — taaki merge kar sakein
        existing = None
        try:
            result = (supabase.table("tv_screener_cache")
                      .select("poc_value, prev_high_val, ema_coil_pct, vol5d_median, crossover_status")
                      .eq("symbol", symbol)
                      .eq("calc_date", calc_date.isoformat())
                      .limit(1)
                      .execute())
            if result.data and len(result.data) > 0:
                existing = result.data[0]
        except:
            existing = None

        # Merge: naya value diya gaya hai toh woh use karo, warna existing (agar hai) rakho
        def merged(new_val, key):
            if new_val is not None:
                return new_val
            if existing is not None:
                return existing.get(key)
            return None

        payload = {
            "symbol"          : symbol,
            "signal_date"      : signal_date.isoformat(),
            "calc_date"        : calc_date.isoformat(),
            "poc_value"        : merged(poc_value, "poc_value"),
            "prev_high_val"    : merged(prev_high_val, "prev_high_val"),
            "ema_coil_pct"     : merged(ema_coil_pct, "ema_coil_pct"),
            "vol5d_median"     : merged(vol5d_median, "vol5d_median"),
            "crossover_status" : merged(crossover_status, "crossover_status"),
        }

        supabase.table("tv_screener_cache").upsert(payload, on_conflict="symbol,calc_date").execute()
        if 'supabase_save_success_count' not in st.session_state:
            st.session_state['supabase_save_success_count'] = 0
        st.session_state['supabase_save_success_count'] += 1
    except Exception as e:
        if 'supabase_save_errors' not in st.session_state:
            st.session_state['supabase_save_errors'] = []
        st.session_state['supabase_save_errors'].append(f"{symbol}: {e}")
        pass  # Supabase save fail ho toh bhi app chalti rahe — session cache fallback hai

# ─────────────────────────────────────────────────────────────
# POC (Point of Control) — kal ka Fixed Range Volume Profile
# Bins-based approach: har candle ka volume price-bins mein
# distribute karo, jis bin mein sabse zyada volume ho wahi POC
# ─────────────────────────────────────────────────────────────
def calculate_poc_from_df(df_day, num_bins=50):
    price_min = df_day['Low'].min()
    price_max = df_day['High'].max()
    if price_max <= price_min:
        return None

    bins = np.linspace(price_min, price_max, num_bins + 1)
    bin_volumes = np.zeros(num_bins)

    for _, row in df_day.iterrows():
        low, high, vol = row['Low'], row['High'], row['Volume']
        if high == low:
            idx = np.digitize(low, bins) - 1
            idx = min(max(idx, 0), num_bins - 1)
            bin_volumes[idx] += vol
            continue
        for i in range(num_bins):
            bin_low, bin_high = bins[i], bins[i+1]
            overlap = min(high, bin_high) - max(low, bin_low)
            if overlap > 0:
                proportion = overlap / (high - low)
                bin_volumes[i] += vol * proportion

    bin_centers = (bins[:-1] + bins[1:]) / 2
    poc_idx = np.argmax(bin_volumes)
    return round(float(bin_centers[poc_idx]), 2)


def fetch_poc_once(symbol, num_bins=50):
    """Ek single POC fetch attempt — kal ke poore din ka data leke."""
    try:
        last_day = get_last_trading_day()
        ticker = symbol + ".NS"
        df = yf.download(ticker, start=last_day, end=last_day + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        df = df.between_time("09:15", "15:30")
        if df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return calculate_poc_from_df(df, num_bins=num_bins)
    except:
        return None


def get_yesterday_poc(symbol, num_bins=50, max_attempts=3, tolerance_pct=0.5):
    """
    Retry-and-verify POC fetch — kabhi kabhi yfinance ka historical
    data thoda shift ho jata hai fetch-to-fetch. Isliye 2 consecutive
    fetches lete hain, agar match karein (tolerance ke andar) tabhi
    accept karte hain — warna retry karte hain max_attempts tak.
    """
    prev_val = None
    for attempt in range(max_attempts):
        current_val = fetch_poc_once(symbol, num_bins=num_bins)
        if current_val is None:
            return None
        if prev_val is not None:
            diff_pct = abs(current_val - prev_val) / prev_val * 100 if prev_val else 0
            if diff_pct <= tolerance_pct:
                return current_val  # Do consecutive fetches match — stable value
        prev_val = current_val
        if attempt < max_attempts - 1:
            time.sleep(2)  # thoda ruk ke dobara try karo
    return prev_val  # Match nahi hua, but jo aakhri mila woh return karo

# ─────────────────────────────────────────────────────────────
# CANDLE CHECK — Entry Signal (STANDALONE — POC/ATP pe depend nahi karta)
# Sirf aaj ki specific 5min candle ka Close > Open check karta hai
# ─────────────────────────────────────────────────────────────
def get_candle_signal(symbol, candle_time_str):
    try:
        today = datetime.now(IST).date()
        ticker = symbol + ".NS"
        df = yf.download(ticker, start=today, end=today + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return ""
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        df_candle = df.between_time(candle_time_str, candle_time_str)
        if df_candle.empty:
            return ""
        row = df_candle.iloc[0]
        open_  = float(row['Open'].values[0] if hasattr(row['Open'], 'values') else row['Open'])
        close_ = float(row['Close'].values[0] if hasattr(row['Close'], 'values') else row['Close'])
        return "green" if close_ > open_ else ""
    except:
        return ""

# ─────────────────────────────────────────────────────────────
# CANDLE CHECK — Entry Signal, OPTIMIZED (single fetch for all 3)
# Same logic jaisa get_candle_signal() — Close > Open check —
# bas ek hi yfinance call se 9:40/9:45/9:50 teeno nikalta hai,
# har candle ke liye alag call karne ki jagah. Poora din ka data
# ek baar fetch hota hai, phir teeno candles usi se filter hoti hain.
# ─────────────────────────────────────────────────────────────
def get_all_candle_signals(symbol):
    """
    Returns dict: {"09:40": "green"/"", "09:45": "green"/"", "09:50": "green"/""}
    Ek hi yfinance call se saare teen candle-checks — 3x fetches ki
    jagah sirf 1x fetch per stock.
    """
    result = {"09:40": "", "09:45": "", "09:50": ""}
    try:
        today = datetime.now(IST).date()
        ticker = symbol + ".NS"
        df = yf.download(ticker, start=today, end=today + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return result
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)

        for candle_time_str in ["09:40", "09:45", "09:50"]:
            df_candle = df.between_time(candle_time_str, candle_time_str)
            if df_candle.empty:
                continue
            row = df_candle.iloc[0]
            open_  = float(row['Open'].values[0] if hasattr(row['Open'], 'values') else row['Open'])
            close_ = float(row['Close'].values[0] if hasattr(row['Close'], 'values') else row['Close'])
            result[candle_time_str] = "green" if close_ > open_ else ""
        return result
    except:
        return result

# ─────────────────────────────────────────────────────────────
# EMA CONSOLIDATION — "EMA Coil" check
# Kal ke poore din (5min candles) mein kitne % candles ka
# Close, 20 EMA ke ±0.5% range ke andar tha. 2 din ka data
# (kal + parso) lekar EMA warm-up karte hain, phir sirf
# kal ke candles pe % nikalte hain.
# ─────────────────────────────────────────────────────────────
def get_ema_consolidation_pct(symbol, ema_span=20, tolerance_pct=0.5):
    try:
        last_day = get_last_trading_day()
        day_before = get_trading_day_before(last_day)
        ticker = symbol + ".NS"
        df = yf.download(ticker, start=day_before, end=last_day + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.between_time("09:15", "15:30")
        if df.empty:
            return None

        df['EMA'] = df['Close'].ewm(span=ema_span, adjust=False).mean()

        # Sirf "last_day" (kal) ke candles filter karo — day_before sirf warm-up ke liye tha
        df_yesterday = df[df.index.date == last_day]
        if df_yesterday.empty:
            return None

        diff_pct = ((df_yesterday['Close'] - df_yesterday['EMA']).abs() / df_yesterday['EMA']) * 100
        near_ema_count = (diff_pct <= tolerance_pct).sum()
        total_count = len(df_yesterday)
        if total_count == 0:
            return None
        return round((near_ema_count / total_count) * 100, 1)
    except:
        return None

# ─────────────────────────────────────────────────────────────
# CROSSOVER SIGNAL — 9 EMA cross 20 EMA (bullish) + candle close
# > POC. 9:15 candle mein teesri condition bhi hai: candle body
# >= 70% honi chahiye (strong directional candle, na ki doji).
# 9:15 candle CLOSE hone ka strict wait karte hain pehle.
# Agar 9:15 pe match nahi hua, toh 9:20 candle ka jo bhi LATEST
# data available ho (partial ya closed, wait nahi karna) usse
# bhi try karte hain — bina body-check ke, sirf 9:15 ke liye hai.
# Ek baar True mil jaye toh session cache mein permanent rahega.
# ─────────────────────────────────────────────────────────────
def get_crossover_signal(symbol, poc_value, fast_span=9, slow_span=20):
    """
    Returns "✓" if either:
      A) 9:15 candle (CLOSED) — 9EMA was below 20EMA yesterday,
         is above 20EMA at 9:15 close, 9:15 close > poc_value,
         AND candle body >= 70% of (High - Low).
      B) 9:20 candle (ANY available data, closed or still forming) —
         EMA + POC conditions checked (no body-check) against 9:20's latest data.
    Returns "" if neither condition set is met yet.
    """
    try:
        if poc_value is None:
            return ""

        last_day = get_last_trading_day()
        today = datetime.now(IST).date()
        ticker = symbol + ".NS"
        # Kal ka poora din + aaj ka abhi tak ka data — EMA continuity ke liye
        df = yf.download(ticker, start=last_day, end=today + timedelta(days=1),
                         interval="5m", progress=False, auto_adjust=True)
        if df.empty:
            return ""
        df.index = pd.to_datetime(df.index)
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)
        df = df.between_time("09:15", "15:30")
        if df.empty:
            return ""

        df['EMA_fast'] = df['Close'].ewm(span=fast_span, adjust=False).mean()
        df['EMA_slow'] = df['Close'].ewm(span=slow_span, adjust=False).mean()

        df_yesterday = df[df.index.date == last_day]
        df_today     = df[df.index.date == today]

        if df_yesterday.empty or df_today.empty:
            return ""

        yesterday_last_fast = df_yesterday['EMA_fast'].iloc[-1]
        yesterday_last_slow = df_yesterday['EMA_slow'].iloc[-1]
        was_below = yesterday_last_fast < yesterday_last_slow

        if not was_below:
            return ""  # Kal hi upar tha — "crossover" ka koi matlab nahi

        def check_candle(candle_time_str, require_body_check=False, min_body_pct=70):
            df_candle = df_today.between_time(candle_time_str, candle_time_str)
            if df_candle.empty:
                return False
            row = df_candle.iloc[0]
            open_  = float(row['Open'])
            high_  = float(row['High'])
            low_   = float(row['Low'])
            close_ = float(row['Close'])
            fast_  = float(row['EMA_fast'])
            slow_  = float(row['EMA_slow'])

            basic_ok = (fast_ > slow_) and (close_ > poc_value)
            if not basic_ok:
                return False

            if require_body_check:
                candle_range = high_ - low_
                if candle_range <= 0:
                    return False  # Doji/flat candle — body % undefined, reject
                body_pct = abs(close_ - open_) / candle_range * 100
                if body_pct < min_body_pct:
                    return False

            return True

        # A) 9:15 candle — strict close-wait + body>=70% check
        if check_candle("09:15", require_body_check=True):
            return "09:15"

        # B) 9:20 candle — flexible, jo bhi latest data mile (closed ya forming)
        #    Body-check yahan NAHI hota, sirf 9:15 ke liye hai
        if check_candle("09:20", require_body_check=False):
            return "09:20"

        return ""
    except:
        return ""

# ─────────────────────────────────────────────────────────────
# 5-DAY MEDIAN VOLUME — Rel Vol (5D) ka baseline
# Yahoo Finance se peechle 5 COMPLETE trading days ka daily
# volume leke median nikalte hain. Aaj ka (incomplete/live) din
# explicitly exclude karte hain — warna self-referencing error
# ho jata hai (aaj ka volume khud denominator mein aa jata hai).
# Median use kiya hai average ki jagah — outlier-proof hai.
# ─────────────────────────────────────────────────────────────
def get_5day_median_volume(symbol, days=5):
    try:
        ticker = symbol + ".NS"
        df = yf.download(ticker, period="15d", interval="1d", progress=False, auto_adjust=True)
        if df.empty:
            return None
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        # Aaj ka incomplete row (Close = NaN hota hai jab din chal raha ho) exclude karo
        df = df.dropna(subset=['Close'])
        if df.empty:
            return None
        last_n = df['Volume'].tail(days)
        if last_n.empty:
            return None
        return round(float(last_n.median()), 0)
    except:
        return None

# ─────────────────────────────────────────────────────────────
# TV SCREENER FETCH — open + prev_close added for gap filter
# ─────────────────────────────────────────────────────────────
def fetch_tv_data():
    try:
        from tradingview_screener import Query
        from tradingview_screener.column import col

        count, df = (Query()
            .select(
                'name', 'close', 'change', 'volume',
                'relative_volume', 'market_cap_basic', 'sector',
                'High.1M', 'high', 'open', 'close[1]', 'high[1]'
            )
            .set_markets('india')
            .where(
                col('market_cap_basic') > 41_000_000_000,
                col('exchange') == 'NSE',
                col('high') >= col('High.1M'),
            )
            .order_by('change', ascending=False)
            .limit(100)  # Bada buffer — koi hard cap nahi, jitne bhi filters pass karein sab aayenge
            .get_scanner_data()
        )
        return count, df, None
    except Exception as e:
        return 0, pd.DataFrame(), str(e)

# ─────────────────────────────────────────────────────────────
# SHARED FORMAT HELPERS — market-open aur market-closed dono
# views isi ek copy ko use karte hain (koi duplicate-code nahi).
# ─────────────────────────────────────────────────────────────
def fmt_volume(v):
    try:
        v = float(v)
        if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
        if v >= 100_000:   return f"{v/100_000:.1f}L"
        if v >= 1_000:     return f"{v/1_000:.1f}K"
        return str(int(v))
    except: return str(v)

def fmt_relvol(v):
    if v is None:
        return '<span style="color:#9ca3af;">N/A</span>'
    try:
        v = float(v)
        if v >= 3:     bg, color = "#fef9c3", "#854f0b"
        elif v >= 1.5: bg, color = "#dcfce7", "#166534"
        else:          bg, color = "transparent", "#374151"
        return f'<span style="background:{bg};color:{color};padding:2px 7px;border-radius:4px;font-weight:600;">{v:.2f}x</span>'
    except: return '<span style="color:#9ca3af;">N/A</span>'

def fmt_entry_badges(c940, c945, c950):
    def badge(label, active):
        if active == "green":
            return f'<span style="background:#dcfce7;color:#166534;border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600;">{label}</span>'
        else:
            return f'<span style="color:#d1d5db;font-size:11px;padding:2px 5px;">{label}</span>'
    return f'{badge("9:40", c940)}&nbsp;{badge("9:45", c945)}&nbsp;{badge("9:50", c950)}'

def fmt_poc_gap(poc, gap_pct):
    if poc is None:
        return '<span style="color:#9ca3af;">N/A</span>'
    poc_str = f"₹{float(poc):,.2f}"
    if gap_pct is None:
        return f'<div style="font-size:12px;">{poc_str}</div>'
    if gap_pct > 0:
        if gap_pct >= 5:   color = "#14532d"
        elif gap_pct >= 2: color = "#16a34a"
        else:              color = "#4ade80"
        gap_str = f'<span style="color:{color};font-weight:700;">↑ +{gap_pct:.1f}%</span>'
    else:
        gap_str = f'<span style="color:#dc2626;font-weight:600;">↓ {gap_pct:.1f}%</span>'
    return f'<div style="font-size:12px;font-weight:500;">{poc_str}</div><div style="font-size:11px;">{gap_str}</div>'

def fmt_prev_high(dist, val):
    if dist is None or val is None:
        return '<span style="color:#9ca3af;">N/A</span>'
    val_str = f"₹{val:,.2f}"
    if dist >= 0:
        if dist >= 3:   color = "#14532d"
        elif dist >= 1: color = "#16a34a"
        else:           color = "#4ade80"
        pct_str = f'<span style="color:{color};font-weight:700;">↑ +{dist:.1f}%</span>'
    else:
        pct_str = f'<span style="color:#dc2626;font-weight:600;">↓ {dist:.1f}%</span>'
    return f'<div style="font-size:12px;font-weight:500;">{val_str}</div><div style="font-size:11px;">{pct_str}</div>'

def fmt_ema_coil(pct, min_threshold=70):
    if pct is None or pct < min_threshold:
        return '<span style="color:#9ca3af;">—</span>'
    return f'<span style="background:#dcfce7;color:#166534;border-radius:4px;padding:3px 9px;font-weight:600;">✓ {pct:.0f}%</span>'

def fmt_crossover(matched_candle):
    if matched_candle == "09:15":
        return '<span style="background:#dcfce7;color:#166534;border-radius:4px;padding:3px 9px;font-weight:700;">✓</span>'
    elif matched_candle == "09:20":
        return '<span style="background:#fce7f3;color:#9d174d;border-radius:4px;padding:3px 9px;font-weight:700;">✓</span>'
    else:
        return ''

# Shared HTML cell-styles (table borders/padding) — dono views isi ko use karte hain
TH = "padding:8px 10px;font-size:11px;font-weight:700;color:#6b7280;border-bottom:2px solid #e5e7eb;white-space:nowrap;text-align:center;"
TH_L = "padding:8px 10px;font-size:11px;font-weight:700;color:#6b7280;border-bottom:2px solid #e5e7eb;text-align:left;"
TD = "padding:8px 10px;font-size:12px;border-bottom:1px solid #f3f4f6;white-space:nowrap;text-align:center;vertical-align:middle;"
TD_L = "padding:8px 10px;font-size:12px;border-bottom:1px solid #f3f4f6;text-align:left;vertical-align:middle;"


def render_stock_table(df, height_per_row=52, extra_height=60):
    """
    Shared table-renderer — df mein columns: Symbol, Price, Chg, Volume,
    RelVol5D, POC, GapPct, c940, c945, c950, PrevHighDist, PrevHighVal,
    EmaCoilPct, Crossover, MktCap, Sector. Market-open aur market-closed
    dono views isi function ko call karte hain.
    """
    rows_html = ""
    for i, (_, row) in enumerate(df.iterrows()):
        sym    = row.get("Symbol", "")
        price  = row.get("Price", 0)
        chg    = row.get("Chg", 0)
        vol    = row.get("Volume", 0)
        relvol = row.get("RelVol5D", 0)
        poc    = row.get("POC", None)
        gappct = row.get("GapPct", None)
        prevhd = row.get("PrevHighDist", None)
        prevhv = row.get("PrevHighVal", None)
        emacoil = row.get("EmaCoilPct", None)
        crossover = row.get("Crossover", "")
        c940   = row.get("c940", "")
        c945   = row.get("c945", "")
        c950   = row.get("c950", "")
        mktcap = row.get("MktCap", "")
        sector = row.get("Sector", "")

        bg      = "#f9fafb" if i % 2 == 0 else "#ffffff"
        chg_col = "#16a34a" if float(chg) > 0 else "#dc2626"
        chg_sgn = "+" if float(chg) > 0 else ""

        rows_html += f"""
        <tr style="background:{bg};">
            <td style="{TD_L}">
                <span onclick="tsCopy(event,this,'{sym}')" style="cursor:pointer;color:#1e40af;font-weight:700;">
                    <span class="ts-sym-name">{sym}</span>
                </span>
                <div style="font-size:10px;color:#9ca3af;margin-top:1px;">{sector}</div>
            </td>
            <td style="{TD}">
                <div style="font-weight:600;color:#111827;">₹{float(price):.2f}</div>
                <div style="font-size:11px;color:{chg_col};font-weight:600;">{chg_sgn}{float(chg):.2f}%</div>
            </td>
            <td style="{TD}">{fmt_volume(vol)}</td>
            <td style="{TD}">{fmt_relvol(relvol)}</td>
            <td style="{TD}">{fmt_poc_gap(poc, gappct)}</td>
            <td style="{TD}">{fmt_entry_badges(c940, c945, c950)}</td>
            <td style="{TD}">{fmt_prev_high(prevhd, prevhv)}</td>
            <td style="{TD}">{fmt_ema_coil(emacoil)}</td>
            <td style="{TD}">{fmt_crossover(crossover)}</td>
            <td style="{TD};color:#374151;">₹{float(mktcap):.1f}B</td>
        </tr>"""

    table_html = f"""
    <script>
    function tsCopy(e,btn,sym){{
      e.stopPropagation();
      function showCopied(){{
        var el=btn.querySelector('.ts-sym-name');
        if(!el)return;
        var orig=el.textContent;
        el.textContent='✓ '+sym;
        el.style.color='#00a854';
        setTimeout(function(){{el.textContent=orig;el.style.color='';}},1500);
      }}
      if(navigator.clipboard&&window.isSecureContext){{
        navigator.clipboard.writeText(sym).then(showCopied).catch(function(){{
          var ta=document.createElement('textarea');
          ta.value=sym;ta.style.position='fixed';ta.style.opacity='0';
          document.body.appendChild(ta);ta.select();
          try{{document.execCommand('copy');showCopied();}}catch(err){{}}
          document.body.removeChild(ta);
        }});
      }}else{{
        var ta=document.createElement('textarea');
        ta.value=sym;ta.style.position='fixed';ta.style.opacity='0';
        document.body.appendChild(ta);ta.select();
        try{{document.execCommand('copy');showCopied();}}catch(err){{}}
        document.body.removeChild(ta);
      }}
    }}
    </script>
    <div style="overflow-x:auto;border:1px solid #e5e7eb;border-radius:8px;margin-top:8px;">
    <table style="width:100%;border-collapse:collapse;font-family:sans-serif;">
      <thead style="background:#f9fafb;">
        <tr>
          <th style="{TH_L}">Symbol</th>
          <th style="{TH}">Price / Chg%</th>
          <th style="{TH}">Volume</th>
          <th style="{TH}">Rel Vol</th>
          <th style="{TH}">POC / Gap</th>
          <th style="{TH}">Entry Signal</th>
          <th style="{TH}">Prev High</th>
          <th style="{TH}">EMA Coil</th>
          <th style="{TH}">Crossover</th>
          <th style="{TH}">Mkt Cap</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>
    """

    import streamlit.components.v1 as components
    components.html(table_html, height=len(df) * height_per_row + extra_height, scrolling=False)

def render_market_closed_view():
    """
    Market band hai — TV se stocks fetch karte hain (sirf DISPLAY ke
    liye: Price, Chg%, Volume, Entry-Signal jaisi cheezein — TV apna
    "last trading session" ka data deta hai chahe market band ho).
    Koi POC/EMA-Coil/Crossover/Vol5D CALCULATION nahi hoti — woh sab
    Supabase se seedha merge hoti hain (jo already market-hours mein
    calculate/save ho chuki thi).
    """
    calc_date = get_last_trading_day()

    st.markdown(f"""
    <div style="background:#fefce8;border:1px solid #fef08a;border-radius:8px;padding:10px 16px;margin-bottom:10px;">
        <span style="color:#854f0b;font-weight:600;font-size:13px;">🔒 Market Closed</span>
        <span style="color:#6b7280;font-size:12px;"> — showing last saved data for {calc_date.strftime('%d %b %Y')}. No live calculation happening.</span>
    </div>
    """, unsafe_allow_html=True)

    # ── TV se fetch (sirf display-fields ke liye, koi calculation nahi) ──
    count, df, error = fetch_tv_data()
    if error or df.empty:
        st.info("TV se data fetch nahi ho paya abhi.")
        return

    # ── Gap filter (same jaisa market-open mein) ──
    def calc_gap_pct(row):
        try:
            open_price = float(row.get('open', 0) or 0)
            prev_close = float(row.get('close[1]', 0) or 0)
            if prev_close == 0:
                return 0
            return ((open_price - prev_close) / prev_close) * 100
        except:
            return 0

    df['_opening_gap'] = df.apply(calc_gap_pct, axis=1)
    df = df[df['_opening_gap'].abs() <= 2.0]

    if df.empty:
        st.info("Gap-filter ke baad koi stock nahi bacha.")
        return

    # ── Clean/rename (same jaisa market-open mein) ──
    df = df.copy()
    def calc_prev_high_dist(row):
        try:
            price    = float(row.get('close', 0) or 0)
            prev_high = float(row.get('high[1]', 0) or 0)
            if prev_high == 0:
                return None
            return round(((price - prev_high) / prev_high) * 100, 2)
        except:
            return None

    def get_prev_high_val(row):
        try:
            v = float(row.get('high[1]', 0) or 0)
            return v if v > 0 else None
        except:
            return None

    df['PrevHighDist'] = df.apply(calc_prev_high_dist, axis=1)
    df['PrevHighVal']  = df.apply(get_prev_high_val, axis=1)
    df = df.drop(columns=['high', 'High.1M', 'open', 'close[1]', 'high[1]', '_opening_gap'], errors='ignore')
    df['change']           = df['change'].round(2)
    df['relative_volume']  = df['relative_volume'].round(2)
    df['market_cap_basic'] = (df['market_cap_basic'] / 1e9).round(1)
    df['name'] = df['ticker'].str.replace('NSE:', '', regex=False)
    df = df.drop(columns=['ticker'], errors='ignore')
    df = df.rename(columns={
        'name'            : 'Symbol',
        'close'           : 'Price',
        'change'          : 'Chg',
        'volume'          : 'Volume',
        'relative_volume' : 'RelVol',
        'market_cap_basic': 'MktCap',
        'sector'          : 'Sector',
    })

    # ── Supabase se calculated-fields merge karo (POC, EMA-Coil, Vol5D, Crossover) ──
    saved_data = supabase_get_all_for_date(calc_date)

    poc_vals, gap_vals, ema_vals, vol5d_vals, crossover_vals = [], [], [], [], []
    for _, row in df.iterrows():
        symbol = row['Symbol']
        price  = row['Price']
        saved  = saved_data.get(symbol, {})

        poc = saved.get('poc_value')
        if poc is None:
            poc_vals.append(None)
            gap_vals.append(None)
        elif price > poc:
            poc_vals.append(poc)
            gap_vals.append(((price - poc) / poc) * 100)
        else:
            poc_vals.append(poc)
            gap_vals.append(-((poc - price) / poc) * 100)

        ema_vals.append(saved.get('ema_coil_pct'))
        vol5d_vals.append(saved.get('vol5d_median'))
        crossover_vals.append(saved.get('crossover_status', ''))

    df['POC']         = poc_vals
    df['GapPct']      = gap_vals
    df['EmaCoilPct']  = ema_vals
    df['Crossover']   = crossover_vals

    # ── Rel Vol (5D) — Vol5D (Supabase se) ÷ aaj/last-known volume (TV se) ──
    def calc_rel_vol_5d(row, vol5d_map):
        try:
            today_vol  = float(row.get('Volume', 0) or 0)
            median_vol = vol5d_map.get(row['Symbol'])
            if median_vol is None or median_vol == 0:
                return None
            return round(today_vol / median_vol, 2)
        except:
            return None

    vol5d_map = {row['Symbol']: v for row, v in zip(df.to_dict('records'), vol5d_vals)}
    df['RelVol5D'] = df.apply(lambda r: calc_rel_vol_5d(r, vol5d_map), axis=1)

    # ── Crossover-filter (same jaisa market-open mein — sirf confirmed-stocks dikhein) ──
    df = df[df['Crossover'] == "09:15"]

    if df.empty:
        st.info("Is trading day ke liye koi stock 9:15 crossover confirm nahi kar paaya tha.")
        return

    # ── Entry Signal — Supabase mein store NAHI hota, isliye market-band
    # mode mein yeh blank rahega (candles ka data bhi TV se nahi milta) ──
    df['c940'] = ""
    df['c945'] = ""
    df['c950'] = ""

    # ── Header cards (same style jaisa market-open) ──
    sectors    = ['All'] + sorted(df['Sector'].dropna().unique().tolist())
    top_gainer = df.iloc[0]['Symbol'] if len(df) > 0 else '-'
    max_chg    = df['Chg'].max() if len(df) > 0 else 0.0

    st.markdown(f"""
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:6px 0;">
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">STOCKS</div>
            <div style="font-size:18px;font-weight:700;color:#16a34a;line-height:1.2;">{len(df)}</div>
        </div>
        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">TOP GAINER</div>
            <div style="font-size:16px;font-weight:700;color:#2563eb;line-height:1.2;">{top_gainer}</div>
        </div>
        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">MAX CHG%</div>
            <div style="font-size:16px;font-weight:700;color:#16a34a;line-height:1.2;">+{max_chg:.2f}%</div>
        </div>
        <div style="background:#fdf4ff;border:1px solid #e9d5ff;border-radius:6px;padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">POC DATE</div>
            <div style="font-size:13px;font-weight:700;color:#7c3aed;line-height:1.2;">{calc_date.strftime('%d %b')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    render_stock_table(df)

# ─────────────────────────────────────────────────────────────
# AUTO-REFRESH FRAGMENT — har 60s sirf yeh section re-run hoga
# Poora page reload NAHI hoga — sidebar/header stable rahenge
# ─────────────────────────────────────────────────────────────
@st.fragment(run_every=60)
def screener_fragment():
    # ── FETCH TV DATA ──
    with st.spinner("Fetching Top Gainer stocks from TradingView..."):
        count, df, error = fetch_tv_data()

    if error:
        st.error(f"❌ Error: {error}")
        return

    if df.empty:
        st.warning("No stocks found.")
        return

    # ─────────────────────────────────────────────────────────────
    # GAP FILTER — 2% se zyada gap up/down remove karo
    # ─────────────────────────────────────────────────────────────
    def calc_gap_pct(row):
        try:
            open_price = float(row.get('open', 0) or 0)
            prev_close = float(row.get('close[1]', 0) or 0)  # close[1] = previous day close ✅
            if prev_close == 0:
                return 0
            return ((open_price - prev_close) / prev_close) * 100
        except:
            return 0

    df['_opening_gap'] = df.apply(calc_gap_pct, axis=1)
    df = df[df['_opening_gap'].abs() <= 2.0]  # Gap filter — koi count-limit nahi, jitne bhi pass karein

    # ─────────────────────────────────────────────────────────────
    # CLEAN DATA
    # ─────────────────────────────────────────────────────────────
    df = df.copy()
    # Prev High Distance calculate karo before dropping
    def calc_prev_high_dist(row):
        try:
            price    = float(row.get('close', 0) or 0)
            prev_high = float(row.get('high[1]', 0) or 0)
            if prev_high == 0:
                return None
            return round(((price - prev_high) / prev_high) * 100, 2)
        except:
            return None

    def get_prev_high_val(row):
        try:
            v = float(row.get('high[1]', 0) or 0)
            return v if v > 0 else None
        except:
            return None

    df['PrevHighDist'] = df.apply(calc_prev_high_dist, axis=1)
    df['PrevHighVal']  = df.apply(get_prev_high_val, axis=1)
    df = df.drop(columns=['high', 'High.1M', 'open', 'close[1]', 'high[1]', '_opening_gap'], errors='ignore')
    df['change']           = df['change'].round(2)
    df['relative_volume']  = df['relative_volume'].round(2)
    df['market_cap_basic'] = (df['market_cap_basic'] / 1e9).round(1)
    df['name'] = df['ticker'].str.replace('NSE:', '', regex=False)
    df = df.drop(columns=['ticker'], errors='ignore')
    df = df.rename(columns={
        'name'            : 'Symbol',
        'close'           : 'Price',
        'change'          : 'Chg',
        'volume'          : 'Volume',
        'relative_volume' : 'RelVol',
        'market_cap_basic': 'MktCap',
        'sector'          : 'Sector',
    })

    # ─────────────────────────────────────────────────────────────
    # STEP 1: CROSSOVER CHECK — sabse pehle, saare gap-filtered
    # stocks pe. POC bhi isi step mein calculate hota hai (jinke
    # POC missing hain unke liye), taaki POC bhi ek hi baar ho aur
    # jo stocks pass karein unke liye already cache mein ready rahe.
    #
    # Cache priority: session_state (fastest) → Supabase (persists
    # across restarts) → yfinance (slowest, sirf tab jab dono jagah
    # miss ho). Naya calculation Supabase mein save hota hai (agli
    # baar/naya-session ke liye instant mile) — market-hours mein hi.
    #
    # IMPORTANT: session_state ko worker-threads ke andar access
    # NAHI karte (thread-safety issue) — sirf main-thread mein
    # cache-check aur cache-write hota hai, threads sirf pure
    # calculation (get_yesterday_poc, get_crossover_signal) karte hain.
    # ─────────────────────────────────────────────────────────────
    calc_date   = get_last_trading_day()
    signal_date = datetime.now(IST).date()

    if 'poc_cache' not in st.session_state:
        st.session_state['poc_cache'] = {}
    if 'crossover_cache' not in st.session_state:
        st.session_state['crossover_cache'] = {}

    # Main-thread pe hi decide karo kaunse symbols ka POC missing hai (session-cache mein)
    symbols_needing_poc = [s for s in df['Symbol'] if s not in st.session_state['poc_cache']]

    # In mein se, pehle Supabase check karo — agar mila, seedha cache mein daal do
    still_missing_poc = []
    for symbol in symbols_needing_poc:
        cached_row = supabase_get_cached_row(symbol, calc_date)
        if cached_row is not None and cached_row.get('poc_value') is not None:
            st.session_state['poc_cache'][symbol] = cached_row['poc_value']
            # Baaki cheezein bhi mil gayi Supabase se — cache kar do, baad mein re-calc na ho
            if cached_row.get('ema_coil_pct') is not None:
                if 'ema_cache' not in st.session_state:
                    st.session_state['ema_cache'] = {}
                st.session_state['ema_cache'][symbol] = cached_row['ema_coil_pct']
            if cached_row.get('vol5d_median') is not None:
                if 'vol5d_cache' not in st.session_state:
                    st.session_state['vol5d_cache'] = {}
                st.session_state['vol5d_cache'][symbol] = cached_row['vol5d_median']
            if cached_row.get('prev_high_val') is not None:
                if 'prevhigh_cache' not in st.session_state:
                    st.session_state['prevhigh_cache'] = {}
                st.session_state['prevhigh_cache'][symbol] = cached_row['prev_high_val']
            if cached_row.get('crossover_status'):
                st.session_state['crossover_cache'][symbol] = cached_row['crossover_status']
        else:
            still_missing_poc.append(symbol)

    # Ab sirf woh bache hain jo Supabase mein bhi nahi mile — yfinance se calculate karo
    if still_missing_poc:
        with st.spinner(f"Calculating POC for {len(still_missing_poc)} stocks..."):
            with ThreadPoolExecutor(max_workers=10) as executor:
                # Worker thread sirf pure calculation karta hai — session_state touch nahi
                futures = {executor.submit(get_yesterday_poc, s): s for s in still_missing_poc}
                for future in as_completed(futures):
                    sym = futures[future]
                    poc_val = future.result()
                    st.session_state['poc_cache'][sym] = poc_val  # Main-thread pe cache-write
                    supabase_save_row(sym, signal_date, calc_date, poc_value=poc_val)

    def crossover_pure(symbol, poc_val):
        """Pure calculation — session_state touch nahi karta, thread-safe hai."""
        result = get_crossover_signal(symbol, poc_val)
        return symbol, result

    crossover_symbols_to_check = [
        s for s in df['Symbol']
        if st.session_state['crossover_cache'].get(s, "") not in ("09:15", "09:20")
    ]

    if crossover_symbols_to_check:
        with st.spinner(f"Checking crossover for {len(crossover_symbols_to_check)} stocks..."):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(crossover_pure, s, st.session_state['poc_cache'].get(s))
                    for s in crossover_symbols_to_check
                ]
                for future in as_completed(futures):
                    sym, result = future.result()
                    if result in ("09:15", "09:20"):  # Match mila — permanent rahega
                        st.session_state['crossover_cache'][sym] = result
                        supabase_save_row(sym, signal_date, calc_date, crossover_status=result)
                    elif sym not in st.session_state['crossover_cache']:
                        st.session_state['crossover_cache'][sym] = ""

    df['Crossover'] = df['Symbol'].map(lambda s: st.session_state['crossover_cache'].get(s, ""))

    # ─────────────────────────────────────────────────────────────
    # STEP 2: FINAL FILTER — sirf woh stocks aage badhein jinka
    # Crossover 9:15 (strict) confirm hua ho. Baaki sab yahi drop
    # ho jate hain — unke liye EMA-Coil/Vol5D/Entry-Signal calculate
    # hi nahi honge (waste-calculation avoid hota hai).
    # ─────────────────────────────────────────────────────────────
    df = df[df['Crossover'] == "09:15"]

    if df.empty:
        st.info("Abhi tak koi stock 9:15 crossover confirm nahi kar paaya. Refresh karte rahiye.")
        return

    # ─────────────────────────────────────────────────────────────
    # STEP 3: POC/GapPct display-values — sirf FILTERED stocks ke
    # liye (POC already crossover-step mein calculate ho chuka hai,
    # cache se instant milega).
    # ─────────────────────────────────────────────────────────────
    poc_vals, gap_vals = [], []
    for _, row in df.iterrows():
        symbol = row['Symbol']
        price  = row['Price']
        poc    = st.session_state['poc_cache'].get(symbol)
        if poc is None:
            poc_vals.append(None)
            gap_vals.append(None)
        elif price > poc:
            pct = ((price - poc) / poc) * 100
            poc_vals.append(poc)
            gap_vals.append(pct)
        else:
            pct = ((poc - price) / poc) * 100
            poc_vals.append(poc)
            gap_vals.append(-pct)
    df['POC']     = poc_vals
    df['GapPct']  = gap_vals

    # ─────────────────────────────────────────────────────────────
    # STEP 4: EMA-COIL + VOL5D — sirf FILTERED (Crossover-passed)
    # stocks ke liye calculate. session_state cache — naya stock
    # aane pe hi fetch hoga.
    # ─────────────────────────────────────────────────────────────
    if 'ema_cache' not in st.session_state:
        st.session_state['ema_cache'] = {}
    if 'prevhigh_cache' not in st.session_state:
        st.session_state['prevhigh_cache'] = {}
    if 'vol5d_cache' not in st.session_state:
        st.session_state['vol5d_cache'] = {}

    need_check = [s for s in df['Symbol'] if s not in st.session_state['ema_cache']]

    def calculate_ema_and_vol5d(symbol):
        """Sirf EMA-Coil aur Vol5D — POC ab yahan nahi (already ho chuka hai)."""
        ema_val   = get_ema_consolidation_pct(symbol)
        vol5d_val = get_5day_median_volume(symbol)
        return symbol, ema_val, vol5d_val

    if need_check:
        with st.spinner(f"Calculating EMA Coil & Volume for {len(need_check)} qualified stocks..."):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(calculate_ema_and_vol5d, s) for s in need_check]
                for future in as_completed(futures):
                    symbol, ema_val, vol5d_val = future.result()
                    st.session_state['ema_cache'][symbol] = ema_val
                    # PrevHighVal is stock ke liye df se nikal lo (TV se already mila hua hai)
                    row_match = df[df['Symbol'] == symbol]
                    prevhigh_val = float(row_match['PrevHighVal'].iloc[0]) if not row_match.empty and pd.notna(row_match['PrevHighVal'].iloc[0]) else None
                    st.session_state['prevhigh_cache'][symbol] = prevhigh_val
                    st.session_state['vol5d_cache'][symbol] = vol5d_val
                    supabase_save_row(
                        symbol, signal_date, calc_date,
                        prev_high_val=prevhigh_val,
                        ema_coil_pct=ema_val,
                        vol5d_median=vol5d_val,
                    )

    df['EmaCoilPct'] = df['Symbol'].map(lambda s: st.session_state['ema_cache'].get(s))

    # ─────────────────────────────────────────────────────────────
    # REL VOL (5D) — LIVE calculation, cache NAHI hoga
    # Aaj ka volume (TV se, real-time) ÷ 5-day median (cached, historical)
    # ─────────────────────────────────────────────────────────────
    def calc_rel_vol_5d(row):
        try:
            today_vol = float(row.get('Volume', 0) or 0)
            median_vol = st.session_state['vol5d_cache'].get(row['Symbol'])
            if median_vol is None or median_vol == 0:
                return None
            return round(today_vol / median_vol, 2)
        except:
            return None

    df['RelVol5D'] = df.apply(calc_rel_vol_5d, axis=1)

    # ─────────────────────────────────────────────────────────────
    # CANDLE COLUMNS — Entry Signal, standalone, session_state cache
    # Kisi bhi price-comparison (POC/ATP) pe depend nahi karta —
    # sirf candle ka Close > Open check karta hai.
    # ─────────────────────────────────────────────────────────────
    now_ist  = get_current_ist_time()
    now_time = now_ist.strftime('%H:%M:%S')
    now_hhmm = now_ist.hour * 60 + now_ist.minute

    show_940 = now_hhmm >= (9 * 60 + 45)
    show_945 = now_hhmm >= (9 * 60 + 50)
    show_950 = now_hhmm >= (9 * 60 + 55)

    if 'candle_cache' not in st.session_state:
        st.session_state['candle_cache'] = {}

    def get_candle_cached(symbol, candle_time, should_show):
        if not should_show:
            return ""
        key = f"{symbol}_{candle_time}"
        return st.session_state['candle_cache'].get(key, "")

    # Har stock ke liye — jitni candles abhi "should_show" (time aa chuka hai)
    # hain aur cache mein nahi hain, unko ek hi optimized call se nikal lo
    # (get_all_candle_signals ek hi yfinance fetch se teeno candles deta hai)
    symbols_needing_fetch = []
    for _, row in df.iterrows():
        sym = row['Symbol']
        missing_needed = any(
            show and f"{sym}_{t}" not in st.session_state['candle_cache']
            for t, show in [("09:40", show_940), ("09:45", show_945), ("09:50", show_950)]
        )
        if missing_needed:
            symbols_needing_fetch.append(sym)

    if symbols_needing_fetch:
        with st.spinner(f"Fetching candles for {len(symbols_needing_fetch)} stocks..."):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(get_all_candle_signals, sym): sym for sym in symbols_needing_fetch}
                for future in as_completed(futures):
                    sym = futures[future]
                    all_signals = future.result()
                    for t in ["09:40", "09:45", "09:50"]:
                        st.session_state['candle_cache'][f"{sym}_{t}"] = all_signals[t]

    c940_list, c945_list, c950_list = [], [], []
    for _, row in df.iterrows():
        sym = row['Symbol']
        c940_list.append(get_candle_cached(sym, "09:40", show_940))
        c945_list.append(get_candle_cached(sym, "09:45", show_945))
        c950_list.append(get_candle_cached(sym, "09:50", show_950))
    df['c940'] = c940_list
    df['c945'] = c945_list
    df['c950'] = c950_list

    # ─────────────────────────────────────────────────────────────
    # HEADER ROW
    # ─────────────────────────────────────────────────────────────
    sectors    = ['All'] + sorted(df['Sector'].dropna().unique().tolist())
    top_gainer = df.iloc[0]['Symbol'] if len(df) > 0 else '-'
    max_chg    = df['Chg'].max() if len(df) > 0 else 0.0
    last_day   = get_last_trading_day()

    c1, c2, c3 = st.columns([3, 5, 2])
    with c1:
        st.markdown(f"""
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:6px 0;">
            <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:5px 12px;text-align:center;">
                <div style="font-size:10px;color:#6b7280;font-weight:600;">STOCKS</div>
                <div style="font-size:18px;font-weight:700;color:#16a34a;line-height:1.2;">{len(df)}</div>
            </div>
            <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:5px 12px;text-align:center;">
                <div style="font-size:10px;color:#6b7280;font-weight:600;">TOP GAINER</div>
                <div style="font-size:16px;font-weight:700;color:#2563eb;line-height:1.2;">{top_gainer}</div>
            </div>
            <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:5px 12px;text-align:center;">
                <div style="font-size:10px;color:#6b7280;font-weight:600;">MAX CHG%</div>
                <div style="font-size:16px;font-weight:700;color:#16a34a;line-height:1.2;">+{max_chg:.2f}%</div>
            </div>
            <div style="background:#fefce8;border:1px solid #fef08a;border-radius:6px;padding:5px 12px;text-align:center;">
                <div style="font-size:10px;color:#6b7280;font-weight:600;">UPDATED</div>
                <div style="font-size:14px;font-weight:700;color:#ca8a04;line-height:1.2;">{now_time}</div>
            </div>
            <div style="background:#fdf4ff;border:1px solid #e9d5ff;border-radius:6px;padding:5px 12px;text-align:center;">
                <div style="font-size:10px;color:#6b7280;font-weight:600;">POC DATE</div>
                <div style="font-size:13px;font-weight:700;color:#7c3aed;line-height:1.2;">{last_day.strftime('%d %b')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        selected_sector = st.selectbox("", sectors, index=0, label_visibility="collapsed")

    with c3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun(scope="fragment")

    if selected_sector != 'All':
        df = df[df['Sector'] == selected_sector]

    # ─────────────────────────────────────────────────────────────
    # TABLE RENDER — shared render_stock_table() use karta hai
    # (module-level, market-closed view ke saath bhi share hota hai)
    # ─────────────────────────────────────────────────────────────
    render_stock_table(df)

    # ── TEMP DIAGNOSTIC — Supabase save status, ek line mein ──
    success_count = st.session_state.get('supabase_save_success_count', 0)
    errors = st.session_state.get('supabase_save_errors', [])
    if success_count or errors:
        st.caption(f"🔍 Supabase saves this session: {success_count} successful, {len(errors)} failed")
        if errors:
            with st.expander("⚠️ Show Supabase errors"):
                for e in errors[-10:]:  # sirf aakhri 10 dikhao
                    st.text(e)

    st.markdown("""
    <div style="margin-top:6px;font-size:10px;color:#9ca3af;text-align:center;">
        TradingView Screener · NSE · Mkt Cap > ₹51B · New High 1M · Gap filter ±2% · Sorted by Chg% ↓ · POC = Yesterday Volume Profile Point of Control
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# RUN FRAGMENT
# ─────────────────────────────────────────────────────────────
screener_fragment()
