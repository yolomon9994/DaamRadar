# Manual price refresh in Django admin

## Start and follow a request

After pulling this feature, apply its migration:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Sign in to `/admin/` with your own account and open **Collection health** (`/admin/catalog/retailer/collection-health/`). Under **Manual price refresh**, choose Jalal Sons, Cartpk, or both, then select **Start manual refresh**. Both sources run sequentially, in that order. The diagnostics table's retailer filter does not change this explicit source selection.

The browser redirects to a saved progress page showing queued/running/completed/error state, exact audit-run links, finished URL counts, stored observations, request counts and per-URL outcomes. Counts update after completed URLs; robots checks, delays and timeouts may take time. While visible, the page polls stored progress every three seconds. Polling stops on completion/operator-attention state or after three request failures. **Refresh progress** is a read-only fallback, including without JavaScript. Closing/reloading the page neither starts another request nor cancels its worker.

The dashboard links the active request and ten recent admin requests across all sources. Double submissions and requests from another browser cannot start a second active admin worker. Expected source errors allow the other selected source to be attempted. Successfully stored observations survive partial failures. Fresh/empty sources show **Skipped — fresh or empty**, without HTTP requests, new `ScrapeRun` records or history; the explicit admin request itself is retained.

## Access and configuration

Normal active/staff admin login and CSRF protection apply. Viewing health/progress requires view or change permissions for all four existing models: retailer, retailer listing, product and scrape run. Starting additionally requires **Can manually refresh reviewed prices** (`catalog.run_price_refresh`). Superusers qualify automatically; grant this permission explicitly to other trusted operators who should collect data. Request records are not exposed through an editable model-admin screen.

The selected source switches/validated statuses and code-level adapters must already be enabled, with `SCRAPING_ENABLED=true` and a valid `SCRAPER_CONTACT`. See the [collection runbook](collection-workflow.md). No source is enabled automatically. Refresh only checks stale existing collected URLs in the saved reviewed catalog, up to ten distinct URLs per source. It refuses oversized sets, unsupported/unreviewed URLs, invalid configuration, or a selected source with an existing running CLI collection. Fresh demo-only checkouts can now use [reviewed catalog import in admin](admin-catalog-import.md) for their initial imports; refresh still updates existing listings only.

Catalog imports use the same worker, progress pages, active-job reservation and recovery procedure. Their separate `catalog.import_reviewed_catalog` permission and signed missing-URL previews prevent the refresh action from becoming an import action. Request kinds and batch scopes are retained explicitly; migration `0005` preserves earlier requests as price refreshes.

The exact allowlist includes all saved reviewed batches, including Everyday 180ml in the original `jalal-sons-basics` batch as well as the later milk/pantry pairs. This preserves the existing nine-Jalal/eight-Cartpk local catalog; it does not admit arbitrary URLs that merely match a retailer's path pattern.

The web process launches one finite local subprocess with the same Python interpreter, settings module, environment and project directory. Both processes need the same persistent SQLite file or PostgreSQL database; in-memory SQLite is refused. There is no Celery requirement, scheduler, catalog discovery, arbitrary-URL input or anonymous collection endpoint. Opening/filtering/polling diagnostics never collects prices; only an authorized CSRF-protected POST reserves work.

## Audit, progress and overlap protection

Migration `0004_adminpricerefresh` adds the request table and start permission. A database constraint permits only one queued/running admin request across processes. A worker atomically claims its queued request; invoking it twice cannot execute it again. The request retains its requesting account, timestamps, sources, exact owned run IDs, worker PID and sanitized failures. It delegates to the existing stale-only collectors; the existing `ScrapeRun` per-retailer overlap constraint also protects against CLI collisions. No transaction remains open during retailer delays/network access.

Existing robots rules, fixed identity, source origins, delays, timeout-only retry, factual parsing, history ingestion and delivery-area clearing remain in force. Successful unchanged prices still append observations. The worker rechecks configuration and reviewed-URL limits. Completed-URL results and request counts are published to the original run and admin request; links never guess the latest unrelated run. Web requests store results in the database, without exporting reports or automatically retrying an entire failed job. CLI commands and optional report exports remain available.

A process-launch failure finalizes the queued request as failed. A worker exiting before claiming also fails without collection. Claimed unfinished work stays locked for inspection, with no age-based automatic unlocking. Closing or restarting the web process does not intentionally stop an already launched finite worker.

## Recover an interrupted worker

For a request left queued/running, reload its page to read its worker PID and owned audit links. Inspect the process in your operating system and verify that its command is this project's `manage.py run_admin_refresh <request-id>`; a PID alone can be reused. If it is still working, let it finish or deliberately stop that specific worker, then verify it has stopped. Closing the browser does not stop it.

Only after independently confirming the worker has stopped:

```powershell
# Replace 12 with the admin request ID, not a ScrapeRun ID:
.\.venv\Scripts\python.exe manage.py recover_admin_refresh 12 --confirm-worker-stopped
```

Recovery finalizes only this request's owned running collections, marks the request stopped and releases its admin reservation. It adds/removes no observations, does not touch unrelated CLI runs, and refuses finalized requests. It does not terminate a process itself. Do not confirm while the worker is alive. Inspect results before starting another explicit refresh.

## Verification, 29 October 2026

All **198 tests passed on SQLite and PostgreSQL 17.11**, under Windows/Python 3.13. Seventeen new tests cover permissions, CSRF, POST-only actions, commit-before-launch behavior, duplicate reservations, database constraints, configuration rechecks, CLI overlap, reviewed URLs/limits, exact audit ownership/progress, no-op skips, failure continuation, process-launch failure, sanitized errors, retained locks and confirmed recovery. Fresh migrations, static collection, production HTTP smoke and PostgreSQL dump/restore passed; the disposable PostgreSQL server was stopped.

Ten authenticated Chrome checks exercised a real POST → separate subprocess → persistent progress/polling flow against disposable SQLite, including duplicate rejection, exact audit links, completion updates, counts, 1440px/390px layouts and a second refresh that skipped fresh records. Saved fixtures replaced the collector client, with real requests HTTP transport blocked in both web process and workers. Two jobs produced exactly two fixture collection runs and two new QA observations; the no-op job produced none. QA accounts/sessions were temporary.

Before applying the migration to the development database, an integrity-checked backup was saved under ignored `backups/`. Every preexisting row remained unchanged, without new collection/history records, changes to existing accounts or `.env` changes. Migrations add the new table and permission/content-type metadata; they do not refresh retailer prices. No real retailer requests were made for this milestone's validation.
