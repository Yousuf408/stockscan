import streamlit as st
import pandas as pd
from datetime import datetime

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
page_header("TV Screener", "NSE · Mkt Cap > 51B · New High 1M")

# ─────────────────────────────────────────────────────────────
# FETCH FUNCTION
# ─────────────────────────────────────────────────────────────
def fetch_tv_data():
    try:
        from tradingview_screener import Query
        from tradingview_screener.column import col

        count, df = (Query()
            .select(
                'name',
                'close',
                'change',
                'volume',
                'relative_volume',
                'market_cap_basic',
                'sector',
                'High.1M',
                'high'
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
# HEADER ROW — Refresh button + last updated
# ─────────────────────────────────────────────────────────────
col1, col2 = st.columns([8, 2])
with col2:
    refresh = st.button("🔄 Refresh", use_container_width=True)

if refresh:
    st.rerun()

# ─────────────────────────────────────────────────────────────
# FETCH DATA
# ─────────────────────────────────────────────────────────────
with st.spinner("Fetching from TradingView..."):
    count, df, error = fetch_tv_data()

if error:
    st.error(f"❌ Error fetching data: {error}")
    st.stop()

if df.empty:
    st.warning("No stocks found. Try refreshing.")
    st.stop()

# ─────────────────────────────────────────────────────────────
# CLEAN & FORMAT DATA
# ─────────────────────────────────────────────────────────────
df = df.copy()
df = df.drop(columns=['ticker', 'high', 'High.1M'], errors='ignore')

df['change']           = df['change'].round(2)
df['relative_volume']  = df['relative_volume'].round(2)
df['market_cap_basic'] = (df['market_cap_basic'] / 1e9).round(1)

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
# FILTERS — Sector
# ─────────────────────────────────────────────────────────────
sectors = ['All'] + sorted(df['Sector'].dropna().unique().tolist())
selected_sector = st.selectbox("Filter by Sector", sectors, index=0)

if selected_sector != 'All':
    df = df[df['Sector'] == selected_sector]

# ─────────────────────────────────────────────────────────────
# STATS ROW
# ─────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="display:flex; gap:16px; margin:12px 0 16px 0; flex-wrap:wrap;">
    <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:10px 20px; min-width:120px;">
        <div style="font-size:11px; color:#6b7280; font-weight:600;">TOTAL STOCKS</div>
        <div style="font-size:22px; font-weight:700; color:#16a34a;">{len(df)}</div>
    </div>
    <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:10px 20px; min-width:120px;">
        <div style="font-size:11px; color:#6b7280; font-weight:600;">TOP GAINER</div>
        <div style="font-size:22px; font-weight:700; color:#2563eb;">{df.iloc[0]['Symbol'] if len(df) > 0 else '-'}</div>
    </div>
    <div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:10px 20px; min-width:120px;">
        <div style="font-size:11px; color:#6b7280; font-weight:600;">MAX CHG%</div>
        <div style="font-size:22px; font-weight:700; color:#2563eb;">+{df['Chg %'].max():.2f}%</div>
    </div>
    <div style="background:#fefce8; border:1px solid #fef08a; border-radius:8px; padding:10px 20px; min-width:120px;">
        <div style="font-size:11px; color:#6b7280; font-weight:600;">LAST UPDATED</div>
        <div style="font-size:18px; font-weight:700; color:#ca8a04;">{datetime.now().strftime('%H:%M:%S')}</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# TABLE
# ─────────────────────────────────────────────────────────────
def color_chg(val):
    if val > 0:
        return 'color: #16a34a; font-weight: 600;'
    elif val < 0:
        return 'color: #dc2626; font-weight: 600;'
    return ''

def color_relvol(val):
    if val >= 3:
        return 'background-color: #fef9c3; font-weight: 600;'
    elif val >= 1.5:
        return 'background-color: #dcfce7;'
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

st.dataframe(
    styled_df,
    use_container_width=True,
    height=600,
    hide_index=True,
)

# ─────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:16px; font-size:11px; color:#9ca3af; text-align:center;">
    Data source: TradingView Screener · NSE · Mkt Cap &gt; ₹51B · New High 1 Month · Sorted by Chg% ↓
</div>
""", unsafe_allow_html=True)
