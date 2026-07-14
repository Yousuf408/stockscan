# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER FRONTEND MODULE
# Display formatting, table rendering, UI helpers
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
import json

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: ORDER RESULT DISPLAY — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def display_order_result(symbol, result, max_inline_length=100):
    """
    Show order placement result cleanly:
      - Success: short green message with order ID
      - Failure: try to extract a clean human-readable error (Dhan/AlgoMojo
        errors are usually JSON with an 'errorMessage'/'message' field) for
        the inline message. ALWAYS also show an expander with the full raw
        error (payload sent, exact response) — even when the clean message
        is short — since order-placement issues need full traceability for
        debugging.
    """
    if result.get('success'):
        st.success(f"✅ {symbol} | Order ID: {result['order_id']}")
        return

    raw_error = str(result.get('error', 'Unknown error'))
    clean_msg = raw_error

    try:
        if '{' in raw_error:
            json_str = raw_error[raw_error.index('{'):].split('| Payload sent:')[0].strip()
            parsed = json.loads(json_str)
            clean_msg = parsed.get('errorMessage') or parsed.get('message') or clean_msg
    except Exception:
        pass

    display_msg = clean_msg if len(clean_msg) <= max_inline_length else clean_msg[:max_inline_length] + "..."
    st.error(f"❌ {symbol}: {display_msg}")
    with st.expander(f"🔍 Show full error details ({symbol})"):
        st.code(raw_error)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: TABLE STYLING CONSTANTS
# CHANGE: Updated to OS-style white theme — tighter padding, cleaner borders
# ─────────────────────────────────────────────────────────────────────────────

TH   = ("padding:7px 10px;font-size:9px;font-weight:500;color:#94a3b8;"
        "border-bottom:1px solid #e2e6ed;white-space:nowrap;text-align:center;"
        "text-transform:uppercase;letter-spacing:0.6px;background:#f8fafc;")
TH_L = ("padding:7px 10px;font-size:9px;font-weight:500;color:#94a3b8;"
        "border-bottom:1px solid #e2e6ed;text-align:left;"
        "text-transform:uppercase;letter-spacing:0.6px;background:#f8fafc;")
TD   = ("padding:9px 10px;font-size:12px;border-bottom:1px solid #f1f5f9;"
        "white-space:nowrap;text-align:center;vertical-align:middle;")
TD_L = ("padding:9px 10px;font-size:12px;border-bottom:1px solid #f1f5f9;"
        "text-align:left;vertical-align:middle;")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — VOLUME — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def fmt_volume(v):
    try:
        v = float(v)
        if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
        if v >= 100_000:   return f"{v/100_000:.1f}L"
        if v >= 1_000:     return f"{v/1_000:.1f}K"
        return str(int(v))
    except:
        return str(v)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — SIGNAL TIME — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def fmt_signal_time(signal_time):
    """
    Format signal time (HH:MM:SS) as a compact badge.
    Shows time when stock first appeared in scanner.
    """
    if not signal_time:
        return '<span style="color:#9ca3af;font-size:11px;">—</span>'
    try:
        t = str(signal_time)[:5]
    except:
        t = str(signal_time)
    return f'<span style="background:#f0f9ff;color:#0369a1;border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600;">{t}</span>'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — RELATIVE VOLUME — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def fmt_relvol(v):
    if v is None:
        return '<span style="color:#9ca3af;">N/A</span>'
    try:
        v = float(v)
        if v >= 3:     bg, color = "#fef9c3", "#854f0b"
        elif v >= 1.5: bg, color = "#dcfce7", "#166534"
        else:          bg, color = "transparent", "#374151"
        return f'<span style="background:{bg};color:{color};padding:2px 7px;border-radius:4px;font-weight:600;">{v:.2f}x</span>'
    except:
        return '<span style="color:#9ca3af;">N/A</span>'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — VOLUME BAR (NEW — UI only, no logic)
