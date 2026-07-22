"""
Work-email pattern engine — the core of "find a person's work email".

Given a person's name and their employer's domain, generate the candidate
addresses a company is statistically likely to use (first.last@, flast@, ...),
in priority order. If we already KNOW one real email at a domain, we can infer
that company's pattern and apply it to everyone else there with high confidence
— exactly how Hunter/Apollo do it.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Tuple

# Honorifics / credentials to strip from a display name before parsing.
_TITLES = {"dr", "mr", "mrs", "ms", "miss", "mx", "prof", "professor", "sir", "dame"}
_CREDS = {
    "ot", "otr", "aht", "ahpra", "ba", "bsc", "msc", "ma", "phd", "md", "jp",
    "bocctherapy", "boccthy", "bappsc", "mocctherapy", "cht", "apam", "reg",
}

# Empirical frequency priors from a study of 336k verified B2B emails
# (Sendburg). Used to rank guesses so the most likely address is tried first.
# Tokens: {first} {last} {f} {l}
FREQUENCY = {
    "{first}.{last}": 0.477,
    "{f}{last}": 0.268,
    "{first}": 0.081,
    "{first}{last}": 0.023,
    "{first}_{last}": 0.023,
    "{f}.{last}": 0.021,
    "{last}": 0.012,
    "{last}.{first}": 0.0065,
    "{first}.{l}": 0.0013,
    "{first}-{last}": 0.0010,
}

# Full candidate set: frequency-ranked head, then rarer tail forms.
PATTERN_TEMPLATES: List[str] = list(FREQUENCY.keys()) + [
    "{last}{first}",
    "{last}{f}",
    "{f}{l}",
    "{first}{l}",
    "{f}-{last}",
    "{last}-{first}",
    "{f}_{last}",
]


def pattern_prior(template: str) -> float:
    """Real-world probability weight for a template (0-1)."""
    return FREQUENCY.get(template, 0.004)


def _ascii(s: str) -> str:
    """Strip accents and lowercase to bare a-z0-9."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def split_name(full_name: str) -> Optional[Tuple[str, str]]:
    """
    Return (first, last) as bare ascii tokens, or None if we can't parse a
    plausible person name. Strips honorifics and trailing credentials.
    """
    if not full_name:
        return None
    # drop anything after a comma (e.g. "Smith, Jane" -> keep, or credentials)
    raw = re.split(r"[,(]", full_name)[0]
    tokens = [t for t in re.split(r"[\s.]+", raw.strip()) if t]
    # remove honorifics / credentials
    clean = []
    for t in tokens:
        bare = _ascii(t)
        if not bare or bare in _TITLES or bare in _CREDS:
            continue
        clean.append(bare)
    if len(clean) < 2:
        return None
    first, last = clean[0], clean[-1]
    if len(first) < 2 or len(last) < 2:
        return None
    return first, last


def _render(template: str, first: str, last: str) -> str:
    return template.format(first=first, last=last, f=first[:1], l=last[:1])


def generate_candidates(full_name: str, domain: str) -> List[Tuple[str, str]]:
    """
    Return ordered [(email, pattern), ...] candidates for name @ domain.
    Empty if the name can't be parsed.
    """
    parsed = split_name(full_name)
    if not parsed or not domain:
        return []
    first, last = parsed
    domain = domain.strip().lower().lstrip("@")
    seen, out = set(), []
    for tpl in PATTERN_TEMPLATES:
        local = _render(tpl, first, last)
        email = f"{local}@{domain}"
        if email not in seen:
            seen.add(email)
            out.append((email, tpl))
    return out


def infer_pattern(full_name: str, known_email: str) -> Optional[str]:
    """
    Given a person and one of their real emails, deduce the company's pattern
    template (e.g. '{first}.{last}'). Returns None if no template matches.
    """
    parsed = split_name(full_name)
    if not parsed or "@" not in (known_email or ""):
        return None
    first, last = parsed
    local = _ascii(known_email.split("@", 1)[0])
    for tpl in PATTERN_TEMPLATES:
        if _ascii(_render(tpl, first, last)) == local:
            return tpl
    return None


def apply_pattern(pattern: str, full_name: str, domain: str) -> Optional[str]:
    """Apply a known company pattern to a new person at that domain."""
    parsed = split_name(full_name)
    if not parsed or not pattern or not domain:
        return None
    first, last = parsed
    return f"{_render(pattern, first, last)}@{domain.strip().lower().lstrip('@')}"
