"""
momentum/renderer.py — EXACT original + Phase/Vol Trend columns only
"""

def _short_vol(vol: float) -> str:
    if vol >= 1_000_000:
        return f"{vol/1_000_000:.2f}M"
    if vol >= 1_000:
        return f"{vol/1_000:.1f}K"
    return str(int(vol))


def _ema_cell(status) -> str:
    if status is None or status == "⏳":
        return '<span style="color:#94a3b8">⏳</span>'
    s = str(status)
    if s.startswith("✅"):
        return f'<span class="ema-pass">{s}</span>'
    if "Below" in s:
        return f'<span class="ema-fail">{s}</span>'
    if s.startswith("❌"):
        return f'<span class="ema-ext">{s}</span>'
    return f'<span style="color:#94a3b8">{s}</span>'


def _ema9_cell(status: str, ema9_value) -> str:
    if not status or status == "⏳":
        return '<span style="color:#94a3b8">⏳</span>'
    s = str(status)
    if s.startswith("✅"):   color = "#16a34a"
    elif s.startswith("⚠️"): color = "#d97706"
    elif s.startswith("❌"): color = "#dc2626"
    elif s.startswith("📉"): color = "#7c3aed"
    else:                    color = "#94a3b8"
    val_html = ""
    if ema9_value is not None:
        try:
            val_html = f'<div class="num-primary">₹{float(ema9_value):,.2f}</div>'
        except Exception:
            pass
    pct_html = f'<div style="color:{color};font-weight:700;font-size:13px;">{s}</div>'
    return f'{val_html}{pct_html}'


def _phase_cell(phase: str) -> str:
    if not phase or phase in ("⏳ Forming", "⏳"):
        return '<span style="color:#94a3b8;font-size:12px">⏳ Forming</span>'
    s = str(phase)
    if   "BUILDING"  in s: color, bg, border = "#15803d", "#f0fdf4", "#bbf7d0"
    elif "PULLBACK"  in s: color, bg, border = "#b45309", "#fffbeb", "#fde68a"
    elif "REVERSAL"  in s: color, bg, border = "#be123c", "#fff1f2", "#fecdd3"
    else:                  color, bg, border = "#64748b", "#f1f5f9", "#e2e8f0"
    return (f'<span style="display:inline-flex;align-items:center;padding:2px 8px;'
            f'border-radius:4px;font-size:12px;font-weight:700;white-space:nowrap;'
            f'background:{bg};color:{color};border:1px solid {border}">{s}</span>')

def _vol_trend_cell(vol_trend: str) -> str:
    if not vol_trend:
        return '<span style="color:#94a3b8;font-size:13px">→ Stable</span>'
    s = str(vol_trend)
    if s.startswith("↑"): return f'<span style="color:#16a34a;font-weight:700;font-size:14px">{s}</span>'
    if s.startswith("↓"): return f'<span style="color:#dc2626;font-weight:700;font-size:14px">{s}</span>'
    return f'<span style="color:#94a3b8;font-weight:600;font-size:14px">{s}</span>'


def _move_color(val: float) -> str:
    if val >= 5.0: return "#16a34a"
    if val >= 2.0: return "#ca8a04"
    if val >= 0:   return "#64748b"
    return "#dc2626"


def _vol_badge(vm: str) -> str:
    if "Very Strong" in vm or "🔥" in vm:
        return '<span class="vol-badge vol-high">🔥 Very Strong</span>'
    if "Strong" in vm or "⚡" in vm:
        return '<span class="vol-badge vol-med">⚡ Strong</span>'
    if "Building" in vm or "👀" in vm:
        return '<span class="vol-badge vol-low">👀 Building</span>'
    return f'<span class="vol-badge vol-low">{vm}</span>'


def _vol_emoji(vm: str) -> str:
    if "Very Strong" in vm or "🔥" in vm: return "🔥"
    if "Strong"      in vm or "⚡" in vm: return "⚡"
    if "Building"    in vm or "👀" in vm: return "👀"
    return ""


