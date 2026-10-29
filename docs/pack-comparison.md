# Compatible pack sizes and unit value

Milestone 5 adds **Pack sizes & value** on product cards and **Compare compatible pack sizes and unit value** on product details. Each link opens `/products/<slug>/pack-comparison/` for that product's catalog. Demo and Collected families remain separate.

The page shows each recorded retailer observation alongside its exact product, pack size/count, total contents, original pack price, Rs/L or Rs/kg or Rs/item, check time, stock and delivery scope. Existing retailer links let readers confirm collected observations. **Add this pack** uses the existing shopping list and preserves the selected pack; it selects a product rather than a retailer. Without JavaScript, the comparison, sorting form, evidence and product/retailer links remain usable.

## What belongs together

Membership uses exact normalized identity, without fuzzy matching. Brand, sorted normalized name tokens, unit dimension, variants, packaging and category must agree. Only quantity and pack count may differ. Existing narrow name aliases, including the milk baseline normalization, still apply. Different brands, flavors, oil types, explicit packaging or dimensions are not suggested as equivalent alternatives.

The parsed title's quantity, normalized unit and pack count must agree with stored canonical fields. Missing brand/name/size, conflicting metadata and fractional piece counts need review rather than a guessed family. Structured variant/packaging metadata also participates in membership. Unspecified packaging stays unspecified and is explicitly disclosed; no bottle, pouch or carton is inferred from a size.

Barcodes normally change across sizes and therefore do not define a size family. A same-format candidate with a known barcode conflicting with the selected product is excluded. Other known barcode conflicts within a single pack format withhold the overall highlight and are shown for review. No products or listings are merged, reassigned or rewritten.

Each listing title must also agree with its canonical product's normalized identity and exact pack contents. A changed or manually reassigned listing cannot supply a unit rate for the wrong pack. Its price remains visible with **Product or listing identity needs review**, while its rate and eligibility are withheld.

## Calculation and sorting

The view reuses the [standard-unit calculator](unit-pricing.md), based on `quantity × pack_count` total contents. It never converts mass to volume or compares different dimensions. For example, a fictional six-pack of 250ml priced at Rs. 510 contains 1.5L and costs Rs. 340/L. Buying several such packs in a shopping list changes the total cost, not the unit rate.

| Sort | Behavior |
| --- | --- |
| Total pack contents | Default; smaller total contents first, with deterministic pack/name/retailer ties. |
| Eligible unit rate | Exact unit-rate ratios for fresh, in-stock, validated observations first; excluded observations follow with their warnings. |
| Recorded pack price | Original numeric pack prices, including dated/unavailable observations with visible warnings. This is not a value ranking. |

Displayed rates use Decimal calculations and two-decimal `ROUND_HALF_UP` rounding. Rate sorting and exact ties use rational arithmetic over the original Decimal prices and contents, so rounded display strings do not determine winners. Positive rates below one paisa show **< Rs. 0.01/unit**, never a free-price claim.

## When a unit rate can be highlighted

A row is eligible for numerical comparison only when the product/listing identity and PKR rate are usable, stock is explicitly `in_stock`, and its check time lies between the snapshot minus the configured freshness window and the snapshot, inclusive. The default window is 48 hours. Stale, future-dated, out-of-stock and unknown-stock observations remain visible with individual exclusion reasons. These dated rates never become eligible merely by opening this page.

The **Lowest comparable unit rate** highlight additionally requires:

1. At least two distinct pack formats among eligible observations.
2. Every eligible collected observation has valid, dated, same-origin delivery evidence for the same scope key and the same delivery label (apart from whitespace/case). A city label alone is insufficient. Non-Latin labels are preserved when comparing scopes.
3. No candidate, product, listing or identity-completeness limit prevents a complete selection.
4. No different exact rate overlaps the lowest rate at the displayed precision.

The highlight can compare two sizes at one retailer or across multiple retailers when that evidence agrees. It describes the lowest unit rate among eligible displayed observations; it does not declare a cheapest retailer, delivered price, basket winner or savings amount between different quantities. Fees and checkout costs remain excluded. Exact equal lowest rates share the highlight. If rounded rates would misleadingly appear tied, no lowest-rate highlight is shown.

