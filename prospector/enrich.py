"""
Optional email enrichment via Hunter.io domain-search.

Set HUNTER_API_KEY in .env to enable. Free tier ~25 searches/month.
Given a domain, Hunter returns published/known role & personal emails plus a
confidence score. We only keep results Hunter marks as reasonably confident.
"""

from __future__ import annotations

import os
from typing import Dict, List

try:
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

_TIMEOUT = 20


def enabled() -> bool:
    return bool(os.getenv("HUNTER_API_KEY")) and requests is not None


def domain_search(domain: str, min_confidence: int = 50) -> List[Dict[str, str]]:
    """
    Return a list of {email, type, first_name, last_name, position, confidence}
    for a domain. Empty list if disabled or on error.
    """
    if not enabled() or not domain:
        return []
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": os.getenv("HUNTER_API_KEY")},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except Exception as exc:  # pragma: no cover
        print(f"    ! hunter error for {domain}: {exc}")
        return []

    out: List[Dict[str, str]] = []
    for e in data.get("emails", []):
        if int(e.get("confidence") or 0) < min_confidence:
            continue
        out.append(
            {
                "email": (e.get("value") or "").lower(),
                "type": e.get("type") or "",        # personal | generic
                "first_name": e.get("first_name") or "",
                "last_name": e.get("last_name") or "",
                "position": e.get("position") or "",
                "confidence": str(e.get("confidence") or ""),
            }
        )
    return out


def find_email(domain: str, first_name: str, last_name: str) -> Optional[Dict[str, str]]:
    """
    Hunter.io email-finder: given a domain + person name, return the most likely
    work email and Hunter's confidence. None if disabled or not found.
    """
    if not enabled() or not (domain and first_name and last_name):
        return None
    try:
        resp = requests.get(
            "https://api.hunter.io/v2/email-finder",
            params={
                "domain": domain,
                "first_name": first_name,
                "last_name": last_name,
                "api_key": os.getenv("HUNTER_API_KEY"),
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
    except Exception as exc:  # pragma: no cover
        print(f"    ! hunter email-finder error for {first_name} {last_name}@{domain}: {exc}")
        return None
    if not data.get("email"):
        return None
    return {
        "email": (data.get("email") or "").lower(),
        "confidence": str(data.get("confidence") or ""),
        "position": data.get("position") or "",
    }
