"""Retailer-specific entry points. None is authorized for live collection yet."""
from urllib.parse import urlparse

from .parsers import parse_product_html
from .types import CollectionError


class UnavailableAdapter:
    enabled = False
    reason = "Source access has not been validated."

    def collect(self, client, url):
        raise CollectionError(self.reason)


class NaheedAdapter(UnavailableAdapter):
    reason = "Naheed returned HTTP 403; robots could not be validated. No access bypass is supported."


class SpringsAdapter(UnavailableAdapter):
    reason = "Springs requires a delivery branch/location; robots and permitted feed access remain unverified."


class AlFatahAdapter(UnavailableAdapter):
    reason = "Al-Fatah terms restrict reuse to personal shopping. Obtain written permission or a licensed feed before enabling collection."

    @staticmethod
    def parse_saved_html(html, url):
        # A provisional offline parser, not a claim of a validated live integration.
        if urlparse(url).netloc != "alfatah.pk" or not urlparse(url).path.startswith("/products/"):
            raise CollectionError("Expected an Al-Fatah product URL.")
        return parse_product_html(html, url)


ADAPTERS = {"naheed": NaheedAdapter, "springs": SpringsAdapter, "alfatah": AlFatahAdapter}
