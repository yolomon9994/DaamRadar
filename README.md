# DaamRadar

A local-first Pakistani grocery discovery and listed-price comparison MVP, built with Python, Django 5.2 LTS, Django REST Framework, Django Templates, Bootstrap 5, and vanilla JavaScript.

**Data status:** no live prices have been collected. All 12 seeded products and 36 seeded listings are clearly labeled fictional demo data. Initial retailer integrations are unavailable. See [the source investigation](docs/retailer-review.md).

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

Try `Olpers Milk 1L`, `nutela`, `Surf Excel`, or `National Ketchup 400g`. Select category, retailer, brand, or price sorting and press **Apply**. Open a product for sorted listings, availability, timestamps, and sample history. The **Collected prices** tab has an intentional empty state. Demo links do not point at invented retailer product URLs.

`seed_demo` can be rerun: it refreshes demo observations without duplicating products/listings or creating a fictitious history trend. It never modifies live products. To initialize retailer records without sample products, use `python manage.py seed_retailers`.

## Implemented

- Responsive homepage, category navigation, search, comparison cards, detail tables, source transparency, and empty/error states.
- Local database search with case-insensitive partial and fuzzy matches; compatible size filtering; category/retailer/brand filters; price sorting; pagination.
- Separate canonical products, categories, retailers, listings, observations, and scrape audit runs, with migrations and database constraints.
- Normalized metric quantities, brand aliases, pack counts, variant and packaging guards, GTIN checks, RapidFuzz ranking, and conservative canonical linking.
- Atomic listing upserts with a history observation for every check, even if the price is unchanged.
- Read-only REST API, administration interface, SQLite default, and environment-based PostgreSQL configuration.
- Collection framework: bounded requests, contact-identifying user agent, fail-closed robots checks, crawl delays, no redirects/retries/access bypass, parser errors, manual management command, and audit trail.
- Synthetic saved-HTML fixture tests. The provisional Al-Fatah parser is **offline only**, not a validated live adapter.

## API

| Endpoint | Result |
| --- | --- |
| `GET /api/products/` | Paginated product comparisons, default demo source |
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

Demo/live flags are explicit in serialized results. Amounts are decimal strings, denominated in PKR. `best_price` excludes stale, out-of-stock, and unknown-availability offers. Different delivery areas suppress winning-retailer flags; `has_mixed_areas` warns that the lowest observed figure is not a direct comparison. APIs do not accept anonymous writes. Anonymous API traffic is limited to 120 requests/minute per application cache/IP; use shared caching and correctly configured proxies for a multi-process production deployment.

## Checks

```powershell
.\.venv\Scripts\python.exe manage.py test
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe manage.py collectstatic --noinput
```

Tests cover product identities and rejection cases, typo search and combined filters, source separation, price ranking, stale/unavailable observations, mixed delivery areas, idempotent demo seeding, API pagination and read-only behavior, escaped queries, atomic ingestion/history, synthetic HTML parsing, rate limiting, robots denials, source timeouts, and unavailable adapters. They make no retailer network calls. Bootstrap is vendored locally, including its source map and MIT license.

## Collection and manual setup

Do not enable collection until the source has been validated. No scheduler, Celery, or cron job is activated.

```powershell
.\.venv\Scripts\python.exe manage.py seed_retailers
.\.venv\Scripts\python.exe manage.py scrape alfatah --url 'https://alfatah.pk/products/REVIEWED-PRODUCT-HANDLE'
```

**The command above deliberately fails with an actionable source limitation today**, without contacting the retailer, and records a blocked `ScrapeRun`. Configuration alone cannot bypass an adapter's disabled state.

To enable a future source:

1. Obtain a permitted data-access route (written permission, licensed feed, or explicit applicable API terms), validate robots and product/variant/location behavior, and record dated evidence in `docs/retailer-review.md`.
2. Implement and test that retailer's `collect(client, url)` adapter using real, permitted saved fixtures. Set its code-level `enabled` flag only after that validation. The current JSON-LD parser accepts one unambiguous PKR offer and intentionally rejects ranges and multiple variants.
3. Set `SCRAPER_CONTACT` to your monitored address and `SCRAPING_ENABLED=true` in `.env`. Mark that retailer `Validated` and enable collection in Django admin. Use the approved frequency, at least the configured five-second delay and any stricter robots delay. The command accepts at most ten explicit URLs; it is not a catalog crawler.
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
catalog/tests/            Automated tests and synthetic saved HTML
templates/                Django templates
static/                   Custom styles, SVG illustrations, JS, Bootstrap
docs/                     Architecture and dated source investigation
```

`requirements.txt` declares supported ranges; `requirements.lock.txt` records the exact versions installed during this build.

## Next implementation phase

The foundation and sample comparison workflow are functional. **Phase 2 remains gated on an accessible, permitted source.** Secure one retailer feed/access agreement, validate actual product and location/variant semantics, add a production adapter with permitted fixtures, and collect a small reviewed batch. Only then expand live matching and choose scheduling frequency.

Current limits: no real retailer prices, no active live purchase links in seeded data, no scheduler, no price-trend chart, no checkout/delivery, and no location selector. Search scores at most 1,000 candidates; replace that bounded small-catalog approach with indexed retrieval as the dataset grows. Matching favors false negatives over incorrect merges and needs broader brand/variant coverage and manual review tools. Browser layout/JavaScript and PostgreSQL require separate environment validation.
