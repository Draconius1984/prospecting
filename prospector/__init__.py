"""
OT Prospector — a compliance-first B2B prospecting tool for finding the
published business contact emails of occupational therapy providers in
Queensland, Australia.

The package is intentionally modular:

    sources     Curated Queensland OT directories + search-query builders
    search      Pluggable web-search providers (SerpAPI / Google CSE / Bing)
    crawler     Polite website crawler (robots.txt aware, rate limited)
    extract     Email / phone / name extraction from HTML
    compliance  Filters that keep collection to conspicuously-published
                business emails and honour "no unsolicited contact" notices
    validate    Email syntax + MX-record validation
    enrich      Optional Hunter.io domain-search enrichment
    models      The Prospect record + CSV schema
"""

__version__ = "1.0.0"
__all__ = ["__version__"]

# Make HTTPS use the operating-system trust store when possible. This lets the
# tool work behind TLS-intercepting corporate proxies (whose root CA lives in
# the OS store, not in certifi's bundle). No-op if 'truststore' isn't installed.
try:  # pragma: no cover
    import truststore as _truststore

    _truststore.inject_into_ssl()
except Exception:
    pass
