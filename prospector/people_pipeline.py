"""
Criteria-driven PEOPLE finder — the ZoomInfo/Apollo-style workflow.

Input: user criteria (job titles/roles, location, industry keywords) + either a
search key (to discover companies) or a supplied list of company sites.

For each company:
  1. crawl home + team/about/contact pages
  2. extract PEOPLE (name + job title) and any published personal emails
  3. learn the company's email pattern from any known email on the domain
  4. for people without a published email, GUESS via the pattern engine
  5. VERIFY every email (MX + optional SMTP probe, catch-all aware)
  6. keep people whose title matches the user's role criteria

Optional Hunter email-finder is used as a fallback when enabled.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from .models import Prospect
from .patterns import apply_pattern, generate_candidates, infer_pattern
from .pipeline import registrable_domain, SKIP_DOMAINS

LogFn = Optional[Callable[[str], None]]
ResultFn = Optional[Callable[[Prospect], None]]


def _domain_from_site(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    net = urlparse(url).netloc.lower()
    return net[4:] if net.startswith("www.") else net


def title_matches(title: str, roles: List[str]) -> bool:
    """True if no roles given (keep all) or any role keyword is in the title."""
    if not roles:
        return True
    t = (title or "").lower()
    return any(r.strip().lower() in t for r in roles if r.strip())


def _learn_pattern(people: List[Dict[str, str]]) -> Optional[str]:
    """Infer the company email pattern from any person with a known email."""
    for p in people:
        if p.get("email"):
            pat = infer_pattern(p["name"], p["email"])
            if pat:
                return pat
    return None


def find_people_on_site(
    site_url: str,
    roles: List[str],
    *,
    crawler,
    do_smtp: bool = True,
    smtp_timeout: float = 8.0,
    smtp_from: Optional[str] = None,
    use_hunter: bool = False,
    on_log: LogFn = None,
) -> List[Prospect]:
    from bs4 import BeautifulSoup  # type: ignore

    from . import enrich
    from .compliance import classify_email, page_forbids_unsolicited
    from .people import extract_people
    from .verify import verify_email

    log = on_log or (lambda m: None)
    domain = registrable_domain(site_url)
    if not domain or domain in SKIP_DOMAINS:
        return []

    pages = crawler.collect_pages(site_url)
    if not pages:
        log(f"    ({domain}: no pages fetched)")
        return []

    company = ""
    forbids = False
    all_people: Dict[str, Dict[str, str]] = {}
    for url, html in pages:
        soup = BeautifulSoup(html, "html.parser")
        if not company and soup.title and soup.title.string:
            import re
            company = re.split(r"[|\-–—:]", soup.title.string)[0].strip()[:120]
        if page_forbids_unsolicited(soup.get_text(" ", strip=True)):
            forbids = True
        for person in extract_people(soup, url):
            key = person["name"].lower()
            cur = all_people.get(key)
            if cur is None:
                person["source_url"] = url
                all_people[key] = person
            else:
                if not cur.get("title") and person.get("title"):
                    cur["title"] = person["title"]
                if not cur.get("email") and person.get("email"):
                    cur["email"] = person["email"]

    people = list(all_people.values())
    if not people:
        log(f"    ({domain}: no named people found)")
        return []

    mail_domain = _domain_from_site(site_url)
    pattern = _learn_pattern(people)
    if pattern:
        log(f"    ({domain}: learned email pattern '{pattern}')")

    out: List[Prospect] = []
    matched = 0
    for person in people:
        if not title_matches(person.get("title", ""), roles):
            continue
        matched += 1
        name = person["name"]
        title = person.get("title", "")
        email = person.get("email", "")
        email_pattern = ""
        email_status = ""
        confidence = "low"
        note_bits = []

        if email:
            # Published personal email — strongest.
            email_pattern = infer_pattern(name, email) or ""
            confidence = "high"
            note_bits.append("email published on site")
        else:
            # Guess it.
            if pattern:
                guess = apply_pattern(pattern, name, mail_domain)
                if guess:
                    email = guess
                    email_pattern = pattern
                    confidence = "medium"
                    note_bits.append(f"inferred from company pattern '{pattern}'")
            if not email and use_hunter and enrich.enabled():
                parsed = person.get("name", "").split()
                if len(parsed) >= 2:
                    hit = enrich.find_email(mail_domain, parsed[0], parsed[-1])
                    if hit and hit.get("email"):
                        email = hit["email"]
                        confidence = "medium"
                        note_bits.append(f"hunter finder (conf {hit.get('confidence')})")
            if not email:
                cands = generate_candidates(name, mail_domain)
                if cands:
                    email, email_pattern = cands[0]
                    note_bits.append("top pattern guess (unconfirmed)")

        # Verify whatever email we ended with.
        mx_ok = ""
        if email:
            res = verify_email(email, do_smtp=do_smtp, timeout=smtp_timeout,
                               from_addr=smtp_from or os.getenv("SMTP_FROM", "verify@example.com"))
            email_status = str(res["status"])
            mx_ok = "yes" if res["mx"] else ("no" if res["mx"] is False else "unknown")
            if email_status == "verified" and confidence != "high":
                confidence = "high"
                note_bits.append("SMTP-verified")
            elif email_status == "invalid":
                confidence = "low"
                note_bits.append("failed verification")
            elif email_status == "accept_all":
                note_bits.append("domain is catch-all (can't confirm individual)")

        from .people import seniority_of
        status = "flagged" if forbids else "new"
        if forbids:
            note_bits.append("PAGE REQUESTS NO UNSOLICITED CONTACT")

        p = Prospect(
            practice_name=company or domain,
            company=company or domain,
            contact_name=name,
            title=title,
            email=email,
            email_type=classify_email(email) if email else "",
            email_status=email_status,
            email_pattern=email_pattern,
            website=site_url,
            source_url=person.get("source_url", site_url),
            seniority=seniority_of(title),
            confidence=confidence,
            status=status,
            mx_ok=mx_ok,
            notes="; ".join(note_bits),
        )
        out.append(p)
    log(f"    ({domain}: {len(people)} people, {matched} match role filter)")
    return out


def find_people(
    sites: List[str],
    roles: List[str],
    *,
    delay: float = 2.0,
    timeout: float = 15.0,
    max_pages: int = 6,
    do_smtp: bool = True,
    smtp_timeout: float = 8.0,
    smtp_from: Optional[str] = None,
    use_hunter: bool = False,
    on_log: LogFn = None,
    on_result: ResultFn = None,
) -> List[Prospect]:
    from .crawler import Crawler, DEFAULT_UA

    log = on_log or (lambda m: None)
    crawler = Crawler(
        user_agent=os.getenv("CRAWL_USER_AGENT", DEFAULT_UA),
        delay=float(os.getenv("CRAWL_DELAY_SECONDS", delay)),
        timeout=float(os.getenv("CRAWL_TIMEOUT", timeout)),
        max_pages=max_pages,
    )
    out: List[Prospect] = []
    seen: Set[str] = set()
    total = len(sites)
    for i, site in enumerate(sites, 1):
        dom = registrable_domain(site)
        if not dom or dom in SKIP_DOMAINS or dom in seen:
            continue
        seen.add(dom)
        log(f"[{i}/{total}] {dom} — finding people...")
        for p in find_people_on_site(
            site, roles, crawler=crawler, do_smtp=do_smtp, smtp_timeout=smtp_timeout,
            smtp_from=smtp_from, use_hunter=use_hunter, on_log=log,
        ):
            out.append(p)
            if on_result:
                on_result(p)
    return out


def build_people_queries(roles: List[str], location: str, industry: str) -> List[str]:
    """Build search queries to discover companies matching the criteria."""
    loc = location.strip()
    ind = industry.strip()
    role_terms = [r.strip() for r in roles if r.strip()] or [""]
    queries = []
    for r in role_terms:
        parts = [p for p in [r, ind, loc] if p]
        base = " ".join(parts)
        queries.append(f"{base} contact")
        queries.append(f'{base} "our team"')
        if ind:
            queries.append(f"{ind} {loc} clinic OR practice OR company")
    # de-dupe, preserve order
    seen, uniq = set(), []
    for q in queries:
        q = " ".join(q.split())
        if q and q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq


def discover_companies(
    roles: List[str], location: str, industry: str,
    per_query: int = 10, max_companies: int = 25, on_log: LogFn = None,
) -> List[str]:
    """Use the configured search provider to find company sites matching criteria."""
    from . import search

    log = on_log or (lambda m: None)
    if search.active_provider() == "none":
        log("No search key configured — supply company URLs instead (or add SERPAPI_API_KEY).")
        return []
    queries = build_people_queries(roles, location, industry)
    log(f"Discovering companies with {len(queries)} search queries...")
    urls: Set[str] = set()
    for q in queries:
        hits = search.search(q, num=per_query)
        urls.update(hits)
        log(f"  {len(hits):>2} results :: {q}")
    seen: Set[str] = set()
    out: List[str] = []
    for u in sorted(urls):
        d = registrable_domain(u)
        if not d or d in SKIP_DOMAINS or d in seen:
            continue
        seen.add(d)
        out.append(u)
    log(f"{len(out)} unique companies discovered.")
    return out[:max_companies]