def _mom_badge(mom: str, vol_ratio: float = 0.0, intraday_pct: float = 0.0) -> str:
    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    if "STRONG BUILDING" in mom:
        vol_p   = _clamp((vol_ratio    - 2.5) / (5.0 - 2.5), 0, 1)
        intra_p = _clamp((intraday_pct - 1.5) / (4.0 - 1.5), 0, 1)
        within  = vol_p * 0.4 + intra_p * 0.6
        fill_pct   = int(66 + within * 34)
        fill_color = "#7c3aed"
        badge_html = f'<span class="badge badge-accel">{mom}</span>'
        next_label = "🏆 Top Level"

    elif "BUILDING" in mom:
        vol_p   = _clamp((vol_ratio    - 2.0) / (2.5 - 2.0), 0, 1)
        intra_p = _clamp((intraday_pct - 0.8) / (1.5 - 0.8), 0, 1)
        within  = vol_p * 0.4 + intra_p * 0.6
        fill_pct   = int(33 + within * 33)
        fill_color = "#22c55e"
        badge_html = f'<span class="badge badge-bull">{mom}</span>'
        v_need     = max(0.0, round(2.5 - vol_ratio, 1))
        i_need     = max(0.0, round(1.5 - intraday_pct, 1))
        next_label = f"→ Strong: need {v_need}x vol · {i_need}% move"

    elif "STABLE" in mom:
        vol_p   = _clamp((vol_ratio    - 1.5) / (2.0 - 1.5), 0, 1)
        intra_p = _clamp((intraday_pct - 0.0) / (0.8 - 0.0), 0, 1)
        within  = vol_p * 0.4 + intra_p * 0.6
        fill_pct   = int(20 + within * 13)
        fill_color = "#3b82f6"
        badge_html = f'<span class="badge badge-hold">{mom}</span>'
        v_need     = max(0.0, round(2.0 - vol_ratio, 1))
        i_need     = max(0.0, round(0.8 - intraday_pct, 1))
        next_label = f"→ Building: need {v_need}x vol · {i_need}% move"

    elif "COOLING" in mom:
        vol_p   = _clamp((vol_ratio    - 1.5) / (2.0 - 1.5), 0, 1)
        intra_p = _clamp((intraday_pct + 3.0) / 3.0,          0, 1)
        within  = vol_p * 0.4 + intra_p * 0.6
        fill_pct   = int(10 + within * 10)
        fill_color = "#f59e0b"
        badge_html = f'<span class="badge badge-watch">{mom}</span>'
        next_label = "→ Building: price must turn +ve"

    elif "WEAK" in mom:
        vol_p   = _clamp((vol_ratio    - 1.5) / (2.0 - 1.5), 0, 1)
        intra_p = _clamp((intraday_pct - 1.0) / (0.8        ), 0, 1)
        within  = vol_p * 0.4 + intra_p * 0.6
        fill_pct   = int(within * 20)
        fill_color = "#ef4444"
        badge_html = f'<span class="badge badge-bear">{mom}</span>'
        v_need     = max(0.0, round(2.0 - vol_ratio, 1))
        next_label = f"→ Building: need {v_need}x more vol"

    else:
        return f'<span class="badge badge-hold">{mom}</span>'

    pct_color = fill_color
    is_top    = "STRONG BUILDING" in mom

    return (
        f'<div class="mom-wrap">'
        f'  <div class="mom-top-row">'
        f'    {badge_html}'
        f'    <span class="mom-pct-label" style="color:{pct_color}">{fill_pct}%</span>'
        f'  </div>'
        f'  <div class="mom-progress-bar">'
        f'    <div class="mom-progress-fill" style="width:{fill_pct}%;background:{fill_color};"></div>'
        f'  </div>'
        f'  <div class="mom-next-label">{"✅ Top Level" if is_top else next_label}</div>'
        f'</div>'
    )


def _chg_html(val: float) -> str:
    cls  = "chg-pos" if val >= 0 else "chg-neg"
    sign = "▲" if val >= 0 else "▼"
    return f'<span class="{cls}">{sign} {abs(val):.2f}%</span>'


