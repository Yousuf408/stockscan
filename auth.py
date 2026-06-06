# auth.py v5.0 — Simple server-side session using cache_resource

import streamlit as st
import requests
import os
import uuid
from datetime import datetime, timedelta, timezone

SESSION_DAYS = 7

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
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def _table_url(table):
    url, _ = _get_config()
    return f"{url}/rest/v1/{table}"

def _create_session_db(user_id, user_email, access_token):
    token = str(uuid.uuid4()).replace("-", "")
    expires_at = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
    try:
        requests.post(
            _table_url("sessions"),
            headers=_headers(),
            json={"token": token, "user_id": user_id,
                  "user_email": user_email, "access_token": access_token,
                  "expires_at": expires_at},
            timeout=10,
        )
    except Exception as e:
        print(f"[auth] DB session create failed: {e}")
    return token

def _get_session_db(token):
    try:
        res = requests.get(
            _table_url("sessions"),
            headers=_headers(),
            params={"token": f"eq.{token}", "select": "*"},
            timeout=10,
        )
        rows = res.json()
        return rows[0] if rows and isinstance(rows, list) else {}
    except Exception as e:
        print(f"[auth] DB session lookup failed: {e}")
        return {}

def _delete_session_db(token):
    try:
        requests.delete(
            f"{_table_url('sessions')}?token=eq.{token}",
            headers=_headers(), timeout=10,
        )
    except Exception:
        pass

def save_session(access_token, user_id, user_email):
    token = _create_session_db(user_id, user_email, access_token)
    st.session_state["session_token"] = token
    st.query_params["s"] = token
    return token

def restore_session():
    if st.session_state.get("user_id"):
        # Already logged in — ensure token stays in URL
        token = st.session_state.get("session_token", "")
        if token and not st.query_params.get("s"):
            st.query_params["s"] = token
        return True

    # Try query param first
    token = st.query_params.get("s", "")

    # If no query param — check session_state for token
    if not token:
        token = st.session_state.get("session_token", "")

    if not token:
        return False

    session = _get_session_db(token)
    if not session:
        return False

    try:
        expires_at = datetime.fromisoformat(
            session["expires_at"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expires_at:
            _delete_session_db(token)
            return False
    except Exception:
        return False

    st.session_state["user_id"]       = session.get("user_id", "")
    st.session_state["user_email"]    = session.get("user_email", "")
    st.session_state["access_token"]  = session.get("access_token", "")
    st.session_state["session_token"] = token
    # Always keep token in URL
    st.query_params["s"] = token
    return True

def is_logged_in():
    return bool(st.session_state.get("user_id"))

def logout():
    token = st.session_state.get("session_token", "")
    if token:
        _delete_session_db(token)
    try:
        st.query_params.clear()
    except Exception:
        pass
    for k in ["user_id", "user_email", "access_token", "session_token",
              "results", "scan_log", "wl_names", "db_results_loaded"]:
        st.session_state.pop(k, None)
    st.rerun()