# Inline horizontal bar showing relative volume strength visually.
# Color tiers: green (>=2x), amber (>=1x), grey (<1x)
# ─────────────────────────────────────────────────────────────────────────────

def fmt_vol_bar(relvol):
    """
    Render a small inline progress bar for relative volume.
    Bar width capped at 100% (represents 5x = full bar).
    Color: green >= 2x | amber >= 1x | grey < 1x
    """
    if relvol is None:
        return '<div style="width:40px;height:4px;background:#e2e6ed;border-radius:2px;display:inline-block;"></div>'
    try:
        v = float(relvol)
        pct = min(int((v / 5.0) * 100), 100)
        if v >= 2.0:
            bar_color = "#16a34a"
            num_color = "#16a34a"
        elif v >= 1.0:
            bar_color = "#d97706"
            num_color = "#d97706"
        else:
            bar_color = "#94a3b8"
            num_color = "#94a3b8"
        return (
            f'<div style="display:flex;align-items:center;gap:5px;justify-content:center;">'
            f'<div style="width:38px;height:4px;background:#e2e6ed;border-radius:2px;display:inline-block;vertical-align:middle;">'
            f'<div style="width:{pct}%;height:4px;background:{bar_color};border-radius:2px;"></div>'
            f'</div>'
            f'<span style="font-size:11px;font-weight:700;color:{num_color};font-family:Consolas,monospace;">{v:.2f}x</span>'
            f'</div>'
        )
    except:
        return '<div style="width:40px;height:4px;background:#e2e6ed;border-radius:2px;display:inline-block;"></div>'


def fmt_vol_relvol(vol, relvol):
    """
    Merged Volume + Rel Vol in one cell.
    Top line : volume string (e.g. 2.5M)
    Bottom line: visual bar + rel vol number
    Logic 100% unchanged — only bar added below existing vol string.
    """
    vol_str = fmt_volume(vol)
    bar_str = fmt_vol_bar(relvol)
    return (
        f'<div style="font-size:12px;font-weight:500;color:#475569;'
        f'font-family:Consolas,monospace;margin-bottom:3px;">{vol_str}</div>'
        f'{bar_str}'
    )

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — SIGNAL BADGE (NEW — UI only)
# BUY badge  : signal_time present + relvol >= 1.0  → green  "● BUY HH:MM"
# LATE badge : signal_time present + relvol <  1.0  → amber  "◆ LATE HH:MM"
# WEAK badge : no signal_time                        → grey   "— WEAK"
# All data comes from existing df columns — zero new logic/calculation.
# ─────────────────────────────────────────────────────────────────────────────

