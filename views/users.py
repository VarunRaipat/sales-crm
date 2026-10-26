import pandas as pd
import streamlit as st

from core.config import ROLES, ROLE_LABELS
from core.db import users_df, insert_user, update_user, password_problem, user_names
from core.leads import leads_df
from core.config import OPEN_STAGES


def render(user):
    st.title("👥 Users")
    st.caption("**Admin** sees everything. **Sales manager** sees their own leads and their "
               "team's (people who report to them). **Salesperson** sees only their own leads.")
    df = users_df()
    names = user_names()
    managers = {int(r["id"]): r["name"] for r in df.to_dict("records")
                if r["role"] in ("manager", "admin") and r["active"]}

    with st.expander("➕ Add a person", expanded=df.shape[0] <= 1):
        nonce = st.session_state.setdefault("user_nonce", 0)
        with st.form(f"add_user_{nonce}"):
            c1, c2 = st.columns(2)
            name = c1.text_input("Full name *")
            username = c2.text_input("User ID *", help="What they type to log in, e.g. ramesh")
            c3, c4 = st.columns(2)
            role = c3.selectbox("Role", ROLES, index=2, format_func=ROLE_LABELS.get)
            phone = c4.text_input("Phone")
            c5, c6 = st.columns(2)
            mgr = c5.selectbox("Reports to", [None] + list(managers),
                               format_func=lambda i: "— nobody —" if i is None else managers[i])
            pw = c6.text_input("Temporary password *", type="password",
                               help="They will be asked to change it at first login.")
            if st.form_submit_button("Add person", type="primary"):
                prob = password_problem(pw)
                if not name.strip() or not username.strip():
                    st.error("Name and user ID are required.")
                elif " " in username.strip():
                    st.error("User ID can't have spaces.")
                elif prob:
                    st.error(prob)
                else:
                    try:
                        insert_user(username, name, pw, role, phone, mgr)
                        st.session_state["user_nonce"] = nonce + 1
                        st.session_state["user_flash"] = (
                            f"Added {name.strip()} — user ID "
                            f"'{username.strip().lower()}'. Share the password with them.")
                        st.rerun()
                    except ValueError as ex:
                        st.error(str(ex))

    if st.session_state.get("user_flash"):
        st.success(st.session_state.pop("user_flash"))

    ld = leads_df()
    open_count = ld[ld["stage"].isin(OPEN_STAGES)].groupby("assigned_to")["id"].count()
    show_all = st.checkbox("Show inactive people")
    view = df if show_all else df[df["active"]]
    st.dataframe(pd.DataFrame({
        "Name": view["name"],
        "User ID": view["username"],
        "Role": view["role"].map(ROLE_LABELS),
        "Phone": view["phone"],
        "Reports to": view["manager_id"].map(lambda i: names.get(int(i), "") if pd.notna(i) else ""),
        "Open leads": view["id"].map(lambda i: int(open_count.get(i, 0))),
        "Active": view["active"].map({True: "Yes", False: "No"}),
    }), hide_index=True, width="stretch",
        column_config={"Name": st.column_config.TextColumn("Name", pinned=True)})

    st.divider()
    opts = {int(r["id"]): f"{r['name']} ({r['username']})" for r in df.to_dict("records")}
    uid = st.selectbox("Edit a person", list(opts), format_func=opts.get,
                       index=None, placeholder="Choose…")
    if uid is None:
        return
    r = df[df["id"] == uid].iloc[0]
    is_me = uid == int(user["id"])
    with st.form(f"edit_user_{uid}"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name", r["name"])
        phone = c2.text_input("Phone", r["phone"] or "")
        c3, c4 = st.columns(2)
        role = c3.selectbox("Role", ROLES, index=ROLES.index(r["role"]) if r["role"] in ROLES else 2,
                            format_func=ROLE_LABELS.get, disabled=is_me)
        mopts = [None] + [m for m in managers if m != uid]
        cur = int(r["manager_id"]) if pd.notna(r["manager_id"]) else None
        mgr = c4.selectbox("Reports to", mopts,
                           index=mopts.index(cur) if cur in mopts else 0,
                           format_func=lambda i: "— nobody —" if i is None else managers[i])
        c5, c6 = st.columns(2)
        active = c5.toggle("Active (can log in)", bool(r["active"]), disabled=is_me)
        new_pw = c6.text_input("Reset password (leave blank to keep)", type="password",
                               help="Passwords are stored scrambled, so no one can read them. "
                                    "If someone forgets theirs, set a new one here.")
        if st.form_submit_button("Save", type="primary"):
            fields = {"name": name.strip(), "phone": phone.strip(), "manager_id": mgr}
            if not is_me:
                fields.update({"role": role, "active": active})
            if new_pw:
                prob = password_problem(new_pw)
                if prob:
                    st.error(prob)
                    st.stop()
                fields.update({"password": new_pw, "must_change": True})
            update_user(uid, **fields)
            st.success("Saved.")
            st.rerun()
    n_open = int(open_count.get(uid, 0))
    if n_open and not r["active"]:
        st.warning(f"{r['name']} is inactive but still has {n_open} open leads. Move them to "
                   "someone else from 📋 Leads → open a lead → Edit lead details, or use "
                   "the button below.")
    if n_open:
        others = {int(x["id"]): x["name"] for x in df[df["active"]].to_dict("records")
                  if int(x["id"]) != uid}
        with st.expander(f"↪️ Move all {n_open} open leads of {r['name']} to someone else"):
            to = st.selectbox("Give them to", list(others), format_func=others.get, key=f"mv_{uid}")
            if st.button("Move leads", key=f"mvb_{uid}"):
                from core.leads import update_lead
                mine = ld[(ld["assigned_to"] == uid) & ld["stage"].isin(OPEN_STAGES)]
                for lead in mine.to_dict("records"):
                    update_lead(lead["id"], user, {"assigned_to": int(to)}, old=lead)
                st.success(f"Moved {len(mine)} leads to {others[to]}.")
                st.rerun()
    st.caption("People are never deleted, only made inactive, so their lead history stays.")
