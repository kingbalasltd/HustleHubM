import json

import database
import lead_agent
import lead_pipeline


def site(status="ok", **values):
    base = {
        "status": status,
        "title": "",
        "description": "",
        "text": "",
        "business_email": "",
        "phone": "",
        "whatsapp": "",
        "mobile_friendly": True,
        "has_booking": True,
        "https": True,
        "has_contact_form": True,
        "has_social_links": True,
        "copyright_year": None,
        "load_seconds": 1.0,
        "checked_on": "2026-10-05",
    }
    base["description"] = "A business"
    base.update(values)
    return base


SITES = {
    "https://directory.co.za/": site(),
    "https://weak.co.za/": site(
        mobile_friendly=False,
        has_booking=False,
        business_email="info@weak.co.za",
        phone="011 123 4567",
        text="Family dentistry and Invisalign in Sandton. " * 5,
    ),
    "https://good.co.za/": site(business_email="info@good.co.za"),
    "https://gone.co.za/": site(status="dead"),
    "https://nocontact.co.za/": site(mobile_friendly=False, has_booking=False),
}

BUSINESSES = [
    {"business_name": "Top 10 Dentists", "website": "https://directory.co.za/"},
    {"business_name": "Weak Dental", "website": "https://weak.co.za/"},
    {"business_name": "Good Dental", "website": "https://good.co.za/"},
    {"business_name": "Gone Dental", "website": "https://gone.co.za/"},
    {"business_name": "No Contact Dental", "website": "https://nocontact.co.za/"},
]


def fake_ai(prompt, json_mode=False, max_tokens=350):
    if '"category"' in prompt:
        category = "directory_or_list" if "Top 10" in prompt else "single_business"
        return json.dumps({
            "reason": "test",
            "category": category,
            "business_name": "",
            "business_type": "dental practice",
        })

    return json.dumps({"sentence": "I saw that you offer Invisalign and family dentistry in Sandton."})


def run(monkeypatch, **kwargs):
    monkeypatch.setattr(lead_pipeline, "discover_all", lambda *a, **k: [dict(b) for b in BUSINESSES])
    monkeypatch.setattr(lead_pipeline, "ai_status", lambda: (True, "AI ready"))
    monkeypatch.setattr(lead_pipeline, "check_email_domain", lambda email: "valid" if email else "none")
    monkeypatch.setattr(lead_agent, "analyze_website", lambda url: dict(SITES[url]))
    monkeypatch.setattr(lead_agent, "ask_ai", fake_ai)

    lines = []
    summary = lead_pipeline.run_pipeline("dentists", "Sandton", log=lines.append, **kwargs)
    return summary, lines


def test_pipeline_saves_only_contactable_leads_with_gaps(temp_db, monkeypatch):
    summary, _ = run(monkeypatch, max_leads=5, minimum_score=20)

    statuses = {lead["business_name"]: lead["status"] for lead in database.get_leads("all")}

    assert statuses == {
        "Top 10 Dentists": "Rejected",
        "Weak Dental": "New",
        "Good Dental": "Skipped",
        "Gone Dental": "Skipped",
        "No Contact Dental": "Skipped",
    }
    assert summary["saved"] == 1
    assert summary["rejected"] == 1
    assert summary["skipped"] == 3


def test_saved_lead_has_everything_needed_to_send(temp_db, monkeypatch):
    run(monkeypatch, max_leads=5, minimum_score=20)

    lead = database.get_leads("New")[0]

    assert lead["email"] == "info@weak.co.za"
    assert lead["email_status"] == "valid"
    assert lead["phone"] == "011 123 4567"
    assert lead["lead_score"] == 35
    assert lead["qualification"] == "MEDIUM"
    assert lead["email_subject"] == "Weak Dental website on phones"
    assert "I saw that you offer Invisalign" in lead["email_body"]
    assert "doesn't seem to be set up for phones" in lead["email_body"]

    signals = json.loads(lead["signals"])
    assert [item["key"] for item in signals["opportunities"]] == ["not_mobile", "no_booking"]


def test_second_run_skips_everything_already_checked(temp_db, monkeypatch):
    run(monkeypatch, max_leads=5, minimum_score=20)
    summary, _ = run(monkeypatch, max_leads=5, minimum_score=20)

    assert summary["saved"] == 0
    assert summary["existing"] == len(BUSINESSES)


def test_stops_at_max_leads(temp_db, monkeypatch):
    summary, _ = run(monkeypatch, max_leads=1, minimum_score=0)

    assert summary["saved"] == 1
