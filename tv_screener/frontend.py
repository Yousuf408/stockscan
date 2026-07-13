# ═══════════════════════════════════════════════════════════════════════════════
# TV SCREENER FRONTEND MODULE
# Display formatting, table rendering, UI helpers
# ═══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
import json

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: ORDER RESULT DISPLAY (clean short message, expandable full details)
# ─────────────────────────────────────────────────────────────────────────────

def display_order_result(symbol, result, max_inline_length=100):
    """
    Show order placement result cleanly:
      - Success: short green message with order ID
      - Failure: try to extract a clean human-readable error (Dhan/AlgoMojo
        errors are usually JSON with an 'errorMessage'/'message' field).
        If the clean message is short, show it inline. If it's still long
        (or extraction failed), show a short summary inline + full raw
        error in a collapsed expander — instead of dumping everything
        into one long red message box.

    Args:
        symbol (str): Stock symbol (for the message prefix)
        result (dict): {"success": bool, "order_id": str, "error": str}
        max_inline_length (int): Threshold above which details move to expander
    """
    if result.get('success'):
        st.success(f"✅ {symbol} | Order ID: {result['order_id']}")
        return

    raw_error = str(result.get('error', 'Unknown error'))
    clean_msg = raw_error

    # Try to pull out just the human-readable error message from a JSON
    # blob embedded in the raw error string (e.g. Dhan's errorMessage field)
    try:
        if '{' in raw_error:
            json_str = raw_error[raw_error.index('{'):].split('| Payload sent:')[0].strip()
            parsed = json.loads(json_str)
            clean_msg = parsed.get('errorMessage') or parsed.get('message') or clean_msg
    except Exception:
        pass

    if len(clean_msg) <= max_inline_length:
        st.error(f"❌ {symbol}: {clean_msg}")
    else:
        st.error(f"❌ {symbol}: {clean_msg[:max_inline_length]}...")
        with st.expander("Show full error details"):
            st.code(raw_error)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: TABLE STYLING CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Header cell styles (center-aligned, except first column)
TH = "padding:8px 10px;font-size:11px;font-weight:700;color:#6b7280;border-bottom:2px solid #e5e7eb;white-space:nowrap;text-align:center;"
TH_L = "padding:8px 10px;font-size:11px;font-weight:700;color:#6b7280;border-bottom:2px solid #e5e7eb;text-align:left;"

# Data cell styles (center-aligned, except first column)
TD = "padding:8px 10px;font-size:12px;border-bottom:1px solid #f3f4f6;white-space:nowrap;text-align:center;vertical-align:middle;"
TD_L = "padding:8px 10px;font-size:12px;border-bottom:1px solid #f3f4f6;text-align:left;vertical-align:middle;"

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — VOLUME
# ─────────────────────────────────────────────────────────────────────────────

def fmt_volume(v):
    """
    Format volume into human-readable units (M/L/K).
    
    Args:
        v: Volume value (float or str)
    
    Returns:
        str: Formatted volume (e.g., "2.5M", "50K")
    """
    try:
        v = float(v)
        if v >= 1_000_000: 
            return f"{v/1_000_000:.1f}M"
        if v >= 100_000:   
            return f"{v/100_000:.1f}L"
        if v >= 1_000:     
            return f"{v/1_000:.1f}K"
        return str(int(v))
    except: 
        return str(v)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — RELATIVE VOLUME
# ─────────────────────────────────────────────────────────────────────────────

def fmt_relvol(v):
    """
    Format relative volume with color coding.
    
    Color scheme:
      >= 3.0x : Yellow background (high alert)
      >= 1.5x : Green background (elevated)
      < 1.5x  : Gray text (normal)
    
    Args:
        v: Relative volume value (float)
    
    Returns:
        str: HTML-formatted relative volume
    """
    if v is None:
        return '<span style="color:#9ca3af;">N/A</span>'
    try:
        v = float(v)
        if v >= 3:     
            bg, color = "#fef9c3", "#854f0b"
        elif v >= 1.5: 
            bg, color = "#dcfce7", "#166534"
        else:          
            bg, color = "transparent", "#374151"
        return f'<span style="background:{bg};color:{color};padding:2px 7px;border-radius:4px;font-weight:600;">{v:.2f}x</span>'
    except: 
        return '<span style="color:#9ca3af;">N/A</span>'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — ENTRY SIGNAL BADGES