def _signal_price_html(signal_price_str: str, move_since: float) -> str:
    positive  = move_since >= 0
    w         = min(abs(move_since) * 10, 100)
    fill_cls  = "fill-green" if positive else "fill-red"
    color     = _move_color(move_since)
    sign      = "+" if positive else ""
    pct_str   = f"{sign}{move_since:.2f}%"
    return (
        f'<div class="sig-price-wrap">'
        f'  <div class="sig-top-row">'
        f'    <span class="num-primary">{signal_price_str}</span>'
        f'    <span class="bar-pct" style="color:{color}">{pct_str}</span>'
        f'  </div>'
        f'  <div class="progress-bar"><div class="progress-fill {fill_cls}" style="width:{w:.0f}%"></div></div>'
        f'</div>'
    )


def _progress_html(val: float) -> str:
    positive  = val >= 0
    w         = min(abs(val) * 10, 100)
    fill_cls  = "fill-green" if positive else "fill-red"
    color     = _move_color(val)
    sign      = "+" if positive else ""
    return (
        f'<div class="bar-row">'
        f'<div class="progress-bar"><div class="progress-fill {fill_cls}" style="width:{w:.0f}%"></div></div>'
        f'<span class="bar-pct" style="color:{color}">{sign}{val:.2f}%</span>'
        f'</div>'
    )


