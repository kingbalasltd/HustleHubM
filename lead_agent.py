import json
import re

import requests

from local_ai import ask_ai
from website_analyzer import analyze_website
from lead_scorer import score_website, qualification
from email_generator import generate_email


# The local AI does two jobs it is good at:
#   1. "What kind of page is this search result?"
#   2. One friendly, personal opening line for the email.
# The lead score is NOT the AI's opinion - lead_scorer works it
# out from what the website analyzer actually found - and the
# problem we mention in the email is written by the code, word
# for word, so a small model can't twist the facts.


CATEGORIES = {
    "single_business": "the website of ONE local business",
    "directory_or_list": "a directory, a list of businesses, or a booking/comparison site for many businesses",
    "article": "a news article, blog post or general information page",
    "government_or_education": "government, a university, school or NGO",
    "chain_or_hospital": "a big national chain, franchise head office or hospital group",
    "other": "anything else",
}


def parse_ai_json(text):
    """Pull a JSON object out of a model reply, even if it is
    wrapped in ```json fences or has chatter around it."""

    if not text:
        return None

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end <= start:
        return None

    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

    return data if isinstance(data, dict) else None


def to_bool(value):
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")

    return bool(value)


def unchecked(business, reason):
    return {
        "is_target_business": True,
        "business_name": business.get("business_name", ""),
        "business_type": business.get("industry", ""),
        "reason": reason,
        "ai_used": False,
    }


def classify_business(business, site):

    # Google Maps listings are already real businesses.
    if business.get("verified"):
        return unchecked(business, "Listed on Google Maps")

    category_list = "\n".join(
        f'- "{key}": {meaning}'
        for key, meaning in CATEGORIES.items()
    )

    prompt = f"""
You sort web search results for HustleHubM, a small agency that
sells websites and online marketing to local businesses.

What kind of page is this?

{category_list}

SEARCH RESULT
Title: {business.get("search_title") or business.get("business_name", "")}
Snippet: {business.get("search_evidence", "")}
Website: {business.get("website", "")}

THE WEBSITE ITSELF
Page title: {site.get("title", "")}
Description: {site.get("description", "")}
Text (start): {site.get("text", "")[:1500]}

Reply with JSON only, with exactly these keys in this order:
{{
    "reason": "one short sentence about what this page is",
    "category": "one of: {", ".join(CATEGORIES)}",
    "business_name": "the business's real name, without slogans",
    "business_type": "for example: dental practice"
}}
"""

    try:
        reply = ask_ai(prompt, json_mode=True, max_tokens=200)

    except requests.RequestException as error:
        return unchecked(
            business,
            f"Not checked by AI ({error.__class__.__name__}) - please review"
        )

    data = parse_ai_json(reply)

    if data is None:
        return unchecked(business, "AI reply could not be read - please review")

    category = str(data.get("category") or "").strip().lower()

    # Older prompts / other models may still answer true/false.
    if category not in CATEGORIES and "is_target_business" in data:
        category = (
            "single_business"
            if to_bool(data["is_target_business"])
            else "other"
        )

    name = str(data.get("business_name") or "").strip()

    return {
        "is_target_business": category == "single_business",
        "category": category,
        "business_name": name or business.get("business_name", ""),
        "business_type": str(data.get("business_type") or "").strip(),
        "reason": str(data.get("reason") or "").strip(),
        "ai_used": True,
    }


def analyze_business(business):
    """Check the website, ask the AI what kind of page it is,
    and score it from the evidence."""

    website = business.get("website", "")

    site = analyze_website(website)

    classification = classify_business(business, site)

    score, opportunities = score_website(site)

    if classification["is_target_business"]:
        level = qualification(score)
    else:
        score = 0
        level = "REJECT"

    return {
        "is_target_business": classification["is_target_business"],
        "business_name": classification["business_name"],
        "business_type": classification["business_type"],
        "reason": classification["reason"],
        "ai_used": classification["ai_used"],
        "lead_score": score,
        "qualification": level,
        "opportunities": opportunities,
        "opportunity": "; ".join(item["label"] for item in opportunities),
        "website_data": site,
    }


