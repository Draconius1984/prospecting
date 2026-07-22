"""
Pluggable web-search providers for automated discovery.

The tool works with ZERO keys (crawl mode + curated directories). To enable
automated `discover`, set ONE of these in your .env:

    SERPAPI_API_KEY                 (https://serpapi.com)
    GOOGLE_CSE_API_KEY + GOOGLE_CSE_CX   (Google Programmable Search)
    BING_SEARCH_API_KEY             (Azure Bing Web Search)

Each provider returns a list of result URLs for a query.
"""

from __future__ import annotations

import os
from typing import List

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

_TIMEOUT = 20


def active_provider() -> str:
    if os.getenv("SERPAPI_API_KEY"):
        return "serpapi"
    if os.getenv("GOOGLE_CSE_API_KEY") and os.getenv("GOOGLE_CSE_CX"):
        return "google_cse"
    if os.getenv("BING_SEARCH_API_KEY"):
        return "bing"
    return "none"


def search(query: str, num: int = 10) -> List[str]:
    """Dispatch to whichever provider is configured. [] if none."""
    provider = active_provider()
    if provider == "none" or requests is None:
        return []
    try:
        if provider == "serpapi":
            return _serpapi(query, num)
        if provider == "google_cse":
            return _google_cse(query, num)
        if provider == "bing":
            return _bing(query, num)
    except Exception as exc:  # pragma: no cover
        print(f"    ! search provider '{provider}' error: {exc}")
    return []


def _serpapi(query: str, num: int) -> List[str]:
    resp = requests.get(
        "https://serpapi.com/search.json",
        params={
            "q": query,
            "engine": "google",
            "google_domain": "google.com.au",
            "gl": "au",
            "hl": "en",
            "num": num,
            "api_key": os.getenv("SERPAPI_API_KEY"),
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return [r["link"] for r in data.get("organic_results", []) if r.get("link")]


def _google_cse(query: str, num: int) -> List[str]:
    resp = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={
            "key": os.getenv("GOOGLE_CSE_API_KEY"),
            "cx": os.getenv("GOOGLE_CSE_CX"),
            "q": query,
            "num": min(num, 10),
            "gl": "au",
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return [it["link"] for it in data.get("items", []) if it.get("link")]


def _bing(query: str, num: int) -> List[str]:
    resp = requests.get(
        "https://api.bing.microsoft.com/v7.0/search",
        headers={"Ocp-Apim-Subscription-Key": os.getenv("BING_SEARCH_API_KEY")},
        params={"q": query, "count": num, "mkt": "en-AU"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    return [v["url"] for v in data.get("webPages", {}).get("value", []) if v.get("url")]
