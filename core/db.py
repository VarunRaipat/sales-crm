"""
Database layer.

Uses Supabase (REST) when SUPABASE_URL / SUPABASE_KEY are in
.streamlit/secrets.toml. Without them it falls back to a local SQLite file
(local.db) so the app can be tried before Supabase is set up.

All access goes through four primitives: db_select / db_insert / db_update /
db_delete. Filters are either a dict {col: value} (equality) or a list of
(col, op, value) with op in eq, neq, gt, gte, lt, lte, in.
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

TIMEOUT = 20
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SQLITE_PATH = os.environ.get("CRM_SQLITE") or os.path.join(_ROOT, "local.db")
_BOOL_COLS = {"active", "must_change"}


# ─────────────────────────── backend choice ───────────────────────────
def _creds():
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        url = key = ""
    return (url or "").rstrip("/"), (key or "")


def using_supabase():
    if os.environ.get("CRM_SQLITE"):   # tests: never touch live data
        return False
    u, k = _creds()
    return bool(u and k)


# ─────────────────────────── helpers ───────────────────────────
def now_utc():
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(dt):
    """Always store timestamps as UTC 'YYYY-MM-DDTHH:MM:SS+00:00'."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _norm_filters(filters):
    if not filters:
        return []
    if isinstance(filters, dict):
        return [(c, "eq", v) for c, v in filters.items()]
    return list(filters)


def _clean_row(r):
    for c in _BOOL_COLS:
        if c in r and r[c] is not None:
            r[c] = bool(r[c])
    return r


# ─────────────────────────── Supabase ───────────────────────────
@st.cache_resource
def _session():
    s = requests.Session()
    s.mount("https://", requests.adapters.HTTPAdapter(
        pool_connections=4, pool_maxsize=8, max_retries=1))
    return s


def _headers(prefer=None):
    _, k = _creds()
    h = {"apikey": k, "Authorization": f"Bearer {k}",
         "Content-Type": "application/json"}
    if prefer:
        h["Prefer"] = prefer
    return h


def _url(table):
    u, _ = _creds()
    return f"{u}/rest/v1/{table}"


