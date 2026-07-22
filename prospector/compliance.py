"""
Compliance filters.

This module keeps collection limited to *conspicuously published business
email addresses* and helps you honour Australia's Spam Act 2003 and the
Privacy Act 1988. See docs/COMPLIANCE.md for the full guidance.

Nothing here is legal advice — it is a set of sensible technical guardrails.
"""

from __future__ import annotations

import re
from typing import Optional

# Role / shared-inbox local parts. Emails to these are business contacts and
# are the safest to use for inferred-consent B2B outreach.
ROLE_PREFIXES = {
    "info", "admin", "administration", "reception", "referral", "referrals",
    "intake", "hello", "contact", "enquiries", "enquiry", "inquiries",
    "inquiry", "bookings", "booking", "appointments", "office", "practice",
    "clinic", "mail", "team", "support", "accounts", "hr", "careers",
    "jobs", "ndis", "therapy", "ot", "frontdesk", "front.desk",
}

# Free mailbox providers — legitimate for small clinics but worth flagging.
FREE_PROVIDERS = {
    "gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "yahoo.com.au",
    "bigpond.com", "bigpond.net.au", "live.com", "icloud.com", "me.com",
    "optusnet.com.au", "iinet.net.au", "internode.on.net",
}

# Substrings that indicate a non-human / system / placeholder / asset email
# rather than a real business contact.
_SYSTEM_MARKERS = (
    "example.com", "example.org", "yourdomain", "domain.com", "email.com",
    "sentry.io", "sentry-next", "wixpress.com", "wix.com", "squarespace",
    "godaddy", "cloudflare", "no-reply", "noreply", "donotreply",
    "do-not-reply", "u003e", "u003c", "@2x", "sentry.",
)

# Image / asset filenames sometimes match the email regex (e.g. logo@2x.png).
_ASSET_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".css", ".js")

# Phrases that indicate the page/owner does NOT want unsolicited contact.
_NO_UNSOLICITED = (
    "no unsolicited", "do not contact", "no marketing", "no cold call",
    "no cold-call", "unsolicited emails will", "unsolicited email will",
    "will not accept unsolicited", "do not accept unsolicited",
    "not accept unsolicited", "unsolicited marketing", "unsolicited commercial",
    "no sales calls", "no solicitation", "not accept marketing",
)


def normalize_email(email: str) -> str:
    return (email or "").strip().strip(".,;:<>()[]\"'").lower()


def domain_of(email: str) -> str:
    email = normalize_email(email)
    return email.split("@", 1)[1] if "@" in email else ""


def looks_like_system_email(email: str) -> bool:
    """True for placeholder / asset / no-reply / tracking addresses."""
    e = normalize_email(email)
    if not e or "@" not in e:
        return True
    if e.endswith(_ASSET_EXT):
        return True
    return any(marker in e for marker in _SYSTEM_MARKERS)


def classify_email(email: str) -> str:
    """Return 'generic' (role/shared inbox), 'personal' (named), or 'unknown'."""
    e = normalize_email(email)
    if "@" not in e:
        return "unknown"
    local = e.split("@", 1)[0]
    base = re.split(r"[._-]", local)[0]
    if local in ROLE_PREFIXES or base in ROLE_PREFIXES:
        return "generic"
    # firstname.lastname / first.last style => personal
    if re.fullmatch(r"[a-z]+[._][a-z]+", local) or re.fullmatch(r"[a-z]{2,}", local):
        return "personal"
    return "unknown"


def is_free_provider(email: str) -> bool:
    return domain_of(email) in FREE_PROVIDERS


def page_forbids_unsolicited(text: Optional[str]) -> bool:
    """True if the page text asks not to be contacted for marketing."""
    if not text:
        return False
    low = text.lower()
    return any(p in low for p in _NO_UNSOLICITED)


def is_collectable_business_email(email: str) -> bool:
    """
    Gate an email should pass before we keep it: it must be a syntactically
    plausible, non-system address. (Free-provider addresses are allowed but
    flagged elsewhere.)
    """
    e = normalize_email(email)
    if "@" not in e or "." not in e.split("@", 1)[1]:
        return False
    return not looks_like_system_email(e)
