import os
import sqlite3
from datetime import date, datetime

from dotenv import load_dotenv

load_dotenv()

# Keep the database next to the code, whatever folder you run from.
DATABASE = os.getenv(
    "HUSTLEHUB_DB",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.db")
)


STATUSES = [
    "New",
    "Contacted",
    "Replied",
    "Won",
    "Not interested",
    "Do not contact",
    "Skipped",
    "Rejected",
]

# What the dashboard shows by default.
ACTIVE_STATUSES = ["New", "Contacted", "Replied", "Won"]


# Columns added after the first version. init_db() adds any that
# are missing, so an old leads.db keeps its leads.
NEW_COLUMNS = {
    "phone": "TEXT",
    "whatsapp": "TEXT",
    "email_status": "TEXT",
    "qualification": "TEXT",
    "signals": "TEXT",
    "ai_reason": "TEXT",
    "source": "TEXT",
    "notes": "TEXT",
    "contacted_at": "TIMESTAMP",
    "updated_at": "TIMESTAMP",
}

LEAD_FIELDS = {
    "business_name",
    "website",
    "email",
    "industry",
    "location",
    "lead_score",
    "opportunity",
    "status",
    "email_subject",
    "email_body",
    *NEW_COLUMNS,
}


DEFAULT_SETTINGS = {
    "sender_name": os.getenv("SENDER_NAME", ""),
    "sender_company": os.getenv("SENDER_COMPANY", "HustleHubM"),
    "sender_contact": os.getenv("SENDER_CONTACT", ""),
    "daily_send_limit": os.getenv("DAILY_SEND_LIMIT", "20"),
    "default_country_code": os.getenv("DEFAULT_COUNTRY_CODE", "27"),
}


def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def now():
    return datetime.now().isoformat(" ", "seconds")


def init_db():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            website TEXT,
            email TEXT,
            industry TEXT,
            location TEXT,
            lead_score INTEGER DEFAULT 0,
            opportunity TEXT,
            status TEXT DEFAULT 'New',
            email_subject TEXT,
            email_body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(leads)")
    }

    for column, column_type in NEW_COLUMNS.items():
        if column not in existing:
            conn.execute(
                f"ALTER TABLE leads ADD COLUMN {column} {column_type}"
            )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS do_not_contact (
            value TEXT PRIMARY KEY,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    conn.commit()
    conn.close()


def add_lead(
    business_name,
    website="",
    email="",
    industry="",
    location="",
    lead_score=0,
    opportunity="",
    **extra
):
    fields = {
        "business_name": business_name,
        "website": website,
        "email": email,
        "industry": industry,
        "location": location,
        "lead_score": lead_score,
        "opportunity": opportunity,
        "updated_at": now(),
    }

    fields.update(
        (key, value)
        for key, value in extra.items()
        if key in LEAD_FIELDS
    )

    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)

    conn = get_connection()

    cursor = conn.execute(
        f"INSERT INTO leads ({columns}) VALUES ({placeholders})",
        list(fields.values())
    )

    conn.commit()
    conn.close()

    return cursor.lastrowid


def get_leads(status=None):
    """status=None -> active leads, "all" -> everything,
    anything else -> just that status."""

    conn = get_connection()

    if status == "all":
        leads = conn.execute("""
            SELECT * FROM leads
            ORDER BY lead_score DESC, id DESC
        """).fetchall()

    else:
        statuses = [status] if status else ACTIVE_STATUSES
        placeholders = ", ".join("?" for _ in statuses)

        leads = conn.execute(f"""
            SELECT * FROM leads
            WHERE COALESCE(status, 'New') IN ({placeholders})
            ORDER BY lead_score DESC, id DESC
        """, statuses).fetchall()

    conn.close()

    return leads


def get_lead(lead_id):
    conn = get_connection()

    lead = conn.execute(
        "SELECT * FROM leads WHERE id = ?",
        (lead_id,)
    ).fetchone()

    conn.close()

    return lead


def update_lead(lead_id, **fields):
    fields = {
        key: value
        for key, value in fields.items()
        if key in LEAD_FIELDS
    }

    if not fields:
        return

    fields["updated_at"] = now()

    assignments = ", ".join(f"{key} = ?" for key in fields)

    conn = get_connection()

    conn.execute(
        f"UPDATE leads SET {assignments} WHERE id = ?",
        [*fields.values(), lead_id]
    )

    conn.commit()
    conn.close()


def delete_lead(lead_id):
    conn = get_connection()
    conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()


def count_by_status():
    conn = get_connection()

    rows = conn.execute("""
        SELECT COALESCE(status, 'New') AS status, COUNT(*) AS total
        FROM leads
        GROUP BY COALESCE(status, 'New')
    """).fetchall()

    conn.close()

    counts = {status: 0 for status in STATUSES}

    for row in rows:
        counts[row["status"]] = row["total"]

    return counts


def count_contacted_today():
    conn = get_connection()

    total = conn.execute(
        "SELECT COUNT(*) FROM leads WHERE date(contacted_at) = ?",
        (date.today().isoformat(),)
    ).fetchone()[0]

    conn.close()

    return total


def normalize_domain(url):
    from urllib.parse import urlparse

    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    domain = urlparse(url).netloc.lower().split(":")[0]
    return domain.removeprefix("www.")


def find_existing_lead(website, business_name):
    new_domain = normalize_domain(website)
    new_name = (business_name or "").strip().lower()

    conn = get_connection()

    rows = conn.execute(
        "SELECT id, website, business_name FROM leads"
    ).fetchall()

    conn.close()

    for row in rows:

        if new_domain and normalize_domain(row["website"]) == new_domain:
            return row

        existing_name = (row["business_name"] or "").strip().lower()

        if new_name and existing_name == new_name:
            return row

    return None


def add_do_not_contact(*values):
    conn = get_connection()

    for value in values:
        value = (value or "").strip().lower()

        if value:
            conn.execute(
                "INSERT OR IGNORE INTO do_not_contact (value) VALUES (?)",
                (value,)
            )

    conn.commit()
    conn.close()


def is_do_not_contact(email="", website=""):
    values = [
        (email or "").strip().lower(),
        normalize_domain(website),
    ]

    if email and "@" in email:
        values.append(email.split("@")[1].lower())

    values = [value for value in values if value]

    if not values:
        return False

    placeholders = ", ".join("?" for _ in values)

    conn = get_connection()

    found = conn.execute(
        f"SELECT 1 FROM do_not_contact WHERE value IN ({placeholders})",
        values
    ).fetchone()

    conn.close()

    return found is not None


def get_settings():
    settings = dict(DEFAULT_SETTINGS)

    conn = get_connection()

    for row in conn.execute("SELECT key, value FROM settings"):
        settings[row["key"]] = row["value"]

    conn.close()

    return settings


def save_settings(values):
    conn = get_connection()

    for key, value in values.items():
        if key in DEFAULT_SETTINGS:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, (value or "").strip())
            )

    conn.commit()
    conn.close()
