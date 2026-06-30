"""
momentum/renderer.py — Redesigned to match TradeSentry Image 1 style
Clean white, spacious rows, bold symbol, muted time below, clear hierarchy.
Volume column REMOVED — visible in expand dropdown instead.
"""

def _short_vol(vol: float) -> str:
    if vol >= 1_000_000:
        return f"{vol/1_000_000:.2f}M"
    if vol >= 1_000:
        return f"{vol/1_000:.1f}K"
    return str(int(vol))


def _ema_cell(status) -> str:
    if status is None or status == "⏳":
        return '<span style="color:#94a3b8;font-size:13px">⏳</span>'
    s = str(status)
    if s.startswith("✅"):
        return f'<span style="color:#16a34a;font-weight:600;font-size:13px">{s}</span>'
    if "Below" in s:
        return f'<span style="color:#dc2626;font-weight:600;font-size:13px">{s}</span>'
    if s.startswith("❌"):
        return f'<span style="color:#ea580c;font-weight:600;font-size:13px">{s}</span>'
    return f'<span style="color:#94a3b8;font-size:13px">{s}</span>'


def _ema9_cell(status: str, ema9_value) -> str:
    if not status or status == "⏳":
        return '<span style="color:#94a3b8;font-size:13px">⏳</span>'
    s = str(status)
    if s.startswith("✅"):   color = "#16a34a"
    elif s.startswith("⚠️"): color = "#d97706"
    elif s.startswith("❌"): color = "#dc2626"
    elif s.startswith("📉"): color = "#7c3aed"
    else:                    color = "#94a3b8"
    val_html = ""
    if ema9_value is not None:
        try:
            val_html = f'<div style="font-size:14px;font-weight:700;color:#1e3a5f">₹{float(ema9_value):,.2f}</div>'
        except Exception:
            pass
    pct_html = f'<div style="color:{color};font-weight:600;font-size:12px;margin-top:2px">{s}</div>'
    return f'{val_html}{pct_html}'


def _phase_cell(phase: str) -> str:
    if not phase or phase in ("⏳ Forming", "⏳"):
        return '<span style="color:#94a3b8;font-size:12px">⏳ Forming</span>'
    s = str(phase)
    # Extract just the keyword — PULLBACK / BUILDING / REVERSAL
    if   "BUILDING"  in s: keyword, color, bg, border, icon = "BUILDING",  "#15803d", "#f0fdf4", "#bbf7d0", "🚀"
    elif "PULLBACK"  in s: keyword, color, bg, border, icon = "PULLBACK",  "#b45309", "#fffbeb", "#fde68a", "⚠️"
    elif "REVERSAL"  in s: keyword, color, bg, border, icon = "REVERSAL",  "#be123c", "#fff1f2", "#fecdd3", "🔴"
    else:                  keyword, color, bg, border, icon = s,            "#64748b", "#f1f5f9", "#e2e8f0", ""
    return (
        f'<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;'
        f'border-radius:6px;font-size:12px;font-weight:700;white-space:nowrap;'
        f'background:{bg};color:{color};border:1px solid {border}">'
        f'{icon} {keyword}</span>'
    )


def _vol_trend_cell(vol_trend: str) -> str:
    if not vol_trend:
        return '<span style="color:#94a3b8;font-size:13px">→ Stable</span>'
    s = str(vol_trend)
    if s.startswith("↑"): return f'<span style="color:#16a34a;font-weight:600;font-size:13px">{s}</span>'
    if s.startswith("↓"): return f'<span style="color:#dc2626;font-weight:600;font-size:13px">{s}</span>'
    return f'<span style="color:#94a3b8;font-size:13px">{s}</span>'


def _move_color(val: float) -> str:
    if val >= 5.0: return "#16a34a"
    if val >= 2.0: return "#ca8a04"
    if val >= 0:   return "#64748b"
    return "#dc2626"


def _vol_emoji(vm: str) -> str:
    if "Very Strong" in vm or "🔥" in vm: return "🔥"
    if "Strong"      in vm or "⚡" in vm: return "⚡"
    if "Building"    in vm or "👀" in vm: return "👀"
    return ""


