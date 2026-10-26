import streamlit as st

from core.config import ROLE_LABELS
from core.db import change_own_password, clear_all_caches


def password_form(user, forced=False):
    if forced:
        st.warning("Please set your own password before continuing.")
    with st.form("change_pw"):
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password")
        new2 = st.text_input("Repeat new password", type="password")
        if st.form_submit_button("Change password", type="primary"):
            if new != new2:
                st.error("New passwords don't match.")
            elif new == old:
                st.error("Choose a different password from the current one.")
            else:
                err = change_own_password(user["id"], old, new)
                if err:
                    st.error(err)
                else:
                    st.session_state["user"]["must_change"] = False
                    st.success("Password changed.")
                    st.rerun()


def render(user):
    st.title("🔑 My account")
    st.write(f"**{user['name']}** · user ID `{user['username']}` · "
             f"{ROLE_LABELS.get(user['role'], user['role'])}")
    if user["role"] == "sales":   # salespeople have no sidebar
        b1, b2 = st.columns(2)
        if b1.button("🔄 Refresh", width="stretch"):
            clear_all_caches()
            st.rerun()
        if b2.button("🚪 Log out", width="stretch"):
            st.session_state.clear()
            st.rerun()
    st.subheader("Change password")
    password_form(user)
    with st.expander("📱 Put this app on your phone's home screen"):
        st.markdown("Open the app link in your phone's browser, then:")
        st.markdown("**Android (Chrome):** tap **⋮** (top right) → **Add to Home screen** → **Add**.")
        st.markdown("**iPhone (Safari):** tap **Share** (square with arrow) → "
                    "**Add to Home Screen** → **Add**.")
