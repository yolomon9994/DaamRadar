# DaamRadar

A local-first Pakistani grocery discovery and listed-price comparison MVP, built with Python, Django 5.2 LTS, Django REST Framework, Django Templates, Bootstrap 5, and vanilla JavaScript.

**Data status:** the local database contains three real, dated Jalal Sons observations collected on 18 October 2026: Olpers Milk 1Ltr (PKR 350), Olpers Milk 1.5Ltr (PKR 518), and Nestle Everyday Milk 180Ml (PKR 44). These are not real-time quotes or delivery guarantees. One intermediate run timed out; a later manual invocation completed the batch. The 12 seeded products and 36 seeded listings remain clearly labeled fictional demo data. See [the source investigation](docs/retailer-review.md).

## Run on Windows / PowerShell

Python 3.12 or 3.13 is recommended. The current workspace has a Python 3.13 virtual environment, installed dependencies, migrations applied, and demo data loaded.

```powershell
cd 'I:\Personal Projects\DaamRadar'
# For a fresh checkout:
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
# Start here if the workspace is already initialized:
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open **http://127.0.0.1:8000/**. No account is required. Virtual-environment activation is optional; using the executable directly avoids PowerShell execution-policy issues. Copy `.env.example` only if you do not already have a `.env` file.

Try `Olpers Milk 1L` in the collected catalog. The website and API default to collected records once any exist; a fresh database with only demo fixtures defaults to demo. Switch to **Demo catalog** for `nutela`, `Surf Excel`, or `National Ketchup 400g`. Select category, retailer, brand, or sorting and press **Apply**. Collected product details show real source links, schema availability, check time, and history. One source is labeled an observed price, with no winning-retailer badge. Demo links remain disabled. Real observations are stored in your ignored local database; a fresh checkout must collect its own observations.

`seed_demo` can be rerun: it refreshes demo observations without duplicating products/listings or creating a fictitious history trend. It never modifies live products. To initialize retailer records without sample products, use `python manage.py seed_retailers`.

## Implemented

- Responsive homepage, category navigation, search, comparison cards, detail tables, source transparency, and empty/error states.
- Local database search with case-insensitive partial and fuzzy matches; compatible size filtering; category/retailer/brand filters; price sorting; pagination.
- Separate canonical products, categories, retailers, listings, observations, and scrape audit runs, with migrations and database constraints.
- Normalized metric quantities, brand aliases, pack counts, variant and packaging guards, GTIN checks, RapidFuzz ranking, and conservative canonical linking.
- Atomic listing upserts with a history observation for every check, even if the price is unchanged.
- Read-only REST API, administration interface, SQLite default, and environment-based PostgreSQL configuration.
- Collection framework: bounded requests, contact-identifying user agent, fail-closed robots checks, crawl delays, no redirects/retries/access bypass, parser errors, manual management command, and audit trail.
- A manual Jalal Sons public-HTML adapter, with three actual imported observations. Naheed's source-format parser is retained offline because its collector request returned 403. Springs and Al-Fatah remain disabled.
- Synthetic and minimal factual-extract fixture tests, with provenance. Source descriptions, images, session data, and unrelated configuration are not imported.

## API

| Endpoint | Result |
| --- | --- |
| `GET /api/products/` | Paginated comparisons, collected source when present, otherwise demo |
| `GET /api/products/<slug>/` | Product and ascending-price listings |
| `GET /api/categories/` | Grocery categories |
| `GET /api/retailers/` | Retailers, availability status, and access notes |
| `GET /api/listings/<id>/history/` | Paginated newest-first price observations |

Product list parameters: `q`, `category` (slug), `retailer` (slug), `brand`, `source=demo|live`, `sort=relevance|price_asc|price_desc`, `page`, and `page_size` (up to 48).

```text
/api/products/?q=Olpers%20Milk%201L&source=demo
/api/products/?category=pantry&sort=price_asc
/api/products/?source=live
```

Demo/live flags are explicit in serialized results. Amounts are decimal strings, denominated in PKR. `best_price` excludes stale, out-of-stock, and unknown-availability offers. `has_comparison` requires multiple retailers with one known comparable area. A single retailer or unverified areas suppress winning-retailer flags; `has_mixed_areas` warns that the numerical minimum is not a direct comparison. APIs do not accept anonymous writes. Anonymous API traffic is limited to 120 requests/minute per application cache/IP; use shared caching and correctly configured proxies for a multi-process production deployment.

## Checks

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

Tests cover matching, search/filters, source separation and selection, price ranking, stale/unavailable observations, area and single-source safeguards, idempotent seeding, API behavior, ingestion/history, observed source formats, heading checks, robots wildcard precedence, timeouts, manual upserts, partial runs, and unavailable sources. They make no retailer network calls. See [fixture provenance](catalog/tests/fixtures/README.md). Bootstrap is vendored locally with its source map and MIT license.

## Collection and manual setup

Jalal Sons has a limited manual adapter. No scheduler, Celery, or cron job is activated. The current workspace has manual collection configured for Jalal Sons only. A fresh checkout defaults to collection disabled.

```powershell
.\.venv\Scripts\python.exe manage.py seed_retailers
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --url 'https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398'
```

The command reads robots, then the explicit product page, and records a fresh observation. It stops without automatic retry on denial, redirect, timeout, unsupported format, or challenge. Three listings have been imported locally; an intermediate connection timeout was followed by a successful later manual invocation. The source needs more reliability validation before scheduling. Naheed, Springs, and Al-Fatah remain blocked even if their configuration flags are changed.

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

## PostgreSQL and deployment

Install PostgreSQL and create a database/user through your normal local administration workflow. Set an appropriately escaped URL in `.env`:

```dotenv
DATABASE_URL=postgresql://daamradar:YOUR_PASSWORD@localhost:5432/daamradar
```

Then run `manage.py migrate` against that configured database. SQLite data is not automatically transferred. To seed PostgreSQL for development, run `seed_demo` again. PostgreSQL configuration is provided; runtime testing in this workspace uses SQLite.

For deployment, generate a unique `DJANGO_SECRET_KEY` (for example, Python's `secrets.token_urlsafe(50)`), set `DJANGO_DEBUG=false`, explicit `DJANGO_ALLOWED_HOSTS`, appropriate HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_SECURE_SSL_REDIRECT=true`, and `DJANGO_SECURE_COOKIES=true`. Run `collectstatic --noinput` and `check --deploy`. Use an appropriate production WSGI/ASGI server with `config.wsgi:application` or `config.asgi:application` and HTTPS; Django's development server is for local use. Proxy SSL settings, HSTS, logging, backups, and shared caching depend on the hosting environment and must be configured there. No hosted deployment has been configured.

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

## Next implementation phase

The foundation and first factual-price import are functional. Next, improve Jalal Sons request reliability and validate more exact product pages, verify location-specific semantics through a supported route, and establish another reliable source to compare the same SKU. Naheed needs its denied collector access resolved; its identity must not be changed to evade the denial. Broader reuse arrangements and a safe frequency must be established before publishing a large dataset or scheduling collection.

Current limits: three real listings from one retailer; intermittent connection timeout observed; delivery area unverified; no real cross-retailer comparison yet; no scheduler, trend chart, checkout/delivery, or location selector. Search scores at most 1,000 candidates; replace this bounded small-catalog approach as data grows. Matching needs broader brand/variant coverage and review tools. Browser layout/JavaScript and PostgreSQL need separate runtime validation.
