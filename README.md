# DaamRadar

A local-first Pakistani grocery discovery and listed-price comparison MVP, built with Python, Django 5.2 LTS, Django REST Framework, Django Templates, Bootstrap 5, and vanilla JavaScript.

**Run locally from GitHub.** A hosted website is optional and deployment work is deferred. You can clone this repository or download its ZIP, run it on `localhost`, and explore the complete application with clearly labeled demo data. Python 3.12 or 3.13 is required; no hosting account, PostgreSQL installation or retailer credentials are needed for the demo. Installing dependencies requires internet access; browsing the seeded demo does not fetch retailer websites.

This is also a data science portfolio project: it combines public-data collection, cleaning, quantity normalization, product entity resolution, and observed-price history. See the [data science case study](docs/data-science-case-study.md) for implemented methods, evidence, limitations and the next analytical milestones.

**Data status:** the author's local development catalog contains **31 collected products and 40 listings** across dairy, pantry, drinks and household categories. Nine products have reviewed listings from both Jalal Sons and Cartpk; the remaining 22 have one reviewed source. **This development database is not included in a Git clone or ZIP.** Prices are dated observations, not real-time quotes or delivery guarantees. Delivery areas remain unverified, so no winning retailer or savings claim is shown. A fresh setup instead provides 12 seeded products and 36 seeded listings as fictional demo data. See the [29 October expansion and import batches](docs/expanded-catalog.md), earlier [pantry](docs/pantry-catalog.md)/[milk](docs/milk-catalog.md) reviews and [collection runbook](docs/collection-workflow.md).

On **29 October 2026**, six bounded import runs added 23 fresh listings and their captured observations, bringing real history to 57 records. The earlier 17 listings retain their original 23–24 October check times and are stale at this validation. The imports preserved every earlier record and did not manufacture trends. Freshness changes with time; a new checkout must collect its own observations.

## Quick start: Windows / PowerShell

Install Python 3.12 or 3.13 first. With Git installed:

```powershell
git clone https://github.com/yolomon9994/DaamRadar.git
cd DaamRadar
```

Alternatively, choose **Code → Download ZIP** on GitHub, extract it, and open a terminal in the extracted folder containing `manage.py`. Git is not needed for that option. From that folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open **http://127.0.0.1:8000/**. No account is required. Virtual-environment activation is optional; using the executable directly avoids PowerShell execution-policy issues. The first setup loads fictional examples and does not collect live prices. Stop the server with **Ctrl+C**.

To start it again later, open a terminal in the same project folder and run only:

