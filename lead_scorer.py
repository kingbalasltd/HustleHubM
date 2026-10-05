from datetime import date


def score_lead(
    has_website=True,
    website_outdated=False,
    has_booking=False,
    weak_call_to_action=False,
    weak_social_presence=False,
    public_email=False
):
    score = 0
    opportunities = []

    if not has_website:
        score += 30
        opportunities.append("No website")

    if website_outdated:
        score += 20
        opportunities.append("Website may need improvement")

    if not has_booking:
        score += 15
        opportunities.append("No obvious online booking")

    if weak_call_to_action:
        score += 15
        opportunities.append("Weak call-to-action")

    if weak_social_presence:
        score += 10
        opportunities.append("Weak social presence")

    if public_email:
        score += 10

    return min(score, 100), ", ".join(opportunities)


def qualification(score):
    if score >= 50:
        return "HIGH"

    if score >= 25:
        return "MEDIUM"

    return "LOW"


def opportunity(key, points, label, pitch):
    """label is what the dashboard shows; pitch is a sentence the
    email can use word for word, because it's a checked fact."""
    return {
        "key": key,
        "points": points,
        "label": label,
        "pitch": pitch
    }


def score_website(site):
    """Score a lead from what website_analyzer actually found.

    Higher score = more we can honestly help with. Every
    opportunity is something observable, so the outreach email
    never has to guess.

    Returns (score, opportunities).
    """
    found = []
    status = site.get("status", "none")
    checked_on = site.get("checked_on") or date.today().isoformat()

    if status == "none":
        found.append(opportunity(
            "no_website", 45,
            "No website found",
            "I couldn't find a website for your business"
        ))

    elif status == "down":
        found.append(opportunity(
            "site_down", 45,
            "Website did not load when checked",
            f"when I tried to open your website on {checked_on}, it didn't load for me"
        ))

    elif status == "ok":

        if not site.get("mobile_friendly"):
            found.append(opportunity(
                "not_mobile", 20,
                "No mobile setup (viewport tag) - may display badly on phones",
                "your website doesn't seem to be set up for phones, so it may "
                "display very small on a mobile screen"
            ))

        if not site.get("has_booking"):
            found.append(opportunity(
                "no_booking", 15,
                "No online booking detected",
                "I couldn't find a way to book or request an appointment online"
            ))

        if not site.get("https"):
            found.append(opportunity(
                "no_https", 10,
                "Not served over HTTPS",
                "your website doesn't load over a secure (https) connection, "
                "so some browsers show a \"Not secure\" warning"
            ))

        year = site.get("copyright_year")

        if year and year <= date.today().year - 2:
            found.append(opportunity(
                "old_copyright", 10,
                f"Footer still says (c) {year}",
                f"the footer of your website still says {year}, which can make "
                f"it look out of date to new visitors"
            ))

        if not site.get("has_contact_form") and not site.get("has_whatsapp"):
            found.append(opportunity(
                "no_quick_contact", 10,
                "No contact form or WhatsApp button detected",
                "I couldn't find a contact form or a WhatsApp button, so "
                "visitors have to call or email to reach you"
            ))

        if not site.get("description"):
            found.append(opportunity(
                "no_description", 5,
                "No Google description (meta description)",
                "your website has no description set for Google, so Google "
                "picks random text to show under your name"
            ))

        seconds = site.get("load_seconds")

        if seconds and seconds >= 4:
            found.append(opportunity(
                "slow", 5,
                f"Homepage took {seconds}s to load",
                f"your homepage took about {seconds:.0f} seconds just to start "
                f"loading when I opened it"
            ))

        if not site.get("has_social_links"):
            found.append(opportunity(
                "no_social", 5,
                "No social media links on the website",
                "I couldn't find links to your social media pages on the website"
            ))

    # "blocked", "thin" (JavaScript-only) or "dead" (domain gone):
    # we couldn't really look, so we claim nothing.

    score = min(sum(item["points"] for item in found), 100)

    return score, found
