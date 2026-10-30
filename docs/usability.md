# Usability, snapshot expiry and performance

## Observation snapshots

Comparison pages, source freshness, basket estimates/budgets/printing and watch targets now use the same finite lifetime rule. A snapshot is valid for **at most five minutes**, or until the earliest relevant observation reaches the configured freshness cutoff or a future check time becomes current. The default observation window remains 48 hours, including its exact cutoff. A five-minute display lifetime does not make the underlying observation newer or guarantee retailer stock, delivery coverage or checkout costs.

The basket service now explicitly excludes future-dated checks, alongside stale/unknown/out-of-stock observations. Such a line has `status: "check_time_invalid"`, no eligible price or line total, and cannot support a complete budget assessment. The last observed timestamp remains available for review. This fixes a previous difference between basket eligibility and the catalog/watch/pack views.

Browser expiry hides current comparison prices/highlights, source freshness cards/counts, basket totals, budget assessments and target alerts. Product names and list-add controls remain available. Basket print snapshots are cleared; printing an expired estimate shows an explanation instead of old prices. Saved products, pack quantities, budgets, targets, histories and catalog records are kept. Use **Reload snapshot**, **Refresh estimates** or **Check targets** to explicitly reload local eligibility. Expiry never polls, fetches retailer pages or starts collection. Recorded historical charts remain historical records, rather than current eligibility claims.

The shared guard checks both absolute expiry and elapsed monotonic time. Request/navigation time counts conservatively against the lifetime, so slow responses do not receive a new full lifetime on arrival. Backward wall-clock changes cannot extend it. Focus, visibility and page-history events check the deadline even when timers were suspended or throttled. Leaving a page invalidates active claims before a browser can cache its DOM. Persisted page-return handlers reload changed saved lists/targets, preserve page-only data when storage is blocked, and retain an unchanged unsaved budget draft. Browser cache behavior varies; the lifecycle handlers are tested using persisted page events.

Server-rendered pages include an as-of time, expiry deadline and manual reload link. Without JavaScript, comparisons remain readable as dated snapshots, and a visible notice asks the reader to reload before use; automatic hiding is unavailable. Printing/PDFs retain dated-observation and delivery caveats. An already saved PDF is a static document and cannot expire or update itself.

The product API adds a nested `snapshot` object with `as_of`, `expires_at` and `max_age_seconds` (300). The pack API uses the same nested object. Basket/target responses expose those fields at the top level, retaining their existing `estimated_at`/`evaluated_at` aliases. Unavailable and empty results also have a finite deadline. Public comparison HTML and product API responses use no-store caching. Source freshness computes its earliest transition inside the existing two queries. Admin quality/history reports are dated review artifacts, not current price snapshots, and are outside automatic expiry.

## Accessibility and control behavior

- Skip navigation moves focus to the main landmark. The wide retailer comparison table is a named keyboard-focusable scrolling region, also without JavaScript. Existing pack/history/import tables retain their scrolling behavior.
- Important price/offer/filter labels have a 12 px minimum in the revised selectors. Action buttons have a 44 px minimum height. Muted text uses a darker token; the tested muted-on-cream pair exceeds 4.5:1 contrast. This is a checked color pair, not a claim that every rendered combination was audited.
- Snapshot expiry moves focus to Reload if the focused comparison region is being hidden. Saved-list feedback has an explicit named Dismiss control instead of permanently obscuring lower controls.
- Main search restores each submit button's original label after page-history returns. Shopping and print observation times use PKT, matching other comparison dates.
- Public home/planning controls were checked at 1280, 390 and 320 CSS px. Existing watchlist/search/print checks retain their other viewport coverage. The Chrome accessibility tree exposes named main/search/action controls, and keyboard search, skip navigation and table access were exercised.

These are concrete accessibility and usability checks, not a formal WCAG conformance certificate or a substitute for testing with screen readers and other browsers.

## Reproduce local performance measurements

Run from the project root with the normal project dependencies installed:

```powershell
.\.venv\Scripts\python.exe scripts/measure_performance.py
# Optionally save to a new filename; existing files are never replaced:
.\.venv\Scripts\python.exe scripts/measure_performance.py --samples 7 --output reports/performance-local.json
```

The script always forces `config.ci` and in-memory SQLite before initializing Django, even if development/CI database URLs are set. It migrates/seeds only that disposable database and blocks requests HTTP. It creates 300 synthetic collected products, 900 listings and 1,800 history rows, alongside the separate 12-product/36-listing Demo catalog. These fixtures are not actual retailer data and the synthetic history is not an analytical dataset.

Each route gets one unmeasured warm-up and seven sequential measured Django Client requests. Timings include rendering/serialization and query capture. They exclude browser work, static assets, network and Waitress/proxy overhead. The following observations are from one Windows/Python 3.13 machine on 30 October 2026, not load-test or production latency promises:

| Route / case | Before median (ms) | After median (ms) | Before → after queries |
| --- | ---: | ---: | --- |
| Home, 300-product candidate set | 128.56 | 133.22 | 7 → 7 |
| Filtered search | 132.52 | 137.89 | 8 → 8 |
| Six local suggestions | 106.66 | 25.09 | 3 → 2 |
| Product detail with history | 16.93 | 17.16 | 5 → 4 |
| Pack comparison | 105.72 | 103.43 | 3 → 3 |
| Public source freshness | 12.16 | 12.92 | 2 → 2 |
| 50-product basket | 20.23 | 20.03 | 3 → 3 |
| 50 target checks | 15.90 | 15.44 | 2 → 2 |

Suggestions now reuse identity/offer-filter matching without fetching/decorating all retailer offers that their response never displays. Detail prefetch joins retailers in the listing query, removing an extra query. Existing bounds on candidates, history, pack comparisons and quality scans remain. Timing noise and additional expiry metadata account for small changes elsewhere; no blanket speedup is claimed. The final filtered-search maximum was 260.979 ms, illustrating why the median alone is not a latency guarantee. Raw per-request samples and response byte counts are in the optional JSON output; local before/final artifacts remain ignored under `reports/`.

## Validation, 30 October 2026

All **384 offline tests passed on SQLite and PostgreSQL 17.11**. Ten new snapshot/performance regression tests cover maximum lifetime, exact cutoff/future transitions, basket totals/budgets, non-minimum offer transitions, source query bounds, API/HTML metadata and cache policy, lightweight guarded suggestions, detail query count and keyboard markup. Existing watch expiry assertions now use the capped shared contract.

**32 new Chrome checks** cover expiry on home/detail/pack/sources/basket/watch views, print/budget invalidation, saved-data preservation, no automatic fetch on expiry, explicit refresh, backward clocks, suspended timers, persisted history events, changed saved lists, budget drafts, blocked-storage targets, keyboard/focus behavior, accessible control names, contrast, readable targets/labels, narrow reflow and no-JavaScript caveats. The existing **24 watchlist**, **21 print/PDF** and **23 search** checks also passed: **100 Chrome checks** for this milestone. Actual PDFs retained the one-page two-item and five-page 50-item checklist layouts. Browser helpers used disposable data, blocked retailer HTTP and verified the development database and `.env` were unchanged.

SQLite and PostgreSQL production smoke checks passed through Waitress/WhiteNoise, including the new hashed snapshot JavaScript. PostgreSQL fresh migrations, static collection, migration-drift checks and full-row dump/restore passed; temporary servers stopped. The committed performance command ran successfully using its disposable fixtures. No dependency or migration was added. Milestones 9 and 10 remain skipped; the remaining v1 milestone is fresh-install/release verification.
