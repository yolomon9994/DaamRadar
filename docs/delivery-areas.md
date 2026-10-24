# Delivery-area investigation and comparison evidence

Reviewed **24 October 2026**. The current sources do not establish a shared delivery scope for the collected prices. All seventeen real listings therefore retain their original unverified area notes. No real winning-retailer badge or price-spread claim has been enabled.

## Public findings

| Source | Public evidence | What remains unknown |
| --- | --- | --- |
| Jalal Sons | The [reviewed milk page](https://www.jalalsons.com.pk/product/olpers-milk-1ltr-2809398) has a Lahore reference in its public title/metadata. Its [delivery terms](https://www.jalalsons.com.pk/terms-and-conditions) make availability, delivery timing and charges location-dependent. | The retrieved page does not tie its price and stock to a selected address, branch or explicit delivery boundary. A Lahore reference does not verify city-wide coverage or coverage elsewhere. |
| Cartpk | The [homepage](https://www.cartpk.com/) advertises Karachi delivery and checkout time slots. The [milk page](https://www.cartpk.com/olper-s-milk-full-cream-milk-1ltr) marks the product shippable outside Karachi. Its [terms](https://www.cartpk.com/terms-conditions) describe checkout delivery slots. | Outside-Karachi eligibility does not identify destinations, applicable stock, extra charges or whether the observed price applies there. It does not verify Lahore delivery or a shared scope with Jalal Sons. |

These findings do **not** establish disjoint retailer coverage. They also do not establish overlapping coverage. Cartpk's homepage and footer show different free-shipping thresholds; neither is used to compute delivery charges or final costs. No delivery-speed or free-shipping promise is reproduced as a DaamRadar guarantee.

The existing identified, robots-aware client read each source's homepage, canonical terms and one reviewed milk page: four HTTP requests per source including robots, at the existing minimum delay. The local sandbox initially prevented a socket connection; the same helper then ran with network approval. Both approved reviews succeeded. The helper discarded scripts/styles and retained only minimal delivery-related evidence. No price observations or scrape runs were created. The Jalal Sons homepage provided no usable static delivery controls; the reviewed HTML did not establish a supported location-specific retrieval route. This is a bounded review, not a claim that no such route exists anywhere.

No checkout, address submission, account, geolocation permission, branch-cookie manipulation, internal API, alternate bot identity or source configuration payload was used. A browser-tool result for an older Jalal Sons storefront is not treated as evidence for the current adapter's origin or product context. Unknown coverage stays unknown.

## Implemented safeguards

Previously, identical nonempty `delivery_area` strings without the word `unverified` could enable a winner. A manually entered city name was therefore enough to look verified. Live comparisons now require explicit evidence for **each eligible observation**:

- `delivery_area` describes the delivery scope for people.
- `delivery_area_key` is a shared, lowercase, hyphen-separated identifier for precisely the same scope across retailers. Similar city/district names must not be assigned a shared key without confirming the boundaries and applicability.
- `area_evidence_url` identifies public HTTPS evidence on that retailer's exact origin tying this particular listing's price and stock to that scope. Homepage advertising, store addresses and location-free `InStock` markup are insufficient.
- `area_verified_at` records when the observation's scope was verified. It must be on or after `last_checked` and no later than now.

`area_is_verified` derives from these fields; it is not a checkbox. Model/admin validation rejects incomplete evidence, placeholder areas, invalid keys, foreign/insecure URLs, credentials, URL fragments and incompatible times. A database constraint requires the evidence fields together, a nonempty area and a non-demo record, or no evidence at all. Legacy area strings are not backfilled into verification.

The existing collectors have no validated location context and leave every evidence field empty. Ingestion clears previous evidence when it stores a new check, even if price is unchanged. Comparison also rejects evidence older than the current observation, protecting direct updates that did not clear it. Failed imports preserve the previous observation and its evidence through the atomic ingestion boundary. No source adapter currently creates verified evidence automatically.

Fresh, in-stock, source-compatible observations must all have valid evidence for one shared key, from at least two distinct retailers, before winners/spread are displayed. An eligible unverified offer suppresses comparison. Stale, out-of-stock and unknown-availability offers remain visible but do not participate. Ties remain supported. The numeric `best_price` remains the lowest fresh in-stock observed value, with area caveats when comparison is unavailable. Demo comparisons keep their fictional labels and do not acquire real verification.

The product API exposes `area_is_verified`, evidence fields, `has_unverified_areas` and `comparison_area`. Detail pages show area evidence only when valid, otherwise explicitly mark coverage unverified and link to the sources explanation. The sources page displays dated, linked delivery findings separately from listing verification. All page/API requests read local data only.

## Future verified collection

Establish a supported public page or agreed feed that binds an exact scope to product identity, PKR price and stock before implementing a location-specific adapter. Validate its access rules and actual location behavior, preserve the provenance, and add realistic permitted fixtures. An authorized staff reviewer may record evidence on an existing observation in the listing admin only when that evidence exists. The current research does not supply such evidence; do not populate fields merely to enable badges.

Existing listing uniqueness includes the original `delivery_area`. Do not rename existing area notes or turn location-free historical listings into verified-area listings. A future area-specific collector needs a stable separate listing identity and must keep its history distinct. There is no location selector or automatic collection scheduler in this change.

## Setup and validation

Apply the additive migration on another checkout:

```powershell
.\.venv\Scripts\python.exe manage.py migrate
```

The migration adds three empty evidence fields and one completeness constraint. A local before/after audit compared every original column/row in products, listings, history, retailers, runs and categories. All were preserved: nine real products, seventeen real listings and thirty-four real history observations, plus twelve demo products and thirty-six demo listings. No additional source was enabled and no observation was freshened by the review.

All **154 tests** passed, including fifteen synthetic delivery tests for matching text without evidence, shared/different scope keys, ties, eligible unverified offers, freshness/stock, distinct retailers, evidence validation, database constraints, refresh invalidation, admin forms, API/template behavior, demo separation and network-free page views. Django checks and migration consistency checks passed. Local headless Chrome checked the sources and collected product pages at 1280px and 390px, including evidence links, visible area warnings, history points and page width. The product coverage-explanation link remains visible on mobile. Synthetic proof used in tests is not evidence of actual retailer coverage. PostgreSQL has not been runtime-tested.

Local evidence summaries and migration audit files stay under ignored `reports/`; no source HTML, account/session information or development database is added to Git.
