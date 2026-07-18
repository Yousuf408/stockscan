import streamlit as st
import pandas as pd
import yfinance as yf
from tradingview_screener import Query
from tradingview_screener.column import col
from datetime import datetime
import pytz
import concurrent.futures
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

warnings.filterwarnings('ignore')

from tv_screener.quantity_calculator import (
    calculate_max_quantity_column,
    get_qty_calc_debug
)
from tv_screener.dhan_orders import place_dhan_order
from tv_screener.frontend import display_order_result

# ─── PAGE CONFIG ───
st.set_page_config(page_title="Gap Screener", page_icon="📊", layout="wide")

# ─── SESSION STATE ───
if 'user_capital' not in st.session_state:
    st.session_state['user_capital'] = 100000.0
if 'amo_mode' not in st.session_state:
    st.session_state['amo_mode'] = False
if 'stage1_data' not in st.session_state:
    st.session_state['stage1_data'] = None
if 'show_inside_only' not in st.session_state:
    st.session_state['show_inside_only'] = False
if 'show_breakout_only' not in st.session_state:
    st.session_state['show_breakout_only'] = False
if 'stage1_last_refresh' not in st.session_state:
    st.session_state['stage1_last_refresh'] = datetime.now(pytz.timezone('Asia/Kolkata'))

IST = pytz.timezone('Asia/Kolkata')

# ─── HARDCODED SETTINGS ───
SETTINGS = {
    'price_min': 200,
    'price_max': 2000,
    'market_cap_min': 41_000_000_000,
    'stocks_limit': 50
}

# ─── DATA FUNCTIONS ───
def get_gap_filtered_stocks(df):
    yahoo_tickers = []
    ticker_map = {}
    for row in df.itertuples():
        base = row.ticker.replace('NSE:', '')
        yahoo_ticker = base + '.NS'
        yahoo_tickers.append(yahoo_ticker)
        ticker_map[yahoo_ticker] = row.ticker

    data = yf.download(tickers=yahoo_tickers, period="10d", interval="1d",
                       group_by='ticker', progress=False, threads=True, auto_adjust=False)

    filtered = []
    rejected = []

    for yahoo_ticker, original_ticker in ticker_map.items():
        if yahoo_ticker not in data:
            filtered.append(original_ticker)
            continue

        hist = data[yahoo_ticker]
        if hist.empty or len(hist) < 2:
            filtered.append(original_ticker)
            continue

        latest_date = hist.index[-1].date()
        latest_data = hist[hist.index.date == latest_date]
        if latest_data.empty:
            filtered.append(original_ticker)
            continue
        today_open = float(latest_data.iloc[0]['Open'])

        prev_rows = hist[hist.index.date < latest_date]
        if prev_rows.empty:
            filtered.append(original_ticker)
            continue
        prev_close = float(prev_rows.iloc[-1]['Close'])
        if prev_close == 0:
            filtered.append(original_ticker)
            continue
        gap_percent = ((today_open - prev_close) / prev_close) * 100

        if abs(gap_percent) >= 2.0:
            rejected.append({
                'ticker': original_ticker,
                'gap_percent': gap_percent,
                'type': 'Gap UP' if gap_percent > 0 else 'Gap DOWN',
                'reason': f"Gap {gap_percent:.2f}%"
            })
        else:
            filtered.append(original_ticker)

    return filtered, rejected

def get_tradingview_stocks():
    try:
        count, df = (Query()
            .select('name', 'close', 'change', 'volume', 'relative_volume', 'market_cap_basic', 'sector')
            .set_markets('india')
            .where(
                col('close') > SETTINGS['price_min'],
                col('close') <= SETTINGS['price_max'],
                col('market_cap_basic') > SETTINGS['market_cap_min'],
                col('exchange') == 'NSE'
            )
            .order_by('change', ascending=False)
            .limit(SETTINGS['stocks_limit'])
            .get_scanner_data()
        )
        return count, df
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return 0, pd.DataFrame()

def get_intraday_data_for_symbol(yahoo_ticker, period="2d", interval="5m"):
    try:
        data = yf.download(yahoo_ticker, period=period, interval=interval,
                           progress=False, auto_adjust=False, threads=False)
        if data.empty:
            return None
        ist = pytz.timezone('Asia/Kolkata')
        if data.index.tz is None:
            data.index = data.index.tz_localize('UTC').tz_convert(ist)
        else:
            data.index = data.index.tz_convert(ist)
        return data
    except:
        return None

