"""Web connector — public-page reading with robots.txt respect, rate limiting, and no scraping abuse.

Rules:
  * Respect robots.txt and published rate limits.
  * Identify honestly in the User-Agent.
  * No paywall bypass, no auth bypass, no ToS violation.
  * Fetched text is treated as UNTRUSTED DATA and fenced before any model sees it.
"""
from __future__ import annotations

import time
import urllib.parse
import urllib.robotparser
from html.parser import HTMLParser

from ..governance import injection
from .. import store
from .base import Capability, Connector

MIN_SECONDS_BETWEEN_CALLS = 2.0
_last_call: dict[str, float] = {}


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self.parts.append(text)

    @property
    def text(self) -> str:
        return "\n".join(self.parts)


class WebConnector(Connector):
    id = "web"
    label = "Public Web (read-only)"
    kind = "research"
    docs_url = "https://www.rfc-editor.org/rfc/rfc9309.html"
    required_env: list[str] = []
    scopes = ["public_pages_only"]
    free_tier_note = "Public pages are free to read. Rate limits and robots.txt are respected."
    capabilities = [
        Capability("fetch_public_page", "Fetch and extract readable text from a public page", "LOW"),
        Capability("check_robots", "Check whether a path may be fetched", "LOW"),
        Capability("search", "Web search", "LOW", implemented=False,
                   note="Requires the owner to configure a search API key (Brave/Serper/etc.). "
                        "Scraping search engines violates their terms, so it is not done here."),
    ]

    def probe(self) -> dict:
        return {"status": "ok", "detail": "No credentials required for public-page reading.",
                "verified": True}

    def allowed(self, url: str) -> tuple[bool, str]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, "Only http(s) URLs are fetched."
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        try:
            parser.set_url(robots_url)
            parser.read()
            ua = "SauravAICivilization"
            ok = parser.can_fetch(ua, url)
            return ok, ("Allowed by robots.txt" if ok else "Disallowed by robots.txt")
        except Exception:
            # If robots.txt is unreachable we do NOT assume permission.
            return False, "robots.txt could not be read — treated as not permitted."

    def fetch_public_page(self, *, url: str, max_chars: int = 6000) -> dict:
        self._guard("fetch_public_page")
        allowed, reason = self.allowed(url)
        if not allowed:
            return {"status": "REFUSED", "url": url, "reason": reason, "verified": False}

        host = urllib.parse.urlparse(url).netloc
        now = time.time()
        if now - _last_call.get(host, 0) < MIN_SECONDS_BETWEEN_CALLS:
            time.sleep(MIN_SECONDS_BETWEEN_CALLS - (now - _last_call.get(host, 0)))
        _last_call[host] = time.time()

        res = self.http("GET", url, action="fetch_public_page", timeout=20)
        if res.get("status") != "ok":
            return res
        raw = res.get("data", {}).get("raw")
        if raw is None:
            return {"status": "error", "error": "Non-text response.", "verified": False}
        parser = _TextExtractor()
        parser.feed(raw)
        text = parser.text[:max_chars]
        scan = injection.scan(text, origin=f"web:{host}")
        store.bump_counter("web_pages_fetched")
        return {
            "status": "ok",
            "url": url,
            "title": parser.title[:200],
            "text": text,
            "chars": len(text),
            "injection_scan": scan,
            "untrusted": True,
            "how_to_use": "Pass this through injection.wrap_untrusted() before any model sees it.",
            "verified": True,
        }

    def search(self, *, query: str) -> dict:
        return {"status": "NOT_CONFIGURED",
                "reason": "No search API is configured. Add a search provider key to .env to enable "
                          "real web search. Scraping search engines is not done (terms of service).",
                "query": query, "verified": False}
