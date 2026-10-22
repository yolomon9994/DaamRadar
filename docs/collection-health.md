# Admin collection health

Sign in to Django admin and choose **Collection health** in the header or on the retailer list. The direct route is `/admin/catalog/retailer/collection-health/`. Existing admin credentials apply; no new account, permission type, or database migration is introduced.

## What the page shows

- Per-retailer collected, fresh and stale listing counts, plus the latest listing check.
- The last completed successful run and the latest attempted run. A successful run covers only its own selected URLs, not the retailer's entire catalog. Partial runs can still update some listing checks without replacing the last fully successful run.
- Manual collection switches and adapter state. The global switch, source switch, validated source status and code-level adapter flag must all allow collection. A run marked `running` is shown separately and prevents another collection. This configuration view does not verify current robots rules, contact configuration, network access or retailer availability.
- Stale listings ordered oldest first, 25 per page, with links to the listing editor and public product page. Multiple listings for one product remain separate. The queue cannot identify never-imported products; first imports still use reviewed batches or URLs.
- The latest 20 failed, blocked or partial runs, including stored-observation counts, request counts and escaped error details. Links open the original run records and per-URL results. Historical failures remain after later successes. Older runs may lack structured counts or codes.

The retailer filter applies consistently to source totals, the stale queue and recent issues. Pagination keeps that filter. Invalid retailer choices produce a clear form error rather than silently showing unrelated sources. Empty databases and sources with no observations/runs have explicit empty states.

## Freshness and access

One timestamp is captured for each page request. The cutoff is `snapshot time - PRICE_STALE_HOURS`, currently 48 hours by default. A listing checked before the cutoff is stale; a listing exactly at the cutoff is fresh. The page displays the snapshot, cutoff and check times in Pakistan time. Availability is shown separately: fresh does not imply in stock or a comparable delivery area.

Both the listing and its product must have `is_demo=False`. Demo records and mismatched source flags are excluded from the counts and stale queue. The collected-listings admin link uses the same two flags; the listing admin now exposes a product-catalog filter alongside its listing demo flag.

The standard admin authentication gate requires active staff. The page additionally requires view or change permission for **all four** models: retailer, retailer listing, product and scrape run. Superusers qualify normally. Read-only staff with those view permissions can use the dashboard. The header link follows the same permission combinations. Existing admin model pages retain their own permissions.

This is a read-only GET/HEAD view with admin cache protection. POST is rejected. Opening/filtering/paginating the page does not fetch retailers, start jobs, change collection switches, refresh price timestamps, append history or clear running runs. An old running run requires the existing operator inspection procedure; age alone never declares it stopped. No scheduler or browser-triggered collection action is added.

## Implementation and validation

`catalog/services/collection_health.py` obtains retailer summaries and bounded issue records in two queries, using filtered aggregates and correlated run subqueries. The stale queue uses a separate paginated queryset with related products/retailers loaded. It avoids one query per source or listing. `RetailerAdmin` registers the protected custom route; dedicated admin templates and `static/css/admin-health.css` use Django's theme colors and horizontal table scrolling on small screens. The dashboard needs no custom JavaScript or new dependency.

All 108 automated tests passed, including 17 dashboard tests for demo isolation, exact/configurable freshness cutoffs, successful versus partial/failed runs, running-run preservation, adapter/global/source gates, permissions, filter validation, pagination, bounded results/queries, read-only behavior, escaping, empty data and working drill-down links. Django configuration/migration checks, static collection and Git whitespace checks passed.

Local stored-data validation found five source records, eleven collected listings, no running jobs, and the original Cartpk partial run. At the 22 October 2026 snapshot all eleven listings were stale; loading the page did not refresh them. The preview compared prices, history, runs, retailer flags and account counts before/after and found no changes. It used an unsaved preview user rather than creating an account or bypassing normal web authentication.

Headless Chrome checked rendered local snapshots at 1440px and 390px widths, including filter keyboard focus, counters, contained mobile table scrolling and expandable error details. Screenshots and preview artifacts are local ignored files under `reports/`. Authentication, filtering, pagination and linked admin pages were exercised through Django request tests. PostgreSQL runtime was not tested in this phase.

On 23 October 2026, real stale-only refreshes completed as runs #10 (Jalal Sons, six listings) and #11 (Cartpk, five listings). The dashboard correctly moved from eleven stale listings to eleven fresh listings, displayed those new successful runs, and retained the earlier partial issue. Viewing it added no observations. See the [refresh audit](collection-workflow.md#end-to-end-stale-refresh-23-october-2026) for dated prices, request counts and before/after verification.
