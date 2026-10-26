"""Dropdown lists the admin can edit (stored as JSON in app_settings).

The values in core/config.py are only the starting lists.
"""
import json

from core import config
from core.db import cached, get_setting, set_setting, db_update

KEY = "dropdowns"

# list name -> (title, help, column in leads that stores it)
LISTS = {
    "companies": ("Companies", "Businesses a lead can belong to.", "company"),
    "products": ("Products", "Product choices, separate for each company.", "product"),
    "sources": ("Lead sources", "Where a lead came from.", "source"),
    "lost_reasons": ("Lost reasons", "Why a lead was lost.", "lost_reason"),
    "activity_kinds": ("Follow-up types", "What the salesperson did (call, visit …).", None),
}


def _defaults():
    return {
        "companies": list(config.COMPANIES),
        "products": {c: list(v) for c, v in config.PRODUCTS.items()},
        "sources": list(config.SOURCES),
        "lost_reasons": list(config.LOST_REASONS),
        "activity_kinds": list(config.ACTIVITY_KINDS),
    }


@cached("app_settings")
def get_lists():
    data = _defaults()
    raw = get_setting(KEY)
    if raw:
        try:
            saved = json.loads(raw)
            for k in data:
                if k in saved:
                    data[k] = saved[k]
        except ValueError:
            pass
    for c in data["companies"]:
        data["products"].setdefault(c, [])
    return data


def save_lists(data):
    set_setting(KEY, json.dumps(data, ensure_ascii=False))


def companies():
    return list(get_lists()["companies"])


def products(company=None):
    p = get_lists()["products"]
    if company:
        return list(p.get(company, []))
    out = []
    for c in companies():
        for x in p.get(c, []):
            if x not in out:
                out.append(x)
    return out


def sources():
    return list(get_lists()["sources"])


def lost_reasons():
    return list(get_lists()["lost_reasons"])


def activity_kinds():
    return list(get_lists()["activity_kinds"])


def rename_in_leads(column, old, new, company=None):
    """Change existing leads so a renamed option stays matched."""
    if not column or not old or old == new:
        return
    flt = {column: old}
    if company and column == "product":
        flt["company"] = company
    db_update("leads", flt, {column: new})
