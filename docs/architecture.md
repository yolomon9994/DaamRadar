# Architecture and matching decisions

```mermaid
flowchart LR
    M[Manual reviewed collection] --> A[Retailer adapter]
    A --> C[Rate-limited robots-aware client]
    C --> P[Strict public-data parser]
    P --> N[Normalize and match]
    N --> D[(Listings and price history)]
    U[Anonymous search] --> S[Local search and comparison]
    S --> D
    S --> T[Django Templates / REST API]
```

Search never performs retailer requests. SQLite is used locally; the same models target PostgreSQL via `DATABASE_URL`. Categories are normalized independently; brands are a bounded string field for the MVP. Retailer status describes source readiness, not the presence of fictional demo listings. Canonical products and listings have explicit demo/live flags; the ingestion service keeps them in separate matching pools.

`Product.quantity` stores normalized base-unit size per package (`ml`, `g`, or `pc`), with `pack_count` separately. A pack of six 1L cartons does not match a single 6L container. Titles with multiple ambiguous quantities have no inferred size and cannot automatically match a different listing. Known brands and aliases are normalized. Empty brand or size prevents automatic cross-listing matches.

Candidate matching requires equal brand, quantity, base unit, pack count, known variants, and packaging signature. Explicit GTIN disagreement rejects a match. GTIN agreement still cannot override an incompatible size or variant. Compatible names use RapidFuzz `token_sort_ratio`, with a minimum score of 92 and a five-point margin over the runner-up. Ambiguous candidates create a separate canonical record. Existing unchanged unknown identities retain their original canonical record on updates. Variant vocabulary is deliberately conservative but finite: this is an MVP matcher, not a general proof of product identity. Unknown variants, new retailers, and brand catalog additions need review before expanding automatic linking.

Public search uses looser fuzzy relevance because discovery can return related products. An explicitly parsed quantity, brand, or known variant still narrows results. Search retrieval is capped at 1,000 database candidates; large catalogs need indexed full-text/trigram retrieval and database-level pagination. Nothing in this search path creates canonical matches.

Ingestion validates source URL origin, PKR price and availability, then atomically updates a stable retailer/product-area identifier and appends a `PriceHistory` snapshot. Updates to an existing listing are row-locked. The unique listing constraint prevents duplicate identity rows, but first-time concurrent imports and concurrent canonical creation can still race; current collection is sequential and unscheduled. Larger deployments need an ingestion queue and conflict retry/review policy before adding concurrent workers. History stays associated with the retailer listing when a changed title forces canonical reassignment; a future product-level history visualization must account for these identity changes.

Listings are sorted by numeric decimal price. The lowest observed price considers in-stock availability and a fresh check within `PRICE_STALE_HOURS` (default 48). Stale and unavailable listings remain visible with status. A winning comparison additionally requires multiple distinct retailers with one known area: `has_comparison` is false for a single retailer or unverified areas. Ties can have multiple winners when these conditions hold. Mixed areas suppress winner badges and savings; a numerical minimum is still returned with `has_mixed_areas=true`. Verify final checkout costs with the retailer.

The HTTP client is restricted to each configured HTTPS origin, checks robots per run, respects a minimum five-second interval and stricter crawl delays/rates, caps bodies at 2 MB, applies timeouts, and rejects redirects/errors/challenges without automatic retries. Unavailable robots fail closed. Protego handles robots wildcard/allow precedence and repeated groups. The crawler identifies itself using a configured email or HTTPS project/contact URL. Public product adapters reject query strings and unrelated routes, require one PKR JSON-LD Product/Offer and a matching heading, and exclude images/descriptions from imports. Both compact and fully qualified schema types are accepted. Factual-extract fixtures document actual Naheed/Jalal Sons formats; they do not establish a general source license. Only Jalal Sons is enabled locally, with three observations imported; Naheed's named collection attempt returned 403 and was paused. An intermediate Jalal Sons run timed out before a later successful manual invocation. See the dated source review.

There is no automatic scheduling. A later scheduler should call the same reviewed collection/ingestion boundaries, with overlap prevention, per-source quotas, global backoff, and source validation refreshes. No pandas dependency is needed for the transactional MVP; introduce it when an actual batch-cleaning or analysis workflow justifies it.