# ─────────────────────────────────────────────────────────────────────────────

def fmt_entry_badges(c940, c945, c950):
    """
    Format entry candle signals as badges (9:40, 9:45, 9:50).
    
    Green badge = bullish candle detected, Gray = not yet/bearish.
    
    Args:
        c940, c945, c950 (str): Candle signal ("green" or "")
    
    Returns:
        str: HTML badge display
    """
    def badge(label, active):
        if active == "green":
            return f'<span style="background:#dcfce7;color:#166534;border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600;">{label}</span>'
        else:
            return f'<span style="color:#d1d5db;font-size:11px;padding:2px 5px;">{label}</span>'
    return f'{badge("9:40", c940)}&nbsp;{badge("9:45", c945)}&nbsp;{badge("9:50", c950)}'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — POC & GAP
# ─────────────────────────────────────────────────────────────────────────────

def fmt_poc_gap(poc, gap_pct):
    """
    Format POC price and gap % with color coding.
    
    Green = gap up, Red = gap down. Intensity based on magnitude.
    
    Args:
        poc (float): Point of Control price
        gap_pct (float): Gap percentage from POC
    
    Returns:
        str: HTML-formatted POC + gap display
    """
    if poc is None:
        return '<span style="color:#9ca3af;">N/A</span>'
    poc_str = f"₹{float(poc):,.2f}"
    if gap_pct is None:
        return f'<div style="font-size:12px;">{poc_str}</div>'
    if gap_pct > 0:
        if gap_pct >= 5:   
            color = "#14532d"
        elif gap_pct >= 2: 
            color = "#16a34a"
        else:              
            color = "#4ade80"
        gap_str = f'<span style="color:{color};font-weight:700;">↑ +{gap_pct:.1f}%</span>'
    else:
        gap_str = f'<span style="color:#dc2626;font-weight:600;">↓ {gap_pct:.1f}%</span>'
    return f'<div style="font-size:12px;font-weight:500;">{poc_str}</div><div style="font-size:11px;">{gap_str}</div>'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — PREVIOUS HIGH DISTANCE
# ─────────────────────────────────────────────────────────────────────────────

def fmt_prev_high(dist, val):
    """
    Format previous day's high with distance %, color-coded.
    
    Green = above prev high (bullish), Red = below prev high.
    
    Args:
        dist (float): Distance % from previous high
        val (float): Previous high price value
    
    Returns:
        str: HTML-formatted display
    """
    if dist is None or val is None:
        return '<span style="color:#9ca3af;">N/A</span>'
    val_str = f"₹{val:,.2f}"
    if dist >= 0:
        if dist >= 3:   
            color = "#14532d"
        elif dist >= 1: 
            color = "#16a34a"
        else:           
            color = "#4ade80"
        pct_str = f'<span style="color:{color};font-weight:700;">↑ +{dist:.1f}%</span>'
    else:
        pct_str = f'<span style="color:#dc2626;font-weight:600;">↓ {dist:.1f}%</span>'
    return f'<div style="font-size:12px;font-weight:500;">{val_str}</div><div style="font-size:11px;">{pct_str}</div>'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — EMA COIL
# ─────────────────────────────────────────────────────────────────────────────

# fmt_ema_coil() — REMOVED, EMA Coil column no longer used in the strategy.

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — CROSSOVER SIGNAL
# ─────────────────────────────────────────────────────────────────────────────

def fmt_crossover(matched_candle):
    """
    Format crossover signal as badge.
    
    Green checkmark = 9:15 (strict), Pink checkmark = 9:20 (flexible).
    
    Args:
        matched_candle (str): "09:15", "09:20", or ""
    
    Returns:
        str: HTML badge or empty
    """
    if matched_candle == "09:15":
        return '<span style="background:#dcfce7;color:#166534;border-radius:4px;padding:3px 9px;font-weight:700;">✓</span>'
    elif matched_candle == "09:20":
        return '<span style="background:#fce7f3;color:#9d174d;border-radius:4px;padding:3px 9px;font-weight:700;">✓</span>'
    else:
        return ''

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — MAX QUANTITY
# ─────────────────────────────────────────────────────────────────────────────

