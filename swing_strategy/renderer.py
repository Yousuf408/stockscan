# ──────────────────────────────────────────────────────────────────────────────
# swing_strategy/renderer.py
# Card UI for Swing Breakout Signals
# ──────────────────────────────────────────────────────────────────────────────

def get_status_style(status: str) -> tuple:
    """Returns (border_color, badge_bg, badge_color) based on status."""
    if status == "TRIGGERED":
        return "#059669", "#d1fae5", "#065f46"
    if status == "WATCHING":
        return "#2563eb", "#dbeafe", "#1e3a8a"
    if status == "EXITED":
        return "#94a3b8", "#f1f5f9", "#475569"
    return "#d97706", "#fef9c3", "#713f12"


def get_score_color(score: int) -> str:
    if score >= 8: return "#059669"
    if score >= 6: return "#d97706"
    return "#dc2626"


def format_vol_ratio(ratio) -> str:
    if not ratio:
        return "—"
    try:
        r = float(ratio)
        if r >= 5: return f"🔥 {r:.2f}x"
        if r >= 2: return f"🟢 {r:.2f}x"
        if r >= 1: return f"🟡 {r:.2f}x"
        return f"🔴 {r:.2f}x"
    except:
        return "—"


def render_swing_cards(signals: list) -> str:
    """
    Render swing breakout signals as cards.
    Each card shows:
    - Top row: Symbol + Signal date + Status badge + Zone score
    - Middle row: Zone info (resistance, support, width, consolidation days)
    - Bottom row: Entry, Stoploss, Target, Vol ratios, Breakout time
    """

    html = """
<style>
.sw-wrap{display:flex;flex-direction:column;gap:10px;padding:4px 0;font-family:sans-serif;}
.sw-card{background:#fff;border:0.5px solid #e2e8f0;border-radius:10px;padding:12px 16px;}

/* ── TOP ROW ── */
.sw-top{display:flex;align-items:center;gap:10px;margin-bottom:10px;}
.sw-sym{font-size:15px;font-weight:700;color:#0f172a;cursor:pointer;background:none;border:none;
        font-family:sans-serif;padding:0;letter-spacing:0.02em;}
.sw-sym:hover{text-decoration:underline;}
.sw-date{font-size:11px;color:#64748b;background:#f1f5f9;border-radius:4px;padding:2px 7px;}
.sw-sp{flex:1;}
.sw-badge{font-size:11px;font-weight:600;padding:3px 10px;border-radius:999px;white-space:nowrap;}
.sw-score-wrap{display:flex;flex-direction:column;align-items:center;flex-shrink:0;}
.sw-score{width:34px;height:34px;border-radius:50%;display:flex;align-items:center;
          justify-content:center;font-size:13px;font-weight:700;color:#fff;}
.sw-score-lbl{font-size:9px;color:#94a3b8;text-transform:uppercase;margin-top:2px;letter-spacing:0.04em;}

/* ── ZONE ROW ── */
.sw-zone{display:flex;align-items:center;gap:0;
         background:#f8fafc;border-radius:8px;padding:8px 12px;
         margin-bottom:10px;border:0.5px solid #e2e8f0;}
.sw-zm{display:flex;flex-direction:column;align-items:center;padding:0 14px;
       border-right:0.5px solid #e2e8f0;}
.sw-zm:last-child{border-right:none;}
.sw-zlbl{font-size:9px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;
         color:#94a3b8;margin-bottom:2px;white-space:nowrap;}
.sw-zval{font-size:12px;font-weight:600;color:#0f172a;white-space:nowrap;}
.sw-zval.res{color:#dc2626;}
.sw-zval.sup{color:#16a34a;}
.sw-zval.days{color:#2563eb;}

/* ── METRICS ROW ── */
.sw-metrics{display:flex;align-items:center;gap:0;
            border-top:0.5px solid #e2e8f0;padding-top:10px;}
.sw-m{display:flex;flex-direction:column;align-items:center;padding:0 12px;
      border-right:0.5px solid #e2e8f0;}
.sw-m:last-child{border-right:none;}
.sw-lbl{font-size:9px;font-weight:500;text-transform:uppercase;letter-spacing:0.05em;
        color:#94a3b8;margin-bottom:2px;white-space:nowrap;}
.sw-val{font-size:12px;font-weight:600;color:#0f172a;white-space:nowrap;}
.sw-val.entry{color:#2563eb;font-weight:700;}
.sw-val.sl{color:#dc2626;}
.sw-val.tgt{color:#059669;font-weight:700;}
.sw-val.time{color:#92400e;background:#fef3c7;border-radius:4px;padding:1px 6px;font-size:11px;}
.sw-val.none{color:#94a3b8;font-style:italic;}

/* ── TOAST ── */
.sw-toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);
          background:#0f172a;color:#fff;padding:7px 18px;border-radius:8px;
          font-size:12px;z-index:9999;opacity:0;transition:opacity 0.3s;pointer-events:none;}
.sw-toast.show{opacity:1;}
</style>

<div id="sw-toast" class="sw-toast">✅ Copied!</div>
<script>
function swCopy(sym){
    navigator.clipboard.writeText(sym);
    var t=document.getElementById('sw-toast');
    t.classList.add('show');
    setTimeout(function(){t.classList.remove('show');},1500);
}
</script>

<div class="sw-wrap">
"""

    if not signals:
        html += """
<div style="text-align:center;padding:40px;color:#94a3b8;font-size:14px;">
    No swing signals found. Run the scanner to detect setups.
</div>"""
    else:
        for s in signals:
            status  = s.get("status", "WATCHING")
            score   = s.get("zone_score", 0)
            symbol  = s.get("stock", "")
            sig_date = s.get("signal_date", "")

            border_color, badge_bg, badge_color = get_status_style(status)
            score_color = get_score_color(score)

            # ── Values ──────────────────────────────────────
            resistance   = s.get("resistance")
            support      = s.get("support")
            zone_high    = s.get("zone_high")
            zone_low     = s.get("zone_low")
            zone_width   = s.get("zone_width_pct")
            consol_days  = s.get("consolidation_days")

            entry_price  = s.get("entry_price")
            stoploss     = s.get("stoploss")
            target       = s.get("target")
            vol_daily    = s.get("vol_ratio_daily")
            vol_1h       = s.get("breakout_vol_ratio")
            b_time       = s.get("breakout_time")

            # Format helpers
            def fmt_price(v):
                return f"₹{float(v):.2f}" if v else "—"

            def fmt_pct(v):
                return f"{float(v):.1f}%" if v else "—"

            entry_str  = fmt_price(entry_price) if entry_price else "Waiting..."
            sl_str     = fmt_price(stoploss)    if stoploss    else "—"
            tgt_str    = fmt_price(target)      if target      else "—"
            time_str   = b_time                 if b_time      else "—"

            # RR ratio
            rr_str = "—"
            if entry_price and stoploss and target:
                try:
                    risk   = float(entry_price) - float(stoploss)
                    reward = float(target) - float(entry_price)
                    if risk > 0:
                        rr_str = f"{reward/risk:.1f}:1"
                except:
                    pass

            html += f"""
<div class="sw-card" style="border-left:4px solid {border_color};">

  <!-- TOP ROW -->
  <div class="sw-top">
    <button class="sw-sym" onclick="swCopy('{symbol}')">{symbol}</button>
    <span class="sw-date">📅 {sig_date}</span>
    <span class="sw-sp"></span>
    <span class="sw-badge" style="background:{badge_bg};color:{badge_color};">{status}</span>
    <div class="sw-score-wrap">
      <div class="sw-score" style="background:{score_color};">{score}</div>
      <span class="sw-score-lbl">Zone Score</span>
    </div>
  </div>

  <!-- ZONE ROW -->
  <div class="sw-zone">
    <div class="sw-zm">
      <span class="sw-zlbl">Resistance</span>
      <span class="sw-zval res">{fmt_price(resistance)}</span>
    </div>
    <div class="sw-zm">
      <span class="sw-zlbl">Support</span>
      <span class="sw-zval sup">{fmt_price(support)}</span>
    </div>
    <div class="sw-zm">
      <span class="sw-zlbl">Zone High</span>
      <span class="sw-zval">{fmt_price(zone_high)}</span>
    </div>
    <div class="sw-zm">
      <span class="sw-zlbl">Zone Low</span>
      <span class="sw-zval">{fmt_price(zone_low)}</span>
    </div>
    <div class="sw-zm">
      <span class="sw-zlbl">Zone Width</span>
      <span class="sw-zval">{fmt_pct(zone_width)}</span>
    </div>
    <div class="sw-zm">
      <span class="sw-zlbl">Consol Days</span>
      <span class="sw-zval days">{consol_days}d</span>
    </div>
  </div>

  <!-- METRICS ROW -->
  <div class="sw-metrics">
    <div class="sw-m">
      <span class="sw-lbl">Entry</span>
      <span class="sw-val {'entry' if entry_price else 'none'}">{entry_str}</span>
    </div>
    <div class="sw-m">
      <span class="sw-lbl">Stoploss</span>
      <span class="sw-val sl">{sl_str}</span>
    </div>
    <div class="sw-m">
      <span class="sw-lbl">Target</span>
      <span class="sw-val tgt">{tgt_str}</span>
    </div>
    <div class="sw-m">
      <span class="sw-lbl">R:R</span>
      <span class="sw-val">{rr_str}</span>
    </div>
    <div class="sw-m">
      <span class="sw-lbl">Daily Vol</span>
      <span class="sw-val">{format_vol_ratio(vol_daily)}</span>
    </div>
    <div class="sw-m">
      <span class="sw-lbl">1H Vol</span>
      <span class="sw-val">{format_vol_ratio(vol_1h)}</span>
    </div>
    <div class="sw-m">
      <span class="sw-lbl">Breakout Time</span>
      <span class="sw-val {'time' if b_time else 'none'}">{time_str if b_time else 'Waiting...'}</span>
    </div>
  </div>

</div>"""

    html += "\n</div>"
    return html
