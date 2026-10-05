import os
import re
from urllib.parse import urlparse

from ddgs import DDGS
from ddgs.exceptions import DDGSException


DIRECTORY_DOMAINS = {
    "whatclinic.com",
    "getadoc.co.za",
    "topreviews.co.za",
    "yellosa.co.za",
    "yellowpages.com",
    "yellowpages-south-africa.com",
    "brabys.com",
    "cylex.co.za",
    "snupit.co.za",
    "hellopeter.com",
    "sayellow.com",
    "infoisinfo.co.za",
    "sa-venues.com",
    "localbusinessdirectory.co.za",
    "gumtree.co.za",
    "yelp.com",
    "tripadvisor.com",
    "tripadvisor.co.za",
    "google.com",
    "wikipedia.org",
    "medpages.info",
    "healthbridge.co.za",
    "doctoralia.co.za",
    "booksy.com",
    "fresha.com",
    "treatwell.co.za",
    "sweepsouth.com",
    "pretoria.co.za",
    "joburg.co.za",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "pinterest.com",
}


# Titles that are almost always a list of businesses, not one business.
LIST_TITLE_PATTERN = re.compile(
    r"\b(top \d+|best \d+|\d+ best|directory|near me|list of)\b",
    re.IGNORECASE
)


def is_directory(url):
    domain = urlparse(url).netloc.lower()
    domain = domain.removeprefix("www.")

    return any(
        domain == blocked or domain.endswith("." + blocked)
        for blocked in DIRECTORY_DOMAINS
    )


def clean_business_name(title):
    """'Home | Smile Dental - Best Dentist in Joburg' -> 'Smile Dental'"""

    parts = [
        part.strip()
        for part in re.split(r"\s+[|\-–—:•]\s+", title or "")
        if part.strip()
    ]

    generic = {"home", "home page", "homepage", "welcome", "contact us", "about us"}

    parts = [part for part in parts if part.lower() not in generic]

    if not parts:
        return (title or "").strip()

    # Usually the name comes first; the local AI also returns a
    # clean name later, which replaces this guess.
    return parts[0]


def discover_businesses(niche, location, max_results=10):

    queries = [
        f"{niche} in {location} official website",
        f"{niche} {location} contact us",
        f"independent {niche} practices in {location}",
        f"{niche} {location}",
        f"{niche} near {location}",
    ]

    businesses = []
    seen_domains = set()

    try:

        with DDGS() as search:

            for query in queries:

                print(f"\nSearching: {query}")

                try:

                    results = search.text(
                        query,
                        max_results=max_results
                    )

                except DDGSException as error:

                    print(
                        f"Search failed for this query: {error}"
                    )

                    print("Trying the next search...")
                    continue

                except Exception as error:

                    print(
                        f"Unexpected search error: {error}"
                    )

                    print("Trying the next search...")
                    continue

                for result in results:

                    url = result.get("href", "").strip()
                    title = result.get("title", "").strip()
                    snippet = result.get("body", "").strip()

                    if not url.startswith(
                        ("http://", "https://")
                    ):
                        continue

                    parsed = urlparse(url)
                    domain = parsed.netloc.lower()
                    domain = domain.removeprefix("www.")

                    if not domain:
                        continue

                    if is_directory(url):
                        continue

                    if LIST_TITLE_PATTERN.search(title):
                        continue

                    if domain in seen_domains:
                        continue

                    seen_domains.add(domain)

                    businesses.append({
                        "business_name": clean_business_name(title),
                        "search_title": title,
                        "location": location,
                        # Check the homepage, not whichever page
                        # the search happened to return.
                        "website": f"{parsed.scheme}://{parsed.netloc}/",
                        "search_evidence": snippet,
                        "phone": "",
                        "source": "web search",
                        "verified": False,
                    })

                    print(
                        f"  + Found: {title}"
                    )

                    if len(businesses) >= max_results:
                        return businesses

    except Exception as error:

        print(
            f"\nDiscovery system error: {error}"
        )

    return businesses


def discover_all(niche, location, max_results=10, log=print):
    """Google Places first (if a key is set), then web search.

    Places also returns businesses with NO website - the
    strongest leads for a website agency, which a web search
    can never find.
    """
    businesses = []

    if os.getenv("GOOGLE_PLACES_API_KEY"):

        from lead_finder import find_leads

        try:
            places = find_leads(niche, location, max_results=max_results)
            log(f"Google Places: {len(places)} businesses")
            businesses.extend(places)

        except Exception as error:
            log(f"Google Places failed ({error}) - using web search only")

    web = discover_businesses(niche, location, max_results=max_results)
    log(f"Web search: {len(web)} websites")

    seen = set()
    merged = []

    for business in businesses + web:

        domain = urlparse(business.get("website", "")).netloc.lower()
        domain = domain.removeprefix("www.")
        name = business.get("business_name", "").strip().lower()

        key = domain or name

        if not key or key in seen or (name and name in seen):
            continue

        seen.add(key)

        if name:
            seen.add(name)

        merged.append(business)

    return merged


if __name__ == "__main__":

    leads = discover_businesses(
        niche="dentists",
        location="Johannesburg",
        max_results=10
    )

    print("\n==============================")
    print("DISCOVERY RESULTS")
    print("==============================")

    for lead in leads:

        print("\n--------------------------")
        print("Business:", lead["business_name"])
        print("Website:", lead["website"])
        print("Evidence:", lead["search_evidence"])
