import csv
import io
import json
import os
import re
import threading
from datetime import datetime

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from database import (
    STATUSES,
    init_db,
    add_lead,
    get_leads,
    get_lead,
    update_lead,
    delete_lead,
    count_by_status,
    count_contacted_today,
    add_do_not_contact,
    find_existing_lead,
    get_settings,
    save_settings,
    now,
)
from email_checker import check_email_domain
from email_generator import generate_email
from lead_agent import write_email
from lead_pipeline import run_pipeline, signals_json
from lead_scorer import score_website, qualification
from local_ai import ai_status, MODEL
from website_analyzer import analyze_website, normalize_url


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(16)

init_db()


# ---------------------------------------------------------------
# Background pipeline run (one at a time)
# ---------------------------------------------------------------

RUN = {
    "running": False,
    "lines": [],
    "summary": None,
    "started": "",
}

RUN_LOCK = threading.Lock()


def start_run(niche, location, max_leads, minimum_score):

    with RUN_LOCK:
        if RUN["running"]:
            return False

        RUN.update(
            running=True,
            lines=[],
            summary=None,
            started=datetime.now().strftime("%H:%M"),
        )

    def log(line):
        RUN["lines"].append(str(line))
        del RUN["lines"][:-600]

    def worker():
        try:
            RUN["summary"] = run_pipeline(
                niche,
                location,
                max_leads=max_leads,
                minimum_score=minimum_score,
                log=log,
            )
        except Exception as error:
            log(f"\nThe run stopped because of an error: {error}")
        finally:
            RUN["running"] = False

    threading.Thread(target=worker, daemon=True).start()
    return True


# ---------------------------------------------------------------
# Helpers used by the templates
# ---------------------------------------------------------------

@app.template_filter("signals")
def signals_filter(lead):
    try:
        return json.loads(lead["signals"] or "{}")
    except (TypeError, ValueError):
        return {}


@app.template_filter("domain")
def domain_filter(url):
    url = (url or "").split("://")[-1]
    return url.removeprefix("www.").rstrip("/")


def whatsapp_number(lead, country_code="27"):
    """International digits for a wa.me link, or ""."""

    raw = lead["whatsapp"] or lead["phone"] or ""
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return ""

    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = country_code + digits[1:]

    # "+27 (0)82 ..." -> drop the 0 after the country code
    if digits.startswith(country_code + "0"):
        digits = country_code + digits[len(country_code) + 1:]

    return digits if len(digits) >= 10 else ""


@app.context_processor
def layout_values():
    ready, message = ai_status()

    return {
        "ai_ready": ready,
        "ai_message": message,
        "ai_model": MODEL,
        "statuses": STATUSES,
    }


# ---------------------------------------------------------------
# Pages
# ---------------------------------------------------------------

FILTERS = [
    ("active", "Active"),
    ("New", "New"),
    ("Contacted", "Contacted"),
    ("Replied", "Replied"),
    ("Won", "Won"),
    ("Not interested", "Not interested"),
    ("Skipped", "Skipped"),
    ("Rejected", "Rejected"),
    ("Do not contact", "Do not contact"),
    ("all", "All"),
]


@app.route("/")
def index():
    show = request.args.get("show", "active")

    leads = get_leads(None if show == "active" else show)

    settings = get_settings()

    try:
        daily_limit = int(settings["daily_send_limit"])
    except ValueError:
        daily_limit = 20

    return render_template(
        "index.html",
        leads=leads,
        show=show,
        filters=FILTERS,
        counts=count_by_status(),
        sent_today=count_contacted_today(),
        daily_limit=daily_limit,
        run=RUN,
        form=request.args,
    )


@app.route("/run", methods=["POST"])
def run():
    niche = request.form.get("niche", "").strip()
    location = request.form.get("location", "").strip()

    if not niche or not location:
        flash("Type what kind of business and where.", "error")
        return redirect(url_for("index"))

    try:
        max_leads = max(1, min(int(request.form.get("max_leads", 5)), 30))
        minimum_score = max(0, min(int(request.form.get("minimum_score", 20)), 100))
    except ValueError:
        max_leads, minimum_score = 5, 20

    if not start_run(niche, location, max_leads, minimum_score):
        flash("A search is already running - wait for it to finish.", "error")

    return redirect(url_for(
        "index",
        niche=niche,
        location=location,
        max_leads=max_leads,
        minimum_score=minimum_score,
    ) + "#run")


@app.route("/api/run")
def run_status():
    try:
        since = int(request.args.get("since", 0))
    except ValueError:
        since = 0

    return jsonify(
        running=RUN["running"],
        started=RUN["started"],
        lines=RUN["lines"][since:],
        total=len(RUN["lines"]),
        summary=RUN["summary"],
    )


