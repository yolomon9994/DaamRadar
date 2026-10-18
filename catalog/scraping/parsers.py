"""Offline-capable JSON-LD parser; no inference from price ranges or variant minima."""
import json
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .types import CollectionError, ScrapedProduct


def parse_product_html(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    nodes = []

    def walk(value):
        if isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, dict):
            kinds = value.get("@type", [])
            if kinds == "Product" or isinstance(kinds, list) and "Product" in kinds:
                nodes.append(value)
            if "@graph" in value:
                walk(value["@graph"])

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.string or script.get_text()))
        except (json.JSONDecodeError, TypeError):
            continue
    if len(nodes) != 1:
        raise CollectionError("Expected one unambiguous JSON-LD Product; source layout may have changed.")
    node = nodes[0]
    offer = node.get("offers", {})
    if isinstance(offer, list):
        if len(offer) != 1:
            raise CollectionError("Multiple variant offers require a validated variant adapter.")
        offer = offer[0]
    if not isinstance(offer, dict) or offer.get("@type") != "Offer" or offer.get("priceCurrency") != "PKR":
        raise CollectionError("A single explicit PKR Offer is required; aggregate prices are unsupported.")
    try:
        price = Decimal(str(offer["price"]))
        if not price.is_finite() or price <= 0 or price.as_tuple().exponent < -2:
            raise ValueError()
    except (KeyError, InvalidOperation, ValueError):
        raise CollectionError("Invalid or missing listed price.") from None
    title = node.get("name")
    if not isinstance(title, str) or not title.strip():
        raise CollectionError("Missing product title.")
    brand = node.get("brand", "")
    if isinstance(brand, dict):
        brand = brand.get("name", "")
    image = node.get("image", "")
    if isinstance(image, list):
        image = image[0] if image else ""
    if isinstance(image, dict):
        image = image.get("url", "")
    availability = {"InStock": "in_stock", "OutOfStock": "out_of_stock", "SoldOut": "out_of_stock"}.get(
        str(offer.get("availability", "")).replace("http://schema.org/", "").replace("https://schema.org/", ""), "unknown")
    return ScrapedProduct(external_id=str(node.get("sku") or node.get("productID") or page_url),
        title=title.strip(), url=page_url, price=price, availability=availability, brand=str(brand),
        gtin=str(node.get("gtin13") or node.get("gtin") or ""), image=urljoin(page_url, image) if isinstance(image, str) and image else "")
