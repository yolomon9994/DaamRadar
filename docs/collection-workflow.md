# Manual collection workflow

Initial batch collection is also available through [reviewed catalog import in admin](admin-catalog-import.md), with a read-only missing-listing preview and create-only imports. The terminal commands below remain available. Refreshing existing observations is a separate action in the [admin refresh flow](admin-refresh.md).

This workflow searches no external sites on behalf of visitors and activates no scheduler. Jalal Sons and Cartpk are enabled locally; Cartpk is restricted to twelve reviewed product URLs. The [29 October expansion](expanded-catalog.md) adds 22 products across four categories, alongside the earlier [pantry](pantry-catalog.md) and [milk](milk-catalog.md) batches. Use PowerShell from the project directory.

## Refresh both reviewed sources

```powershell
.\.venv\Scripts\python.exe manage.py refresh_prices --dry-run
.\.venv\Scripts\python.exe manage.py refresh_prices --report-dir reports
```

This refreshes stale existing listings from Jalal Sons and then Cartpk, preserving the original collector rules and individual run reports. Fresh/empty selections do no work. Expected retailer failures are summarized while the other source is still attempted; the overall command exits nonzero on errors. Ctrl+C stops before the next source. No scheduler or first-time imports are added. See the [combined-command guide](refresh-prices.md) for outcomes, setup and failure handling. Preview and report output are separate invocations; do not combine `--dry-run` with `--report-dir`.

## After pulling these changes

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

Migration `0002` adds structured collection outcomes, request counts, error codes, and a database constraint preventing two running collections for the same retailer. It preserves existing listings and history. Historical runs retain their existing error text; their newly added statistics default to empty/zero rather than invented counts.

## Preview a reviewed batch

```powershell
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-basics --dry-run
```

The tracked batch in `catalog/scraping/batches.py` contains the three previously reviewed product URLs. A dry run validates the URL origin and path and lists targets without making HTTP requests or creating database records. It does not validate current robots or product contents; actual collection checks those. Dry runs work with the environment collection switch disabled, but unavailable adapters remain unavailable.

## Collect the batch

```powershell
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-basics --report-dir reports
```

Global `SCRAPING_ENABLED`, the source's `collection_enabled` flag, and its `enabled` status must permit collection. The workspace has these configured for Jalal Sons and Cartpk. New checkouts default to disabled; see the README for setup. A run accepts at most ten distinct URLs, all validated before any request. Cartpk allows only the twelve exact paths in the reviewed registry, each tied to its expected identity.

For the first Cartpk import on a fresh configured checkout:

```powershell
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-milk-1l --dry-run
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-milk-1l --report-dir reports
```

For later refreshes, use `scrape cartpk --refresh-existing --stale-only --report-dir reports`. The first real import was run #6 on 20 October: one PKR 360 observation in two requests (robots and product). The matcher linked it to Jalal Sons' existing 1L product without creating a duplicate canonical product. Unverified delivery areas suppress winning-retailer and savings labels, even though the listed prices are shown side by side.

To add all five reviewed pairs, including missing listings:

```powershell
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-milk-comparison --dry-run
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-milk-comparison --dry-run
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-milk-comparison --report-dir reports
.\.venv\Scripts\python.exe manage.py scrape cartpk --batch cartpk-milk-comparison --report-dir reports
```

Both five-URL batches use the same ordered product pairs. They preserve the old batches and do not trigger discovery requests. The source adapters reject a changed identity at any reviewed URL. `Milk Pak`/`Milkpak` and the observed missing whitespace in `Full Cream1Ltr` normalize consistently without relaxing size, pack, variant or packaging guards.

## Refresh existing observations

For first-time non-dairy imports, use `--batch jalal-sons-pantry-comparison` or `--batch cartpk-pantry-comparison` with the corresponding source. Each contains the three reviewed oil/spice URLs. See the [pantry catalog](pantry-catalog.md) for previews, import commands, dated prices and runs #12/#13. `refresh_prices` automatically includes these saved URLs on later stale refreshes, subject to the unchanged ten-URL cap.

