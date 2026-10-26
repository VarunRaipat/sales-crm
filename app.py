import importlib
import os
import time
from datetime import datetime

import streamlit as st

from core.config import APP_NAME, TAGLINE, IST
from core.db import init_db, authenticate, fresh_user, using_supabase, clear_all_caches
from core.ui import inject_css

ICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
st.set_page_config(page_title=APP_NAME, page_icon=ICON if os.path.exists(ICON) else "📇",
                   layout="wide")
inject_css()

RECHECK_SEC = 60   # re-read the user's active/role from the DB this often

PAGES = {
    "followups": ("📅 Follow-ups", "views.followups"),
    "new": ("➕ New lead", "views.new_lead"),
    "leads": ("📋 Leads", "views.leads"),
    "dashboard": ("📊 Dashboard", "views.dashboard"),
    "import": ("📥 Import leads", "views.import_leads"),
    "users": ("👥 Users", "views.users"),
    "dropdowns": ("⚙️ Dropdowns", "views.dropdowns"),
    "account": ("🔑 My account", "views.account"),
}
SHORT = {"followups": "📅 Follow-ups", "new": "➕ New", "leads": "📋 Leads",
         "account": "👤 Account"}   # top menu labels (salespeople, on phones)
MENU = {
    "admin": ["followups", "new", "leads", "dashboard", "import", "users", "dropdowns", "account"],
    "manager": ["followups", "new", "leads", "dashboard", "import", "account"],
    "sales": ["followups", "new", "leads", "account"],
}


@st.cache_resource
def _boot():
    init_db()
    return True


def login():
    _, mid, _ = st.columns([1, 1.6, 1])
    with mid:
        st.markdown(f"<h1 class='login-title'>📇 {APP_NAME}</h1>"
                    f"<p style='text-align:center;color:#6b7280'>{TAGLINE}</p>",
                    unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("User ID")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary", width="stretch"):
                user = authenticate(u, p)
                if user:
                    st.session_state["user"] = user
                    st.session_state["checked_at"] = time.time()
                    st.rerun()
                else:
                    st.error("Wrong user ID or password.")
        if not using_supabase():
            st.caption("⚠️ Running on a local test database (no Supabase keys).")


def refresh():
    clear_all_caches()
    st.rerun()


def _copy(src, dst):
    st.session_state[dst] = st.session_state[src]


def side_menu(user, keys):
    with st.sidebar:
        st.markdown(f"### 📇 {APP_NAME}")
        st.caption(user["name"])
        st.caption(f"🕒 {datetime.now(IST):%a %d %b, %I:%M %p}")
        page = st.radio("Menu", keys, format_func=lambda k: PAGES[k][0],
                        label_visibility="collapsed", key="nav",
                        on_change=_copy, args=("nav", "nav_m"))
        st.divider()
        if st.button("🔄 Refresh", width="stretch"):
            refresh()
        if st.button("Log out", width="stretch"):
            st.session_state.clear()
            st.rerun()
    # Phones: the sidebar is folded away, so also show the menu as a dropdown.
    st.session_state["nav_m"] = page
    with st.container(key="mobile_nav"):
        m1, m2 = st.columns([5, 1], vertical_alignment="bottom")
        page = m1.selectbox("Go to", keys, format_func=lambda k: PAGES[k][0], key="nav_m",
                            on_change=_copy, args=("nav_m", "nav"))
        if m2.button("🔄", help="Refresh", key="m_refresh"):
            refresh()
    return page


def top_menu(user, keys):
    """Salespeople: a few big buttons across the top (works well on a phone)."""
    st.markdown(f'<div class="topbar"><b>📇 {APP_NAME}</b>'
                f'<span>{user["name"]} · {datetime.now(IST):%a %d %b, %I:%M %p}</span></div>',
                unsafe_allow_html=True)
    with st.container(key="topnav"):
        page = st.segmented_control("Menu", keys, format_func=lambda k: SHORT.get(k, PAGES[k][0]),
                                    required=True, key="nav", label_visibility="collapsed",
                                    width="stretch")
    return page or keys[0]


def main():
    if not using_supabase() and os.path.exists("/mount/src"):
        st.error("Database keys are missing. Add SUPABASE_URL and SUPABASE_KEY "
                 "in the app's Settings → Secrets on Streamlit Cloud.")
        st.stop()
    _boot()
    user = st.session_state.get("user")
    if not user:
        login()
        return

    if time.time() - st.session_state.get("checked_at", 0) > RECHECK_SEC:
        fresh = fresh_user(user["id"])
        if not fresh or not fresh.get("active"):
            st.session_state.clear()
            st.rerun()
        st.session_state["user"] = user = fresh
        st.session_state["checked_at"] = time.time()

    if user.get("must_change"):
        from views.account import password_form
        st.title(f"Welcome, {user['name']}")
        password_form(user, forced=True)
        if st.button("Log out"):
            st.session_state.clear()
            st.rerun()
        return

    keys = MENU.get(user["role"], MENU["sales"])
    goto = st.session_state.pop("goto", None)
    if goto in keys:
        st.session_state["nav"] = goto
    if st.session_state.get("nav") not in keys:
        st.session_state["nav"] = keys[0]

    page = top_menu(user, keys) if user["role"] == "sales" else side_menu(user, keys)
    importlib.import_module(PAGES[page][1]).render(user)


main()