def get_candle_data_bulk(tickers_list, max_workers=20):
    results = {}
    symbol_formats = ['.NS', '-NS', '']

    def fetch_one(ticker):
        base_ticker = ticker.replace('NSE:', '')
        for suffix in symbol_formats:
            yahoo_ticker = base_ticker + suffix
            data = get_intraday_data_for_symbol(yahoo_ticker)
            if data is not None and not data.empty:
                ist = pytz.timezone('Asia/Kolkata')
                today = datetime.now(ist).date()
                today_data = data[data.index.date == today]
                yesterday_data = data[data.index.date < today]
                prev_close = float(yesterday_data.iloc[-1]['Close']) if len(yesterday_data) > 0 else None
                if today_data.empty:
                    continue
                df_day = today_data

                mask_first = (df_day.index.hour == 9) & (df_day.index.minute >= 10) & (df_day.index.minute <= 20)
                if mask_first.sum() == 0:
                    mask_first = (df_day.index.hour == 9) & (df_day.index.minute < 30)
                    if mask_first.sum() == 0:
                        first_candle = df_day.iloc[0]
                    else:
                        first_candle = df_day[mask_first].iloc[0]
                else:
                    first_candle = df_day[mask_first].iloc[0]

                mask_second = (df_day.index.hour == 9) & (df_day.index.minute >= 20) & (df_day.index.minute <= 25)
                if mask_second.sum() == 0:
                    if len(df_day) >= 2:
                        second_candle = df_day.iloc[1]
                    else:
                        continue
                else:
                    second_candle = df_day[mask_second].iloc[0]

                mask_morning = ((df_day.index.hour == 9) & (df_day.index.minute >= 20)) | \
                               ((df_day.index.hour == 10) & (df_day.index.minute <= 15))
                if mask_morning.sum() > 0:
                    max_high = float(df_day.loc[mask_morning, 'High'].max())
                else:
                    max_high = float(second_candle['High'])

                low_9_15 = float(first_candle['Low'])
                mask_20_to_35 = (df_day.index.hour == 9) & (df_day.index.minute >= 20) & (df_day.index.minute <= 35)
                hit_low_9_20_to_35 = False
                if mask_20_to_35.sum() > 0:
                    candles = df_day.loc[mask_20_to_35]
                    hit_low_9_20_to_35 = ((candles['Low'] <= low_9_15) or (candles['Close'] <= low_9_15)).any().item()

                high_9_15 = float(first_candle['High'])
                mask_30_to_45 = (df_day.index.hour == 9) & (df_day.index.minute >= 30) & (df_day.index.minute <= 45)
                breakout_9_30_to_9_45 = False
                if mask_30_to_45.sum() > 0:
                    candles = df_day.loc[mask_30_to_45]
                    breakout_9_30_to_9_45 = (candles['High'] > high_9_15).any().item()

                if prev_close is not None and prev_close > 0:
                    high_9_20 = float(second_candle['High'])
                    gap_percent = ((high_9_20 - prev_close) / prev_close) * 100
                else:
                    gap_percent = 0.0
                    prev_close = float(first_candle['Close'])

                result = {
                    'high_9_15': float(first_candle['High']),
                    'low_9_15': low_9_15,
                    'close_9_15': float(first_candle['Close']),
                    'open_9_20': float(second_candle['Open']),
                    'high_9_20': float(second_candle['High']),
                    'low_9_20': float(second_candle['Low']),
                    'close_9_20': float(second_candle['Close']),
                    'max_high_up_to_10_15': max_high,
                    'hit_low_9_20_to_35': hit_low_9_20_to_35,
                    'breakout_9_30_to_9_45': breakout_9_30_to_9_45,
                    'prev_close': prev_close,
                    'gap_percent': gap_percent,
                    'yahoo_ticker': yahoo_ticker,
                    'data_date': today.strftime("%Y-%m-%d")
                }
                return base_ticker, result
        return None, None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_ticker = {executor.submit(fetch_one, ticker): ticker for ticker in tickers_list}
        for future in concurrent.futures.as_completed(future_to_ticker):
            base, data = future.result()
            if base and data:
                results[base] = data
    return results

def check_candle_conditions(df, tickers_list):
    with st.spinner('Fetching intraday data...'):
        candle_data = get_candle_data_bulk(tickers_list)

    for col_name in ['inside_9_15', 'breakout_9_30_to_9_45', 'gap_percent']:
        df[col_name] = False
    df['inside_9_15'] = False

    for idx, row in df.iterrows():
        ticker = row['ticker']
        base_ticker = ticker.replace('NSE:', '')
        if base_ticker in candle_data:
            data = candle_data[base_ticker]
            df.at[idx, 'gap_percent'] = data['gap_percent']
            df.at[idx, 'inside_9_15'] = (data['high_9_20'] <= data['high_9_15']) and (data['low_9_20'] >= data['low_9_15'])
            df.at[idx, 'breakout_9_30_to_9_45'] = data['breakout_9_30_to_9_45']

    return df

def load_stage1_data():
    with st.spinner("Loading market data..."):
        count, df = get_tradingview_stocks()
        if count == 0:
            return None
        filtered_tickers, _ = get_gap_filtered_stocks(df)
        df = df[df['ticker'].isin(filtered_tickers)].copy()
        df = df.sort_values('change', ascending=False)
        df = df.head(SETTINGS['stocks_limit'])
        tickers_list = df['ticker'].tolist()
        df = check_candle_conditions(df, tickers_list)
        return {
            'df': df,
            'total_count': count,
            'filtered_count': len(df),
            'timestamp': datetime.now(IST)
        }

def should_refresh():
    if 'stage1_last_refresh' not in st.session_state:
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        return True
    return (datetime.now(IST) - st.session_state['stage1_last_refresh']).total_seconds() >= 60

