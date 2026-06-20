"""
breakout_4h_chart.py
Chart:
  - Sirf 4H candles dikhao
  - Last 4H candle = emerald (breakout zone ke upar)
  - Zone High/Low = dashed pink lines + shading
  - Annotation = 1H Breakout detected
"""

import pandas as pd
import streamlit as st
import plotly.graph_objects as go


def render_chart(result: dict):
    candles_4h   = result["candles_4h"]
    con_high     = result["con_high"]
    con_low      = result["con_low"]
    symbol       = result["symbol"]
    breakout_pct = result["breakout_pct"]

    UP_COLOR   = "#26a69a"
    DOWN_COLOR = "#ef5350"
    BRK_COLOR  = "#059669"
    ZONE_COLOR = "rgba(244,63,94,0.7)"
    ZONE_FILL  = "rgba(244,63,94,0.06)"

    # ── Build 4H candle data ──
    dates  = []
    opens  = []
    highs  = []
    lows   = []
    closes = []

    for c in candles_4h:
        try:
            dt = c["datetime"]
            ts = pd.Timestamp(dt)
            if ts.tzinfo is not None:
                ts = ts.tz_convert("Asia/Kolkata").tz_localize(None)
            dates.append(ts)
            opens.append(float(c["open"]))
            highs.append(float(c["high"]))
            lows.append(float(c["low"]))
            closes.append(float(c["close"]))
        except Exception as e:
            print(f"[chart] error: {e}")
            continue

    if not dates:
        st.warning("Chart data unavailable.")
        return

    # Last 20 candles
    dates  = dates[-20:]
    opens  = opens[-20:]
    highs  = highs[-20:]
    lows   = lows[-20:]
    closes = closes[-20:]

    # All candles except last = consolidation
    # Last candle = breakout (emerald)
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

    # ── 4. Zone labels right side ──
    fig.add_annotation(
        xref="paper", x=1.01, y=con_high,
        text=f"Zone High ₹{con_high:,.0f}",
        showarrow=False, xanchor="left", yanchor="middle",
        font=dict(size=11, color=ZONE_COLOR),
    )
    fig.add_annotation(
        xref="paper", x=1.01, y=con_low,
        text=f"Zone Low ₹{con_low:,.0f}",
        showarrow=False, xanchor="left", yanchor="middle",
        font=dict(size=11, color=ZONE_COLOR),
    )

    # ── 5. Consolidation 4H candles (all except last) ──
    fig.add_trace(go.Candlestick(
        x      = dates[:-1],
        open   = opens[:-1],
        high   = highs[:-1],
        low    = lows[:-1],
        close  = closes[:-1],
        name   = "4H",
        increasing = dict(line=dict(color=UP_COLOR, width=1), fillcolor=UP_COLOR),
        decreasing = dict(line=dict(color=DOWN_COLOR, width=1), fillcolor=DOWN_COLOR),
    ))

    # ── 6. Last 4H candle = breakout (emerald) ──
    fig.add_trace(go.Candlestick(
        x      = [dates[-1]],
        open   = [opens[-1]],
        high   = [highs[-1]],
        low    = [lows[-1]],
        close  = [closes[-1]],
        name   = "Breakout",
        increasing = dict(line=dict(color=BRK_COLOR, width=2), fillcolor=BRK_COLOR),
        decreasing = dict(line=dict(color=BRK_COLOR, width=2), fillcolor=BRK_COLOR),
    ))

    # ── 7. Breakout annotation ──
    fig.add_annotation(
        x=dates[-1], y=highs[-1],
        text=f"⚡ 1H Breakout<br><b>+{breakout_pct:.1f}%</b>",
        showarrow=True,
        arrowhead=2, arrowcolor=BRK_COLOR,
        arrowsize=1, arrowwidth=1.5,
        ax=0, ay=-50,
        font=dict(size=11, color=BRK_COLOR),
        bgcolor="rgba(5,150,105,0.08)",
        bordercolor=BRK_COLOR,
        borderwidth=1, borderpad=5,
        align="center",
    )

    # ── Layout ──
    fig.update_layout(
        title=dict(
            text=f"<b>{symbol}</b> · 4H Zone + 1H Breakout",
            font=dict(size=14, color="#131722"),
            x=0.01,
        ),
        xaxis_rangeslider_visible=False,
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        height=460,
        margin=dict(l=10, r=160, t=45, b=40),
        showlegend=False,
        hovermode="x unified",
        xaxis=dict(
            showgrid=True,
            gridcolor="#f0f3fa",
            gridwidth=1,
            linecolor="#e0e3eb",
            tickfont=dict(color="#787b86", size=11),
            tickformat="%b %d",
            dtick="D1",
            tickangle=0,
            type="date",
            rangebreaks=[dict(bounds=["sat", "mon"])],
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#f0f3fa",
            gridwidth=1,
            linecolor="#e0e3eb",
            tickfont=dict(color="#787b86", size=11),
            tickprefix="₹",
            side="right",
            showline=True,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)

    st.markdown("""
    <div style="display:flex;gap:20px;font-size:12px;color:#64748b;margin-top:4px;">
        <span>🟩 4H up candle</span>
        <span>🟥 4H down candle</span>
        <span style="color:#059669;">🟢 Breakout candle (4H)</span>
        <span>🔴 Consolidation zone</span>
    </div>
    """, unsafe_allow_html=True)
