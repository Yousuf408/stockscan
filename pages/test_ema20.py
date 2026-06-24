"""
test_ema20.py
Streamlit page — EMA20 test for today's momentum scan stocks
Checks: yesterday's close vs EMA20 as of yesterday
"""

import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="EMA20 Test", page_icon="📊", layout="wide")
st.markdown("<style>header {visibility: hidden;}</style>", unsafe_allow_html=True)

st.title("📊 EMA20 Test — Momentum Scan Stocks")
st.caption("Checks if yesterday's close was above/below 20 EMA (as of yesterday)")

# ── All stocks from today's momentum scan ────────────────────
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

# ── Fetch button ─────────────────────────────────────────────
if st.button("🚀 Fetch EMA20 for All Stocks", use_container_width=True, type="primary"):
    with st.spinner(f"Fetching 60d daily data for {len(STOCKS)} stocks from yfinance..."):
        tickers = [f"{s}.NS" for s in STOCKS]
        try:
            raw = yf.download(
                tickers,
                period="60d",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
        except Exception as e:
            st.error(f"yfinance download failed: {e}")
            st.stop()

        if "Close" not in raw:
            st.error("No Close data returned from yfinance.")
            st.stop()

        close = raw["Close"]
        results = []

        for stock in STOCKS:
            ticker = f"{stock}.NS"

            # ── No data at all ────────────────────────────────
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

            # ── Need at least 21 rows (20 for EMA + 1 for iloc[-2]) ──
            if len(series) < 21:
                results.append({
                    "Stock"          : stock,
                    "Yesterday Close": None,
                    "EMA20 Yesterday": None,
                    "Gap to EMA %"   : "-",
                    "Status"         : "⚠️ < 21 candles",
                })
                continue

            # ── Use iloc[-2] = yesterday ──────────────────────
            ema_series       = series.ewm(span=20, adjust=False).mean()
            yesterday_close  = round(float(series.iloc[-2]), 2)
            ema20_yesterday  = round(float(ema_series.iloc[-2]), 2)
            gap              = round(((yesterday_close - ema20_yesterday) / ema20_yesterday) * 100, 2)
            above_below      = "✅ ABOVE" if yesterday_close >= ema20_yesterday else "❌ BELOW"

            results.append({
                "Stock"          : stock,
                "Yesterday Close": yesterday_close,
                "EMA20 Yesterday": ema20_yesterday,
                "Gap to EMA %"   : f"{gap:+.2f}%",
                "Status"         : above_below,
            })

        df = pd.DataFrame(results)

        # ── Summary metrics ───────────────────────────────────
        above  = df[df["Status"] == "✅ ABOVE"].shape[0]
        below  = df[df["Status"] == "❌ BELOW"].shape[0]
        nodata = df[~df["Status"].isin(["✅ ABOVE", "❌ BELOW"])].shape[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Stocks",    len(df))
        c2.metric("✅ Above EMA20",  above)
        c3.metric("❌ Below EMA20",  below)
        c4.metric("⚠️ No Data",      nodata)

        st.divider()

        # ── Filter tabs ───────────────────────────────────────
        tab1, tab2, tab3 = st.tabs(["All", "✅ Above Only", "❌ Below Only"])

        def color_status(val):
            if "ABOVE" in str(val): return "background-color: #d4edda; color: #155724;"
            if "BELOW" in str(val): return "background-color: #f8d7da; color: #721c24;"
            return "background-color: #fff3cd; color: #856404;"

        with tab1:
            st.dataframe(
                df.style.applymap(color_status, subset=["Status"]),
                use_container_width=True,
                height=600,
            )
        with tab2:
            df_above = df[df["Status"] == "✅ ABOVE"]
            st.dataframe(
                df_above.style.applymap(color_status, subset=["Status"]),
                use_container_width=True,
                height=min(600, 40 + len(df_above) * 35),
            )
        with tab3:
            df_below = df[df["Status"] == "❌ BELOW"]
            st.dataframe(
                df_below.style.applymap(color_status, subset=["Status"]),
                use_container_width=True,
                height=min(600, 40 + len(df_below) * 35),
            )
else:
    st.info("👆 Click the button above to fetch EMA20 values for all stocks.")