BANNED_PHRASES = (
    "losing",
    "untapped",
    "guarantee",
    "http",
    "www.",
    "unsubscribe",
    "improve",
    "boost",
    "online presence",
    # Pretending to be a customer is dishonest.
    "looking for",
    "i need",
    "as a customer",
    "caught my attention",
)


def parse_outreach(outreach):

    if not outreach:
        return "", ""

    outreach = outreach.strip()

    subject_match = re.search(
        r"(?im)^\s*\**subject:\**\s*(.+)$",
        outreach
    )

    # (?m) makes ^ match at the start of any line, not only the
    # start of the text (the old version never found BODY:).
    body_match = re.search(
        r"(?ims)^\s*\**body:\**\s*(.*)$",
        outreach
    )

    subject = ""

    if subject_match:
        subject = subject_match.group(1).strip().strip("*").strip()

    body = ""

    if body_match:
        body = body_match.group(1).strip()

    if not body:
        body = outreach

        if subject_match:
            body = body.replace(subject_match.group(0), "", 1).strip()

    return subject, body


def opening_is_acceptable(sentence):
    words = len(sentence.split())

    if not 8 <= words <= 40:
        return False

    lower = sentence.lower()

    # \b so "hi needs" (a salon name) doesn't count as "i need".
    if any(re.search(r"\b" + re.escape(phrase), lower) for phrase in BANNED_PHRASES):
        return False

    # Placeholders like [Name] mean the model didn't finish the job.
    if any(char in sentence for char in "[]{}<>"):
        return False

    return True


def write_opening(name, business_type, location, source_text):
    """One personal sentence, grounded in the business's own words.
    Returns "" when there is nothing to ground it in or the AI fails."""

    if len(source_text.strip()) < 80:
        return ""

    prompt = f"""
I am writing a short, friendly first email to {name}, a
{business_type or "local business"} in {location}.

Text from their website:
\"\"\"{source_text[:1200]}\"\"\"

Write ONE sentence (12 to 30 words), in the first person ("I"),
that shows I really looked at their business: mention one
specific service, speciality, area or detail that appears in the
text above.

Rules: start with "I saw" or "I came across", no advice, no
problems, no compliments about the website itself, no exclamation
marks, nothing that is not in the text. I am NOT a customer - never
say I need their service or am looking for one.

Reply as JSON: {{"sentence": "..."}}
"""

    try:
        reply = ask_ai(prompt, json_mode=True, max_tokens=120)
    except requests.RequestException:
        return ""

    data = parse_ai_json(reply) or {}
    sentence = str(data.get("sentence") or "").strip().replace("!", ".")

    if not opening_is_acceptable(sentence):
        return ""

    if sentence[-1] not in ".?":
        sentence += "."

    return sentence


def write_email(business, analysis, sender=None):
    """Returns (subject, body, ai_wrote_the_opening)."""

    site = analysis.get("website_data") or {}

    lead = {
        "business_name": analysis.get("business_name") or business.get("business_name", ""),
        "location": business.get("location", ""),
        "opportunities": analysis.get("opportunities", []),
    }

    source_text = " ".join(
        part
        for part in (
            site.get("description", ""),
            site.get("text", ""),
        )
        if part
    ) or business.get("search_evidence", "")

    opening = write_opening(
        lead["business_name"],
        analysis.get("business_type", ""),
        lead["location"],
        source_text,
    )

    subject, body = generate_email(lead, sender, opening)

    return subject, body, bool(opening)


def generate_outreach(business, analysis, sender=None):
    """Kept for test_ai.py: returns the email as one block of text."""

    subject, body, _ = write_email(business, analysis, sender)

    return f"SUBJECT: {subject}\n\nBODY:\n{body}"
