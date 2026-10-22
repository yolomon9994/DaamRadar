"""Small manual public-HTML adapters. Never use internal APIs or copy rich content."""
from dataclasses import replace
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from catalog.matching.normalization import identify, match_score, normalize_text
from .parsers import parse_product_html
from .cartpk import parse_cartpk_html
from .reviewed import MILK_COMPARISON_PRODUCTS
from .types import CollectionError


class UnavailableAdapter:
    enabled = False
    reason = "Source access has not been validated."

    def collect(self, client, url):
        raise CollectionError(self.reason)


class PublicProductAdapter:
    enabled = True
    reason = "Source collection is paused; review access before enabling it."
    origin = ""
    path_pattern = ""
    area_note = ""

    def parse_page(self, html, url):
        return parse_product_html(html, url)

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
            item = self.parse_page(html, url)
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

    def parse_page(self, html, url):
        item = super().parse_page(html, url)
        expected = {entry["jalal_path"]: entry["title"] for entry in MILK_COMPARISON_PRODUCTS}.get(urlparse(url).path)
        if expected and match_score(identify(item.title, item.brand), identify(expected)) != 100:
            raise CollectionError("Jalal Sons title no longer identifies the reviewed product for this URL.", code="parse_error")
        return item


class CartpkAdapter(PublicProductAdapter):
    origin = "https://www.cartpk.com"
    # Every URL has a reviewed identity; a generic product-path pattern is insufficient.
    reviewed_titles = {entry["cartpk_path"]: entry["title"] for entry in MILK_COMPARISON_PRODUCTS}
    path_pattern = "(?:" + "|".join(re.escape(path) for path in reviewed_titles) + ")"
    area_note = "Cartpk public catalog; delivery area unverified"

    def parse_page(self, html, url):
        item = parse_cartpk_html(html, url)
        expected = self.reviewed_titles.get(urlparse(url).path)
        if not expected or match_score(identify(item.title, item.brand), identify(expected)) != 100:
            raise CollectionError("Cartpk title no longer identifies the reviewed product for this URL.", code="parse_error")
        return item


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


ADAPTERS = {"naheed": NaheedAdapter, "jalal-sons": JalalSonsAdapter, "cartpk": CartpkAdapter,
            "springs": SpringsAdapter, "alfatah": AlFatahAdapter}
