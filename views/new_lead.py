from datetime import time

import pandas as pd
import streamlit as st

from core.config import COMPANIES, PRODUCTS, SOURCES, DEFAULT_FOLLOWUP_HOUR
from core.db import user_names
from core.leads import add_lead, find_duplicates, clean_phone, to_utc_iso
from core.scope import owner_options
from core.ui import flash, start_of_today


def render(user):
    st.title("➕ New lead")
    flash("new_flash")
    company = st.segmented_control("Company *", COMPANIES, key="nl_company",
                                   default=st.session_state.get("nl_last_company", COMPANIES[0]))
    if not company:
        st.info("Pick the company this lead is for.")
        return
    owners = owner_options(user)
    nonce = st.session_state.setdefault("nl_nonce", 0)

    with st.form(f"new_lead_{nonce}"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Contact person *", placeholder="e.g. Ramesh Kumar")
        firm = c2.text_input("Firm / project", placeholder="e.g. Shiv Constructions")
        c3, c4 = st.columns(2)
        phone = c3.text_input("Phone *", placeholder="10-digit mobile")
        alt = c4.text_input("Other phone")
        c5, c6 = st.columns(2)
        city = c5.text_input("City / area")
        source = c6.selectbox("Where did the lead come from?", SOURCES, index=None,
                              placeholder="Choose…")
        c7, c8 = st.columns(2)
        product = c7.selectbox("Product", PRODUCTS.get(company, []), index=None,
                               accept_new_options=True, placeholder="Choose or type…")
        req = c8.text_input("Quantity / requirement", placeholder="e.g. 5,000 sq ft, 80 mm")
        c9, c10 = st.columns(2)
        value = c9.number_input("Expected order value (₹)", min_value=0.0, step=1000.0)
        email = c10.text_input("Email")
        notes = st.text_area("Notes", height=70, placeholder="Anything useful about this lead")
        st.markdown("**First follow-up**")
        c11, c12, c13 = st.columns(3)
        d = c11.date_input("Date", value=start_of_today().date(), format="DD/MM/YYYY")
        t = c12.time_input("Time", value=time(DEFAULT_FOLLOWUP_HOUR, 0), step=900)
        if user["role"] == "sales":
            owner = int(user["id"])
            c13.text_input("Salesperson", user["name"], disabled=True)
        else:
            owner = c13.selectbox("Salesperson", list(owners), format_func=owners.get,
                                  index=list(owners).index(int(user["id"]))
                                  if int(user["id"]) in owners else 0)
        same_ok = st.checkbox("Save even if this phone is already a lead for this company")
        go = st.form_submit_button("Save lead", type="primary", width="stretch")

    if not go:
        return
    p = clean_phone(phone)
    if not name.strip():
        st.error("Contact person is required.")
        return
    if len(p) != 10:
        st.error("Enter a 10-digit phone number.")
        return
    if d is None:
        st.error("Pick the first follow-up date.")
        return
    if d < start_of_today().date():
        st.error("First follow-up can't be in the past.")
        return
    dup = find_duplicates(p)
    if not dup.empty:
        names = user_names()
        same = dup[dup["company"] == company]
        if not same.empty and not same_ok:
            r = same.iloc[0]
            owner_name = names.get(int(r["assigned_to"]), "?") if pd.notna(r["assigned_to"]) else "?"
            st.error(f"This phone is already lead #{int(r['id'])} — **{r['name']}** "
                     f"({r['stage']}, with {owner_name}) for {company}. "
                     "Tick the box above the Save button to add it anyway.")
            return
        others = dup[dup["company"] != company]
        if not others.empty:
            st.session_state["nl_note"] = ("Same phone is also a lead for "
                                           + ", ".join(sorted(set(others["company"]))) + ".")
    saved = add_lead({
        "company": company, "name": name, "firm": firm, "phone": p, "alt_phone": alt,
        "email": email, "city": city, "source": source or "", "product": product or "",
        "requirement": req, "value": value, "notes": notes, "assigned_to": owner,
    }, user, followup_at=to_utc_iso(d, t))
    st.session_state["nl_nonce"] = nonce + 1
    st.session_state["nl_last_company"] = company
    msg = f"Lead #{saved['id']} saved — {name.strip()} ({company})."
    if st.session_state.get("nl_note"):
        msg += " " + st.session_state.pop("nl_note")
    st.session_state["new_flash"] = msg
    st.rerun()
