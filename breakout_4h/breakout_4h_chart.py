"""
breakout_4h_chart.py
Chart rendering — TradingView Light Theme style using Plotly
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go


def render_chart(result: dict):
    """
    Render 4H candlestick chart — TradingView Light style.
    Colors  : #26a69a (green) / #ef5350 (red)
    Y-axis  : right side
    Gaps    : weekends removed
    Candles : last 10 trading days (~20 4H candles)
    Zone    : pink dashed lines + shaded area
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

    for c in candles:
        try:
            dt = c["datetime"]
            if hasattr(dt, "strftime"):
                ts = pd.Timestamp(dt)
            else:
                ts = pd.Timestamp(dt)
            # Strip timezone → Plotly aligns correctly
            if ts.tzinfo is not None:
                ts = ts.tz_convert("Asia/Kolkata").tz_localize(None)
            dates.append(ts)

            opens.append(float(c["open"]))
            highs.append(float(c["high"]))
            lows.append(float(c["low"]))
            closes.append(float(c["close"]))
        except Exception as e:
            print(f"[chart] candle error: {e}")
            continue

    if not dates:
        st.warning("Chart data unavailable.")
        return

    # Last 20 candles = ~10 trading days
    dates  = dates[-20:]
    opens  = opens[-20:]
    highs  = highs[-20:]
    lows   = lows[-20:]
    closes = closes[-20:]

    # Consolidation = all except last
    # Breakout = last candle
    con_dates  = dates[:-1]
    con_opens  = opens[:-1]
    con_highs  = highs[:-1]
    con_lows   = lows[:-1]
    con_closes = closes[:-1]

    brk_date  = dates[-1]
    brk_open  = opens[-1]
    brk_high  = highs[-1]
    brk_low   = lows[-1]
    brk_close = closes[-1]

    # ── TV Light theme colors ──
    UP_COLOR   = "#26a69a"
    DOWN_COLOR = "#ef5350"
    BRK_COLOR  = "#26a69a"
    ZONE_COLOR = "rgba(244, 63, 94, 0.7)"
    ZONE_FILL  = "rgba(244, 63, 94, 0.06)"

    fig = go.Figure()

    # ── 1. Zone shaded area ──
    fig.add_hrect(
        y0        = con_low,
        y1        = con_high,
        fillcolor = ZONE_FILL,
        line_width= 0,
        layer     = "below",
    )

    # ── 2. Zone High dashed line ──
    fig.add_hline(
        y          = con_high,
        line_dash  = "dash",
        line_color = ZONE_COLOR,
        line_width = 1.5,
    )

    # ── 3. Zone Low dashed line ──
    fig.add_hline(
        y          = con_low,
        line_dash  = "dash",
        line_color = ZONE_COLOR,
        line_width = 1.5,
    )

    # ── 4. Zone labels (right side) ──
    fig.add_annotation(
        xref      = "paper",
        x         = 1.01,
        y         = con_high,
        text      = f"Zone High ₹{con_high:,.0f}",
        showarrow = False,
        xanchor   = "left",
        yanchor   = "middle",
        font      = dict(size=11, color=ZONE_COLOR),
    )
    fig.add_annotation(
        xref      = "paper",
        x         = 1.01,
        y         = con_low,
        text      = f"Zone Low ₹{con_low:,.0f}",
        showarrow = False,
        xanchor   = "left",
        yanchor   = "middle",
        font      = dict(size=11, color=ZONE_COLOR),
    )

    # ── 5. Consolidation candles ──
    fig.add_trace(go.Candlestick(
        x      = con_dates,
        open   = con_opens,
        high   = con_highs,
        low    = con_lows,
        close  = con_closes,
        name   = "4H Candles",
        increasing = dict(
            line      = dict(color=UP_COLOR, width=1),
            fillcolor = UP_COLOR,
        ),
        decreasing = dict(
            line      = dict(color=DOWN_COLOR, width=1),
            fillcolor = DOWN_COLOR,
        ),
    ))

    # ── 6. Breakout candle ──
    fig.add_trace(go.Candlestick(
        x      = [brk_date],
        open   = [brk_open],
        high   = [brk_high],
        low    = [brk_low],
        close  = [brk_close],
        name   = "Breakout",
        increasing = dict(
            line      = dict(color=BRK_COLOR, width=2),
            fillcolor = BRK_COLOR,
        ),
        decreasing = dict(
            line      = dict(color=BRK_COLOR, width=2),
            fillcolor = BRK_COLOR,
        ),
    ))

    # ── 7. Breakout annotation ──
    fig.add_annotation(
        x          = brk_date,
        y          = brk_high,
        text       = f"⚡ Breakout<br><b>+{result['breakout_pct']:.1f}%</b>",
        showarrow  = True,
        arrowhead  = 2,
        arrowcolor = BRK_COLOR,
        arrowsize  = 1,
        arrowwidth = 1.5,
        ax         = 0,
        ay         = -50,
        font       = dict(size=11, color=BRK_COLOR),
        bgcolor    = "rgba(38,166,154,0.08)",
        bordercolor= BRK_COLOR,
        borderwidth= 1,
        borderpad  = 5,
        align      = "center",
    )

    # ── Layout ──
    fig.update_layout(
        title = dict(
            text = f"<b>{symbol}</b> · 4H Chart",
            font = dict(size=14, color="#131722"),
            x    = 0.01,
        ),
        xaxis_rangeslider_visible = False,
        plot_bgcolor  = "#ffffff",
        paper_bgcolor = "#ffffff",
        height        = 460,
        margin        = dict(l=10, r=160, t=45, b=40),
        showlegend    = False,
        hovermode     = "x unified",

        xaxis = dict(
            showgrid    = True,
            gridcolor   = "#f0f3fa",
            gridwidth   = 1,
            linecolor   = "#e0e3eb",
            tickfont    = dict(color="#787b86", size=11),
            tickformat  = "%b %d",
            dtick       = "D1",         # Show every day
            tickangle   = 0,
            type        = "date",
            # Remove weekend gaps
            rangebreaks = [
                dict(bounds=["sat", "mon"]),
            ],
        ),

        yaxis = dict(
            showgrid    = True,
            gridcolor   = "#f0f3fa",
            gridwidth   = 1,
            linecolor   = "#e0e3eb",
            tickfont    = dict(color="#787b86", size=11),
            tickprefix  = "₹",
            side        = "right",
            showline    = True,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)
