"""
Backtest Page - Inside 9:15 Strategy
"""

import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')


def fetch_5min_data(symbol):
    """Fetch 5-minute data for last 60 days."""
    ticker = symbol + ".NS"
    
    data = yf.download(
        ticker,
        period="60d",
        interval="5m",
        progress=False,
        auto_adjust=False
    )
    
    if data.empty:
        return None
    
    if data.index.tz is None:
        data.index = data.index.tz_localize('UTC').tz_convert(IST)
    else:
        data.index = data.index.tz_convert(IST)
    
    return data


def calculate_ema_200(data):
    """Calculate 200 EMA."""
    if len(data) < 200:
        return None
    close_prices = data['Close'].astype(float)
    return close_prices.ewm(span=200, adjust=False).mean()


def backtest_single_stock(symbol):
    """Backtest one stock."""
    data = fetch_5min_data(symbol)
    
    if data is None or data.empty:
        return []
    
    ema_200 = calculate_ema_200(data)
    if ema_200 is None:
        return []
    
    data['date'] = data.index.date
    trading_days = data['date'].unique()
    
    trades = []
    
    for day in trading_days:
        day_data = data[data['date'] == day].copy()
        
        if len(day_data) < 5:
            continue
        
        # 9:15 Candle
        mask_9_15 = (day_data.index.hour == 9) & (day_data.index.minute == 15)
        if mask_9_15.sum() == 0:
            continue
        
        candle_9_15 = day_data[mask_9_15].iloc[0]
        high_9_15 = float(candle_9_15['High'])
        low_9_15 = float(candle_9_15['Low'])
        
        # 9:20 Candle
        mask_9_20 = (day_data.index.hour == 9) & (day_data.index.minute == 20)
        if mask_9_20.sum() == 0:
            continue
        
        candle_9_20 = day_data[mask_9_20].iloc[0]
        high_9_20 = float(candle_9_20['High'])
        low_9_20 = float(candle_9_20['Low'])
        close_9_20 = float(candle_9_20['Close'])
        
        # Condition 1: Inside 9:15
        inside = (high_9_20 <= high_9_15) and (low_9_20 >= low_9_15)
        if not inside:
            continue
        
        # Condition 2: Above 200 EMA
        ema_val = float(ema_200[day_data.index[0]])
        if close_9_20 <= ema_val:
            continue
        
        # Entry Setup
        trigger = high_9_15 * 1.0015
        stop_loss = low_9_20
        risk = trigger - stop_loss
        
        if risk <= 0:
            continue
        
        target = trigger + (risk * 1.5)
        
        # Check candles after 9:20
        remaining = day_data[day_data.index > day_data[mask_9_20].index[0]]
        
        if len(remaining) == 0:
            continue
        
        entry_price = None
        entry_time = None
        exit_price = None
        exit_time = None
        exit_type = None
        
        for idx, candle in remaining.iterrows():
            high = float(candle['High'])
            low = float(candle['Low'])
            
            if entry_price is None:
                if high >= trigger:
                    entry_price = trigger
                    entry_time = idx
                    
                    if low <= stop_loss:
                        exit_price = stop_loss
                        exit_time = idx
                        exit_type = "SL"
                    elif high >= target:
                        exit_price = target
                        exit_time = idx
                        exit_type = "TARGET"
            else:
                if exit_price is None:
                    if low <= stop_loss:
                        exit_price = stop_loss
                        exit_time = idx
                        exit_type = "SL"
                    elif high >= target:
                        exit_price = target
                        exit_time = idx
                        exit_type = "TARGET"
        
        if entry_price and not exit_price:
            exit_price = float(remaining.iloc[-1]['Close'])
            exit_time = remaining.index[-1]
            exit_type = "EOD"
        
        if entry_price and exit_price:
            pnl = exit_price - entry_price
            pnl_pct = (pnl / entry_price) * 100
            
            trades.append({
                'Date': str(day),
                'Symbol': symbol,
                'Entry': round(entry_price, 2),
                'Exit': round(exit_price, 2),
                'SL': round(stop_loss, 2),
                'Target': round(target, 2),
                'P&L': round(pnl, 2),
                'P&L%': round(pnl_pct, 2),
                'Result': exit_type
            })
    
    return trades


