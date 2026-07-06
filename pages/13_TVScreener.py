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
    today = datetime.now(IST).date()
    tv_ref = get_trading_day_before(today + timedelta(days=1))
    atp_date = get_trading_day_before(tv_ref)
    return atp_date

def get_current_ist_time():
    return datetime.now(IST)

# ─────────────────────────────────────────────────────────────
# ATP — kal ka full day 5min VWAP
# ─────────────────────────────────────────────────────────────
def get_yesterday_atp(symbol):
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
        close  = df['Close'].values.flatten()
        volume = df['Volume'].values.flatten()
        atp = (close * volume).sum() / volume.sum()
        return round(float(atp), 2)
    except:
        return None

# ─────────────────────────────────────────────────────────────
# CANDLE CHECK
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
                col('market_cap_basic') > 51_000_000_000,
                col('exchange') == 'NSE',
                col('high') >= col('High.1M'),
            )
            .order_by('change', ascending=False)
            .limit(30)  # Extra fetch — gap filter ke baad 15 reh jayenge
            .get_scanner_data()
        )
        return count, df, None
    except Exception as e:
        return 0, pd.DataFrame(), str(e)

# ─────────────────────────────────────────────────────────────
# AUTO-REFRESH FRAGMENT — har 60s sirf yeh section re-run hoga
# Poora page reload NAHI hoga — sidebar/header stable rahenge
# ─────────────────────────────────────────────────────────────
@st.fragment(run_every=60)
def screener_fragment():
    # ── FETCH TV DATA ──
    with st.spinner("Fetching from TradingView..."):
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
    df = df[df['_opening_gap'].abs() <= 2.0].head(15)  # Gap filter + top 15

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
    # ATP FETCH — session_state cache
    # ─────────────────────────────────────────────────────────────
    if 'atp_cache' not in st.session_state:
        st.session_state['atp_cache'] = {}

    new_symbols = [s for s in df['Symbol'] if s not in st.session_state['atp_cache']]
    if new_symbols:
        with st.spinner(f"Fetching ATP for {len(new_symbols)} new stocks..."):
            for symbol in new_symbols:
                st.session_state['atp_cache'][symbol] = get_yesterday_atp(symbol)

    atp_vals, gap_vals = [], []
    for _, row in df.iterrows():
        symbol = row['Symbol']
        price  = row['Price']
        atp    = st.session_state['atp_cache'].get(symbol)
        if atp is None:
            atp_vals.append(None)
            gap_vals.append(None)
        elif price > atp:
            pct = ((price - atp) / atp) * 100
            atp_vals.append(atp)
            gap_vals.append(pct)
        else:
            pct = ((atp - price) / atp) * 100
            atp_vals.append(atp)
            gap_vals.append(-pct)
    df['ATP']     = atp_vals
    df['GapPct']  = gap_vals

    # ─────────────────────────────────────────────────────────────
    # CANDLE COLUMNS — session_state cache
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
        if key not in st.session_state['candle_cache']:
            st.session_state['candle_cache'][key] = get_candle_signal(symbol, candle_time)
        return st.session_state['candle_cache'][key]

    new_candles = [
        (row['Symbol'], t)
        for _, row in df.iterrows()
        for t, show in [("09:40", show_940), ("09:45", show_945), ("09:50", show_950)]
        if show and f"{row['Symbol']}_{t}" not in st.session_state['candle_cache']
    ]
    if new_candles:
        with st.spinner(f"Fetching {len(new_candles)} new candles..."):
            for sym, t in new_candles:
                st.session_state['candle_cache'][f"{sym}_{t}"] = get_candle_signal(sym, t)

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
    max_chg    = df['Chg'].max()
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
                <div style="font-size:10px;color:#6b7280;font-weight:600;">ATP DATE</div>
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

    def fmt_relvol(v):
        try:
            v = float(v)
            if v >= 3:     bg, color = "#fef9c3", "#854f0b"
            elif v >= 1.5: bg, color = "#dcfce7", "#166534"
            else:          bg, color = "transparent", "#374151"
            return f'<span style="background:{bg};color:{color};padding:2px 7px;border-radius:4px;font-weight:600;">{v:.2f}x</span>'
        except: return str(v)

    def fmt_entry_badges(c940, c945, c950):
        def badge(label, active):
            if active == "green":
                return f'<span style="background:#dcfce7;color:#166534;border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600;">{label}</span>'
            else:
                return f'<span style="color:#d1d5db;font-size:11px;padding:2px 5px;">{label}</span>'
        return f'{badge("9:40", c940)}&nbsp;{badge("9:45", c945)}&nbsp;{badge("9:50", c950)}'

    def fmt_atp_gap(atp, gap_pct):
        if atp is None:
            return '<span style="color:#9ca3af;">N/A</span>'
        atp_str = f"₹{float(atp):,.2f}"
        if gap_pct is None:
            return f'<div style="font-size:12px;">{atp_str}</div>'
        if gap_pct > 0:
            if gap_pct >= 5:   color = "#14532d"
            elif gap_pct >= 2: color = "#16a34a"
            else:              color = "#4ade80"
            gap_str = f'<span style="color:{color};font-weight:700;">↑ +{gap_pct:.1f}%</span>'
        else:
            gap_str = f'<span style="color:#dc2626;font-weight:600;">↓ {gap_pct:.1f}%</span>'
        return f'<div style="font-size:12px;font-weight:500;">{atp_str}</div><div style="font-size:11px;">{gap_str}</div>'

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

    # ─────────────────────────────────────────────────────────────
    # HTML TABLE — merged columns
    # ─────────────────────────────────────────────────────────────
    TH = "padding:8px 10px;font-size:11px;font-weight:700;color:#6b7280;border-bottom:2px solid #e5e7eb;white-space:nowrap;text-align:center;"
    TH_L = "padding:8px 10px;font-size:11px;font-weight:700;color:#6b7280;border-bottom:2px solid #e5e7eb;text-align:left;"
    TD = "padding:8px 10px;font-size:12px;border-bottom:1px solid #f3f4f6;white-space:nowrap;text-align:center;vertical-align:middle;"
    TD_L = "padding:8px 10px;font-size:12px;border-bottom:1px solid #f3f4f6;text-align:left;vertical-align:middle;"

    rows_html = ""
    for i, (_, row) in enumerate(df.iterrows()):
        sym    = row.get("Symbol", "")
        price  = row.get("Price", 0)
        chg    = row.get("Chg", 0)
        vol    = row.get("Volume", 0)
        relvol = row.get("RelVol", 0)
        atp    = row.get("ATP", None)
        gappct = row.get("GapPct", None)
        prevhd = row.get("PrevHighDist", None)
        prevhv = row.get("PrevHighVal", None)
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
            <td style="{TD}">{fmt_atp_gap(atp, gappct)}</td>
            <td style="{TD}">{fmt_entry_badges(c940, c945, c950)}</td>
            <td style="{TD}">{fmt_prev_high(prevhd, prevhv)}</td>
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
          <th style="{TH}">ATP / Gap</th>
          <th style="{TH}">Entry Signal</th>
          <th style="{TH}">Prev High</th>
          <th style="{TH}">Mkt Cap</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>
    """

    import streamlit.components.v1 as components
    components.html(table_html, height=len(df) * 52 + 60, scrolling=False)

    st.markdown("""
    <div style="margin-top:6px;font-size:10px;color:#9ca3af;text-align:center;">
        TradingView Screener · NSE · Mkt Cap > ₹51B · New High 1M · Gap filter ±2% · Sorted by Chg% ↓ · ATP = Yesterday VWAP
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# RUN FRAGMENT
# ─────────────────────────────────────────────────────────────
screener_fragment()
