"""
Polite website crawler.

Design goals (see docs/COMPLIANCE.md):
  * Respect robots.txt for every domain.
  * Identify ourselves with a truthful User-Agent.
  * Rate-limit requests (default 2s between hits).
  * Only visit a handful of high-signal pages (home + contact/about/team).
  * Surface a "no unsolicited contact" flag so you can exclude those sites.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from .compliance import page_forbids_unsolicited
from .extract import (
    extract_emails,
    extract_mailto,
    extract_phones,
    guess_business_name,
)

DEFAULT_UA = "OT-Prospector/1.0 (+B2B research bot; respects robots.txt)"

# Link text / hrefs that suggest a page likely to list a business email.
_CONTACT_HINTS = (
    "contact", "about", "team", "our-team", "our team", "staff",
    "referral", "referrals", "book", "appointment", "location", "reach",
)

try:  # optional heavy deps — imported lazily-ish so --help still works
    import requests  # type: ignore
    from bs4 import BeautifulSoup  # type: ignore
    _HAVE_DEPS = True
except Exception:  # pragma: no cover
    requests = None  # type: ignore
    BeautifulSoup = None  # type: ignore
    _HAVE_DEPS = False


class Crawler:
    def __init__(
        self,
        user_agent: str = DEFAULT_UA,
        delay: float = 2.0,
        timeout: float = 15.0,
        max_pages: int = 5,
    ):
        if not _HAVE_DEPS:
            raise RuntimeError(
                "The crawler needs 'requests' and 'beautifulsoup4'.\n"
                "Install them with:  pip install -r requirements.txt"
            )
        self.ua = user_agent
        self.delay = float(delay)
        self.timeout = float(timeout)
        self.max_pages = int(max_pages)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.ua})
        self._robots: Dict[str, Optional[RobotFileParser]] = {}
        self._last_hit = 0.0

    # -- robots.txt -------------------------------------------------------
    def _robots_for(self, url: str) -> Optional[RobotFileParser]:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base in self._robots:
            return self._robots[base]
        rp = RobotFileParser()
        try:
            resp = self.session.get(urljoin(base, "/robots.txt"), timeout=self.timeout)
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
            else:
                rp = None  # no robots => allowed
        except Exception:
            rp = None
        self._robots[base] = rp
        return rp

    def allowed(self, url: str) -> bool:
        rp = self._robots_for(url)
        if rp is None:
            return True
        try:
            return rp.can_fetch(self.ua, url)
        except Exception:
            return True

    # -- fetching ---------------------------------------------------------
    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_hit)
        if wait > 0:
            time.sleep(wait)
        self._last_hit = time.monotonic()

    def fetch(self, url: str) -> Optional[str]:
        if not self.allowed(url):
            return None
        self._throttle()
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        except Exception:
            return None
        ctype = resp.headers.get("Content-Type", "")
        if resp.status_code != 200 or "html" not in ctype.lower():
            return None
        return resp.text

    # -- page discovery ---------------------------------------------------
    def _contact_links(self, html: str, base_url: str) -> List[str]:
        soup = BeautifulSoup(html, "html.parser")
        base_netloc = urlparse(base_url).netloc
        scored: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            label = (a.get_text(" ", strip=True) or "").lower()
            target = urljoin(base_url, href)
            if urlparse(target).netloc != base_netloc:
                continue
            hay = (href + " " + label).lower()
            if any(h in hay for h in _CONTACT_HINTS):
                scored.append(target.split("#", 1)[0])
        # de-dupe, preserve order
        seen: Set[str] = set()
        ordered = []
        for u in scored:
            if u not in seen:
                seen.add(u)
                ordered.append(u)
        return ordered

    def collect_pages(self, start_url: str) -> List:
        """Return [(url, html), ...] for the home + contact/about/team pages."""
        if not start_url.startswith(("http://", "https://")):
            start_url = "https://" + start_url
        pages: List = []
        home = self.fetch(start_url)
        if home is None:
            return pages
        pages.append((start_url, home))
        for link in self._contact_links(home, start_url)[: self.max_pages - 1]:
            page = self.fetch(link)
            if page:
                pages.append((link, page))
        return pages

    # -- public API -------------------------------------------------------
    def crawl_site(self, start_url: str) -> Dict:
        """
        Crawl a single site's home + contact-like pages.

        Returns a dict:
            {emails, phones, name, pages, blocked, forbids_unsolicited}
        """
        result = {
            "emails": set(),
            "phones": set(),
            "name": "",
            "pages": [],
            "blocked": False,
            "forbids_unsolicited": False,
        }
        if not start_url.startswith(("http://", "https://")):
            start_url = "https://" + start_url

        home = self.fetch(start_url)
        if home is None:
            result["blocked"] = True
            return result

        soup = BeautifulSoup(home, "html.parser")
        result["name"] = guess_business_name(soup)
        result["pages"].append(start_url)
        result["emails"] |= extract_mailto(soup)
        result["emails"] |= extract_emails(home)
        result["phones"] |= extract_phones(home)
        if page_forbids_unsolicited(soup.get_text(" ", strip=True)):
            result["forbids_unsolicited"] = True

        for link in self._contact_links(home, start_url)[: self.max_pages - 1]:
            page = self.fetch(link)
            if not page:
                continue
            psoup = BeautifulSoup(page, "html.parser")
            result["pages"].append(link)
            result["emails"] |= extract_mailto(psoup)
            result["emails"] |= extract_emails(page)
            result["phones"] |= extract_phones(page)
            if page_forbids_unsolicited(psoup.get_text(" ", strip=True)):
                result["forbids_unsolicited"] = True

        return result
