# Search suggestions and offer filters

Milestone 4 adds local product suggestions, fresh/in-stock filters, PKR pack-price ranges and clearer empty results. The existing category, brand, retailer, compatible-size search, sorting and pagination remain available. No retailer requests run during search.

## Using the website

Type at least two characters in the main search box. After a short pause, up to six matching products appear from the selected **Demo** or **Collected** catalog and the filters already applied to the page. Suggestions include the exact product name and pack size, without prices or stock claims. Select one to open its detail page; submitting the form searches normally.

Use **Arrow Down/Up** to select suggestions, **Enter** to open the selection and **Escape** to dismiss them. With no selected suggestion, Enter submits the search. Tab leaves the input normally. Loading/error/empty announcements are available to screen readers. Names are inserted as text, not HTML.

Suggestion requests are debounced by 200 milliseconds, cancelled when replaced or dismissed, and guarded against older responses arriving after a newer query. They run only while the input is focused. There is no background polling. A failed request leaves ordinary GET search usable. Without JavaScript, search, filtering, pagination and empty-result recovery still work; suggestions are an optional enhancement.

Under the catalog, choose any combination of:

| Filter | Meaning |
| --- | --- |
| Fresh checks only | Check time is within the configured freshness window (48 hours by default), including the exact cutoff, and is not in the future. |
| In stock only | The recorded availability is explicitly `in_stock`. This does not require freshness unless that filter is also selected. |
| Minimum / maximum pack price (PKR) | Inclusive range applied to a retailer's recorded pack price, before delivery/checkout charges. These are not Rs/L or Rs/kg bounds. |

Select **Apply** after changing filters. A product must have **one listing satisfying all selected offer conditions**, along with the selected retailer. A stale cheap listing and a fresh expensive listing cannot jointly satisfy “fresh below Rs. 200.” An unknown-stock record does not meet the in-stock filter.

## Preserve comparison context

Product cards and product-list API responses retain all source-compatible offers from the selected retailer(s). **Matches filters** marks the individual offers meeting the new conditions. Other offers remain visible with their existing availability/staleness cautions. This preserves evidence for the comparison rather than creating a winning price by hiding a cheaper offer.

The displayed lowest price, numeric sorting, standard-unit rate and any winning-price claim continue to use **all fresh, in-stock offers from the selected retailer(s)**, with the existing verified-area rules for winners. Consequently, a card's lowest price can fall outside the requested range when another offer matched it. An explanatory note appears whenever offer filters are active.

Example: a product has fresh observed pack prices of Rs. 300 and Rs. 400. A minimum price of Rs. 350 includes that product because the second offer matches; both offers stay visible, the second receives **Matches filters**, and the displayed lowest observed price remains Rs. 300. No cheaper observation is hidden to manufacture a winner.

Future-dated observations are excluded from fresh filtering and the product's eligible best price. Their cards show **Check time needs review**. The API exposes this timestamp anomaly separately from age-based `is_stale`. Stock and delivery-area verification remain separate questions.

## Validation and empty results

Pack-price limits accept nonnegative decimal PKR amounts up to `9999999999.99`, with at most two decimal places. Zero is valid. Negative values, nonfinite numbers, exponent notation, comma-formatted numbers, extra decimal places, unsupported boolean values and reversed ranges are rejected. HTML returns a clear filter error with HTTP 400; APIs return field-level HTTP 400 errors. Valid entered bounds remain available for correction.

Both the main search form and pagination preserve applied offer/category/brand/retailer filters and the catalog. Applying filters preserves the query. If products match the search but none meets the offer conditions, **Remove offer filters** keeps the query, catalog and other filters. Other empty states explain exact pack-size matching and offer catalog reset/source-health links. An empty Collected installation still offers the fictional Demo catalog explicitly; no automatic pack substitution occurs.

## API

The product list and suggestion endpoint accept the same offer parameters:

```text
/api/products/?source=live&q=Olpers+Milk+1L&fresh=1&in_stock=1&min_price=300&max_price=400
/api/search-suggestions/?source=live&q=Olpers&fresh=1&in_stock=1
```

`fresh` and `in_stock` accept `1` (enabled), `0`, blank or absence (disabled). Existing `source`, `q`, `category`, `brand` and `retailer` behavior is preserved. Price bounds can be supplied independently. Product-list sorting and pagination remain supported; suggestions always rank by relevance and return at most six entries.

Suggestion responses have this shape:

```json
{
  "source": "live",
  "results": [
    {
      "name": "Olpers Milk 1L",
      "size": "1 L",
      "slug": "example-local-product-slug",
      "url": "/products/example-local-product-slug/"
    }
  ]
}
```

The slug above is illustrative. Actual slugs belong to each local database. Query text shorter than two characters returns an empty suggestion list. Suggestions reuse the existing spelling fallback and hard brand, metric size, pack-count, variant and explicit-packaging constraints. Both suggestions and full search examine at most 1,000 candidates; this remains a small-catalog implementation.

Listing objects now include `matches_offer_filters`: `true`/`false` on filtered product-list results and `null` when no offer filters apply, including ordinary detail responses. `check_time_is_future` is a boolean timestamp-anomaly flag. Existing `best_price`, `is_best`, stock and area semantics are preserved apart from excluding future-dated checks from eligible product best prices. Product-list and suggestion responses use private/no-store cache headers; the normal anonymous API throttle still applies. POST to the suggestion endpoint is unsupported.

## Validation, 29–30 October 2026

All **321 offline tests passed on SQLite and PostgreSQL 17.11**. Thirteen new tests cover exact/custom freshness cutoffs, future times, independent stock criteria, conditions on a single listing, retailer scope, decimal boundaries, pack versus standard-unit prices, preserved comparison context and real winner eligibility, invalid ranges/flags, catalog separation, bounded suggestions, identity guards, preserved navigation state, scoped empty resets, escaping and read-only behavior. After the final keyboard/anomaly-label refinements, 43 targeted search/catalog/price-change tests passed.

**23 Chrome checks** passed at 1280px and 390px. They cover typo suggestions, keyboard selection/wrapping/dismissal, opening a product, applied filter scope, retained other offers, future/stale exclusion, mobile layouts, corrective errors, empty-result recovery, delayed old responses, network-failure fallback and operation without JavaScript. Browser QA used an isolated database and blocked retailer requests. Screenshots and helpers stay under ignored `reports/`.

Fresh PostgreSQL migrations, static collection, production HTTP checks and full-row dump/restore passed, with temporary servers stopped. SQLite production checks also cover suggestions, preserved comparison context and invalid-range responses. No dependency or migration was added.

Read-only checks against the actual development database matched seven filter combinations to independent database queries: 31 collected products overall, 22 with a fresh observation, 12 with a recorded pack price up to Rs. 200, seven between Rs. 200 and Rs. 400, and two Cartpk products with fresh/in-stock observations up to Rs. 300 at validation. These are dated catalog counts, not guarantees. SHA-256 checks confirmed the database and `.env` were unchanged; no prices were collected. The ignored local audit is `reports/local-search-validation.json`.
