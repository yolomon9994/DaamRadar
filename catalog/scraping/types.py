from dataclasses import dataclass
from decimal import Decimal


class CollectionError(Exception):
    """Actionable source failure. Never retry access denials."""


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