def render_backtest_page():
    """Streamlit page for backtesting."""
    
    st.markdown("""
    <div style="padding:1rem 0;">
        <h2 style="color:#1a1a2e;">📊 Strategy Backtest</h2>
        <p style="color:#888;">Inside 9:15 Strategy - Historical Performance</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Strategy Summary
    with st.expander("📋 Strategy Rules", expanded=False):
        st.markdown("""
        | Rule | Value |
        |------|-------|
        | Entry | Price > 9:15 High + 0.15% |
        | Stop Loss | 9:20 Low |
        | Target | 1:1.5 Risk-Reward |
        | Max Hold | EOD (3:15 PM) |
        | 200 EMA Filter | Price must be above 200 EMA |
        """)
    
    # Stock selection
    st.markdown("### Select Stocks")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        default_symbols = "RELIANCE,TCS,HDFCBANK,INFY,ICICIBANK,SBIN,ITC,KOTAKBANK,LT,AXISBANK"
        symbols_input = st.text_area(
            "Enter NSE symbols (comma separated)",
            value=default_symbols,
            height=80,
            help="Max 20 symbols recommended for faster results"
        )
    
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        run_btn = st.button("🚀 Run Backtest", type="primary", use_container_width=True)
    
    symbols = [s.strip().upper() for s in symbols_input.split(",") if s.strip()]
    
    if run_btn:
        if len(symbols) == 0:
            st.warning("Please enter at least one symbol")
        else:
            all_trades = []
            errors = []
            
            progress = st.progress(0)
            status = st.empty()
            
            for i, symbol in enumerate(symbols):
                status.text(f"Testing {symbol} ({i+1}/{len(symbols)})...")
                trades = backtest_single_stock(symbol)
                
                if trades:
                    all_trades.extend(trades)
                else:
                    errors.append(symbol)
                
                progress.progress((i + 1) / len(symbols))
            
            status.empty()
            
            if len(all_trades) == 0:
                st.warning("No trades found for any symbol in the period")
            else:
                trades_df = pd.DataFrame(all_trades)
                
                # ── Summary ──
                st.markdown("---")
                st.markdown("### 📊 Results Summary")
                
                total = len(trades_df)
                winners = trades_df[trades_df['P&L'] > 0]
                losers = trades_df[trades_df['P&L'] <= 0]
                win_rate = (len(winners) / total) * 100 if total > 0 else 0
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Trades", total)
                with col2:
                    st.metric("Win Rate", f"{win_rate:.1f}%")
                with col3:
                    st.metric("Total P&L", f"₹{trades_df['P&L'].sum():,.2f}")
                with col4:
                    st.metric("Avg P&L/Trade", f"₹{trades_df['P&L'].mean():,.2f}")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Winners", len(winners))
                with col2:
                    st.metric("Losers", len(losers))
                with col3:
                    st.metric("Target Hits", len(trades_df[trades_df['Result'] == 'TARGET']))
                with col4:
                    st.metric("SL Hits", len(trades_df[trades_df['Result'] == 'SL']))
                
                # ── Trade List ──
                st.markdown("---")
                st.markdown("### 📋 All Trades")
                
                # Color P&L
                def color_pnl(val):
                    if isinstance(val, (int, float)):
                        color = 'green' if val > 0 else 'red'
                        return f'color: {color}'
                    return ''
                
                styled = trades_df.style.applymap(color_pnl, subset=['P&L', 'P&L%'])
                st.dataframe(styled, use_container_width=True)
                
                # ── CSV Download ──
                csv = trades_df.to_csv(index=False)
                st.download_button(
                    "📥 Download CSV",
                    csv,
                    "backtest_results.csv",
                    "text/csv",
                    use_container_width=True
                )
                
                # ── Errors ──
                if errors:
                    st.caption(f"⚠️ No trades for: {', '.join(errors)}")


# For standalone testing
if __name__ == "__main__":
    st.set_page_config(page_title="Backtest", page_icon="📊", layout="wide")
    render_backtest_page()
