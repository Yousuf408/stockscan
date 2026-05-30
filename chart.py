# ══════════════════════════════════════════
#  TRADESENTRY — chart.py
#  Reusable chart module
#  Usage: from chart import render_chart
#  Works with any page — Watchlist, Prewatch, Sectors
# ══════════════════════════════════════════

import streamlit as st
import yfinance as yf
import json
import pandas as pd
import numpy as np
import pytz
from datetime import datetime, timedelta

import sys, os
sys.path.append(os.path.dirname(__file__))
from stocks import get_stock_token

IST = pytz.timezone("Asia/Kolkata")

# ══════════════════════════════════════════
#  TIMEFRAME CONFIG
# ══════════════════════════════════════════

TIMEFRAMES = {
    "FIVE_MINUTE":    {"label": "5m",  "days": 5,    "angel": "FIVE_MINUTE"},
    "FIFTEEN_MINUTE": {"label": "15m", "days": 15,   "angel": "FIFTEEN_MINUTE"},
    "ONE_HOUR":       {"label": "1h",  "days": 60,   "angel": "ONE_HOUR"},
    "ONE_DAY":        {"label": "1D",  "days": 365,  "angel": "ONE_DAY"},
    "ONE_WEEK":       {"label": "1W",  "days": 730,  "angel": "ONE_WEEK"},
    "ONE_MONTH":      {"label": "1M",  "days": 1825, "angel": "ONE_MONTH"},
}

VALID_TFS = list(TIMEFRAMES.keys())


# ══════════════════════════════════════════
#  SYMBOL HELPER
# ══════════════════════════════════════════

def clean_symbol(symbol: str) -> str:
    return symbol.lstrip("$").strip().upper().replace(".NS", "").replace(".BO", "")


# ══════════════════════════════════════════
#  DATA FETCH
#  Primary:  Angel One getCandleData()
#  Fallback: yfinance
# ══════════════════════════════════════════

@st.cache_data(ttl=300)
def fetch_ohlcv(symbol: str, exchange: str, interval: str) -> list:
    """
    Returns list of [timestamp, open, high, low, close, volume]
    Tries Angel One first, falls back to yfinance.
    """
    days     = TIMEFRAMES[interval]["days"]
    to_dt    = datetime.now(IST)
    from_dt  = to_dt - timedelta(days=days)
    fromdate = from_dt.strftime("%Y-%m-%d 09:15")
    todate   = to_dt.strftime("%Y-%m-%d 15:30")
    exch     = "NSE" if exchange == "NS" else "BSE"
    token    = get_stock_token(clean_symbol(symbol))

    # ── Angel One ──
    if token:
        try:
            import pyotp
            from SmartApi import SmartConnect
            obj  = SmartConnect(api_key=st.secrets["API_KEY"])
            totp = pyotp.TOTP(st.secrets["TOTP_SECRET"]).now()
            sess = obj.generateSession(
                st.secrets["CLIENT_CODE"],
                st.secrets["PASSWORD"], totp
            )
            if sess.get("status"):
                resp = obj.getCandleData({
                    "exchange":    exch,
                    "symboltoken": str(token),
                    "interval":    interval,
                    "fromdate":    fromdate,
                    "todate":      todate,
                })
                if resp and resp.get("status") and resp.get("data"):
                    print(f"[Chart] Angel One ✅ {symbol} — {len(resp['data'])} candles")
                    return resp["data"]
        except Exception as e:
            print(f"[Chart] Angel One failed: {e}")

    # ── yfinance fallback ──
    yf_map = {
        "FIVE_MINUTE":    ("5d",   "5m"),
        "FIFTEEN_MINUTE": ("15d",  "15m"),
        "ONE_HOUR":       ("60d",  "1h"),
        "ONE_DAY":        ("1y",   "1d"),
        "ONE_WEEK":       ("5y",   "1wk"),
        "ONE_MONTH":      ("10y",  "1mo"),
    }
    period, yf_interval = yf_map.get(interval, ("1y", "1d"))
    try:
        sym    = clean_symbol(symbol)
        suffix = ".NS" if exchange == "NS" else ".BO"
        hist   = yf.Ticker(f"{sym}{suffix}").history(period=period, interval=yf_interval)
        if hist is not None and not hist.empty:
            rows = []
            for ts, row in hist.iterrows():
                rows.append([
                    str(ts),
                    round(float(row["Open"]),  2),
                    round(float(row["High"]),  2),
                    round(float(row["Low"]),   2),
                    round(float(row["Close"]), 2),
                    int(row["Volume"])
                ])
            print(f"[Chart] yfinance ✅ {symbol} — {len(rows)} candles")
            return rows
    except Exception as e:
        print(f"[Chart] yfinance failed: {e}")

    return []


