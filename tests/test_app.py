import pytest

import app as app_module
import database
from website_analyzer import analyze_website


@pytest.fixture
def client(temp_db, monkeypatch):
    monkeypatch.setattr(app_module, "ai_status", lambda: (False, "Ollama is not running"))
    monkeypatch.setattr(
        app_module,
        "check_email_domain",
        lambda email: "valid" if email else "none"
    )
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_dashboard_loads(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Find new leads" in response.data
    assert b"No leads yet" in response.data


def test_add_lead_by_hand_drafts_an_email(client, monkeypatch):
    monkeypatch.setattr(app_module, "analyze_website", lambda url: analyze_website(""))

    response = client.post("/add-lead", data={
        "business_name": "Smile Dental",
        "email": "info@smile.co.za",
        "location": "Sandton",
    })

    assert response.status_code == 302

    lead = database.get_leads()[0]

    assert lead["lead_score"] == 45
    assert lead["email_subject"] == "Website for Smile Dental?"
    assert "I couldn't find a website for your business" in lead["email_body"]

    page = client.get(f"/lead/{lead['id']}")

    assert page.status_code == 200
    assert b"Website for Smile Dental?" in page.data


def test_save_and_mark_contacted(client):
    lead_id = database.add_lead("Smile Dental", email="info@smile.co.za")

    client.post(f"/lead/{lead_id}", data={
        "email": "info@smile.co.za",
        "email_subject": "Edited subject",
        "email_body": "Edited body",
        "action": "contacted",
    })

    lead = database.get_lead(lead_id)

    assert lead["email_subject"] == "Edited subject"
    assert lead["status"] == "Contacted"
    assert lead["contacted_at"]


def test_do_not_contact_button(client):
    lead_id = database.add_lead(
        "Smile Dental",
        website="https://smile.co.za/",
        email="info@smile.co.za"
    )

    client.post(f"/lead/{lead_id}/do-not-contact")

    assert database.get_lead(lead_id)["status"] == "Do not contact"
    assert database.is_do_not_contact(website="https://www.smile.co.za")


def test_whatsapp_number():
    assert app_module.whatsapp_number({"whatsapp": "", "phone": "082 123 4567"}) == "27821234567"
    assert app_module.whatsapp_number({"whatsapp": "+27 82 123 4567", "phone": ""}) == "27821234567"
    assert app_module.whatsapp_number({"whatsapp": "", "phone": ""}) == ""


def test_export_csv(client):
    database.add_lead("Smile Dental", email="info@smile.co.za")

    response = client.get("/export.csv")

    assert response.status_code == 200
    assert "Smile Dental" in response.get_data(as_text=True)


def test_run_needs_niche_and_location(client):
    response = client.post(
        "/run",
        data={"niche": "", "location": ""},
        follow_redirects=True
    )

    assert b"Type what kind of business and where." in response.data


def test_whatsapp_number_drops_zero_after_country_code():
    assert app_module.whatsapp_number({"whatsapp": "", "phone": "+27 (0)31 123 4567"}) == "27311234567"
