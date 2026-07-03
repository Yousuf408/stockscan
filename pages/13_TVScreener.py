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

/* Center align all table cells */
div[data-testid="stDataFrame"] td {
    text-align: center !important;
}
div[data-testid="stDataFrame"] th {
    text-align: center !important;
}
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
            .limit(15)
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
# ATP FETCH — session_state cache (fetch once, reuse on refresh)
# ─────────────────────────────────────────────────────────────
if 'atp_cache' not in st.session_state:
    st.session_state['atp_cache'] = {}

# Sirf naye stocks fetch karo
new_symbols = [s for s in df['Symbol'] if s not in st.session_state['atp_cache']]
if new_symbols:
    with st.spinner(f"Fetching ATP for {len(new_symbols)} new stocks..."):
        for symbol in new_symbols:
            st.session_state['atp_cache'][symbol] = get_yesterday_atp(symbol)

# Ab cache se ATP lo aur Gap calculate karo
atp_vals, gap_vals, gap_pcts = [], [], []
for _, row in df.iterrows():
    symbol = row['Symbol']
    price  = row['Price ₹']
    atp    = st.session_state['atp_cache'].get(symbol)
    if atp is None:
        atp_vals.append("N/A")
        gap_vals.append("—")
        gap_pcts.append(None)
    elif price > atp:
        pct = ((price - atp) / atp) * 100
        atp_vals.append(atp)
        gap_vals.append(f"↑ +{pct:.1f}%")
        gap_pcts.append(pct)
    else:
        pct = ((atp - price) / atp) * 100
        atp_vals.append(atp)
        gap_vals.append(f"↓ -{pct:.1f}%")
        gap_pcts.append(-pct)
df['ATP'] = atp_vals
df['Gap'] = gap_vals
df['_gap_pct'] = gap_pcts  # hidden col for coloring

# ─────────────────────────────────────────────────────────────
# CANDLE COLUMNS — session_state cache
# Ek baar candle close ho gayi → fix ho gayi → cache mein rakh do
# ─────────────────────────────────────────────────────────────
now_ist  = get_current_ist_time()
now_time = now_ist.strftime('%H:%M:%S')
now_hhmm = now_ist.hour * 60 + now_ist.minute

show_940 = now_hhmm >= (9 * 60 + 45)   # 9:45+ → 9:40 candle closed
show_945 = now_hhmm >= (9 * 60 + 50)   # 9:50+ → 9:45 candle closed
show_950 = now_hhmm >= (9 * 60 + 55)   # 9:55+ → 9:50 candle closed

if 'candle_cache' not in st.session_state:
    st.session_state['candle_cache'] = {}

def get_candle_cached(symbol, candle_time, should_show):
    """Cache se lo — nahi hai toh fetch karo"""
    if not should_show:
        return ""
    key = f"{symbol}_{candle_time}"
    if key not in st.session_state['candle_cache']:
        st.session_state['candle_cache'][key] = get_candle_signal(symbol, candle_time)
    return st.session_state['candle_cache'][key]

# Sirf naye symbols ya uncached candles fetch honge
new_candles = [
    (row['Symbol'], t)
    for _, row in df.iterrows()
    for t, show in [("09:40", show_940), ("09:45", show_945), ("09:50", show_950)]
    if show and f"{row['Symbol']}_{t}" not in st.session_state['candle_cache']
]

if new_candles:
    with st.spinner(f"Fetching {len(new_candles)} new candles..."):
        for sym, t in new_candles:
            key = f"{sym}_{t}"
            st.session_state['candle_cache'][key] = get_candle_signal(sym, t)

c940_list, c945_list, c950_list = [], [], []
for _, row in df.iterrows():
    sym = row['Symbol']
    c940_list.append(get_candle_cached(sym, "09:40", show_940))
    c945_list.append(get_candle_cached(sym, "09:45", show_945))
    c950_list.append(get_candle_cached(sym, "09:50", show_950))

df['9:40'] = c940_list
df['9:45'] = c945_list
df['9:50'] = c950_list

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
# FORMAT HELPERS
# ─────────────────────────────────────────────────────────────
def fmt_volume(v):
    try:
        v = float(v)
        if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
        if v >= 100_000:   return f"{v/100_000:.1f}L"
        if v >= 1_000:     return f"{v/1_000:.1f}K"
        return str(int(v))
    except: return str(v)

def fmt_chg(v):
    try:
        v = float(v)
        color = "#16a34a" if v > 0 else "#dc2626"
        return f'<span style="color:{color};font-weight:600;">{v:+.2f}%</span>'
    except: return str(v)

def fmt_relvol(v):
    try:
        v = float(v)
        if v >= 3:   bg = "#fef9c3"
        elif v >= 1.5: bg = "#dcfce7"
        else: bg = "transparent"
        return f'<span style="background:{bg};padding:2px 6px;border-radius:4px;font-weight:600;">{v:.2f}x</span>'
    except: return str(v)

def fmt_gap(v):
    if not isinstance(v, str) or v == "—": return '<span style="color:#9ca3af;">—</span>'
    if v.startswith("↑"):
        try:
            pct = float(v.replace("↑ +","").replace("%",""))
            if pct >= 5:   color = "#14532d"
            elif pct >= 2: color = "#16a34a"
            else:          color = "#4ade80"
        except: color = "#16a34a"
        return f'<span style="color:{color};font-weight:700;">{v}</span>'
    elif v.startswith("↓"):
        return f'<span style="color:#dc2626;font-weight:600;">{v}</span>'
    return v

