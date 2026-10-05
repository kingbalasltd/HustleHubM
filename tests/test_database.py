import sqlite3

import database


def test_old_database_is_upgraded(tmp_path, monkeypatch):
    path = str(tmp_path / "old.db")

    # The table exactly as the first version created it.
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL, website TEXT, email TEXT,
            industry TEXT, location TEXT, lead_score INTEGER DEFAULT 0,
            opportunity TEXT, status TEXT DEFAULT 'New',
            email_subject TEXT, email_body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("INSERT INTO leads (business_name, lead_score) VALUES ('Old Lead', 40)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(database, "DATABASE", path)
    database.init_db()

    leads = database.get_leads()

    assert [lead["business_name"] for lead in leads] == ["Old Lead"]
    assert "phone" in leads[0].keys()


def test_add_update_and_filter(temp_db):
    lead_id = database.add_lead(
        "Smile Dental",
        website="https://www.smile.co.za/",
        email="info@smile.co.za",
        lead_score=55,
        email_subject="Hi",
        email_body="Body",
        phone="011 123 4567",
        not_a_column="ignored",
    )

    lead = database.get_lead(lead_id)

    assert lead["email_subject"] == "Hi"
    assert lead["phone"] == "011 123 4567"

    database.update_lead(lead_id, status="Contacted", contacted_at=database.now())

    assert database.get_leads("New") == []
    assert len(database.get_leads()) == 1
    assert database.count_by_status()["Contacted"] == 1
    assert database.count_contacted_today() == 1


def test_hidden_statuses_are_not_active(temp_db):
    database.add_lead("Directory", status="Rejected")
    database.add_lead("Low", status="Skipped")

    assert database.get_leads() == []
    assert len(database.get_leads("all")) == 2


def test_existing_lead_matches_domain_or_name(temp_db):
    database.add_lead("Smile Dental", website="https://www.smile.co.za/")

    assert database.find_existing_lead("http://smile.co.za/about", "Other")
    assert database.find_existing_lead("", "smile dental ")
    assert database.find_existing_lead("https://other.co.za/", "Other") is None


def test_do_not_contact(temp_db):
    database.add_do_not_contact("Info@Smile.co.za", "smile.co.za")

    assert database.is_do_not_contact(email="info@smile.co.za")
    assert database.is_do_not_contact(website="https://www.smile.co.za/")
    assert database.is_do_not_contact(email="reception@smile.co.za")
    assert not database.is_do_not_contact(email="info@other.co.za")


def test_settings(temp_db):
    database.save_settings({"sender_name": " Madjer ", "unknown": "x"})

    settings = database.get_settings()

    assert settings["sender_name"] == "Madjer"
    assert settings["sender_company"] == "HustleHubM"
    assert "unknown" not in settings