def prepare_display_df(display_df, user_capital):
    display_df['name'] = display_df['ticker'].str.replace('NSE:', '')
    display_df['Symbol'] = display_df['name']
    display_df['Price'] = display_df['close']

    with st.spinner("Calculating max quantity..."):
        display_df['MaxQty'] = calculate_max_quantity_column(display_df, user_capital, 4)

    display_df = display_df.rename(columns={
        'name': 'Symbol',
        'close': 'Price',
        'change': 'Chg%',
        'volume': 'Volume',
        'relative_volume': 'Rel Vol',
        'sector': 'Sector'
    })

    display_df['Price'] = display_df['Price'].apply(lambda x: f"₹{x:,.2f}")
    display_df['Chg%'] = display_df['Chg%'].apply(lambda x: f"+{x:.2f}%" if x >= 0 else f"{x:.2f}%")

    def fmt_gap(x):
        if pd.isna(x) or x is None:
            return "0.00%"
        return f"+{x:.2f}%" if x >= 0 else f"{x:.2f}%"

    display_df['Gap%'] = display_df['gap_percent'].apply(fmt_gap)

    def fmt_vol(x):
        if pd.isna(x) or x is None:
            return "0"
        if x >= 1e6:
            return f"{x/1e6:.1f}M"
        elif x >= 1e3:
            return f"{x/1e3:.1f}K"
        return f"{x:.0f}"

    display_df['Volume'] = display_df['Volume'].apply(fmt_vol)
    display_df['Rel Vol'] = display_df['Rel Vol'].apply(lambda x: f"{x:.2f}x" if pd.notna(x) else "0x")
    display_df['Inside 9:15'] = display_df['inside_9_15'].apply(lambda x: "✅" if x else "❌")
    display_df['Breakout'] = display_df['breakout_9_30_to_9_45'].apply(lambda x: "✅" if x else "❌")

    def get_signal(row):
        if row['Inside 9:15'] == "✅" and row['Breakout'] == "✅":
            return "🟢 BUY"
        elif row['Inside 9:15'] == "✅":
            return "🟡 HOLD"
        else:
            return "🔴 SELL"

    display_df['Signal'] = display_df.apply(get_signal, axis=1)

    cols = ['Symbol', 'Price', 'Chg%', 'Gap%', 'Volume', 'Rel Vol', 'Inside 9:15', 'Breakout', 'Signal', 'MaxQty', 'Sector']
    return display_df[[c for c in cols if c in display_df.columns]]

# ─── MAIN APP ───
st.title("📊 Gap Screener")

# Refresh
if should_refresh() or st.session_state['stage1_data'] is None:
    data = load_stage1_data()
    if data:
        st.session_state['stage1_data'] = data
        st.session_state['stage1_last_refresh'] = datetime.now(IST)
        st.rerun()

if st.session_state['stage1_data']:
    data = st.session_state['stage1_data']
    df = data['df'].copy()

    # Stats
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total", data['total_count'])
    col2.metric("After Gap", data['filtered_count'])
    col3.metric("Pass Candle", 0)
    col4.metric("Last Refresh", st.session_state['stage1_last_refresh'].strftime('%H:%M:%S'))

    # Filters
    st.caption("💰 200-2000  |  📊 ≥41B  |  📈 Gap ±2%")
    c1, c2, c3 = st.columns(3)
    with c1:
        show_inside = st.checkbox("Inside 9:15 Range", value=st.session_state['show_inside_only'])
        st.session_state['show_inside_only'] = show_inside
    with c2:
        show_breakout = st.checkbox("Breakout 9:30-9:45", value=st.session_state['show_breakout_only'])
        st.session_state['show_breakout_only'] = show_breakout
    with c3:
        amo = st.checkbox("AMO", value=st.session_state['amo_mode'])
        st.session_state['amo_mode'] = amo

    # Apply filters
    display_df = df.copy()
    if show_breakout:
        display_df = display_df[display_df['breakout_9_30_to_9_45'] == True]
    if show_inside:
        display_df = display_df[display_df['inside_9_15'] == True]

    if display_df.empty:
        st.warning("No stocks match filters")
    else:
        display_df = prepare_display_df(display_df, st.session_state['user_capital'])

        # Table
        st.dataframe(display_df, use_container_width=True, height=400)

        # Buy buttons
        st.markdown("### 🚀 Quick Buy")
        cols = st.columns(min(4, len(display_df)))
        for idx, (_, row) in enumerate(display_df.iterrows()):
            with cols[idx % len(cols)]:
                symbol = row['Symbol']
                qty = row['MaxQty']
                if st.button(f"{symbol} {int(qty)}" + (" 🌙" if amo else ""), key=f"buy_{symbol}_{idx}", disabled=(qty <= 0)):
                    result = place_dhan_order(symbol, int(qty), "INTRADAY", amo, "OPEN")
                    display_order_result(symbol, result)

        # Download
        st.download_button("📥 Download CSV", display_df.to_csv(index=False),
                          f"screener_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")

    with st.expander("🔍 Debug"):
        st.json(get_qty_calc_debug())

else:
    st.warning("No data loaded")
