"""Leads and their follow-up history."""
import re
from datetime import datetime, time, timedelta

import pandas as pd

from core.config import IST, OPEN_STAGES, CLOSED_STAGES
from core.db import db_select, db_insert, db_update, cached, now_utc, iso

LEAD_COLS = ["id", "company", "name", "firm", "phone", "alt_phone", "email", "city",
             "source", "product", "requirement", "value", "stage", "lost_reason",
             "assigned_to", "created_by", "next_followup_at", "last_contact_at",
             "closed_at", "notes", "created_at", "updated_at"]
TEXT_COLS = ["company", "name", "firm", "phone", "alt_phone", "email", "city", "source",
             "product", "requirement", "stage", "lost_reason", "notes"]
TIME_COLS = ["next_followup_at", "last_contact_at", "closed_at", "created_at", "updated_at"]
ACT_COLS = ["id", "lead_id", "user_id", "kind", "note", "stage_from", "stage_to",
            "next_followup_at", "created_at"]


def clean_phone(p):
    """Keep the last 10 digits (drops +91 / 0 prefixes and spaces)."""
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) > 10 else d


def now_ist():
    return datetime.now(IST)


def start_of_today():
    n = now_ist()
    return n.replace(hour=0, minute=0, second=0, microsecond=0)


def to_utc_iso(d, t=None):
    """A date (+ optional time) picked in IST → stored UTC string."""
    if d is None:
        return None
    t = t or time(11, 0)
    return iso(datetime.combine(d, t, tzinfo=IST))


def _times(s):
    return pd.to_datetime(s, utc=True, errors="coerce", format="ISO8601").dt.tz_convert(IST)


@cached("leads")
def leads_df():
    df = pd.DataFrame(db_select("leads", order="id.desc"), columns=LEAD_COLS)
    for c in TEXT_COLS:
        df[c] = df[c].fillna("").astype(str)
    for c in TIME_COLS:
        df[c] = _times(df[c])
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    for c in ("id", "assigned_to", "created_by"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df


@cached("activities")
def activities_df():
    df = pd.DataFrame(db_select("activities", order="id.desc"), columns=ACT_COLS)
    for c in ("kind", "note", "stage_from", "stage_to"):
        df[c] = df[c].fillna("").astype(str)
    for c in ("next_followup_at", "created_at"):
        df[c] = _times(df[c])
    for c in ("id", "lead_id", "user_id"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df


def visible_leads(user):
    from core.scope import team_ids
    df = leads_df()
    if user["role"] == "admin":
        return df
    return df[df["assigned_to"].isin(team_ids(user))]


def lead_by_id(lead_id):
    df = leads_df()
    hit = df[df["id"] == int(lead_id)]
    return hit.iloc[0].to_dict() if not hit.empty else None


def find_duplicates(phone, exclude_id=None):
    p = clean_phone(phone)
    if len(p) < 6:
        return pd.DataFrame(columns=LEAD_COLS)
    df = leads_df()
    hit = df[(df["phone"] == p) | (df["alt_phone"] == p)]
    if exclude_id is not None:
        hit = hit[hit["id"] != int(exclude_id)]
    return hit


def add_lead(data, user, followup_at=None):
    """data: lead fields. followup_at: UTC iso string or None."""
    now = iso(now_utc())
    row = {c: data.get(c, "") for c in TEXT_COLS if c not in ("stage", "lost_reason")}
    row.update({
        "phone": clean_phone(data.get("phone")),
        "alt_phone": clean_phone(data.get("alt_phone")),
        "value": float(data.get("value") or 0),
        "stage": data.get("stage") or "New",
        "lost_reason": "",
        "assigned_to": data.get("assigned_to") or int(user["id"]),
        "created_by": int(user["id"]),
        "next_followup_at": followup_at,
        "created_at": data.get("created_at") or now,
        "updated_at": now,
    })
    for k in ("name", "firm", "city", "email", "requirement", "notes", "product"):
        row[k] = str(row.get(k) or "").strip()
    saved = db_insert("leads", row)[0]
    db_insert("activities", {
        "lead_id": saved["id"], "user_id": int(user["id"]), "kind": "Created",
        "note": "Lead added" + (f" — {row['notes']}" if row["notes"] else ""),
        "stage_from": "", "stage_to": row["stage"],
        "next_followup_at": followup_at, "created_at": now,
    })
    return saved


def log_followup(lead, user, kind, note, stage, followup_at=None, lost_reason="",
                 value=None):
    """Record what happened on a lead and set the next follow-up."""
    now = iso(now_utc())
    closed = stage in CLOSED_STAGES
    nxt = None if closed else followup_at
    db_insert("activities", {
        "lead_id": int(lead["id"]), "user_id": int(user["id"]), "kind": kind,
        "note": note.strip(), "stage_from": lead["stage"], "stage_to": stage,
        "next_followup_at": nxt, "created_at": now,
    })
    upd = {"stage": stage, "next_followup_at": nxt, "updated_at": now,
           "lost_reason": lost_reason if stage == "Lost" else ""}
    if kind != "Note":
        upd["last_contact_at"] = now
    if value is not None:
        upd["value"] = float(value)
    if closed and lead["stage"] not in CLOSED_STAGES:
        upd["closed_at"] = now
    elif not closed:
        upd["closed_at"] = None
    db_update("leads", {"id": int(lead["id"])}, upd)


def update_lead(lead_id, user, fields, old=None):
    """Edit lead details. A change of owner is written to the history."""
    fields = dict(fields)
    for k in ("phone", "alt_phone"):
        if k in fields:
            fields[k] = clean_phone(fields[k])
    fields["updated_at"] = iso(now_utc())
    db_update("leads", {"id": int(lead_id)}, fields)
    if old is not None and "assigned_to" in fields and \
            pd.notna(old.get("assigned_to")) and int(old["assigned_to"]) != int(fields["assigned_to"]):
        from core.db import user_names
        n = user_names()
        db_insert("activities", {
            "lead_id": int(lead_id), "user_id": int(user["id"]), "kind": "Reassigned",
            "note": f"{n.get(int(old['assigned_to']), '?')} → {n.get(int(fields['assigned_to']), '?')}",
            "stage_from": old["stage"], "stage_to": old["stage"],
            "next_followup_at": None, "created_at": fields["updated_at"],
        })


def followup_buckets(df):
    """Split open leads into overdue / today / upcoming (7 days) / no date."""
    op = df[df["stage"].isin(OPEN_STAGES)]
    nf = op["next_followup_at"]
    sod = start_of_today()
    eod = sod + timedelta(days=1)
    return {
        "overdue": op[nf < sod].sort_values("next_followup_at"),
        "today": op[(nf >= sod) & (nf < eod)].sort_values("next_followup_at"),
        "upcoming": op[(nf >= eod) & (nf < sod + timedelta(days=8))].sort_values("next_followup_at"),
        "later": op[nf >= sod + timedelta(days=8)].sort_values("next_followup_at"),
        "nodate": op[nf.isna()],
    }