_STYLES = """
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  margin: 0 !important; padding: 0 !important;
  background: linear-gradient(135deg, #f0f4ff 0%, #f8faff 55%, #eef6f2 100%) !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
  color: #1a202c; font-size: 13px;
}

/* ── FILTER BAR ── */
.filterbar {
  background: rgba(255,255,255,0.85);
  border-bottom: 1px solid rgba(224,227,232,0.8);
  padding: 8px 16px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  backdrop-filter: blur(6px);
}
.filter-label { font-size: 12px; font-weight: 700; color: #374151; }
.filter-count {
  background: rgba(241,245,249,0.9); border: 1px solid #e2e8f0;
  padding: 3px 8px; border-radius: 4px; font-size: 12px; color: #64748b;
}
.filter-count b { color: #00a854; }
select.filter-select {
  border: 1px solid #e0e3e8; background: rgba(255,255,255,0.9);
  padding: 6px 28px 6px 10px; border-radius: 6px;
  font-size: 13px; color: #374151; cursor: pointer; outline: none; appearance: none;
  height: 36px;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center;
}
select.filter-select:focus { border-color: #00a854; }
.filter-sep { width: 1px; height: 20px; background: #e2e8f0; }
.meta-info { margin-left: auto; font-size: 13px; font-weight: 600; color: #0f172a; }

/* ── TABLE WRAP ── */
.table-wrap { padding: 12px 16px; overflow-x: auto; }
table {
  width: 100%; border-collapse: collapse;
  background: rgba(255,255,255,0.6);
  border-radius: 12px;
  border: 1px solid rgba(255,255,255,0.9);
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04);
  backdrop-filter: blur(8px);
}

/* ── HEADER ── */
thead tr {
  background: rgba(248,250,252,0.9);
}
th {
  padding: 10px 10px; text-align: left; font-size: 11px; font-weight: 700;
  color: #64748b; border-bottom: 1px solid rgba(224,227,232,0.8); white-space: nowrap;
  cursor: pointer; user-select: none; transition: background 0.15s;
  border-right: 1px solid rgba(224,227,232,0.6);
  text-transform: uppercase; letter-spacing: 0.5px;
}
th:last-child { border-right: none; }
th:hover { background: rgba(240,244,255,0.9); color: #0f172a; }
th.active-col { background: rgba(0,168,84,0.08) !important; color: #00a854 !important; }
th .sort-arrow { margin-left: 4px; font-size: 10px; opacity: 0.4; }
th.active-col .sort-arrow { opacity: 1; }
th.th-ema   { color: #15803d; }
th.th-sig   { color: #7c3aed; }
th.th-ema9  { color: #0369a1; }
th.th-phase { color: #5b21b6; }
th.th-trend { color: #15803d; }

/* ── ROWS ── */
tbody tr.main-row {
  border-bottom: 1px solid rgba(224,227,232,0.6);
  cursor: pointer; transition: background 0.12s;
  border-left: 4px solid transparent;
  background: rgba(255,255,255,0.5);
}
tbody tr.main-row:hover   { background: rgba(255,255,255,0.85); }
tbody tr.main-row.expanded { background: rgba(240,249,255,0.9); border-bottom: none; }
tbody tr.main-row:nth-child(even) { background: rgba(248,250,252,0.5); }
tbody tr.main-row:nth-child(even):hover { background: rgba(255,255,255,0.85); }

/* Left border by momentum */
tbody tr.main-row.mom-strong  { border-left: 4px solid #7c3aed; }
tbody tr.main-row.mom-build   { border-left: 4px solid #22c55e; }
tbody tr.main-row.mom-stable  { border-left: 4px solid #3b82f6; }
tbody tr.main-row.mom-cooling { border-left: 4px solid #f59e0b; }
tbody tr.main-row.mom-weak    { border-left: 4px solid #ef4444; }

td {
  padding: 9px 10px; vertical-align: middle; white-space: nowrap;
  border-right: 1px solid rgba(224,227,232,0.5);
  font-size: 13px; color: #374151;
  border-bottom: 1px solid rgba(224,227,232,0.5);
}
td:last-child { border-right: none; }
td.active-col { background: rgba(0,168,84,0.05); }

/* ── EXPAND ROW ── */
tr.expand-row td { padding: 0; border-bottom: 2px solid #00a854; }
.expand-panel {
  background: rgba(240,250,245,0.8);
  padding: 12px 16px;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px;
  backdrop-filter: blur(4px);
}
.expand-card {
  background: rgba(255,255,255,0.85);
  border: 1px solid rgba(0,168,84,0.15);
  border-radius: 8px; padding: 8px 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.expand-card .ec-label { font-size: 10px; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.expand-card .ec-value { font-size: 13px; font-weight: 700; color: #1e3a5f; margin-top: 2px; }
.expand-card .ec-sub   { font-size: 10px; color: #94a3b8; margin-top: 1px; }

/* ── STOCK CELL ── */
.stock-cell { display: flex; align-items: center; gap: 8px; }
.expand-icon {
  width: 18px; height: 18px; border-radius: 4px;
  background: #e2e8f0; color: #64748b;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; flex-shrink: 0; transition: all 0.15s;
}
tr.expanded .expand-icon { background: #00a854; color: #fff; }
.stock-name { font-weight: 700; font-size: 13px; color: #1e3a5f; }

/* ── BADGES ── */
.badge {
  display: inline-flex; align-items: center; gap: 3px;
  padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 700; white-space: nowrap;
}
.badge-bull  { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.badge-bear  { background: #fff1f2; color: #be123c; border: 1px solid #fecdd3; }
.badge-watch { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
.badge-hold  { background: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd; }
.badge-accel { background: #faf5ff; color: #7c3aed; border: 1px solid #ddd6fe; }

/* ── VOL BADGE ── */
.vol-badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 700; }
.vol-high  { background: #fff7ed; color: #c2410c; }
.vol-med   { background: #e0f2fe; color: #075985; }
.vol-low   { background: #f1f5f9; color: #64748b; }

/* ── SIGNAL PRICE ── */
.sig-price-wrap { display: flex; flex-direction: column; gap: 3px; min-width: 110px; }
.sig-top-row    { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.progress-bar   { width: 100%; height: 3px; background: rgba(224,227,232,0.8); border-radius: 3px; overflow: hidden; }
.progress-fill  { height: 100%; border-radius: 3px; transition: width 0.3s; }
.fill-green { background: #22c55e; }
.fill-red   { background: #ef4444; }
.bar-pct    { font-size: 11px; font-weight: 600; white-space: nowrap; }

/* ── MOMENTUM ── */
.mom-wrap         { display: flex; flex-direction: column; gap: 3px; min-width: 160px; }
.mom-top-row      { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.mom-pct-label    { font-size: 12px; font-weight: 700; white-space: nowrap; }
.mom-progress-bar { width: 100%; height: 3px; background: rgba(224,227,232,0.8); border-radius: 3px; overflow: hidden; }
.mom-progress-fill{ height: 100%; border-radius: 3px; transition: width 0.4s ease; }
.mom-next-label   { font-size: 11px; color: #94a3b8; font-weight: 500; white-space: nowrap; }

/* ── NUMBERS ── */
.num-primary { font-size: 13px; font-weight: 700; color: #0f172a; }
.chg-pos  { color: #16a34a; font-weight: 600; font-size: 12px; }
.chg-neg  { color: #dc2626; font-weight: 600; font-size: 12px; }
.ema-pass { color: #16a34a; font-weight: 600; font-size: 12px; }
.ema-fail { color: #dc2626; font-weight: 600; font-size: 12px; }
.ema-ext  { color: #ea580c; font-weight: 600; font-size: 12px; }
.ltp-val  { font-size: 13px; font-weight: 700; color: #0f172a; }
.peak-val { color: #0f172a; font-weight: 700; font-size: 13px; }

/* ── COPY BUTTON ── */
.copy-btn {
  cursor: pointer; font-weight: 700; color: #1e3a5f;
  background: transparent; border: none; padding: 0;
  font-size: 13px; transition: color 0.2s;
}
.copy-btn:hover  { color: #00a854; }
.copy-btn.copied { color: #00a854; }

/* ── TOAST ── */
.toast {
  position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
  background: #0f172a; color: white; padding: 8px 20px;
  border-radius: 8px; font-size: 13px; z-index: 9999;
  opacity: 0; transition: opacity 0.3s; pointer-events: none;
}
.toast.show { opacity: 1; }

/* ── SCROLLBAR ── */
::-webkit-scrollbar { height: 5px; width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #cdd1d8; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #00a854; }
</style>

<div id="toast" class="toast">✅ Copied!</div>

<script>
function copySymbol(btn, symbol) {
    navigator.clipboard.writeText(symbol);
    btn.classList.add('copied');
    btn.innerText = '✓ ' + symbol;
    var toast = document.getElementById('toast');
    toast.classList.add('show');
    setTimeout(function() {
        btn.classList.remove('copied');
        btn.innerText = symbol;
        toast.classList.remove('show');
    }, 1500);
}
var activeCol = -1;
function toggleRow(sym) {
    var mainRow = document.getElementById('main-' + sym);
    var expRow  = document.getElementById('exp-'  + sym);
    if (!expRow) return;
    var isOpen = expRow.style.display !== 'none';
    expRow.style.display = isOpen ? 'none' : 'table-row';
    mainRow.classList.toggle('expanded', !isOpen);
    var icon = mainRow.querySelector('.expand-icon');
    if (icon) icon.textContent = isOpen ? '+' : '−';
}
function toggleColExpand(col) {
    document.querySelectorAll('th').forEach(function(th) { th.classList.remove('active-col'); });
    document.querySelectorAll('td').forEach(function(td) { td.classList.remove('active-col'); });
    if (activeCol === col) { activeCol = -1; return; }
    activeCol = col;
    document.querySelectorAll('th')[col].classList.add('active-col');
    document.querySelectorAll('tbody tr.main-row').forEach(function(row) {
        var cells = row.querySelectorAll('td');
        if (cells[col]) cells[col].classList.add('active-col');
    });
}
function applyFilter() {
    var momVal = document.getElementById('momFilter').value.toLowerCase();
    var emaVal = document.getElementById('emaFilter').value;
    localStorage.setItem('momFilter', momVal);
    localStorage.setItem('emaFilter', emaVal);
    var rows   = document.querySelectorAll('tbody tr.main-row');
    var count  = 0;
    rows.forEach(function(row) {
        var mom = (row.dataset.mom || '').toLowerCase();
        var ema = (row.dataset.ema || '');
        var show = true;
        if (momVal && !mom.includes(momVal)) show = false;
        if (emaVal === 'pass' && !ema.includes('✅')) show = false;
        if (emaVal === 'fail' && !ema.includes('❌')) show = false;
        row.style.display = show ? '' : 'none';
        var expRow = document.getElementById('exp-' + row.dataset.sym);
        if (expRow) expRow.style.display = 'none';
        if (show) count++;
    });
    document.getElementById('matchCount').textContent = count;
}
window.addEventListener('load', function() {
    var momVal = localStorage.getItem('momFilter') || '';
    var emaVal = localStorage.getItem('emaFilter') || '';
    if (momVal || emaVal) {
        document.getElementById('momFilter').value = momVal;
        document.getElementById('emaFilter').value = emaVal;
        applyFilter();
    }
});
</script>
"""


