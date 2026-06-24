"""
test_ema20.py
Streamlit page — EMA20 test for today's momentum scan stocks
"""

import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="EMA20 Test", page_icon="📊", layout="wide")
st.markdown("<style>header {visibility: hidden;}</style>", unsafe_allow_html=True)

st.title("📊 EMA20 Test — Momentum Scan Stocks")
st.caption("Checks if each stock's signal price is above/below its 20 EMA")

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

SIGNAL_PRICES = {
    "DPABHUSHAN": 963.9,  "SUNDROP": 659.05,   "RAMCOSYS": 592.75,
    "JLHL": 1384.7,       "TSFINV": 406.05,    "SHAKTIPUMP": 586.3,
    "BAJAJST": 433.5,     "SAKAR": 842.0,      "KRISHANA": 684.75,
    "AETHER": 1322.9,     "AMBIKCO": 1775.0,   "ENTERO": 1188.6,
    "JYOTICNC": 761.1,    "NITTAGELA": 1713.4, "OSWALPUMPS": 434.6,
    "POLYPLEX": 1001.05,  "SANGAMIND": 559.0,  "TCIEXP": 571.0,
    "CORONA": 1950.0,     "PGIL": 2048.9,      "FAIRCHEMOR": 625.0,
    "KDDL": 3209.2,       "AUBANK": 1061.0,    "DICIND": 530.0,
    "DRREDDY": 1335.5,    "EMAMILTD": 406.5,   "HNDFDS": 558.85,
    "MANGLMCEM": 913.0,   "NOVARTIND": 1498.7, "SEDEMAC": 2941.4,
    "WHEELS": 1623.3,     "RAMCOCEM": 908.0,   "AARTISURF": 377.1,
    "AKCAPIT": 1781.1,    "ARMANFIN": 1653.3,  "BIL": 788.0,
    "BLUESTONE": 531.9,   "CHOLAHLDNG": 1646.0,"CREDITACC": 1446.4,
    "EIMCOELECO": 1799.9, "GOKEX": 858.7,      "HOMEFIRST": 1162.0,
    "INDIGO": 5177.5,     "NITINSPIN": 568.85, "OBEROIRLTY": 1760.0,
    "PRICOLLTD": 588.6,   "PSPPROJECT": 1006.9,"RUBICON": 1417.0,
    "SAATVIKGL": 475.9,   "SHARDAMOTR": 856.0, "SHRIRAMFIN": 1015.4,
    "SIYSIL": 638.0,      "SKYGOLD": 501.8,    "SPAL": 1088.85,
    "SUMICHEM": 440.9,    "TMCV": 412.8,       "VIMTALABS": 582.5,
    "DELHIVERY": 481.35,  "CAPLIPOINT": 2511.0,"ONESOURCE": 1574.7,
    "NILE": 1772.6,       "PRECWIRE": 439.55,  "LGBBROSLTD": 1590.8,
    "VIJAYA": 1320.0,     "KKCL": 510.0,       "ACC": 1346.8,
    "DENORA": 943.95,     "SMARTWORKS": 478.5, "BUTTERFLY": 677.0,
    "UNITDSPR": 1359.4,   "ICICIBANK": 1374.9, "AXISBANK": 1385.0,
    "MBAPL": 572.0,       "CHOLAFIN": 1793.7,  "EVERESTIND": 415.25,
}

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
            signal_price = SIGNAL_PRICES.get(stock, 0)

            if ticker not in close.columns:
                results.append({
                    "Stock"        : stock,
                    "Signal Price" : signal_price,
                    "EMA20"        : None,
                    "Gap to EMA"   : None,
                    "Status"       : "⚠️ No Data",
                })
                continue

            series = close[ticker].dropna()
            if len(series) < 20:
                results.append({
                    "Stock"        : stock,
                    "Signal Price" : signal_price,
                    "EMA20"        : None,
                    "Gap to EMA"   : None,
                    "Status"       : "⚠️ < 20 candles",
                })
                continue

            ema20       = round(series.ewm(span=20, adjust=False).mean().iloc[-1], 2)
            gap         = round(((signal_price - ema20) / ema20) * 100, 2) if ema20 else None
            above_below = "✅ ABOVE" if signal_price >= ema20 else "❌ BELOW"

            results.append({
                "Stock"        : stock,
                "Signal Price" : signal_price,
                "EMA20"        : ema20,
                "Gap to EMA %": f"{gap:+.2f}%" if gap is not None else "-",
                "Status"       : above_below,
            })

        df = pd.DataFrame(results)

        # ── Summary metrics ───────────────────────────────────
        above  = df[df["Status"] == "✅ ABOVE"].shape[0]
        below  = df[df["Status"] == "❌ BELOW"].shape[0]
        nodata = df[~df["Status"].isin(["✅ ABOVE", "❌ BELOW"])].shape[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Stocks", len(df))
        c2.metric("✅ Above EMA20", above)
        c3.metric("❌ Below EMA20", below)
        c4.metric("⚠️ No Data", nodata)

        st.divider()

        # ── Filter tabs ───────────────────────────────────────
        tab1, tab2, tab3 = st.tabs(["All", "✅ Above Only", "❌ Below Only"])

        def color_status(val):
            if "ABOVE" in str(val):   return "background-color: #d4edda; color: #155724;"
            if "BELOW" in str(val):   return "background-color: #f8d7da; color: #721c24;"
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
