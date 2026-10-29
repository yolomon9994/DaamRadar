# Shopping list and retailer basket estimates

## Use locally

Start Django using the README instructions. Select **Add to list** on a product card or detail page, then open **Shopping list** in the header. Adding the same product again increments its quantity. Quantities count packs of that exact canonical product, including its existing size/pack definition; the app does not substitute sizes or brands.

The demo and collected catalogs have separate lists. Adjust quantities, remove items, clear the active list, or refresh estimates. A list supports up to 50 distinct products and 1–99 packs of each. No account, migration or new dependency is needed.

Lists are saved in this browser's local storage under `daamradar.shopping-list.v1`. Slugs, quantities and cached product identity details are saved; prices are re-read from the local database. Old slug/quantity-only lists remain supported. Lists survive a restart at the same browser origin, but do not automatically sync across devices, browser profiles, ports or `localhost`/`127.0.0.1`. Clearing browser storage removes them. Tabs at the same origin receive storage updates. Blocked/full storage falls back to memory with a warning; those changes last only on the current page. Invalid saved data produces an empty list with a warning.

JavaScript is required for shopping-list controls. Product browsing and individual comparisons remain available without it. Page views and basket calculations never trigger retailer collection.

## Back up or transfer an editable list

1. Open **Shopping list**, choose **Demo list** or **Collected list**, and let its estimates load so product identities can be cached.
2. Under **Back up or transfer your list**, select **Download list JSON**. This downloads just the selected catalog's list. Keep the file as a backup or move it to another computer.
3. Run DaamRadar on the receiving computer and open the same catalog's list. Select **Preview a list file** and choose the JSON export. The local server must be running to validate and resolve it; an empty list can accept imports too.
4. Review the imported names, pack sizes, quantities and local matches. Choose **Merge** to add quantities to matching current items, or **Replace** to replace only this catalog's list. Select **Apply merge** or **Replace current list** to save the result. **Cancel import** discards the preview.

Previewing a file changes nothing. Merge refuses a result above 50 products or 99 packs of one product, rather than clipping quantities; choose Replace or adjust the list/file. Invalid quantities on the current page must be corrected before downloading or applying a file. The other catalog's list is preserved. A wrong-catalog file tells you to switch lists first. Applying a file clears temporary purchase checkmarks and reloads estimates from the receiving database.

Files contain names, brand, normalized quantity/unit, pack count, variant, packaging, GTIN when known, a display size, a slug hint and requested pack quantities. They exclude prices, stock, delivery-area evidence, retailer URLs, account data and purchase marks. They do not copy the catalog or create products. Cached identities allow downloads even if a later estimate request fails; an older saved entry whose identity has never loaded exports with `product: null`.

Product slugs may contain generated suffixes and differ across installations. A slug hint is accepted only with matching local product details. Otherwise the resolver requires one exact normalized product identity in the selected catalog, including brand, size, pack count, variant, packaging and GTIN. It uses no fuzzy substitutions. Missing metadata, unknown size/brand, conflicting details, multiple matching products or a candidate search exceeding 1,000 compatible products produce an unpriced preview entry. A same-installation product with unspecified size can restore using its exact slug and descriptor. Imported display sizes are recomputed from the quantity/unit fields.

Unmatched items retain their imported names, sizes and quantities in browser storage, estimates and print checklists, without a broken product link or a full basket total. They never acquire a price just because a placeholder slug coincides with a product. Review them manually: add the correct local product and remove the unpriced entry, or keep it for later. Repeatedly merging the same unresolved file entry adds quantities to that entry; exporting and importing a list with unresolved items preserves them. Imports do not silently retry those matches during ordinary estimate refreshes.

Malformed files, unsupported versions, unexpected fields (including prices), duplicate references, duplicate resolved products and invalid limits are rejected before application. The limit is 256 KiB per file and 1–50 entries. Preview metadata is sent only to this local Django server, held in memory for validation, and never saved by the server. Files are ordinary editable JSON; treat shared names/quantities as data you chose to share. Blocked browser storage allows page-only use with a warning; download the result to keep a copy.

The version 1 structure is:

