# Public source health and freshness

Open **Our sources** in the website header, or visit `/sources/`. The page now combines the existing delivery/access information with a public, read-only view of stored collection health. No account is required to read it.

## What visitors see

- Distinct collected products with at least one collected listing, total retailer listings, and fresh/stale counts.
- For each source: collected/fresh/stale counts, its latest valid observation time, latest collection-attempt outcome and the last completed successful selection.
- Separate descriptions for no observations, recent checks, some/all stale observations, timestamp anomalies, paused collection, source review and unavailable collection.
- Source-filtered links back to collected products. Sources without observations still show their status and external website, without implying catalog coverage.
- The earlier dated delivery research and the explanation of why unverified delivery areas withhold winning-price claims.

Both the product and listing must have `is_demo=False`. Mismatched flags and all fictional demo data are excluded. The product count is distinct across retailers; one product listed twice counts as one product and two listings. Unlisted canonical products do not count as collected coverage.

## Time and outcome semantics

One aware timestamp is captured for the snapshot. Fresh observations have check times between `snapshot - PRICE_STALE_HOURS` and the snapshot, inclusive. Older times are stale. Future timestamps count as anomalies, excluded from both fresh and stale totals and from the latest-valid-observation timestamp. The configured freshness window is used throughout; it defaults to 48 hours.

The snapshot, cutoff, observation times and run times are displayed in PKT with machine-readable `<time datetime>` values. Counters explicitly say **at snapshot**. They are dated facts rather than continuously updated counters. **Reload snapshot** reads the local database again; there is no polling or automatic retailer collection. The complete overview also works without JavaScript.

Freshness measures check age. It does not establish current stock, matching delivery areas, a complete retailer catalog or final checkout cost. Failed or partial collection can coexist with recent observations. A successful selection covers only its selected URLs, and its completion time does not replace each listing's check time.

The latest attempted run is ordered by start time, then ID. The last completed successful run is selected separately by completion time, then ID; a success without a completion time does not qualify. Partial and failed runs do not erase earlier completed successes. An older record marked running is shown even if a newer attempt exists, with an explicit warning that stored state does not prove a worker is alive. Viewing the page never clears locks.

Collection configuration is described separately from observation freshness. The adapter, validated source status, global/source switches and a valid configured contact must permit manual collection before the page says **Manual collection configured**. This label does not establish current network/robots access. The contact itself is not displayed.

## Operator access

Active staff with view or change permission for all four collection-health models (retailer, listing, product and scrape run) see **Review collection health**, linking to the existing protected admin dashboard. Extra links follow the existing action permissions:

| Permission | Additional link |
| --- | --- |
| `catalog.run_price_refresh` | Review and refresh stale prices |
| `catalog.import_reviewed_catalog` | Import reviewed products |

Superusers qualify normally. Anonymous visitors, ordinary accounts and staff missing the model-permission floor see no management section. Links lead to existing admin review screens; starting collection still requires their authorized, CSRF-protected POST actions. The public page accepts GET/HEAD only and cannot start a worker.

Public summaries do not expose raw collection errors, error codes, per-URL results, worker IDs, account information or contact configuration. Those details remain available through authorized admin diagnostics. Source names and existing public access notes remain escaped. Responses use private/no-store cache controls so operator links and dated snapshots are not shared-cached.

## Implementation and validation, 29 October 2026

`catalog/services/source_health.py` computes the eager retailer summary and distinct product count in two queries, using filtered aggregates, scalar run subqueries and a running-record existence check. It does not load detailed run logs or perform a query per source. `/sources/` renders this summary and checks the existing operator permissions. No schema migration, dependency, API write route, scheduler or new JavaScript was added.

All **308 tests passed on SQLite and PostgreSQL 17.11** under Windows/Python 3.13. Sixteen new tests cover count isolation, duplicate retailer coverage, exact/configured cutoffs, future timestamps, PKT snapshot dates, completed/partial/failed/running states, configuration gates, private-field omission, granular permissions and admin links, safe methods, unchanged records, two-query bounds, source browsing, escaping, private caching and empty/demo-only installations.

**20 Chrome checks** passed at 1280px and 390px, including summary layouts, source states, observation/run distinctions, private-data omission, keyboard reload, source browsing, anonymous/read-only/operator views, existing admin navigation and operation without page JavaScript. Browser QA used an isolated in-memory database, temporary accounts and blocked retailer HTTP. Screenshots are ignored local artifacts under `reports/source-health-1280.png` and `reports/source-health-390.png`.

PostgreSQL fresh migrations, static collection, production HTTP checks and full-row dump/restore passed, with temporary servers stopped. SQLite production HTTP checks also cover the public snapshot, demo exclusion, no-store responses and refusal of collection POSTs.

Read-only validation of the development catalog at **23:47:54 PKT on 29 October** confirmed **31 collected products, 40 listings, 23 fresh, 17 stale and zero future timestamps**. Jalal Sons had 19 fresh/nine stale listings; Cartpk had four fresh/eight stale. These counts age naturally. SHA-256 comparisons confirmed the development database and `.env` were unchanged. No prices were refreshed or retailers contacted during this milestone. The local audit is `reports/public-source-health-validation.json` and is not shipped in Git.