def _fmt(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _sb_params(filters):
    out = []
    for c, op, v in _norm_filters(filters):
        if op == "in":
            out.append((c, "in.(" + ",".join(_fmt(x) for x in v) + ")"))
        elif v is None:
            out.append((c, "is.null" if op == "eq" else "not.is.null"))
        else:
            out.append((c, f"{op}.{_fmt(v)}"))
    return out


def _check(r):
    if r.status_code >= 300:
        raise RuntimeError(f"Database error {r.status_code}: {r.text[:300]}")


# ─────────────────────────── SQLite ───────────────────────────
_SQLITE_SCHEMA = """
create table if not exists users (
  id integer primary key autoincrement,
  username text unique not null,
  name text not null,
  password text not null,
  role text not null default 'sales',
  phone text default '',
  manager_id integer references users(id),
  active integer not null default 1,
  must_change integer not null default 1,
  created_at text
);
create table if not exists leads (
  id integer primary key autoincrement,
  company text not null,
  name text not null,
  firm text default '',
  phone text default '',
  alt_phone text default '',
  email text default '',
  city text default '',
  source text default '',
  product text default '',
  requirement text default '',
  value real default 0,
  stage text not null default 'New',
  lost_reason text default '',
  assigned_to integer references users(id),
  created_by integer references users(id),
  next_followup_at text,
  last_contact_at text,
  closed_at text,
  notes text default '',
  created_at text,
  updated_at text
);
create index if not exists leads_owner on leads(assigned_to);
create index if not exists leads_phone on leads(phone);
create table if not exists activities (
  id integer primary key autoincrement,
  lead_id integer not null references leads(id) on delete cascade,
  user_id integer references users(id),
  kind text not null,
  note text default '',
  stage_from text default '',
  stage_to text default '',
  next_followup_at text,
  created_at text
);
create index if not exists act_lead on activities(lead_id);
create table if not exists app_settings (
  key text primary key,
  value text
);
"""
_SQ_LOCK = threading.Lock()
_SQ_OPS = {"eq": "=", "neq": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
_SQ_READY = []


def _sq():
    con = sqlite3.connect(_SQLITE_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("pragma foreign_keys = on")
    if not _SQ_READY:
        con.executescript(_SQLITE_SCHEMA)
        _SQ_READY.append(True)
    return con


def _sq_where(filters):
    parts, params = [], []
    for c, op, v in _norm_filters(filters):
        if op == "in":
            if not v:
                parts.append("0")
                continue
            parts.append(f"{c} in ({','.join('?' * len(v))})")
            params.extend(v)
        elif v is None:
            parts.append(f"{c} is null" if op == "eq" else f"{c} is not null")
        else:
            parts.append(f"{c} {_SQ_OPS[op]} ?")
            params.append(v)
    return (" where " + " and ".join(parts)) if parts else "", params


# ─────────────────────────── primitives ───────────────────────────
def db_select(table, filters=None, order=None):
    flt = _norm_filters(filters)
    if any(op == "in" and not v for _, op, v in flt):
        return []
    if using_supabase():
        rows, start, page = [], 0, 1000
        params = _sb_params(flt) + [("select", "*")]
        if order:
            params.append(("order", order))
        while True:
            h = _headers()
            h["Range"] = f"{start}-{start + page - 1}"
            r = _session().get(_url(table), params=params, headers=h,
                               timeout=TIMEOUT)
            _check(r)
            chunk = r.json()
            rows.extend(chunk)
            if len(chunk) < page:
                break
            start += page
        return [_clean_row(x) for x in rows]
    where, params = _sq_where(flt)
    sql = f"select * from {table}{where}"
    if order:
        col, _, direction = order.partition(".")
        sql += f" order by {col} {'desc' if direction == 'desc' else 'asc'}"
    with _SQ_LOCK:
        con = _sq()
        try:
            return [_clean_row(dict(r)) for r in con.execute(sql, params)]
        finally:
            con.close()


def db_insert(table, rows, ignore_conflict_on=None):
    """Insert one dict or a list of dicts; returns the inserted rows.
    ignore_conflict_on="task_id,due_at" silently skips duplicates."""
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return []
    if using_supabase():
        out = []
        for i in range(0, len(rows), 500):
            chunk = rows[i:i + 500]
            params = {}
            prefer = "return=representation"
            if ignore_conflict_on:
                params["on_conflict"] = ignore_conflict_on
                prefer = "resolution=ignore-duplicates,return=representation"
            r = _session().post(_url(table), params=params, json=chunk,
                                headers=_headers(prefer), timeout=TIMEOUT)
            _check(r)
            out.extend(r.json() or [])
        _touch(table)
        return [_clean_row(x) for x in out]
    out = []
    with _SQ_LOCK:
        con = _sq()
        try:
            for row in rows:
                cols = list(row.keys())
                verb = "insert or ignore" if ignore_conflict_on else "insert"
                cur = con.execute(
                    f"{verb} into {table} ({','.join(cols)}) values "
                    f"({','.join('?' * len(cols))})", [row[c] for c in cols])
                if cur.rowcount:
                    got = con.execute(f"select * from {table} where rowid = ?",
                                      (cur.lastrowid,)).fetchone()
                    out.append(_clean_row(dict(got)))
            con.commit()
        finally:
            con.close()
    _touch(table)
    return out


def db_update(table, filters, data):
    flt = _norm_filters(filters)
    if not flt:
        raise ValueError("Refusing to update without a filter")
    if using_supabase():
        r = _session().patch(_url(table), params=_sb_params(flt), json=data,
                             headers=_headers("return=minimal"), timeout=TIMEOUT)
        _check(r)
    else:
        where, params = _sq_where(flt)
        cols = list(data.keys())
        with _SQ_LOCK:
            con = _sq()
            try:
                con.execute(f"update {table} set "
                            + ",".join(f"{c} = ?" for c in cols) + where,
                            [data[c] for c in cols] + params)
                con.commit()
            finally:
                con.close()
    _touch(table)


def db_delete(table, filters):
    flt = _norm_filters(filters)
    if not flt:
        raise ValueError("Refusing to delete without a filter")
    if using_supabase():
        r = _session().delete(_url(table), params=_sb_params(flt),
                              headers=_headers("return=minimal"),
                              timeout=TIMEOUT)
        _check(r)
    else:
        where, params = _sq_where(flt)
        with _SQ_LOCK:
            con = _sq()
            try:
                con.execute(f"delete from {table}{where}", params)
                con.commit()
            finally:
                con.close()
    _touch(table)


# ─────────────────────────── caching ───────────────────────────
# Cached reads are cleared whenever their table is written. Streamlit runs
# one server process, so a save by any user clears the cache for everyone.
_CACHE_DEPS = []


def cached(*tables, ttl=300):
    def deco(fn):
        f = st.cache_data(ttl=ttl, show_spinner=False)(fn)
        _CACHE_DEPS.append((f, set(tables)))
        return f
    return deco


def _touch(table):
    for f, deps in _CACHE_DEPS:
        if table in deps:
            f.clear()


def clear_all_caches():
    st.cache_data.clear()


# ─────────────────────────── settings ───────────────────────────
def get_setting(key):
    rows = db_select("app_settings", {"key": key})
    return rows[0]["value"] if rows else None


def set_setting(key, value):
    if db_select("app_settings", {"key": key}):
        db_update("app_settings", {"key": key}, {"value": value})
    else:
        db_insert("app_settings", {"key": key, "value": value})


# ─────────────────────────── passwords ───────────────────────────
PBKDF2_ITERATIONS = 200_000
DEFAULT_ADMIN_PW = "changeme"


def hash_password(pw):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt),
                             PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk.hex()}"


def verify_password(stored, pw):
    try:
        _, iters, salt, h = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt),
                                 int(iters))
        return hmac.compare_digest(dk.hex(), h)
    except Exception:
        return False