```json
{
  "format": "daamradar-shopping-list",
  "version": 1,
  "source": "demo",
  "exported_at": "2026-10-29T12:00:00Z",
  "items": [{
    "slug": "demo-olpers-milk-1l",
    "quantity": 2,
    "product": {
      "name": "Olpers Milk 1L", "brand": "olpers",
      "quantity": "1000.000", "unit": "ml", "pack_count": 1,
      "variant": "", "packaging": "", "gtin": "", "size": "1 L"
    }
  }]
}
```

The outer `quantity` counts requested packs; `product.quantity` describes the canonical size in base units (`ml`, `g` or `pc`). `product` may be `null`; otherwise all fields except the recomputed display `size` are required. Edit the outer quantity to change how many packs you want. JSON transfers preserve an editable list; PDFs remain dated print snapshots.

## Print a checklist or save a PDF

After estimates load, scroll to **Take your list with you**. Choose a retailer, or **Items only — no prices**, then select **Print / Save as PDF**. In the browser's print dialog, choose your printer or **Save as PDF**. The checklist uses an A4 portrait layout; printer settings can override the paper size. You can turn off the browser's own headers/footers in that dialog if desired.

**Preview checklist** opens a screen preview. On a small screen, scroll the preview sideways to see the price columns; it also accepts keyboard focus for scrolling. Tick **Picked up** boxes in this preview or mark the printed boxes by hand. Browser marks last only on the current page, survive estimate refreshes/retailer changes for products still on the list, and never reduce quantities or totals. Reloading the page clears them; PDF output is a snapshot, not an interactive form.

The printed page includes the selected catalog/retailer, exact pack sizes and quantities, all requested products, item eligibility, available check dates in Pakistan time (PKT), and the estimate-snapshot time. Missing, stale, unavailable and ambiguous offers stay on the checklist without contributing prices. The most recent observation date is shown for an excluded item when available; it does not make that observation eligible. Incomplete coverage or conflicting areas withhold the full estimate and label any covered-items subtotal separately. Demo, unverified-area and delivery/checkout-charge caveats remain on paper.

Only the selected retailer's estimate is printed. Items-only mode omits price columns and totals. Browser navigation, list-editing controls, other retailer cards and the site footer are hidden. Long checklists paginate with repeated table headings. Both the button and **Ctrl+P** use the same selection, even when the preview is collapsed. Empty lists, invalid quantities and pending/failed estimate requests clear the printable snapshot; printing then shows an explanation instead of an old total. Prices are the dated snapshot shown, not a fresh collection performed when printing.

Printing uses the browser and creates no server-side PDF, new dependency or retailer request. Sharing a saved PDF does not share or synchronize the editable browser list.

## Estimate rules

- Quantities multiply the exact observed unit price using Python `Decimal`; the API returns two-decimal PKR strings.
- Only fresh, in-stock observations from the selected demo/live catalog are included. Missing listings, removed/wrong-catalog products, stale observations, out-of-stock offers and unknown stock are identified separately in the retailer breakdown. The current freshness window follows `PRICE_STALE_HOURS` (48 hours by default).
- Multiple eligible listings for the same retailer/product require the same verified delivery scope before choosing the lowest price. Conflicting or unverified alternatives are excluded as ambiguous. Demo alternatives require the same fictional area label.
- Retailers show the number of distinct selected products included, an included-items subtotal, and an item breakdown with quantities, prices, check times and delivery areas. This coverage count does not assert that the requested number of packs is available.
- A full estimate is shown only when all products have eligible offers and the chosen delivery scopes do not conflict. Conflicting verified keys, different unverified area labels, or mixed verified/unverified scopes withhold the full total. No eligible items produces no subtotal, rather than a misleading zero-price basket.
- Single unverified offers can contribute to an explicitly labeled **observed item-price estimate**, with a delivery-area warning. This is not a verified delivered basket. Delivery fees, checkout charges and stock reservations are excluded. Demo totals are fictional and labeled.
- Retailers appear alphabetically. There is no basket winner, savings badge or cheapest-retailer ranking; an incomplete subtotal cannot win a comparison.

Estimates are reloaded on opening the list, changing quantities, removing items, storage changes from another tab, or selecting **Refresh estimates**. They are not polled in the background. Invalid quantity input clears displayed totals until corrected. Failed requests retain saved items, clear estimates and offer a retry. Removed products remain visible for removal instead of silently shrinking the requested basket.

## Read-only API

```text
GET /api/basket/?source=demo&item=demo-olpers-milk-1l:2&item=demo-nutella-350g:1
```

