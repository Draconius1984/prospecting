"""
Shared engine used by BOTH the CLI (ot_prospector.py) and the web app
(webapp/app.py). Keeping the crawl/discover/validate logic here means the two
front-ends behave identically.

Callbacks:
    on_log(msg: str)          -> progress line (printed by CLI, streamed by web)
    on_result(p: Prospect)    -> emit a record as soon as it's found (live table)
"""

from __future__ import annotations

import csv
import os
from typing import Callable, Iterable, List, Optional, Set
from urllib.parse import urlparse

from .compliance import classify_email, is_free_provider
from .extract import first_email_by_type
from .models import CSV_FIELDS, Prospect

LogFn = Optional[Callable[[str], None]]
ResultFn = Optional[Callable[[Prospect], None]]

# Directory / social / aggregator domains — we use them to *find* clinics, but
# don't scrape emails from them (that would grab the directory's address).
SKIP_DOMAINS: Set[str] = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "yelp.com.au", "yellowpages.com.au",
    "healthengine.com.au", "healthdirect.gov.au", "ndis.gov.au",
    "cylex-australia.com", "halaxy.com", "google.com", "maps.google.com",
    "wikipedia.org", "gumtree.com.au", "seek.com.au", "indeed.com",
    "truelocal.com.au", "hotfrog.com.au", "localsearch.com.au",
    "otaus.com.au", "ahpra.gov.au", "health.qld.gov.au",
}

_TLD_EXTRACTOR = None


def registrable_domain(url: str) -> str:
    global _TLD_EXTRACTOR
    if not url:
        return ""
    url = url.strip().lstrip("﻿")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    netloc = urlparse(url).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    try:
        import tldextract  # type: ignore

        if _TLD_EXTRACTOR is None:
            # suffix_list_urls=() -> bundled snapshot only, never the network.
            _TLD_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())
        ext = _TLD_EXTRACTOR(url)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}"
    except Exception:
        pass
    return netloc


def read_prospects(path: str) -> List[Prospect]:
    """Read a CSV of prospects, or a .txt of one URL per line."""
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    rows: List[Prospect] = []
    if path.lower().endswith(".txt"):
        with open(path, encoding="utf-8-sig") as fh:
            for line in fh:
                url = line.strip()
                if url and not url.startswith("#"):
                    rows.append(Prospect(website=url, source_url=url))
        return rows
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            rows.append(Prospect.from_row(row))
    return rows


def urls_from_text(text: str) -> List[Prospect]:
    """Turn a pasted block of URLs (one per line) into Prospect seeds."""
    rows: List[Prospect] = []
    for line in (text or "").splitlines():
        url = line.strip()
        if url and not url.startswith("#"):
            rows.append(Prospect(website=url, source_url=url))
    return rows


def write_prospects(path: str, prospects: Iterable[Prospect]) -> int:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    n = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for p in prospects:
            writer.writerow(p.to_row())
            n += 1
    return n


def dedupe(prospects) -> List[Prospect]:
    seen: Set[str] = set()
    out: List[Prospect] = []
    for p in prospects:
        k = p.key()
        if not k or k == "|" or k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


def _rows_from_crawl(url: str, res: dict) -> List[Prospect]:
    emails = sorted(res["emails"])
    phone = sorted(res["phones"])[0] if res["phones"] else ""
    name = res["name"] or registrable_domain(url)
    src = res["pages"][0] if res["pages"] else url
    note = "PAGE REQUESTS NO UNSOLICITED CONTACT — exclude from outreach" if res["forbids_unsolicited"] else ""

    if not emails:
        return [Prospect(
            practice_name=name, website=url, source_url=src,
            status="crawled", confidence="low", notes=note or "no published email found",
        )]

    primary = first_email_by_type(emails)
    rows: List[Prospect] = []
    for e in emails:
        flags = []
        if is_free_provider(e):
            flags.append("free-provider mailbox")
        if e != primary:
            flags.append("secondary")
        rows.append(Prospect(
            practice_name=name,
            email=e,
            email_type=classify_email(e),
            phone=phone,
            website=url,
            source_url=src,
            confidence="high",
            status="flagged" if res["forbids_unsolicited"] else "crawled",
            notes="; ".join([n for n in [note] + flags if n]),
        ))
    return rows


def crawl_sites(
    urls: List[str],
    *,
    delay: float = 2.0,
    timeout: float = 15.0,
    max_pages: int = 5,
    user_agent: Optional[str] = None,
    on_log: LogFn = None,
    on_result: ResultFn = None,
) -> List[Prospect]:
    """Crawl each unique domain and return the Prospect rows found."""
    from .crawler import Crawler, DEFAULT_UA

    log = on_log or (lambda m: None)
    crawler = Crawler(
        user_agent=user_agent or os.getenv("CRAWL_USER_AGENT", DEFAULT_UA),
        delay=float(os.getenv("CRAWL_DELAY_SECONDS", delay)),
        timeout=float(os.getenv("CRAWL_TIMEOUT", timeout)),
        max_pages=max_pages,
    )

    out: List[Prospect] = []
    seen: Set[str] = set()
    total = len(urls)
    for i, url in enumerate(urls, 1):
        dom = registrable_domain(url)
        if not dom or dom in SKIP_DOMAINS or dom in seen:
            continue
        seen.add(dom)
        log(f"[{i}/{total}] crawling {dom} ...")
        res = crawler.crawl_site(url)
        if res["blocked"]:
            log(f"    ({dom}: no page fetched — robots.txt block, unreachable, or TLS error)")
            continue
        rows = _rows_from_crawl(url, res)
        got = sum(1 for r in rows if r.email)
        log(f"    ({dom}: {got} email(s) found)")
        for r in rows:
            out.append(r)
            if on_result:
                on_result(r)
    return out


def discover_urls(regions=None, per_query: int = 10, on_log: LogFn = None) -> List[str]:
    """Use the configured search provider to find candidate clinic URLs."""
    from . import search, sources

    log = on_log or (lambda m: None)
    provider = search.active_provider()
    if provider == "none":
        log("No search provider configured — returning curated directory URLs only.")
        return [s["url"] for s in sources.CURATED_SOURCES]

    region_list = regions if regions else sources.QLD_REGIONS
    queries = sources.build_queries(region_list)
    log(f"Using '{provider}'. Running {len(queries)} queries ...")
    url_set: Set[str] = set()
    for q in queries:
        hits = search.search(q, num=per_query)
        url_set.update(hits)
        log(f"  {len(hits):>2} results :: {q}")
    return sorted(url_set)


def validate_prospects(prospects: List[Prospect], on_log: LogFn = None) -> int:
    """Set mx_ok/status on each prospect with an email. Returns #checked."""
    from .validate import validate_email

    log = on_log or (lambda m: None)
    checked = 0
    for r in prospects:
        if not r.email:
            continue
        res = validate_email(r.email)
        r.mx_ok = res["mx_label"]
        if not res["syntax"]:
            r.status = "flagged"
            r.notes = (r.notes + "; invalid syntax").strip("; ")
        elif res["mx"] is False:
            r.status = "flagged"
            r.notes = (r.notes + "; domain has no MX (may not receive mail)").strip("; ")
        elif r.status in ("new", "crawled"):
            r.status = "validated"
        checked += 1
    log(f"Validated {checked} email(s).")
    return checked
