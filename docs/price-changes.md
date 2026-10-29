# Recorded price changes and observation context

Retailer rows on product cards/detail pages show **Recorded increase**, **Recorded decrease**, or **Recorded price unchanged** when the latest two consecutive observations can be compared safely. Detail rows include both check dates in PKT and an absolute percentage rounded to two decimal places. This compares a listing with its previous check, not another retailer, an advertised regular price, or the last distinct price.

Changes use exact Python `Decimal` pack prices. Percentage magnitude is `abs(latest − previous) / previous × 100`, rounded with `ROUND_HALF_UP`; direction is explicit in the status. For example, fictional checks at Rs. 340 and Rs. 325 give a recorded decrease of Rs. 15 (4.41%). Unit rates, basket totals, budgets, alerts, stock and winning-retailer rules retain their existing behavior. A stale recorded change may remain visible alongside its stale check date; it does not become a fresh offer or a current discount.

## What new observations preserve

Migration `0006_pricehistory_context` adds nullable `PriceHistory.context`. Successful ingestion now captures version 1 context in the same atomic transaction as the price/time:

- Demo/collected flags for the listing and product, canonical product ID and full descriptor: name, brand, normalized size/unit, pack count, variant, packaging and GTIN.
- Retailer ID/slug/website, external SKU, original title, source URL and currency.
- Stock status, delivery-area label/key, evidence URL, verification time and whether that evidence was valid when captured.

Price and check time remain the existing typed columns. Context contains factual metadata, not page HTML, accounts or sessions. Later listing/product edits cannot retroactively alter these stored JSON snapshots. Ingestion still clears earlier area verification when a new unverified check is stored. A fresh demo seed captures context only for newly created sample observations; rerunning it neither fabricates a trend nor backfills old metadata.

History is inspectable through Django admin, with add/change/delete disabled for observation records. Manual edits to a current listing do not create an implied historical observation; the change indicator is withheld until the listing agrees with its latest captured check. Collection remains manual and follows the existing source controls.

## Comparison safeguards

- Zero or one record: **No earlier price recorded**; no inferred baseline.
- Missing, malformed or unsupported snapshot context in either of the latest two records: **Historical context unknown**.
- Equal/reversed check times or a future latest check: no change amount.
- Current price, check time or metadata differs from the latest record: **Listing changed since its recorded check**.
- Captured product identity, catalog, retailer/SKU/URL, currency, area label/key or verification status differs between checks: **Product or delivery context changed**.
- Either observation is not recorded in stock: **Comparable in-stock history unavailable**.

Both snapshots must agree with the current product/catalog. Equivalent retailer-title wording may compare when the canonical identity and other context agree; the original titles still remain captured. An unverified public listing can have a recorded price change when its recorded scope is unchanged, with existing delivery caveats retained. This does not verify an address or establish delivered savings. Earlier verification dates/evidence are preserved, but different check-specific evidence timestamps alone do not prevent comparison when both observations have the same verified scope.

Lookups fetch at most two observations per displayed listing in one window query. Homepage and product API history-change lookups are limited to the rendered/serialized page rather than all search candidates. There are no retailer requests, history writes, or extra checks on page loads.

## Charts and API

The history table shows each captured pack, stock, source and delivery context. It labels legacy metadata unknown. Known records captured for another product/catalog are excluded from the current product chart; the listing's full history API remains available. Captured context/stock changes break connecting lines. Legacy-to-legacy lines preserve the existing visual record of price amounts but explicitly disclose unverified comparability; a legacy-to-captured transition breaks the line. Historical area labels are not replaced by today's area.

Each product API listing includes `price_change` with `status`, `label`, nullable `amount`/`percent`, previous price/time and latest recorded price/time. Numeric fields are decimal strings; unavailable comparisons return no delta or percentage. Statuses are `increased`, `decreased`, `unchanged`, `no_previous`, `context_unknown`, `invalid_time`, `unrecorded_changes`, `context_changed` and `stock_unavailable`.

`GET /api/listings/<id>/history/` additionally returns `context`, `context_status` (`captured` or `unknown`) and historical `is_demo`. **Historical `is_demo` is now nullable**: legacy records return `null`, rather than borrowing the current listing's flag. Existing `price` and `checked_at` fields are unchanged. Consumers should handle the unknown source explicitly. Current product/listing source flags retain their existing boolean meaning.

## Existing installations

Back up the local database and apply the migration:

```powershell
.\.venv\Scripts\python.exe manage.py backup_sqlite backups/before-history-context.sqlite3
.\.venv\Scripts\python.exe manage.py migrate
```

The SQLite backup command refuses an existing destination; choose a new filename if needed. PostgreSQL installations should use their documented backup procedure. Migration only adds a nullable field. It never guesses past stock, pack or area data from current listings. Existing records retain their original prices/timestamps and have `context: null`; two subsequent comparable captured checks are needed for a numeric indicator. No dependency change or retailer collection is required to migrate.

The development SQLite database was backed up and migrated on 29 October 2026. Its 21 products, 53 listings and 70 historical observations were preserved; all 70 existing contexts remain null, and the original history price/time digest was unchanged. Configuration was unchanged. The private backup and migration audit remain ignored local artifacts.

## Validation, 29 October 2026

All 281 offline tests passed on SQLite and PostgreSQL 17.11 under Windows/Python 3.13, including 18 new tests covering exact deltas/percentages, consecutive-check semantics, immutable captured metadata, legacy/malformed context, current edits, pack/source/area changes, stock/time guards, stale observations, equivalent titles, reassigned listings, chart boundaries, nullable historical source, API rendering, one-query lookups, read-only admin and a real migration from the previous schema without backfill. Fresh migrations, drift checks, static collection, production HTTP smoke and PostgreSQL dump/restore passed; temporary servers stopped afterward.

Twenty-one Chrome checks passed for cards, details, dates, captured context, history lines/API, unknown or unsafe comparisons, stale observations and single-point demo data. Card layouts were checked at 1280px and 390px using fictional disposable observations. Browser QA performed no retailer requests and left the development database/configuration unchanged. Generated QA files remain ignored.
