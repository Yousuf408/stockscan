# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER PAGE (9_TVScreener.py)
# Main orchestration: Fragment-based live market view + market-closed fallback
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
from datetime import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: PAGE CONFIGURATION & STYLES
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="TV Screener · TradeSentry",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: IMPORTS FROM TV_SCREENER PACKAGE
# ─────────────────────────────────────────────────────────────────────────────

from tv_screener.strategy import (
    fetch_tv_data, clean_tv_data, prepare_tv_data_for_processing,
    get_yesterday_poc, get_crossover_signal, calc_gap_pct
)
from tv_screener.backend import (
    get_last_trading_day, get_current_ist_time, is_market_hours,
    get_all_candle_signals, get_5day_median_volume,
    calc_prev_high_dist, get_prev_high_val
)
from tv_screener.database import (
    get_supabase, supabase_get_cached_row, supabase_get_all_for_date,
    supabase_save_row, init_session_caches, get_supabase_stats
)
from tv_screener.frontend import render_stock_table, render_market_closed_view, fmt_entry_badges, display_order_result
from tv_screener.algomojo import place_buy_order
from tv_screener.dhan_orders import place_dhan_order
from tv_screener.quantity_calculator import calculate_max_quantity_column, get_qty_calc_debug

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: SESSION STATE INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

init_session_caches()

if 'user_capital' not in st.session_state:
    st.session_state['user_capital'] = 100000.0

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: CAPITAL INPUT (auto-reflects on change, no separate update button)
# ─────────────────────────────────────────────────────────────────────────────