def fmt_atp(v):
    try: return f"₹{float(v):,.2f}"
    except: return str(v)

def fmt_mktcap(v):
    try: return f"₹{float(v):.1f}B"
    except: return str(v)

# ─────────────────────────────────────────────────────────────
# HTML TABLE
# ─────────────────────────────────────────────────────────────
headers = ["Symbol", "Price ₹", "Chg %", "Volume", "Rel Vol", "ATP", "Gap", "9:40", "9:45", "9:50", "Mkt Cap (B)", "Sector"]

th_style = "padding:8px 10px;text-align:center;font-size:11px;font-weight:700;color:#6b7280;border-bottom:2px solid #e5e7eb;white-space:nowrap;"
th_left  = "padding:8px 10px;text-align:left;font-size:11px;font-weight:700;color:#6b7280;border-bottom:2px solid #e5e7eb;"
td_style = "padding:7px 10px;text-align:center;font-size:12px;border-bottom:1px solid #f3f4f6;white-space:nowrap;"
td_left  = "padding:7px 10px;text-align:left;font-size:12px;border-bottom:1px solid #f3f4f6;font-weight:600;"

rows_html = ""
for i, (_, row) in enumerate(df.iterrows()):
    sym     = row.get("Symbol", "")
    price   = row.get("Price ₹", "")
    chg     = row.get("Chg %", "")
    vol     = row.get("Volume", "")
    relvol  = row.get("Rel Vol", "")
    atp     = row.get("ATP", "")
    gap     = row.get("Gap", "—")
    c940    = row.get("9:40", "")
    c945    = row.get("9:45", "")
    c950    = row.get("9:50", "")
    mktcap  = row.get("Mkt Cap (B)", "")
    sector  = row.get("Sector", "")

    bg = "#f9fafb" if i % 2 == 0 else "#ffffff"

    rows_html += f"""
    <tr style="background:{bg};">
        <td style="{td_left}">
            <span id="sym_{i}" onclick="
                var sym = '{sym}';
                var el = document.getElementById('sym_{i}');
                var orig = el.innerHTML;
                function showCopied() {{
                    el.innerHTML = '<span style=\'color:#16a34a;font-weight:700;font-size:11px;\'>✓ ' + sym + '</span>';
                    setTimeout(function(){{ el.innerHTML = orig; }}, 1500);
                }}
                if (navigator.clipboard && window.isSecureContext) {{
                    navigator.clipboard.writeText(sym).then(showCopied).catch(function() {{
                        var ta = document.createElement('textarea');
                        ta.value = sym;
                        ta.style.position = 'fixed';
                        ta.style.opacity = '0';
                        document.body.appendChild(ta);
                        ta.select();
                        try {{ document.execCommand('copy'); showCopied(); }} catch(e) {{}}
                        document.body.removeChild(ta);
                    }});
                }} else {{
                    var ta = document.createElement('textarea');
                    ta.value = sym;
                    ta.style.position = 'fixed';
                    ta.style.opacity = '0';
                    document.body.appendChild(ta);
                    ta.select();
                    try {{ document.execCommand('copy'); showCopied(); }} catch(e) {{}}
                    document.body.removeChild(ta);
                }}
            " style="cursor:pointer;color:#1e40af;font-weight:700;">{sym}</span>
        </td>
        <td style="{td_style}">₹{float(price):.2f}</td>
        <td style="{td_style}">{fmt_chg(chg)}</td>
        <td style="{td_style}">{fmt_volume(vol)}</td>
        <td style="{td_style}">{fmt_relvol(relvol)}</td>
        <td style="{td_style}">{fmt_atp(atp)}</td>
        <td style="{td_style}">{fmt_gap(gap)}</td>
        <td style="{td_style}">{c940}</td>
        <td style="{td_style}">{c945}</td>
        <td style="{td_style}">{c950}</td>
        <td style="{td_style}">{fmt_mktcap(mktcap)}</td>
        <td style="{td_style};color:#6b7280;font-size:11px;">{sector}</td>
    </tr>"""

table_html = f"""
<div style="overflow-x:auto; border:1px solid #e5e7eb; border-radius:8px; margin-top:8px;">
<table style="width:100%; border-collapse:collapse; font-family:sans-serif;">
    <thead style="background:#f9fafb;">
        <tr>
            <th style="{th_left}">Symbol</th>
            <th style="{th_style}">Price ₹</th>
            <th style="{th_style}">Chg %</th>
            <th style="{th_style}">Volume</th>
            <th style="{th_style}">Rel Vol</th>
            <th style="{th_style}">ATP</th>
            <th style="{th_style}">Gap</th>
            <th style="{th_style}">9:40</th>
            <th style="{th_style}">9:45</th>
            <th style="{th_style}">9:50</th>
            <th style="{th_style}">Mkt Cap</th>
            <th style="{th_style}">Sector</th>
        </tr>
    </thead>
    <tbody>{rows_html}</tbody>
</table>
</div>
"""

import streamlit.components.v1 as components
components.html(table_html, height=len(df) * 42 + 60, scrolling=False)

# ─────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:6px; font-size:10px; color:#9ca3af; text-align:center;">
    TradingView Screener · NSE · Mkt Cap > ₹51B · New High 1M · Sorted by Chg% ↓ · ATP = Yesterday VWAP · 🟢 = Green candle
</div>
""", unsafe_allow_html=True)
