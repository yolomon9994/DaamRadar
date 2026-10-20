import time
from urllib.parse import urlparse

import requests
from protego import Protego
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email

from .types import CollectionError


class PoliteClient:
    """Single origin, bounded timeout recovery, and no access-denial retries."""

    def __init__(self, origin):
        self.origin = origin.rstrip("/")
        self.host = urlparse(self.origin).netloc
        contact = settings.SCRAPER_CONTACT.strip()
        try:
            if contact.startswith("https://"):
                URLValidator(schemes=["https"])(contact)
                identity = contact
            else:
                validate_email(contact)
                identity = f"mailto:{contact}"
        except ValidationError:
            raise CollectionError("Set SCRAPER_CONTACT to a monitored email or public HTTPS project/contact URL.") from None
        self.user_agent = f"DaamRadarBot/0.1 (+{identity})"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})
        self.delay = settings.SCRAPER_DELAY_SECONDS
        self.last_request = None
        self.robots = None
        self.request_count = 0

    def _validate_url(self, url):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != self.host or parsed.username or parsed.fragment:
            raise CollectionError("Only the configured HTTPS origin is allowed; redirects and fragments are unsupported.", code="invalid_input")
        return parsed

    def _request(self, url):
        parsed = self._validate_url(url)
        for attempt in range(settings.SCRAPER_TIMEOUT_RETRIES + 1):
            if self.last_request is not None:
                wait = max(0, self.delay - (time.monotonic() - self.last_request))
                if attempt:
                    wait = max(wait, settings.SCRAPER_RETRY_DELAY_SECONDS)
                time.sleep(wait)
            self.last_request = time.monotonic()
            self.request_count += 1
            try:
                with self.session.get(url, timeout=(settings.SCRAPER_CONNECT_TIMEOUT, settings.SCRAPER_READ_TIMEOUT),
                                      allow_redirects=False, stream=True) as response:
                    if response.status_code != 200:
                        raise CollectionError(
                            f"HTTP {response.status_code} on {parsed.path}; stopped without retrying or bypassing access controls.",
                            code="http_error", http_status=response.status_code,
                        )
                    chunks, length = [], 0
                    for chunk in response.iter_content(16384):
                        length += len(chunk)
                        if length > 2_000_000:
                            raise CollectionError("Source response exceeds the 2 MB safety limit.", code="invalid_content")
                        chunks.append(chunk)
                    body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                    if any(token in body.lower() for token in ["cf-chl-", "g-recaptcha", "verify you are human", "access denied"]):
                        raise CollectionError("Access challenge detected; collection stopped.", code="access_challenge")
                    return body, response.headers.get("Content-Type", "")
            except requests.Timeout as exc:
                if attempt < settings.SCRAPER_TIMEOUT_RETRIES:
                    continue
                raise CollectionError(
                    f"{type(exc).__name__} on {parsed.path} after {attempt + 1} attempt(s); no further retry.", code="timeout",
                ) from exc
            except requests.RequestException as exc:
                raise CollectionError(f"Source request failed ({type(exc).__name__}) on {parsed.path}.", code="network_error") from exc

    def get_html(self, url):
        self._validate_url(url)
        if self.robots is None:
            text, content_type = self._request(f"{self.origin}/robots.txt")
            if "text/plain" not in content_type or not any(line.strip().lower().startswith("user-agent:") for line in text.splitlines()):
                raise CollectionError("robots.txt could not be validated; collection blocked.", code="robots_unverified")
            self.robots = Protego.parse(text)
            crawl_delay = self.robots.crawl_delay(self.user_agent) or 0
            rate = self.robots.request_rate(self.user_agent)
            self.delay = max(self.delay, crawl_delay, rate.seconds / rate.requests if rate else 0)
        if not self.robots.can_fetch(url, self.user_agent):
            raise CollectionError("robots.txt disallows this URL.", code="robots_disallowed")
        body, content_type = self._request(url)
        if "text/html" not in content_type:
            raise CollectionError("Expected a public HTML product page.", code="invalid_content")
        return body

    def close(self):
        self.session.close()
