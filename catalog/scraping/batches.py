"""Small reviewed URL sets for repeatable manual collection, never discovery crawls."""
from .reviewed import MILK_COMPARISON_PRODUCTS, MILK_REVIEW_DATE, PANTRY_COMPARISON_PRODUCTS, PANTRY_REVIEW_DATE

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