def fmt_max_qty(qty):
    """
    Format max-quantity value (from DhanHQ margin-based calculation).

    Shows "—" if quantity couldn't be determined (0 or None) — e.g. symbol
    not found in Dhan's instrument master, or margin API call failed.

    Args:
        qty: Max quantity value (int or None)

    Returns:
        str: HTML-formatted quantity badge
    """
    if qty is None or qty <= 0:
        return '<span style="color:#9ca3af;">—</span>'
    return f'<span style="background:#eff6ff;color:#1e40af;padding:2px 8px;border-radius:4px;font-weight:700;">{int(qty)}</span>'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: FORMATTING HELPERS — % SINCE SIGNAL
# ─────────────────────────────────────────────────────────────────────────────

def fmt_pct_since_signal(pct):
    """
    Format the live "% moved since this stock's signal was first detected"
    value, color-coded (green = up since signal, red = down since signal).

    Args:
        pct (float): % change since signal_price, or None if not available

    Returns:
        str: HTML-formatted percentage
    """
    if pct is None:
        return '<span style="color:#9ca3af;">—</span>'
    if pct >= 0:
        color = "#16a34a"
        sign = "+"
    else:
        color = "#dc2626"
        sign = ""
    return f'<span style="color:{color};font-weight:600;">{sign}{pct:.2f}%</span>'

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: TABLE RENDERING
# ─────────────────────────────────────────────────────────────────────────────

def render_stock_table(df, height_per_row=52, extra_height=60):
    """
    Render main stock results table with all columns.
    
    Interactive: Click symbol to copy to clipboard.
    Color-coded: Prices, changes, volumes, signals all visually distinct.
    
    Args:
        df (pd.DataFrame): Data with columns:
                          [Symbol, Price, Chg, Volume, RelVol5D, POC, GapPct,
                           c940, c945, c950, PrevHighDist, PrevHighVal, 
                           EmaCoilPct, Crossover, MktCap, Sector]
        height_per_row (int): Pixels per row (default 52)
        extra_height (int): Extra padding (default 60)
    """
    rows_html = ""
    for i, (_, row) in enumerate(df.iterrows()):
        sym    = row.get("Symbol", "")
        maxqty = row.get("MaxQty", None)
        price  = row.get("Price", 0)
        chg    = row.get("Chg", 0)
        vol    = row.get("Volume", 0)
        relvol = row.get("RelVol5D", 0)
        poc    = row.get("POC", None)
        gappct = row.get("GapPct", None)
        pct_since_signal = row.get("PctSinceSignal", None)
        prevhd = row.get("PrevHighDist", None)
        prevhv = row.get("PrevHighVal", None)
        crossover = row.get("Crossover", "")
        c940   = row.get("c940", "")
        c945   = row.get("c945", "")
        c950   = row.get("c950", "")
        mktcap = row.get("MktCap", "")
        sector = row.get("Sector", "")

        bg      = "#f9fafb" if i % 2 == 0 else "#ffffff"
        chg_col = "#16a34a" if float(chg) > 0 else "#dc2626"
        chg_sgn = "+" if float(chg) > 0 else ""

        rows_html += f"""
        <tr style="background:{bg};">
            <td style="{TD_L}">
                <span onclick="tsCopy(event,this,'{sym}')" style="cursor:pointer;color:#1e40af;font-weight:700;">
                    <span class="ts-sym-name">{sym}</span>
                </span>
                <div style="font-size:10px;color:#9ca3af;margin-top:1px;">{sector}</div>
            </td>
            <td style="{TD}">{fmt_max_qty(maxqty)}</td>
            <td style="{TD}">
                <div style="font-weight:600;color:#111827;">₹{float(price):.2f}</div>
                <div style="font-size:11px;color:{chg_col};font-weight:600;">{chg_sgn}{float(chg):.2f}%</div>
            </td>
            <td style="{TD}">{fmt_volume(vol)}</td>
            <td style="{TD}">{fmt_relvol(relvol)}</td>
            <td style="{TD}">{fmt_poc_gap(poc, gappct)}</td>
            <td style="{TD}">{fmt_pct_since_signal(pct_since_signal)}</td>
            <td style="{TD}">{fmt_entry_badges(c940, c945, c950)}</td>
            <td style="{TD}">{fmt_prev_high(prevhd, prevhv)}</td>
            <td style="{TD}">{fmt_crossover(crossover)}</td>
            <td style="{TD};color:#374151;">₹{float(mktcap):.1f}B</td>
        </tr>"""

    table_html = f"""
    <script>
    function tsCopy(e,btn,sym){{
      e.stopPropagation();
      function showCopied(){{
        var el=btn.querySelector('.ts-sym-name');
        if(!el)return;
        var orig=el.textContent;
        el.textContent='✓ '+sym;
        el.style.color='#00a854';
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
    <div style="overflow-x:auto;border:1px solid #e5e7eb;border-radius:8px;margin-top:8px;">
    <table style="width:100%;border-collapse:collapse;font-family:sans-serif;">
      <thead style="background:#f9fafb;">
        <tr>
          <th style="{TH_L}">Symbol</th>
          <th style="{TH}">Max Qty</th>
          <th style="{TH}">Price / Chg%</th>
          <th style="{TH}">Volume</th>
          <th style="{TH}">Rel Vol</th>
          <th style="{TH}">POC / Gap</th>
          <th style="{TH}">% Since Signal</th>
          <th style="{TH}">Entry Signal</th>
          <th style="{TH}">Prev High</th>
          <th style="{TH}">Crossover</th>
          <th style="{TH}">Mkt Cap</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    </div>
    """

    components.html(table_html, height=len(df) * height_per_row + extra_height, scrolling=False)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION: MARKET-CLOSED VIEW (READ-ONLY)
