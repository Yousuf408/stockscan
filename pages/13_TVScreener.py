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

# ─────────────────────────────────────────────────────────────
# COMPACT CSS
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Remove default streamlit top padding */
.block-container { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; }

/* Compact selectbox */
div[data-testid="stSelectbox"] { margin-top: 0 !important; margin-bottom: 0 !important; }

/* Compact button */
div[data-testid="stButton"] button {
    padding: 4px 12px !important;
    font-size: 12px !important;
    height: 32px !important;
}

/* Hide streamlit header gap */
div[data-testid="stVerticalBlock"] { gap: 0.3rem !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# FETCH FUNCTION
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
# TOP BAR — Title + Filters + Refresh in one row
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
# HEADER ROW — all controls in one line
# ─────────────────────────────────────────────────────────────
sectors = ['All'] + sorted(df['Sector'].dropna().unique().tolist())
top_gainer = df.iloc[0]['Symbol'] if len(df) > 0 else '-'
max_chg    = df['Chg %'].max()
now_time   = datetime.now().strftime('%H:%M:%S')

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
    </div>
    """, unsafe_allow_html=True)

with c2:
    selected_sector = st.selectbox("", sectors, index=0, label_visibility="collapsed")

with c3:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

# ─────────────────────────────────────────────────────────────
# FILTER
# ─────────────────────────────────────────────────────────────
if selected_sector != 'All':
    df = df[df['Sector'] == selected_sector]

# ─────────────────────────────────────────────────────────────
# TABLE
# ─────────────────────────────────────────────────────────────
def color_chg(val):
    if val > 0:   return 'color: #16a34a; font-weight: 600;'
    elif val < 0: return 'color: #dc2626; font-weight: 600;'
    return ''

def color_relvol(val):
    if val >= 3:   return 'background-color: #fef9c3; font-weight: 600;'
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
    TradingView Screener · NSE · Mkt Cap > ₹51B · New High 1M · Sorted by Chg% ↓
</div>
""", unsafe_allow_html=True)
