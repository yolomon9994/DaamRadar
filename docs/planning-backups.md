# Portable targets and budget backups

## Download and restore locally

1. Open **Watchlist** and select **Demo** or **Collected**. Under **Back up targets and budget**, select **Download targets and budget JSON**. The shopping-budget panel also links here.
2. Keep the file, or take it to another local installation. It contains this catalog's saved target amounts, portable product identities and budget. It contains no observed prices, target-match results, shopping-list items, purchase marks, retailer sessions or accounts.
3. On the receiving installation, select the same catalog and choose **Preview a backup file**. Review each local product match, every unmatched target and the old/new budget. No data changes during preview.
4. Select **Replace targets and budget** to replace both for the active catalog, or **Cancel restore** to keep the current values. Download the current backup first if you need to retain it.

Use the separate [shopping-list JSON transfer](shopping-list.md#back-up-or-transfer-an-editable-list) for items and quantities. Existing shopping-list files retain version 1 and their Merge/Replace behavior. A targets-and-budget backup never changes shopping-list items or the other catalog's targets/budget. There is no automatic collection, account sync or remote storage.

Replacement is explicit: an empty `targets` array clears that watchlist, `budget: null` removes its budget, and `budget: "0.00"` retains an explicit zero spending limit. Budget-only backups are supported. There is no merge mode for targets/budgets, so conflicting thresholds or budgets cannot be silently combined.

Save edited targets or reload to discard drafts before downloading/restoring. Downloads are disabled for unreadable saved targets; repair those by saving a valid target first. Unreadable budgets must be reviewed on the shopping-list page before using a backup. A failed or cancelled preview leaves saved preferences intact. New file choices and navigation cancel old previews; slower responses cannot reopen a cancelled preview. Target edits or same-origin target/budget changes in another tab invalidate a ready preview. A final storage/signature check also catches newer saved data whose event has not arrived yet.

## Identity and observation safeguards

Successful target checks now cache a portable product descriptor alongside the saved target, without caching observed prices. Legacy slug/name/size targets still load. Missing products may have no descriptor; their names and size hints remain recognizable, but a matching slug alone never establishes a portable match.

Preview uses the existing bounded exact resolver shared with shopping-list imports. Brand, canonical contents/unit, pack count, variant, explicit packaging and known GTIN differences prevent substitution. Catalogs stay separate. Display size hints are recomputed from normalized product contents when known. Exact same-installation descriptors can match unknown-size products; unknown or ambiguous cross-installation identities stay unmatched.

Unmatched targets are retained with their amounts, safe text names and cached identity details, marked `unresolved` with a generated local reference. The watch-check API excludes them from product lookup, including if their reference collides with an existing product. They cannot display an observed price or trigger an alert. Remove an unmatched entry and open the intended local product to save a new target after reviewing its exact pack. Restored matched targets immediately reload current local observations and retain existing freshness, stock and delivery warnings; imported amounts never imply that a target is met.

## Storage behavior

Restoration requires browser storage. Both catalog arrays are validated/preserved, and the page changes its state only after target and budget writes succeed. If the budget write fails after targets were written, restoration attempts to roll back the targets to the exact previous stored value. A successful rollback reports that existing preferences were kept. If storage also prevents rollback, the page explicitly reports the incomplete rollback and asks the user to reload/review both targets and budgets while keeping the backup file.

Web Storage does not provide transactions across two keys. The pre-apply check and rollback cover detected changes and write failures; they do not promise crash-safe or atomic writes across browser tabs. No undo history or price snapshot is restored. Normal manual watchlist editing still permits page-only use when storage is blocked; backup restoration refuses to claim persistence in that situation.

The existing keys remain `daamradar.watchlist.v1` and `daamradar.shopping-budget.v1`; no migration or dependency is required. Optional watch entry fields `product`, `unresolved` and `origin_slug` preserve identity and unavailable status. Portability still requires compatible products in the receiving catalog: the Git repository does not ship the development collected database.

## Version 1 file format and preview API

```json
{
  "format": "daamradar-planning-preferences",
  "version": 1,
  "source": "live",
  "exported_at": "2026-10-30T01:00:00+05:00",
  "budget": "3000.00",
  "targets": [{
    "slug": "installation-specific-product-reference",
    "target": "325.00",
    "name": "Olpers Milk 1L",
    "size": "1 L",
    "product": {
      "name": "Olpers Milk 1L", "brand": "olpers",
      "quantity": "1000.000", "unit": "ml", "pack_count": 1,
      "variant": "", "packaging": "", "gtin": "", "size": "1 L"
    }
  }]
}
```

This is a format example; target and budget amounts are user preferences, not retailer prices. `source` is `demo` or `live`, with at most 50 unique target references and a 256 KiB file limit. `product` may be `null` when no portable identity was saved. Names and size hints are bounded text. Positive target strings accept 0.01–9,999,999,999.99 PKR; budgets accept zero through the same maximum, or `null`. Plain decimal strings with up to two fractional digits normalize to two places. Numbers, booleans, exponent notation, non-finite amounts, negative values and extra precision are rejected. Unexpected fields, including observed prices, are rejected at every document level.

`POST /api/preferences/preview/` validates this document and returns `source`, normalized `budget`, and `targets` rows with `original_slug`, nullable local `slug`, `target`, `name`, `size`, nullable normalized `product`, match `status` and explanatory `reason`. Raw duplicate references and multiple aliases resolving to one local product are rejected. GET is unsupported; invalid JSON/documents return 400, files over the byte limit return 413, and the normal anonymous throttle can return 429. Responses are never cached. The anonymous endpoint ignores account sessions and only reads the local catalog; it saves no targets/budgets and makes no retailer requests. Applying a reviewed preview is a separate browser action.

## Validation, 30 October 2026

All **352 offline tests passed on SQLite and PostgreSQL 17.11**, including 14 new tests for portable identity/aliases, size/brand/variant/pack/packaging/GTIN guards, missing metadata, recomputed sizes, source isolation, ambiguity, bounded candidates, duplicate references/resolutions, strict exact decimal strings, zero/unset budgets, empty/budget-only files, product/amount/file boundaries, read-only behavior and unresolved target exclusions.

**27 new Chrome checks** passed against disposable Demo/QA data, covering actual downloads, portable preview/cancel/restore, budget changes, unchanged shopping quantities and other-catalog preferences, reloads, unmatched/escaped identities, unresolved slug collisions, malformed/oversized/observation-bearing files, invalid amounts, drafts, cross-tab invalidation, queued-event races, rollback after a second-key write failure, empty and budget-only restores, blocked storage, late cancelled responses, failed requests and operation without JavaScript. Controls and the contained preview table fit 1280px and 390px screens. The **24 existing watchlist checks** also passed, for **51 Chrome checks** in this milestone. Browser helpers blocked retailer HTTP and confirmed the development database and `.env` were unchanged. QA helpers/screenshots remain ignored under `reports/`.

SQLite and PostgreSQL production HTTP checks passed through Waitress/WhiteNoise, including hashed delivery of the new asset, portable preview amounts/matches, unresolved target exclusions and existing list/budget/import routes. PostgreSQL fresh migrations, migration-drift checks, static collection and full-row dump/restore passed, and temporary servers stopped. JavaScript syntax and Git whitespace checks passed. No dependency or migration was added.
