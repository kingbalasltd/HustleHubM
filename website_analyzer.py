import re
import warnings
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/154.0 Safari/537.36"
    ),
    "Accept-Language": "en-ZA,en;q=0.9"
}


BUSINESS_EMAIL_PREFIXES = {
    "info",
    "hello",
    "contact",
    "bookings",
    "booking",
    "enquiries",
    "enquiry",
    "sales",
    "office",
    "admin",
    "support",
    "reception",
    "appointments",
    "practice",
    "frontdesk",
    "mail",
    "general",
}


# Small businesses in SA often use these instead of their own domain.
FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "yahoo.co.za",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "webmail.co.za",
    "mweb.co.za",
    "telkomsa.net",
    "vodamail.co.za",
    "iafrica.com",
    "absamail.co.za",
    "lantic.net",
}


JUNK_EMAIL_DOMAINS = {
    "example.com",
    "domain.com",
    "email.com",
    "yourdomain.com",
    "sentry.io",
    "wixpress.com",
    "sentry.wixpress.com",
    "sentry-next.wixpress.com",
}


JUNK_EMAIL_NAMES = {
    "noreply",
    "no-reply",
    "donotreply",
    "privacy",
    "abuse",
    "postmaster",
    "webmaster",
}


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")


EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

# South African numbers: 011 123 4567, +27 11 123 4567,
# +27 (0)11 123 4567, (011) 123-4567
PHONE_PATTERN = re.compile(
    r"(?:\+27\s?\(0\)|\+27|\b0)[\s-]?\(?\d{2}\)?[\s-]?\d{3}[\s-]?\d{4}\b"
)

# "\b" stops "facebook" from counting as a booking link.
BOOKING_PATTERN = re.compile(
    r"\b(book|appointment|schedul|reserv)",
    re.IGNORECASE
)

BOOKING_PLATFORMS = (
    "calendly.com",
    "setmore.com",
    "fresha.com",
    "booksy.com",
    "simplybook",
    "acuityscheduling.com",
    "appointy.com",
    "zocdoc.com",
)

SOCIAL_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "youtube.com",
)

COPYRIGHT_PATTERN = re.compile(
    r"(?:©|\(c\)|copyright)\s*(?:\d{4}\s*[-–]\s*)?((?:19|20)\d{2})",
    re.IGNORECASE
)

CTA_WORDS = [
    "book now",
    "book online",
    "schedule",
    "appointment",
    "contact us",
    "get started",
    "call now",
    "request",
    "enquire",
    "enquiry"
]


def site_domain(url):
    domain = urlparse(url or "").netloc.lower().split(":")[0]
    return domain.removeprefix("www.")


def normalize_url(url):
    url = (url or "").strip()

    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url


def homepage_url(url):
    parsed = urlparse(normalize_url(url))

    if not parsed.netloc:
        return ""

    return f"{parsed.scheme}://{parsed.netloc}/"


def is_business_email(email):

    if not email or "@" not in email:
        return False

    local_part = email.split("@")[0].lower()

    return local_part in BUSINESS_EMAIL_PREFIXES


def decode_cfemail(encoded):
    """Cloudflare hides emails as hex; the first byte is the XOR key."""
    try:
        data = bytes.fromhex(encoded)
    except ValueError:
        return ""

    if len(data) < 2:
        return ""

    key = data[0]
    return "".join(chr(byte ^ key) for byte in data[1:])


def find_emails(soup):
    found = []

    # 1. mailto links
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()

        if href.lower().startswith("mailto:"):
            found.append(href[7:].split("?")[0])

        if "/cdn-cgi/l/email-protection#" in href:
            found.append(decode_cfemail(href.split("#", 1)[1]))

    # 2. Cloudflare-protected emails
    for tag in soup.select("[data-cfemail]"):
        found.append(decode_cfemail(tag.get("data-cfemail", "")))

    # 3. Visible page text
    found.extend(
        EMAIL_PATTERN.findall(soup.get_text(" ", strip=True))
    )

    emails = []

    for email in found:
        email = email.strip().strip(".").lower()

        if email and email not in emails:
            emails.append(email)

    return emails


