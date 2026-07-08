"""
momentum/renderer.py — Compressed version. Same logic/output as original, fewer lines.
Clean white TradeSentry style. Volume column in expand dropdown.
BUY button added as first column — postMessage to Streamlit parent.
"""

_GREY = '<span style="color:#94a3b8;font-size:13px">{}</span>'


def _short_vol(vol: float) -> str:
    if vol >= 1_000_000: return f"{vol/1_000_000:.2f}M"
    if vol >= 1_000:     return f"{vol/1_000:.1f}K"
    return str(int(vol))


def _ema_cell(status) -> str:
    if status is None or status == "⏳": return _GREY.format("⏳")
    s = str(status)
    color = ("#16a34a" if s.startswith("✅") else "#dc2626" if "Below" in s
             else "#ea580c" if s.startswith("❌") else None)
    if color: return f'<span style="color:{color};font-weight:600;font-size:13px">{s}</span>'
    return _GREY.format(s)


def _ema9_cell(status: str, ema9_value) -> str:
    if not status or status == "⏳": return _GREY.format("⏳")
    s = str(status)
    color = {"✅": "#16a34a", "⚠": "#d97706", "❌": "#dc2626", "📉": "#7c3aed"}.get(s[:1], "#94a3b8")
    if s.startswith("⚠️"): color = "#d97706"
    val_html = ""
    if ema9_value is not None:
        try: val_html = f'<div style="font-size:14px;font-weight:700;color:#1e3a5f">₹{float(ema9_value):,.2f}</div>'
        except Exception: pass
    return f'{val_html}<div style="color:{color};font-weight:600;font-size:12px;margin-top:2px">{s}</div>'


_PHASES = {
    "BUILDING": ("#15803d", "#f0fdf4", "#bbf7d0", "🚀"),
    "PULLBACK": ("#b45309", "#fffbeb", "#fde68a", "⚠️"),
    "REVERSAL": ("#be123c", "#fff1f2", "#fecdd3", "🔴"),
}

def _phase_cell(phase: str) -> str:
    if not phase or phase in ("⏳ Forming", "⏳"):
        return '<span style="color:#94a3b8;font-size:12px">⏳ Forming</span>'
    s = str(phase)
    for kw, (color, bg, border, icon) in _PHASES.items():
        if kw in s:
            keyword = kw; break
    else:
        keyword, (color, bg, border, icon) = s, ("#64748b", "#f1f5f9", "#e2e8f0", "")
    return (f'<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;'
            f'border-radius:6px;font-size:12px;font-weight:700;white-space:nowrap;'
            f'background:{bg};color:{color};border:1px solid {border}">{icon} {keyword}</span>')


def _vol_trend_cell(vol_trend: str) -> str:
    if not vol_trend: return _GREY.format("→ Stable")
    s = str(vol_trend)
    if s[:1] in ("↑", "↓"):
        color = "#16a34a" if s.startswith("↑") else "#dc2626"
        return f'<span style="color:{color};font-weight:600;font-size:13px">{s}</span>'
    return _GREY.format(s)


def _move_color(val: float) -> str:
    if val >= 5.0: return "#16a34a"
    if val >= 2.0: return "#ca8a04"
    if val >= 0:   return "#64748b"
    return "#dc2626"


def _vol_emoji(vm: str) -> str:
    for kw, e in (("Explosive", "🔥"), ("🔥", "🔥"), ("Strong", "🟢"), ("🟢", "🟢"),
                  ("Build", "🟡"), ("🟡", "🟡"), ("Emerging", "🔵"), ("🔵", "🔵")):
        if kw in vm: return e
    return ""


def _delivery_cell(delivery_pct) -> str:
    if delivery_pct is None or delivery_pct == "" or str(delivery_pct).upper() == "NA":
        return _GREY.format("—")
    try: val = float(delivery_pct)
    except (ValueError, TypeError): return _GREY.format("—")
    color = "#16a34a" if val >= 60 else "#d97706" if val >= 40 else "#94a3b8"
    return f'<span style="color:{color};font-weight:700;font-size:14px">{val:.1f}%</span>'


