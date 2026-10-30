# Catalog quality review

## Use through admin or the local command

Sign in to Django admin and choose **Products → Catalog quality**. **Collection health → Review catalog quality** opens the same report. The direct route is `/admin/catalog/product/quality/`. An active staff account needs view or change permission for each of Product, Retailer listing and Retailer; collection-start/import permissions and ScrapeRun access are not required. Standard admin login/cache protections apply. Only GET/HEAD are supported.

Collected data is selected by default. Switch explicitly to Demo, choose a severity/check, then select **Apply filters**. Conflicts appear before review warnings, ordered deterministically by check and record IDs. Findings show the reason, relevant identity evidence and links to existing admin records. Twenty-five findings appear per page; filters persist through pagination. **Download this report as JSON** downloads all retained findings matching the filters, across pages. Invalid choices return 400 without falling back to an unfiltered report. No JavaScript is needed; wide tables scroll inside a keyboard-focusable region on small screens.

The equivalent local commands use the configured database:

```powershell
.\.venv\Scripts\python.exe manage.py catalog_quality
.\.venv\Scripts\python.exe manage.py catalog_quality --source demo
.\.venv\Scripts\python.exe manage.py catalog_quality --severity error
.\.venv\Scripts\python.exe manage.py catalog_quality --check listing_uncertain
.\.venv\Scripts\python.exe manage.py catalog_quality --source live --format json
```

`--severity` accepts `all`, `error`, `warning`; `--check` accepts `all` or one of the stable codes below. `--format` accepts `text` or `json`. Normal findings do not make the command fail: this is an inspection report, not a pass/fail certificate. Save stdout separately if you want a local artifact; reports contain catalog record identifiers/names and should be reviewed before sharing.

## Checks and interpretation

| Code | Meaning |
| --- | --- |
| `missing_size` | Quantity and normalized unit are both unknown; verify the source instead of guessing |
| `invalid_contents` | Inconsistent/unsupported quantity or unit, invalid count, or fractional pieces |
| `missing_brand` | No explicit canonical brand stored, even if one is recognized in the title |
| `missing_category` | No grocery category assigned |
| `no_listings` | No listing with the same Demo/Collected flag attached to the product |
| `canonical_conflict` | Known title brand/contents/count/variant/packaging contradict stored metadata |
| `canonical_uncertain` | Title has no verifiable size/name, or only inferred brand evidence |
| `potential_duplicate` | Separate products share a normalized exact pack identity, without conflicting stored barcodes |
| `barcode_conflict` | One normalized identity has different nonempty stored barcode values |
| `shared_barcode` | One barcode occurs on different or unverifiable identities; differing complete hard identities are conflicts, while name-only/unknown differences need review |
| `barcode_format` | Nonempty barcode is not an 8-, 12-, 13- or 14-digit value; no checksum/authenticity validation is claimed |
| `source_mismatch` | A listing and its product have different Demo/Collected flags |
| `listing_conflict` | Listing title contradicts a known canonical brand, size/count, variant or explicit packaging |
| `listing_uncertain` | Listing identity cannot be fully established, names differ, or variant/packaging evidence is incomplete |
| `similar_products` | Hard guards agree but product names differ with guarded similarity from 80 inclusive to below 100 |

`error` identifies a detected conflict/invalid structure; it does not authorize an automatic correction. `warning` asks for review or additional evidence. Missing GTIN or unspecified packaging alone is not treated as a defect. A different pack size or count is not a duplicate. Multiple legitimate retailer/location listings on one product are not themselves duplicates. Categories are reviewed for missingness, not semantic correctness; different category assignments do not hide otherwise duplicate identities.

Exact duplicate candidates require known valid structured contents, explicit brand and a verifiable canonical title. Brand, per-inner quantity, normalized unit, pack count, variants, packaging and normalized name tokens must agree. Quantity is not replaced by total contents: six 250 ml units and one 1.5 L pack are different formats. Existing narrow aliases and guarded variant normalization apply; unknown names/sizes or contradictory metadata stay outside duplicate/pair grouping. Known conflicting barcodes withhold the possible-duplicate label.

Similarity checks use the existing hard-guarded matcher within compatible product buckets. Different nonempty known barcode values are excluded from these fuzzy candidates. Exact identities are already covered by grouping. A similarity score is a heuristic out of 100, **not confidence, precision or matching accuracy**, and it never merges records. Listing name differences are review warnings even when similarity is high; title-only barcode evidence is not invented.