def _mom_badge(mom: str, vol_ratio: float = 0.0, intraday_pct: float = 0.0) -> str:
    def _clamp(v, lo, hi): return max(lo, min(hi, v))
    # Extract clean label — just the keyword(s) without leading emojis
    if   "STRONG BUILDING" in mom: clean_mom = "STRONG BUILDING"
    elif "BUILDING"        in mom: clean_mom = "BUILDING"
    elif "STABLE"          in mom: clean_mom = "STABLE"
    elif "COOLING"         in mom: clean_mom = "COOLING"
    elif "WEAK"            in mom: clean_mom = "WEAK"
    else:                          clean_mom = mom.strip()

    if "STRONG BUILDING" in mom:
        vol_p   = _clamp((vol_ratio    - 2.5) / (5.0 - 2.5), 0, 1)
        intra_p = _clamp((intraday_pct - 1.5) / (4.0 - 1.5), 0, 1)
        fill_pct   = int(66 + (vol_p * 0.4 + intra_p * 0.6) * 34)
        fill_color = "#7c3aed"
        badge_color, badge_bg, badge_border = "#7c3aed", "#faf5ff", "#ddd6fe"
        badge_icon = "🚀"
        next_label = "✅ Top Level"

    elif "BUILDING" in mom:
        vol_p   = _clamp((vol_ratio    - 2.0) / (2.5 - 2.0), 0, 1)
        intra_p = _clamp((intraday_pct - 0.8) / (1.5 - 0.8), 0, 1)
        fill_pct   = int(33 + (vol_p * 0.4 + intra_p * 0.6) * 33)
        fill_color = "#22c55e"
        badge_color, badge_bg, badge_border = "#15803d", "#f0fdf4", "#bbf7d0"
        badge_icon = "📈"
        v_need     = max(0.0, round(2.5 - vol_ratio, 1))
        i_need     = max(0.0, round(1.5 - intraday_pct, 1))
        next_label = f"→ Strong: need {v_need}x vol · {i_need}% move"

    elif "STABLE" in mom:
        vol_p   = _clamp((vol_ratio    - 1.5) / (2.0 - 1.5), 0, 1)
        intra_p = _clamp((intraday_pct - 0.0) / (0.8 - 0.0), 0, 1)
        fill_pct   = int(20 + (vol_p * 0.4 + intra_p * 0.6) * 13)
        fill_color = "#3b82f6"
        badge_color, badge_bg, badge_border = "#1d4ed8", "#eff6ff", "#bfdbfe"
        badge_icon = "➡️"
        v_need     = max(0.0, round(2.0 - vol_ratio, 1))
        i_need     = max(0.0, round(0.8 - intraday_pct, 1))
        next_label = f"→ Building: need {v_need}x vol · {i_need}% move"

    elif "COOLING" in mom:
        fill_pct, fill_color = 15, "#f59e0b"
        badge_color, badge_bg, badge_border = "#b45309", "#fffbeb", "#fde68a"
        badge_icon = "⚠️"
        next_label = "→ Building: price must turn +ve"

    elif "WEAK" in mom:
        fill_pct, fill_color = 8, "#ef4444"
        badge_color, badge_bg, badge_border = "#be123c", "#fff1f2", "#fecdd3"
        badge_icon = "❌"
        v_need = max(0.0, round(2.0 - vol_ratio, 1))
        next_label = f"→ Building: need {v_need}x more vol"
    else:
        return f'<span style="color:#64748b;font-size:13px">{clean_mom}</span>'

    return (
        f'<div style="display:flex;flex-direction:column;gap:5px;min-width:180px">'
        f'  <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">'
        f'    <span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;'
        f'           border-radius:6px;font-size:13px;font-weight:700;'
        f'           background:{badge_bg};color:{badge_color};border:1px solid {badge_border}">'
        f'      {badge_icon} {clean_mom}</span>'
        f'    <span style="font-size:12px;font-weight:700;color:{fill_color}">{fill_pct}%</span>'
        f'  </div>'
        f'  <div style="width:100%;height:4px;background:#e2e8f0;border-radius:4px;overflow:hidden">'
        f'    <div style="height:100%;width:{fill_pct}%;background:{fill_color};border-radius:4px;transition:width 0.4s"></div>'
        f'  </div>'
        f'  <div style="font-size:11px;color:#94a3b8">{next_label}</div>'
        f'</div>'
    )


def _chg_html(val: float) -> str:
    color = "#16a34a" if val >= 0 else "#dc2626"
    sign  = "▲" if val >= 0 else "▼"
    return f'<span style="color:{color};font-weight:600;font-size:12px">{sign} {abs(val):.2f}%</span>'