def password_problem(pw):
    if len(pw or "") < 6:
        return "Password must be at least 6 characters."
    return None


# ─────────────────────────── users ───────────────────────────
def init_db():
    """Create the first admin if the users table is empty."""
    if not db_select("users"):
        db_insert("users", {
            "username": "admin", "name": "Admin",
            "password": hash_password(DEFAULT_ADMIN_PW), "role": "admin",
            "phone": "", "active": True, "must_change": True,
            "created_at": iso(now_utc()),
        })


def authenticate(username, pw):
    rows = db_select("users", {"username": (username or "").strip().lower()})
    if not rows:
        verify_password("pbkdf2_sha256$1$00$00", pw)   # similar timing
        return None
    u = rows[0]
    if not u.get("active") or not verify_password(u["password"], pw):
        return None
    u.pop("password", None)
    return u


@cached("users")
def users_df():
    rows = db_select("users", order="name.asc")
    for r in rows:
        r.pop("password", None)
    cols = ["id", "username", "name", "role", "phone", "manager_id",
            "active", "must_change", "created_at"]
    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df["manager_id"] = df["manager_id"].astype("Int64")
        df["phone"] = df["phone"].fillna("")
    return df


def user_names():
    df = users_df()
    return {int(k): v for k, v in zip(df["id"], df["name"])}


def insert_user(username, name, pw, role, phone="", manager_id=None):
    username = username.strip().lower()
    if db_select("users", {"username": username}):
        raise ValueError(f"User ID '{username}' is already taken.")
    db_insert("users", {
        "username": username, "name": name.strip(),
        "password": hash_password(pw), "role": role,
        "phone": phone.strip(), "manager_id": manager_id,
        "active": True, "must_change": True,
        "created_at": iso(now_utc()),
    })
def update_user(uid, **fields):
    if "password" in fields:
        fields["password"] = hash_password(fields["password"])
    db_update("users", {"id": int(uid)}, fields)


def change_own_password(uid, old_pw, new_pw):
    rows = db_select("users", {"id": int(uid)})
    if not rows or not verify_password(rows[0]["password"], old_pw):
        return "Current password is wrong."
    prob = password_problem(new_pw)
    if prob:
        return prob
    db_update("users", {"id": int(uid)},
              {"password": hash_password(new_pw), "must_change": False})
    return None


def fresh_user(uid):
    rows = db_select("users", {"id": int(uid)})
    if not rows:
        return None
    u = rows[0]
    u.pop("password", None)
    return u
