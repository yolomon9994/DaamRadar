# Three reviewed pantry pairs

These non-dairy products were reviewed and collected on **24 October 2026**. Prices are dated public listed prices in PKR, before delivery/checkout costs. Delivery areas remain unverified; no winning-retailer or savings claim is shown.

| Product | Jalal Sons | Cartpk |
| --- | --- | --- |
| Dalda Sunflower Oil Pouch 1L | [609](https://www.jalalsons.com.pk/product/dalda-sunflower--oil-pouch-1ltr-2809005) | [630](https://www.cartpk.com/dalda-sunflower-oil-pouch-1ltr) |
| Dalda Canola Oil 4.5L | [2,834](https://www.jalalsons.com.pk/product/dalda-canola-oil-45l-2809029) | [3,150](https://www.cartpk.com/dalda-canola-oil-4-5ltr) |
| Shan Biryani Masala 50g | [158](https://www.jalalsons.com.pk/product/shan-biryani-masala-50g-2808968) | [130](https://www.cartpk.com/shan-biryani-masala-50g) |

All six pages reported in-stock availability. The sunflower titles explicitly identify a pouch. Canola/spice titles do not specify packaging; it stays unspecified rather than inferred from size. Brand, normalized size/unit, variant, pack count and normalized name tokens agree within each pair. Source titles are preserved, and demo records stay separate.

## Review and implementation

The existing named collector rechecked robots and canonical terms, then inspected the exact product pages. The same source-access limits in the [retailer review](retailer-review.md) apply. No internal APIs, source photos/descriptions, account data, identity switching or access bypass were used. Cartpk closed connections during preliminary terms/Korma review; the client stopped without automatic connection-error retries. Separate unchanged-identity reviews succeeded. Tea/water candidates lacked an exact counterpart; Korma was not included. Search/category snapshots were not substituted for the independently checked Biryani product price of 130.

The reviewed registry retains five milk pairs and adds three pantry pairs, with expected titles, dates, categories and owned illustrations. Cartpk now accepts only eight exact paths. Both adapters check the reviewed identity at those URLs. Oil types and selected spice variants have hard matching guards; size, packaging and pack checks remain, with no lower matching threshold. The strict Cartpk final/visible/metadata PKR checks remain unchanged.

Collection assigns Pantry essentials and the existing oil/spice illustrations from reviewed URL metadata. A missing category can be created without loading demo products. Unreviewed products receive no guessed pantry classification. Fixtures are minimal factual extracts with [documented provenance](../catalog/tests/fixtures/README.md).

## Commands

On a configured checkout with the reviewed sources enabled:

```powershell
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-pantry-comparison --dry-run
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-pantry-comparison --dry-run
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-pantry-comparison --report-dir reports
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-pantry-comparison --report-dir reports

# Later, refresh stale existing milk and pantry listings together:
.\.venv\Scripts\python.exe manage.py refresh_prices --report-dir reports
```

Old milk batches are unchanged. The new pantry batches have three URLs each. The ten-URL cap is unchanged: Jalal Sons now has nine collected URLs and Cartpk has eight. More data may require smaller explicit batches; the wrapper does not silently split or exceed the cap. No scheduler is enabled.

## Validation

Run #12 stored three Jalal Sons observations in four requests, checked 20:34:42–20:34:52 PKT on 24 October. Run #13 stored three Cartpk observations in four requests, checked 20:35:03–20:35:20 PKT. Both succeeded and their reports agree with the database.

A before/after audit preserved all earlier products, listings, history, retailer records and runs. The catalog now has **nine real products, seventeen listings and thirty-four real history observations**. Twelve demo products and thirty-six demo listings remain separate. All seventeen collected listings were fresh at validation; no jobs were running.

Actual product pages, category/brand/retailer/size filters, product/history APIs and admin health were checked. Each new product has two real source links, two historical points (one per source), the correct category/illustration and the delivery-area caveat. No trend is invented from single observations.

All **139 tests** passed, including thirteen pantry tests covering source formats, both import orders, repeats, identity drift, URL scoping, conflicting prices, category/filter behavior, real-only setup, stale refresh and fresh no-ops. Django configuration and migration checks passed; there are no new dependencies or migrations. Headless Chrome checked pantry snapshots at 1280px and 390px, including all three cards, both retailers, selected filters, rendered oil/spice SVGs and page width. PostgreSQL was not tested.

Observations, reports `scrape-12.json`/`scrape-13.json`, `pantry-validation-2026-10-24.json`, screenshots and audit helpers remain local under ignored `reports/`. A Git checkout contains code, minimal fixtures and documentation, not the development database.
