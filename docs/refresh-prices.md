# Refresh both reviewed retailers

For an authenticated browser action with persistent progress, use [Manual price refresh in Django admin](admin-refresh.md). The terminal command below remains available; the admin worker delegates to the same stale-only collectors with a stricter saved-reviewed-URL restriction.

Run from the project directory in PowerShell:

```powershell
# Preview stale existing URLs without requests or database writes:
.\.venv\Scripts\python.exe manage.py refresh_prices --dry-run

# Refresh stale existing listings and retain each retailer's JSON report:
.\.venv\Scripts\python.exe manage.py refresh_prices --report-dir reports
```

`--report-dir` is optional. Without it, each collection still has its normal database audit record. Do not combine it with `--dry-run`; that combination is rejected before any work. This command creates no scheduler and has no force-refresh option. Use the original single-source `scrape` commands when you deliberately need different targeting.

## Scope and collection behavior

The command visits **Jalal Sons, then Cartpk**, in that fixed order. Each source finishes and closes its client before the next starts. It delegates to the existing collector with `--refresh-existing --stale-only`: only existing collected listings with a collected product and a saved URL are considered, using the current `PRICE_STALE_HOURS` cutoff. It creates no source records, discovers no URLs and does not import missing products. On a fresh checkout, seed/configure the reviewed sources and perform their reviewed first-time batch imports first.

The original collection gates, exact-URL validation, ten-URL limit per source, robots checks, fixed identity, crawl delays, timeout recovery and run-overlap constraint remain in place. As of the [29 October catalog expansion](expanded-catalog.md), a larger existing target set selects the oldest ten distinct URLs and prints a notice; remaining due URLs require another explicit manual invocation. The wrapper does not enable a source, clear a running job, split the selection into extra runs, retry a failed retailer, rotate identities or bypass denials. Failed URLs retain their old timestamps and may remain at the front of the next selection; inspect failures first.

Fresh or empty target sets produce `no_work`, with no HTTP client, request, new audit run, report file or history entry. This describes the target selection, not source availability or configuration: the existing collector checks collection gates when there is work to do. A missing retailer record is an error; use `seed_retailers` rather than expecting this wrapper to configure it.

## Summary and errors

Every invocation prints one combined summary after the individual collector output. Each row includes the source, outcome, number of observations stored, HTTP request count, and this invocation's run ID/status and report path when present. Totals include successful observations from partial runs. Every successful check appends one real history observation, including unchanged prices.

| Outcome | Meaning |
| --- | --- |
| `success` | All selected URLs for that retailer were stored. |
| `partial` | Some observations were stored before collection stopped. |
| `failed` / `blocked` | The collector recorded a failed attempt or a configuration/access refusal. |
| `no_work` | No stale existing URLs were selected; no new run exists. |
| `dry_run` | URL preview only; no requests, writes or run records. |
| `error` | The attempt was rejected before creating a run, such as an existing active run or missing retailer. An unexpected programming/database exception also prints the available summary before propagating. |
| `report_error` | Collection succeeded in the database, but its requested report export failed. The successful run and observations are retained. |
| `interrupted` / `not_attempted` | The operator interrupted the active source; remaining sources did not start. |

An expected retailer error does not prevent the other reviewed source from being attempted. The command exits nonzero after printing the summary if either source has a problem, including report export. Successful observations and both sources' existing logs remain intact. Unexpected exceptions propagate after the available summary and do not start another source. Ctrl+C stops before the next retailer, preserves the finalized database run, attempts its optional report export, and exits with code 130.

Each report retains the existing filename `scrape-<run-id>.json`. There is no extra combined JSON report. Report files are never overwritten; export errors do not trigger another collection. A conflict with another running collector reports no new run for this wrapper, rather than attributing the other process's record to it. The wrapper obtains its exact run/report references from its own collector instances instead of guessing the latest database record. The original dashboard and history views need no changes.

## Verification

The full suite passed with **126 tests**, including 18 wrapper tests. Coverage includes source order/client closure, exact run/report ownership, partial/error continuation, no automatic access-denial retry, no-op and dry-run behavior, all collection switches, the URL cap, active-run preservation, report export failure, interruption, unexpected exceptions and empty/missing-source setup. Existing matching, ingestion, HTTP, admin and chart tests still pass. Django checks, migration checks and Git whitespace checks passed; no dependency or migration was added.

On 23 October 2026, the command was checked against the recently refreshed local catalog in both preview and normal report-enabled mode, with HTTP requests and client construction mocked to fail if unexpectedly used. Both sources correctly returned no work. All products, listings, history, source settings and existing run records were compared before/after and remained unchanged. The catalog retained six live products, eleven fresh listings and twenty-eight real history observations; no new audit runs or reports were created. Stale collection, failures and report writing were exercised with source-format fixtures in the tests; no unnecessary live recheck was performed for already-fresh data.
