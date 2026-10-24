"""Manually reviewed single-item product pairs; no automatic URL discovery.

Milk pairs were reviewed on 20 October; pantry pairs on 24 October 2026. Adding a pair
requires a fresh access/markup review and factual-extract regression fixtures.
"""

MILK_REVIEW_DATE = "2026-10-20"
MILK_COMPARISON_PRODUCTS = (
    {
        "title": "Olpers Milk 1L",
        "jalal_path": "/product/olpers-milk-1ltr-2809398",
        "cartpk_path": "/olper-s-milk-full-cream-milk-1ltr",
    },
    {
        "title": "Olpers Milk 1.5L",
        "jalal_path": "/product/olpers-milk-15ltr-2809399",
        "cartpk_path": "/olpers-milk-1-5-ltr",
    },
    {
        "title": "Nestle Milkpak 250ml",
        "jalal_path": "/product/nestle-milkpak-250ml-2809389",
        "cartpk_path": "/nestle-milk-pack-250-ml",
    },
    {
        "title": "Nurpur Milk 1L",
        "jalal_path": "/product/nurpur-milk-1ltr-2809394",
        "cartpk_path": "/nurpur-milk-full-cream-1ltr",
    },
    {
        "title": "Haleeb Milk 1L",
        "jalal_path": "/product/haleeb-milk-1ltr-2809384",
        "cartpk_path": "/haleeb-milk-1ltr",
    },
)

PANTRY_REVIEW_DATE = "2026-10-24"
PANTRY_COMPARISON_PRODUCTS = (
    {
        "title": "Dalda Sunflower Oil Pouch 1L",
        "jalal_path": "/product/dalda-sunflower--oil-pouch-1ltr-2809005",
        "cartpk_path": "/dalda-sunflower-oil-pouch-1ltr",
        "category": "pantry",
        "illustration": "oil",
        "reviewed_at": PANTRY_REVIEW_DATE,
    },
    {
        "title": "Dalda Canola Oil 4.5L",
        "jalal_path": "/product/dalda-canola-oil-45l-2809029",
        "cartpk_path": "/dalda-canola-oil-4-5ltr",
        "category": "pantry",
        "illustration": "oil",
        "reviewed_at": PANTRY_REVIEW_DATE,
    },
    {
        "title": "Shan Biryani Masala 50g",
        "jalal_path": "/product/shan-biryani-masala-50g-2808968",
        "cartpk_path": "/shan-biryani-masala-50g",
        "category": "pantry",
        "illustration": "spice",
        "reviewed_at": PANTRY_REVIEW_DATE,
    },
)

# Keep the original milk tuple/batches stable; the registry covers all reviewed pairs.
REVIEWED_PRODUCTS = tuple({**item, "category": "dairy", "illustration": "milk", "reviewed_at": MILK_REVIEW_DATE}
                          for item in MILK_COMPARISON_PRODUCTS) + PANTRY_COMPARISON_PRODUCTS
REVIEWED_BY_SOURCE = {
    "jalal-sons": {item["jalal_path"]: item for item in REVIEWED_PRODUCTS},
    "cartpk": {item["cartpk_path"]: item for item in REVIEWED_PRODUCTS},
}
COLLECTION_CATEGORIES = {"dairy": ("Dairy & eggs", "milk"), "pantry": ("Pantry essentials", "jar")}