```powershell
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

If `python` is not found on Windows, try `py -3.13 -m venv .venv` for the environment-creation step. Keep the server bound to `127.0.0.1` for local use. To choose another port, replace `8000` with `8001` in both the command and browser URL.

## Quick start: macOS / Linux

Clone or extract the repository, open its folder, and use an installed Python 3.12/3.13 executable:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
test -e .env || cp .env.example .env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

Open **http://127.0.0.1:8000/**. These instructions use the same SQLite/demo configuration; local runtime verification in the development workspace uses Windows/Python 3.13.

Try `Olpers Milk 1L` in the collected catalog. The website and API default to collected records once any exist; a fresh database with only demo fixtures defaults to demo. Switch to **Demo catalog** for `nutela`, `Surf Excel`, or `National Ketchup 400g`. Select category, retailer, brand, or sorting and press **Apply**. Collected product details show real source links, schema availability, check time, and history. One source is labeled an observed price, with no winning-retailer badge. Demo links remain disabled. Real observations are stored in your ignored local database; a fresh checkout must collect its own observations.

`seed_demo` can be rerun: it refreshes demo observations without duplicating products/listings or creating a fictitious history trend. It never modifies live products. To initialize retailer records without sample products, use `python manage.py seed_retailers`.

## Plan a shopping list

Select **Add to list** on product cards or detail pages, then open **Shopping list** in the header. Adjust pack quantities and compare retailer coverage, included-item subtotals and full observed estimates where available. Missing, stale or unavailable items are flagged; incomplete baskets never receive a full total. Delivery-area conflicts also withhold full estimates, and unverified areas carry a warning. Delivery fees and checkout charges are excluded.

Demo and collected lists stay separate and are saved in the same browser without an account. JavaScript and browser storage enable persistence; the page warns if storage is unavailable. No live collection runs when using the list. See [shopping-list behavior, API and checks](docs/shopping-list.md).

Use **Add groceries to this list** to search the active catalog without leaving the list. Check the exact pack size, then select **Add 1 pack**. After removing an item or clearing the list, **Undo** restores that latest action until the next list edit or a list change in another tab. Estimates reload from the local catalog. See [search and undo rules](docs/shopping-list.md#find-products-and-undo-removals).

Under **Plan your shopping budget**, enter a PKR amount and select **Save budget**. Complete retailer estimates show the amount remaining, exact equality or an overage; incomplete or conflicting-area baskets show **Cannot assess full budget**. Demo and Collected budgets stay separate in this browser. Budget comparisons exclude delivery and checkout charges. See [budget rules](docs/shopping-list.md#set-a-shopping-budget).

To take a checklist to the store, open **Take your list with you**, select a retailer (or items only), and choose **Print / Save as PDF**. The print view includes pack sizes, quantities, purchase checkboxes, dated observations and any exclusion/area warnings. Choose **Save as PDF** in the browser's print dialog to keep a copy on your phone. See [printing instructions](docs/shopping-list.md#print-a-checklist-or-save-a-pdf).

To back up or move an editable list, use **Back up or transfer your list → Download list JSON**. On another local installation, choose **Preview a list file**, review local matches, then **Merge** quantities or **Replace** that catalog's list. Files contain product identities and quantities; prices come from the receiving database. Uncertain matches remain visible and unpriced. See [transfer rules and file format](docs/shopping-list.md#back-up-or-transfer-an-editable-list).

On **Watchlist**, use **Back up targets and budget** to download a separate JSON backup for the active catalog. Preview exact product matches and the budget change, then choose **Replace targets and budget** to restore. Unmatched targets remain visible without price alerts. Shopping-list items and the other catalog are kept. See [backup rules and format](docs/planning-backups.md).

Product cards, retailer listings and included basket items also show **Rs/L**, **Rs/kg** or **Rs/item** alongside the pack price. These rates use total pack contents, including multipacks; unknown sizes show **Unit price unavailable**. For example, the fictional demo's 250 ml milk at Rs. 85 is Rs. 340/L. See [calculation rules and API fields](docs/unit-pricing.md).

To follow a regular purchase, select **Watch price** on its card or detail page, enter your target pack price in PKR, and save it. Open **Watchlist** in the header to check, edit or remove targets. Fresh, in-stock observations at or below the target show **Observed target met** with check times and delivery warnings. Targets stay in this browser, separately for Demo and Collected; checks use stored data when you open the watchlist/product or select **Check targets**. See [watchlist behavior and limits](docs/watchlist.md).

## Implemented

- Responsive homepage, category navigation, search, comparison cards, detail tables, source transparency, and empty/error states.
- Browser-saved shopping lists with pack quantities, separate demo/collected lists and read-only retailer basket estimates. Per-item exclusions and coverage keep incomplete subtotals separate from full estimates; no cheapest-basket claim is made. See [shopping lists](docs/shopping-list.md).
- Separate saved Demo/Collected shopping budgets, exact Decimal remaining/over-budget amounts for complete baskets, and retailer print/PDF budget summaries. Incomplete baskets cannot claim to fit a budget.
- Standard-unit price labels (Rs/L, Rs/kg and Rs/item) on cards, detail listings, basket breakdowns and retailer print checklists. Decimal calculations include multipacks and preserve the original eligibility/area rules. See [unit pricing](docs/unit-pricing.md).
- A dedicated **Pack sizes & value** view groups exact compatible product identities across sizes/counts, shows total contents and dated retailer rates, and adds the chosen pack to the existing shopping list. Value highlights require fresh in-stock observations and matching delivery evidence; unknown/conflicting data withholds them. See [pack comparison rules and API](docs/pack-comparison.md).
- Browser-saved target-price watchlists with per-pack thresholds, explicit fresh/in-stock matches, observation timestamps, delivery caveats and separate Demo/Collected targets. Local checks expire old results and never trigger retailer collection. See [watchlists](docs/watchlist.md).
- Retailer-selectable shopping checklists for browser printing/Save as PDF, with pack sizes, purchase checkboxes, check dates and exclusions. Items-only mode omits prices; printed totals retain the same basket safeguards.
- Shopping-list JSON downloads and import previews with explicit merge/replace choices, conservative local identity matching, catalog separation and retained unpriced items. Imports never restore prices or modify the catalog.
- Local database search with case-insensitive partial and fuzzy matches; compatible size filtering; category/retailer/brand filters; price sorting; pagination.
- Local search suggestions with keyboard controls, fresh-check/in-stock filters, validated PKR pack-price ranges and scoped empty-result recovery. Offer conditions must match one listing; other offers remain visible for comparison context. See [search rules and API](docs/search.md).
- Separate canonical products, categories, retailers, listings, observations, and scrape audit runs, with migrations and database constraints.
- Normalized metric quantities, brand aliases, pack counts, variant and packaging guards, GTIN checks, RapidFuzz ranking, and conservative canonical linking.
- Atomic listing upserts with a history observation for every check, even if the price is unchanged.
- Product price-history charts with separate retailer series, dated PKR markers, keyboard/pointer inspection, retailer filters and an exact-values table. Single observations remain single points; fictional demo histories stay labeled. SVG and table work without JavaScript. See [chart behavior and validation](docs/price-history.md).
- Recorded price-change indicators on cards/detail listings and the product API. New observations capture pack, source, stock and delivery context; unknown or incompatible histories withhold changes. Existing history is preserved without guessed metadata. See [change rules and migration](docs/price-changes.md).
- Read-only REST API, administration interface, SQLite default, and environment-based PostgreSQL configuration.
- Evidence-based delivery-area comparisons: live winners require a shared scope and dated, source-linked evidence for each eligible observation. New imports clear old verification. Dated public delivery findings appear on the sources page; current listings remain unverified. See [delivery findings and validation](docs/delivery-areas.md).
- Admin collection-health dashboard with per-source freshness, successful/latest runs, paused/running source state, a paginated stale-listing queue and recent failures/partial runs. It excludes demo data and requires the relevant model view/change permissions. See [dashboard access and behavior](docs/collection-health.md).
- Read-only **Catalog quality** report in Products admin, with missing metadata, possible duplicates, barcode/pack/source conflicts, uncertain matches, filtered JSON downloads and a matching local command. Findings link to records for manual review; nothing is merged or collected. See [checks, limits and usage](docs/catalog-quality.md).
- Public **Our sources** overview with dated collected/fresh/stale counts, source configuration and recorded outcomes, PKT check times and source-filtered browsing. Management links follow existing admin permissions; raw operator logs stay private. Viewing or reloading reads stored data only. See [public freshness behavior and validation](docs/public-source-health.md).
- Admin-only manual price refresh with a separate finite local worker, persistent progress/audit links, stale-only reviewed URLs and database overlap protection. Requires explicit start permission and configured sources; viewing pages never starts collection. See [admin refresh and recovery](docs/admin-refresh.md).
- Reviewed-batch imports from admin with missing/existing previews, account-bound signed approval, create-only ingestion and the same worker/overlap safeguards. Existing prices and histories are preserved. See [catalog import](docs/admin-catalog-import.md).
- Collection framework: bounded requests, fixed identifying user agent, fail-closed robots, crawl delays, one delayed retry for timeouts only, no access-denial retries, structured errors, per-URL reports, and overlap protection.
- A manual `refresh_prices` command checks stale existing listings from Jalal Sons and then Cartpk, retains per-source audit/report details, and prints a combined summary. Fresh data is skipped; retailer errors produce a nonzero exit after the other source is attempted. See [usage and outcomes](docs/refresh-prices.md).
- Manual Jalal Sons and Cartpk public-HTML adapters with reviewed URL/identity metadata, original milk/pantry batches and six additional source/category batches. Real-only imports create categories and owned illustrations without loading demo data. Cartpk accepts twelve exact reviewed paths and requires visible price, numeric final price and explicit PKR metadata to agree, excluding regular/reference prices. Its malformed description JSON-LD is neither repaired nor used. Naheed's parser is retained offline after a denied collector request; Springs and Al-Fatah remain disabled.
- Synthetic and minimal factual-extract fixture tests, with provenance. Source descriptions, images, session data, and unrelated configuration are not imported.
- GitHub CI for Python 3.12/3.13 with SQLite/PostgreSQL 17: locked dependencies, Django/migration checks, fresh database migrations, offline tests and production static-file collection. See [automated checks and local reproduction](docs/continuous-integration.md).
- Production profile and cross-platform Waitress startup, database readiness at `/health/`, and real production HTTP smoke checks in CI. See [deployment configuration and commands](docs/deployment.md).
- Consistent SQLite backups with integrity verification and non-overwrite behavior; documented and locally validated SQLite/PostgreSQL restore procedures. See [backup/restore](docs/backups.md).

## API

| Endpoint | Result |
| --- | --- |
| `GET /api/products/` | Paginated comparisons, collected source when present, otherwise demo |
| `GET /api/products/<slug>/` | Product and ascending-price listings |
| `GET /api/categories/` | Grocery categories |
| `GET /api/retailers/` | Retailers, availability status, and access notes |
| `GET /api/listings/<id>/history/` | Paginated newest-first price observations |
| `GET /api/basket/?source=demo&item=<slug>:<quantity>` | Read-only retailer basket coverage and item-price estimates |
| `GET /api/watchlist/?source=demo&item=<slug>:<target>` | Read-only target checks against fresh, in-stock observed pack prices |
| `POST /api/shopping-list/preview/` | Read-only list-file validation and local product resolution; no list or catalog writes |
| `POST /api/preferences/preview/` | Read-only watch-target/budget backup validation and local product resolution; no saved-preference or catalog writes |
| `GET /health/` | Database connectivity readiness; generic 200/503 response |

Product list parameters: `q`, `category` (slug), `retailer` (slug), `brand`, `source=demo|live`, `sort=relevance|price_asc|price_desc`, `page`, and `page_size` (up to 48).

Product listings include guarded `price_change` metadata. Historical observations expose their captured `context`; history `is_demo` is nullable for legacy observations whose source was not recorded. See [history compatibility and migration](docs/price-changes.md).

```text
/api/products/?q=Olpers%20Milk%201L&source=demo
/api/products/?category=pantry&sort=price_asc
/api/products/?source=live
```

Demo/live flags are explicit in serialized results. Amounts are decimal strings, denominated in PKR. `best_price` excludes stale, out-of-stock, and unknown-availability offers. Live `has_comparison` requires multiple retailers with evidence for the same delivery scope for every eligible observation; matching area text alone is insufficient. `has_unverified_areas` and `has_mixed_areas` expose area caveats. Listings include `area_is_verified`, `delivery_area_key`, `area_evidence_url` and `area_verified_at`; `comparison_area` describes the qualifying area. APIs do not accept anonymous writes. Anonymous API traffic is limited to 120 requests/minute per application cache/IP; use shared caching and correctly configured proxies for a multi-process production deployment.

## Checks

For catalog review, open **Admin → Products → Catalog quality**, or run these read-only commands:

```powershell
.\.venv\Scripts\python.exe manage.py catalog_quality
.\.venv\Scripts\python.exe manage.py catalog_quality --source demo
.\.venv\Scripts\python.exe manage.py catalog_quality --severity error --format json
```

Collected data is the default; Demo must be selected explicitly. Findings are review candidates, and any scan limits are reported. The report does not certify matching accuracy or change records. See [catalog-quality rules](docs/catalog-quality.md).

Run the project checks:

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

Tests cover matching, search/filters, source separation and selection, price ranking, stale/unavailable observations, area and single-source safeguards, idempotent seeding, API behavior, ingestion/history, observed source formats, heading checks, robots wildcard precedence, timeouts, manual upserts, partial runs, and unavailable sources. They make no retailer network calls. See [fixture provenance](catalog/tests/fixtures/README.md). Bootstrap is vendored locally with its source map and MIT license.

Use `manage.py test --settings=config.ci --noinput` to run with in-memory SQLite and a runner that rejects unmocked requests HTTP calls. CI uses the same configuration with a separate `CI_DATABASE_URL` for its disposable PostgreSQL service. Hosted workflow results become available after pushing this change; see the [CI guide](docs/continuous-integration.md).

## Collection and manual setup

Jalal Sons and Cartpk have limited manual adapters. No scheduler, Celery, or cron job is activated. The current workspace has manual collection configured for those two retailers. A fresh checkout defaults to collection disabled.

```powershell
.\.venv\Scripts\python.exe manage.py seed_retailers
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --url 'https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398'
```

The command checks robots and records fresh observations. Only timeout exceptions get one delayed additional attempt; access denials, redirects, HTTP errors, and challenges stop immediately. Parser errors preserve the previous price and check time. Naheed, Springs, and Al-Fatah remain disabled at the adapter level. The three Jalal Sons records were refreshed successfully on 20 October in four HTTP requests, with no duplicate listings. See the [runbook](docs/collection-workflow.md) for detailed behavior and configuration.

For repeatable manual collection:

```powershell
# Preview stale existing URLs for both reviewed retailers:
.\.venv\Scripts\python.exe manage.py refresh_prices --dry-run
# Refresh both sources sequentially with their individual reports:
.\.venv\Scripts\python.exe manage.py refresh_prices --report-dir reports
# Preview the saved three-product batch without making requests or writing data:
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-basics --dry-run
# Refresh existing stale observations; do nothing when all are fresh:
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --refresh-existing --stale-only --report-dir reports
```

Reports are written as `reports/scrape-<run-id>.json` and remain local. After pulling this change, run `manage.py migrate` for the structured run fields and the one-active-run-per-retailer constraint. No scheduler is activated.

The reviewed five-product batches (both support dry runs):

```powershell
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-milk-comparison --dry-run
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-milk-comparison --dry-run
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-milk-comparison --report-dir reports
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-milk-comparison --report-dir reports
# Later, refresh only existing stale Cartpk records:
.\.venv\Scripts\python.exe manage.py scrape cartpk --refresh-existing --stale-only --report-dir reports
```

The initial Cartpk import was run #6: one listing linked to the existing 1L canonical product. The expanded batches also create missing listings; existing-only refresh cannot do that on an empty checkout. Source detail pages and the product API sort offers by numeric listed prices and retain source links, check times, availability and area caveats. The original small batches remain available. After `seed_retailers`, enable each reviewed source in admin or use the setup command below with its slug (`jalal-sons` or `cartpk`). Do not enable other Cartpk URLs without further markup/access review. See the [reviewed catalog](docs/milk-catalog.md) for exact pairs, fixture evidence and live run outcomes.

For a fresh setup, configure `.env` with `SCRAPING_ENABLED=true` and `SCRAPER_CONTACT` as a monitored email or public HTTPS project/contact URL. Enable the reviewed source only:

```powershell
.\.venv\Scripts\python.exe manage.py shell -c "from catalog.models import Retailer; Retailer.objects.filter(slug='jalal-sons').update(status='enabled', collection_enabled=True)"
```

This only enables explicit manual commands. It does not activate background or automatic scraping. Product links should be checked against currently published crawler rules before adding new URLs; the client checks robots again on each run. Delivery area is explicitly unverified, and schema `InStock` is not a delivery guarantee.

To enable a future source:

1. Establish the applicable data-access and reuse basis, review source terms/robots, and validate product/variant/location behavior. Record dated evidence in `docs/retailer-review.md`. An API/feed agreement is preferable for broader publication; open-source code and nonprofit intent do not grant rights in third-party content.
2. Implement and test that retailer's `collect(client, url)` adapter using real, permitted saved fixtures. Set its code-level `enabled` flag only after that validation. The current JSON-LD parser accepts one unambiguous PKR offer and intentionally rejects ranges and multiple variants.
3. Set `SCRAPER_CONTACT` to your monitored email or public HTTPS project/contact URL and `SCRAPING_ENABLED=true` in `.env`. Mark that retailer `Validated` and enable collection in Django admin. Use at least the configured five-second delay and any stricter robots delay. The command accepts at most ten explicit URLs; it is not a catalog crawler.
4. Run a small manual collection and inspect listing titles, sizes, prices, availability, URLs, delivery areas, and scrape logs before adding a scheduler. Access challenges, 403, 429, and redirects stop collection without retries.

Create your own admin credentials if needed:

```powershell
.\.venv\Scripts\python.exe manage.py createsuperuser
```

Visit `/admin/`. No default account or password is bundled.

Choose **Collection health** in the admin header, or open `/admin/catalog/retailer/collection-health/`. It brings together stored-data freshness, source configuration, run history and listings due for another check. Loading it does not trigger collection or change records. See the [dashboard guide](docs/collection-health.md) for required permissions and freshness semantics.

To refresh through the website, apply migrations, sign in as a superuser or authorized operator, choose sources under **Manual price refresh**, and select **Start manual refresh**. The saved progress page follows a separate local worker; fresh listings are skipped, partial observations retained and duplicate active admin requests refused. Sources/contact settings must already be configured. See [permissions, limits and recovery](docs/admin-refresh.md). This adds no scheduler or automatic collection on page views.

For first-time real data, choose **Import reviewed catalog — preview batches** from collection health. Select a saved milk/pantry batch, preview the missing listings, then choose **Import N missing listings**. This requires the separate import permission and explicit source configuration. Existing listings are skipped regardless of freshness; imports do not refresh their prices/history. See [preview, setup and import behavior](docs/admin-catalog-import.md).

## PostgreSQL and deployment

Install PostgreSQL and create a database/user through your normal local administration workflow. Set an appropriately escaped URL in `.env`:

```dotenv
DATABASE_URL=postgresql://daamradar:YOUR_PASSWORD@localhost:5432/daamradar
```

Then run `manage.py migrate` against that configured database. SQLite data is not automatically transferred. To seed PostgreSQL for development, run `seed_demo` again. SQLite remains the default development database. All 168 tests passed locally with Python 3.13 against both SQLite and an isolated PostgreSQL 17.11 cluster; see [deployment validation](docs/deployment.md#validation-24-october-2026).

Use the [production environment example](.env.production.example) in a separate deployment checkout. Run migration/static/deployment checks with `--settings=config.production`, then start `python -m config.serve` with the host, port and exact trusted proxy IP appropriate to the environment. The production profile requires debug off, a secret and explicit allowed hosts. HTTPS, process supervision, HSTS policy and shared caching depend on the actual host; HSTS is deliberately deferred and `check --deploy` reports that warning. The [deployment guide](docs/deployment.md) provides exact steps and proxy details. No hosted deployment has been provisioned.

To exercise the production server locally using temporary data without editing `.env`:

```powershell
.\.venv\Scripts\python.exe scripts/smoke_production.py
# Create a new, verified backup of the current local SQLite database:
.\.venv\Scripts\python.exe manage.py backup_sqlite backups/daamradar-2026-10-24.sqlite3
```

## Layout

```text
config/                   Django configuration, URLs, WSGI/ASGI
catalog/models.py         Canonical products, retailers, listings, history, runs
catalog/views.py          Template views
catalog/api/              Read-only REST views and serializers
catalog/matching/         Normalization and compatible-identity matching
catalog/services/         Local search/comparison and atomic ingestion
catalog/scraping/         HTTP client, parsing, per-retailer adapter boundaries
catalog/management/       Seed and manual collection commands
catalog/tests/            Automated tests and documented source-format extracts
templates/                Django templates
static/                   Custom styles, SVG illustrations, JS, Bootstrap
docs/                     Architecture and dated source investigation
```

`requirements.txt` declares supported ranges; `requirements.lock.txt` records the exact versions installed during this build.

## Current focus and next implementation phase

Follow the [ordered v1 roadmap](docs/roadmap.md). The analysis-export/notebook and measured matching-evaluation milestones (original items 9 and 10) are excluded from the current release plan at the author's request.

The current distribution target is a downloadable local application with useful grocery-planning features. Hosting is deferred; the production tooling remains available for later use. Shopping lists and retailer basket estimates now support planning across multiple products. The [portfolio case study](docs/data-science-case-study.md) records implemented data work and possible future analytical milestones separately.

Nine real cross-retailer listed-price pairs are functional across dairy and pantry in the author's development database; 22 other products have one reviewed source. The [24 October delivery investigation](docs/delivery-areas.md) found public delivery claims but no verified shared price/stock scope; comparison requires explicit observation-level evidence. A supported location-specific page/feed and sustained source reliability remain future research. Naheed needs its denied access resolved without identity switching. Establish appropriate broader reuse arrangements and a safe frequency before publishing a large dataset or scheduling collection.

Current limits: Cartpk's adapter is restricted to twelve exact URLs; sustained reliability and delivery areas remain unverified; no final delivered-cost comparison is claimed. Prior connection failures remain in the audit history; the six 29 October imports all succeeded. Olpers Mart is not enabled. There is no scheduler, checkout/delivery, or location selector. History charts show up to 120 recent observations per listing, with older records available through the paginated API; real histories are still sparse. Search scores at most 1,000 candidates. Refreshes select the oldest ten URLs per source; further due URLs require another explicit manual run. Matching and catalog-quality review remain on the [v1 roadmap](docs/roadmap.md). Local validation uses Windows/Python 3.13; hosted CI results must be checked after pushing.
