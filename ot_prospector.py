#!/usr/bin/env python3
"""
OT Prospector — compliance-first B2B prospecting for occupational therapy
providers in Queensland, Australia.

Two front-ends share one engine (prospector/pipeline.py):
  * this CLI
  * a local web app —  python webapp/app.py  then open http://localhost:5000

Quick start:
    python ot_prospector.py sources
    python ot_prospector.py crawl  --input data/prospects.csv --out data/crawled.csv
    python ot_prospector.py discover --regions all --out data/discovered.csv   # needs search key
    python ot_prospector.py validate --input data/crawled.csv --out data/validated.csv
    python ot_prospector.py enrich   --input data/crawled.csv --out data/enriched.csv  # needs HUNTER key
    python ot_prospector.py dedupe   --inputs a.csv b.csv --out data/master.csv

See docs/COMPLIANCE.md before you send anything.
"""

from __future__ import annotations

import argparse
import sys
from typing import Dict, List

# Load .env if python-dotenv is available (optional).
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

from prospector import __version__
from prospector.models import Prospect
from prospector.pipeline import (
    SKIP_DOMAINS,
    crawl_sites,
    dedupe,
    discover_urls,
    read_prospects,
    registrable_domain,
    validate_prospects,
    write_prospects,
)


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


def cmd_crawl(args) -> None:
    rows = read_prospects(args.input)
    urls = [r.website or r.source_url for r in rows if (r.website or r.source_url)]
    print(f"\nCrawling {len(urls)} site(s) from {args.input} ...")
    found = dedupe(crawl_sites(
        urls, delay=args.delay, max_pages=args.max_pages,
        on_log=lambda m: print("  " + m),
    ))
    n = write_prospects(args.out, found)
    with_email = sum(1 for p in found if p.email)
    print(f"\nDone. Wrote {n} records ({with_email} with an email) -> {args.out}\n")


def cmd_discover(args) -> None:
    from prospector import search, sources

    if search.active_provider() == "none":
        print("\nNo search provider configured (SERPAPI_API_KEY / GOOGLE_CSE_* / BING_SEARCH_API_KEY).")
        print("Falling back to crawling the curated directory homepages, which is limited.")
        print("For real discovery, add a search key (see config.example.env) or use `crawl`.\n")
        regions = None
    else:
        regions = sources.QLD_REGIONS
        if args.regions and args.regions != "all":
            wanted = {r.strip().lower() for r in args.regions.split(",")}
            regions = [r for r in sources.QLD_REGIONS if r["region"].lower() in wanted] or sources.QLD_REGIONS

    urls = discover_urls(regions=regions, per_query=args.per_query, on_log=print)
    print(f"\n{len(urls)} candidate URL(s); crawling clinic sites ...")
    found = dedupe(crawl_sites(
        urls, delay=args.delay, max_pages=args.max_pages,
        on_log=lambda m: print("  " + m),
    ))
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
            name = f"{e['first_name']} {e['last_name']}".strip()
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
    rows = read_prospects(args.input)
    validate_prospects(rows, on_log=print)
    n = write_prospects(args.out, rows)
    good = sum(1 for r in rows if r.mx_ok == "yes")
    print(f"\n{good} email(s) with working MX. Wrote {n} -> {args.out}\n")


def cmd_dedupe(args) -> None:
    combined: List[Prospect] = []
    for path in args.inputs:
        combined.extend(read_prospects(path))
    found = dedupe(combined)
    n = write_prospects(args.out, found)
    print(f"\nMerged {len(args.inputs)} file(s): {len(combined)} rows -> {n} unique -> {args.out}\n")


def cmd_people(args) -> None:
    from prospector.people_pipeline import discover_companies, find_people

    roles = [r.strip() for r in (args.roles or "").split(",") if r.strip()]
    if args.input:
        sites = [r.website or r.source_url for r in read_prospects(args.input) if (r.website or r.source_url)]
        print(f"\nFinding people on {len(sites)} supplied site(s)...")
    else:
        print(f"\nDiscovering companies: roles={roles} industry='{args.industry}' location='{args.location}'")
        sites = discover_companies(
            roles, args.location, args.industry,
            per_query=args.per_query, max_companies=args.max_companies, on_log=print,
        )
    if not sites:
        sys.exit("No company sites to scan. Add a search key (SERPAPI_API_KEY) or pass --input.")

    people = find_people(
        sites, roles,
        delay=args.delay, max_pages=args.max_pages,
        do_smtp=not args.no_smtp, use_hunter=args.hunter,
        on_log=lambda m: print("  " + m),
    )
    found = dedupe(people)
    n = write_prospects(args.out, found)
    with_email = sum(1 for p in found if p.email)
    verified = sum(1 for p in found if p.email_status == "verified")
    print(f"\nDone. {n} people ({with_email} with an email, {verified} SMTP-verified) -> {args.out}\n")


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

    pp = sub.add_parser("people", help="Find people (name, title, work email) by criteria.")
    pp.add_argument("--roles", default="", help="Comma list of target titles, e.g. 'occupational therapist,practice manager'.")
    pp.add_argument("--industry", default="", help="Industry / keywords, e.g. 'occupational therapy clinic'.")
    pp.add_argument("--location", default="", help="Location, e.g. 'Gold Coast QLD'.")
    pp.add_argument("--input", help="Instead of discovery: CSV/txt of company sites to scan.")
    pp.add_argument("--per-query", type=int, default=10)
    pp.add_argument("--max-companies", type=int, default=25)
    pp.add_argument("--max-pages", type=int, default=6)
    pp.add_argument("--delay", type=float, default=1.5)
    pp.add_argument("--no-smtp", action="store_true", help="Skip live SMTP verification.")
    pp.add_argument("--hunter", action="store_true", help="Use Hunter.io email-finder if HUNTER_API_KEY set.")
    pp.add_argument("--out", default="data/people.csv")
    pp.set_defaults(func=cmd_people)

    return p


def main(argv: List[str] = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
