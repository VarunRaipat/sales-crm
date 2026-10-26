import html

import pandas as pd
import streamlit as st

from core.config import STAGES, OPEN_STAGES
from core.lists import companies
from core.db import user_names
from core.leads import visible_leads, activities_df, lead_by_id
from core.ui import lead_header, flash, fmt_dt, rupees, stage_pill
from views.lead_forms import followup_form, edit_form


def _filters(df, user, names):
    c1, c2, c3 = st.columns([2, 1, 1])
    q = c1.text_input("Search", placeholder="Name, firm, phone or city", key="ld_q")
    comp = c2.multiselect("Company", companies(), placeholder="All", key="ld_comp")
    stage_opts = ["Open (not won/lost)"] + STAGES
    stages = c3.multiselect("Stage", stage_opts, placeholder="All", key="ld_stage")
    c4, c5, c6 = st.columns(3)
    who = []
    if user["role"] != "sales":
        owners = sorted({int(i) for i in df["assigned_to"].dropna()},
                        key=lambda i: names.get(i, "").lower())
        who = c4.multiselect("Salesperson", owners, format_func=lambda i: names.get(i, "?"),
                             placeholder="Everyone", key="ld_who")
    sources = c5.multiselect("Source", sorted({s for s in df["source"] if s}),
                             placeholder="All", key="ld_src")
    products = c6.multiselect("Product", sorted({s for s in df["product"] if s}),
                              placeholder="All", key="ld_prod")

    if q.strip():
        s = q.strip().lower()
        digits = "".join(ch for ch in s if ch.isdigit())
        hay = (df["name"] + " " + df["firm"] + " " + df["city"] + " " + df["email"]).str.lower()
        m = hay.str.contains(s, regex=False)
        if len(digits) >= 4:
            m |= df["phone"].str.contains(digits, regex=False) | \
                df["alt_phone"].str.contains(digits, regex=False)
        df = df[m]
    if comp:
        df = df[df["company"].isin(comp)]
    if stages:
        want = set(s for s in stages if s in STAGES)
        if "Open (not won/lost)" in stages:
            want |= set(OPEN_STAGES)
        df = df[df["stage"].isin(want)]
    if who:
        df = df[df["assigned_to"].isin(who)]
    if sources:
        df = df[df["source"].isin(sources)]
    if products:
        df = df[df["product"].isin(products)]
    return df


def _table(df, names):
    return pd.DataFrame({
        "Lead": df["name"] + df["firm"].map(lambda f: f" · {f}" if f else ""),
        "Company": df["company"],
        "Stage": df["stage"],
        "Next follow-up": df["next_followup_at"].map(lambda t: fmt_dt(t)),
        "Phone": df["phone"],
        "City": df["city"],
        "Product": df["product"],
        "Value (₹)": df["value"].round(0).astype(int),
        "Salesperson": df["assigned_to"].map(lambda i: names.get(int(i), "") if pd.notna(i) else ""),
        "Source": df["source"],
        "Added": df["created_at"].map(lambda t: fmt_dt(t, with_time=False)),
        "No.": df["id"],
    })


def history(lead_id, names):
    a = activities_df()
    a = a[a["lead_id"] == int(lead_id)]
    if a.empty:
        st.caption("No history yet.")
        return
    out = []
    for r in a.to_dict("records"):
        who = html.escape(names.get(int(r["user_id"]), "") if pd.notna(r["user_id"]) else "")
        head = f"<b>{html.escape(r['kind'])}</b>"
        if r["stage_to"] and r["stage_from"] and r["stage_to"] != r["stage_from"]:
            head += f" · {html.escape(r['stage_from'])} → {stage_pill(r['stage_to'])}"
        line = f'<div class="hist">{head}<br><small>{fmt_dt(r["created_at"])} · {who}'
        if pd.notna(r["next_followup_at"]):
            line += f' · next follow-up {fmt_dt(r["next_followup_at"])}'
        line += "</small>"
        if r["note"]:
            line += f"<p>{html.escape(r['note'])}</p>"
        out.append(line + "</div>")
    st.markdown("".join(out), unsafe_allow_html=True)


def detail(lead, user, names):
    with st.container(border=True):
        owner = names.get(int(lead["assigned_to"])) if pd.notna(lead["assigned_to"]) else None
        lead_header(lead, owner_name=owner)
        extra = []
        if lead["alt_phone"]:
            extra.append(f"Other phone: {lead['alt_phone']}")
        if lead["email"]:
            extra.append(f"Email: {lead['email']}")
        if lead["requirement"]:
            extra.append(f"Requirement: {lead['requirement']}")
        if lead["source"]:
            extra.append(f"Source: {lead['source']}")
        if lead["stage"] == "Lost" and lead["lost_reason"]:
            extra.append(f"Lost because: {lead['lost_reason']}")
        extra.append(f"Added {fmt_dt(lead['created_at'], with_time=False)}")
        st.caption(" · ".join(extra))
        if lead["notes"]:
            st.markdown(f"📝 {lead['notes']}")
        with st.expander("✏️ Log a follow-up / change stage", expanded=True):
            followup_form(lead, user, key="ld")
        with st.expander("🛠️ Edit lead details"):
            edit_form(lead, user)
        st.markdown("**History**")
        history(lead["id"], names)


def render(user):
    st.title("📋 Leads")
    flash()
    names = user_names()
    allv = visible_leads(user)
    df = _filters(allv, user, names)

    m = st.columns(4)
    m[0].metric("Leads", len(df))
    m[1].metric("Open", int(df["stage"].isin(OPEN_STAGES).sum()))
    m[2].metric("Won", int((df["stage"] == "Won").sum()))
    m[3].metric("Open value", rupees(df.loc[df["stage"].isin(OPEN_STAGES), "value"].sum()))

    if df.empty:
        st.info("No leads match." if len(allv) else "No leads yet. Add one from ➕ New lead.")
        return

    tbl = _table(df, names)
    st.caption("Tap a row to open the lead.")
    ev = st.dataframe(tbl, hide_index=True, width="stretch", height=min(420, 38 + 35 * len(tbl)),
                      on_select="rerun", selection_mode="single-row", key="ld_table",
                      column_config={
                          "Lead": st.column_config.TextColumn("Lead", pinned=True),
                          "Value (₹)": st.column_config.NumberColumn("Value (₹)", format="localized"),
                      })
    st.download_button("⬇️ Download these leads (CSV)", tbl.to_csv(index=False).encode("utf-8-sig"),
                       "leads.csv", "text/csv")

    lead_id = None
    rows = ev.selection.rows if ev and ev.selection else []
    if rows:
        lead_id = int(df.iloc[rows[0]]["id"])
        st.session_state["open_lead"] = lead_id
    elif st.session_state.get("open_lead"):
        lead_id = int(st.session_state["open_lead"])
    if lead_id is None:
        return
    lead = lead_by_id(lead_id)
    if not lead or lead_id not in set(int(i) for i in allv["id"]):
        st.session_state.pop("open_lead", None)
        return
    st.divider()
    h1, h2 = st.columns([5, 1], vertical_alignment="center")
    h1.subheader(f"Lead #{lead_id}")
    if h2.button("✖ Close", width="stretch"):
        st.session_state.pop("open_lead", None)
        st.session_state.pop("ld_table", None)
        st.rerun()
    detail(lead, user, names)
