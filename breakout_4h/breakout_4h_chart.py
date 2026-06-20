"""
breakout_4h_chart.py
Chart rendering using Plotly (reliable in Streamlit)
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go


def render_chart(result: dict):
    """
    Render 4H candlestick chart using Plotly.
    - Green candles   = consolidation period
    - Emerald candle  = breakout candle (last one)
    - Red dashed lines = consolidation zone
    """
    candles  = result["candles_4h"]
    con_high = result["con_high"]
    con_low  = result["con_low"]
    symbol   = result["symbol"]

    # ── Build chart data ──
    dates  = []
    opens  = []
    highs  = []
    lows   = []
    closes = []
    colors = []

    for i, c in enumerate(candles):
        try:
            dt = c["datetime"]
            if hasattr(dt, "strftime"):
                dates.append(dt)
            else:
                dates.append(pd.Timestamp(dt))

            opens.append(float(c["open"]))
            highs.append(float(c["high"]))
            lows.append(float(c["low"]))
            closes.append(float(c["close"]))

            # Last candle = breakout candle → emerald
            if i == len(candles) - 1:
                colors.append("#10b981")
            else:
                colors.append("#10b981" if float(c["close"]) >= float(c["open"]) else "#f87171")

        except Exception as e:
            print(f"[chart] candle error: {e}")
            continue

    if not dates:
        st.warning("Chart data unavailable.")
        return

    # ── Plotly candlestick ──
    fig = go.Figure()

    # Normal candles
    fig.add_trace(go.Candlestick(
        x     = dates[:-1],
        open  = opens[:-1],
        high  = highs[:-1],
        low   = lows[:-1],
        close = closes[:-1],
        name  = "4H Candles",
        increasing_line_color = "#10b981",
        decreasing_line_color = "#f87171",
        increasing_fillcolor  = "#10b981",
        decreasing_fillcolor  = "#f87171",
    ))

    # Breakout candle — highlighted separately
    if dates:
        fig.add_trace(go.Candlestick(
            x     = [dates[-1]],
            open  = [opens[-1]],
            high  = [highs[-1]],
            low   = [lows[-1]],
            close = [closes[-1]],
            name  = "Breakout",
            increasing_line_color = "#059669",
            decreasing_line_color = "#059669",
            increasing_fillcolor  = "#059669",
            decreasing_fillcolor  = "#059669",
        ))

    # ── Consolidation zone ──
    fig.add_hline(
        y           = con_high,
        line_dash   = "dash",
        line_color  = "rgba(244,63,94,0.7)",
        line_width  = 1.5,
        annotation_text     = f"Zone High ₹{con_high:,.0f}",
        annotation_position = "top right",
        annotation_font_color = "rgba(244,63,94,0.9)",
    )
    fig.add_hline(
        y           = con_low,
        line_dash   = "dash",
        line_color  = "rgba(244,63,94,0.7)",
        line_width  = 1.5,
        annotation_text     = f"Zone Low ₹{con_low:,.0f}",
        annotation_position = "bottom right",
        annotation_font_color = "rgba(244,63,94,0.9)",
    )

    # ── Zone shading ──
    fig.add_hrect(
        y0          = con_low,
        y1          = con_high,
        fillcolor   = "rgba(244,63,94,0.06)",
        line_width  = 0,
    )

    # ── Layout ──
    fig.update_layout(
        title           = dict(
            text        = f"{symbol} — 4H Breakout Chart",
            font        = dict(size=14, color="#0f172a"),
        ),
        xaxis_rangeslider_visible = False,
        plot_bgcolor    = "#ffffff",
        paper_bgcolor   = "#ffffff",
        height          = 420,
        margin          = dict(l=10, r=10, t=40, b=10),
        showlegend      = False,
        xaxis = dict(
            showgrid      = True,
            gridcolor     = "#f1f5f9",
            linecolor     = "#e2e8f0",
            tickfont      = dict(color="#64748b", size=11),
        ),
        yaxis = dict(
            showgrid      = True,
            gridcolor     = "#f1f5f9",
            linecolor     = "#e2e8f0",
            tickfont      = dict(color="#64748b", size=11),
            tickprefix    = "₹",
        ),
    )

    st.plotly_chart(fig, use_container_width=True)
