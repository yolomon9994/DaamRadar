# Reviewed catalog expansion, 29 October 2026

Milestone 2 adds **22 products and 23 listings** through six small, manually selected batches. The author's local catalog now contains **31 collected products and 40 listings**, separate from 12 fictional demo products and 36 demo listings. Coverage spans Dairy & eggs, Pantry essentials, Drinks & tea and Household.

Only **nine products have listings from both supported retailers**: the earlier eight pairs plus Nestle Milkpak Cream 200ml. The other 22 products are single-source observations. They support search, lists, unit rates, watches and history, but do not imply cross-retailer coverage. Delivery areas remain unverified, so no winning-retailer or savings claim is enabled.

The development database is ignored by Git. A clone/ZIP contains reviewed URLs, parsers, minimal factual test extracts and these instructions; it must collect its own observations. Test fixtures are dated format evidence and are never loaded as current retail prices.

## Source review and exclusions

The existing named `DaamRadarBot/0.1` client rechecked robots and the canonical [Jalal Sons terms](https://www.jalalsons.com.pk/terms-and-conditions) and [Cartpk terms](https://www.cartpk.com/terms-conditions), then inspected exact public product pages. Requests retained the configured contact, minimum five-second delay, fail-closed access rules and timeout-only recovery. No source images/descriptions, internal APIs, accounts, location cookies or alternate identities were used. The source-specific limitations in the [retailer review](retailer-review.md) continue to apply.

Excluded candidates include:

- Jalal Sons Nesfruta Mango 200ml: no unambiguous structured Product was parsed. Its price was not inferred from search results.
- Jalal Sons `Surf Excel 1 KG`: the title only supplies a brand and size, with structured brand `Surf`; no product type was guessed. The independently reviewed Cartpk Detergent Powder listing is used instead.
- Tapal `Dane Dar Tea 100pcs`: the counterpart does not independently state tea bags, so it is not paired with Jalal Sons' explicit tea-bag product.
- Cartpk Lipton Yellow Label 430g: Jalal Sons only states Lipton Tea 430g, so the more specific variant is not assumed equivalent.
- Cartpk yogurt with a 200ml title is not paired with the 200g yogurt. Sweet N Tasty, whipping cream, different spice sizes and promotional oil bundles are not substituted for the reviewed products.

Evian and Malee are added as literal brand names. No new fuzzy aliases, lower matching threshold or relaxed size/variant/packaging guards were introduced. Unknown packaging stays unspecified. The reviewed cream pair uses the existing narrow Milk Pak/Milkpak normalization.

## Import on another local installation

First configure the supported sources as described in the [collection runbook](collection-workflow.md). Collection remains disabled by default on a fresh checkout. In admin, open **Collection health → Import reviewed catalog**, select one of the following batches, preview the missing listings, then import it. Each batch remains below the ten-URL cap.

| Batch | New source listings |
| --- | ---: |
| `jalal-sons-expanded-dairy` | 5 |
| `jalal-sons-expanded-pantry` | 7 |
| `jalal-sons-expanded-drinks` | 7 |
| `cartpk-expanded-dairy` | 1 |
| `cartpk-expanded-pantry` | 2 |
| `cartpk-expanded-household` | 1 |

The equivalent terminal commands for one batch are:

```powershell
# Preview: no requests or database writes.
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-expanded-dairy --missing-only --dry-run

# Explicit missing-only collection; repeat for each desired source/batch above.
.\.venv\Scripts\python.exe manage.py scrape jalal-sons --batch jalal-sons-expanded-dairy --missing-only --report-dir reports
```

Use the original milk, pantry and basics batches for the previously reviewed products. Missing-only imports preserve existing source observations, even when stale; they do not refresh them. New product categories and owned illustrations come from reviewed URL metadata. A demo-free installation creates the necessary categories without seeding fictional products.

## Refreshing the larger catalog

```powershell
.\.venv\Scripts\python.exe manage.py refresh_prices --dry-run
.\.venv\Scripts\python.exe manage.py refresh_prices --report-dir reports
```

A single refresh selects **the oldest ten distinct existing URLs per source**, ordered by check time then listing ID. It prints a selection notice when more exist. Remaining URLs need another explicit manual invocation after reviewing the result; the command does not split the selection into background runs. The admin action uses the same bound and explains the follow-up. Failed checks keep their old timestamp and may remain due on the next invocation; inspect failures before repeating.

Saved imports and explicit `--url` requests still reject more than ten distinct URLs. No scheduler, source switch or request rate is changed. Successful unchanged checks still append captured history; one newly imported observation does not manufacture a price change.

## Validation

The database was backed up before importing, and every earlier product, listing, observation, category, source and collection record was compared by ID and full row contents afterward. Accounts and `.env` were also verified unchanged. Existing timestamps were not refreshed merely to make the catalog appear current. Actual import outcomes and final check evidence are recorded below.

Runs **#14–#19** all succeeded, storing **23 observations in 29 HTTP requests** between **21:56:10 and 21:58:18 PKT on 29 October 2026**. Prices and stock agreed with the reviewed extracts. Real history now contains **57 observations**. The new 23 listings were fresh at validation; the original 17 retain their 23–24 October timestamps and are stale. All 40 listings remain area-unverified. No collection jobs remain running.

| Run | Batch | Stored | Requests |
| --- | --- | ---: | ---: |
| 14 | Jalal Sons expanded dairy | 5 | 6 |
| 15 | Jalal Sons expanded pantry | 7 | 8 |
| 16 | Jalal Sons expanded drinks | 7 | 8 |
| 17 | Cartpk expanded dairy | 1 | 2 |
| 18 | Cartpk expanded pantry | 2 | 3 |
| 19 | Cartpk expanded household | 1 | 2 |

All **292 offline tests passed on SQLite and PostgreSQL 17.11**. Eleven new tests cover every reviewed extract and URL, identity/stock/currency/price drift, exact bounded batches, both import orders, preserved demo data, distinct pack sizes, category/search/detail/API behavior, create-only repeats, demo-free setup and successive bounded refreshes. Arbitrary eleven-URL imports still fail before fetching. Configuration and migration-drift checks passed; no dependency or migration was added.

**28 Chrome checks** passed at 1280px and 390px, covering four filtered categories, pagination, rendered owned illustrations, the cream pair, single-source labels, unit rates, isolated history points, unchanged demo separation and withheld winners/trends. Browser QA used a disposable in-memory database and factual fixtures, with retailer HTTP blocked; the development database and `.env` were unchanged. PostgreSQL fresh migrations, static collection, production HTTP smoke and all-table dump/restore passed; temporary HTTP and database servers were stopped.

The verified backup is `backups/before-catalog-expansion-20261029-165546.sqlite3`. Before/after audits, run reports and screenshots stay under ignored `reports/`. The backup filename uses UTC; source check times above use PKT. Categories contain 11 dairy, 12 pantry, seven drinks and one household product. This is a reviewed prototype catalog, with limited cross-retailer coverage and sparse history.

## Reviewed additions

Prices below are dated factual extracts from individual product pages on 29 October 2026, in PKR before delivery/checkout charges. Each source reported in-stock availability during review. A dash means no counterpart was enabled, rather than an assumed missing product or price.

| Product | Jalal Sons | Cartpk |
| --- | --- | --- |
| Dalda Ghee 5Kg | [3,044.00](https://www.jalalsons.com.pk/product/dalda-ghee-5kg-2809046) | — |
| Dalda Ghee 2.5Kg | [1,574.00](https://www.jalalsons.com.pk/product/dalda-ghee-25kg-2809045) | — |
| Tapal Danedar Tea Bags 100 Pieces | [899.00](https://www.jalalsons.com.pk/product/tapal-danedar-tea-bags-100-pieces-3007873) | — |
| Lipton Tea 430Gm | [1,008.00](https://www.jalalsons.com.pk/product/lipton-tea-430gm-2810108) | — |
| Surf Excel Detergent Powder 1kg | — | [640.00](https://www.cartpk.com/surf-excel-detergent-powder-1kg) |
| Nestle Yogurt Plain 200Gm | [164.00](https://www.jalalsons.com.pk/product/nestle-yogurt-plain-200gm-2808831) | — |
| Nestle Fruit Yogurt Strawberry 100Gm | [110.00](https://www.jalalsons.com.pk/product/nestle-fruit-yogurt-strawberry-100gm-2808827) | — |
| Nestle Milkpak Cream 200Ml | [228.00](https://www.jalalsons.com.pk/product/nestle-milkpak-cream-200ml-2809410) | [250.00](https://www.cartpk.com/nestle-milk-pack-cream-200-ml) |
| Nestle Milk Pak Dairy Butter 200g | [658.00](https://www.jalalsons.com.pk/product/nestle-milk-pak-dairy-butter-200g-3007553) | — |
| Nestle Nesfruta Mango 1L | [249.00](https://www.jalalsons.com.pk/product/nestle-nesfruta-mango-1l-2809139) | — |
| Nestle Milo Drink 180ML | [94.00](https://www.jalalsons.com.pk/product/nestle-milo-drink-180ml-2809136) | — |
| Nestle Milo Drink Tin 235ML | [594.00](https://www.jalalsons.com.pk/product/nestle-milo-drink-tin-235ml-2809137) | — |
| National Chat Masala 100G | [188.00](https://www.jalalsons.com.pk/product/national-chat-masala-100g-2808927) | — |
| National Biryani Masala 45G | [158.00](https://www.jalalsons.com.pk/product/national-biryani-masala-45g-2808924) | — |
| National Ginger Powder 50g | [244.00](https://www.jalalsons.com.pk/product/national-ginger-powder-50g-3012051) | — |
| National Iodized Salt 800Gm | [60.00](https://www.jalalsons.com.pk/product/national-iodized-salt-800gm-2808929) | — |
| National Red Chilli Powder 100Gm | [198.00](https://www.jalalsons.com.pk/product/national-red-chilli-powder-100gm-2808930) | — |
| Evian Water 500Ml | [594.00](https://www.jalalsons.com.pk/product/evian-water-500ml-2810170) | — |
| Malee Coconut Water 330ML | [548.00](https://www.jalalsons.com.pk/product/malee-coconut-water-330ml-2809163) | — |
| Nestle Everyday 15G | [30.00](https://www.jalalsons.com.pk/product/nestle-everyday-15g-2809418) | — |
| Shan Korma Masala 50g | — | [350.00](https://www.cartpk.com/shan-korma-masala-50g) |
| National Chat Masala 50g | — | [170.00](https://www.cartpk.com/national-chat-masala-50g) |
