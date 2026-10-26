from datetime import timedelta

import pandas as pd
import streamlit as st

from core.config import COMPANIES, OPEN_STAGES
from core.db import user_names
from core.leads import visible_leads, activities_df, followup_buckets, start_of_today
from core.ui import rupees

PERIODS = ["This month", "Last month", "Last 7 days", "Last 30 days", "This year", "All time"]


def _range(p):
    sod = start_of_today()
    end = sod + timedelta(days=1)
    first = sod.replace(day=1)
    if p == "This month":
        return first, end
    if p == "Last month":
        prev = (first - timedelta(days=1)).replace(day=1)
        return prev, first
    if p == "Last 7 days":
        return sod - timedelta(days=6), end
    if p == "Last 30 days":
        return sod - timedelta(days=29), end
    if p == "This year":
        return sod.replace(month=1, day=1), end
    return None, None


def _between(s, a, b):
    if a is None:
        return s.notna()
    return (s >= a) & (s < b)


def _conv(won, lost):
    return f"{won / (won + lost) * 100:.0f}%" if won + lost else "—"


def render(user):
    st.title("📊 Dashboard")
    names = user_names()
    df = visible_leads(user)
    c1, c2 = st.columns(2)
    period = c1.selectbox("Period", PERIODS, key="db_period")
    comp = c2.multiselect("Company", COMPANIES, placeholder="All companies", key="db_comp")
    if comp:
        df = df[df["company"].isin(comp)]
    a, b = _range(period)

    new = df[_between(df["created_at"], a, b)]
    closed = df[_between(df["closed_at"], a, b)]
    won = closed[closed["stage"] == "Won"]
    lost = closed[closed["stage"] == "Lost"]
    openl = df[df["stage"].isin(OPEN_STAGES)]
    bk = followup_buckets(df)

    m = st.columns(4)
    m[0].metric("New leads", len(new))
    m[1].metric("Won", len(won), help="Leads marked Won in this period")
    m[2].metric("Won value", rupees(won["value"].sum()))
    m[3].metric("Win rate", _conv(len(won), len(lost)), help="Won ÷ (Won + Lost) in this period")
    m = st.columns(4)
    m[0].metric("Open leads", len(openl), help="Right now, any period")
    m[1].metric("Open value", rupees(openl["value"].sum()))
    m[2].metric("🔴 Overdue follow-ups", len(bk["overdue"]))
    m[3].metric("Lost", len(lost))

    st.subheader("Pipeline right now")
    st.caption("Number of open leads in each stage (all dates).")
    pipe = pd.crosstab(openl["stage"], openl["company"]).reindex(
        index=OPEN_STAGES, columns=comp or COMPANIES, fill_value=0)
    pipe["Total"] = pipe.sum(axis=1)
    val = openl.groupby("stage")["value"].sum().reindex(OPEN_STAGES, fill_value=0)
    pipe["Value"] = val.map(rupees)
    st.dataframe(pipe.rename_axis("Stage").reset_index(), hide_index=True, width="stretch")

    st.subheader("Salespeople")
    acts = activities_df()
    acts = acts[acts["lead_id"].isin(set(int(i) for i in df["id"]))
                & ~acts["kind"].isin(["Created", "Reassigned"])]
    acts = acts[_between(acts["created_at"], a, b)]
    people = sorted({int(i) for i in df["assigned_to"].dropna()}, key=lambda i: names.get(i, "").lower())
    rows = []
    for pid in people:
        mine = df[df["assigned_to"] == pid]
        mc = closed[closed["assigned_to"] == pid]
        w, l_ = int((mc["stage"] == "Won").sum()), int((mc["stage"] == "Lost").sum())
        rows.append({
            "Salesperson": names.get(pid, "?"),
            "Open leads": int(mine["stage"].isin(OPEN_STAGES).sum()),
            "Overdue": int((bk["overdue"]["assigned_to"] == pid).sum()),
            "No date": int((bk["nodate"]["assigned_to"] == pid).sum()),
            "New": int((new["assigned_to"] == pid).sum()),
            "Follow-ups done": int((acts["user_id"] == pid).sum()),
            "Won": w,
            "Won value": rupees(mc.loc[mc["stage"] == "Won", "value"].sum()),
            "Lost": l_,
            "Win rate": _conv(w, l_),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"Salesperson": st.column_config.TextColumn(pinned=True)})
    else:
        st.caption("No leads yet.")

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Where leads come from")
        if new.empty:
            st.caption("No new leads in this period.")
        else:
            src = new.assign(source=new["source"].replace("", "Not given"))
            t = src.groupby("source").agg(Leads=("id", "count")).sort_values("Leads", ascending=False)
            t["Won so far"] = src[src["stage"] == "Won"].groupby("source")["id"].count() \
                .reindex(t.index, fill_value=0)
            st.dataframe(t.rename_axis("Source").reset_index(), hide_index=True, width="stretch")
    with c2:
        st.subheader("Why leads were lost")
        if lost.empty:
            st.caption("No lost leads in this period.")
        else:
            t = lost.assign(r=lost["lost_reason"].replace("", "Not given")) \
                .groupby("r").agg(Leads=("id", "count")).sort_values("Leads", ascending=False)
            st.dataframe(t.rename_axis("Reason").reset_index(), hide_index=True, width="stretch")
