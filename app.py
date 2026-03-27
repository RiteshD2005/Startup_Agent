"""
app.py
------
Entry point. Auth, rate limiting, page routing.
"""

import time
import streamlit as st
from contextlib import contextmanager

from database.db import init_db, SessionLocal
from database import crud

init_db()

st.set_page_config(
    page_title="Venture Agent",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _init_auth():
    defaults = {
        "authenticated":       False,
        "user_id":             None,
        "user_email":          None,
        "_login_attempts":     0,
        "_login_locked_until": 0.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_auth()
_MAX_ATTEMPTS = 5
_LOCKOUT_SECS = 60


with st.sidebar:
    if not st.session_state.authenticated:
        st.title("Venture Agent")
        st.caption("Sign in or create an account to continue.")
        st.divider()

        locked_until = st.session_state._login_locked_until
        if time.time() < locked_until:
            remaining = int(locked_until - time.time())
            st.error(f"Too many failed attempts. Try again in {remaining}s.")
            st.stop()

        with st.form("auth_form"):
            email       = st.text_input("Email")
            password    = st.text_input("Password", type="password")
            c1, c2      = st.columns(2)
            do_login    = c1.form_submit_button("Login",    use_container_width=True)
            do_register = c2.form_submit_button("Register", use_container_width=True)

        if do_login:
            with get_db() as db:
                user_info = crud.authenticate_user(db, email, password)
            if user_info:
                st.session_state.authenticated       = True
                st.session_state.user_id             = user_info["id"]
                st.session_state.user_email          = user_info["email"]
                st.session_state._login_attempts     = 0
                st.rerun()
            else:
                st.session_state._login_attempts += 1
                if st.session_state._login_attempts >= _MAX_ATTEMPTS:
                    st.session_state._login_locked_until = time.time() + _LOCKOUT_SECS
                    st.error(f"Account locked for {_LOCKOUT_SECS}s.")
                else:
                    left = _MAX_ATTEMPTS - st.session_state._login_attempts
                    st.error(f"Invalid credentials. {left} attempt(s) left.")

        if do_register:
            if not email or not password:
                st.error("Email and password are required.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                with get_db() as db:
                    user_info = crud.create_user(db, email, password)
                if user_info:
                    st.success("Account created! You can now log in.")
                else:
                    st.error("That email is already registered.")

    else:
        st.markdown(f"**{st.session_state.user_email}**")
        st.caption("Logged in")
        st.divider()

        with get_db() as db:
            projects  = crud.get_projects_by_user(db, st.session_state.user_id)
            active    = sum(1 for p in projects if p.status == "active")
            completed = sum(1 for p in projects if p.status == "completed")
            st.metric("Active ventures",    active)
            st.metric("Completed ventures", completed)
            st.divider()

        if st.button("Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


if not st.session_state.authenticated:
    st.title("Welcome to Venture Agent 🚀")
    st.write("Your autonomous AI startup team. Log in or register in the sidebar.")
    st.stop()


pages = [
    st.Page("pages/dashboard.py",   title="Dashboard",   icon="🏠"),
    st.Page("pages/new_venture.py", title="New Venture",  icon="➕"),
    st.Page("pages/agents.py",      title="Agents",       icon="🤖"),
    st.Page("pages/project.py",     title="Project",      icon="📊"),
]

# if st.session_state.get("selected_project_id"):
#     pages.insert(2, st.Page("pages/project.py", title="Project", icon="📊"))

pg = st.navigation(pages)
pg.run()