def fmt_signal_badge(signal_time, relvol):
    """
    Render BUY / LATE / WEAK badge based on signal_time and relvol.
    Uses same data already present in df — no new fetching or logic.
    """
    if not signal_time:
        return (
            '<span style="background:#f1f5f9;color:#94a3b8;border:1px solid #e2e6ed;'
            'border-radius:4px;padding:3px 9px;font-size:11px;font-weight:600;">'
            '&mdash; WEAK</span>'
        )
    try:
        t = str(signal_time)[:5]
    except:
        t = str(signal_time)

    try:
        rv = float(relvol) if relvol is not None else 0.0
    except:
        rv = 0.0

    if rv >= 1.0:
        # BUY — green
        return (
            f'<span style="background:#dcfce7;color:#15803d;border:1px solid #bbf7d0;'
            f'border-radius:4px;padding:3px 9px;font-size:11px;font-weight:600;">'
            f'&#9679; BUY {t}</span>'
        )
    else:
        # LATE — amber (signal exists but volume weak)
        return (
            f'<span style="background:#fef9c3;color:#a16207;border:1px solid #fde68a;'
            f'border-radius:4px;padding:3px 9px;font-size:11px;font-weight:600;">'
            f'&#9670; LATE {t}</span>'
        )

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — ENTRY SIGNAL BADGES — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def fmt_entry_badges(c940, c945, c950):
    """
    Format entry candle signals as badges (9:40, 9:45, 9:50).

    Color intensity based on body_pct — more body = stronger/darker green:
      >= 75% : Dark green   — strong candle
      >= 50% : Medium green — decent candle
      >= 30% : Light green  — moderate candle
      >  0%  : Very light   — bullish but weak body
      ""     : Gray         — bearish or not yet available

    Args:
        c940, c945, c950: dict {"signal": "green"/"", "body_pct": float}
                          OR str "green"/"" (backward compat)
    Returns:
        str: HTML badge display
    """
    def badge(label, candle):
        if isinstance(candle, str):
            active   = candle
            body_pct = 0
        else:
            active   = candle.get("signal", "")
            body_pct = candle.get("body_pct", 0)

        if active == "green":
            if body_pct >= 75:
                bg, color = "#166534", "#ffffff"
            elif body_pct >= 50:
                bg, color = "#16a34a", "#ffffff"
            elif body_pct >= 30:
                bg, color = "#4ade80", "#166534"
            else:
                bg, color = "#dcfce7", "#166534"
            return (
                f'<span style="background:{bg};color:{color};border-radius:4px;'
                f'padding:2px 7px;font-size:11px;font-weight:600;" '
                f'title="Body: {body_pct:.1f}%">{label}</span>'
            )
        else:
            return (
                f'<span style="color:#d1d5db;font-size:11px;padding:2px 5px;">'
                f'{label}</span>'
            )

    return f'{badge("9:40", c940)}&nbsp;{badge("9:45", c945)}&nbsp;{badge("9:50", c950)}'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — POC & GAP — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def fmt_poc_gap(poc, gap_pct):
    if poc is None:
        return '<span style="color:#9ca3af;">N/A</span>'
    poc_str = f"₹{float(poc):,.2f}"
    if gap_pct is None:
        return f'<div style="font-size:12px;">{poc_str}</div>'
    if gap_pct > 0:
        if gap_pct >= 5:   color = "#14532d"
        elif gap_pct >= 2: color = "#16a34a"
        else:              color = "#4ade80"
        gap_str = f'<span style="color:{color};font-weight:700;">↑ +{gap_pct:.1f}%</span>'
    else:
        gap_str = f'<span style="color:#dc2626;font-weight:600;">↓ {gap_pct:.1f}%</span>'
    return (
        f'<div style="font-size:12px;font-weight:500;">{poc_str}</div>'
        f'<div style="font-size:11px;">{gap_str}</div>'
    )

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — PREVIOUS HIGH — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

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
    return (
        f'<div style="font-size:12px;font-weight:500;">{val_str}</div>'
        f'<div style="font-size:11px;">{pct_str}</div>'
    )

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — CROSSOVER — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def fmt_crossover(matched_candle):
    if matched_candle == "09:15":
        return (
            '<span style="background:#dcfce7;color:#166534;border-radius:4px;'
            'padding:3px 9px;font-weight:700;">&#10003;</span>'
        )
    elif matched_candle == "09:20":
        return (
            '<span style="background:#fce7f3;color:#9d174d;border-radius:4px;'
            'padding:3px 9px;font-weight:700;">&#10003;</span>'
        )
    else:
        return '<span style="color:#e2e6ed;font-size:13px;">&#8212;</span>'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — MAX QUANTITY — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def fmt_max_qty(qty):
    if qty is None or qty <= 0:
        return '<span style="color:#9ca3af;">—</span>'
    return (
        f'<span style="background:#eff6ff;color:#1e40af;padding:2px 8px;'
        f'border-radius:4px;font-weight:700;font-family:Consolas,monospace;">'
        f'{int(qty)}</span>'
    )

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — % SINCE SIGNAL — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def fmt_pct_since_signal(signal_price, pct):
    if signal_price is None:
        return '<span style="color:#9ca3af;">—</span>'
    price_str = f"₹{float(signal_price):,.2f}"
    if pct is None:
        return f'<div style="font-size:12px;">{price_str}</div>'
    if pct >= 0:
        color = "#16a34a"
        sign  = "+"
    else:
        color = "#dc2626"
        sign  = ""
    pct_str = f'<span style="color:{color};font-weight:600;">{sign}{pct:.2f}%</span>'
    return (
        f'<div style="font-size:12px;font-weight:500;">{price_str}</div>'
        f'<div style="font-size:11px;">{pct_str}</div>'
    )

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: TABLE RENDERING
# CHANGE: OS-style white theme table — tighter headers, vol bar, signal badge.
#         All data columns, df fields, function calls 100% UNCHANGED.
#         Only HTML wrapper CSS + two cell renderers updated (vol, signal).
# ─────────────────────────────────────────────────────────────────────────────

