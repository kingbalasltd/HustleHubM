import requests

from bs4 import BeautifulSoup

from website_analyzer import (
    analyze_website,
    decode_cfemail,
    email_rank,
    extract_business_email,
)


HOME = "https://example.co.za/"


def page(body, head='<meta name="viewport" content="width=device-width">'):
    return (
        "<html><head><title>Smile Dental</title>"
        f"{head}</head><body>{body}</body></html>"
    )


def cloudflare_encode(email, key):
    return f"{key:02x}" + "".join(f"{ord(char) ^ key:02x}" for char in email)


def test_facebook_link_is_not_online_booking(fake_site):
    fake_site({HOME: page('<a href="https://facebook.com/smile">Facebook</a>')})

    result = analyze_website(HOME)

    assert result["has_social_links"] is True
    assert result["has_booking"] is False


def test_real_booking_link_is_detected(fake_site):
    fake_site({HOME: page('<a href="/book-online">Book an appointment</a>')})

    assert analyze_website(HOME)["has_booking"] is True


def test_booking_widget_iframe_is_detected(fake_site):
    fake_site({HOME: page('<iframe src="https://calendly.com/smile/visit"></iframe>')})

    assert analyze_website(HOME)["has_booking"] is True


def test_decode_cloudflare_email():
    assert decode_cfemail(cloudflare_encode("info@example.com", 0x42)) == "info@example.com"
    assert decode_cfemail("zz") == ""


def test_cloudflare_protected_email_is_found(fake_site):
    encoded = cloudflare_encode("info@example.co.za", 0x1C)

    fake_site({HOME: page(
        f'<a href="/cdn-cgi/l/email-protection#{encoded}">'
        f'<span class="__cf_email__" data-cfemail="{encoded}">'
        "[email&#160;protected]</span></a>"
    )})

    assert analyze_website(HOME)["business_email"] == "info@example.co.za"


def test_email_on_contact_page_is_found(fake_site):
    fake_site({
        HOME: page('<a href="/contact-us">Contact us</a>'),
        "https://example.co.za/contact-us": page("Email us: reception@example.co.za"),
    })

    result = analyze_website(HOME)

    assert result["business_email"] == "reception@example.co.za"
    assert result["has_email"] is True


def test_email_ranking_prefers_own_domain():
    soup = BeautifulSoup(
        "designer@webagency.co.za smiledental@gmail.com "
        "hello@example.co.za logo@2x.png",
        "html.parser"
    )

    assert extract_business_email(soup, "example.co.za") == "hello@example.co.za"


def test_email_rank_rejects_junk():
    assert email_rank("noreply@example.co.za", "example.co.za") is None
    assert email_rank("x@sentry.wixpress.com", "example.co.za") is None
    assert email_rank("designer@webagency.co.za", "example.co.za") is None
    assert email_rank("practice@gmail.com", "example.co.za") == 2


def test_mobile_https_copyright_and_description(fake_site):
    fake_site({HOME: page(
        "<footer>&copy; 2018 Smile Dental</footer>",
        head='<meta name="description" content="Family dentist">'
    )})

    result = analyze_website(HOME)

    assert result["status"] == "ok"
    assert result["https"] is True
    assert result["mobile_friendly"] is False
    assert result["copyright_year"] == 2018
    assert result["description"] == "Family dentist"


def test_copyright_range_uses_latest_year(fake_site):
    fake_site({HOME: page("<footer>Copyright 2015 - 2025 Smile Dental</footer>")})

    assert analyze_website(HOME)["copyright_year"] == 2025


def test_phone_and_whatsapp_are_found(fake_site):
    fake_site({HOME: page(
        '<a href="https://wa.me/27821234567">Chat on WhatsApp</a> '
        "Call 011 123 4567"
    )})

    result = analyze_website(HOME)

    assert result["whatsapp"] == "27821234567"
    assert result["phone"] == "011 123 4567"


def test_http_site_with_working_https_counts_as_secure(fake_site):
    fake_site({
        "http://example.co.za/": page("Hello"),
        "https://example.co.za/": page("Hello"),
    })

    assert analyze_website("http://example.co.za/")["https"] is True


def test_http_only_site_is_not_secure(fake_site):
    fake_site({"http://example.co.za/": page("Hello")})

    assert analyze_website("http://example.co.za/")["https"] is False


def test_website_that_errors_is_down(fake_site):
    fake_site({}, default_status=500)

    result = analyze_website(HOME)

    assert result["status"] == "down"
    assert result["reachable"] is False


def test_firewall_block_is_not_called_down(fake_site):
    fake_site({}, default_status=403)

    assert analyze_website(HOME)["status"] == "blocked"


def test_no_website():
    assert analyze_website("")["status"] == "none"


def test_dead_domain_is_not_called_down(monkeypatch):
    import website_analyzer

    def no_dns(url, **kwargs):
        raise requests.ConnectionError("Failed to resolve 'gone.co.za'")

    monkeypatch.setattr(website_analyzer.requests, "get", no_dns)

    assert analyze_website("https://gone.co.za/")["status"] == "dead"


def test_javascript_only_page_is_not_judged(fake_site):
    fake_site({HOME: (
        '<html><head><title>App</title></head><body><div id="root"></div>'
        '<script src="/static/js/main.js"></script></body></html>'
    )})

    result = analyze_website(HOME)

    assert result["status"] == "thin"
    assert result["has_booking"] is False


def test_phone_with_country_code_and_zero(fake_site):
    fake_site({HOME: page("Call us on +27 (0)31 123 4567 today")})

    assert analyze_website(HOME)["phone"] == "+27 (0)31 123 4567"