def render_html_table(df, data_source: str = "", target_date: str = "",
                      prev_date: str = "", tick_count: int = 0) -> str:
    rows_html = ""

    for _, row in df.iterrows():
        symbol           = str(row["Symbol"])
        signal_time      = str(row.get("Signal Time", "-"))
        ltp              = float(row["LTP"])
        signal_price     = row.get("Signal Price", None)
        peak_ltp         = row.get("High Since Signal", None)
        ema_status       = row.get("EMA20 Status", None)
        momentum_str     = str(row.get("Momentum", ""))
        vol_ratio_raw    = float(str(row.get("Vol Ratio", "0")).replace("x", "") or 0)
        intraday_pct_raw = float(row.get("intraday_pct", 0) or 0)

        if signal_price and float(signal_price) > 0:
            move_since = ((ltp - float(signal_price)) / float(signal_price)) * 100
        else:
            move_since = 0.0

        if signal_price and peak_ltp and float(signal_price) > 0:
            peak_move     = ((float(peak_ltp) - float(signal_price)) / float(signal_price)) * 100
            peak_move_str = f"{peak_move:+.2f}%"
        else:
            peak_move_str = "-"

        signal_price_str = f"₹{float(signal_price):,.2f}" if signal_price else "-"
        peak_ltp_str     = f"₹{float(peak_ltp):,.2f}"    if peak_ltp     else "-"
        vol_fmt          = _short_vol(float(row['Volume']))
        median_vol_raw   = row.get("median_vol", None)
        median_vol_str   = _short_vol(float(median_vol_raw)) if median_vol_raw else "-"
        vr_color         = "#7c3aed" if vol_ratio_raw >= 5 else "#d97706" if vol_ratio_raw >= 3 else "#374151"

        if "STRONG BUILDING" in momentum_str:   mom_cls = "mom-strong"
        elif "BUILDING"      in momentum_str:   mom_cls = "mom-build"
        elif "STABLE"        in momentum_str:   mom_cls = "mom-stable"
        elif "COOLING"       in momentum_str:   mom_cls = "mom-cooling"
        elif "WEAK"          in momentum_str:   mom_cls = "mom-weak"
        else:                                   mom_cls = ""

        rows_html += f"""
        <tr class="main-row {mom_cls}" id="main-{symbol}"
            data-sym="{symbol}"
            data-mom="{momentum_str.lower()}"
            data-ema="{ema_status or ''}"
            onclick="toggleRow('{symbol}')">
            <td>
                <div class="stock-cell">
                    <div class="expand-icon">+</div>
                    <div>
                        <div class="stock-name">
                            <button class="copy-btn"
                                onclick="event.stopPropagation();copySymbol(this,'{symbol}')">{symbol}</button>
                        </div>
                        <div style="font-size:11px;color:#94a3b8;margin-top:3px;border-top:1px solid rgba(224,227,232,0.6);padding-top:3px">{signal_time[:5]}</div>
                    </div>
                </div>
            </td>
            <td>{_signal_price_html(signal_price_str, move_since)}</td>
            <td>
                <div class="ltp-val">₹{ltp:,.2f}</div>
                {_chg_html(float(str(row['Chg vs Prev %']).replace('%','').replace('+','')))}
            </td>
            <td><span class="num-primary">{_vol_emoji(str(row['Vol Momentum']))} {row['Vol Ratio']}</span></td>
            <td>{_mom_badge(momentum_str, vol_ratio_raw, intraday_pct_raw)}</td>
            <td>{_ema_cell(ema_status)}</td>
            <td>{_ema9_cell(str(row.get('EMA9 5min', '⏳')), row.get('EMA9 Value', None))}</td>
            <td>{_phase_cell(str(row.get('Phase', '⏳ Forming')))}</td>
            <td>{_vol_trend_cell(str(row.get('Vol Trend', '→ Stable')))}</td>
            <td><span class="num-primary">{vol_fmt}</span></td>
        </tr>
        <tr class="expand-row" id="exp-{symbol}" style="display:none">
            <td colspan="10">
                <div class="expand-panel">
                    <div class="expand-card"><div class="ec-label">Open</div><div class="ec-value">₹{float(row['Open']):,.2f}</div><div class="ec-sub">Today's open</div></div>
                    <div class="expand-card"><div class="ec-label">Prev Close</div><div class="ec-value">₹{float(row['Prev Close']):,.2f}</div><div class="ec-sub">Yesterday's close</div></div>
                    <div class="expand-card"><div class="ec-label">Signal Price</div><div class="ec-value" style="color:#2563eb">{signal_price_str}</div><div class="ec-sub">Entry trigger</div></div>
                    <div class="expand-card"><div class="ec-label">High Since Signal</div><div class="ec-value" style="color:#7c3aed">{peak_ltp_str}</div><div class="ec-sub">Peak after signal</div></div>
                    <div class="expand-card"><div class="ec-label">Peak Move%</div><div class="ec-value" style="color:#16a34a">{peak_move_str}</div><div class="ec-sub">Max gain possible</div></div>
                    <div class="expand-card"><div class="ec-label">Volume</div><div class="ec-value">{vol_fmt}</div><div class="ec-sub">Median: {median_vol_str}</div></div>
                    <div class="expand-card"><div class="ec-label">Vol Ratio</div><div class="ec-value" style="color:{vr_color}">{row['Vol Ratio']}</div><div class="ec-sub">vs 5-day median</div></div>
                    <div class="expand-card"><div class="ec-label">Signal Time</div><div class="ec-value">{signal_time}</div><div class="ec-sub">First detected</div></div>
                    <div class="expand-card"><div class="ec-label">EMA20 Status</div><div class="ec-value">{_ema_cell(ema_status)}</div><div class="ec-sub">Distance from EMA</div></div>
                </div>
            </td>
        </tr>"""

    total = len(df)
    meta  = ""
    if data_source or target_date:
        meta = f"{data_source} &nbsp;|&nbsp; 📅 {target_date} vs {prev_date} &nbsp;|&nbsp; Ticks: {tick_count}"

    html = _STYLES + f"""
    <div class="filterbar">
        <span class="filter-label">Momentum Scanner</span>
        <span class="filter-count"><b id="matchCount">{total}</b> stocks</span>
        <div class="filter-sep"></div>
        <select class="filter-select" id="momFilter" onchange="applyFilter()">
            <option value="">All Momentum</option>
            <option value="strong building">🚀 Strong Building</option>
            <option value="building">📈 Building</option>
            <option value="stable">➡️ Stable</option>
            <option value="cooling">⚠️ Cooling</option>
            <option value="weak">❌ Weak</option>
        </select>
        <select class="filter-select" id="emaFilter" onchange="applyFilter()">
            <option value="">All EMA</option>
            <option value="pass">✅ EMA Pass</option>
            <option value="fail">❌ EMA Fail / Below</option>
        </select>
        <span class="meta-info">{meta}</span>
    </div>
    <div class="table-wrap">
    <table>
        <thead>
            <tr>
                <th onclick="toggleColExpand(0)">Symbol <span class="sort-arrow">↕</span></th>
                <th class="th-sig" onclick="toggleColExpand(1)">Signal Price <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(2)">LTP <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(3)">Vol Ratio <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(4)">Momentum <span class="sort-arrow">↕</span></th>
                <th class="th-ema" onclick="toggleColExpand(5)">EMA20 Status <span class="sort-arrow">↕</span></th>
                <th class="th-ema9" onclick="toggleColExpand(6)">9 EMA 5min <span class="sort-arrow">↕</span></th>
                <th class="th-phase" onclick="toggleColExpand(7)">Phase <span class="sort-arrow">↕</span></th>
                <th class="th-trend" onclick="toggleColExpand(8)">Vol Trend <span class="sort-arrow">↕</span></th>
                <th onclick="toggleColExpand(9)">Volume <span class="sort-arrow">↕</span></th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    </div>
    """
    return html