The chosen catalog scopes products, duplicates and similarity checks. Listing scans include either matching listing flags or matching product flags, so a cross-catalog inconsistency is visible from both affected catalogs. That does not make its observations eligible or combine the two catalogs. The identity report does not assess current stock, stale prices, delivery evidence, source access or historical compatibility; use the existing collection/source/history tools for those questions.

## Bounds and report format

One report uses four SELECT queries: product/listing totals, a bounded product scan with a same-catalog listing-existence annotation, and a bounded listing scan joined to product/retailer. Rows are ordered by primary key. No PriceHistory, account/session, collection log or environment content enters the report. Admin authentication may perform its normal reads independently.

Current bounds are **1,000 products**, **5,000 listings**, **5,000 compatible-pair checks** and **1,000 returned findings** for the selected filters. Group references show at most **20 products and 20 listings per finding**, retaining group counts and a shortened-reference flag. Reference shortening does not omit the group analysis itself. Filters apply before the returned-finding cap, so another check/severity can still expose findings beyond an unfiltered output cap.

The HTML, text and JSON reports disclose scan/pair/output limits. Counts cover evaluated records; they may be lower bounds when a scan/pair limit is reached. Pair totals refer only to compatible buckets in the scanned product subset. A capped or empty selection cannot establish a clean catalog. Large catalogs may need separately scoped future tooling; this report does not silently paginate the scan and claim exhaustive analysis.

JSON version 1 includes `source`, `as_of` (ISO timestamp with PKT offset), `filters`, `counts`, `by_severity`, `by_check`, `limits`, `complete`, `bounds` and `findings`. Summary counters cover evaluated checks before filters. Findings include stable `code`, `severity`, `title`, `detail`, product/listing references, group counts, `references_limited` and explicit `evidence`. References contain catalog IDs, product names/slugs and listing titles/source names; they contain no observed price or operator log. The report is a snapshot of reads, not an atomic database-wide audit during concurrent catalog edits.

## Review safely

Open each referenced record and its original source evidence. Verify brand, exact contents/count, flavor/type, explicit packaging and any barcode. An unknown field is a reason to gather evidence, not to infer a match. Keep plausible alternatives separate until reviewed. Back up the database before manual corrections and preserve historical provenance; merging/deleting/reassigning products or histories is outside this report. Viewing, filtering, exporting and running the command never mutate catalog records, start jobs, fetch retailers or offer bulk repair actions.

This milestone requires no dependency or migration. It does not implement the skipped notebook/export-analysis or measured matching benchmark milestones.

## Validation, 30 October 2026

All **374 offline tests passed on SQLite and PostgreSQL 17.11**, including 22 new tests covering canonical/listing brand, contents, count, variant and packaging conflicts; missing metadata; valid aliases; exact duplicates and barcode differences; uncertain names; non-Latin/unknown identities; catalog-flag inconsistencies in both directions; source isolation; all scan/pair/output/reference caps; filtered summaries; four SELECT queries; command JSON/text output; permissions; safe methods/cache; invalid filters; pagination; escaping and explicit partial-report warnings. Test fixtures with known problems verify detection even though the reviewed development catalog currently has no findings.

**20 Chrome checks** passed using disposable data and operator/read-only/denied accounts. They cover authentication and model permissions, conflict/duplicate/uncertainty evidence, filtered and paginated findings, escaped product text, Demo separation, empty/invalid selections, actual multi-page JSON downloads, entry points from Products/Collection health, refusal of mutation methods and operation without JavaScript. Filters and contained tables fit 1280px and 390px viewports. Browser servers blocked retailer HTTP and confirmed the development database and `.env` were unchanged; QA helpers and screenshots remain ignored under `reports/`.

SQLite and PostgreSQL production checks passed through Waitress/WhiteNoise, including the new read-only command against the 12-product/36-listing fictional Demo catalog and authentication protection for the report route. PostgreSQL fresh migrations, migration-drift checks, static collection and full-row dump/restore passed; temporary servers stopped. Git whitespace checks passed.

A separate audit at **18:33:15 PKT on 30 October 2026** used a read-only SQLite connection to evaluate all **31 collected products and 40 listings**, plus the separate **12 Demo products and 36 listings**. Neither catalog hit a bound or produced findings from these checks. The collected subset had two compatible product-pair checks. This is a result of the stated rules, not a benchmark or proof that every match is correct, nor a freshness/availability guarantee. All eight report queries were SELECTs; SHA-256 comparisons confirmed the development database and `.env` were unchanged. The ignored artifact is `reports/local-catalog-quality-validation.json`.
