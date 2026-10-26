"""Bulk-add leads from an Excel / CSV sheet."""
import io
from datetime import time

import pandas as pd
import streamlit as st

from core.config import COMPANIES, STAGES, CLOSED_STAGES, DEFAULT_FOLLOWUP_HOUR
from core.db import users_df
from core.leads import add_lead, clean_phone, leads_df, to_utc_iso
from core.ui import start_of_today

TEMPLATE_COLS = ["Company", "Contact person", "Firm", "Phone", "Other phone", "City",
                 "Source", "Product", "Requirement", "Value", "Salesperson user ID",
                 "Next follow-up", "Stage", "Notes"]
# header in the sheet (lower-case, any of these) -> field
ALIASES = {
    "company": ["company", "vertical", "business"],
    "name": ["contact person", "name", "contact", "customer", "customer name", "party"],
    "firm": ["firm", "firm / project", "project", "company name", "organisation", "organization"],
    "phone": ["phone", "mobile", "mobile no", "phone no", "contact no", "number"],
    "alt_phone": ["other phone", "alt phone", "alternate phone", "phone 2"],
    "city": ["city", "area", "location", "city / area", "address"],
    "source": ["source", "lead source"],
    "product": ["product", "item"],
    "requirement": ["requirement", "quantity", "qty"],
    "value": ["value", "expected value", "amount"],
    "owner": ["salesperson user id", "salesperson", "assigned to", "owner"],
    "next": ["next follow-up", "follow-up", "follow up", "followup", "next followup"],
    "stage": ["stage", "status"],
    "notes": ["notes", "remarks", "remark", "comments"],
}


def _template():
    buf = io.BytesIO()
    pd.DataFrame([{
        "Company": "ECO", "Contact person": "Ramesh Kumar", "Firm": "Shiv Constructions",
        "Phone": "9876543210", "Other phone": "", "City": "Ranchi", "Source": "Reference",
        "Product": "Paver blocks", "Requirement": "5000 sq ft", "Value": 250000,
        "Salesperson user ID": "", "Next follow-up": "30/10/2026", "Stage": "New",
        "Notes": "",
    }], columns=TEMPLATE_COLS).to_excel(buf, index=False)
    return buf.getvalue()


def _read(f):
    if f.name.lower().endswith(".csv"):
        return pd.read_csv(f, dtype=str).fillna("")
    return pd.read_excel(f, dtype=str).fillna("")


def _map_cols(df):
    low = {c.strip().lower(): c for c in df.columns}
    out = {}
    for field, names in ALIASES.items():
        for n in names:
            if n in low:
                out[field] = low[n]
                break
    return out


def _company(v):
    v = str(v).strip().lower()
    for c in COMPANIES:
        if v == c.lower():
            return c
    guess = {"eco": "ECO", "ecostructures": "ECO", "pipe": "Pipe", "pipes": "Pipe",
             "bwall": "B Wall", "b-wall": "B Wall", "boundary wall": "B Wall",
             "pratap": "PI", "pratap industries": "PI", "pi": "PI"}
    return guess.get(v.replace("  ", " "), "")


def render(user):
    st.title("📥 Import leads")
    st.write("Add many leads at once from an Excel or CSV sheet. Download the template, "
             "fill one lead per row, then upload it.")
    st.download_button("⬇️ Download template (Excel)", _template(), "crm_leads_template.xlsx")
    st.caption("Needed: **Contact person** and **Phone**. Company can be ECO, Pipe, B Wall "
               "or PI. Salesperson = their user ID (blank = choose below). Next follow-up "
               "as DD/MM/YYYY (blank = today).")

    f = st.file_uploader("Upload sheet", type=["xlsx", "xls", "csv"])
    if not f:
        return
    try:
        raw = _read(f)
    except Exception as ex:
        st.error(f"Couldn't read that file: {ex}")
        return
    cols = _map_cols(raw)
    if "name" not in cols or "phone" not in cols:
        st.error("The sheet needs a 'Contact person' (or 'Name') column and a 'Phone' column.")
        return

    c1, c2 = st.columns(2)
    default_company = c1.selectbox("Company for rows that don't say", COMPANIES)
    u = users_df()
    u = u[u["active"]]
    by_login = {r["username"]: int(r["id"]) for r in u.to_dict("records")}
    people = {int(r["id"]): r["name"] for r in u.to_dict("records")}
    default_owner = c2.selectbox("Salesperson for rows that don't say", list(people),
                                 format_func=people.get,
                                 index=list(people).index(int(user["id"])) if int(user["id"]) in people else 0)

    existing = leads_df()
    have = set(zip(existing["company"], existing["phone"]))
    today = start_of_today().date()
    rows, seen = [], set()
    for i, r in raw.iterrows():
        g = lambda k: str(r[cols[k]]).strip() if k in cols else ""
        name, phone = g("name"), clean_phone(g("phone"))
        company = _company(g("company")) or default_company
        problem = ""
        if not name:
            problem = "No name"
        elif len(phone) != 10:
            problem = "Phone is not 10 digits"
        elif (company, phone) in have:
            problem = "Already in CRM"
        elif (company, phone) in seen:
            problem = "Repeated in sheet"
        owner_login = g("owner").lower()
        owner = by_login.get(owner_login, default_owner)
        if owner_login and owner_login not in by_login:
            owner = next((k for k, v in people.items() if v.lower() == owner_login), default_owner)
        nxt = pd.to_datetime(g("next"), dayfirst=True, errors="coerce") if g("next") else None
        d = nxt.date() if nxt is not None and pd.notna(nxt) else today
        stage = next((s for s in STAGES if s.lower() == g("stage").lower()), "New")
        try:
            value = float(g("value").replace(",", "").replace("₹", "") or 0)
        except ValueError:
            value = 0.0
        seen.add((company, phone))
        rows.append({"Row": i + 2, "Problem": problem, "company": company, "name": name,
                     "firm": g("firm"), "phone": phone, "alt_phone": g("alt_phone"),
                     "city": g("city"), "source": g("source"), "product": g("product"),
                     "requirement": g("requirement"), "value": value, "stage": stage,
                     "notes": g("notes"), "assigned_to": owner, "next": max(d, today)})
    prev = pd.DataFrame(rows)
    good = prev[prev["Problem"] == ""]
    bad = prev[prev["Problem"] != ""]
    st.success(f"{len(good)} leads ready to add.") if len(good) else st.warning("No rows can be added.")
    show = good.assign(Salesperson=good["assigned_to"].map(people))[
        ["company", "name", "firm", "phone", "city", "product", "stage", "Salesperson", "next"]]
    st.dataframe(show.rename(columns={"company": "Company", "name": "Contact", "firm": "Firm",
                                      "phone": "Phone", "city": "City", "product": "Product",
                                      "stage": "Stage", "next": "Next follow-up"}),
                 hide_index=True, width="stretch")
    if len(bad):
        st.warning(f"{len(bad)} rows will be skipped:")
        st.dataframe(bad[["Row", "name", "phone", "Problem"]].rename(
            columns={"name": "Contact", "phone": "Phone"}), hide_index=True, width="stretch")
    if len(good) and st.button(f"Add {len(good)} leads", type="primary"):
        bar = st.progress(0.0)
        for n, r in enumerate(good.to_dict("records"), 1):
            fu = None if r["stage"] in CLOSED_STAGES else                 to_utc_iso(r["next"], time(DEFAULT_FOLLOWUP_HOUR, 0))
            add_lead(r, user, followup_at=fu)
            bar.progress(n / len(good))
        st.success(f"Added {len(good)} leads.")
        st.balloons()
