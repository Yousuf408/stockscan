# ══════════════════════════════════════════════════════════════════════════════
#  TRADE SENTRY — auth.py  v4.0
#  Server-side session persistence via Supabase sessions table
#  Token stored in URL query param — persists across all refreshes
# ══════════════════════════════════════════════════════════════════════════════

import streamlit as st
import requests
import os
import uuid
from datetime import datetime, timedelta, timezone

SESSION_PARAM   = "s"        # URL query param name
SESSION_DAYS    = 7          # session validity


def _get_config():
    try:
        url = st.secrets["SUPABASE_URL"].rstrip("/")
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_KEY", "")
    return url, key


def _headers():
    _, key = _get_config()
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "return=representation",
    }


def _table_url(table: str) -> str:
    url, _ = _get_config()
    return f"{url}/rest/v1/{table}"


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STORE — Supabase sessions table
# ─────────────────────────────────────────────────────────────────────────────

def _create_session(user_id: str, user_email: str, access_token: str) -> str:
    """Create session in Supabase, return session_token."""
    token      = str(uuid.uuid4()).replace("-", "")
    expires_at = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
    try:
        requests.post(
            _table_url("sessions"),
            headers=_headers(),
            json={
                "token":        token,
                "user_id":      user_id,
                "user_email":   user_email,
                "access_token": access_token,
                "expires_at":   expires_at,
            },
            timeout=10,
        )
    except Exception as e:
        print(f"[auth] Session create failed: {e}")
    return token


def _get_session(token: str) -> dict:
    """Lookup session from Supabase by token."""
    try:
        url  = _table_url("sessions")
        res  = requests.get(
            url,
            headers=_headers(),
            params={"token": f"eq.{token}", "select": "*"},
            timeout=10,
        )
        rows = res.json()
        if rows and isinstance(rows, list) and len(rows) > 0:
            return rows[0]
        return {}
    except Exception as e:
        print(f"[auth] Session lookup failed: {e}")
        return {}


def _delete_session(token: str):
    """Delete session from Supabase."""
    try:
        requests.delete(
            f"{_table_url('sessions')}?token=eq.{token}",
            headers=_headers(),
            timeout=10,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def restore_session() -> bool:
    """
    Call at top of EVERY page before auth guard.
    Reads session token from URL param → looks up Supabase → restores session.
    Works perfectly across all page refreshes and navigation.
    """
    # Already logged in this session
    if st.session_state.get("user_id"):
        return True

    # Read token from URL
    token = st.query_params.get(SESSION_PARAM, "")
    if not token:
        return False

    # Lookup in Supabase
    session = _get_session(token)
    if not session:
        return False

    # Check expiry
    try:
        expires_at = datetime.fromisoformat(
            session["expires_at"].replace("Z", "+00:00")
        )
        if datetime.now(timezone.utc) > expires_at:
            _delete_session(token)
            return False
    except Exception:
        return False

    # Restore session
    st.session_state["user_id"]      = session.get("user_id", "")
    st.session_state["user_email"]   = session.get("user_email", "")
    st.session_state["access_token"] = session.get("access_token", "")
    st.session_state["session_token"]= token
    return True


def save_session(access_token: str, user_id: str, user_email: str) -> str:
    """
    Call after successful login.
    Creates server-side session and returns token.
    Token must be added to URL manually after this call.
    """
    token = _create_session(user_id, user_email, access_token)
    st.session_state["session_token"] = token
    return token


def is_logged_in() -> bool:
    return bool(st.session_state.get("user_id"))


def logout():
    """Delete session and clear state."""
    token = st.session_state.get("session_token", "")
    if token:
        _delete_session(token)

    # Clear URL param
    try:
        st.query_params.clear()
    except Exception:
        pass

    # Clear session state
    for k in ["user_id", "user_email", "access_token", "session_token",
              "results", "scan_log", "wl_names", "db_results_loaded"]:
        st.session_state.pop(k, None)

    st.rerun()
