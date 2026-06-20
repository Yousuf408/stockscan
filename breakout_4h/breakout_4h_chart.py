"""
breakout_4h_chart.py
Chart:
  - 4H candles = consolidation zone background
  - 1H breakout candle = highlighted separately (emerald)
  - Zone High/Low = dashed pink lines
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go


def render_chart(result: dict):
    """
    4H candles + 1H breakout candle chart.
    """
    candles_4h   = result["candles_4h"]
    brk_1h       = result.get("candle_1h_breakout", {})
    con_high     = result["con_high"]
    con_low      = result["con_low"]
    symbol       = result["symbol"]

    # ── TV Light colors ──
    UP_COLOR   = "#26a69a"
    DOWN_COLOR = "#ef5350"
    BRK_COLOR  = "#059669"   # Darker emerald for 1H breakout candle
    ZONE_COLOR = "rgba(244, 63, 94, 0.7)"
    ZONE_FILL  = "rgba(244, 63, 94, 0.06)"

    # ── Build 4H candle data ──
    dates_4h  = []
    opens_4h  = []
    highs_4h  = []
    lows_4h   = []
    closes_4h = []

    for c in candles_4h:
        try:
            dt = c["datetime"]
            if hasattr(dt, "strftime"):
                ts = pd.Timestamp(dt)
            else:
                ts = pd.Timestamp(dt)
            if ts.tzinfo is not None:
                ts = ts.tz_convert("Asia/Kolkata").tz_localize(None)
            dates_4h.append(ts)
            opens_4h.append(float(c["open"]))
            highs_4h.append(float(c["high"]))
            lows_4h.append(float(c["low"]))
            closes_4h.append(float(c["close"]))
        except Exception as e:
            print(f"[chart] 4H candle error: {e}")
            continue

    if not dates_4h:
        st.warning("Chart data unavailable.")
        return

    # ── Build 1H breakout candle ──
    brk_date  = None
    brk_open  = None
    brk_high  = None
    brk_low   = None
    brk_close = None

    if brk_1h:
        try:
            dt = brk_1h.get("datetime", None)
            if dt:
                ts = pd.Timestamp(dt)
                if ts.tzinfo is not None:
                    ts = ts.tz_convert("Asia/Kolkata").tz_localize(None)
                brk_date  = ts
                brk_open  = float(brk_1h.get("open",  0))
                brk_high  = float(brk_1h.get("high",  0))
                brk_low   = float(brk_1h.get("low",   0))
                brk_close = float(brk_1h.get("close", 0))
        except Exception as e:
            print(f"[chart] 1H candle error: {e}")

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

    # ── 4. Zone labels ──
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

    # ── 5. 4H consolidation candles ──
    fig.add_trace(go.Candlestick(
        x      = dates_4h,
        open   = opens_4h,
        high   = highs_4h,
        low    = lows_4h,
        close  = closes_4h,
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

    # ── 6. 1H Breakout candle ──
    if brk_date and brk_open:
        fig.add_trace(go.Candlestick(
            x      = [brk_date],
            open   = [brk_open],
            high   = [brk_high],
            low    = [brk_low],
            close  = [brk_close],
            name   = "1H Breakout",
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
            text       = f"⚡ 1H Breakout<br><b>+{result['breakout_pct']:.1f}%</b>",
            showarrow  = True,
            arrowhead  = 2,
            arrowcolor = BRK_COLOR,
            arrowsize  = 1,
            arrowwidth = 1.5,
            ax         = 0,
            ay         = -50,
            font       = dict(size=11, color=BRK_COLOR),
            bgcolor    = "rgba(5,150,105,0.08)",
            bordercolor= BRK_COLOR,
            borderwidth= 1,
            borderpad  = 5,
            align      = "center",
        )

    # ── Layout ──
    fig.update_layout(
        title = dict(
            text = f"<b>{symbol}</b> · 4H Zone + 1H Breakout",
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
            dtick       = "D1",
            tickangle   = 0,
            type        = "date",
            rangebreaks = [dict(bounds=["sat", "mon"])],
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

    # ── Legend manually ──
    st.plotly_chart(fig, use_container_width=True)

    # Chart legend
    st.markdown("""
    <div style="display:flex;gap:20px;font-size:12px;color:#64748b;margin-top:4px;">
        <span>🟩 4H candles (consolidation zone)</span>
        <span style="color:#059669;">🟢 1H breakout candle</span>
        <span>🔴 Zone High/Low</span>
    </div>
    """, unsafe_allow_html=True)
