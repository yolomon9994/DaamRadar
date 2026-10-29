"""Small reviewed URL sets for repeatable manual collection, never discovery crawls."""
from .reviewed import MILK_COMPARISON_PRODUCTS, MILK_REVIEW_DATE, PANTRY_COMPARISON_PRODUCTS, PANTRY_REVIEW_DATE
from .expansion import EXPANSION_PRODUCTS, EXPANSION_REVIEW_DATE

BATCHES = {
    "jalal-sons-pantry-comparison": {
        "retailer": "jalal-sons",
        "reviewed_at": PANTRY_REVIEW_DATE,
        "urls": ["https://www.jalalsons.com.pk" + item["jalal_path"] for item in PANTRY_COMPARISON_PRODUCTS],
    },
    "cartpk-pantry-comparison": {
        "retailer": "cartpk",
        "reviewed_at": PANTRY_REVIEW_DATE,
        "urls": ["https://www.cartpk.com" + item["cartpk_path"] for item in PANTRY_COMPARISON_PRODUCTS],
    },
    "cartpk-milk-comparison": {
        "retailer": "cartpk",
        "reviewed_at": MILK_REVIEW_DATE,
        "urls": ["https://www.cartpk.com" + item["cartpk_path"] for item in MILK_COMPARISON_PRODUCTS],
    },
    "jalal-sons-milk-comparison": {
        "retailer": "jalal-sons",
        "reviewed_at": MILK_REVIEW_DATE,
        "urls": ["https://www.jalalsons.com.pk" + item["jalal_path"] for item in MILK_COMPARISON_PRODUCTS],
    },
    "cartpk-milk-1l": {
        "retailer": "cartpk",
        "reviewed_at": "2026-10-20",
        "urls": ["https://www.cartpk.com/olper-s-milk-full-cream-milk-1ltr"],
    },
    "jalal-sons-basics": {
        "retailer": "jalal-sons",
        "reviewed_at": "2026-10-18",
        "urls": [
            "https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398",
            "https://www.jalalsons.com.pk/product/olpers-milk-15ltr-2809399",
            "https://www.jalalsons.com.pk/product/nestle-everyday-milk-180ml-2809387",
        ],
    },
}

# Each source/category group is an explicit, independently selected manual run.
# Empty groups are omitted; the collector's ten-URL cap is unchanged.
for source, origin, path_key in (("jalal-sons", "https://www.jalalsons.com.pk", "jalal_path"),
                                 ("cartpk", "https://www.cartpk.com", "cartpk_path")):
    for category in ("dairy", "pantry", "drinks", "household"):
        urls = [origin + item[path_key] for item in EXPANSION_PRODUCTS
                if item["category"] == category and path_key in item]
        if urls:
            BATCHES[f"{source}-expanded-{category}"] = {
                "retailer": source, "reviewed_at": EXPANSION_REVIEW_DATE, "urls": urls,
            }


def reviewed_urls(retailer_slug):
    """Exact URLs in saved reviewed batches, including original single-source items."""
    return frozenset(url for batch in BATCHES.values() if batch["retailer"] == retailer_slug for url in batch["urls"])