def _signal_price_html(signal_price_str: str, move_since: float) -> str:
    if signal_price_str == "-":
        return '<span style="color:#94a3b8;font-size:13px">—</span>'
    positive = move_since >= 0
    w        = min(abs(move_since) * 10, 100)
    fill     = "#22c55e" if positive else "#ef4444"
    color    = _move_color(move_since)
    sign     = "+" if positive else ""
    return (
        f'<div style="display:flex;flex-direction:column;gap:4px;min-width:110px">'
        f'  <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">'
        f'    <span style="font-size:14px;font-weight:700;color:#1e3a5f">{signal_price_str}</span>'
        f'    <span style="font-size:12px;font-weight:700;color:{color}">{sign}{move_since:.2f}%</span>'
        f'  </div>'
        f'  <div style="width:100%;height:3px;background:#e2e8f0;border-radius:3px;overflow:hidden">'
        f'    <div style="height:100%;width:{w:.0f}%;background:{fill};border-radius:3px"></div>'
        f'  </div>'
        f'</div>'
    )


_STYLES = """
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: #f8faff !important;
  font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
  color: #1a202c; font-size: 14px;
}

/* ── HEADER BAR ── */
.ts-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px 12px;
  background: #fff;
  border-bottom: 1px solid #f0f2f5;
}
.ts-brand {
  font-size: 20px; font-weight: 800; letter-spacing: -0.5px;
  color: #0f172a;
}
.ts-brand span { color: #00a854; }
.ts-status {
  display: flex; align-items: center; gap: 16px;
  font-size: 13px; color: #64748b;
}
.ts-live {
  display: flex; align-items: center; gap: 6px;
  background: #f0fdf4; color: #16a34a;
  border: 1px solid #bbf7d0;
  padding: 4px 10px; border-radius: 20px;
  font-size: 12px; font-weight: 600;
}
.ts-live-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #16a34a;
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.4; transform: scale(0.8); }
}

/* ── STATUS BANNER ── */
.ts-banner {
  background: #f0fdf4;
  border-bottom: 1px solid #d1fae5;
  padding: 10px 20px;
  display: flex; align-items: center; justify-content: space-between;
  font-size: 13px; color: #166534;
}
.ts-banner b { font-weight: 700; color: #15803d; }

/* ── FILTER BAR ── */
.ts-filters {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 20px;
  background: #fff;
  border-bottom: 1px solid #f0f2f5;
  flex-wrap: wrap;
}
.ts-filter-label {
  font-size: 13px; font-weight: 700; color: #0f172a;
}
.ts-count {
  background: #16a34a; color: #fff;
  font-size: 11px; font-weight: 700;
  padding: 2px 8px; border-radius: 10px;
  min-width: 24px; text-align: center;
}
.ts-sep { width: 1px; height: 18px; background: #e2e8f0; }
select.ts-select {
  height: 32px;
  padding: 0 28px 0 10px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  font-size: 13px; color: #374151;
  background: #fff;
  cursor: pointer; outline: none; appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center;
  transition: border-color 0.15s;
}
select.ts-select:focus { border-color: #00a854; }
.ts-meta { margin-left: auto; font-size: 12px; color: #94a3b8; }

/* ── TABLE WRAP ── */
.ts-table-wrap { overflow-x: auto; }
table {
  width: 100%; border-collapse: collapse;
  background: #fff;
}

/* ── HEADER ROW ── */
thead tr { border-bottom: 2px solid #f0f2f5; }
th {
  padding: 10px 16px;
  text-align: left;
  font-size: 11px; font-weight: 700;
  color: #0f172a;
  letter-spacing: 0.6px; text-transform: uppercase;
  white-space: nowrap;
  user-select: none; cursor: pointer;
  border-right: 1px solid #f8faff;
}
th:last-child { border-right: none; }
th:hover { color: #374151; }
th.sorted { color: #00a854; cursor: pointer; }
td.active-col { background: #f0fdf4 !important; }
.sort-arrow { margin-left: 3px; font-size: 10px; opacity: 0.5; }
th.sorted .sort-arrow { opacity: 1; }

/* ── BODY ROWS ── */
tbody tr.ts-row {
  border-bottom: 1px solid #f5f7fa;
  cursor: pointer;
  transition: background 0.12s;
  border-left: 3px solid transparent;
}
tbody tr.ts-row:hover { background: #fafbfe; }
tbody tr.ts-row.expanded { background: #f0fdf4; border-left-color: #00a854; }

/* Left accent by momentum type */
tbody tr.ts-row.mom-strong  { border-left-color: #7c3aed; }
tbody tr.ts-row.mom-build   { border-left-color: #22c55e; }
tbody tr.ts-row.mom-stable  { border-left-color: #3b82f6; }
tbody tr.ts-row.mom-cooling { border-left-color: #f59e0b; }
tbody tr.ts-row.mom-weak    { border-left-color: #ef4444; }

td {
  padding: 14px 16px;
  vertical-align: middle;
  font-size: 14px; color: #374151;
  border-right: 1px solid #f8faff;
  white-space: nowrap;
}
td:last-child { border-right: none; }

/* ── SYMBOL CELL ── */
.ts-symbol-cell { display: flex; align-items: center; gap: 10px; }
.ts-expand-btn {
  width: 20px; height: 20px; border-radius: 4px;
  background: #f1f5f9; color: #64748b;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; flex-shrink: 0;
  transition: all 0.15s;
  border: 1px solid #e2e8f0;
}
tr.expanded .ts-expand-btn { background: #00a854; color: #fff; border-color: #00a854; }
.ts-sym-name {
  font-size: 15px; font-weight: 800;
  color: #0f172a; letter-spacing: 0.2px;
}
.ts-sym-time {
  font-size: 13px; color: #374151;
  margin-top: 3px; font-weight: 700;
}
.ts-copy-btn {
  background: none; border: none; padding: 0; cursor: pointer;
  color: inherit; font-weight: inherit; font-size: inherit;
  font-family: inherit;
}
.ts-copy-btn:hover .ts-sym-name { color: #00a854; }

/* ── LTP CELL ── */
.ts-ltp-val {
  font-size: 15px; font-weight: 700; color: #0f172a;
}

/* ── VOL RATIO ── */
.ts-vol-ratio {
  font-size: 14px; font-weight: 700;
  display: inline-flex; align-items: center; gap: 4px;
}
.ts-vol-ratio.vr-high   { color: #7c3aed; }
.ts-vol-ratio.vr-med    { color: #d97706; }
.ts-vol-ratio.vr-normal { color: #374151; }

/* ── EXPAND ROW ── */
tr.ts-expand-row td {
  padding: 0;
  border-bottom: 2px solid #00a854;
}
.ts-expand-panel {
  background: #f8fffe;
  padding: 14px 20px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 10px;
}
.ts-ec {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px; padding: 10px 12px;
}
.ts-ec-label {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.5px; color: #94a3b8;
}
.ts-ec-value {
  font-size: 14px; font-weight: 700; color: #0f172a; margin-top: 4px;
}
.ts-ec-sub { font-size: 11px; color: #94a3b8; margin-top: 2px; }

/* ── TOAST ── */
.ts-toast {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%);
  background: #0f172a; color: #fff;
  padding: 8px 18px; border-radius: 8px;
  font-size: 13px; font-weight: 600;
  z-index: 9999; opacity: 0; pointer-events: none;
  transition: opacity 0.2s;
}
.ts-toast.show { opacity: 1; }

/* ── SCROLLBAR ── */
::-webkit-scrollbar { height: 5px; width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #00a854; }
</style>

<div id="ts-toast" class="ts-toast">✅ Copied!</div>
<script>
function tsToast(msg) {
  var t = document.getElementById('ts-toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(function() { t.classList.remove('show'); }, 1500);
}
function tsCopy(e, btn, sym) {
  e.stopPropagation();
  function showCopied() {
    var nameEl = btn.querySelector('.ts-sym-name');
    if (!nameEl) return;
    var original = nameEl.textContent;
    nameEl.textContent = '✓ ' + sym;
    nameEl.style.color = '#00a854';
    tsToast('✅ ' + sym + ' copied!');
    setTimeout(function() {
      nameEl.textContent = original;
      nameEl.style.color = '';
    }, 1500);
  }
  navigator.clipboard.writeText(sym).then(showCopied).catch(function() {
    // Fallback for browsers/contexts where clipboard API is blocked
    var ta = document.createElement('textarea');
    ta.value = sym;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); showCopied(); }
    catch (err) { tsToast('❌ Copy failed'); }
    document.body.removeChild(ta);
  });
}
function tsToggle(sym) {
  var main = document.getElementById('tsm-' + sym);
  var exp  = document.getElementById('tse-' + sym);
  if (!exp) return;
  var open = exp.style.display !== 'none';
  exp.style.display = open ? 'none' : 'table-row';
  main.classList.toggle('expanded', !open);
  var btn = main.querySelector('.ts-expand-btn');
  if (btn) btn.textContent = open ? '+' : '−';
}
var tsActiveCol = -1;
function tsColHighlight(col) {
  document.querySelectorAll('th').forEach(function(th) { th.classList.remove('sorted'); });
  document.querySelectorAll('td.active-col').forEach(function(td) { td.classList.remove('active-col'); });
  if (tsActiveCol === col) { tsActiveCol = -1; return; }
  tsActiveCol = col;
  var headers = document.querySelectorAll('th');
  if (headers[col]) headers[col].classList.add('sorted');
  document.querySelectorAll('tbody tr.ts-row').forEach(function(row) {
    var cells = row.querySelectorAll('td');
    if (cells[col]) cells[col].classList.add('active-col');
  });
}
function tsFilter() {
  var mom = document.getElementById('tsf-mom').value.toLowerCase();
  var ema = document.getElementById('tsf-ema').value;
  // Persist filter choices so the 5-sec fragment refresh doesn't reset them
  try {
    localStorage.setItem('ts_filter_mom', mom);
    localStorage.setItem('ts_filter_ema', ema);
  } catch (e) {}
  var rows = document.querySelectorAll('tbody tr.ts-row');
  var count = 0;
  rows.forEach(function(row) {
    var rmom = (row.dataset.mom || '').toLowerCase();
    var rema = (row.dataset.ema || '');
    var show = true;
    if (mom && !rmom.includes(mom)) show = false;
    if (ema === 'pass' && !rema.includes('✅')) show = false;
    if (ema === 'fail' && !rema.includes('❌')) show = false;
    row.style.display = show ? '' : 'none';
    var exp = document.getElementById('tse-' + row.dataset.sym);
    if (exp) exp.style.display = 'none';
    if (show) count++;
  });
  document.getElementById('ts-match-count').textContent = count;
  tsAutoResize();
}

// ── Restore filters + scroll position after every refresh ──
function tsRestoreState() {
  try {
    var savedMom = localStorage.getItem('ts_filter_mom') || '';
    var savedEma = localStorage.getItem('ts_filter_ema') || '';
    if (savedMom || savedEma) {
      var momEl = document.getElementById('tsf-mom');
      var emaEl = document.getElementById('tsf-ema');
      if (momEl) momEl.value = savedMom;
      if (emaEl) emaEl.value = savedEma;
      tsFilter();
    }
  } catch (e) {}
  try {
    var savedScroll = sessionStorage.getItem('ts_scroll_y');
    if (savedScroll !== null) {
      window.scrollTo(0, parseInt(savedScroll, 10));
      if (window.parent) {
        window.parent.scrollTo(0, parseInt(savedScroll, 10));
      }
    }
  } catch (e) {}
}

// Save scroll position continuously (both iframe and parent page)
function tsSaveScroll() {
  try {
    sessionStorage.setItem('ts_scroll_y', window.scrollY || window.pageYOffset || 0);
  } catch (e) {}
}
window.addEventListener('scroll', tsSaveScroll);
try {
  if (window.parent) {
    window.parent.addEventListener('scroll', tsSaveScroll);
  }
} catch (e) {}

window.addEventListener('load', tsRestoreState);
setTimeout(tsRestoreState, 200);

// ── Auto-resize: tell parent iframe the real content height ──
function tsAutoResize() {
  var height = document.documentElement.scrollHeight;
  if (window.frameElement) {
    window.frameElement.style.height = height + 'px';
  }
  // Streamlit's own resize bridge (works inside components.v1.html)
  try {
    window.parent.postMessage({
      type: 'streamlit:setFrameHeight',
      height: height
    }, '*');
  } catch (e) {}
}
window.addEventListener('load', tsAutoResize);
window.addEventListener('resize', tsAutoResize);
// Re-measure shortly after load (fonts/icons can shift layout)
setTimeout(tsAutoResize, 150);
setTimeout(tsAutoResize, 500);
// Watch for DOM changes (row expand/collapse, filter, live updates)
new MutationObserver(tsAutoResize).observe(document.body, {
  childList: true, subtree: true, attributes: true
});

// ── Screenshot shortcut: Ctrl + Shift + S ──
document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.shiftKey && (e.key === 'S' || e.key === 's')) {
        e.preventDefault();
        takeScreenshot();
    }
});

async function takeScreenshot() {
    var toast = document.getElementById('ts-toast');
    toast.innerHTML = '📸 Capturing...';
    toast.classList.add('show');
    try {
        var blobPromise = new Promise(function(resolve) {
            html2canvas(document.body, {
                scale: 2,
                useCORS: true,
                backgroundColor: '#f8faff',
                scrollY: 0,
                windowHeight: document.body.scrollHeight,
                height: document.body.scrollHeight,
            }).then(function(canvas) {
                canvas.toBlob(function(blob) { resolve(blob); }, 'image/png');
            });
        });
        await navigator.clipboard.write([
            new ClipboardItem({ 'image/png': blobPromise })
        ]);
        toast.innerHTML = '✅ Screenshot copied!';
        setTimeout(function() {
            toast.classList.remove('show');
            toast.innerHTML = '✅ Copied!';
        }, 2000);
    } catch(e) {
        toast.innerHTML = '❌ ' + (e.message || 'Failed');
        setTimeout(function() {
            toast.classList.remove('show');
            toast.innerHTML = '✅ Copied!';
        }, 2500);
    }
}
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
"""


