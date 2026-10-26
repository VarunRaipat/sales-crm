"""Small shared UI helpers."""
import html
from datetime import timedelta

import pandas as pd
import streamlit as st

from core.config import STAGE_COLORS, BRAND
from core.leads import start_of_today

CSS = f"""
<style>
.block-container {{ padding-top: 2.2rem; max-width: 1150px; }}
.lead-title {{ font-weight: 600; font-size: 1.05rem; margin: 0; }}
.lead-meta {{ color: #6b7280; font-size: 0.86rem; margin: 2px 0 0 0; }}
.lead-note {{ font-size: 0.9rem; margin: 6px 0 0 0; }}
.lead-links a {{ display:inline-block; margin: 6px 8px 0 0; padding: 3px 12px;
                border-radius: 999px; border: 1px solid #d1d5db; text-decoration: none;
                font-size: 0.88rem; color: inherit; }}
.pill {{ display:inline-block; padding:1px 9px; border-radius:999px;
         font-size:0.75rem; font-weight:600; margin-right:4px; vertical-align: middle; }}
.due-over {{ color:#b91c1c; font-weight:600; }}
.due-today {{ color:#92400e; font-weight:600; }}
.st-key-mobile_nav {{ display: none; }}
.login-title {{ text-align:center; margin-bottom:0; white-space:nowrap; }}
.topbar {{ display:flex; justify-content:space-between; align-items:baseline;
           margin-bottom: 4px; }}
.topbar b {{ font-size: 1.05rem; color: {BRAND}; }}
.topbar span {{ color:#6b7280; font-size: 0.85rem; }}
.hist {{ border-left: 3px solid #e5e7eb; padding: 2px 0 8px 12px; margin-left: 4px; }}
.hist b {{ font-size: 0.9rem; }}
.hist p {{ margin: 2px 0 0 0; font-size: 0.9rem; }}
.hist small {{ color:#6b7280; }}

/* ---------- phones ---------- */
@media (max-width: 640px) {{
  .block-container {{ padding: 3rem 0.75rem 3rem 0.75rem !important; }}
  [data-testid="stToolbarActions"], [data-testid="stMainMenu"], [data-testid="stDecoration"],
  [data-testid="stAppDeployButton"], footer {{ display:none !important; }}
  h1 {{ font-size: 1.6rem !important; }}
  .login-title {{ font-size: 1.8rem !important; white-space: normal; }}
  h2, h3 {{ font-size: 1.15rem !important; }}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"]) {{
      flex-wrap: wrap !important; gap: 0.5rem !important; }}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stMetric"])
      > [data-testid="stColumn"] {{
      flex: 1 1 calc(50% - 0.5rem) !important; min-width: calc(50% - 0.5rem) !important; }}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3)):has(
      [data-testid="stSelectbox"], [data-testid="stMultiSelect"], [data-testid="stDateInput"]) {{
      flex-wrap: wrap !important; gap: 0.5rem !important; }}
  [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3)):has(
      [data-testid="stSelectbox"], [data-testid="stMultiSelect"], [data-testid="stDateInput"])
      > [data-testid="stColumn"] {{
      flex: 1 1 calc(50% - 0.5rem) !important; min-width: calc(50% - 0.5rem) !important; }}
  [data-testid="stMetric"] {{ background:#f8fafc; border-radius:10px; padding:8px 10px; }}
  [data-testid="stMetricValue"] {{ font-size: 1.4rem !important; }}
  [data-testid="stMetricLabel"] p {{ font-size: 0.8rem !important; }}
  .stButton button, .stDownloadButton button, [data-testid="stPopover"] button,
  [data-testid="stFormSubmitButton"] button {{ min-height: 46px; }}
  .lead-links a {{ padding: 7px 14px; font-size: 0.95rem; }}
  .st-key-mobile_nav {{ display: block; margin-bottom: 0.5rem; }}
  .st-key-mobile_nav [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; }}
  .st-key-mobile_nav [data-testid="stColumn"] {{ min-width: 0 !important; }}
  [data-testid="stButtonGroup"] > div {{ flex-wrap: wrap !important; }}
  .stApp:not(:has([data-testid="stSidebar"])) header[data-testid="stHeader"] {{ display:none; }}
  .stApp:not(:has([data-testid="stSidebar"])) .block-container {{ padding-top: 1rem !important; }}
  .st-key-topnav [data-testid="stButtonGroup"] > div {{ flex-wrap: nowrap !important; }}
  .st-key-topnav [data-testid="stButtonGroup"] button {{ padding: 4px 4px !important; min-height: 44px;
      min-width: 0 !important; flex: 1 1 0 !important; }}
  .st-key-topnav [data-testid="stButtonGroup"] button p {{ font-size: 0.78rem !important;
      white-space: nowrap; }}
}}
</style>
"""

