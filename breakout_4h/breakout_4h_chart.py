"""
breakout_4h_chart.py
Chart rendering:
  - render_chart() → 4H candlestick with consolidation band
"""

import json
import pandas as pd
import streamlit as st


def render_chart(result: dict):
    """
    Render 4H candlestick chart using Lightweight Charts.
    - Gray candles    = consolidation period
    - Emerald candle  = breakout candle (last one)
    - Red dashed lines = consolidation zone (high + low)
    """
    candles  = result["candles_4h"]
    con_high = result["con_high"]
    con_low  = result["con_low"]
    symbol   = result["symbol"]

    # ── Build chart data ──
    chart_data = []
    for c in candles:
        try:
            dt = c["datetime"]
            if hasattr(dt, "timestamp"):
                ts = int(dt.timestamp())
            else:
                ts = int(pd.Timestamp(dt).timestamp())

            chart_data.append({
                "time" : ts,
                "open" : round(float(c["open"]),  2),
                "high" : round(float(c["high"]),  2),
                "low"  : round(float(c["low"]),   2),
                "close": round(float(c["close"]), 2),
            })
        except Exception:
            continue

    if not chart_data:
        st.warning("Chart data unavailable.")
        return

    # Last candle = breakout candle
    breakout_time = chart_data[-1]["time"]

    chart_json    = json.dumps(chart_data)
    con_high_json = json.dumps(con_high)
    con_low_json  = json.dumps(con_low)
    brk_time_json = json.dumps(breakout_time)

    html = f"""
    <div id="chart_{symbol}" style="width:100%;height:420px;border-radius:8px;overflow:hidden;"></div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.1.3/lightweight-charts.standalone.production.js"></script>
    <script>
    (function() {{
        // Wait for DOM + script to be ready
        function initChart() {{
            var container = document.getElementById('chart_{symbol}');
            if (!container) {{ setTimeout(initChart, 100); return; }}
            if (typeof LightweightCharts === 'undefined') {{ setTimeout(initChart, 100); return; }}

            // Use fixed width since iframe clientWidth can be 0
            var chartWidth = container.offsetWidth || window.innerWidth || 800;

        var chart = LightweightCharts.createChart(container, {{
            width  : chartWidth,
            height : 400,
            layout : {{
                background : {{ color: '#ffffff' }},
                textColor  : '#475569',
            }},
            grid: {{
                vertLines : {{ color: '#f1f5f9' }},
                horzLines : {{ color: '#f1f5f9' }},
            }},
            crosshair        : {{ mode: LightweightCharts.CrosshairMode.Normal }},
            rightPriceScale  : {{ borderColor: '#e2e8f0' }},
            timeScale        : {{
                borderColor    : '#e2e8f0',
                timeVisible    : true,
                secondsVisible : false,
            }},
        }});

        // ── Candlestick series ──
        var candleSeries = chart.addCandlestickSeries({{
            upColor         : '#10b981',
            downColor       : '#f87171',
            borderUpColor   : '#10b981',
            borderDownColor : '#f87171',
            wickUpColor     : '#10b981',
            wickDownColor   : '#f87171',
        }});

        var allCandles = {chart_json};
        var conHigh    = {con_high_json};
        var conLow     = {con_low_json};
        var brkTime    = {brk_time_json};

        // Highlight breakout candle in emerald
        var colored = allCandles.map(function(c) {{
            if (c.time === brkTime) {{
                return Object.assign({{}}, c, {{
                    color       : '#10b981',
                    borderColor : '#10b981',
                    wickColor   : '#10b981',
                }});
            }}
            return c;
        }});

        candleSeries.setData(colored);

        // ── Consolidation zone — upper dashed line ──
        var upperLine = chart.addLineSeries({{
            color            : 'rgba(244, 63, 94, 0.7)',
            lineWidth        : 1,
            lineStyle        : LightweightCharts.LineStyle.Dashed,
            priceLineVisible : false,
            lastValueVisible : false,
        }});

        // ── Consolidation zone — lower dashed line ──
        var lowerLine = chart.addLineSeries({{
            color            : 'rgba(244, 63, 94, 0.7)',
            lineWidth        : 1,
            lineStyle        : LightweightCharts.LineStyle.Dashed,
            priceLineVisible : false,
            lastValueVisible : false,
        }});

        var times = allCandles.map(function(c) {{ return c.time; }});
        upperLine.setData(times.map(function(t) {{ return {{ time: t, value: conHigh }}; }}));
        lowerLine.setData(times.map(function(t) {{ return {{ time: t, value: conLow  }}; }}));

        // ── Price line labels ──
        candleSeries.createPriceLine({{
            price            : conHigh,
            color            : 'rgba(244, 63, 94, 0.5)',
            lineWidth        : 1,
            lineStyle        : LightweightCharts.LineStyle.Dotted,
            axisLabelVisible : true,
            title            : 'Zone High',
        }});
        candleSeries.createPriceLine({{
            price            : conLow,
            color            : 'rgba(244, 63, 94, 0.5)',
            lineWidth        : 1,
            lineStyle        : LightweightCharts.LineStyle.Dotted,
            axisLabelVisible : true,
            title            : 'Zone Low',
        }});

        chart.timeScale().fitContent();

        // Responsive resize
        window.addEventListener('resize', function() {{
            var w = container.offsetWidth || window.innerWidth || 800;
            chart.applyOptions({{ width: w }});
        }});
        }} // end initChart

        // Start after slight delay to ensure iframe is ready
        setTimeout(initChart, 200);
    }})();
    </script>
    """

    st.components.v1.html(html, height=440)
