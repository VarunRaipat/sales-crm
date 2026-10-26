import pandas as pd
import streamlit as st

from core.lists import companies
from core.db import user_names
from core.leads import visible_leads, followup_buckets, activities_df
from core.ui import lead_header, flash
from views.lead_forms import followup_form

MAX_CARDS = 60


def _last_notes():
    a = activities_df()
    a = a[a["note"] != ""]
    return a.drop_duplicates("lead_id").set_index("lead_id")["note"].to_dict()


def render(user):
    st.title("📅 Follow-ups")
    flash()
    df = visible_leads(user)
    names = user_names()
    show_owner = user["role"] != "sales"

    c1, c2 = st.columns(2)
    comp = c1.multiselect("Company", companies(), placeholder="All companies", key="fu_comp")
    if comp:
        df = df[df["company"].isin(comp)]
    if show_owner:
        owners = sorted({int(i) for i in df["assigned_to"].dropna()},
                        key=lambda i: names.get(i, "").lower())
        who = c2.multiselect("Salesperson", owners, format_func=lambda i: names.get(i, "?"),
                             placeholder="Everyone", key="fu_who")
        if who:
            df = df[df["assigned_to"].isin(who)]

    b = followup_buckets(df)
    m = st.columns(4)
    m[0].metric("🔴 Overdue", len(b["overdue"]))
    m[1].metric("🟡 Today", len(b["today"]))
    m[2].metric("🕒 Next 7 days", len(b["upcoming"]))
    m[3].metric("⚪ No date set", len(b["nodate"]))

    views = {
        "now": f"To do now ({len(b['overdue']) + len(b['today'])})",
        "upcoming": f"Next 7 days ({len(b['upcoming'])})",
        "nodate": f"No date ({len(b['nodate'])})",
        "later": f"Later ({len(b['later'])})",
    }
    pick = st.segmented_control("Show", list(views), format_func=views.get, default="now",
                                key="fu_view", label_visibility="collapsed") or "now"
    if pick == "now":
        rows = list(b["overdue"].to_dict("records")) + list(b["today"].to_dict("records"))
    else:
        rows = list(b[pick].to_dict("records"))

    if not rows:
        st.info("🎉 Nothing here. All follow-ups are done." if pick == "now"
                else "No leads in this list.")
        if user["role"] != "admin" and not len(df):
            st.caption("Add your first lead from ➕ New lead.")
        return

    notes = _last_notes()
    for lead in rows[:MAX_CARDS]:
        with st.container(border=True):
            owner = names.get(int(lead["assigned_to"])) if show_owner and pd.notna(lead["assigned_to"]) else None
            lead_header(lead, owner_name=owner, last_note=notes.get(lead["id"]))
            with st.expander("✏️ Update this lead"):
                followup_form(lead, user, key="fu")
            if st.button("Open full lead →", key=f"open_{lead['id']}"):
                st.session_state["open_lead"] = int(lead["id"])
                st.session_state["goto"] = "leads"
                st.rerun()
    if len(rows) > MAX_CARDS:
        st.caption(f"Showing the first {MAX_CARDS} of {len(rows)}. Use the filters above "
                   "or the 📋 Leads page to see the rest.")