def render_stock_table(df, height_per_row=56, extra_height=60):
    """
    Render main stock results table with all columns.
    Interactive: Click symbol to copy to clipboard.

    UI changes vs original:
      - OS-style white theme (clean borders, #f8fafc header bg)
      - Volume cell: progress bar added via fmt_vol_bar() — visual only
      - Signal cell: BUY/LATE/WEAK badge via fmt_signal_badge() — uses same
        existing signal_time + relvol columns, zero new logic
      - Row hover highlight via CSS
    All other columns, logic, data access: 100% identical to original.
    """
    rows_html = ""
    for i, (_, row) in enumerate(df.iterrows()):
        sym              = row.get("Symbol", "")
        maxqty           = row.get("MaxQty", None)
        price            = row.get("Price", 0)
        chg              = row.get("Chg", 0)
        vol              = row.get("Volume", 0)
        relvol           = row.get("RelVol5D", 0)
        signal_time      = row.get("SignalTime", None)
        poc              = row.get("POC", None)
        gappct           = row.get("GapPct", None)
        pct_since_signal = row.get("PctSinceSignal", None)
        signal_price_val = row.get("SignalPrice", None)
        prevhd           = row.get("PrevHighDist", None)
        prevhv           = row.get("PrevHighVal", None)
        crossover        = row.get("Crossover", "")
        c940             = row.get("c940", {"signal": "", "body_pct": 0})
        c945             = row.get("c945", {"signal": "", "body_pct": 0})
        c950             = row.get("c950", {"signal": "", "body_pct": 0})
        sector           = row.get("Sector", "")

        # Row background — alternating, selected row blue-tint
        bg      = "#f8fafc" if i % 2 == 0 else "#ffffff"
        chg_col = "#16a34a" if float(chg) > 0 else "#dc2626"
        chg_sgn = "+" if float(chg) > 0 else ""

        rows_html += f"""
        <tr class="ts-row" style="background:{bg};">
            <td style="{TD_L}">
                <span onclick="tsCopy(event,this,'{sym}')"
                      style="cursor:pointer;color:#1e40af;font-weight:700;font-size:13px;">
                    <span class="ts-sym-name">{sym}</span>
                </span>
                <div style="font-size:10px;color:#94a3b8;margin-top:2px;">{sector}</div>
            </td>
            <td style="{TD}">{fmt_max_qty(maxqty)}</td>
            <td style="{TD}">
                <div style="font-weight:600;color:#1e293b;font-family:Consolas,monospace;">
                    &#8377;{float(price):.2f}
                </div>
                <div style="font-size:11px;color:{chg_col};font-weight:600;margin-top:1px;">
                    {chg_sgn}{float(chg):.2f}%
                </div>
            </td>
            <td style="{TD}">{fmt_vol_relvol(vol, relvol)}</td>
            <td style="{TD}">{fmt_signal_badge(signal_time, relvol)}</td>
            <td style="{TD}">{fmt_poc_gap(poc, gappct)}</td>
            <td style="{TD}">{fmt_pct_since_signal(signal_price_val, pct_since_signal)}</td>
            <td style="{TD}">{fmt_entry_badges(c940, c945, c950)}</td>
            <td style="{TD}">{fmt_prev_high(prevhd, prevhv)}</td>
            <td style="{TD}">{fmt_crossover(crossover)}</td>
        </tr>"""

    table_html = f"""
    <script>
    function tsCopy(e,btn,sym){{
      e.stopPropagation();
      function showCopied(){{
        var el=btn.querySelector('.ts-sym-name');
        if(!el)return;
        var orig=el.textContent;
        el.textContent='&#10003; '+sym;
        el.style.color='#16a34a';
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
    <style>
    .ts-row:hover {{ background: #f0f7ff !important; }}
    .ts-table-wrap {{ overflow-x:auto; border:1px solid #e2e6ed; border-radius:8px; margin-top:4px; }}
    </style>
    <div class="ts-table-wrap">
    <table style="width:100%;border-collapse:collapse;font-family:-apple-system,'Inter',sans-serif;">
      <thead>
        <tr>
          <th style="{TH_L}">Symbol</th>
          <th style="{TH}">Max Qty</th>
          <th style="{TH}">Price / Chg%</th>
          <th style="{TH}">Vol / RelVol</th>
          <th style="{TH}">Signal</th>
          <th style="{TH}">POC / Gap</th>
          <th style="{TH}">Sig Price / % Chg</th>
          <th style="{TH}">Entry Window</th>
          <th style="{TH}">Prev High</th>
          <th style="{TH}">Cross</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>
    """

    components.html(
        table_html,
        height=len(df) * height_per_row + extra_height,
        scrolling=False
    )

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: MARKET-CLOSED VIEW — 100% UNCHANGED
# ─────────────────────────────────────────────────────────────────────────────