`source` is `demo` (default) or `live`. Repeat `item=product-slug:quantity` for each product. Duplicate slugs, malformed values, quantities outside 1–99, more than 50 entries and unknown sources return HTTP 400. An empty list returns empty items/retailers. Wrong-source or deleted slugs are unavailable items, not substitutes. The response includes the selected items (including `size`) and retailer estimates with `covered_count`, `item_count`, `subtotal`, nullable `total`, `is_complete`, area flags and per-item exclusion statuses. Lines include `last_checked` for the included offer and `last_observed_at` for the most recent candidate observation, even when excluded. These dates can differ when newer observations are ineligible. Responses use `Cache-Control: no-store`; the normal anonymous API throttle applies. POST is not supported. This endpoint calculates estimates without persisting the list or changing price history.

Available items also include a price-free `product` identity descriptor for transfers. Repeated `unresolved=<selected-slug>` parameters force designated imported entries to stay unavailable; every unresolved reference must be in the requested list, otherwise HTTP 400 is returned.

```text
POST /api/shopping-list/preview/
Content-Type: application/json
```

Send a version 1 document as shown above. HTTP 200 returns `source` and one row per file entry with `original_slug`, requested `quantity`, `imported_name`, nullable local `slug`, `status` (`matched`, `unavailable`, `ambiguous`), `reason` and normalized nullable `product`. No price is returned. Validation errors return HTTP 400, oversized files HTTP 413, and the normal anonymous API throttle can return HTTP 429. GET is unsupported. This anonymous POST computes a read-only preview, ignores account sessions, uses `Cache-Control: no-store`, and performs no database writes, shopping-list storage or retailer requests. Browser application is a separate explicit action after preview.

## Validation, 29 October 2026

All 181 automated tests passed on SQLite under Windows/Python 3.13, including 13 new basket tests for decimal totals, eligibility, incomplete coverage, catalog isolation, missing products, delivery-area conflicts, same-scope alternatives, input validation, no network calls and read-only behavior.

Eighteen Chrome checks against a disposable local Django server covered additions from cards/details, repeated-add quantities, recalculation, persistence across navigation, removal, clearing only one catalog, cross-tab storage updates, deleted products, corrupt/blocked storage and failed estimate requests. Layouts were checked at 1280px and 390px. These checks used fictional demo data and temporary QA observations; the development database and `.env` were unchanged.

The production HTTP smoke check also passed using a separate SQLite database: Waitress served the shopping-list page and basket API, and WhiteNoise served the new hashed JavaScript asset. Django checks and the migration-drift check passed; no database migration is required.

The print milestone retained all 181 passing SQLite tests, extending basket assertions for pack sizes and excluded-observation timestamps. Twenty-one additional Chrome print checks passed, including retailer selection, quantities/totals, purchase marks, items-only output, invalid/error/empty states, and a 50-item checklist. Actual browser-generated PDFs included a one-page two-item checklist and a five-page 50-item checklist; print controls/preview were checked at 1280px and 390px. Generated QA PDFs and screenshots remain ignored local artifacts, not new project dependencies or public data exports.

The list-transfer milestone passed all 229 automated tests on SQLite and PostgreSQL 17.11 under Windows/Python 3.13, including 15 transfer tests. They cover portable identities, size/brand/variant/pack/packaging/GTIN guards, ambiguous matches, source separation, missing metadata, duplicate references, bounded candidate resolution, validation limits and read-only behavior. No new dependency or migration is required.

Twenty-four Chrome transfer checks passed against disposable demo/QA data: actual JSON download, cross-installation slug changes, preview/cancel, merge/replace, local price reloads, reload persistence, safely displayed unavailable items, repeated unresolved merges, catalog isolation, malformed/price-bearing/oversized files, quantity/product limits, invalid current quantities and blocked storage. Transfer controls were checked at 1280px and 390px. The existing 18 shopping-list checks and 21 print/PDF checks also passed. Browser helpers verified that the development database and `.env` were unchanged.

Production smoke validation served the new hashed transfer JavaScript through WhiteNoise on SQLite and PostgreSQL. The SQLite HTTP smoke check also exercised the anonymous read-only preview endpoint through Waitress. PostgreSQL validation checked fresh migrations, migration drift, static collection and a disposable dump/restore, then stopped the temporary server.
