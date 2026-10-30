# Target-price watchlists

## Use locally

1. Start DaamRadar using the README instructions. Choose **Watch price** on a product card, or scroll to **Watch this pack's price** on its detail page.
2. Enter your target price in PKR for **one exact canonical pack** and select **Watch price**. A target for a six-pack is for the whole six-pack, not one inner unit or a litre/kg rate.
3. Open **Watchlist** in the header to review the selected catalog's targets. Edit an amount and select **Save target**, remove a product, or clear that catalog's watchlist. Demo and Collected tabs stay separate.
4. Choose **Check targets** after collecting new prices, or reopen the watchlist/product page. This reads the local database; it does not collect retailer prices. Product pages also offer **Check target again**.

Targets are checked when their watchlist or watched product page opens, after a saved edit/removal, on same-origin storage updates from another tab, or on an explicit check. Homepage cards indicate watched products and link to their controls. Header counts count watched products across both catalogs, not triggered alerts. There is no polling, email, OS notification, scheduler or automatic collection. Results appear inside the website.

Amounts range from **0.01 to 9,999,999,999.99 PKR**, with at most two decimal places. Save up to **50 distinct products per catalog**. Client input normalizes e.g. `300` to `300.00`; comparisons use Python `Decimal`. Invalid edits keep the last saved target but hide its previous alert until a valid amount is saved. A slower older response cannot restore an outdated target match after an edit.

## What a match means

**Observed target met** means at least one stored observation for this exact product is in stock, has a valid check time within `PRICE_STALE_HOURS` (48 by default), belongs to the selected catalog, and has a pack price **less than or equal to** the target. **Above target** means eligible observations exist and all exceed the target. Rates per litre/kg/item may appear as context; targets are always compared with original pack prices.

Eligible retailer observations are listed alphabetically, with their individual prices, target status, original check times in PKT and delivery-area labels/verification. The minimum eligible observed pack price is a numeric summary; this is not a verified cheapest delivered purchase. Different or unverified delivery scopes keep explicit warnings. A single unverified listing can meet a target as an observed price, with confirmation required. No winner, savings or shared-area basket claim is inferred.

Demo matches use fictional observations and remain labeled. Stale, out-of-stock, unknown-stock and future-dated observations cannot trigger an alert. Products without observations, removed products and wrong-catalog references remain visible with an unavailable explanation. Excluded observations can show their last stored check time, without contributing a target-match price. Unknown product sizes do not prevent checking an exact known pack price, but no standard-unit rate is calculated.

Each successful check shows its local evaluation time separately from retailer check times. Results are snapshots. They expire within five minutes, or earlier when an observation reaches its freshness boundary or a future timestamp becomes current. The browser clears result states and asks for another check; it does not fetch automatically. Focus, visibility and history events recheck expiry, with monotonic elapsed time preventing a backward clock change from prolonging a snapshot. Pending/failed checks clear previous results and retain targets. Freshness only describes stored observations: retailer stock, address coverage, delivery fees and final checkout prices still need confirmation. See [shared snapshot rules and checks](usability.md).

## Browser storage

No account or new dependency is needed. JavaScript is required for saving and checking targets. Storage key `daamradar.watchlist.v1` contains separate `demo` and `live` arrays with `slug`, normalized `target`, cached `name` and cached `size`. Successful checks also cache an optional portable `product` identity descriptor; older entries without it still load. Unmatched imported entries carry `unresolved` and `origin_slug` and remain ineligible for price alerts. It stores no observed prices, match results, retailer sessions or account data. Cached names keep removed products recognizable; available products use current local names/sizes when displayed.

Targets persist only at the same browser origin/profile. Ports, `localhost` versus `127.0.0.1`, other computers/profiles and cleared browser storage do not share them. Blocked/full storage falls back to page-only use with a warning; leaving that page loses unsaved-to-storage changes. Malformed or oversized stored lists produce an empty state with an explanation. Other tabs at the same origin receive storage updates. Shopping-list storage and its JSON/PDF transfers remain separate and do not include watch targets.

Use **Back up targets and budget** on the watchlist page for a separate portable JSON backup of the active catalog's targets and budget. Preview exact local matches before explicitly replacing both. Unmatched targets remain visible without alerts, and shopping-list items are kept. See [the file format, restoration rules and validation](planning-backups.md).

## Read-only API

```text
GET /api/watchlist/?source=demo&item=demo-olpers-milk-1l:325.00
```

Repeat `item=slug:target` for up to 50 unique products. `source` is `demo` (default) or `live`. The API accepts positive decimal PKR targets with up to ten integer digits and two fractional digits, without leading zeroes except `0.xx`. It rejects malformed amounts, duplicates, wrong source values and more than 50 items with HTTP 400. An empty list returns empty `items`. Optional repeated `unresolved=slug` values must belong to the submitted items; these entries are excluded from product lookup and cannot produce price alerts, even if a local slug collides. POST and other writes are unsupported. Responses use `Cache-Control: no-store` and the normal anonymous API throttle.

The response has `source`, `currency`, `evaluated_at`, `as_of`, `expires_at`, `max_age_seconds` (300), and `items`. Even an unavailable/empty result has a finite recheck deadline. Each item includes:

- `slug`, normalized `target`, `available`, current nullable `name`/`size` and nullable portable `product` identity (no prices).
- `status`: `target_met`, `above_target`, `stale`, `out_of_stock`, `availability_unknown`, `not_listed`, `product_unavailable` or `unavailable` (invalid observation time).
- `message`, nullable `observed_price`, nullable `standard_unit_price`, and nullable `last_observed_at`.
- `has_unverified_areas`, `has_mixed_areas`, and `offers` containing only eligible observations. Each offer includes `retailer`, `price`, `meets_target`, `last_checked`, `delivery_area` and `area_is_verified`.

Missing/wrong-source references produce unavailable items, not substitutions. All threshold comparisons use exact Decimal pack prices; no rounded standard-unit rate participates. API checks never persist targets or change catalog records/history. The browser sends slug/target query values to the local Django server for evaluation, with no retailer requests. No model changes or migration is required.

## Validation, 29 October 2026

All 253 offline automated tests passed on SQLite under Windows/Python 3.13, including 13 new watchlist tests for exact Decimal thresholds, multipacks, stale/stock/future-time exclusions, area warnings, catalog separation, missing products, snapshot expiry, input bounds, read-only behavior and account-free page access. Django checks and the migration-drift check passed.

Twenty-four Chrome watchlist checks passed using a disposable local server and fictional demo/QA observations. These covered saving/editing/removing targets, equality matches, invalid drafts, reloads, catalog isolation, observation dates, cross-tab updates, delayed older responses, failed requests, snapshot expiry, missing/escaped products, size limits, corrupt storage and blocked storage. Forms and navigation were checked at 1280px, 768px and 390px. The existing 18 shopping-list browser checks also passed after the navigation changes. Browser helpers verified the development database and `.env` were unchanged.

The SQLite production smoke check passed through Waitress and WhiteNoise, including the watchlist page, no-store target API, newly hashed watchlist JavaScript, existing product/basket/list-transfer routes and server shutdown. QA browser helpers and screenshots remain ignored local artifacts.