@app.route("/add-lead", methods=["POST"])
def create_lead():

    business_name = request.form.get("business_name", "").strip()
    website = normalize_url(request.form.get("website", ""))
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    industry = request.form.get("industry", "").strip()
    location = request.form.get("location", "").strip()

    if not business_name:
        flash("A business name is required.", "error")
        return redirect(url_for("index"))

    existing = find_existing_lead(website, business_name)

    if existing:
        flash("That business is already in your list.", "error")
        return redirect(url_for("lead_page", lead_id=existing["id"]))

    # Check the website straight away so the score is based on facts.
    site = analyze_website(website)
    score, opportunities = score_website(site)

    analysis = {
        "website_data": site,
        "opportunities": opportunities,
    }

    email = email or site.get("business_email", "")

    subject, body = generate_email(
        {
            "business_name": business_name,
            "location": location,
            "opportunities": opportunities,
        },
        get_settings()
    )

    lead_id = add_lead(
        business_name=business_name,
        website=website,
        email=email,
        industry=industry,
        location=location,
        lead_score=score,
        opportunity="; ".join(item["label"] for item in opportunities),
        phone=phone or site.get("phone", ""),
        whatsapp=site.get("whatsapp", ""),
        email_status=check_email_domain(email),
        qualification=qualification(score),
        signals=signals_json(analysis),
        ai_reason="Added by hand",
        source="manual",
        status="New",
        email_subject=subject,
        email_body=body,
    )

    flash("Lead added and website checked. Use 'Rewrite with AI' for a more personal email.", "ok")
    return redirect(url_for("lead_page", lead_id=lead_id))


@app.route("/lead/<int:lead_id>")
def lead_page(lead_id):
    lead = get_lead(lead_id)

    if lead is None:
        abort(404)

    settings = get_settings()

    return render_template(
        "lead.html",
        lead=lead,
        whatsapp=whatsapp_number(lead, settings["default_country_code"] or "27"),
    )


@app.route("/lead/<int:lead_id>", methods=["POST"])
def save_lead(lead_id):
    lead = get_lead(lead_id)

    if lead is None:
        abort(404)

    email = request.form.get("email", "").strip().lower()

    fields = {
        "email": email,
        "email_subject": request.form.get("email_subject", "").strip(),
        "email_body": request.form.get("email_body", "").strip(),
        "phone": request.form.get("phone", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }

    if email != (lead["email"] or ""):
        fields["email_status"] = check_email_domain(email)

    if request.form.get("action") == "contacted":
        fields["status"] = "Contacted"
        fields["contacted_at"] = now()
        flash("Saved and marked as contacted.", "ok")
    else:
        flash("Saved.", "ok")

    update_lead(lead_id, **fields)

    return redirect(url_for("lead_page", lead_id=lead_id))


@app.route("/lead/<int:lead_id>/status", methods=["POST"])
def set_status(lead_id):
    lead = get_lead(lead_id)
    status = request.form.get("status", "")

    if lead is None or status not in STATUSES:
        abort(400)

    fields = {"status": status}

    if status == "Contacted" and not lead["contacted_at"]:
        fields["contacted_at"] = now()

    update_lead(lead_id, **fields)
    flash(f"Status changed to {status}.", "ok")

    return redirect(url_for("lead_page", lead_id=lead_id))


@app.route("/lead/<int:lead_id>/rewrite", methods=["POST"])
def rewrite_email(lead_id):
    lead = get_lead(lead_id)

    if lead is None:
        abort(404)

    signals = signals_filter(lead)

    analysis = {
        "business_name": lead["business_name"],
        "business_type": lead["industry"],
        "opportunities": signals.get("opportunities", []),
        "website_data": signals.get("site", {}),
    }

    business = {
        "business_name": lead["business_name"],
        "location": lead["location"],
    }

    subject, body, used_ai = write_email(business, analysis, get_settings())

    update_lead(lead_id, email_subject=subject, email_body=body)

    if used_ai:
        flash("New email - the opening line was written by the local AI.", "ok")
    else:
        flash("The AI couldn't write an opening (it's off, there was no website text, or its line broke the rules), so the standard template was used.", "error")

    return redirect(url_for("lead_page", lead_id=lead_id))


@app.route("/lead/<int:lead_id>/do-not-contact", methods=["POST"])
def do_not_contact(lead_id):
    lead = get_lead(lead_id)

    if lead is None:
        abort(404)

    add_do_not_contact(lead["email"], domain_filter(lead["website"]).split("/")[0])
    update_lead(lead_id, status="Do not contact")

    flash("Added to your do-not-contact list. Future searches will skip them.", "ok")
    return redirect(url_for("lead_page", lead_id=lead_id))


@app.route("/lead/<int:lead_id>/delete", methods=["POST"])
def remove_lead(lead_id):
    delete_lead(lead_id)
    flash("Lead deleted.", "ok")
    return redirect(url_for("index"))


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if request.method == "POST":
        save_settings(request.form)
        flash("Settings saved.", "ok")
        return redirect(url_for("settings_page"))

    return render_template("settings.html", settings=get_settings())


@app.route("/export.csv")
def export_csv():
    columns = [
        "id", "business_name", "website", "email", "email_status",
        "phone", "whatsapp", "industry", "location", "lead_score",
        "qualification", "opportunity", "status", "email_subject",
        "email_body", "notes", "source", "created_at", "contacted_at",
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)

    for lead in get_leads("all"):
        writer.writerow([lead[column] for column in columns])

    return Response(
        # BOM so Excel opens accents correctly.
        "﻿" + output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=hustlehubm-leads.csv"},
    )


if __name__ == "__main__":
    # 127.0.0.1 = only this computer can open the app.
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", 5000)),
        debug=os.getenv("FLASK_DEBUG") == "1",
    )