def _mom_badge(mom: str, vol_ratio: float = 0.0, intraday_pct: float = 0.0) -> str:
    c = lambda v: max(0.0, min(1.0, v))
    clean = next((k for k in ("STRONG BUILDING", "BUILDING", "STABLE", "COOLING", "WEAK") if k in mom), mom.strip())

    if clean == "STRONG BUILDING":
        fp = int(66 + (c((vol_ratio - 2.5) / 2.5) * 0.4 + c((intraday_pct - 1.5) / 2.5) * 0.6) * 34)
        fill, bc, bg, bd, icon = "#7c3aed", "#7c3aed", "#faf5ff", "#ddd6fe", "🚀"
        nxt = "✅ Top Level"
    elif clean == "BUILDING":
        fp = int(33 + (c((vol_ratio - 2.0) / 0.5) * 0.4 + c((intraday_pct - 0.8) / 0.7) * 0.6) * 33)
        fill, bc, bg, bd, icon = "#22c55e", "#15803d", "#f0fdf4", "#bbf7d0", "📈"
        nxt = f"→ Strong: need {max(0.0, round(2.5 - vol_ratio, 1))}x vol · {max(0.0, round(1.5 - intraday_pct, 1))}% move"
    elif clean == "STABLE":
        fp = int(20 + (c((vol_ratio - 1.5) / 0.5) * 0.4 + c(intraday_pct / 0.8) * 0.6) * 13)
        fill, bc, bg, bd, icon = "#3b82f6", "#1d4ed8", "#eff6ff", "#bfdbfe", "➡️"
        nxt = f"→ Building: need {max(0.0, round(2.0 - vol_ratio, 1))}x vol · {max(0.0, round(0.8 - intraday_pct, 1))}% move"
    elif clean == "COOLING":
        fp, fill, bc, bg, bd, icon = 15, "#f59e0b", "#b45309", "#fffbeb", "#fde68a", "⚠️"
        nxt = "→ Building: price must turn +ve"
    elif clean == "WEAK":
        fp, fill, bc, bg, bd, icon = 8, "#ef4444", "#be123c", "#fff1f2", "#fecdd3", "❌"
        nxt = f"→ Building: need {max(0.0, round(2.0 - vol_ratio, 1))}x more vol"
    else:
        return f'<span style="color:#64748b;font-size:13px">{clean}</span>'

    return (
        f'<div style="display:flex;flex-direction:column;gap:5px;min-width:180px">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:8px">'
        f'<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:6px;'
        f'font-size:13px;font-weight:700;background:{bg};color:{bc};border:1px solid {bd}">{icon} {clean}</span>'
        f'<span style="font-size:12px;font-weight:700;color:{fill}">{fp}%</span></div>'
        f'<div style="width:100%;height:4px;background:#e2e8f0;border-radius:4px;overflow:hidden">'
        f'<div style="height:100%;width:{fp}%;background:{fill};border-radius:4px;transition:width 0.4s"></div></div>'
        f'<div style="font-size:11px;color:#94a3b8">{nxt}</div></div>'
    )


def _prev_day_move_html(val_str: str) -> str:
    if not val_str or val_str == "-": return _GREY.format("—")
    try: val = float(val_str.replace("%", "").replace("+", ""))
    except (ValueError, AttributeError): return _GREY.format("—")
    sign = "+" if val >= 0 else ""
    return f'<span style="color:{_move_color(val)};font-weight:600;font-size:13px">{sign}{val:.2f}%</span>'


def _chg_html(val: float) -> str:
    color, sign = ("#16a34a", "▲") if val >= 0 else ("#dc2626", "▼")
    return f'<span style="color:{color};font-weight:600;font-size:12px">{sign} {abs(val):.2f}%</span>'


def _signal_price_html(signal_price_str: str, move_since: float) -> str:
    if signal_price_str == "-": return _GREY.format("—")
    positive = move_since >= 0
    w    = min(abs(move_since) * 10, 100)
    fill = "#22c55e" if positive else "#ef4444"
    sign = "+" if positive else ""
    return (
        f'<div style="display:flex;flex-direction:column;gap:4px;min-width:110px">'
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:8px">'
        f'<span style="font-size:14px;font-weight:700;color:#1e3a5f">{signal_price_str}</span>'
        f'<span style="font-size:12px;font-weight:700;color:{_move_color(move_since)}">{sign}{move_since:.2f}%</span></div>'
        f'<div style="width:100%;height:3px;background:#e2e8f0;border-radius:3px;overflow:hidden">'
        f'<div style="height:100%;width:{w:.0f}%;background:{fill};border-radius:3px"></div></div></div>'
    )


