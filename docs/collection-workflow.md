# Manual collection workflow

This workflow searches no external sites on behalf of visitors and activates no scheduler. Jalal Sons is the only currently enabled collector. Use PowerShell from the project directory.

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

Global `SCRAPING_ENABLED`, the source's `collection_enabled` flag, and its `enabled` status must permit real collection. The workspace already has these configured for Jalal Sons. New checkouts default to disabled; see the README for setup. A run accepts at most ten distinct product URLs, and all selected URLs are validated before any request.

## Refresh existing observations

```powershell
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --refresh-existing --stale-only --report-dir reports
```

This selects existing non-demo URLs whose observations are older than `PRICE_STALE_HOURS` (48 by default), oldest first. Omit `--stale-only` to deliberately recheck all existing non-demo URLs. If nothing needs checking, the command performs no HTTP requests, creates no run, and adds no history. A successful recheck updates the existing listing and appends one historical observation, even if the price has not changed. An unsuccessful check never refreshes its timestamp or overwrites its previous price.

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
