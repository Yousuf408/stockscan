# ══════════════════════════════════════════════════════════════════════════════
#   ENHANCED CHART RENDERER — TradingView Lightweight Charts + Angel One API
#   SIMPLIFIED VERSION - No indicator checkboxes, just chart
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import pytz


# ══════════════════════════════════════════════════════════════════════════════
#   ANGEL ONE SESSION
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource
def get_angel_session():
    """Get Angel One session from credentials"""
    try:
        import pyotp
        from SmartApi import SmartConnect
        
        # Get credentials from Streamlit secrets
        api_key = st.secrets.get("API_KEY")
        client_code = st.secrets.get("CLIENT_CODE")
        password = st.secrets.get("PASSWORD")
        totp_secret = st.secrets.get("TOTP_SECRET")
        
        if not all([api_key, client_code, password, totp_secret]):
            st.error("Missing Angel One credentials in secrets")
            return None
        
        # Initialize SmartConnect
        obj = SmartConnect(api_key=api_key)
        
        # Generate TOTP
        totp = pyotp.TOTP(totp_secret).now()
        
        # Create session
        sess = obj.generateSession(client_code, password, totp)
        
        if sess and sess.get("status"):
            return obj
        else:
            st.error("Angel One session creation failed")
            return None
            
    except Exception as e:
        st.error(f"Angel One connection error: {str(e)}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#   FETCH DATA FROM ANGEL ONE
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def fetch_chart_data_angelone(symbol: str, exchange: str):
    """Fetch historical OHLC data from Angel One API"""
    try:
        # Get Angel One session
        obj = get_angel_session()
        if not obj:
            st.error("Cannot connect to Angel One")
            return None
        
        # Import token fetcher
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        try:
            from stocks import get_stock_token
            token = get_stock_token(symbol)
        except:
            st.error(f"Cannot find stock token for {symbol}")
            return None
        
        if not token:
            st.error(f"Token not found for {symbol}")
            return None
        
        # Fetch candle data from Angel One
        resp = obj.getCandleData(
            mode="FULL",  # FULL = Open, High, Low, Close, Volume
            exchangeTokens=[str(token)],
            interval="ONE_DAY"  # Daily candles
        )
        
        if not resp:
            st.error("No response from Angel One API")
            return None
        
        if resp.get("status") != True:
            st.error(f"Angel One API error: {resp.get('message', 'Unknown error')}")
            return None
        
        # Extract candle data
        fetched_data = resp.get("data", {}).get("fetched", [])
        
        if not fetched_data or len(fetched_data) == 0:
            st.error(f"No candle data available for {symbol}")
            return None
        
        # Convert to DataFrame
        candles = []
        for candle in fetched_data:
            try:
                # Angel One format: [timestamp, open, high, low, close, volume]
                candles.append({
                    'Date': pd.to_datetime(int(candle[0]), unit='s'),
                    'Open': float(candle[1]),
                    'High': float(candle[2]),
                    'Low': float(candle[3]),
                    'Close': float(candle[4]),
                    'Volume': int(candle[5]) if len(candle) > 5 else 0
                })
            except (ValueError, IndexError) as e:
                continue
        
        if not candles:
            st.error("Could not parse candle data")
            return None
        
        # Create DataFrame
        df = pd.DataFrame(candles)
        df.set_index('Date', inplace=True)
        df = df.sort_index()
        
        return df
        
    except Exception as e:
        st.error(f"Error fetching Angel One data: {str(e)}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#   TECHNICAL INDICATORS
# ══════════════════════════════════════════════════════════════════════════════

def calculate_sma(data: pd.Series, period: int = 20) -> pd.Series:
    """Simple Moving Average"""
    return data.rolling(window=period).mean()

def calculate_ema(data: pd.Series, period: int = 12) -> pd.Series:
    """Exponential Moving Average"""
    return data.ewm(span=period, adjust=False).mean()

def calculate_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(data: pd.Series, period: int = 20, std_dev: int = 2):
    """Bollinger Bands"""
    sma = calculate_sma(data, period)
    std = data.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower

def calculate_macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD - Moving Average Convergence Divergence"""
    ema_fast = calculate_ema(data, fast)
    ema_slow = calculate_ema(data, slow)
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ══════════════════════════════════════════════════════════════════════════════
#   CHART HTML GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def generate_tradingview_chart_html(symbol: str, hist: pd.DataFrame) -> str:
    """
    Generate interactive TradingView Lightweight Chart with all indicators ON
    No user controls - just the chart
    """
    
    # Prepare data for chart
    hist = hist.copy()
    hist.index = pd.to_datetime(hist.index)
    hist = hist.sort_index()
    
    # Calculate all indicators (always ON)
    hist['SMA20'] = calculate_sma(hist['Close'], 20)
    hist['EMA12'] = calculate_ema(hist['Close'], 12)
    hist['RSI'] = calculate_rsi(hist['Close'], 14)
    hist['BB_Upper'], hist['BB_Middle'], hist['BB_Lower'] = calculate_bollinger_bands(hist['Close'], 20)
    hist['Volume'] = hist.get('Volume', 0)
    
    # Format data for JavaScript
    candles = []
    for idx, row in hist.iterrows():
        timestamp = int(idx.timestamp())
        candles.append({
            'time': timestamp,
            'open': round(float(row['Open']), 2),
            'high': round(float(row['High']), 2),
            'low': round(float(row['Low']), 2),
            'close': round(float(row['Close']), 2),
            'volume': int(row.get('Volume', 0))
        })
    
    # Format moving averages
    sma20_data = [
        {'time': int(idx.timestamp()), 'value': round(float(val), 2)}
        for idx, val in hist['SMA20'].items() if pd.notna(val)
    ]
    
    ema12_data = [
        {'time': int(idx.timestamp()), 'value': round(float(val), 2)}
        for idx, val in hist['EMA12'].items() if pd.notna(val)
    ]
    
    rsi_data = [
        {'time': int(idx.timestamp()), 'value': round(float(val), 2)}
        for idx, val in hist['RSI'].items() if pd.notna(val)
    ]
    
    # Convert to JSON-safe format
    import json
    candles_json = json.dumps(candles)
    sma20_json = json.dumps(sma20_data)
    ema12_json = json.dumps(ema12_data)
    rsi_json = json.dumps(rsi_data)
    
    html = f"""
    <div id="tv-chart-container" style="height: 700px; width: 100%; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <div id="chart-container" style="height: 100%; width: 100%;"></div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.1.2/lightweight-charts.standalone.production.min.js"></script>
    <script>
    (function() {{
        // Initialize chart
        const container = document.getElementById('chart-container');
        const chart = LightweightCharts.createChart(container, {{
            layout: {{
                textColor: '#0f1117',
                background: {{ color: '#ffffff' }},
            }},
            width: container.clientWidth,
            height: 700,
            timeScale: {{
                timeVisible: true,
                secondsVisible: false,
                fixLeftEdge: true,
                fixRightEdge: true,
            }},
            crosshair: {{
                mode: LightweightCharts.CrosshairMode.Normal,
            }},
            grid: {{
                hStyle: LightweightCharts.LineStyle.Dashed,
                vStyle: LightweightCharts.LineStyle.Dashed,
            }},
        }});

        // Main candlestick series
        const candleSeries = chart.addCandlestickSeries({{
            upColor: '#00a854',
            downColor: '#e53935',
            borderUpColor: '#00a854',
            borderDownColor: '#e53935',
            wickUpColor: '#00a854',
            wickDownColor: '#e53935',
        }});

        // Set candlestick data
        const candleData = {candles_json};
        candleSeries.setData(candleData);

        // Add SMA 20
        const sma20Series = chart.addLineSeries({{
            color: '#2563eb',
            lineWidth: 1.5,
            title: 'SMA 20',
        }});
        sma20Series.setData({sma20_json});

        // Add EMA 12
        const ema12Series = chart.addLineSeries({{
            color: '#f59e0b',
            lineWidth: 1.5,
            title: 'EMA 12',
            lineStyle: LightweightCharts.LineStyle.Dashed,
        }});
        ema12Series.setData({ema12_json});

        // Volume series
        const volumeSeries = chart.addHistogramSeries({{
            color: 'rgba(37, 99, 235, 0.3)',
            title: 'Volume',
        }});
        
        const volumeData = {candles_json}.map(c => ({{
            time: c.time,
            value: c.volume,
            color: c.close >= c.open ? 'rgba(0, 168, 84, 0.3)' : 'rgba(229, 57, 53, 0.3)',
        }}));
        volumeSeries.setData(volumeData);

        // Fit content
        chart.timeScale().fitContent();

        // Responsive
        window.addEventListener('resize', () => {{
            chart.applyOptions({{ width: container.clientWidth }});
        }});

        // Legend
        const legend = document.createElement('div');
        legend.style.cssText = `
            position: absolute;
            top: 10px;
            right: 10px;
            z-index: 10;
            background: rgba(255, 255, 255, 0.95);
            border: 1px solid #e0e3e8;
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 12px;
            color: #0f1117;
            font-family: 'Courier New', monospace;
            line-height: 1.6;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        `;
        
        chart.subscribeCrosshairMove(param => {{
            if (!param.time || param.point.x < 0 || param.point.y < 0) {{
                legend.style.display = 'none';
                return;
            }}
            legend.style.display = 'block';
            
            const candle = candleSeries.dataByIndex(param.logical);
            const sma = sma20Series.dataByIndex(param.logical);
            const ema = ema12Series.dataByIndex(param.logical);
            
            if (candle) {{
                legend.innerHTML = `
                    <b style="color: #0f1117;">O:</b> ₹${{candle.open.toFixed(2)}} | 
                    <b style="color: #00a854;">H:</b> ₹${{candle.high.toFixed(2)}} | 
                    <b style="color: #e53935;">L:</b> ₹${{candle.low.toFixed(2)}} | 
                    <b style="color: #2563eb;">C:</b> ₹${{candle.close.toFixed(2)}}<br>
                    <b style="color: #2563eb;">SMA20:</b> ₹${{sma ? sma.value.toFixed(2) : 'N/A'}}<br>
                    <b style="color: #f59e0b;">EMA12:</b> ₹${{ema ? ema.value.toFixed(2) : 'N/A'}}
                `;
            }}
        }});

        container.parentElement.style.position = 'relative';
        container.parentElement.appendChild(legend);
    }})();
    </script>
    """
    
    return html


# ══════════════════════════════════════════════════════════════════════════════
#   STREAMLIT INTEGRATION - SIMPLIFIED
# ══════════════════════════════════════════════════════════════════════════════

def render_enhanced_chart(symbol: str, exchange: str):
    """Render trading chart directly - no indicator controls"""
    
    with st.spinner(f"📊 Loading chart for {symbol}..."):
        hist = fetch_chart_data_angelone(symbol, exchange)
    
    if hist is None or hist.empty:
        exch_label = "NSE" if exchange == "NS" else "BSE"
        st.error(f"❌ No data available for {symbol} ({exch_label})")
        st.info("💡 Make sure Angel One credentials are configured in Streamlit secrets.")
        return
    
    # Generate and render chart (no controls, just chart)
    chart_html = generate_tradingview_chart_html(symbol, hist)
    st.components.v1.html(chart_html, height=750)
    
    # Statistics
    current = hist['Close'].iloc[-1]
    year_high = hist['High'].max()
    year_low = hist['Low'].min()
    avg_vol = hist['Volume'].mean() if 'Volume' in hist else 0
    
    st.divider()
    
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        st.metric("Current Price", f"₹{current:,.0f}")
    with stat_col2:
        st.metric("High", f"₹{year_high:,.0f}")
    with stat_col3:
        st.metric("Low", f"₹{year_low:,.0f}")
    with stat_col4:
        st.metric("Avg Volume", f"{int(avg_vol):,}")