def _buy_btn_cell(symbol: str, qty: int, ltp: float, already_bought: bool) -> str:
    """BUY button cell — postMessage to Streamlit parent on click."""
    if already_bought:
        return (
            '<div style="display:flex;align-items:center;justify-content:center;">'
            '<span style="background:#f0fdf4;color:#16a34a;border:1px solid #bbf7d0;'
            'padding:5px 10px;border-radius:6px;font-size:11px;font-weight:700;white-space:nowrap;">'
            '✅ Bought</span></div>'
        )
    est = int(qty * ltp)
    return (
        f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">'
        f'<button onclick="tsBuy(event,\'{symbol}\',{qty},{ltp})" '
        f'style="background:#16a34a;color:#fff;border:none;border-radius:6px;'
        f'padding:6px 12px;font-size:12px;font-weight:700;cursor:pointer;'
        f'white-space:nowrap;transition:background 0.15s;width:100%;" '
        f'onmouseover="this.style.background=\'#15803d\'" '
        f'onmouseout="this.style.background=\'#16a34a\'">'
        f'BUY x{qty}</button>'
        f'<span style="font-size:10px;color:#94a3b8;">≈ ₹{est:,}</span>'
        f'</div>'
    )


_STYLES = """
<style>
*, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }
html, body { background:#f8faff !important; font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',sans-serif; color:#1a202c; font-size:14px; }
.ts-header { display:flex; align-items:center; justify-content:space-between; padding:14px 20px 12px; background:#fff; border-bottom:1px solid #f0f2f5; }
.ts-brand { font-size:20px; font-weight:800; letter-spacing:-0.5px; color:#0f172a; }
.ts-brand span { color:#00a854; }
.ts-status { display:flex; align-items:center; gap:16px; font-size:13px; color:#64748b; }
.ts-live { display:flex; align-items:center; gap:6px; background:#f0fdf4; color:#16a34a; border:1px solid #bbf7d0; padding:4px 10px; border-radius:20px; font-size:12px; font-weight:600; }
.ts-live-dot { width:7px; height:7px; border-radius:50%; background:#16a34a; animation:pulse 1.8s ease-in-out infinite; }
@keyframes pulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:0.4; transform:scale(0.8); } }
.ts-banner { background:#f0fdf4; border-bottom:1px solid #d1fae5; padding:10px 20px; display:flex; align-items:center; justify-content:space-between; font-size:13px; color:#166534; }
.ts-banner b { font-weight:700; color:#15803d; }
.ts-filters { display:flex; align-items:center; gap:10px; padding:10px 20px; background:#fff; border-bottom:1px solid #f0f2f5; flex-wrap:wrap; }
.ts-filter-label { font-size:13px; font-weight:700; color:#0f172a; }
.ts-count { background:#16a34a; color:#fff; font-size:11px; font-weight:700; padding:2px 8px; border-radius:10px; min-width:24px; text-align:center; }
.ts-sep { width:1px; height:18px; background:#e2e8f0; }
.ts-toggle-switch { position:relative; display:inline-block; width:34px; height:18px; }
.ts-toggle-switch input { opacity:0; width:0; height:0; }
.ts-toggle-slider { position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background:#e2e8f0; border-radius:18px; transition:0.2s; }
.ts-toggle-slider::before { content:""; position:absolute; height:14px; width:14px; left:2px; bottom:2px; background:#fff; border-radius:50%; transition:0.2s; box-shadow:0 1px 2px rgba(0,0,0,0.15); }
.ts-toggle-switch input:checked + .ts-toggle-slider { background:#00a854; }
.ts-toggle-switch input:checked + .ts-toggle-slider::before { transform:translateX(16px); }
select.ts-select { height:32px; padding:0 28px 0 10px; border:1px solid #e2e8f0; border-radius:6px; font-size:13px; color:#374151; background:#fff; cursor:pointer; outline:none; appearance:none; background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E"); background-repeat:no-repeat; background-position:right 8px center; transition:border-color 0.15s; }
select.ts-select:focus { border-color:#00a854; }
.ts-meta { margin-left:auto; font-size:12px; color:#94a3b8; }
.ts-table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; background:#fff; }
thead tr { border-bottom:2px solid #f0f2f5; }
th { padding:10px 16px; text-align:left; font-size:11px; font-weight:700; color:#0f172a; letter-spacing:0.6px; text-transform:uppercase; white-space:nowrap; user-select:none; cursor:pointer; border-right:1px solid #f8faff; }
th:last-child { border-right:none; }
th:hover { color:#374151; }
th.sorted { color:#00a854; cursor:pointer; }
td.active-col { background:#f0fdf4 !important; }
.sort-arrow { margin-left:3px; font-size:10px; opacity:0.5; }
th.sorted .sort-arrow { opacity:1; }
tbody tr.ts-row { border-bottom:1px solid #f5f7fa; cursor:pointer; transition:background 0.12s; border-left:3px solid transparent; }
tbody tr.ts-row:hover { background:#fafbfe; }
tbody tr.ts-row.expanded { background:#f0fdf4; border-left-color:#00a854; }
tbody tr.ts-row.mom-strong  { border-left-color:#7c3aed; }
tbody tr.ts-row.mom-build   { border-left-color:#22c55e; }
tbody tr.ts-row.mom-stable  { border-left-color:#3b82f6; }
tbody tr.ts-row.mom-cooling { border-left-color:#f59e0b; }
tbody tr.ts-row.mom-weak    { border-left-color:#ef4444; }
td { padding:10px 16px; vertical-align:middle; font-size:14px; color:#374151; border-right:1px solid #f8faff; white-space:nowrap; }
td:last-child { border-right:none; }
td.td-buy { padding:8px 10px; width:90px; min-width:90px; }
.ts-symbol-cell { display:flex; align-items:center; gap:10px; }
.ts-expand-btn { width:20px; height:20px; border-radius:4px; background:#f1f5f9; color:#64748b; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:700; flex-shrink:0; transition:all 0.15s; border:1px solid #e2e8f0; }
tr.expanded .ts-expand-btn { background:#00a854; color:#fff; border-color:#00a854; }
.ts-sym-name { font-size:15px; font-weight:800; color:#0f172a; letter-spacing:0.2px; }
.ts-sym-time { font-size:13px; color:#374151; margin-top:3px; font-weight:700; }
.ts-copy-btn { background:none; border:none; padding:0; cursor:pointer; color:inherit; font-weight:inherit; font-size:inherit; font-family:inherit; }
.ts-copy-btn:hover .ts-sym-name { color:#00a854; }
.ts-ltp-val { font-size:15px; font-weight:700; color:#0f172a; }
.ts-vol-ratio { font-size:14px; font-weight:700; display:inline-flex; align-items:center; gap:4px; }
.ts-vol-ratio.vr-high   { color:#7c3aed; }
.ts-vol-ratio.vr-med    { color:#d97706; }
.ts-vol-ratio.vr-normal { color:#374151; }
tr.ts-expand-row td { padding:0; border-bottom:2px solid #00a854; }
.ts-expand-panel { background:#f8fffe; padding:14px 20px; display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:10px; }
.ts-ec { background:#fff; border:1px solid #e2e8f0; border-radius:8px; padding:10px 12px; }
.ts-ec-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; color:#94a3b8; }
.ts-ec-value { font-size:14px; font-weight:700; color:#0f172a; margin-top:4px; }
.ts-ec-sub { font-size:11px; color:#94a3b8; margin-top:2px; }
.ts-toast { position:fixed; bottom:24px; left:50%; transform:translateX(-50%); background:#0f172a; color:#fff; padding:8px 18px; border-radius:8px; font-size:13px; font-weight:600; z-index:9999; opacity:0; pointer-events:none; transition:opacity 0.2s; }
.ts-toast.show { opacity:1; }
::-webkit-scrollbar { height:5px; width:5px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:#d1d5db; border-radius:4px; }
::-webkit-scrollbar-thumb:hover { background:#00a854; }
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
    setTimeout(function() { nameEl.textContent = original; nameEl.style.color = ''; }, 1500);
  }
  navigator.clipboard.writeText(sym).then(showCopied).catch(function() {
    var ta = document.createElement('textarea');
    ta.value = sym; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
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

/* ── BUY button → postMessage to Streamlit ── */
function tsBuy(e, symbol, qty, ltp) {
  e.stopPropagation();
  var btn = e.currentTarget;
  btn.disabled = true;
  btn.textContent = '⏳ Placing...';
  btn.style.background = '#94a3b8';
  window.parent.postMessage(
    { type: 'ts_manual_buy', symbol: symbol, qty: qty, ltp: ltp },
    '*'
  );
  /* Visual feedback — Streamlit will handle actual result */
  setTimeout(function() {
    btn.textContent = 'BUY x' + qty;
    btn.style.background = '#16a34a';
    btn.disabled = false;
  }, 3000);
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
  try { localStorage.setItem('ts_filter_mom', mom); localStorage.setItem('ts_filter_ema', ema); } catch (e) {}
  var count = 0;
  document.querySelectorAll('tbody tr.ts-row').forEach(function(row) {
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
      if (window.parent) { window.parent.scrollTo(0, parseInt(savedScroll, 10)); }
    }
  } catch (e) {}
}
function tsSaveScroll() {
  try { sessionStorage.setItem('ts_scroll_y', window.scrollY || window.pageYOffset || 0); } catch (e) {}
}
window.addEventListener('scroll', tsSaveScroll);
try { if (window.parent) { window.parent.addEventListener('scroll', tsSaveScroll); } } catch (e) {}
window.addEventListener('load', tsRestoreState);
setTimeout(tsRestoreState, 200);
tsRestoreState();
function tsAutoResize() {
  var height = document.documentElement.scrollHeight;
  if (window.frameElement) { window.frameElement.style.height = height + 'px'; }
  try { window.parent.postMessage({ type: 'streamlit:setFrameHeight', height: height }, '*'); } catch (e) {}
}
window.addEventListener('load', tsAutoResize);
window.addEventListener('resize', tsAutoResize);
setTimeout(tsAutoResize, 150);
setTimeout(tsAutoResize, 500);
new MutationObserver(tsAutoResize).observe(document.body, { childList: true, subtree: true, attributes: true });
document.addEventListener('keydown', function(e) {
  if (e.ctrlKey && e.shiftKey && (e.key === 'S' || e.key === 's')) { e.preventDefault(); takeScreenshot(); }
});
async function takeScreenshot() {
  var toast = document.getElementById('ts-toast');
  toast.innerHTML = '📸 Capturing...'; toast.classList.add('show');
  try {
    var blobPromise = new Promise(function(resolve) {
      html2canvas(document.body, {
        scale: 2, useCORS: true, backgroundColor: '#f8faff', scrollY: 0,
        windowHeight: document.body.scrollHeight, height: document.body.scrollHeight,
      }).then(function(canvas) { canvas.toBlob(function(blob) { resolve(blob); }, 'image/png'); });
    });
    await navigator.clipboard.write([ new ClipboardItem({ 'image/png': blobPromise }) ]);
    toast.innerHTML = '✅ Screenshot copied!';
    setTimeout(function() { toast.classList.remove('show'); toast.innerHTML = '✅ Copied!'; }, 2000);
  } catch(e) {
    toast.innerHTML = '❌ ' + (e.message || 'Failed');
    setTimeout(function() { toast.classList.remove('show'); toast.innerHTML = '✅ Copied!'; }, 2500);
  }
}
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
"""


