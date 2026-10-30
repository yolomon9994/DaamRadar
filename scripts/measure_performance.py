"""Warm request timings using disposable synthetic data and in-memory SQLite."""
import argparse
from decimal import Decimal
from io import StringIO
import json
import os
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=7, help="Measured requests per route, from 1 to 30.")
    parser.add_argument("--output", type=Path, help="Optional new JSON filename; existing files are never replaced.")
    options = parser.parse_args()
    if not 1 <= options.samples <= 30:
        parser.error("Use between 1 and 30 samples.")
    if options.output and options.output.exists():
        parser.error("Choose a new output filename; existing files are never replaced.")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    # Always override both selectors before Django initializes; never open the
    # development DATABASE_URL, even when the caller has CI_DATABASE_URL set.
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.ci"
    os.environ["CI_DATABASE_URL"] = "sqlite:///:memory:"
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from django.test import Client, override_settings
    from django.test.utils import CaptureQueriesContext
    from django.utils import timezone
    from catalog.models import Category, Product, Retailer, RetailerListing, PriceHistory

    with patch("requests.sessions.Session.send", side_effect=AssertionError("No external HTTP during measurement")):
        call_command("migrate", verbosity=0)
        call_command("seed_demo", stdout=StringIO())
        category = Category.objects.get(slug="dairy")
        now = timezone.now()
        Product.objects.bulk_create([Product(slug=f"perf-milk-{i}", canonical_name=f"QA Milk Grocery {i:03} 1L",
            brand="QA", quantity=Decimal("1000"), unit="ml", category=category) for i in range(300)])
        products = list(Product.objects.filter(is_demo=False).order_by("pk"))
        retailers = list(Retailer.objects.order_by("pk")[:3])
        RetailerListing.objects.bulk_create([RetailerListing(product=p, retailer=r, external_id=p.slug,
            original_title=p.canonical_name, current_price=Decimal("300") + i, availability="in_stock",
            last_checked=now, delivery_area="Area unverified") for p in products for i, r in enumerate(retailers)])
        PriceHistory.objects.bulk_create([PriceHistory(listing=o, price=o.current_price, checked_at=now)
            for o in RetailerListing.objects.filter(is_demo=False) for _ in range(2)])
        items = "&".join("item=" + p.slug + ":2" for p in products[:50])
        targets = "&".join("item=" + p.slug + ":300.00" for p in products[:50])
        routes = {"home": "/?source=live", "filtered_search": "/?source=live&q=milk&fresh=1&in_stock=1&max_price=302",
            "suggestions": "/api/search-suggestions/?source=live&q=milk", "detail": "/products/perf-milk-0/",
            "pack_comparison": "/products/perf-milk-0/pack-comparison/", "sources": "/sources/",
            "basket_50": "/api/basket/?source=live&" + items, "targets_50": "/api/watchlist/?source=live&" + targets}
        client, metrics = Client(), {}
        with override_settings(ALLOWED_HOSTS=["testserver"], DEBUG=False):
            for name, url in routes.items():
                if client.get(url).status_code != 200:
                    raise RuntimeError("Warm-up request failed: " + name)
                samples, counts, sizes = [], [], []
                for _ in range(options.samples):
                    with CaptureQueriesContext(connection) as queries:
                        started = perf_counter()
                        response = client.get(url)
                        elapsed = (perf_counter() - started) * 1000
                    if response.status_code != 200:
                        raise RuntimeError("Measured request failed: " + name)
                    samples.append(round(elapsed, 3)); counts.append(len(queries)); sizes.append(len(response.content))
                metrics[name] = {"median_ms": round(median(samples), 2), "maximum_ms": max(samples),
                                 "queries": max(counts), "response_bytes": max(sizes), "samples_ms": samples}
    connection.close()
    result = {"dataset": {"collected_products": 300, "collected_listings": 900, "collected_history": 1800,
                          "demo_products": 12, "demo_listings": 36},
              "environment": "Python/Django Client, config.ci SQLite memory, warm sequential requests; no network/browser timings",
              "samples_per_route": options.samples, "metrics": metrics}
    serialized = json.dumps(result, indent=2) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        with options.output.open("x", encoding="utf-8") as output:
            output.write(serialized)
    print(serialized, end="")


if __name__ == "__main__":
    main()
