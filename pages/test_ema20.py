"""
test_ema20.py
Streamlit page — EMA20 test for today's momentum scan stocks
Auto-runs on page load. Cached for 1 hour (EMA20 is daily data).
"""

import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="EMA20 Test", page_icon="📊", layout="wide")
st.markdown("<style>header {visibility: hidden;}</style>", unsafe_allow_html=True)

st.title("📊 EMA20 Test — Momentum Scan Stocks")
st.caption("Condition: Yesterday close must be ABOVE EMA20 AND within 8% distance")

STOCKS = [
    "DPABHUSHAN", "SUNDROP", "RAMCOSYS", "JLHL", "TSFINV",
    "SHAKTIPUMP", "BAJAJST", "SAKAR", "KRISHANA", "AETHER",
    "AMBIKCO", "ENTERO", "JYOTICNC", "NITTAGELA", "OSWALPUMPS",
    "POLYPLEX", "SANGAMIND", "TCIEXP", "CORONA", "PGIL",
    "FAIRCHEMOR", "KDDL", "AUBANK", "DICIND", "DRREDDY",
    "EMAMILTD", "HNDFDS", "MANGLMCEM", "NOVARTIND", "SEDEMAC",
    "WHEELS", "RAMCOCEM", "AARTISURF", "AKCAPIT", "ARMANFIN",
    "BIL", "BLUESTONE", "CHOLAHLDNG", "CREDITACC", "EIMCOELECO",
    "GOKEX", "HOMEFIRST", "INDIGO", "NITINSPIN", "OBEROIRLTY",
    "PRICOLLTD", "PSPPROJECT", "RUBICON", "SAATVIKGL", "SHARDAMOTR",
    "SHRIRAMFIN", "SIYSIL", "SKYGOLD", "SPAL", "SUMICHEM",
    "TMCV", "VIMTALABS", "DELHIVERY", "CAPLIPOINT", "ONESOURCE",
    "NILE", "PRECWIRE", "LGBBROSLTD", "VIJAYA", "KKCL",
    "ACC", "DENORA", "SMARTWORKS", "BUTTERFLY", "UNITDSPR",
    "ICICIBANK", "AXISBANK", "MBAPL", "CHOLAFIN", "EVERESTIND"
]

EMA_DISTANCE_LIMIT = 8.0

# ── Cached fetch — runs once, valid for 1 hour ───────────────
@st.cache_data(ttl=3600, show_spinner="Fetching EMA20 data from yfinance...")
def fetch_ema20(stocks):
    tickers = [f"{s}.NS" for s in stocks]
    raw = yf.download(
        tickers,
        period="60d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    if "Close" not in raw:
        return pd.DataFrame()

    close   = raw["Close"]
    results = []

    for stock in stocks:
        ticker = f"{stock}.NS"

        if ticker not in close.columns:
            results.append({
                "Stock"          : stock,
                "Yesterday Close": None,
                "EMA20 Yesterday": None,
                "Gap to EMA %"   : "-",
                "Status"         : "⚠️ No Data",
            })
            continue

        series = close[ticker].dropna()

        if len(series) < 21:
            results.append({
                "Stock"          : stock,
                "Yesterday Close": None,
                "EMA20 Yesterday": None,
                "Gap to EMA %"   : "-",
                "Status"         : "⚠️ < 21 candles",
            })
            continue

        ema_series      = series.ewm(span=20, adjust=False).mean()
        yesterday_close = round(float(series.iloc[-2]), 2)
        ema20_yesterday = round(float(ema_series.iloc[-2]), 2)
        gap             = round(((yesterday_close - ema20_yesterday) / ema20_yesterday) * 100, 2)

        if yesterday_close < ema20_yesterday:
            status = "❌ BELOW EMA"
        elif gap > EMA_DISTANCE_LIMIT:
            status = "🔼 TOO EXTENDED"
        else:
            status = "✅ PASS"

        results.append({
            "Stock"          : stock,
            "Yesterday Close": yesterday_close,
            "EMA20 Yesterday": ema20_yesterday,
            "Gap to EMA %"   : f"{gap:+.2f}%",
            "Status"         : status,
        })

    return pd.DataFrame(results)


# ── Auto-run on page load ─────────────────────────────────────
df = fetch_ema20(tuple(STOCKS))  # tuple so it's hashable for cache

if df.empty:
    st.error("No data returned from yfinance.")
    st.stop()

# ── Summary metrics ───────────────────────────────────────────
passed   = df[df["Status"] == "✅ PASS"].shape[0]
extended = df[df["Status"] == "🔼 TOO EXTENDED"].shape[0]
below    = df[df["Status"] == "❌ BELOW EMA"].shape[0]
nodata   = df[~df["Status"].isin(["✅ PASS", "🔼 TOO EXTENDED", "❌ BELOW EMA"])].shape[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total",           len(df))
c2.metric("✅ Pass",          passed)
c3.metric("🔼 Too Extended",  extended)
c4.metric("❌ Below EMA",     below)
c5.metric("⚠️ No Data",       nodata)

# ── Manual refresh button (optional) ─────────────────────────
if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()

st.divider()

# ── Filter tabs ───────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "All", "✅ Pass", "🔼 Too Extended", "❌ Below EMA"
])

def color_status(val):
    if "PASS"     in str(val): return "background-color: #d4edda; color: #155724;"
    if "EXTENDED" in str(val): return "background-color: #fff3cd; color: #856404;"
    if "BELOW"    in str(val): return "background-color: #f8d7da; color: #721c24;"
    return "background-color: #e2e8f0; color: #475569;"

with tab1:
    st.dataframe(
        df.style.applymap(color_status, subset=["Status"]),
        use_container_width=True, height=600,
    )
with tab2:
    df_pass = df[df["Status"] == "✅ PASS"]
    st.dataframe(
        df_pass.style.applymap(color_status, subset=["Status"]),
        use_container_width=True,
        height=min(600, 40 + len(df_pass) * 35),
    )
with tab3:
    df_ext = df[df["Status"] == "🔼 TOO EXTENDED"]
    st.dataframe(
        df_ext.style.applymap(color_status, subset=["Status"]),
        use_container_width=True,
        height=min(600, 40 + len(df_ext) * 35),
    )
with tab4:
    df_below = df[df["Status"] == "❌ BELOW EMA"]
    st.dataframe(
        df_below.style.applymap(color_status, subset=["Status"]),
        use_container_width=True,
        height=min(600, 40 + len(df_below) * 35),
    )
