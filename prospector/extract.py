"""Extract emails, phone numbers and a business name from HTML / text."""

from __future__ import annotations

import re
from typing import List, Optional, Set

from .compliance import is_collectable_business_email, normalize_email

# Reasonably strict email regex (RFC-lite, good enough for scraping).
_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)

# Australian phone numbers: mobiles (04xx xxx xxx), landlines (0x xxxx xxxx),
# and +61 variants. Deliberately permissive.
_PHONE_RE = re.compile(
    r"(?:\+?61[\s.\-]?|0)(?:4\d{2}[\s.\-]?\d{3}[\s.\-]?\d{3}"
    r"|[2378][\s.\-]?\d{4}[\s.\-]?\d{4})"
)


def deobfuscate(text: str) -> str:
    """Undo common '[at]' / '(dot)' / HTML-entity email obfuscation."""
    if not text:
        return ""
    t = text
    t = t.replace("&#64;", "@").replace("&commat;", "@").replace("&#46;", ".")
    t = re.sub(r"\s*[\[\(]\s*at\s*[\]\)]\s*", "@", t, flags=re.I)
    t = re.sub(r"\s+at\s+", "@", t, flags=re.I)
    t = re.sub(r"\s*[\[\(]\s*dot\s*[\]\)]\s*", ".", t, flags=re.I)
    t = re.sub(r"\s+dot\s+", ".", t, flags=re.I)
    return t


def decode_cfemail(encoded: str) -> str:
    """Decode a Cloudflare 'email-protection' hex string (XOR with first byte)."""
    try:
        data = bytes.fromhex(encoded.strip())
        key = data[0]
        return "".join(chr(b ^ key) for b in data[1:])
    except Exception:
        return ""


def extract_cfemails(soup) -> Set[str]:
    """Recover Cloudflare-obfuscated emails from a parsed page."""
    out: Set[str] = set()
    if soup is None:
        return out
    for el in soup.select("[data-cfemail]"):
        dec = normalize_email(decode_cfemail(el.get("data-cfemail", "")))
        if is_collectable_business_email(dec):
            out.add(dec)
    for a in soup.select('a[href*="/cdn-cgi/l/email-protection#"]'):
        frag = a.get("href", "").split("#", 1)[-1]
        dec = normalize_email(decode_cfemail(frag))
        if is_collectable_business_email(dec):
            out.add(dec)
    return out


def extract_emails(text: str, deobfuscated: bool = True) -> Set[str]:
    """Return the set of collectable business emails found in free text."""
    if not text:
        return set()
    hay = deobfuscate(text) if deobfuscated else text
    found = set()
    for m in _EMAIL_RE.findall(hay):
        e = normalize_email(m)
        if is_collectable_business_email(e):
            found.add(e)
    return found


def extract_mailto(soup) -> Set[str]:
    """Emails from <a href="mailto:...">, the most reliable signal."""
    out: Set[str] = set()
    if soup is None:
        return out
    for a in soup.select('a[href^="mailto:"]'):
        href = a.get("href", "")
        addr = href[len("mailto:"):].split("?", 1)[0]
        for part in addr.split(","):
            e = normalize_email(part)
            if is_collectable_business_email(e):
                out.add(e)
    return out


def extract_phones(text: str) -> Set[str]:
    if not text:
        return set()
    out: Set[str] = set()
    for m in _PHONE_RE.findall(text):
        cleaned = re.sub(r"[\s.\-]", " ", m).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        out.add(cleaned)
    return out


def guess_business_name(soup, fallback: str = "") -> str:
    """Best-effort business name from <title> / og:site_name / <h1>."""
    if soup is None:
        return fallback
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content"):
        return _clean_name(og["content"])
    if soup.title and soup.title.string:
        return _clean_name(soup.title.string)
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return _clean_name(h1.get_text(strip=True))
    return fallback


def _clean_name(raw: str) -> str:
    name = re.split(r"[|\-–—:]", raw)[0].strip()
    return re.sub(r"\s+", " ", name)[:120]


def first_email_by_type(emails: List[str]) -> Optional[str]:
    """Prefer a role/shared inbox email when several are present."""
    from .compliance import classify_email
    if not emails:
        return None
    generic = [e for e in emails if classify_email(e) == "generic"]
    return (generic or emails)[0]
