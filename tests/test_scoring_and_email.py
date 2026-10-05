from datetime import date

from email_generator import OPT_OUT_LINE, generate_email
from lead_scorer import qualification, score_lead, score_website


def keys(opportunities):
    return [item["key"] for item in opportunities]


GOOD_SITE = {
    "status": "ok",
    "mobile_friendly": True,
    "has_booking": True,
    "https": True,
    "copyright_year": date.today().year,
    "has_contact_form": True,
    "description": "Family dentist",
    "load_seconds": 1.0,
    "has_social_links": True,
}


def test_no_website_scores_high():
    score, found = score_website({"status": "none"})

    assert score == 45
    assert keys(found) == ["no_website"]
    assert qualification(score) == "MEDIUM"


def test_blocked_site_claims_nothing():
    assert score_website({"status": "blocked"}) == (0, [])


def test_good_site_scores_zero():
    assert score_website(GOOD_SITE) == (0, [])


def test_weak_site_lists_each_gap():
    site = {"status": "ok", "copyright_year": 2019, "load_seconds": 6.2}

    score, found = score_website(site)

    assert keys(found) == [
        "not_mobile", "no_booking", "no_https", "old_copyright",
        "no_quick_contact", "no_description", "slow", "no_social",
    ]
    assert score == 80
    assert qualification(score) == "HIGH"


def test_old_manual_scorer_still_works():
    assert score_lead(has_website=False, has_booking=True) == (30, "No website")


def test_template_email_states_the_fact_and_opt_out():
    _, found = score_website(dict(GOOD_SITE, has_booking=False))

    subject, body = generate_email(
        {"business_name": "Smile Dental", "location": "Sandton", "opportunities": found},
        {"sender_name": "Madjer", "sender_company": "HustleHubM"},
    )

    assert subject == "Online bookings for Smile Dental?"
    assert body.startswith("Hi Smile Dental team,")
    assert "I noticed that I couldn't find a way to book or request an appointment online." in body
    assert "Madjer\nHustleHubM" in body
    assert body.endswith(OPT_OUT_LINE)


def test_template_email_uses_ai_opening():
    _, body = generate_email(
        {"business_name": "Smile Dental", "opportunities": []},
        {},
        opening="I saw that you offer Invisalign in Sandton.",
    )

    assert "I saw that you offer Invisalign in Sandton." in body
    assert "I noticed that" not in body


def test_fact_is_not_introduced_twice_the_same_way():
    _, found = score_website(dict(GOOD_SITE, has_booking=False))

    _, body = generate_email(
        {"business_name": "Smile Dental", "opportunities": found},
        {},
        opening="I noticed that your salon offers braids and wig installs.",
    )

    assert body.count("I noticed that") == 1
    assert "I also noticed that I couldn't find a way to book" in body
