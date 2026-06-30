"""
momentum/notification_helper.py
Browser push notifications for Momentum Scanner.
Standalone — does not touch backend.py or renderer.py logic.
Import into pages/8_MomentumScanner.py and call inside scanner_table().
"""

import json
from datetime import datetime, timezone, timedelta
import streamlit as st

IST = timezone(timedelta(hours=5, minutes=30))
NEW_SIGNAL_CUTOFF = "09:45:00"  # after this, no "New Signal" notifications — updates still fire


# ─────────────────────────────────────────────────────────────
# INIT
# ─────────────────────────────────────────────────────────────
def init_notif_state():
    """
    Call once at top of scanner_table().
    Structure: { stock: { vol_momentum, momentum } }
    """
    if "notif_state" not in st.session_state:
        st.session_state["notif_state"] = {}


# ─────────────────────────────────────────────────────────────
# CORE LOGIC
# ─────────────────────────────────────────────────────────────
def process_notifications(df):
    """
    Pass the final df (after Signal Time / Signal Price / etc are assigned).
    Expects columns: Symbol, Momentum, Vol Momentum, Chg vs Prev %, Vol Ratio
    Fires browser notification for:
      - New signal (not WEAK)
      - Vol Momentum changed
      - Momentum changed
    """
    notifications_to_fire = []
    current_time = datetime.now(IST).strftime("%H:%M:%S")
    allow_new_signal = current_time <= NEW_SIGNAL_CUTOFF

    for _, row in df.iterrows():
        symbol   = str(row.get("Symbol", ""))
        momentum = str(row.get("Momentum", ""))
        vol_mom  = str(row.get("Vol Momentum", ""))
        chg      = str(row.get("Chg vs Prev %", ""))
        vol_r    = str(row.get("Vol Ratio", ""))
        sig_time = str(row.get("Signal Time", ""))

        # ── Never notify WEAK ────────────────────────────────
        if "WEAK" in momentum:
            continue

        prev = st.session_state["notif_state"].get(symbol)

        if prev is None:
            if allow_new_signal:
                notifications_to_fire.append({
                    "type"        : "new",
                    "symbol"      : symbol,
                    "time"        : sig_time,
                    "chg_vs_prev" : chg,
                    "vol_ratio"   : vol_r,
                    "vol_momentum": vol_mom,
                    "momentum"    : momentum,
                    "old_vol_mom" : "",
                    "old_momentum": "",
                })
            # else: after cutoff — skip notification but still track state below
            # so that if this stock's vol_momentum/momentum changes later,
            # it correctly fires an "update" notification.
        else:
            vol_mom_changed  = prev["vol_momentum"] != vol_mom
            momentum_changed = prev["momentum"]     != momentum

            if vol_mom_changed:
                notifications_to_fire.append({
                    "type"        : "vol_update",
                    "symbol"      : symbol,
                    "time"        : sig_time,
                    "chg_vs_prev" : chg,
                    "vol_ratio"   : vol_r,
                    "vol_momentum": vol_mom,
                    "momentum"    : momentum,
                    "old_vol_mom" : prev["vol_momentum"],
                    "old_momentum": prev["momentum"],
                })

            if momentum_changed:
                notifications_to_fire.append({
                    "type"        : "mom_update",
                    "symbol"      : symbol,
                    "time"        : sig_time,
                    "chg_vs_prev" : chg,
                    "vol_ratio"   : vol_r,
                    "vol_momentum": vol_mom,
                    "momentum"    : momentum,
                    "old_vol_mom" : prev["vol_momentum"],
                    "old_momentum": prev["momentum"],
                })

        st.session_state["notif_state"][symbol] = {
            "vol_momentum": vol_mom,
            "momentum"    : momentum,
        }

    if notifications_to_fire:
        _fire_js_notifications(notifications_to_fire)


# ─────────────────────────────────────────────────────────────
# ONE-TIME PERMISSION REQUEST
# ─────────────────────────────────────────────────────────────
def request_permission_js():
    """Call ONCE on page load (outside the fragment)."""
    st.components.v1.html("""
        <script>
        if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
            Notification.requestPermission();
        }
        </script>
    """, height=0)


# ─────────────────────────────────────────────────────────────
# INTERNAL — JS FIRE
# ─────────────────────────────────────────────────────────────
def _fire_js_notifications(notifications):
    notif_json = json.dumps(notifications)

    js = f"""
    <script>
    (function() {{
        var notifications = {notif_json};

        function clean(text) {{
            return text.replace(/[^\\w\\s%+\\-.x→]/g, '').trim();
        }}

        function fire(n) {{
            var title, body;

            if (n.type === 'new') {{
                title = n.symbol + ' \u2014 New Signal';
                body  = [
                    'Momentum: '     + clean(n.momentum),
                    'Chg vs Prev: '  + n.chg_vs_prev,
                    'Vol Ratio: '    + n.vol_ratio,
                    'Vol Momentum: ' + clean(n.vol_momentum)
                ].join('\\n');
            }}
            else if (n.type === 'vol_update') {{
                title = n.symbol + ' \u2014 Vol Momentum Updated';
                body  = [
                    'Vol Momentum: ' + clean(n.old_vol_mom) + ' \u2192 ' + clean(n.vol_momentum),
                    'Momentum: '     + clean(n.momentum),
                    'Chg vs Prev: '  + n.chg_vs_prev,
                    'Vol Ratio: '    + n.vol_ratio
                ].join('\\n');
            }}
            else if (n.type === 'mom_update') {{
                title = n.symbol + ' \u2014 Momentum Updated';
                body  = [
                    'Momentum: '     + clean(n.old_momentum) + ' \u2192 ' + clean(n.momentum),
                    'Vol Momentum: ' + clean(n.vol_momentum),
                    'Chg vs Prev: '  + n.chg_vs_prev,
                    'Vol Ratio: '    + n.vol_ratio
                ].join('\\n');
            }}

            var tag = n.symbol + '_' + n.type + '_' + n.time;

            if (Notification.permission === 'granted') {{
                new Notification(title, {{ body: body, tag: tag, requireInteraction: false }});
            }} else if (Notification.permission !== 'denied') {{
                Notification.requestPermission().then(function(p) {{
                    if (p === 'granted') {{
                        new Notification(title, {{ body: body, tag: tag, requireInteraction: false }});
                    }}
                }});
            }}
        }}

        notifications.forEach(function(n) {{
            setTimeout(function() {{ fire(n); }}, 300);
        }});
    }})();
    </script>
    """
    st.components.v1.html(js, height=0)
