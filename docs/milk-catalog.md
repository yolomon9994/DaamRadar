# Reviewed five-product milk catalog

Public pages and crawler rules were checked on 20 October 2026 with the configured `DaamRadarBot` identity. The canonical terms pages were rechecked; they describe ordering/delivery/refunds and did not state an explicit factual-price scraping prohibition. This is a limited manual technical review, not a general reuse license or retailer endorsement. Delivery areas remain unverified.

## Reviewed pairs

These are single-item listed prices observed on the public product pages, in PKR. Check times, availability and price history belong to each listing. Prices can change; verify coverage and final costs with the retailer.

| Product | Jalal Sons | Cartpk |
| --- | --- | --- |
| Olper's milk 1L | [350](https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398) | [360](https://www.cartpk.com/olper-s-milk-full-cream-milk-1ltr) |
| Olper's milk 1.5L | [518](https://www.jalalsons.com.pk/product/olpers-milk-15ltr-2809399) | [570](https://www.cartpk.com/olpers-milk-1-5-ltr) |
| Nestle Milkpak 250ml | [94](https://www.jalalsons.com.pk/product/nestle-milkpak-250ml-2809389) | [105](https://www.cartpk.com/nestle-milk-pack-250-ml) |
| Nurpur milk 1L | [358](https://www.jalalsons.com.pk/product/nurpur-milk-1ltr-2809394) | [620](https://www.cartpk.com/nurpur-milk-full-cream-1ltr) |
| Haleeb milk 1L | [334](https://www.jalalsons.com.pk/product/haleeb-milk-1ltr-2809384) | [405](https://www.cartpk.com/haleeb-milk-1ltr) |

The Nurpur price difference is recorded as published; the collector does not correct it using a category page, another store, or an assumed market price. It does not establish branch stock or a final delivery quote. Cartpk's Milkpak 250ml final/sale price was 105 while its regular reference price was 120; final numeric price, visible price and price metadata all agreed on 105.

## Live validation

- Run #7 stored all five Jalal Sons observations in six HTTP requests (robots plus five products), checked 23:32–23:33 PKT on 20 October.
- Run #8 stored the first three Cartpk observations, then stopped with a connection error on Nurpur. It remains `partial`, with three stored observations and five HTTP requests. Haleeb remained pending. No completed observation was rolled back or reimported for recovery.
- Run #9 separately imported the two unfinished Cartpk URLs in three HTTP requests, checked 23:34 PKT. It succeeded with the unchanged collector identity. No automatic connection-error retry or access bypass was added.

The local database has six live canonical products and eleven live listings: five two-retailer pairs plus the earlier single-source Everyday 180ml product. It contains seventeen real history observations. Demo records remain twelve products and thirty-six listings in a separate matching pool. Local reports `reports/scrape-7.json`, `scrape-8.json` and `scrape-9.json` agree with the database audit records. There are no running collection jobs.

All 79 automated tests passed, including both import orders, repeated imports without duplicate products/listings, sale-price extraction, changed-title rejection, pack/variant/packaging negatives, source separation, history, and five-URL dry runs. Django configuration and migration checks passed. Local request checks verified homepage/search/sources and all five product detail/API/history routes, numeric price ordering, fresh in-stock observations, and suppressed winner labels for unverified areas. Browser interactions and PostgreSQL runtime were not tested in this phase.

## Reproduce the imports

On a configured checkout, with migrations applied, `seed_retailers` run, `SCRAPING_ENABLED=true`, a valid contact, and both reviewed sources enabled:

```powershell
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-milk-comparison --dry-run
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-milk-comparison --dry-run
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-milk-comparison --report-dir reports
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-milk-comparison --report-dir reports
```

These batches also create missing listings; `--refresh-existing` alone cannot expand an empty catalog. The original `jalal-sons-basics` and `cartpk-milk-1l` batches still work. A successful recheck appends history without duplicating the listing. Run reports and the local database remain ignored by Git; a code checkout does not include these observations. No scheduler is enabled. See the [collection workflow](collection-workflow.md) for source setup, partial failures and refresh behavior.

## Identity and extraction boundaries

`catalog/scraping/reviewed.py` retains these five milk URL pairs and expected titles inside the full registry. As of 24 October, Cartpk also accepts the three exact paths in the [pantry expansion](pantry-catalog.md), for eight total. Both adapters check the reviewed title for these URLs after parsing; changed names, quantities, packs, packaging or variants fail instead of silently importing a different SKU. Titles must have identical normalized name tokens, alongside the existing hard identity checks. Unreviewed Jalal Sons URLs retain the existing strict JSON-LD behavior.

The matcher adds the observed Nurpur/Haleeb brand names, treats `Milk Pak` as the spelling `Milkpak`, and recognizes the missing space in `Full Cream1Ltr`. These narrow rules do not equate Milkpak with cream or Active Milk, Haleeb with Haleeb Asli, or a single unit with a carton. The fixtures retain the source titles rather than rewriting them to force a match. Milkpak is classified under dairy and uses the milk illustration.

Cartpk's parser still requires one main product block, its heading and final price, visible/numeric price agreement, agreeing PKR metadata, and unambiguous stock labels. Regular prices and recommendation prices cannot substitute for final price. Variant controls and malformed/missing/conflicting factual fields stop collection. No source descriptions, images, executable scripts or session configuration are retained. Fixture provenance is documented [here](../catalog/tests/fixtures/README.md).

During preliminary review, Cartpk closed connections on Milkpak 1L and Haleeb 1L requests. The client stopped without automatic connection-error retries. A separate unchanged-identity Haleeb review succeeded; Milkpak 1L was not included. A Cartpk Olper's 250ml page was inspected but has no reviewed Jalal Sons counterpart in this batch, so it is also excluded from the adapter allowlist. The five-pair scope is deliberate; no category crawling or discovery is added to the collector.
