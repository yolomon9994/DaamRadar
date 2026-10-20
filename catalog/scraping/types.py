from dataclasses import dataclass
from decimal import Decimal


class CollectionError(Exception):
    """Actionable source failure. Never retry access denials."""

    def __init__(self, message, *, code="collection_error", http_status=None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


@dataclass(frozen=True)
class ScrapedProduct:
    external_id: str
    title: str
    url: str
    price: Decimal
    currency: str = "PKR"
    availability: str = "unknown"
    brand: str = ""
    gtin: str = ""
    image: str = ""
    delivery_area: str = ""
