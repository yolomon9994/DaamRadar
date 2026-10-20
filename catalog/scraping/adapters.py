"""Small manual public-HTML adapters. Never use internal APIs or copy rich content."""
from dataclasses import replace
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from catalog.matching.normalization import normalize_text
from .parsers import parse_product_html
from .types import CollectionError


class UnavailableAdapter:
    enabled = False
    reason = "Source access has not been validated."

    def collect(self, client, url):
        raise CollectionError(self.reason)


class PublicProductAdapter:
    enabled = True
    origin = ""
    path_pattern = ""
    area_note = ""

    def validate_url(self, url):
        parsed = urlparse(url)
        if (f"{parsed.scheme}://{parsed.netloc}" != self.origin or parsed.username
                or parsed.query or parsed.fragment or not re.fullmatch(self.path_pattern, parsed.path)):
            raise CollectionError("Provide an exact public product URL on this retailer's HTTPS origin, without query parameters.", code="invalid_input")
        return parsed

    def collect(self, client, url):
        parsed = self.validate_url(url)
        html = client.get_html(url)
        try:
            item = parse_product_html(html, url)
        except CollectionError as exc:
            raise CollectionError(str(exc), code="parse_error") from exc
        headings = {normalize_text(node.get_text(" ", strip=True)) for node in BeautifulSoup(html, "html.parser").select("h1")}
        if normalize_text(item.title) not in headings:
            raise CollectionError("Product heading and structured title disagree; source layout needs review.", code="parse_error")
        # Stable URL identity; no descriptions, retailer imagery, cookies, or page configuration retained.
        return replace(item, external_id=parsed.path.strip("/"), image="", delivery_area=self.area_note)


class NaheedAdapter(PublicProductAdapter):
    enabled = False
    reason = "Naheed returned HTTP 403 to the named collector after a successful review request. Live collection is paused; no identity switching or access bypass is supported."
    origin = "https://www.naheed.pk"
    path_pattern = r"/[a-z0-9][a-z0-9-]+"
    area_note = "Naheed public catalog; delivery area unverified"


class JalalSonsAdapter(PublicProductAdapter):
    origin = "https://www.jalalsons.com.pk"
    path_pattern = r"/product/[a-z0-9][a-z0-9-]+-\d+"
    area_note = "Jalal Sons public catalog; delivery area unverified"


class SpringsAdapter(UnavailableAdapter):
    reason = "Springs terms restrict copying/distribution without written permission; location-specific data access is unvalidated."


class AlFatahAdapter(UnavailableAdapter):
    reason = "Al-Fatah terms restrict reuse to personal shopping. Obtain written permission or a licensed feed before enabling collection."

    @staticmethod
    def parse_saved_html(html, url):
        # A provisional offline parser, not a claim of a validated live integration.
        if urlparse(url).netloc != "alfatah.pk" or not urlparse(url).path.startswith("/products/"):
            raise CollectionError("Expected an Al-Fatah product URL.")
        return parse_product_html(html, url)


ADAPTERS = {"naheed": NaheedAdapter, "jalal-sons": JalalSonsAdapter, "springs": SpringsAdapter, "alfatah": AlFatahAdapter}
