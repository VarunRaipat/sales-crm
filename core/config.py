"""App-wide settings. Change names, lists and rules here."""
from zoneinfo import ZoneInfo

APP_NAME = "Sales CRM"
TAGLINE = "Every lead. Every follow-up. On time."

IST = ZoneInfo("Asia/Kolkata")

# ── roles ──
ROLES = ["admin", "manager", "sales"]
ROLE_LABELS = {"admin": "Admin", "manager": "Sales manager", "sales": "Salesperson"}

# ── companies / verticals ──
COMPANIES = ["ECO", "Pipe", "B Wall", "PI"]

# Product suggestions per company (salespeople can also type a new one).
PRODUCTS = {
    "ECO": ["Paver blocks", "Concrete blocks", "Fly ash bricks", "Kerb stones", "Grass pavers"],
    "Pipe": ["RCC Hume pipes", "NP2 pipes", "NP3 pipes", "NP4 pipes", "Manhole covers"],
    "B Wall": ["Precast boundary wall", "Wall panels + poles"],
    "PI": ["Breeze blocks (AAKAR)", "U-drains", "Precast products"],
}

# ── pipeline ──
STAGES = ["New", "Contacted", "Interested", "Quotation sent", "Negotiation", "Won", "Lost"]
OPEN_STAGES = STAGES[:5]
CLOSED_STAGES = ["Won", "Lost"]
STAGE_COLORS = {   # (background, text)
    "New": ("#e0f2fe", "#075985"),
    "Contacted": ("#e0e7ff", "#3730a3"),
    "Interested": ("#fef3c7", "#92400e"),
    "Quotation sent": ("#ffedd5", "#9a3412"),
    "Negotiation": ("#fae8ff", "#86198f"),
    "Won": ("#dcfce7", "#166534"),
    "Lost": ("#f3f4f6", "#6b7280"),
}

SOURCES = ["Phone call", "Walk-in", "Reference", "Site visit", "IndiaMART", "Website",
           "WhatsApp", "Dealer", "Tender", "Exhibition", "Other"]
ACTIVITY_KINDS = ["Call", "WhatsApp", "Site visit", "Office meeting", "Email", "Note"]
LOST_REASONS = ["Price too high", "Bought from competitor", "Project cancelled / on hold",
                "Not reachable", "Not interested", "Other"]

DEFAULT_FOLLOWUP_HOUR = 11   # 11:00 AM unless the person picks a time

# ── look ──
BRAND = "#0F766E"
