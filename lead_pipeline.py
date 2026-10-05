import argparse
import json
import sys

from business_discovery import discover_all
from lead_agent import analyze_business, write_email
from database import (
    init_db,
    add_lead,
    find_existing_lead,
    is_do_not_contact,
    get_settings,
)
from email_checker import check_email_domain
from local_ai import ai_status


def lead_already_exists(website, business_name):
    return find_existing_lead(website, business_name) is not None


def signals_json(analysis):
    site = dict(analysis["website_data"])
    # A short excerpt is enough for "Rewrite with AI" later.
    site["text"] = site.get("text", "")[:1200]

    return json.dumps({
        "site": site,
        "opportunities": analysis["opportunities"],
    })


def run_pipeline(
    niche,
    location,
    max_leads=5,
    minimum_score=20,
    log=print
):
    """Find businesses, check their websites, score them and
    write a first email for each good lead.

    log is called with each progress line - the web dashboard
    passes its own function to show progress live.
    """

    log("====================================")
    log("HUSTLEHUBM LEAD MACHINE")
    log("====================================")
    log(f"Niche: {niche} | Location: {location}")
    log(f"Target leads: {max_leads} | Minimum score: {minimum_score}")

    init_db()

    ready, message = ai_status()
    log(message)

    if not ready:
        log(
            "Continuing without AI: results are marked 'please review' "
            "and emails use the built-in template."
        )

    settings = get_settings()

    summary = {
        "candidates": 0,
        "saved": 0,
        "rejected": 0,
        "skipped": 0,
        "existing": 0,
        "lead_ids": [],
    }

    log("\n[1/2] Finding businesses...")

    # Search for extra candidates because some will be rejected.
    search_limit = max(max_leads * 3, 15)

    businesses = discover_all(
        niche=niche,
        location=location,
        max_results=search_limit,
        log=log
    )

    summary["candidates"] = len(businesses)
    log(f"Found {len(businesses)} candidates.")

    log("\n[2/2] Checking websites, scoring and writing emails...")

    for index, business in enumerate(businesses, start=1):

        if summary["saved"] >= max_leads:
            break

        name = business.get("business_name") or "Unknown business"
        website = business.get("website", "")

        log(f"\n{index}/{len(businesses)}: {name}")

        if lead_already_exists(website, name):
            summary["existing"] += 1
            log("  -> Already in your list - skipping.")
            continue

        if is_do_not_contact(website=website):
            summary["existing"] += 1
            log("  x On your do-not-contact list - skipping.")
            continue

        try:
            analysis = analyze_business(business)
        except Exception as error:
            log(f"  ! Check failed: {error}")
            continue

        site = analysis["website_data"]
        business_name = analysis["business_name"] or name
        email = site.get("business_email", "")

        if business_name != name and lead_already_exists("", business_name):
            summary["existing"] += 1
            log(f"  -> Already in your list as {business_name} - skipping.")
            continue

        record = {
            "business_name": business_name,
            "website": website,
            "email": email,
            "industry": niche,
            "location": business.get("location") or location,
            "lead_score": analysis["lead_score"],
            "opportunity": analysis["opportunity"],
            "phone": business.get("phone") or site.get("phone", ""),
            "whatsapp": site.get("whatsapp", ""),
            "qualification": analysis["qualification"],
            "signals": signals_json(analysis),
            "ai_reason": analysis["reason"],
            "source": business.get("source", "web search"),
        }

        if not analysis["is_target_business"]:
            summary["rejected"] += 1
            log(f"  x Not a target business - {analysis['reason']}")
            # Saved (hidden) so the next run doesn't check it again.
            add_lead(**record, status="Rejected")
            continue

        if email and is_do_not_contact(email=email):
            summary["existing"] += 1
            log("  x Email is on your do-not-contact list - skipping.")
            continue

        score = analysis["lead_score"]

        if site.get("status") == "dead":
            summary["skipped"] += 1
            log("  x The website's domain no longer exists - saved under 'Skipped'.")
            add_lead(**record, status="Skipped")
            continue

        if site.get("status") == "blocked":
            log("  ! The website blocked our checker, so it couldn't be scored.")

        if site.get("status") == "thin":
            log("  ! The website is built with JavaScript, so it couldn't be checked.")

        log(f"  Score {score}/100 - {analysis['opportunity'] or 'no gaps found'}")

        if score < minimum_score:
            summary["skipped"] += 1
            log("  x Below your minimum score - saved under 'Skipped'.")
            add_lead(**record, status="Skipped")
            continue

        if not (email or record["phone"] or record["whatsapp"]):
            summary["skipped"] += 1
            log("  x No email, phone or WhatsApp found - saved under 'Skipped'.")
            add_lead(**record, status="Skipped")
            continue

        record["email_status"] = check_email_domain(email)

        if record["email_status"] == "no_mx":
            log(f"  ! {email} can't receive email (no mail server) - check it.")

        contacts = [
            label
            for label, value in (
                ("email", email),
                ("phone", record["phone"]),
                ("WhatsApp", record["whatsapp"]),
            )
            if value
        ]

        log(f"  Contact: {', '.join(contacts) or 'none found - check the website'}")
        log("  Writing email...")

        subject, body, used_ai = write_email(business, analysis, settings)

        lead_id = add_lead(
            **record,
            status="New",
            email_subject=subject,
            email_body=body,
        )

        summary["saved"] += 1
        summary["lead_ids"].append(lead_id)

        written_by = "AI" if used_ai else "template"
        log(f"  + SAVED {business_name} ({score}/100, email by {written_by})")

    log("\n====================================")
    log("PIPELINE COMPLETE")
    log("====================================")
    log(
        f"New leads: {summary['saved']} | Rejected: {summary['rejected']} | "
        f"Skipped: {summary['skipped']} | Already known: {summary['existing']}"
    )

    return summary


if __name__ == "__main__":

    # Windows terminals can't always print every character.
    sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        description="Find, check and score leads, then draft emails."
    )
    parser.add_argument("niche", nargs="?", default="dentists")
    parser.add_argument("location", nargs="?", default="Johannesburg")
    parser.add_argument("--max", type=int, default=5, help="how many new leads")
    parser.add_argument("--min-score", type=int, default=20)

    args = parser.parse_args()

    run_pipeline(
        niche=args.niche,
        location=args.location,
        max_leads=args.max,
        minimum_score=args.min_score
    )
