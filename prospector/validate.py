"""Email validation: syntax + MX-record lookup (best effort)."""

from __future__ import annotations

import re
from typing import Dict, Optional

from .compliance import domain_of, normalize_email

_SYNTAX_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

try:
    import dns.resolver  # type: ignore
    _HAVE_DNS = True
except Exception:  # pragma: no cover
    dns = None  # type: ignore
    _HAVE_DNS = False

_mx_cache: Dict[str, Optional[bool]] = {}


def valid_syntax(email: str) -> bool:
    return bool(_SYNTAX_RE.match(normalize_email(email)))


def has_mx(domain: str) -> Optional[bool]:
    """
    True/False if we could resolve MX (or its absence); None if we cannot
    check (dnspython missing or lookup error). Results are cached per domain.
    """
    domain = (domain or "").strip().lower()
    if not domain:
        return None
    if domain in _mx_cache:
        return _mx_cache[domain]
    if not _HAVE_DNS:
        _mx_cache[domain] = None
        return None
    try:
        answers = dns.resolver.resolve(domain, "MX")
        result: Optional[bool] = len(answers) > 0
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
        result = False
    except Exception:
        result = None
    _mx_cache[domain] = result
    return result


def validate_email(email: str) -> Dict[str, object]:
    """Return {syntax: bool, mx: True/False/None, mx_label: str}."""
    syntax_ok = valid_syntax(email)
    mx = has_mx(domain_of(email)) if syntax_ok else False
    label = "unknown" if mx is None else ("yes" if mx else "no")
    return {"syntax": syntax_ok, "mx": mx, "mx_label": label}