def render_html_table(df, data_source: str = "", target_date: str = "",
                      prev_date: str = "", tick_count: int = 0) -> str:

    rows_html = ""
    total     = len(df)

    for _, row in df.iterrows():
        symbol        = str(row["Symbol"])
        signal_time   = str(row.get("Signal Time", "-"))
        ltp           = float(row["LTP"])
        signal_price  = row.get("Signal Price", None)
        peak_ltp      = row.get("High Since Signal", None)
        ema_status    = row.get("EMA20 Status", None)
        momentum_str  = str(row.get("Momentum", ""))
        vol_ratio_raw = float(str(row.get("Vol Ratio", "0")).replace("x", "") or 0)
        intraday_pct  = float(row.get("intraday_pct", 0) or 0)

        move_since = 0.0
        if signal_price and float(signal_price) > 0:
            move_since = ((ltp - float(signal_price)) / float(signal_price)) * 100

        peak_move_str = "-"
        if peak_ltp and signal_price and float(signal_price) > 0:
            pm = ((float(peak_ltp) - float(signal_price)) / float(signal_price)) * 100
            peak_move_str = f"{pm:+.2f}%"

        signal_price_str = f"₹{float(signal_price):,.2f}" if signal_price else "-"
        peak_ltp_str     = f"₹{float(peak_ltp):,.2f}"    if peak_ltp     else "-"
        vol_fmt          = _short_vol(float(row['Volume']))
        median_vol_raw   = row.get("median_vol", None)
        median_vol_str   = _short_vol(float(median_vol_raw)) if median_vol_raw else "-"

        # Vol ratio color
        vr_class = "vr-high" if vol_ratio_raw >= 5 else "vr-med" if vol_ratio_raw >= 3 else "vr-normal"
        vr_color  = "#7c3aed" if vol_ratio_raw >= 5 else "#d97706" if vol_ratio_raw >= 3 else "#374151"

        # Row momentum class
        if   "STRONG BUILDING" in momentum_str: mom_cls = "mom-strong"
        elif "BUILDING"        in momentum_str: mom_cls = "mom-build"
        elif "STABLE"          in momentum_str: mom_cls = "mom-stable"
        elif "COOLING"         in momentum_str: mom_cls = "mom-cooling"
        elif "WEAK"            in momentum_str: mom_cls = "mom-weak"
        else:                                   mom_cls = ""

        vol_emoji = _vol_emoji(str(row['Vol Momentum']))

        prev_close_val = float(row.get('Prev Close', 0))
        open_val       = float(row.get('Open', 0))

        chg_vs_prev = float(
            str(row.get('Chg vs Prev %', '0'))
            .replace('%', '').replace('+', '') or 0
        )

        rows_html += f"""
        <tr class="ts-row {mom_cls}" id="tsm-{symbol}"
            data-sym="{symbol}"
            data-mom="{momentum_str.lower()}"
            data-ema="{ema_status or ''}"
            onclick="tsToggle('{symbol}')">

          <td>
            <div class="ts-symbol-cell">
              <div class="ts-expand-btn">+</div>
              <button class="ts-copy-btn"
                onclick="tsCopy(event, this, '{symbol}')">
                <div class="ts-sym-name">{symbol}</div>
                <div class="ts-sym-time">{signal_time[:5]}</div>
              </button>
            </div>
          </td>

          <td>{_signal_price_html(signal_price_str, move_since)}</td>

          <td>
            <div class="ts-ltp-val">₹{ltp:,.2f}</div>
            {_chg_html(chg_vs_prev)}
          </td>

          <td>
            <span class="ts-vol-ratio {vr_class}">
              {vol_emoji} {row['Vol Ratio']}
            </span>
          </td>

          <td>{_mom_badge(momentum_str, vol_ratio_raw, intraday_pct)}</td>

          <td>{_ema_cell(ema_status)}</td>

        </tr>
        <tr class="ts-expand-row" id="tse-{symbol}" style="display:none">
          <td colspan="6">
            <div class="ts-expand-panel">
              <div class="ts-ec">
                <div class="ts-ec-label">Open</div>
                <div class="ts-ec-value">₹{open_val:,.2f}</div>
                <div class="ts-ec-sub">Today's open</div>
              </div>
              <div class="ts-ec">
                <div class="ts-ec-label">Prev Close</div>
                <div class="ts-ec-value">₹{prev_close_val:,.2f}</div>
                <div class="ts-ec-sub">Yesterday's close</div>
              </div>
              <div class="ts-ec">
                <div class="ts-ec-label">Peak Since Signal</div>
                <div class="ts-ec-value" style="color:#7c3aed">{peak_ltp_str}</div>
                <div class="ts-ec-sub">Max LTP after entry</div>
              </div>
              <div class="ts-ec">
                <div class="ts-ec-label">Peak Move</div>
                <div class="ts-ec-value" style="color:#16a34a">{peak_move_str}</div>
                <div class="ts-ec-sub">Max gain possible</div>
              </div>
              <div class="ts-ec">
                <div class="ts-ec-label">Volume</div>
                <div class="ts-ec-value">{vol_fmt}</div>
                <div class="ts-ec-sub">Median: {median_vol_str}</div>
              </div>
            </div>
          </td>
        </tr>"""

    meta = ""
    if data_source or target_date:
        meta = f"📅 {target_date} vs {prev_date} &nbsp;|&nbsp; Ticks: {tick_count}"

    html = _STYLES + f"""
<div class="ts-header">
  <div class="ts-brand">TRADE<span>SENTRY</span></div>
  <div class="ts-status">
    <div class="ts-live">
      <div class="ts-live-dot"></div>
      Live WebSocket
    </div>
    <span style="font-size:12px;color:#94a3b8">{meta}</span>
  </div>
</div>

<div class="ts-banner">
  <span><b id="ts-match-count">{total}</b> stocks matching momentum criteria</span>
</div>

<div class="ts-filters">
  <span class="ts-filter-label">Momentum Scanner</span>
  <span class="ts-count">{total}</span>
  <div class="ts-sep"></div>
  <select class="ts-select" id="tsf-mom" onchange="tsFilter()">
    <option value="">All Momentum</option>
    <option value="strong building">🚀 Strong Building</option>
    <option value="building">📈 Building</option>
    <option value="stable">➡️ Stable</option>
    <option value="cooling">⚠️ Cooling</option>
    <option value="weak">❌ Weak</option>
  </select>
  <select class="ts-select" id="tsf-ema" onchange="tsFilter()">
    <option value="">All EMA</option>
    <option value="pass">✅ EMA Pass</option>
    <option value="fail">❌ EMA Fail</option>
  </select>
</div>

<div class="ts-table-wrap">
<table>
  <thead>
    <tr>
      <th onclick="tsColHighlight(0)">Symbol</th>
      <th onclick="tsColHighlight(1)">Signal Price</th>
      <th onclick="tsColHighlight(2)">LTP</th>
      <th onclick="tsColHighlight(3)">Vol Ratio</th>
      <th onclick="tsColHighlight(4)">Momentum</th>
      <th onclick="tsColHighlight(5)">EMA20 Status</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>
</div>
"""
    return html