```powershell
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --refresh-existing --stale-only --report-dir reports
```

This selects existing non-demo URLs whose observations are older than `PRICE_STALE_HOURS` (48 by default), oldest first. Omit `--stale-only` to deliberately recheck all existing non-demo URLs. If nothing needs checking, the command performs no HTTP requests, creates no run, and adds no history. A successful recheck updates the existing listing and appends one historical observation, even if the price has not changed. An unsuccessful check never refreshes its timestamp or overwrites its previous price.

For more than ten distinct existing URLs, each refresh selects the oldest ten and prints a notice. Review the result, then explicitly invoke another stale refresh for the remaining due URLs. The admin action uses the same bound. No extra runs are started automatically; explicit URL/import batches still reject more than ten targets. See the [expanded catalog](expanded-catalog.md#refreshing-the-larger-catalog).

Alternatively, pass one or more explicit `--url 'https://...'` arguments. Choose exactly one targeting mode: `--url`, `--batch`, or `--refresh-existing`.

## Network behavior

- Requests keep the same configured `DaamRadarBot` identity and source origin.
- Each run checks robots before requesting product pages. A missing or unvalidated robots response stops collection.
- At least five seconds separate requests, with stricter robots limits honored.
- `requests.Timeout` exceptions receive at most **one** extra GET attempt, after a delay following the timeout. HTTP errors, redirects, robots denials, access challenges, connection errors, and certificate failures do not retry. No proxies, identity changes, or CAPTCHA solving are used.
- Both timeout attempts failing stops the run. Remaining URLs stay pending, and completed observations are preserved.

Optional `.env` settings (these defaults apply even if an older `.env` lacks them):

```dotenv
SCRAPER_CONNECT_TIMEOUT=10
SCRAPER_READ_TIMEOUT=20
SCRAPER_TIMEOUT_RETRIES=1
SCRAPER_RETRY_DELAY_SECONDS=10
```

`SCRAPER_TIMEOUT_RETRIES` is clamped to 0 or 1; set it to 0 to disable recovery. Retry delay is bounded to 5–30 seconds. Connect/read timeouts are bounded to 1–30 seconds. These measures handle limited transient failures; they cannot guarantee retailer availability or establish permitted reuse.

## Review results

Open **Collection health** from the Django admin header for per-source fresh/stale counts, latest check/successful run, running/paused state, recent issues and the paginated stale queue. The retailer filter applies across these sections. The [dashboard guide](collection-health.md) explains access and definitions. This view reads stored data; it does not start a refresh or clear a running job.

The command prints its run ID and report path. Reports are named `reports/scrape-<run-id>.json`, contain only operational metadata and public product facts, and are excluded from Git. An existing report is never overwritten. JSON export failure does not discard a completed database run; the command reports that the database result remains available.

Each report contains run status, start/completion times, actual HTTP request count including robots and timeout recovery, stored observation count, error code/message, and one outcome per selected URL:

- `stored`: listing ID, observed price, and check time.
- `failed`: collection error, including HTTP status when available.
- `pending`: not completed, usually because an earlier URL or preflight check stopped the run.

Use Django admin's **Scrape runs** view to inspect these same fields. A single failed run is `failed` for transport/parser failures or `blocked` for access/configuration problems; a run with observations stored before failure is `partial`. Errors return a nonzero command exit code. Successful observations are committed individually; the entire batch is not rolled back after a later failure.

Run `--refresh-existing --stale-only` again after a recoverable failure to skip already refreshed records. For a failed first-time import that never created listings, use its explicit pending/failed URLs from the report. Do not repeatedly invoke a denied source or change its identity to bypass a refusal.

## Interrupted runs

Ctrl+C marks the current run failed/partial and preserves completed observations. A hard process kill or machine crash can leave a run marked `running`. A second run for that source is refused by a database constraint. Inspect the previous process and recorded outcomes first. Once you know it has stopped, change that run's status to `Failed` in admin before invoking the command again. The command never automatically declares an old run dead.

## Validation on 20 October 2026

The actual Jalal Sons stale-only refresh was **run #5**: three existing listings refreshed using four HTTP requests (robots plus three product pages). Prices remained PKR 350, 518, and 44. Each listing gained one real observation, for two observations per listing, and no duplicate products or listings were created. All three became fresh under the 48-hour rule. `reports/scrape-5.json` is a local artifact, not a bundled fixture. A new checkout starts without these ignored local observations/reports.

The automated suite covers timeout recovery and exhaustion, post-timeout delay, immediate stopping on access errors, parser failure without stale-data mutation, targeting and dry runs, partial outcomes, JSON export, and overlap rejection. These tests use mocks and saved fixtures, not retailer requests. A single successful live refresh does not demonstrate sustained production reliability.

The five-product expansion used run #7 (Jalal Sons: five stored, six requests), run #8 (Cartpk: three stored, five requests, partial after a connection failure), and run #9 (Cartpk's two unfinished URLs: two stored, three requests). All five pairs now share canonical products across the two sources; the earlier single-source Everyday listing remains. See the [catalog validation](milk-catalog.md#live-validation) for check times, counts and limitations. Run #8 remains partial as an accurate audit record; recovery does not rewrite its status or add automatic connection-error retries.

## End-to-end stale refresh, 23 October 2026

The preview identified six stale Jalal Sons listings and five stale Cartpk listings, with no running jobs. Both configured collectors then completed `--refresh-existing --stale-only --report-dir reports` successfully, rechecking robots with the existing named identity and respecting crawl delays.

| Run | Retailer | Stored observations | HTTP requests | Result | Product check times (PKT) |
| --- | --- | --- | --- | --- | --- |
| #10 | Jalal Sons | 6 | 7 | Success | 23 Oct 2026, 00:11:04–00:11:29 |
| #11 | Cartpk | 5 | 6 | Success | 23 Oct 2026, 00:11:21–00:11:42 |

All eleven listed prices and in-stock labels were unchanged. Jalal Sons: Everyday 180ml 44, Olper's 1L 350, Olper's 1.5L 518, Milkpak 250ml 94, Nurpur 1L 358, Haleeb 1L 334 PKR. Cartpk: Olper's 1L 360, Olper's 1.5L 570, Milkpak 250ml 105, Nurpur 1L 620, Haleeb 1L 405 PKR. These are dated public catalog observations; delivery areas remain unverified.

The dashboard moved from **0 fresh / 11 stale** to **11 fresh / 0 stale**, with no running jobs. Successful-run references became #10 and #11. The original partial run #8 remains in the historical issue list; it was not rewritten. Six live products and eleven live listings retained their original IDs and canonical relationships. Each refreshed listing received exactly one new historical observation, increasing real history from seventeen to twenty-eight. Existing history, demo data and source settings were unchanged.

A before/after audit compared stored records and JSON reports, including per-URL outcomes, request counts, prices and timestamps. Local request checks confirmed the admin dashboard, all six collected product pages, the product/history APIs and chart point/table counts reflect the stored observations. The stored-data admin preview used an unsaved user; authentication and permissions were checked in the dashboard tests. No winning-retailer labels were introduced for unverified areas.

An immediate second stale-only invocation for each source was checked with HTTP requests mocked to fail: both were genuine no-ops, making zero requests, creating zero runs and adding zero history. The 43 relevant collection-workflow, dashboard and chart tests passed. No application-code changes, dependency additions, schema migration or scheduler were needed for this operation.

Local audit artifacts are ignored by Git: `reports/scrape-10.json`, `reports/scrape-11.json`, `reports/refresh-before-20261022T191032.json` and `reports/refresh-validation-20261022T191032.json`. The audit filenames use UTC; 22 October 19:10 UTC falls on **23 October in Pakistan**. A new checkout does not include the local observations or reports.