Demo comparisons use **Lowest sample unit rate**, require a shared known fictional sample area and retain prominent fictional labeling. Demo purchase links are disabled. Collected observations never borrow Demo data, sample areas or sample prices.

The page is a dated snapshot, with PKT timestamps and a reload link. There is no polling, scheduling, automatic collection or account requirement. Private/no-store responses prevent shared caching of dated results. Source access and availability are not rechecked during a page load.

## Bounds and empty states

Family discovery inspects at most 1,000 catalog candidates of the same dimension with source-compatible listings. At most 30 compatible products and 200 observations are displayed. Candidate/product overflow falls back to the selected product with an explicit notice; listing overflow displays a bounded incomplete selection. All such cases withhold the unit-rate highlight. These limits never silently present a partial selection as a complete winner.

If no other compatible format is recorded, the selected pack's observations remain visible with a clear explanation. A product without observations shows a placeholder rather than a price. Unknown or inconsistent contents show a review notice and **Unit price unavailable**. Missing/incompatible variants are not substituted. Invalid sort values return HTTP 400 with a useful message; unknown products return 404.

## Read-only API

```text
/api/products/<slug>/pack-comparison/
/api/products/<slug>/pack-comparison/?sort=unit_price
```

`sort` accepts `size`, `unit_price` or `pack_price`. The product slug determines the catalog; supplying another catalog does not switch the selected product's source.

The response includes `source`, the selected product descriptor/slug, `as_of`, the configured freshness window, sort, displayed product count, alternative pack-format count, completeness/review notices, ranking availability/note, comparison area and `rows`. Each row exposes product identity/pack fields, total contents, retailer, original PKR price as a decimal string, derived `standard_unit_price`, recorded stock/check time, exclusions, eligibility, delivery evidence, safe source URL and `is_lowest_unit_rate`.

`eligible` means the row passes the product/time/stock/rate checks; it does not imply verified delivery scope. Check `ranking_available`, the ranking note and each row's `area_is_verified` separately. Standard-unit objects retain the existing amount/unit/less-than/display format. No exact rational implementation objects, operator logs or account data are serialized. POST is unsupported, and the normal API throttle still applies.

## Validation, 30 October 2026

All **338 offline tests passed on SQLite and PostgreSQL 17.11**. Seventeen new tests cover exact family membership, multipack contents, liquids/mass/pieces, unknown or inconsistent metadata, listing-title drift, stale/future/stock/cutoff rules, shared/conflicting/unverified delivery scopes including non-Latin labels, exact ties and rounded overlaps, sub-paisa rates, barcode conflicts, Demo separation, bounds, empty states, methods/sorting/cache/links, two-query summaries, read-only behavior, escaping and safe source links.

**23 Chrome checks** passed at 1280px and 390px, covering card/detail entry points, total multipack contents, explicit Demo highlights and disabled purchase links, contained and keyboard-accessible table scrolling, sorting, exact-pack shopping-list additions, flavor exclusion, timestamp/stock warnings, public API behavior, verified/unverified scope handling, empty states and operation without page JavaScript. Browser fixtures and temporary accounts/data did not alter the development catalog; retailer HTTP was blocked.

Fresh PostgreSQL migrations, static collection, production HTTP checks and full-row dump/restore passed, and temporary servers stopped. SQLite production checks also cover the new page/API and Demo safeguards. Configuration, migration drift and Git whitespace checks passed. No dependency or migration was added.

Read-only validation at **00:18:53 PKT on 30 October** checked all **31 collected products**. Three distinct multi-format families are currently available: **Olpers Milk 1L/1.5L**, **Dalda Ghee 2.5kg/5kg**, and **National Chat Masala 50g/100g**. Their six reference views show the correct rates and observations. Live highlights are all withheld: the milk observations are stale; ghee/spice observations lack verified delivery scope. The catalog remains 31 collected products/40 listings plus the separate fictional Demo catalog. SHA-256 comparisons confirmed the development database and `.env` were unchanged. The ignored audit is `reports/local-pack-comparison-validation.json`; screenshots and QA helpers also stay local under `reports/`.
