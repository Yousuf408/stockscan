import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import pytz

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
from styles import apply_styles, sidebar_brand, page_header
apply_styles()
sidebar_brand("TVScreener")

# ─────────────────────────────────────────────────────────────
# COMPACT CSS
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
.block-container { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; }
div[data-testid="stSelectbox"] { margin-top: 0 !important; margin-bottom: 0 !important; }
div[data-testid="stButton"] button {
    padding: 4px 12px !important;
    font-size: 12px !important;
    height: 32px !important;
}
div[data-testid="stVerticalBlock"] { gap: 0.3rem !important; }
</style>
""", unsafe_allow_html=True)

IST = pytz.timezone("Asia/Kolkata")

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def get_last_trading_day():
    d = datetime.now(IST).date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

def get_current_ist_time():
    return datetime.now(IST)

# ─────────────────────────────────────────────────────────────
# ATP — kal ka full day 5min VWAP
# ─────────────────────────────────────────────────────────────
def get_yesterday_atp(symbol):
    try:
        last_day = get_last_trading_day()
        ticker = symbol + ".NS"
        df = yf.download(
            ticker,
            start=last_day,
            end=last_day + timedelta(days=1),
            interval="5m",
            progress=False,
            auto_adjust=True
        )
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index)
        df = df.between_time("09:15", "15:30")
        if df.empty:
            return None
        close  = df['Close'].values.flatten()
        volume = df['Volume'].values.flatten()
        atp = (close * volume).sum() / volume.sum()
        return round(float(atp), 2)
    except:
        return None

# ─────────────────────────────────────────────────────────────
# CANDLE CHECK — aaj ka specific time candle
# Green = Close > Open, blank otherwise
# ─────────────────────────────────────────────────────────────
def get_candle_signal(symbol, candle_time_str):
    """
    candle_time_str: start time of the 5min candle
    e.g. "09:35" = candle that starts 9:35 and closes at 9:40
    Returns "🟢" if green (close > open), "" otherwise
    """
    try:
        today = datetime.now(IST).date()
        ticker = symbol + ".NS"
        df = yf.download(
            ticker,
            start=today,
            end=today + timedelta(days=1),
            interval="5m",
            progress=False,
            auto_adjust=True
        )
        if df.empty:
            return ""
        df.index = pd.to_datetime(df.index)
        # Convert to IST
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(IST)
        else:
            df.index = df.index.tz_convert(IST)

        # Filter sirf us candle ka row
        df_candle = df.between_time(candle_time_str, candle_time_str)
        if df_candle.empty:
            return ""

        row = df_candle.iloc[0]
        open_  = float(row['Open'].values[0] if hasattr(row['Open'], 'values') else row['Open'])
        close_ = float(row['Close'].values[0] if hasattr(row['Close'], 'values') else row['Close'])

        return "🟢" if close_ > open_ else ""
    except:
        return ""

# ─────────────────────────────────────────────────────────────
# TV SCREENER FETCH
# ─────────────────────────────────────────────────────────────
def fetch_tv_data():
    try:
        from tradingview_screener import Query
        from tradingview_screener.column import col

        count, df = (Query()
            .select(
                'name', 'close', 'change', 'volume',
                'relative_volume', 'market_cap_basic', 'sector',
                'High.1M', 'high'
            )
            .set_markets('india')
            .where(
                col('market_cap_basic') > 51_000_000_000,
                col('exchange') == 'NSE',
                col('high') >= col('High.1M'),
            )
            .order_by('change', ascending=False)
            .limit(200)
            .get_scanner_data()
        )
        return count, df, None
    except Exception as e:
        return 0, pd.DataFrame(), str(e)

# ─────────────────────────────────────────────────────────────
# FETCH TV DATA
# ─────────────────────────────────────────────────────────────
with st.spinner("Fetching from TradingView..."):
    count, df, error = fetch_tv_data()

if error:
    st.error(f"❌ Error: {error}")
    st.stop()

if df.empty:
    st.warning("No stocks found.")
    st.stop()

# ─────────────────────────────────────────────────────────────
# CLEAN DATA
# ─────────────────────────────────────────────────────────────
df = df.copy()
df = df.drop(columns=['high', 'High.1M'], errors='ignore')
df['change']           = df['change'].round(2)
df['relative_volume']  = df['relative_volume'].round(2)
df['market_cap_basic'] = (df['market_cap_basic'] / 1e9).round(1)

df['name'] = df['ticker'].str.replace('NSE:', '', regex=False)
df = df.drop(columns=['ticker'], errors='ignore')

df = df.rename(columns={
    'name'            : 'Symbol',
    'close'           : 'Price ₹',
    'change'          : 'Chg %',
    'volume'          : 'Volume',
    'relative_volume' : 'Rel Vol',
    'market_cap_basic': 'Mkt Cap (B)',
    'sector'          : 'Sector',
})

# ─────────────────────────────────────────────────────────────
# ATP FETCH
# ─────────────────────────────────────────────────────────────
with st.spinner(f"Calculating yesterday ATP for {len(df)} stocks..."):
    signals = []
    for _, row in df.iterrows():
        symbol = row['Symbol']
        price  = row['Price ₹']
        atp    = get_yesterday_atp(symbol)
        if atp is None:
            signals.append("⚪ N/A")
        elif price > atp:
            pct = ((price - atp) / atp) * 100
            signals.append(f"🟢 ₹{atp:,.2f} (+{pct:.1f}%)")
        else:
            pct = ((atp - price) / atp) * 100
            signals.append(f"🔴 ₹{atp:,.2f} (-{pct:.1f}%)")
    df['Signal'] = signals

# ─────────────────────────────────────────────────────────────
# CANDLE COLUMNS — time based
# 9:40 column = 9:35 candle (closes at 9:40) — show when time >= 9:40
# 9:45 column = 9:40 candle (closes at 9:45) — show when time >= 9:45
# 9:50 column = 9:45 candle (closes at 9:50) — show when time >= 9:50
# ─────────────────────────────────────────────────────────────
now_ist  = get_current_ist_time()
now_time = now_ist.strftime('%H:%M:%S')
now_hhmm = now_ist.hour * 60 + now_ist.minute  # minutes since midnight

show_940 = now_hhmm >= (9 * 60 + 40)   # 9:40+ → fetch 9:35 candle
show_945 = now_hhmm >= (9 * 60 + 45)   # 9:45+ → fetch 9:40 candle
show_950 = now_hhmm >= (9 * 60 + 50)   # 9:50+ → fetch 9:45 candle

if show_940 or show_945 or show_950:
    with st.spinner("Fetching candle data..."):
        c940_list, c945_list, c950_list = [], [], []
        for _, row in df.iterrows():
            sym = row['Symbol']
            # 9:40 column → 9:35 closed candle
            c940_list.append(get_candle_signal(sym, "09:35") if show_940 else "")
            # 9:45 column → 9:40 closed candle
            c945_list.append(get_candle_signal(sym, "09:40") if show_945 else "")
            # 9:50 column → 9:45 closed candle
            c950_list.append(get_candle_signal(sym, "09:45") if show_950 else "")
        df['9:40'] = c940_list
        df['9:45'] = c945_list
        df['9:50'] = c950_list
else:
    df['9:40'] = ""
    df['9:45'] = ""
    df['9:50'] = ""

# ─────────────────────────────────────────────────────────────
# HEADER ROW
# ─────────────────────────────────────────────────────────────
sectors    = ['All'] + sorted(df['Sector'].dropna().unique().tolist())
top_gainer = df.iloc[0]['Symbol'] if len(df) > 0 else '-'
max_chg    = df['Chg %'].max()
last_day   = get_last_trading_day()

c1, c2, c3 = st.columns([3, 5, 2])

with c1:
    st.markdown(f"""
    <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; padding:6px 0;">
        <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:6px; padding:5px 12px; text-align:center;">
            <div style="font-size:10px; color:#6b7280; font-weight:600;">STOCKS</div>
            <div style="font-size:18px; font-weight:700; color:#16a34a; line-height:1.2;">{len(df)}</div>
        </div>
        <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:6px; padding:5px 12px; text-align:center;">
            <div style="font-size:10px; color:#6b7280; font-weight:600;">TOP GAINER</div>
            <div style="font-size:16px; font-weight:700; color:#2563eb; line-height:1.2;">{top_gainer}</div>
        </div>
        <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:6px; padding:5px 12px; text-align:center;">
            <div style="font-size:10px; color:#6b7280; font-weight:600;">MAX CHG%</div>
            <div style="font-size:16px; font-weight:700; color:#16a34a; line-height:1.2;">+{max_chg:.2f}%</div>
        </div>
        <div style="background:#fefce8; border:1px solid #fef08a; border-radius:6px; padding:5px 12px; text-align:center;">
            <div style="font-size:10px; color:#6b7280; font-weight:600;">UPDATED</div>
            <div style="font-size:14px; font-weight:700; color:#ca8a04; line-height:1.2;">{now_time}</div>
        </div>
        <div style="background:#fdf4ff; border:1px solid #e9d5ff; border-radius:6px; padding:5px 12px; text-align:center;">
            <div style="font-size:10px; color:#6b7280; font-weight:600;">ATP DATE</div>
            <div style="font-size:13px; font-weight:700; color:#7c3aed; line-height:1.2;">{last_day.strftime('%d %b')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    selected_sector = st.selectbox("", sectors, index=0, label_visibility="collapsed")

with c3:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# ─────────────────────────────────────────────────────────────
# SECTOR FILTER
# ─────────────────────────────────────────────────────────────
if selected_sector != 'All':
    df = df[df['Sector'] == selected_sector]

# ─────────────────────────────────────────────────────────────
# TABLE STYLING
# ─────────────────────────────────────────────────────────────
def color_chg(val):
    if val > 0:   return 'color: #16a34a; font-weight: 600;'
    elif val < 0: return 'color: #dc2626; font-weight: 600;'
    return ''

def color_relvol(val):
    if val >= 3:     return 'background-color: #fef9c3; font-weight: 600;'
    elif val >= 1.5: return 'background-color: #dcfce7;'
    return ''

styled_df = (
    df.style
    .applymap(color_chg, subset=['Chg %'])
    .applymap(color_relvol, subset=['Rel Vol'])
    .format({
        'Price ₹'    : '₹{:.2f}',
        'Chg %'      : '{:+.2f}%',
        'Volume'     : '{:,.0f}',
        'Rel Vol'    : '{:.2f}x',
        'Mkt Cap (B)': '₹{:.1f}B',
    })
)

st.dataframe(styled_df, use_container_width=True, height=620, hide_index=True)

# ─────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:6px; font-size:10px; color:#9ca3af; text-align:center;">
    TradingView Screener · NSE · Mkt Cap > ₹51B · New High 1M · Sorted by Chg% ↓ · ATP = Yesterday VWAP · 🟢 = Green candle
</div>
""", unsafe_allow_html=True)
