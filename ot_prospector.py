#!/usr/bin/env python3
"""
OT Prospector — compliance-first B2B prospecting for occupational therapy
providers in Queensland, Australia.

Quick start:
    python ot_prospector.py sources                       # list public directories
    python ot_prospector.py crawl  --input data/prospects.csv --out data/crawled.csv
    python ot_prospector.py discover --regions all --out data/discovered.csv   # needs search key
    python ot_prospector.py validate --input data/crawled.csv --out data/validated.csv
    python ot_prospector.py enrich   --input data/crawled.csv --out data/enriched.csv  # needs HUNTER key
    python ot_prospector.py dedupe   --inputs a.csv b.csv --out data/master.csv

Run `python ot_prospector.py <command> -h` for per-command options.
See docs/COMPLIANCE.md before you send anything.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Dict, Iterable, List, Set

# Load .env if python-dotenv is available (optional).
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

from prospector import __version__
from prospector.models import CSV_FIELDS, Prospect

# Domains that are directories/social/aggregators, not individual clinics.
SKIP_DOMAINS = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "tiktok.com", "yelp.com.au", "yellowpages.com.au",
    "healthengine.com.au", "healthdirect.gov.au", "ndis.gov.au",
    "cylex-australia.com", "halaxy.com", "google.com", "maps.google.com",
    "wikipedia.org", "gumtree.com.au", "seek.com.au", "indeed.com",
    "truelocal.com.au", "hotfrog.com.au", "localsearch.com.au",
    "otaus.com.au", "ahpra.gov.au", "health.qld.gov.au",
}


# --------------------------------------------------------------------------
# CSV helpers
# --------------------------------------------------------------------------
def read_prospects(path: str) -> List[Prospect]:
    if not os.path.exists(path):
        sys.exit(f"Input not found: {path}")
    rows: List[Prospect] = []
    if path.lower().endswith(".txt"):
        with open(path, encoding="utf-8-sig") as fh:
            for line in fh:
                url = line.strip()
                if url and not url.startswith("#"):
                    rows.append(Prospect(website=url, source_url=url))
        return rows
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(Prospect.from_row(row))
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


def dedupe(prospects: Iterable[Prospect]) -> List[Prospect]:
    seen: Set[str] = set()
    out: List[Prospect] = []
    for p in prospects:
        k = p.key()
        if not k or k == "|":
            continue
        if k in seen:
            continue
        seen.add(k)
        out.append(p)
    return out


_TLD_EXTRACTOR = None


def registrable_domain(url: str) -> str:
    from urllib.parse import urlparse

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
            # suffix_list_urls=() -> use the bundled snapshot only, never the network.
            _TLD_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())
        ext = _TLD_EXTRACTOR(url)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}"
    except Exception:
        pass
    return netloc


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------
def cmd_sources(args) -> None:
    from prospector.sources import CURATED_SOURCES

    print(f"\nCurated public Queensland OT sources ({len(CURATED_SOURCES)}):\n")
    for s in CURATED_SOURCES:
        print(f"  • {s['name']}  [{s['type']}]")
        print(f"      {s['url']}")
        print(f"      {s['note']}\n")
    print("Tip: open these, filter to your target region, and export the clinic")
    print("websites into a .txt or CSV, then run `crawl` to pull published emails.\n")


def _crawl_urls(urls: List[str], args) -> List[Prospect]:
    from prospector.crawler import Crawler
    from prospector.compliance import classify_email, is_free_provider
    from prospector.extract import first_email_by_type

    crawler = Crawler(
        user_agent=os.getenv("CRAWL_USER_AGENT", "OT-Prospector/1.0 (+B2B research bot; respects robots.txt)"),
        delay=float(os.getenv("CRAWL_DELAY_SECONDS", args.delay)),
        timeout=float(os.getenv("CRAWL_TIMEOUT", 15)),
        max_pages=args.max_pages,
    )

    out: List[Prospect] = []
    seen_domains: Set[str] = set()
    total = len(urls)
    for i, url in enumerate(urls, 1):
        dom = registrable_domain(url)
        if not dom or dom in SKIP_DOMAINS or dom in seen_domains:
            continue
        seen_domains.add(dom)
        print(f"  [{i}/{total}] crawling {dom} ...")
        res = crawler.crawl_site(url)
        if res["blocked"]:
            print("      (no page fetched: robots.txt block, unreachable, or TLS/cert error)")
            continue
        emails = sorted(res["emails"])
        phone = sorted(res["phones"])[0] if res["phones"] else ""
        name = res["name"] or dom
        note = ""
        if res["forbids_unsolicited"]:
            note = "PAGE REQUESTS NO UNSOLICITED CONTACT — exclude from outreach"

        if not emails:
            out.append(Prospect(
                practice_name=name, website=url, source_url=res["pages"][0] if res["pages"] else url,
                status="crawled", confidence="low", notes=note or "no published email found",
            ))
            continue

        primary = first_email_by_type(emails)
        for e in emails:
            flags = []
            if is_free_provider(e):
                flags.append("free-provider mailbox")
            if e != primary:
                flags.append("secondary")
            out.append(Prospect(
                practice_name=name,
                email=e,
                email_type=classify_email(e),
                phone=phone,
                website=url,
                source_url=res["pages"][0] if res["pages"] else url,
                confidence="high",
                status="flagged" if res["forbids_unsolicited"] else "crawled",
                notes="; ".join([n for n in [note] + flags if n]),
            ))
    return out


def cmd_crawl(args) -> None:
    rows = read_prospects(args.input)
    urls = [r.website or r.source_url for r in rows if (r.website or r.source_url)]
    print(f"\nCrawling {len(urls)} site(s) from {args.input} ...")
    found = dedupe(_crawl_urls(urls, args))
    n = write_prospects(args.out, found)
    with_email = sum(1 for p in found if p.email)
    print(f"\nDone. Wrote {n} records ({with_email} with an email) -> {args.out}\n")


def cmd_discover(args) -> None:
    from prospector import search, sources

    provider = search.active_provider()
    if provider == "none":
        print("\nNo search provider configured (SERPAPI_API_KEY / GOOGLE_CSE_* / BING_SEARCH_API_KEY).")
        print("Falling back to crawling the curated directory homepages, which is limited.")
        print("For real discovery, add a search key (see config.example.env) or use `crawl`")
        print("on a list of clinic websites.\n")
        urls = [s["url"] for s in sources.CURATED_SOURCES]
    else:
        regions = sources.QLD_REGIONS
        if args.regions and args.regions != "all":
            wanted = {r.strip().lower() for r in args.regions.split(",")}
            regions = [r for r in sources.QLD_REGIONS if r["region"].lower() in wanted] or sources.QLD_REGIONS
        queries = sources.build_queries(regions)
        print(f"\nUsing '{provider}'. Running {len(queries)} queries ...")
        url_set: Set[str] = set()
        for q in queries:
            hits = search.search(q, num=args.per_query)
            url_set.update(hits)
            print(f"  {len(hits):>2} results  ::  {q}")
        urls = sorted(url_set)
        print(f"\n{len(urls)} candidate URLs discovered; crawling clinic sites ...")

    found = dedupe(_crawl_urls(urls, args))
    n = write_prospects(args.out, found)
    with_email = sum(1 for p in found if p.email)
    print(f"\nDone. Wrote {n} records ({with_email} with an email) -> {args.out}\n")


def cmd_enrich(args) -> None:
    from prospector import enrich
    from prospector.compliance import classify_email

    if not enrich.enabled():
        sys.exit("HUNTER_API_KEY not set (or 'requests' missing). Enrichment unavailable.")

    rows = read_prospects(args.input)
    domains: Dict[str, Prospect] = {}
    for r in rows:
        dom = registrable_domain(r.website or r.source_url)
        if dom and dom not in SKIP_DOMAINS and dom not in domains:
            domains[dom] = r

    print(f"\nEnriching {len(domains)} domain(s) via Hunter.io ...")
    out: List[Prospect] = list(rows)
    for i, (dom, ref) in enumerate(domains.items(), 1):
        print(f"  [{i}/{len(domains)}] {dom}")
        for e in enrich.domain_search(dom, min_confidence=args.min_confidence):
            name = (f"{e['first_name']} {e['last_name']}").strip()
            out.append(Prospect(
                practice_name=ref.practice_name or dom,
                contact_name=name,
                region=ref.region,
                email=e["email"],
                email_type=e["type"] or classify_email(e["email"]),
                website=ref.website,
                source_url=f"hunter.io domain-search:{dom}",
                services=e["position"],
                confidence="medium",
                status="enriched",
                notes=f"hunter confidence {e['confidence']}",
            ))
    found = dedupe(out)
    n = write_prospects(args.out, found)
    print(f"\nDone. Wrote {n} records -> {args.out}\n")


def cmd_validate(args) -> None:
    from prospector.validate import validate_email

    rows = read_prospects(args.input)
    checked = 0
    for r in rows:
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
    n = write_prospects(args.out, rows)
    good = sum(1 for r in rows if r.mx_ok == "yes")
    print(f"\nValidated {checked} email(s): {good} with working MX. Wrote {n} -> {args.out}\n")


def cmd_dedupe(args) -> None:
    combined: List[Prospect] = []
    for path in args.inputs:
        combined.extend(read_prospects(path))
    found = dedupe(combined)
    n = write_prospects(args.out, found)
    print(f"\nMerged {len(args.inputs)} file(s): {len(combined)} rows -> {n} unique -> {args.out}\n")


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ot_prospector",
        description="Compliance-first B2B prospecting for QLD occupational therapists.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Read docs/COMPLIANCE.md before contacting anyone. Not legal advice.",
    )
    p.add_argument("--version", action="version", version=f"OT Prospector {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("sources", help="List curated public QLD OT directories.")
    sp.set_defaults(func=cmd_sources)

    cp = sub.add_parser("crawl", help="Crawl clinic websites (CSV/txt) for published emails.")
    cp.add_argument("--input", required=True, help="CSV (with website/source_url column) or .txt of URLs.")
    cp.add_argument("--out", default="data/crawled.csv")
    cp.add_argument("--delay", type=float, default=2.0, help="Seconds between requests (default 2).")
    cp.add_argument("--max-pages", type=int, default=5, help="Max pages per site (default 5).")
    cp.set_defaults(func=cmd_crawl)

    dp = sub.add_parser("discover", help="Search + crawl to find clinics (needs a search key).")
    dp.add_argument("--regions", default="all", help="'all' or comma list, e.g. 'Brisbane,Gold Coast'.")
    dp.add_argument("--per-query", type=int, default=10, help="Results per query (default 10).")
    dp.add_argument("--delay", type=float, default=2.0)
    dp.add_argument("--max-pages", type=int, default=5)
    dp.add_argument("--out", default="data/discovered.csv")
    dp.set_defaults(func=cmd_discover)

    ep = sub.add_parser("enrich", help="Add role/personal emails per domain via Hunter.io.")
    ep.add_argument("--input", required=True)
    ep.add_argument("--out", default="data/enriched.csv")
    ep.add_argument("--min-confidence", type=int, default=50)
    ep.set_defaults(func=cmd_enrich)

    vp = sub.add_parser("validate", help="Check email syntax + MX records.")
    vp.add_argument("--input", required=True)
    vp.add_argument("--out", default="data/validated.csv")
    vp.set_defaults(func=cmd_validate)

    mp = sub.add_parser("dedupe", help="Merge + de-duplicate several CSVs by email.")
    mp.add_argument("--inputs", nargs="+", required=True)
    mp.add_argument("--out", default="data/master.csv")
    mp.set_defaults(func=cmd_dedupe)

    return p


def main(argv: List[str] = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