def email_rank(email, domain=""):
    """Lower is better. None means the address should not be used."""

    if not EMAIL_PATTERN.fullmatch(email):
        return None

    if email.endswith(IMAGE_EXTENSIONS):
        return None

    local_part, _, email_domain = email.partition("@")

    if email_domain in JUNK_EMAIL_DOMAINS:
        return None

    if local_part in JUNK_EMAIL_NAMES:
        return None

    same_domain = bool(domain) and (
        email_domain == domain
        or email_domain.endswith("." + domain)
        or domain.endswith("." + email_domain)
    )

    role = local_part in BUSINESS_EMAIL_PREFIXES

    if same_domain and role:
        return 0

    if same_domain:
        return 1

    if email_domain in FREE_EMAIL_DOMAINS:
        return 2

    if role:
        return 3

    # Someone else's address, e.g. the web designer in the footer.
    return None


def extract_business_email(soup, domain=""):

    best = None

    for email in find_emails(soup):
        rank = email_rank(email, domain)

        if rank is None:
            continue

        if best is None or rank < best[0]:
            best = (rank, email)

    return best[1] if best else ""


def find_contact_pages(base_url, soup):

    pages = []

    keywords = [
        "contact",
        "contact us",
        "get in touch",
        "about",
        "book",
        "appointment"
    ]

    base_domain = site_domain(base_url)

    for link in soup.find_all("a", href=True):

        href = link.get("href", "").strip()
        text = link.get_text(" ", strip=True).lower()
        combined = f"{href} {text}".lower()

        if not any(keyword in combined for keyword in keywords):
            continue

        full_url = urljoin(base_url, href).split("#")[0]

        # Only follow links on the same website
        # (www. and non-www. count as the same site)
        if site_domain(full_url) != base_domain:
            continue

        if not full_url.startswith(("http://", "https://")):
            continue

        if full_url.rstrip("/") == base_url.rstrip("/"):
            continue

        if full_url not in pages:
            pages.append(full_url)

    return pages[:3]


def fetch(url, timeout=15):
    try:
        return requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True
        )

    except requests.exceptions.SSLError:
        # Python is stricter than browsers about certificate chains,
        # so retry instead of reporting a working site as broken.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InsecureRequestWarning)

            return requests.get(
                url,
                headers=HEADERS,
                timeout=timeout,
                allow_redirects=True,
                verify=False
            )


def has_working_https(url):
    """The site answered on http://. Browsers try https:// first,
    so only call it insecure if the https:// version fails too."""

    secure_url = "https://" + url.split("://", 1)[-1]

    try:
        response = requests.get(
            secure_url,
            headers=HEADERS,
            timeout=8,
            allow_redirects=True
        )
    except requests.RequestException:
        return False

    return response.status_code < 400 and response.url.startswith("https://")


def whatsapp_from_link(href):
    match = re.search(
        r"(?:wa\.me/|phone=)\+?(\d{8,15})",
        href
    )
    return match.group(1) if match else ""


def scan_links(soup, result):
    """Look through every link for booking, contact, social, phone
    and WhatsApp signals. Used on the homepage and contact pages."""

    for link in soup.find_all("a", href=True):

        href = link.get("href", "").strip()
        text = link.get_text(" ", strip=True).lower()
        combined = f"{href} {text}".lower()

        if (
            BOOKING_PATTERN.search(combined)
            or any(site in combined for site in BOOKING_PLATFORMS)
        ):
            result["has_booking"] = True

        if "contact" in combined or "get in touch" in combined:
            result["has_contact_page"] = True

        link_domain = site_domain(href)

        if any(
            link_domain == site or link_domain.endswith("." + site)
            for site in SOCIAL_DOMAINS
        ):
            result["has_social_links"] = True

        if "whatsapp" in combined or "wa.me" in combined:
            result["has_whatsapp"] = True

            if not result["whatsapp"]:
                result["whatsapp"] = whatsapp_from_link(href)

        if href.lower().startswith("tel:"):
            result["has_phone"] = True

            if not result["phone"]:
                result["phone"] = href[4:].strip()

    # Booking widgets are often iframes, not links.
    for frame in soup.find_all("iframe", src=True):
        if any(site in frame["src"] for site in BOOKING_PLATFORMS):
            result["has_booking"] = True

    has_form = any(
        form.find("textarea") or form.find("input", attrs={"type": "email"})
        for form in soup.find_all("form")
    )

    if has_form:
        result["has_contact_form"] = True


