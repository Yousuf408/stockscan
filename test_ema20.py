"""
test_ema20.py
Standalone test — checks EMA20 for today's momentum scan stocks
Run: python test_ema20.py
"""

import yfinance as yf
import pandas as pd

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

# ── Prev close from your Supabase data (signal_price ≈ prev close approx) ──
# Using signal_price as reference — just to cross-check direction
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

def fetch_ema20(stocks):
    tickers = [f"{s}.NS" for s in stocks]
    print(f"Fetching 60d daily data for {len(tickers)} stocks from yfinance...")

    try:
        raw = yf.download(
            tickers,
            period="60d",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as e:
        print(f"yfinance download failed: {e}")
        return []

    if "Close" not in raw:
        print("No Close data returned.")
        return []

    close = raw["Close"]
    results = []

    for stock in stocks:
        ticker = f"{stock}.NS"
        if ticker not in close.columns:
            results.append({
                "Stock"        : stock,
                "Signal Price" : SIGNAL_PRICES.get(stock, "-"),
                "EMA20"        : "NOT FOUND",
                "Status"       : "❌ No Data",
            })
            continue

        series = close[ticker].dropna()
        if len(series) < 20:
            results.append({
                "Stock"        : stock,
                "Signal Price" : SIGNAL_PRICES.get(stock, "-"),
                "EMA20"        : "INSUFFICIENT",
                "Status"       : "⚠️ < 20 candles",
            })
            continue

        ema20       = round(series.ewm(span=20, adjust=False).mean().iloc[-1], 2)
        prev_close  = SIGNAL_PRICES.get(stock, 0)
        above_below = "✅ ABOVE" if prev_close >= ema20 else "❌ BELOW"

        results.append({
            "Stock"        : stock,
            "Signal Price" : prev_close,
            "EMA20"        : ema20,
            "Status"       : above_below,
        })

    return results


if __name__ == "__main__":
    results = fetch_ema20(STOCKS)

    if not results:
        print("No results.")
    else:
        df = pd.DataFrame(results)
        df["EMA20"] = pd.to_numeric(df["EMA20"], errors="coerce")

        print("\n" + "="*65)
        print(f"{'Stock':<15} {'Signal Price':>13} {'EMA20':>10} {'Status':>15}")
        print("="*65)
        for _, row in df.iterrows():
            ema_str = f"{row['EMA20']:.2f}" if pd.notna(row["EMA20"]) else str(row["EMA20"])
            print(f"{row['Stock']:<15} {str(row['Signal Price']):>13} {ema_str:>10} {row['Status']:>15}")

        print("="*65)

        # ── Summary ──────────────────────────────────────────
        above = df[df["Status"] == "✅ ABOVE"].shape[0]
        below = df[df["Status"] == "❌ BELOW"].shape[0]
        nodata = df[~df["Status"].isin(["✅ ABOVE", "❌ BELOW"])].shape[0]

        print(f"\nSummary: ✅ Above EMA20: {above} | ❌ Below: {below} | ⚠️ No Data: {nodata}")
        print(f"Total stocks checked: {len(results)}")
