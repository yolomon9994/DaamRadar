import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from django.conf import settings

from .types import CollectionError


class PoliteClient:
    """Single origin, no redirects/retries, fail-closed robots and bounded bodies."""

    def __init__(self, origin):
        self.origin = origin.rstrip("/")
        self.host = urlparse(self.origin).netloc
        if not settings.SCRAPER_CONTACT:
            raise CollectionError("Set SCRAPER_CONTACT to a monitored contact address before collection.")
        self.user_agent = f"DaamRadarBot/0.1 (+mailto:{settings.SCRAPER_CONTACT})"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self.delay = settings.SCRAPER_DELAY_SECONDS
        self.last_request = None
        self.robots = None

    def _request(self, url):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != self.host or parsed.username or parsed.fragment:
            raise CollectionError("Only the configured HTTPS origin is allowed; redirects and fragments are unsupported.")
        if self.last_request is not None:
            time.sleep(max(0, self.delay - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        try:
            with self.session.get(url, timeout=(5, 20), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise CollectionError(f"HTTP {response.status_code}; stopped without retrying or bypassing access controls.")
                chunks, length = [], 0
                for chunk in response.iter_content(16384):
                    length += len(chunk)
                    if length > 2_000_000:
                        raise CollectionError("Source response exceeds the 2 MB safety limit.")
                    chunks.append(chunk)
                body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                if any(token in body.lower() for token in ["cf-chl-", "g-recaptcha", "verify you are human", "access denied"]):
                    raise CollectionError("Access challenge detected; collection stopped.")
                return body, response.headers.get("Content-Type", "")
        except requests.RequestException as exc:
            raise CollectionError(f"Source request failed ({type(exc).__name__}).") from exc

    def get_html(self, url):
        if self.robots is None:
            text, content_type = self._request(f"{self.origin}/robots.txt")
            if "text/plain" not in content_type or not any(line.strip().lower().startswith("user-agent:") for line in text.splitlines()):
                raise CollectionError("robots.txt could not be validated; collection blocked.")
            self.robots = RobotFileParser()
            self.robots.parse(text.splitlines())
            crawl_delay = self.robots.crawl_delay(self.user_agent) or 0
            rate = self.robots.request_rate(self.user_agent)
            self.delay = max(self.delay, crawl_delay, rate.seconds / rate.requests if rate else 0)
        if not self.robots.can_fetch(self.user_agent, url):
            raise CollectionError("robots.txt disallows this URL.")
        body, content_type = self._request(url)
        if "text/html" not in content_type:
            raise CollectionError("Expected a public HTML product page.")
        return body

    def close(self):
        self.session.close()
