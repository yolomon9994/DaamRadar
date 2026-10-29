# Import reviewed batches through the admin website

## Use locally

Apply migrations after pulling, start the website, and sign in to Django admin with your own account:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Open **Collection health**, then **Import reviewed catalog — preview batches**. The direct preview route is `/admin/catalog/retailer/collection-import/`. Select a saved Jalal Sons or Cartpk batch, such as milk or pantry, and choose **Preview batch**. The preview displays reviewed product names/URLs, the saved review date, and counts for **Missing — will import** and **Existing — will skip**. Legacy batches without a pair-registry title retain their exact source URL and a generic reviewed-product label.

Preview is read-only: it does not fetch retailer pages, seed sources, create products/jobs, change switches or refresh observations. It works with a demo-only database and shows setup errors when collection is not configured. Retailer records must exist, their validated status/collection switches and adapters must allow collection, and `SCRAPING_ENABLED`/`SCRAPER_CONTACT` must be configured explicitly. See the [collection runbook](collection-workflow.md). These requirements are not enabled automatically.

The [29 October expansion](expanded-catalog.md) adds six source/category batches for dairy, pantry, drinks and household products. The same preview, permissions and missing-only behavior apply; single-source entries do not imply matching retailer coverage.

When setup is ready, choose **Import N missing listings** to start a finite local worker. The existing progress page shows the import batch, source audit link, completed URL counts, stored observations and errors. It polls stored state, with a manual refresh fallback; closing the page does not cancel or duplicate collection. Imports use the same file-based SQLite/PostgreSQL requirement, worker setup and [confirmed-stop recovery procedure](admin-refresh.md#recover-an-interrupted-worker) as manual price refresh.

## Permissions and preview scope

Normal active/staff admin login and CSRF protection apply. Viewing previews requires the four model view/change permissions used by collection health. Starting imports additionally requires **Can import reviewed catalog batches** (`catalog.import_reviewed_catalog`). Superusers qualify automatically. The price-refresh permission alone does not authorize creating listings; imported-batch operators do not implicitly receive refresh permission either.

The start action requires a signed preview bound to the account, batch and exact missing URLs, valid for fifteen minutes. An expired, changed, tampered or other-account preview is refused. If the set of missing listings changes before starting, preview again. The worker stores the approved URL set and never expands it to URLs that become missing after that preview. The user submits a batch key and signed preview, not arbitrary URLs or source configuration.

Import and refresh share the same database-backed active-request reservation, so they cannot overlap as separate admin jobs. Existing per-retailer `ScrapeRun` protection also applies to CLI collection. Only supported, saved reviewed batches are selectable, with up to ten distinct product URLs per batch. The source's normal robots rules, identity, delay, factual parsing, timeout-only retry and access-denial handling remain in place.

## Missing-only behavior

An existing non-demo retailer listing is identified by its URL **or** stable retailer product ID. Its freshness, stock and delivery-area label do not make it missing. Existing records linked to an inconsistent catalog flag are also preserved for operator review. Demo listings do not block real imports. Matching a product in another retailer's catalog does not count as having this source's listing: the normal conservative matching process can link a new source listing to the existing non-demo canonical product.

The worker recalculates missing targets at execution, checks before each fetch, and uses create-only ingestion before saving. Existing prices, check timestamps, availability, area evidence and history remain untouched. A record arriving during collection is marked `skipped_existing`, without adding a second observation; a unique-key race also rolls back any newly proposed canonical product. Successful new listings receive their normal history observation and source/category metadata.

If every approved target already exists when the worker starts, it skips the batch without constructing an HTTP client, creating a `ScrapeRun`, or adding history. The explicit admin request remains recorded. A partial failure keeps completed imports; previewing the batch again offers only the remaining missing listings. Existing stale listings must be updated separately with **Manual price refresh**. Imports do not discover URLs, overwrite existing observations or bypass source restrictions.

The optional CLI equivalent is:

```powershell
# Preview only, with no retailer requests or database writes:
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-milk-comparison --missing-only --dry-run
```

Removing `--dry-run` explicitly collects missing listings if the existing source gates permit it. `--missing-only` requires a saved batch; the original refresh and ordinary batch command behaviors remain available.

## Migration and verification, 29 October 2026

Migration `0005` adds request kind, batch and approved targets to `AdminPriceRefresh`, the import permission, and a kind/batch consistency constraint. Earlier requests remain price refreshes, and the shared active-job constraint remains in force.

All **214 tests passed on SQLite and PostgreSQL 17.11** under Windows/Python 3.13. Sixteen new tests cover read-only preview, missing detection, configuration, permissions/CSRF, signed-preview expiry/scope, shared overlap protection, preserved prices/history/evidence, execution-time rechecks, partial retries, malformed batches/targets and create-only race handling. Fresh migrations, static collection, production HTTP smoke and PostgreSQL dump/restore also passed; temporary servers were stopped.

Fourteen Chrome checks exercised an authenticated demo-only checkout, preview layouts at 1440px/390px, actual separate-worker imports for both milk batches, progress polling, duplicate rejection, public catalog visibility and refusal to reimport completed batches. Saved fixtures replaced collection transport, with real retailer HTTP requests blocked. Two import jobs produced five shared canonical products, ten live-flag QA listings and ten observations, separate from the fictional demo catalog. QA accounts, sessions and databases were temporary.

Before applying the migration to the development SQLite database, an integrity-checked backup was saved in ignored `backups/`. Every prior row/column and existing catalog/account count was preserved, and `.env` was unchanged. No real retailer collection was performed for validation.
