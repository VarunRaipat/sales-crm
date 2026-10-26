"""Forms shared by several pages: log a follow-up, edit a lead."""
from datetime import datetime, time

import pandas as pd
import streamlit as st

from core.config import (
    STAGES, CLOSED_STAGES,
    DEFAULT_FOLLOWUP_HOUR, IST,
)
from core.leads import now_ist, log_followup, update_lead, to_utc_iso, find_duplicates, clean_phone
from core.lists import companies, products, sources, lost_reasons, activity_kinds
from core.scope import owner_options
from core.ui import tomorrow


def followup_form(lead, user, key):
    """What happened + next follow-up. Saves and reruns."""
    lid = int(lead["id"])
    k = f"{key}_{lid}"
    with st.form(f"fu_{k}", clear_on_submit=True, border=False):
        c1, c2 = st.columns(2)
        kind = c1.selectbox("What did you do?", activity_kinds(), key=f"kind_{k}")
        stage = c2.selectbox("Stage now", STAGES, index=STAGES.index(lead["stage"])
                             if lead["stage"] in STAGES else 0, key=f"stage_{k}")
        note = st.text_area("What happened? *", key=f"note_{k}", height=80,
                            placeholder="e.g. Spoke to site engineer, wants rate for 5,000 sq ft")
        c3, c4 = st.columns(2)
        d = c3.date_input("Next follow-up", value=tomorrow(), format="DD/MM/YYYY",
                          key=f"d_{k}", help="Not needed if the lead is Won or Lost.")
        t = c4.time_input("Time", value=time(DEFAULT_FOLLOWUP_HOUR, 0), step=900, key=f"t_{k}")
        c5, c6 = st.columns(2)
        value = c5.number_input("Expected order value (₹)", min_value=0.0, step=1000.0,
                                value=float(lead.get("value") or 0), key=f"v_{k}")
        lost = c6.selectbox("If Lost — why?", [""] + lost_reasons(), key=f"lost_{k}")
        if st.form_submit_button("💾 Save follow-up", type="primary", width="stretch"):
            if not note.strip():
                st.error("Write a line about what happened.")
                return
            if stage == "Lost" and not lost:
                st.error("Pick why the lead was lost.")
                return
            if stage not in CLOSED_STAGES and d is None:
                st.error("Pick the next follow-up date.")
                return
            if stage not in CLOSED_STAGES and datetime.combine(d, t, tzinfo=IST) < now_ist():
                st.error("Next follow-up can't be in the past.")
                return
            log_followup(lead, user, kind, note, stage,
                         followup_at=None if stage in CLOSED_STAGES else to_utc_iso(d, t),
                         lost_reason=lost, value=value)
            st.session_state["flash"] = f"Saved — {lead['name']} is now **{stage}**."
            st.rerun()


def edit_form(lead, user, key="edit"):
    """Change contact details, product, owner."""
    lid = int(lead["id"])
    owners = owner_options(user)
    cur_owner = int(lead["assigned_to"]) if pd.notna(lead.get("assigned_to")) else None
    if cur_owner is not None and cur_owner not in owners:
        from core.db import user_names
        owners[cur_owner] = user_names().get(cur_owner, "?")
    with st.form(f"{key}_{lid}", border=False):
        c1, c2 = st.columns(2)
        name = c1.text_input("Contact person *", lead["name"])
        firm = c2.text_input("Firm / project", lead["firm"])
        c3, c4 = st.columns(2)
        phone = c3.text_input("Phone *", lead["phone"])
        alt = c4.text_input("Other phone", lead["alt_phone"])
        c5, c6 = st.columns(2)
        email = c5.text_input("Email", lead["email"])
        city = c6.text_input("City / area", lead["city"])
        c7, c8 = st.columns(2)
        comps = companies()
        if lead["company"] and lead["company"] not in comps:
            comps.append(lead["company"])
        company = c7.selectbox("Company", comps, index=comps.index(lead["company"])
                               if lead["company"] in comps else 0)
        src_opts = sources()
        if lead["source"] and lead["source"] not in src_opts:
            src_opts.append(lead["source"])
        source = c8.selectbox("Source", [""] + src_opts,
                              index=([""] + src_opts).index(lead["source"]))
        c9, c10 = st.columns(2)
        prods = products(lead["company"]) or products()
        if lead["product"] and lead["product"] not in prods:
            prods.append(lead["product"])
        product = c9.selectbox("Product", [""] + prods, accept_new_options=True,
                               index=([""] + prods).index(lead["product"]))
        req = c10.text_input("Quantity / requirement", lead["requirement"])
        notes = st.text_area("Notes", lead["notes"], height=70)
        owner = st.selectbox("Salesperson", list(owners), format_func=owners.get,
                             index=list(owners).index(cur_owner) if cur_owner in owners else 0,
                             disabled=user["role"] == "sales")
        if st.form_submit_button("Save changes", type="primary"):
            if not name.strip() or len(clean_phone(phone)) < 10:
                st.error("Contact person and a 10-digit phone are required.")
                return
            dup = find_duplicates(phone, exclude_id=lid)
            dup = dup[dup["company"] == company]
            if not dup.empty:
                st.warning(f"Note: this phone is also on lead #{int(dup.iloc[0]['id'])} "
                           f"({dup.iloc[0]['name']}) for {company}.")
            fields = {"name": name.strip(), "firm": firm.strip(), "phone": phone,
                      "alt_phone": alt, "email": email.strip(), "city": city.strip(),
                      "company": company, "source": source or "", "product": product or "",
                      "requirement": req.strip(), "notes": notes.strip()}
            if user["role"] != "sales" and owner is not None:
                fields["assigned_to"] = int(owner)
            update_lead(lid, user, fields, old=lead)
            st.session_state["flash"] = "Lead details saved."
            st.rerun()