def render_market_closed_view(df_market_closed):
    """
    Render market-closed mode display.
    Shows last saved data for the day (from Supabase cache). Read-only.
    """
    from .calculations import get_last_trading_day

    calc_date = get_last_trading_day()

    st.markdown(f"""
    <div style="background:#fefce8;border:1px solid #fef08a;border-radius:8px;
                padding:10px 16px;margin-bottom:10px;">
        <span style="color:#854f0b;font-weight:600;font-size:13px;">🔒 Market Closed</span>
        <span style="color:#6b7280;font-size:12px;">
            — showing last saved data for {calc_date.strftime('%d %b %Y')}.
            No live calculation happening.
        </span>
    </div>
    """, unsafe_allow_html=True)

    if df_market_closed.empty:
        st.info("Koi saved data available nahi hai is date ke liye.")
        return

    top_gainer = df_market_closed.iloc[0]['Symbol'] if len(df_market_closed) > 0 else '-'
    max_chg    = df_market_closed['Chg'].max() if len(df_market_closed) > 0 else 0.0

    st.markdown(f"""
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:6px 0;">
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;
                    padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">STOCKS</div>
            <div style="font-size:18px;font-weight:700;color:#16a34a;line-height:1.2;">
                {len(df_market_closed)}
            </div>
        </div>
        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;
                    padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">TOP GAINER</div>
            <div style="font-size:16px;font-weight:700;color:#2563eb;line-height:1.2;">
                {top_gainer}
            </div>
        </div>
        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;
                    padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">MAX CHG%</div>
            <div style="font-size:16px;font-weight:700;color:#16a34a;line-height:1.2;">
                +{max_chg:.2f}%
            </div>
        </div>
        <div style="background:#fdf4ff;border:1px solid #e9d5ff;border-radius:6px;
                    padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">POC DATE</div>
            <div style="font-size:13px;font-weight:700;color:#7c3aed;line-height:1.2;">
                {calc_date.strftime('%d %b')}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    render_stock_table(df_market_closed)