def analyze_website(url):

    result = {
        "url": url,
        "final_url": "",
        "status": "none",
        "reachable": False,
        "title": "",
        "description": "",
        "text": "",
        "has_booking": False,
        "has_contact_page": False,
        "has_contact_form": False,
        "has_email": False,
        "business_email": "",
        "has_phone": False,
        "phone": "",
        "has_whatsapp": False,
        "whatsapp": "",
        "has_social_links": False,
        "mobile_friendly": False,
        "https": False,
        "copyright_year": None,
        "load_seconds": None,
        "cta_count": 0,
        "checked_on": date.today().isoformat(),
        "error": ""
    }

    url = normalize_url(url)
    result["url"] = url

    if not url:
        result["error"] = "No website provided"
        return result

    try:
        try:
            response = fetch(url)
        except requests.Timeout:
            response = fetch(url, timeout=30)

    except requests.RequestException as error:
        message = str(error)

        if "Failed to resolve" in message or "getaddrinfo" in message:
            # The domain no longer exists - there is no business
            # website (or email) left to pitch.
            result["status"] = "dead"
        else:
            # Refused connection or a second timeout: a visitor
            # would not be able to open this site either.
            result["status"] = "down"

        result["error"] = message[:300]
        return result

    result["final_url"] = response.url
    result["load_seconds"] = round(response.elapsed.total_seconds(), 1)

    server = response.headers.get("server", "").lower()

    if response.status_code in (401, 403, 406, 429) or (
        response.status_code == 503 and "cloudflare" in server
    ):
        # A firewall blocked our checker. That says nothing about
        # whether real visitors can see the site, so don't claim it.
        result["status"] = "blocked"
        result["error"] = f"HTTP {response.status_code} (blocked our checker)"
        return result

    if response.status_code >= 400:
        result["status"] = "down"
        result["error"] = f"HTTP {response.status_code}"
        return result

    result["status"] = "ok"
    result["reachable"] = True
    result["https"] = response.url.startswith("https://") or has_working_https(response.url)

    # Passing bytes lets BeautifulSoup read the page's own charset.
    soup = BeautifulSoup(response.content, "html.parser")
    domain = site_domain(response.url)

    if soup.title:
        result["title"] = soup.title.get_text(" ", strip=True)

    description = soup.find(
        "meta",
        attrs={"name": re.compile("^description$", re.I)}
    )

    if description:
        result["description"] = description.get("content", "").strip()

    viewport = soup.find(
        "meta",
        attrs={"name": re.compile("^viewport$", re.I)}
    )

    result["mobile_friendly"] = viewport is not None

    page_text = soup.get_text(" ", strip=True)
    result["text"] = page_text[:3000]

    if (
        len(page_text) < 150
        and len(soup.find_all("a", href=True)) < 5
        and soup.find("script") is not None
    ):
        # Built by JavaScript in the browser - we only see an empty
        # shell, so anything we said would be a guess.
        result["status"] = "thin"
        result["error"] = "Page is built with JavaScript - check it in a browser"
        return result

    years = [
        int(year)
        for year in COPYRIGHT_PATTERN.findall(page_text)
        if 1995 <= int(year) <= date.today().year
    ]

    if years:
        result["copyright_year"] = max(years)

    scan_links(soup, result)

    result["business_email"] = extract_business_email(soup, domain)

    if not result["phone"]:
        phone = PHONE_PATTERN.search(page_text)

        if phone:
            result["has_phone"] = True
            result["phone"] = phone.group(0).strip()

    # Contact/about pages usually hold the email, form and booking link.
    for page_url in find_contact_pages(response.url, soup):

        try:
            page_response = fetch(page_url, timeout=10)
            page_response.raise_for_status()
        except requests.RequestException:
            continue

        page_soup = BeautifulSoup(page_response.content, "html.parser")

        scan_links(page_soup, result)

        if not result["business_email"]:
            result["business_email"] = extract_business_email(
                page_soup,
                domain
            )

        if not result["phone"]:
            phone = PHONE_PATTERN.search(page_soup.get_text(" ", strip=True))

            if phone:
                result["has_phone"] = True
                result["phone"] = phone.group(0).strip()

    result["has_email"] = bool(result["business_email"])

    lower_text = page_text.lower()

    result["cta_count"] = sum(
        lower_text.count(word)
        for word in CTA_WORDS
    )

    return result


if __name__ == "__main__":

    test_url = "https://thedentistsinc.co.za/"

    result = analyze_website(test_url)

    print("\n==============================")
    print("WEBSITE ANALYSIS")
    print("==============================")

    for key, value in result.items():
        if key != "text":
            print(f"{key}: {value}")