st.number_input(
    "💰 Total Capital (₹)",
    min_value=0.0,
    step=1000.0,
    key="user_capital",
    help="Capital ko 4 parts mein divide karke har stock ka Max Qty calculate hota hai (DhanHQ live margin ke hisaab se)."
)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: DHAN ACCESS TOKEN INPUT (optional manual override — no code
# edit/redeploy needed. Session-only, NOT saved anywhere permanent.
# Priority: this box > hardcoded DHAN_MANUAL_ACCESS_TOKEN > automatic TOTP.
# ─────────────────────────────────────────────────────────────────────────────

with st.expander("🔑 Dhan Access Token (optional manual override)"):
    st.text_input(
        "Paste a fresh Dhan access token here",
        type="password",
        key="user_manual_access_token",
        help="Agar khali chhodo, app automatically TOTP se token generate karega (default behavior). "
             "Sirf tab bharo jab TOTP fail/locked ho aur turant test karna ho — session-only hai, "
             "kahin save nahi hota, refresh pe khali ho jayega."
    )

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: AUTO-REFRESH FRAGMENT (MARKET OPEN MODE)
# ─────────────────────────────────────────────────────────────────────────────

@st.fragment(run_every=60)
def screener_fragment():
    """
    Live market screening fragment — runs every 60 seconds.
    
    Only executes when market is open (9:15 AM - 3:30 PM IST).
    Complete calculations: POC, Crossover, EMA-Coil, Vol5D, Entry signals.
    """
    
    # ── STEP 0: Market hours check — DISABLED FOR TESTING ──
    # Testing ke dauraan hamesha live calculation chalega, chahe market
    # khula ho ya band. Production mein wapas enable karna ho toh neeche
    # wale 3 lines uncomment karo.
    #
    # if not is_market_hours():
    #     render_market_closed_view(pd.DataFrame())
    #     return

    # ── STEP 1: FETCH TV DATA ──
    with st.spinner("Fetching Top Gainer stocks from TradingView..."):
        count, df, error = fetch_tv_data()

    if error:
        st.error(f"❌ Error: {error}")
        return

    if df.empty:
        st.warning("No stocks found.")
        return

    # ── STEP 2: CLEAN DATA ──
    df = clean_tv_data(df)

    # ── STEP 3: GAP FILTER (±2%) ──
    df['_opening_gap'] = df.apply(calc_gap_pct, axis=1)
    df = df[df['_opening_gap'].abs() <= 2.0]
    df = df.drop(columns=['_opening_gap'], errors='ignore')

    if df.empty:
        st.warning("No stocks passed gap filter.")
        return

    # ── STEP 4: CALCULATE PREV HIGH DISTANCE ──
    df['PrevHighDist'] = df.apply(calc_prev_high_dist, axis=1)
    df['PrevHighVal']  = df.apply(get_prev_high_val, axis=1)
    df = prepare_tv_data_for_processing(df)

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 5: CROSSOVER CHECK (CRITICAL FILTER)
    # 
    # Cache priority: session_state (fastest) → Supabase (persistent) 
    # → yfinance (slowest)
    # 
    # Key: crossover confirmation is permanent (once matched, cache preserves it)
    # ─────────────────────────────────────────────────────────────────────────
    
    calc_date   = get_last_trading_day()
    signal_date = datetime.now(IST).date()

    # Find symbols still needing POC (for crossover check)
    symbols_needing_poc = [s for s in df['Symbol'] if s not in st.session_state['poc_cache']]

    # Symbol -> current price lookup (used to capture signal_price the
    # first time we save a symbol — see supabase_save_row call below)
    price_lookup = dict(zip(df['Symbol'], df['Price']))

    if 'signalprice_cache' not in st.session_state:
        st.session_state['signalprice_cache'] = {}

    # Check Supabase for cached POC values
    still_missing_poc = []
    for symbol in symbols_needing_poc:
        cached_row = supabase_get_cached_row(symbol, calc_date)
        if cached_row is not None and cached_row.get('poc_value') is not None:
            st.session_state['poc_cache'][symbol] = cached_row['poc_value']
            # Also cache related fields
            if cached_row.get('vol5d_median') is not None:
                if 'vol5d_cache' not in st.session_state:
                    st.session_state['vol5d_cache'] = {}
                st.session_state['vol5d_cache'][symbol] = cached_row['vol5d_median']
            if cached_row.get('prev_high_val') is not None:
                if 'prevhigh_cache' not in st.session_state:
                    st.session_state['prevhigh_cache'] = {}
                st.session_state['prevhigh_cache'][symbol] = cached_row['prev_high_val']
            if cached_row.get('crossover_status'):
                st.session_state['crossover_cache'][symbol] = cached_row['crossover_status']
            if cached_row.get('signal_price') is not None:
                st.session_state['signalprice_cache'][symbol] = cached_row['signal_price']
        else:
            still_missing_poc.append(symbol)

    # Fetch POC for remaining symbols (parallel) — sirf market open mein.
    # Market band hone ke baad naya POC calculate nahi karna (already
    # missing hai toh agle trading-day mein hi milega, retry se koi
    # fayda nahi — sirf waste API calls).
    if still_missing_poc and not is_market_hours():
        still_missing_poc = []

    if still_missing_poc:
        with st.spinner(f"Calculating POC for {len(still_missing_poc)} stocks..."):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(get_yesterday_poc, s): s for s in still_missing_poc}
                for future in as_completed(futures):
                    sym = futures[future]
                    poc_val = future.result()
                    st.session_state['poc_cache'][sym] = poc_val
                    current_price = price_lookup.get(sym)
                    supabase_save_row(sym, signal_date, calc_date, poc_value=poc_val, price=current_price)
                    # Capture signal_price locally too (first time we see
                    # this symbol this session) so the live "% Since Signal"
                    # column works even before next Supabase read-back.
                    if sym not in st.session_state['signalprice_cache'] and current_price is not None:
                        st.session_state['signalprice_cache'][sym] = current_price

    # Check crossover signals (only for stocks not yet confirmed)
    def crossover_pure(symbol, poc_val):
        """Pure calculation for threading."""
        result = get_crossover_signal(symbol, poc_val)
        return symbol, result

    # Market band hone ke baad naya crossover-check attempt nahi karna —
    # jo stocks abhi tak unconfirmed hain ("") woh har 60s refresh pe
    # dobara check hote rehte, chahe market band ho ya khula. Yahi
    # "fetching keeps happening after close" ka root-cause tha.
    #
    # ALSO: sirf "match" (09:15/09:20) permanent nahi hai — "confirmed
    # no-match" bhi permanent hona chahiye, taaki jo stock kabhi crossover
    # nahi karega, uska baar-baar (har 60s) dobara check na ho. Lekin
    # 9:25 AM se pehle "" ka matlab "abhi candle complete hi nahi hui"
    # bhi ho sakta hai — isliye "confirmed no-match" sirf 9:25 AM ke
    # baad hi permanent maana jata hai (jab 9:15 + 9:20 dono candles
    # ka data available ho chuka ho).
    NO_MATCH_CUTOFF_HHMM = 9 * 60 + 25  # 9:25 AM IST

    crossover_symbols_to_check = []
    if is_market_hours():
        crossover_symbols_to_check = [
            s for s in df['Symbol']
            if st.session_state['crossover_cache'].get(s, "") not in ("09:15", "09:20", "NO_MATCH")
        ]

    if crossover_symbols_to_check:
        with st.spinner(f"Checking crossover for {len(crossover_symbols_to_check)} stocks..."):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(crossover_pure, s, st.session_state['poc_cache'].get(s))
                    for s in crossover_symbols_to_check
                ]
                now_hhmm_check = get_current_ist_time().hour * 60 + get_current_ist_time().minute
                for future in as_completed(futures):
                    sym, result = future.result()
                    if result in ("09:15", "09:20"):
                        st.session_state['crossover_cache'][sym] = result
                        supabase_save_row(sym, signal_date, calc_date, crossover_status=result)
                    elif now_hhmm_check >= NO_MATCH_CUTOFF_HHMM:
                        # Confirmed no-match — both candles' data was available
                        # and neither matched. Cache permanently so this stock
                        # is never re-checked again today.
                        st.session_state['crossover_cache'][sym] = "NO_MATCH"
                        supabase_save_row(sym, signal_date, calc_date, crossover_status="NO_MATCH")
                    elif sym not in st.session_state['crossover_cache']:
                        # Still before 9:25 — candle data may not be complete
                        # yet, keep as pending ("") so it gets rechecked
                        st.session_state['crossover_cache'][sym] = ""

    df['Crossover'] = df['Symbol'].map(lambda s: st.session_state['crossover_cache'].get(s, ""))

    # ── STEP 6: CROSSOVER FILTER (compact dropdown — default "09:15 only") ──
    filter_col, _spacer = st.columns([2, 8])
    with filter_col:
        crossover_filter_option = st.selectbox(
            "Crossover Filter",
            ["09:15 only", "09:20 only", "All (09:15 + 09:20)", "No Match (NO_MATCH)"],
            index=0,
            key="crossover_filter_select"
        )

    if crossover_filter_option == "09:15 only":
        df = df[df['Crossover'] == "09:15"]
    elif crossover_filter_option == "09:20 only":
        df = df[df['Crossover'] == "09:20"]
    elif crossover_filter_option == "All (09:15 + 09:20)":
        df = df[df['Crossover'].isin(["09:15", "09:20"])]
    else:  # No Match (NO_MATCH) — stocks that did NOT confirm crossover
        # Vol5D + Max Qty will still calculate for these (since the loops
        # below just operate on whatever `df` is at that point) — this
        # is the deliberate opt-in cost (extra API calls) the user chose.
        df = df[df['Crossover'] == "NO_MATCH"]

    # ── TOP-20 LOCK MODE (opt-in checkbox) ──
    # 9:15-9:35 window: live top-20 (by Chg% descending) among confirmed
    # stocks. At 9:35 AM, whatever is top-20 at that moment gets PERMANENTLY
    # locked for the rest of the day — no new stocks added after that,
    # regardless of how many more confirm crossover later.
    top20_lock_mode = st.checkbox(
        "🔒 Top-20 Lock Mode (9:15-9:35 window — after 9:35, list freezes to top 20 by Chg%)",
        value=False,
        key="top20_lock_checkbox"
    )

    if top20_lock_mode:
        # 👉 CHANGE TIME HERE if you want a different lock-window in future
        # (same concept as Momentum Scanner) — currently locks at 9:35 AM.
        # Format: hour * 60 + minute. E.g. for 10:00 AM → 10 * 60 + 0
        TOP20_WINDOW_END_HHMM = 9 * 60 + 35  # 9:35 AM
        now_hhmm_lock = get_current_ist_time().hour * 60 + get_current_ist_time().minute
        today_str = signal_date.isoformat()

        # Reset the lock if it's a new trading day (safety, in case session
        # somehow persists across days)
        if st.session_state.get('top20_locked_date') != today_str:
            st.session_state['top20_locked_symbols'] = None
            st.session_state['top20_locked_date'] = today_str

        if st.session_state.get('top20_locked_symbols') is not None:
            # Already locked — restrict to the frozen list only
            df = df[df['Symbol'].isin(st.session_state['top20_locked_symbols'])]
        else:
            # Not yet locked — live top-20 by Chg% descending
            df_sorted = df.sort_values('Chg', ascending=False)
            top20_symbols = df_sorted['Symbol'].head(20).tolist()

            if now_hhmm_lock >= TOP20_WINDOW_END_HHMM:
                # 9:35 AM reached — freeze this list permanently for today
                st.session_state['top20_locked_symbols'] = top20_symbols

            df = df[df['Symbol'].isin(top20_symbols)]

    if df.empty:
        st.info(f"Abhi tak koi stock '{crossover_filter_option}' criteria confirm nahi kar paaya.")
        return

    # ── STEP 7: POC & GAP DISPLAY ──
    poc_vals, gap_vals = [], []
    for _, row in df.iterrows():
        symbol = row['Symbol']
        price  = row['Price']
        poc    = st.session_state['poc_cache'].get(symbol)
        if poc is None:
            poc_vals.append(None)
            gap_vals.append(None)
        elif price > poc:
            pct = ((price - poc) / poc) * 100
            poc_vals.append(poc)
            gap_vals.append(pct)
        else:
            pct = ((poc - price) / poc) * 100
            poc_vals.append(poc)
            gap_vals.append(-pct)
    df['POC']     = poc_vals
    df['GapPct']  = gap_vals

    # ── LIVE "% Since Signal" — (current_price - signal_price) / signal_price × 100
    # Purely computed for display, NOT saved to Supabase (changes every
    # refresh, so persisting it wouldn't mean anything as a static value).
    def calc_pct_since_signal(row):
        symbol = row['Symbol']
        signal_price = st.session_state['signalprice_cache'].get(symbol)
        if signal_price is None or signal_price == 0:
            return None
        try:
            return round(((row['Price'] - signal_price) / signal_price) * 100, 2)
        except Exception:
            return None

    def get_signal_price(row):
        return st.session_state['signalprice_cache'].get(row['Symbol'])

    df['PctSinceSignal'] = df.apply(calc_pct_since_signal, axis=1)
    df['SignalPrice']    = df.apply(get_signal_price, axis=1)

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 8: VOL5D (only for crossover-passed stocks)
    # (EMA Coil removed — wasn't useful for the strategy in practice)
    # ─────────────────────────────────────────────────────────────────────────

    if 'prevhigh_cache' not in st.session_state:
        st.session_state['prevhigh_cache'] = {}
    if 'vol5d_cache' not in st.session_state:
        st.session_state['vol5d_cache'] = {}

    # Market band hone ke baad naya Vol5D calculate nahi karna —
    # same reasoning: retry se koi fayda nahi, sirf waste calls.
    need_check = []
    if is_market_hours():
        need_check = [s for s in df['Symbol'] if s not in st.session_state['vol5d_cache']]

    def calculate_vol5d(symbol):
        """Parallel calculation."""
        vol5d_val = get_5day_median_volume(symbol)
        return symbol, vol5d_val

    if need_check:
        with st.spinner(f"Calculating Volume for {len(need_check)} stocks..."):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(calculate_vol5d, s) for s in need_check]
                for future in as_completed(futures):
                    symbol, vol5d_val = future.result()
                    row_match = df[df['Symbol'] == symbol]
                    prevhigh_val = float(row_match['PrevHighVal'].iloc[0]) if not row_match.empty and pd.notna(row_match['PrevHighVal'].iloc[0]) else None
                    st.session_state['prevhigh_cache'][symbol] = prevhigh_val
                    st.session_state['vol5d_cache'][symbol] = vol5d_val
                    supabase_save_row(
                        symbol, signal_date, calc_date,
                        prev_high_val=prevhigh_val,
                        vol5d_median=vol5d_val,
                    )

    # ── STEP 9: RELATIVE VOLUME (5D) ──
    def calc_rel_vol_5d(row):
        try:
            today_vol = float(row.get('Volume', 0) or 0)
            median_vol = st.session_state['vol5d_cache'].get(row['Symbol'])
            if median_vol is None or median_vol == 0:
                return None
            return round(today_vol / median_vol, 2)
        except:
            return None

    df['RelVol5D'] = df.apply(calc_rel_vol_5d, axis=1)

    # ── STEP 10: CANDLE SIGNALS (9:40, 9:45, 9:50) ──
    now_ist  = get_current_ist_time()
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
        return st.session_state['candle_cache'].get(key, "")

    # Market band hone ke baad naya candle-fetch attempt NAHI karna —
    # warna har 60s refresh pe wahi "Fetching candles..." spinner aata
    # rahega bina kisi naye data ke (waste API calls). Sirf market
    # open hone par hi missing candles fetch honge; band hone ke baad
    # jo cache mein hai wahi use hoga (missing wale blank/"" rahenge).
    symbols_needing_fetch = []
    if is_market_hours():
        for _, row in df.iterrows():
            sym = row['Symbol']
            missing_needed = any(
                show and f"{sym}_{t}" not in st.session_state['candle_cache']
                for t, show in [("09:40", show_940), ("09:45", show_945), ("09:50", show_950)]
            )
            if missing_needed:
                symbols_needing_fetch.append(sym)

    if symbols_needing_fetch:
        with st.spinner(f"Fetching candles for {len(symbols_needing_fetch)} stocks..."):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(get_all_candle_signals, sym): sym for sym in symbols_needing_fetch}
                for future in as_completed(futures):
                    sym = futures[future]
                    all_signals = future.result()
                    for t in ["09:40", "09:45", "09:50"]:
                        st.session_state['candle_cache'][f"{sym}_{t}"] = all_signals[t]

    c940_list, c945_list, c950_list = [], [], []
    for _, row in df.iterrows():
        sym = row['Symbol']
        c940_list.append(get_candle_cached(sym, "09:40", show_940))
        c945_list.append(get_candle_cached(sym, "09:45", show_945))
        c950_list.append(get_candle_cached(sym, "09:50", show_950))
    df['c940'] = c940_list
    df['c945'] = c945_list
    df['c950'] = c950_list

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 11: HEADER DISPLAY
    # ─────────────────────────────────────────────────────────────────────────
    
    sectors    = ['All'] + sorted(df['Sector'].dropna().unique().tolist())
    top_gainer = df.iloc[0]['Symbol'] if len(df) > 0 else '-'
    max_chg    = df['Chg'].max() if len(df) > 0 else 0.0
    last_day   = get_last_trading_day()
    now_time   = now_ist.strftime('%H:%M:%S')

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
                <div style="font-size:10px;color:#6b7280;font-weight:600;">POC DATE</div>
                <div style="font-size:13px;font-weight:700;color:#7c3aed;line-height:1.2;">{last_day.strftime('%d %b')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        selected_sector = st.selectbox("Sector", sectors, index=0, label_visibility="collapsed")

    with c3:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun(scope="fragment")

    if selected_sector != 'All':
        df = df[df['Sector'] == selected_sector]

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 11.5: MAX QUANTITY (based on user capital / 4 parts, via DhanHQ margin)
    # ─────────────────────────────────────────────────────────────────────────

    with st.spinner("Calculating max quantity (DhanHQ margin)..."):
        df['MaxQty'] = calculate_max_quantity_column(df, st.session_state['user_capital'], num_parts=4)

    # ── STEP 12: RENDER TABLE + DHAN BUY BUTTONS (side-by-side, 90%/10%) ──
    # Table itself (render_stock_table) is completely unchanged — same
    # function, same visual output. Only the surrounding layout wraps it
    # in a 90/10 column split so native Dhan buy buttons sit right next
    # to each row, without touching the HTML-table rendering logic at all.

    amo_test_mode = st.checkbox(
        "🌙 AMO mode (test outside market hours — order queues for next market open instead of rejecting)",
        value=False,
        help="Enable this to test order placement when market is closed. Places an After-Market Order (AMO) that Dhan queues and sends to the exchange at the next market open, instead of rejecting with 'Market is Closed'."
    )

    col_table, col_buttons = st.columns([8.5, 1.5])

    with col_table:
        render_stock_table(df)  # UNCHANGED — same function, same visual

    with col_buttons:
        # Spacer to roughly line up with the table's header row before the
        # first data row starts. Row heights inside the HTML table can vary
        # slightly with content (two-line cells etc.), so this is a close
        # visual alignment, not pixel-perfect.
        st.markdown('<div style="height:38px"></div>', unsafe_allow_html=True)
        for idx, (_, row) in enumerate(df.iterrows()):
            symbol = row['Symbol']
            max_qty = row.get('MaxQty', 0)
            btn_label = f"{symbol} {int(max_qty)}" + (" 🌙" if amo_test_mode else "")
            if st.button(btn_label, key=f"buy_dhan_{symbol}_{idx}", disabled=(max_qty <= 0), use_container_width=True):
                with st.spinner(f"Placing order for {symbol} via Dhan..."):
                    result = place_dhan_order(
                        symbol, quantity=int(max_qty), product_type="INTRADAY",
                        after_market_order=amo_test_mode, amo_time="OPEN"
                    )
                    display_order_result(symbol, result)
                # NOTE: no st.rerun() here — Streamlit already reruns
                # automatically on button click; an explicit rerun() would
                # wipe the message before it's readable.

    # ── QTY CALCULATOR DEBUG (temporary — shows why Max Qty might be blank) ──
    with st.expander("🔍 Debug: Max Qty calculation"):
        debug_info = get_qty_calc_debug()
        st.write("**Token last generated:**", debug_info.get('token_last_generated'))
        st.write("**Token error:**", debug_info.get('token_error'))
        st.write("**Security map size:**", debug_info.get('security_map_size'))
        st.write("**Security map error:**", debug_info.get('security_map_error'))
        st.write("**Columns detected in Dhan CSV:**", debug_info.get('security_map_columns_found'))
        st.write("**Per-symbol results:**")
        st.json(debug_info.get('per_symbol', {}))

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 13: ALGOMOJO BUY ORDER BUTTONS (unchanged, separate section below)
    # ─────────────────────────────────────────────────────────────────────────

    st.markdown("---")
    st.subheader("📊 Buy Orders — AlgoMojo (Manual)")

    algomojo_cols = st.columns(min(4, len(df)))
    for idx, (_, row) in enumerate(df.iterrows()):
        col_idx = idx % len(algomojo_cols)
        with algomojo_cols[col_idx]:
            symbol = row['Symbol']
            if st.button(f"Buy {symbol}", key=f"buy_algomojo_{symbol}_{idx}"):
                with st.spinner(f"Placing order for {symbol} via AlgoMojo..."):
                    result = place_buy_order(symbol, quantity=1)
                    display_order_result(symbol, result)
                # NOTE: no st.rerun() here on purpose — Streamlit already
                # reruns automatically on button click. An explicit rerun()
                # right after would instantly wipe this message before it's
                # readable (especially now that cached margin data makes
                # reruns very fast). The message stays until the next
                # natural interaction or the fragment's 60s auto-refresh.

    # ── DIAGNOSTICS ──
    success_count, errors = get_supabase_stats()
    if success_count or errors:
        st.caption(f"🔍 Supabase: {success_count} saves, {len(errors)} errors")
        if errors:
            with st.expander("⚠️ Show errors"):
                for e in errors[-10:]:
                    st.text(e)

    st.markdown("""
    <div style="margin-top:6px;font-size:10px;color:#9ca3af;text-align:center;">
        TradingView Screener · NSE · Mkt Cap > ₹41B · Near 1M High · Gap ±2% · Sorted by Chg% · POC = Yesterday's Volume Profile
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: MAIN PAGE EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

screener_fragment()