# ─────────────────────────────────────────────────────────────────────────────

def render_market_closed_view(df_market_closed):
    """
    Render market-closed mode display.
    
    Shows last saved data for the day (from Supabase cache).
    No live calculations — read-only mode.
    
    Args:
        df_market_closed (pd.DataFrame): Prepared market-closed data
    """
    from .calculations import get_last_trading_day
    
    calc_date = get_last_trading_day()

    st.markdown(f"""
    <div style="background:#fefce8;border:1px solid #fef08a;border-radius:8px;padding:10px 16px;margin-bottom:10px;">
        <span style="color:#854f0b;font-weight:600;font-size:13px;">🔒 Market Closed</span>
        <span style="color:#6b7280;font-size:12px;"> — showing last saved data for {calc_date.strftime('%d %b %Y')}. No live calculation happening.</span>
    </div>
    """, unsafe_allow_html=True)

    if df_market_closed.empty:
        st.info("Koi saved data available nahi hai is date ke liye.")
        return

    # Header cards
    top_gainer = df_market_closed.iloc[0]['Symbol'] if len(df_market_closed) > 0 else '-'
    max_chg    = df_market_closed['Chg'].max() if len(df_market_closed) > 0 else 0.0

    st.markdown(f"""
    <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:6px 0;">
        <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">STOCKS</div>
            <div style="font-size:18px;font-weight:700;color:#16a34a;line-height:1.2;">{len(df_market_closed)}</div>
        </div>
        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">TOP GAINER</div>
            <div style="font-size:16px;font-weight:700;color:#2563eb;line-height:1.2;">{top_gainer}</div>
        </div>
        <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">MAX CHG%</div>
            <div style="font-size:16px;font-weight:700;color:#16a34a;line-height:1.2;">+{max_chg:.2f}%</div>
        </div>
        <div style="background:#fdf4ff;border:1px solid #e9d5ff;border-radius:6px;padding:5px 12px;text-align:center;">
            <div style="font-size:10px;color:#6b7280;font-weight:600;">POC DATE</div>
            <div style="font-size:13px;font-weight:700;color:#7c3aed;line-height:1.2;">{calc_date.strftime('%d %b')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    render_stock_table(df_market_closed)
