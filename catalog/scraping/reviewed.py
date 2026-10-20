"""Manually reviewed single-item milk pairs; no automatic URL discovery.

Titles and public offer markup reviewed on 20 October 2026. Adding a pair
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
