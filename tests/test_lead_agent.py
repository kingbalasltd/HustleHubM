import json

import requests

import lead_agent
from lead_agent import (
    classify_business,
    opening_is_acceptable,
    parse_ai_json,
    parse_outreach,
    to_bool,
    write_email,
)


def ai_replies(monkeypatch, reply):
    monkeypatch.setattr(lead_agent, "ask_ai", lambda *args, **kwargs: reply)


def test_parse_ai_json_handles_fences_and_chatter():
    assert parse_ai_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_ai_json('Sure! {"a": 2} Hope this helps') == {"a": 2}
    assert parse_ai_json("no json here") is None
    assert parse_ai_json("") is None


def test_to_bool_reads_strings():
    assert to_bool("false") is False
    assert to_bool("True") is True
    assert to_bool(False) is False


def test_parse_outreach_separates_subject_and_body():
    subject, body = parse_outreach("SUBJECT: Quick idea\n\nBODY:\nHi there,\nThanks.")

    assert subject == "Quick idea"
    assert body == "Hi there,\nThanks."


def test_parse_outreach_without_body_label():
    subject, body = parse_outreach("Subject: Hello\nHi team, short note.")

    assert subject == "Hello"
    assert body == "Hi team, short note."


def test_directory_is_rejected(monkeypatch):
    ai_replies(monkeypatch, json.dumps({
        "reason": "A directory listing many dentists.",
        "category": "directory_or_list",
        "business_name": "Dentists Johannesburg",
        "business_type": "directory",
    }))

    result = classify_business({"business_name": "x"}, {})

    assert result["is_target_business"] is False


def test_single_business_is_accepted(monkeypatch):
    ai_replies(monkeypatch, json.dumps({
        "reason": "A dental practice website.",
        "category": "single_business",
        "business_name": "Smile Dental",
        "business_type": "dental practice",
    }))

    result = classify_business({"business_name": "Home | Smile Dental"}, {})

    assert result["is_target_business"] is True
    assert result["business_name"] == "Smile Dental"


def test_ai_offline_means_review_not_reject(monkeypatch):
    def offline(*args, **kwargs):
        raise requests.ConnectionError("Ollama not running")

    monkeypatch.setattr(lead_agent, "ask_ai", offline)

    result = classify_business({"business_name": "Smile Dental"}, {})

    assert result["is_target_business"] is True
    assert "please review" in result["reason"]


def test_opening_rules():
    assert opening_is_acceptable(
        "I saw that you offer Invisalign and family dentistry in Ridgeway."
    )
    assert not opening_is_acceptable("Hi [Name], we can boost your online presence today.")
    assert not opening_is_acceptable("Too short.")


def test_email_keeps_the_fact_even_when_ai_writes(monkeypatch):
    ai_replies(
        monkeypatch,
        '{"sentence": "I saw that you offer Invisalign and family dentistry '
        'in Ridgeway and Glenanda"}'
    )

    analysis = {
        "business_name": "The Dentists Inc.",
        "opportunities": [{
            "key": "slow",
            "points": 5,
            "label": "Slow",
            "pitch": "your homepage took about 5 seconds just to start loading when I opened it",
        }],
        "website_data": {"text": "Cosmetic, orthodontic, Invisalign and family dentistry " * 3},
    }

    subject, body, used_ai = write_email({"location": "Johannesburg"}, analysis, {})

    assert used_ai is True
    assert subject == "The Dentists Inc. website speed"
    assert "I saw that you offer Invisalign" in body
    assert "your homepage took about 5 seconds just to start loading" in body


def test_bad_ai_opening_falls_back_to_template(monkeypatch):
    ai_replies(monkeypatch, '{"sentence": "We can boost your online presence and guarantee results!"}')

    analysis = {
        "business_name": "Smile Dental",
        "opportunities": [],
        "website_data": {"text": "Family dentistry in Sandton " * 10},
    }

    _, body, used_ai = write_email({"location": "Sandton"}, analysis, {})

    assert used_ai is False
    assert "boost" not in body
    assert "I came across Smile Dental" in body


def test_opening_must_not_pretend_to_be_a_customer():
    assert not opening_is_acceptable(
        "I saw that you offer the best rates in DBN, which caught my attention "
        "as I'm looking for a reliable plumber."
    )
    # "Hi Needs Salon" contains the letters "i need" but is a name.
    assert opening_is_acceptable("I saw that Hi Needs Salon offers braids and wig installs in Soweto.")
