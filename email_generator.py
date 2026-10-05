OPT_OUT_LINE = (
    "If you'd rather not hear from me, just reply \"no thanks\" "
    "and I won't contact you again."
)


# A specific subject gets opened; "Improving your online presence"
# looks like spam.
SUBJECTS = {
    "no_website": "Website for {name}?",
    "site_down": "{name} website not loading",
    "not_mobile": "{name} website on phones",
    "no_booking": "Online bookings for {name}?",
    "no_https": "\"Not secure\" warning on the {name} website",
    "old_copyright": "{name} website footer",
    "no_quick_contact": "WhatsApp button for {name}?",
    "no_description": "{name} on Google",
    "slow": "{name} website speed",
    "no_social": "{name} social media links",
}


def email_footer(sender):
    """Signature + opt-out. South Africa's POPIA (section 69) requires
    every marketing email to say who sent it and how to stop them."""

    lines = [
        sender.get("sender_name", ""),
        sender.get("sender_company", ""),
        sender.get("sender_contact", ""),
    ]

    signature = "\n".join(line for line in lines if line.strip())

    return f"Kind regards,\n{signature}\n\n{OPT_OUT_LINE}"


def add_footer(body, sender):
    body = body.strip()

    if OPT_OUT_LINE in body:
        return body

    return f"{body}\n\n{email_footer(sender)}"


def top_opportunity(lead):
    opportunities = lead.get("opportunities") or []

    if opportunities:
        return opportunities[0]

    return None


def email_subject(lead):
    name = lead["business_name"]
    top = top_opportunity(lead)

    if top and top["key"] in SUBJECTS:
        return SUBJECTS[top["key"]].format(name=name)

    return f"Quick question for {name}"


def generate_email(lead, sender=None, opening=""):
    """Build the email. The checked fact is always written by the
    code, word for word, so it can never be twisted. `opening` is
    an optional personal first line written by the local AI."""

    sender = sender or {}
    business = lead["business_name"]
    location = lead.get("location", "")
    top = top_opportunity(lead)

    where = f" in {location}" if location else ""

    if not opening:
        opening = f"I came across {business} while looking at local businesses{where}."

    noticed = ""

    if top:
        lead_in = "I also noticed" if "noticed" in opening.lower() else "I noticed"
        noticed = f"\n\n{lead_in} that {top['pitch']}."

    body = f"""Hi {business} team,

{opening}{noticed}

I help small businesses with their websites and getting more enquiries online, and I have a couple of simple ideas that could help you.

Would you like me to send them over? It's free and there's no obligation."""

    return email_subject(lead), add_footer(body, sender)
