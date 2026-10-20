"""Strict extraction of factual fields from Cartpk's reviewed Magento markup.

The source's JSON-LD has an invalid escape in its description. We do not repair
or evaluate it: the product's final price must agree with public price metadata.
"""
import re
from decimal import Decimal

from bs4 import BeautifulSoup

from .types import CollectionError, ScrapedProduct


def amount(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d{1,2})?", value.strip()):
        raise CollectionError("Cartpk price is missing or has an unsupported numeric format.", code="parse_error")
    price = Decimal(value.strip())
    if price <= 0:
        raise CollectionError("Cartpk listed price must be positive.", code="parse_error")
    return price


def parse_cartpk_html(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select(".product-info-main")
    headings = soup.select("h1")
    if len(blocks) != 1 or len(headings) != 1:
        raise CollectionError("Expected one Cartpk product block and one product heading.", code="parse_error")
    title = headings[0].get_text(" ", strip=True)
    if not title:
        raise CollectionError("Cartpk product title is empty.", code="parse_error")
    block = blocks[0]
    if block.select('.super-attribute-select, [name^="super_attribute"], .bundle-options-container'):
        raise CollectionError("Cartpk selectable variants require a separately reviewed adapter.", code="parse_error")
    canonical = soup.select('link[rel="canonical"]')
    if canonical and (len(canonical) != 1 or canonical[0].get("href") != page_url):
        raise CollectionError("Cartpk canonical URL disagrees with the requested product.", code="parse_error")

    prices = block.select('[data-price-type="finalPrice"][data-price-amount]')
    if len(prices) != 1:
        raise CollectionError("Expected one Cartpk final price within the product block.", code="parse_error")
    price = amount(prices[0].get("data-price-amount"))
    visible = " ".join(prices[0].get_text(" ", strip=True).split())
    match = re.fullmatch(r"(?:Rs\.?|PKR)\s*(\d+(?:,\d{3})*(?:\.\d{1,2})?)", visible)
    if not match or amount(match[1].replace(",", "")) != price:
        raise CollectionError("Cartpk visible final price disagrees with its numeric field.", code="parse_error")

    currencies = {node.get("content", "").strip() for node in soup.select('meta[property="product:price:currency"]')}
    metadata = soup.select('meta[property="product:price:amount"]')
    if currencies != {"PKR"} or not metadata:
        raise CollectionError("Cartpk must explicitly declare PKR price metadata.", code="parse_error")
    if any(amount(node.get("content")) != price for node in metadata):
        raise CollectionError("Cartpk price metadata disagrees with its final price.", code="parse_error")

    stock = block.select(".stock.available, .stock.unavailable")
    availability = "unknown"
    if stock:
        if len(stock) != 1:
            raise CollectionError("Cartpk stock markers are ambiguous.", code="parse_error")
        label = stock[0].get_text(" ", strip=True).lower()
        if "available" in stock[0].get("class", []) and label == "in stock":
            availability = "in_stock"
        elif "unavailable" in stock[0].get("class", []) and label == "out of stock":
            availability = "out_of_stock"
        else:
            raise CollectionError("Cartpk stock class and visible label disagree.", code="parse_error")
    return ScrapedProduct(external_id=page_url, title=title, url=page_url, price=price,
                          currency="PKR", availability=availability)
