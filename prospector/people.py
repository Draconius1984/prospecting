"""
Extract PEOPLE (name + job title + any published email) from a company's
team / about / staff pages. Heuristic but effective on typical clinic and SMB
websites, which list staff as repeated name + title (+ email) blocks.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .compliance import is_collectable_business_email, normalize_email

# Multi-word phrases / words that signal a job title. Extend for other verticals.
TITLE_KEYWORDS = [
    "therapist", "occupational therap", "physiotherap", "physio", "psycholog",
    "manager", "director", "owner", "principal", "founder", "co-founder",
    "ceo", "coo", "cfo", "cto", "head of", "lead", "clinical", "team leader",
    "coordinator", "practitioner", "clinician", "consultant", "specialist",
    "receptionist", "administrator", "admin", "practice manager", "partner",
    "nurse", "doctor", "dietitian", "speech", "pathologist", "social worker",
    "assistant", "allied health", "supervisor", "president", "vice president",
    "engineer", "sales", "marketing", "account", "recruit", "advisor", "officer",
]

SENIORITY_MAP = [
    ("owner", ["owner", "founder", "co-founder", "principal", "director",
               "ceo", "coo", "cfo", "cto", "president", "partner"]),
    ("manager", ["manager", "head of", "lead", "team leader", "supervisor",
                 "coordinator", "vice president"]),
    ("senior", ["senior", "clinical lead", "specialist", "consultant"]),
    ("staff", []),
]

# Honorifics + credential tokens stripped from a candidate name.
_HONORIFICS = {"dr", "mr", "mrs", "ms", "miss", "mx", "prof", "professor", "sir", "dame"}
_CREDS = {
    "ot", "otr", "aht", "ahpra", "ba", "bsc", "msc", "ma", "phd", "md", "jp",
    "cht", "apam", "reg", "bappsc", "mocctherapy", "bocctherapy", "hons", "grad",
    "dip", "cert", "pg", "assoc", "mba",
}

# Words that appear inside TITLES or page chrome — a real name never contains one.
_TITLE_STOP = {
    "therapist", "therapy", "occupational", "physiotherapist", "physiotherapy",
    "physio", "psychologist", "psychology", "manager", "director", "owner",
    "principal", "founder", "ceo", "coo", "cfo", "cto", "lead", "clinical",
    "coordinator", "practitioner", "clinician", "consultant", "specialist",
    "receptionist", "administrator", "admin", "partner", "nurse", "doctor",
    "dietitian", "speech", "pathologist", "social", "worker", "assistant",
    "allied", "health", "supervisor", "president", "senior", "junior", "head",
    "team", "our", "meet", "about", "contact", "services", "service", "home",
    "welcome", "staff", "clinic", "careers", "career", "news", "blog", "privacy",
    "policy", "terms", "booking", "book", "appointment", "location", "locations",
    "the", "and", "for", "with", "your", "learn", "more", "read", "us",
    "engineer", "sales", "marketing", "officer", "advisor", "account",
}

_NAME_TOKEN = re.compile(r"^[A-Z][a-zA-Z'’.\-]{1,}$")


def seniority_of(title: str) -> str:
    t = (title or "").lower()
    for level, kws in SENIORITY_MAP:
        if any(k in t for k in kws):
            return level
    return "staff" if t else ""


def _looks_like_title(text: str) -> bool:
    low = (text or "").lower()
    return any(k in low for k in TITLE_KEYWORDS)


def clean_person_name(text: str) -> Optional[str]:
    """Return a normalised 'First Last' if `text` is a plausible person name."""
    if not text:
        return None
    text = re.split(r"[,(|]", text)[0].strip()
    if not (3 <= len(text) <= 45):
        return None
    raw = [t for t in re.split(r"\s+", text) if t]
    toks = []
    for t in raw:
        base = re.sub(r"[^a-z]", "", t.lower())
        if base in _HONORIFICS or base in _CREDS:
            continue
        toks.append(t)
    if not (2 <= len(toks) <= 3):
        return None
    for t in toks:
        base = re.sub(r"[^a-z]", "", t.lower())
        if not base or base in _TITLE_STOP or not _NAME_TOKEN.match(t):
            return None
    return " ".join(toks)


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip(" -–—|•·\t"))
    return text[:90]


def _find_title(container, name: str) -> str:
    """Find a short line inside `container` that reads like a job title."""
    for el in container.find_all(["p", "span", "em", "small", "h4", "h5", "h6", "li"]):
        txt = el.get_text(" ", strip=True)
        if not txt or len(txt) > 70:
            continue
        if txt == name or name in txt:
            continue
        if _looks_like_title(txt) and clean_person_name(txt) is None:
            return _clean_title(txt)
    return ""


def _email_in(container) -> str:
    a = container.select_one('a[href^="mailto:"]') if container else None
    if not a:
        return ""
    cand = normalize_email(a.get("href", "")[len("mailto:"):].split("?", 1)[0])
    return cand if is_collectable_business_email(cand) else ""


def _card_for(el, name: str):
    """
    Smallest ancestor of `el` that is still this ONE person's card — i.e. climb
    up only while no *other* person's name appears. Prevents grabbing a
    neighbouring staff member's email/title from a shared container.
    """
    card = el.parent or el
    for _ in range(4):
        parent = getattr(card, "parent", None)
        if parent is None:
            break
        clash = False
        for h in parent.find_all(["h2", "h3", "h4", "h5", "h6", "strong", "b"]):
            other = clean_person_name(h.get_text(" ", strip=True))
            if other and other.lower() != name.lower():
                clash = True
                break
        if clash:
            break
        card = parent
    return card


def _merge(store: Dict[str, Dict[str, str]], name: str, title: str, email: str, src: str) -> None:
    key = name.lower()
    cur = store.get(key)
    if cur is None:
        store[key] = {"name": name, "title": title, "email": email, "source_url": src}
        return
    if not cur["title"] and title:
        cur["title"] = title
    if not cur["email"] and email:
        cur["email"] = email


def extract_people(soup, base_url: str = "") -> List[Dict[str, str]]:
    """Return [{name, title, email, source_url, seniority}] found on the page."""
    if soup is None:
        return []
    store: Dict[str, Dict[str, str]] = {}

    # 1) Name-anchored: scan heading-ish elements for plausible person names,
    #    then look nearby for a title and a mailto.
    anchors = soup.find_all(["h2", "h3", "h4", "h5", "h6", "strong", "b"])
    anchors += soup.select('[class*="name"], [class*="member"], [class*="staff"]')
    for el in anchors:
        name = clean_person_name(el.get_text(" ", strip=True))
        if not name:
            continue
        card = _card_for(el, name)
        _merge(store, name, _find_title(card, name), _email_in(card), base_url)

    # 2) Email-anchored: attach any personal mailto to a nearby name.
    for a in soup.select('a[href^="mailto:"]'):
        cand = normalize_email(a.get("href", "")[len("mailto:"):].split("?", 1)[0])
        if not is_collectable_business_email(cand):
            continue
        container = a.find_parent(["div", "li", "article", "section", "td", "p"]) or a.parent
        if not container:
            continue
        name = None
        for h in container.find_all(["h2", "h3", "h4", "h5", "h6", "strong", "b"]):
            name = clean_person_name(h.get_text(" ", strip=True))
            if name:
                break
        if name:
            _merge(store, name, _find_title(container, name), cand, base_url)

    results = []
    for p in store.values():
        p["seniority"] = seniority_of(p["title"])
        results.append(p)
    return results