# ══════════════════════════════════════════
#  MAIN RENDER FUNCTION
#  Call this from any page:
#    from chart import render_chart
#    render_chart("TCS", "NS")
# ══════════════════════════════════════════

def render_chart(symbol: str, exchange: str):
    """
    Renders a premium TradingView-style chart.
    - Timeframe buttons: 5m, 15m, 1h, 1D, 1W, 1M
    - Indicators: EMA 20 (orange), EMA 200 (blue), Volume
    - Data: Angel One primary, yfinance fallback
    - Library: Lightweight Charts (TradingView open source)
    """
    exch_label = "NSE" if exchange == "NS" else "BSE"

    # ── Timeframe session state ──
    tf_key = f"chart_tf_{symbol}"  # per-symbol key so tabs don't clash
    if tf_key not in st.session_state or st.session_state[tf_key] not in VALID_TFS:
        st.session_state[tf_key] = "ONE_DAY"

    # ── Timeframe buttons ──
    tf_cols = st.columns(len(TIMEFRAMES))
    for i, (tf_id, tf_cfg) in enumerate(TIMEFRAMES.items()):
        with tf_cols[i]:
            is_active = st.session_state[tf_key] == tf_id
            if st.button(
                tf_cfg["label"],
                key=f"tf_{tf_id}_{symbol}_{exchange}",
                use_container_width=True,
                type="primary" if is_active else "secondary"
            ):
                st.session_state[tf_key] = tf_id
                st.rerun()

    selected_tf = st.session_state[tf_key]

    # ── Fetch data ──
    with st.spinner(f"Loading {symbol} · {TIMEFRAMES[selected_tf]['label']}..."):
        raw = fetch_ohlcv(symbol, exchange, selected_tf)

    if not raw:
        st.error(f"❌ No chart data for {symbol}")
        return

    # ── Build DataFrame ──
    df = pd.DataFrame(raw, columns=["time","open","high","low","close","volume"])
    df["time"]   = pd.to_datetime(df["time"]).astype("int64") // 10**9
    df[["open","high","low","close","volume"]] = df[["open","high","low","close","volume"]].astype(float)
    df = df.drop_duplicates("time").sort_values("time").reset_index(drop=True)

    # ── EMAs ──
    df["ema20"]  = df["close"].ewm(span=20,  adjust=False).mean().round(2)
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean().round(2)

    last      = df["close"].iloc[-1]
    prev      = df["close"].iloc[-2] if len(df) > 1 else last
    chg       = last - prev
    chgp      = (chg / prev * 100) if prev else 0
    chg_color = "#089981" if chg >= 0 else "#f23645"

    # ── JSON for JS ──
    candles_js  = json.dumps(df[["time","open","high","low","close"]].to_dict("records"))
    volumes_js  = json.dumps([
        {"time": r["time"], "value": r["volume"],
         "color": "#089981" if r["close"] >= r["open"] else "#f23645"}
        for _, r in df.iterrows()
    ])
    ema20_js  = json.dumps([
        {"time": r["time"], "value": r["ema20"]}
        for _, r in df.iterrows() if not np.isnan(r["ema20"])
    ])
    ema200_js = json.dumps([
        {"time": r["time"], "value": r["ema200"]}
        for _, r in df.iterrows() if not np.isnan(r["ema200"])
    ])

    e20_val  = df["ema20"].iloc[-1]
    e200_val = df["ema200"].iloc[-1]

    # ── Lightweight Charts HTML ──
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#fff; font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif; }}
  #wrap {{
    position:relative; width:100%; height:560px;
    border:1px solid #e5e7eb; border-radius:8px;
    overflow:hidden; background:#fff;
  }}
  #chart {{ width:100%; height:100%; }}
  #leg {{
    position:absolute; top:10px; left:10px;
    background:rgba(255,255,255,0.93);
    border:1px solid #e5e7eb; border-radius:6px;
    padding:8px 12px; z-index:10; min-width:190px;
    backdrop-filter:blur(4px);
  }}
  .l-sym  {{ font-weight:700; font-size:13px; color:#111; }}
  .l-px   {{ font-size:17px; font-weight:700; margin:2px 0; }}
  .l-chg  {{ font-size:11px; }}
  .l-inds {{ margin-top:5px; font-size:11px; color:#555; }}
  .l-row  {{ display:flex; align-items:center; gap:6px; margin-top:2px; }}
  .dot    {{ width:10px; height:3px; border-radius:2px; }}
</style>
</head>
<body>
<div id="wrap">
  <div id="chart"></div>
  <div id="leg">
    <div class="l-sym">{symbol} <span style="color:#888;font-size:10px">{exch_label}</span></div>
    <div class="l-px"  id="lp" style="color:{chg_color}">&#8377;{last:,.2f}</div>
    <div class="l-chg" id="lc" style="color:{chg_color}">{chg:+.2f} ({chgp:+.2f}%)</div>
    <div class="l-inds">
      <div class="l-row"><span class="dot" style="background:#f59e0b"></span><span id="le20">EMA 20: &#8377;{e20_val:,.2f}</span></div>
      <div class="l-row"><span class="dot" style="background:#3b82f6"></span><span id="le200">EMA 200: &#8377;{e200_val:,.2f}</span></div>
    </div>
  </div>
</div>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<script>
const {{ createChart }} = LightweightCharts;
const el = document.getElementById('chart');
const chart = createChart(el, {{
  width: el.offsetWidth, height: 560,
  layout: {{ background:{{color:'#fff'}}, textColor:'#374151', fontSize:11 }},
  grid:   {{ vertLines:{{color:'#f3f4f6'}}, horzLines:{{color:'#f3f4f6'}} }},
  crosshair: {{ mode:1,
    vertLine:{{color:'#9ca3af',width:1,style:2}},
    horzLine:{{color:'#9ca3af',width:1,style:2}}
  }},
  rightPriceScale: {{ borderColor:'#e5e7eb', scaleMargins:{{top:0.08,bottom:0.22}} }},
  timeScale: {{ borderColor:'#e5e7eb', timeVisible:true, secondsVisible:false }},
  watermark: {{ visible:false }},
}});

const cs = chart.addCandlestickSeries({{
  upColor:'#089981', downColor:'#f23645',
  borderUpColor:'#089981', borderDownColor:'#f23645',
  wickUpColor:'#089981', wickDownColor:'#f23645',
}});
cs.setData({candles_js});

const vs = chart.addHistogramSeries({{ priceScaleId:'vol' }});
chart.priceScale('vol').applyOptions({{ scaleMargins:{{top:0.8,bottom:0}} }});
vs.setData({volumes_js});

// ── EMA 20 — with price label on right axis ──
const e20s = chart.addLineSeries({{
  color: '#f59e0b',
  lineWidth: 1.5,
  priceLineVisible: true,
  lastValueVisible: true,
  priceLineStyle: 2,
  priceLineColor: '#f59e0b',
  priceLineWidth: 1,
  lastPriceAnimation: 0,
  title: 'EMA 20',
}});
e20s.setData({ema20_js});

// ── EMA 200 — with price label on right axis ──
const e200s = chart.addLineSeries({{
  color: '#3b82f6',
  lineWidth: 1.5,
  priceLineVisible: true,
  lastValueVisible: true,
  priceLineStyle: 2,
  priceLineColor: '#3b82f6',
  priceLineWidth: 1,
  lastPriceAnimation: 0,
  title: 'EMA 200',
}});
e200s.setData({ema200_js});

chart.timeScale().fitContent();

// ── Zoom buttons ──
const btnStyle = `
  background:#fff; border:1px solid #e5e7eb;
  border-radius:4px; padding:4px 10px;
  font-size:14px; cursor:pointer; color:#374151;
  font-weight:600; margin-left:4px;
  transition: background 0.15s;
`;
const toolbar = document.createElement('div');
toolbar.style.cssText = 'position:absolute;top:10px;right:10px;z-index:20;display:flex;align-items:center;';

const btnZoomIn  = document.createElement('button');
const btnZoomOut = document.createElement('button');
const btnReset   = document.createElement('button');

btnZoomIn.innerHTML  = '+';
btnZoomOut.innerHTML = '−';
btnReset.innerHTML   = '⟳';
btnReset.title       = 'Reset view';

[btnZoomIn, btnZoomOut, btnReset].forEach(b => {{
  b.style.cssText = btnStyle;
  b.onmouseover = () => b.style.background = '#f9fafb';
  b.onmouseout  = () => b.style.background = '#fff';
}});

btnZoomIn.onclick  = () => chart.timeScale().scrollToPosition(
  chart.timeScale().scrollPosition() + 5, true
);
btnZoomOut.onclick = () => chart.timeScale().scrollToPosition(
  chart.timeScale().scrollPosition() - 5, true
);
btnReset.onclick   = () => chart.timeScale().fitContent();

toolbar.appendChild(btnZoomIn);
toolbar.appendChild(btnZoomOut);
toolbar.appendChild(btnReset);
document.getElementById('wrap').appendChild(toolbar);

// ── Crosshair legend update ──
chart.subscribeCrosshairMove(p => {{
  if (!p.time || !p.point) return;
  const b = p.seriesData.get(cs);
  if (!b) return;
  const chg = b.close - b.open;
  const pct = (chg/b.open*100).toFixed(2);
  const col = b.close >= b.open ? '#089981' : '#f23645';
  document.getElementById('lp').style.color = col;
  document.getElementById('lp').textContent = '\u20B9' + b.close.toLocaleString('en-IN',{{minimumFractionDigits:2,maximumFractionDigits:2}});
  document.getElementById('lc').style.color = col;
  document.getElementById('lc').textContent = (chg>=0?'+':'') + chg.toFixed(2) + ' (' + (chg>=0?'+':'') + pct + '%)';
  const v20  = p.seriesData.get(e20s);
  const v200 = p.seriesData.get(e200s);
  if (v20)  document.getElementById('le20').textContent  = 'EMA 20: \u20B9'  + v20.value.toLocaleString('en-IN',{{minimumFractionDigits:2}});
  if (v200) document.getElementById('le200').textContent = 'EMA 200: \u20B9' + v200.value.toLocaleString('en-IN',{{minimumFractionDigits:2}});
}});

new ResizeObserver(() => chart.applyOptions({{width:el.offsetWidth}})).observe(el);
</script>
</body>
</html>"""

    st.components.v1.html(html, height=580, scrolling=False)

    # ── Stats row ──
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Last Close",  f"\u20B9{last:,.2f}", delta=f"{chg:+.2f} ({chgp:+.2f}%)")
    with c2: st.metric("Period High", f"\u20B9{df['high'].max():,.2f}")
    with c3: st.metric("Period Low",  f"\u20B9{df['low'].min():,.2f}")
    with c4: st.metric("EMA 20",      f"\u20B9{e20_val:,.2f}")
    with c5: st.metric("EMA 200",     f"\u20B9{e200_val:,.2f}")