def _expand_card(label: str, value: str, sub: str, color: str = "") -> str:
    style = f' style="color:{color}"' if color else ""
    return (f'<div class="ts-ec"><div class="ts-ec-label">{label}</div>'
            f'<div class="ts-ec-value"{style}>{value}</div>'
            f'<div class="ts-ec-sub">{sub}</div></div>')


def render_html_table(df, data_source: str = "", target_date: str = "",
                      prev_date: str = "", tick_count: int = 0,
                      already_bought: set = None,
                      capital_per_trade: float = 25000.0) -> str:

    if already_bought is None:
        already_bought = set()

    import math
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
        delivery_pct  = row.get("Delivery %", None)

        # BUY qty calculation
        qty         = max(math.floor(capital_per_trade / ltp), 1) if ltp > 0 else 1
        is_bought   = symbol in already_bought

        move_since = ((ltp - float(signal_price)) / float(signal_price)) * 100 \
                     if signal_price and float(signal_price) > 0 else 0.0

        peak_move_str = "-"
        if peak_ltp and signal_price and float(signal_price) > 0:
            pm = ((float(peak_ltp) - float(signal_price)) / float(signal_price)) * 100
            peak_move_str = f"{pm:+.2f}%"

        signal_price_str = f"₹{float(signal_price):,.2f}" if signal_price else "-"
        peak_ltp_str     = f"₹{float(peak_ltp):,.2f}"    if peak_ltp     else "-"
        vol_fmt          = _short_vol(float(row['Volume']))
        median_vol_raw   = row.get("median_vol", None)
        median_vol_str   = _short_vol(float(median_vol_raw)) if median_vol_raw else "-"

        vr_class = "vr-high" if vol_ratio_raw >= 5 else "vr-med" if vol_ratio_raw >= 3 else "vr-normal"

        mom_cls = next((cls for kw, cls in (
            ("STRONG BUILDING", "mom-strong"), ("BUILDING", "mom-build"),
            ("STABLE", "mom-stable"), ("COOLING", "mom-cooling"), ("WEAK", "mom-weak"),
        ) if kw in momentum_str), "")

        vol_emoji      = _vol_emoji(str(row['Vol Momentum']))
        prev_close_val = float(row.get('Prev Close', 0))
        open_val       = float(row.get('Open', 0))
        chg_vs_prev    = float(str(row.get('Chg vs Prev %', '0')).replace('%', '').replace('+', '') or 0)

        expand_cards = (
            _expand_card("Open", f"₹{open_val:,.2f}", "Today's open")
            + _expand_card("Prev Close", f"₹{prev_close_val:,.2f}", "Yesterday's close")
            + _expand_card("Peak Since Signal", peak_ltp_str, "Max LTP after entry", "#7c3aed")
            + _expand_card("Peak Move", peak_move_str, "Max gain possible", "#16a34a")
            + _expand_card("Volume", vol_fmt, f"Median: {median_vol_str}")
        )

        rows_html += f"""
        <tr class="ts-row {mom_cls}" id="tsm-{symbol}" data-sym="{symbol}"
            data-mom="{momentum_str.lower()}" data-ema="{ema_status or ''}"
            onclick="tsToggle('{symbol}')">
          <td class="td-buy" onclick="event.stopPropagation()">{_buy_btn_cell(symbol, qty, ltp, is_bought)}</td>
          <td><div class="ts-symbol-cell">
            <div class="ts-expand-btn">+</div>
            <button class="ts-copy-btn" onclick="tsCopy(event, this, '{symbol}')">
              <div class="ts-sym-name">{symbol}</div>
              <div class="ts-sym-time">{signal_time[:5]}</div>
            </button>
          </div></td>
          <td>{_signal_price_html(signal_price_str, move_since)}</td>
          <td><div class="ts-ltp-val">₹{ltp:,.2f}</div>{_chg_html(chg_vs_prev)}</td>
          <td><span class="ts-vol-ratio {vr_class}">{vol_emoji} {row['Vol Ratio']}</span></td>
          <td>{_prev_day_move_html(str(row.get('Prev Day Move %', '-')))}</td>
          <td>{_mom_badge(momentum_str, vol_ratio_raw, intraday_pct)}</td>
          <td>{_ema_cell(ema_status)}</td>
          <td>{_delivery_cell(delivery_pct)}</td>
        </tr>
        <tr class="ts-expand-row" id="tse-{symbol}" style="display:none">
          <td colspan="9"><div class="ts-expand-panel">{expand_cards}</div></td>
        </tr>"""

    meta = f"📅 {target_date} vs {prev_date} &nbsp;|&nbsp; Ticks: {tick_count}" \
           if (data_source or target_date) else ""

    return _STYLES + f"""
<div class="ts-header">
  <div class="ts-brand">TRADE<span>SENTRY</span></div>
  <div class="ts-status">
    <div class="ts-live"><div class="ts-live-dot"></div>Live WebSocket</div>
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
  <thead><tr>
    <th style="width:90px;">Action</th>
    <th onclick="tsColHighlight(1)">Symbol</th>
    <th onclick="tsColHighlight(2)">Signal Price</th>
    <th onclick="tsColHighlight(3)">LTP</th>
    <th onclick="tsColHighlight(4)">Vol Ratio</th>
    <th onclick="tsColHighlight(5)">Prev Day Move %</th>
    <th onclick="tsColHighlight(6)">Momentum</th>
    <th onclick="tsColHighlight(7)">EMA20 Status</th>
    <th onclick="tsColHighlight(8)">Delivery %</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>
</div>
"""
