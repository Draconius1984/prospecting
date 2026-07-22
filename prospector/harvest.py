"""
Aggressive (but legal, public-data-only) email-discovery channels used to seed
pattern inference and directly surface work emails:

  * Search-engine DORKING with SERP-snippet extraction (needs a search key)
  * Wayback Machine archive mining (keyless)
  * name <-> email similarity matching

All sources here are public pages / public archives / licensed SERP APIs. The
illegal/high-risk techniques flagged by the research (breach dumps, authed
LinkedIn scraping, M365 login enumeration, raw Google scraping, VRFY/EXPN) are
deliberately NOT implemented. See docs/COMPLIANCE.md.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from .compliance import ROLE_PREFIXES, is_collectable_business_email, normalize_email
from .extract import deobfuscate
from .patterns import PATTERN_TEMPLATES, _ascii, _render, split_name

LogFn = Optional[callable]

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Research-recommended dork patterns ({d} = domain). Operators are low-risk;
# run them through a licensed SERP API, never raw google.com scraping.
DORK_TEMPLATES = [
    'site:{d} intext:"@{d}"',
    'site:{d} (inurl:contact OR inurl:team OR inurl:about OR inurl:staff OR inurl:leadership) intext:"@{d}"',
    'filetype:pdf site:{d} intext:"@{d}"',
    'intext:"@{d}" -site:{d}',
    'site:github.com intext:"@{d}"',
]


def _emails_from_text(text: str, domain: str) -> Set[str]:
    out: Set[str] = set()
    for m in _EMAIL_RE.findall(deobfuscate(text or "")):
        e = normalize_email(m)
        if e.endswith("@" + domain) and is_collectable_business_email(e):
            out.add(e)
    return out


def is_role_email(email: str) -> bool:
    local = email.split("@", 1)[0] if "@" in email else email
    base = re.split(r"[._\-]", local)[0]
    return local in ROLE_PREFIXES or base in ROLE_PREFIXES


def dork_domain_emails(domain: str, per_query: int = 8, fetch_pages: bool = True,
                       max_fetch: int = 8, on_log: LogFn = None) -> Set[str]:
    """Mine SERP snippets (and a few result pages) for @domain addresses."""
    from . import search
    log = on_log or (lambda m: None)
    if search.active_provider() == "none":
        return set()
    emails: Set[str] = set()
    to_fetch: List[str] = []
    for tpl in DORK_TEMPLATES:
        q = tpl.format(d=domain)
        try:
            results = search.search_rich(q, num=per_query)
        except Exception:
            results = []
        for r in results:
            snip = f"{r.get('title','')} {r.get('snippet','')} {r.get('url','')}"
            hits = _emails_from_text(snip, domain)
            emails |= hits
            if not hits and r.get("url"):
                to_fetch.append(r["url"])
    if fetch_pages and to_fetch:
        emails |= _fetch_pages_for_emails(to_fetch[:max_fetch], domain)
    if emails:
        log(f"    (dorking found {len(emails)} @{domain} address(es))")
    return emails


def _fetch_pages_for_emails(urls: List[str], domain: str) -> Set[str]:
    from .crawler import Crawler, DEFAULT_UA
    from .extract import extract_cfemails, extract_mailto
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception:
        return set()
    out: Set[str] = set()
    crawler = Crawler(user_agent=DEFAULT_UA, delay=1.0, timeout=12, max_pages=1)
    for u in urls:
        html = crawler.fetch(u)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for e in extract_mailto(soup) | extract_cfemails(soup):
            if e.endswith("@" + domain):
                out.add(e)
        out |= _emails_from_text(soup.get_text(" ", strip=True), domain)
    return out


def wayback_emails(domain: str, max_snapshots: int = 8, on_log: LogFn = None) -> Set[str]:
    """Recover emails from archived contact/team/about pages (keyless)."""
    log = on_log or (lambda m: None)
    try:
        import requests  # type: ignore
    except Exception:
        return set()
    try:
        cdx = requests.get(
            "http://web.archive.org/cdx/search/cdx",
            params={"url": f"{domain}*", "output": "json", "fl": "original,timestamp",
                    "collapse": "urlkey", "limit": "400"},
            timeout=20,
        )
        rows = cdx.json()[1:]  # first row is the header
    except Exception:
        return set()
    wanted = re.compile(r"(contact|team|about|staff|our-?people|practitioner|clinician)", re.I)
    picks = [(o, t) for o, t in rows if wanted.search(o)][:max_snapshots]
    emails: Set[str] = set()
    for original, ts in picks:
        try:
            snap = requests.get(f"http://web.archive.org/web/{ts}id_/{original}", timeout=15)
            emails |= _emails_from_text(snap.text, domain)
        except Exception:
            continue
    if emails:
        log(f"    (wayback found {len(emails)} archived @{domain} address(es))")
    return emails


def gather_domain_emails(domain: str, deep: bool = True, use_wayback: bool = True,
                         on_log: LogFn = None) -> Set[str]:
    """All aggressive channels combined -> set of real @domain addresses."""
    emails: Set[str] = set()
    if deep:
        emails |= dork_domain_emails(domain, on_log=on_log)
        if use_wayback:
            emails |= wayback_emails(domain, on_log=on_log)
    return emails


def match_email_to_name(name: str, emails: Set[str]) -> Optional[str]:
    """Pick the address whose local-part best matches this person's name."""
    parsed = split_name(name)
    if not parsed:
        return None
    first, last = parsed
    # 1) exact template match (strongest)
    for tpl in PATTERN_TEMPLATES:
        want = _ascii(_render(tpl, first, last))
        for e in emails:
            if _ascii(e.split("@", 1)[0]) == want:
                return e
    # 2) local contains both name tokens
    for e in emails:
        local = _ascii(e.split("@", 1)[0])
        if first in local and last in local:
            return e
    return None


def pairs_for_pattern(people: List[Dict[str, str]], harvested: Set[str]) -> List[Tuple[str, str]]:
    """
    Build (name, email) pairs to infer the company pattern: published emails on
    the team page, plus harvested emails we can confidently tie to a name.
    Role/shared inboxes are excluded so they don't corrupt inference.
    """
    pairs: List[Tuple[str, str]] = []
    for p in people:
        e = p.get("email", "")
        if e and not is_role_email(e):
            pairs.append((p["name"], e))
    personal = {e for e in harvested if not is_role_email(e)}
    for p in people:
        if p.get("email"):
            continue
        m = match_email_to_name(p["name"], personal)
        if m:
            pairs.append((p["name"], m))
    return pairs
