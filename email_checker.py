import dns.exception
import dns.resolver


_cache = {}


def check_email_domain(email):
    """Check the email's domain can receive mail (has MX records).

    Catches typos like gmail.con and dead domains before you send.
    Bounced emails are what get a Gmail account suspended.

    Returns "valid", "no_mx", "unknown" (lookup failed) or "none".
    """
    if not email or "@" not in email:
        return "none"

    domain = email.rsplit("@", 1)[1].lower()

    if domain in _cache:
        return _cache[domain]

    try:
        dns.resolver.resolve(domain, "MX", lifetime=6)
        status = "valid"

    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        status = "no_mx"

    except dns.exception.DNSException:
        status = "unknown"

    _cache[domain] = status
    return status
