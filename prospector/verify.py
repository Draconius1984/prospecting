"""
Email verification: syntax -> MX -> live SMTP mailbox probe (with catch-all
detection). This is what lets us confirm a *guessed* work email really exists.

Caveats (surfaced in the UI): many ISPs block outbound port 25 from home
connections, and some mail servers refuse or fake RCPT results. So treat
'verified' as high-confidence, 'accept_all' as "domain accepts anything"
(can't confirm the individual), and 'unverified' as "couldn't check".

Best run from a server/VPS with port 25 open and a warm sending domain.
"""

from __future__ import annotations

import re
import smtplib
import socket
from typing import Dict, List, Optional

_SYNTAX_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

try:
    import dns.resolver  # type: ignore
    _HAVE_DNS = True
except Exception:  # pragma: no cover
    _HAVE_DNS = False

_mx_cache: Dict[str, List[str]] = {}
_catchall_cache: Dict[str, Optional[bool]] = {}

# A neutral MAIL FROM. Use a domain you control in production.
DEFAULT_FROM = "verify@example.com"
DEFAULT_HELO = "prospector.local"


def valid_syntax(email: str) -> bool:
    return bool(_SYNTAX_RE.match((email or "").strip().lower()))


def domain_of(email: str) -> str:
    e = (email or "").strip().lower()
    return e.split("@", 1)[1] if "@" in e else ""


def mx_hosts(domain: str) -> List[str]:
    domain = (domain or "").strip().lower()
    if not domain:
        return []
    if domain in _mx_cache:
        return _mx_cache[domain]
    hosts: List[str] = []
    if _HAVE_DNS:
        try:
            answers = dns.resolver.resolve(domain, "MX")
            hosts = [str(r.exchange).rstrip(".") for r in sorted(answers, key=lambda x: x.preference)]
        except Exception:
            hosts = []
    _mx_cache[domain] = hosts
    return hosts


def _rcpt_code(mx: str, email: str, from_addr: str, timeout: float) -> Optional[int]:
    """Return the SMTP RCPT status code for `email` via `mx`, or None on error."""
    try:
        server = smtplib.SMTP(timeout=timeout)
        server.connect(mx, 25)
        server.helo(DEFAULT_HELO)
        server.mail(from_addr)
        code, _ = server.rcpt(email)
        try:
            server.quit()
        except Exception:
            pass
        return code
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
            socket.timeout, socket.error, OSError, smtplib.SMTPException):
        return None


def is_catch_all(domain: str, timeout: float = 8.0, from_addr: str = DEFAULT_FROM) -> Optional[bool]:
    """Does the domain accept mail to a random (non-existent) mailbox?"""
    domain = (domain or "").strip().lower()
    if domain in _catchall_cache:
        return _catchall_cache[domain]
    hosts = mx_hosts(domain)
    result: Optional[bool] = None
    if hosts:
        probe = f"zz-no-such-user-9x7q2@{domain}"
        code = _rcpt_code(hosts[0], probe, from_addr, timeout)
        if code is not None:
            result = code in (250, 251)
    _catchall_cache[domain] = result
    return result


def verify_email(email: str, do_smtp: bool = True, timeout: float = 8.0,
                 from_addr: str = DEFAULT_FROM) -> Dict[str, object]:
    """
    Return {syntax, mx (bool|None), status}.
    status in: invalid | verified | accept_all | probable | unverified
    """
    email = (email or "").strip().lower()
    if not valid_syntax(email):
        return {"syntax": False, "mx": False, "status": "invalid"}

    hosts = mx_hosts(domain_of(email))
    if not hosts:
        return {"syntax": True, "mx": False, "status": "invalid"}

    if not do_smtp:
        return {"syntax": True, "mx": True, "status": "probable"}

    # Catch-all first: if the domain accepts anything, we can't confirm one user.
    if is_catch_all(domain_of(email), timeout, from_addr):
        return {"syntax": True, "mx": True, "status": "accept_all"}

    code = _rcpt_code(hosts[0], email, from_addr, timeout)
    if code is None:
        return {"syntax": True, "mx": True, "status": "unverified"}
    if code in (250, 251):
        return {"syntax": True, "mx": True, "status": "verified"}
    if code in (550, 551, 553, 501, 552):
        return {"syntax": True, "mx": True, "status": "invalid"}
    return {"syntax": True, "mx": True, "status": "unverified"}