e = html.escape


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def stage_pill(stage):
    bg, fg = STAGE_COLORS.get(stage, ("#e5e7eb", "#374151"))
    return f'<span class="pill" style="background:{bg};color:{fg}">{e(stage)}</span>'


def company_pill(company):
    return (f'<span class="pill" style="background:#f1f5f9;color:#334155">'
            f'{e(company)}</span>') if company else ""


def rupees(v):
    """Indian grouping: 12,34,567."""
    try:
        n = int(round(float(v or 0)))
    except (TypeError, ValueError):
        return "—"
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return ("-" if n < 0 else "") + "₹" + s


def fmt_dt(ts, with_time=True):
    if ts is None or pd.isna(ts):
        return ""
    return ts.strftime("%d %b %Y, %I:%M %p" if with_time else "%d %b %Y")


def due_text(ts):
    """'Overdue 3 days' / 'Today 11:00 AM' / 'Tomorrow 4:00 PM' / 'Fri 31 Oct'."""
    if ts is None or pd.isna(ts):
        return '<span class="due-over">No follow-up date</span>'
    sod = start_of_today()
    days = (ts.replace(hour=0, minute=0, second=0, microsecond=0) - sod).days
    t = ts.strftime("%I:%M %p").lstrip("0")
    if days < 0:
        n = -days
        return f'<span class="due-over">Overdue {n} day{"s" if n > 1 else ""} ({ts:%d %b})</span>'
    if days == 0:
        return f'<span class="due-today">Today {t}</span>'
    if days == 1:
        return f"Tomorrow {t}"
    return f"{ts:%a %d %b}, {t}"


def contact_links(phone, name=""):
    p = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not p:
        return ""
    wa = p if len(p) > 10 else "91" + p
    return (f'<div class="lead-links"><a href="tel:+{wa}">📞 {e(p)}</a>'
            f'<a href="https://wa.me/{wa}" target="_blank">💬 WhatsApp</a></div>')


def lead_header(lead, owner_name=None, show_due=True, last_note=None):
    title = e(lead["name"]) + (f" · {e(lead['firm'])}" if lead.get("firm") else "")
    meta = [e(str(x)) for x in (lead.get("product"), lead.get("city")) if x]
    if lead.get("value"):
        meta.append(rupees(lead["value"]))
    if owner_name:
        meta.append(f"👤 {e(owner_name)}")
    body = (f'<p class="lead-title">{title} {stage_pill(lead["stage"])}'
            f'{company_pill(lead.get("company"))}</p>')
    if show_due:
        body += f'<p class="lead-meta">🗓️ {due_text(lead.get("next_followup_at"))}</p>'
    if meta:
        body += f'<p class="lead-meta">{" · ".join(meta)}</p>'
    if last_note:
        body += f'<p class="lead-note">📝 {e(last_note)}</p>'
    body += contact_links(lead.get("phone"))
    st.markdown(body, unsafe_allow_html=True)


def flash(key="flash"):
    msg = st.session_state.pop(key, None)
    if msg:
        st.success(msg)


def tomorrow():
    return (start_of_today() + timedelta(days=1)).date()
