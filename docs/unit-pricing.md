# Standard-unit prices

Cards and product detail pages show a calculated **Rs/L**, **Rs/kg** or **Rs/item** beside the listed pack price. Each retailer row has its own rate. Included basket lines and retailer print checklists show the same rate; items-only checklists omit prices. The feature works locally with both fictional demo data and collected observations and performs no retailer requests.

## Calculation

The calculator uses the stored canonical `quantity`, normalized `unit` and `pack_count`. `quantity` describes each inner pack; total contents are `quantity × pack_count`. It never reparses the title, converts mass to volume, or assumes an unknown size.

| Stored unit | Standard rate | Formula |
| --- | --- | --- |
| `ml` | PKR per litre (`L`) | listed price × 1000 ÷ total millilitres |
| `g` | PKR per kilogram (`kg`) | listed price × 1000 ÷ total grams |
| `pc` | PKR per item (`item`) | listed price ÷ total pieces |

Examples using fictional prices:

| Canonical pack | Pack price | Standard-unit price |
| --- | ---: | ---: |
| 500 ml | Rs. 180 | Rs. 360.00/L |
| 1 litre | Rs. 325 | Rs. 325.00/L |
| 6 × 250 ml | Rs. 510 | Rs. 340.00/L |
| 2 × 250 g | Rs. 200 | Rs. 400.00/kg |
| 2 × 6 pieces | Rs. 120 | Rs. 10.00/item |

Calculations use Python `Decimal` and round the displayed rate to two decimal places with `ROUND_HALF_UP`. A positive rate that rounds below one paisa displays **< Rs. 0.01/unit**, never a zero-price claim. Unknown/nonpositive/nonfinite quantities or prices, unsupported units, fractional piece counts and invalid pack counts return no rate. The page shows **Unit price unavailable** while retaining any valid listed pack price. Incorrect stored sizes still require catalog review; a derived rate is only as reliable as its inputs.

Buying three canonical six-packs changes the basket total to three times the pack price; it does not change the price per litre. Basket totals continue to multiply the original pack price, so rounded rates never feed back into the charged estimate. Product matching, filtering and listed-price sorting retain their existing behavior; rates of different dimensions are not ranked against one another.

## Observation and comparison rules

A product summary's rate uses the same fresh, in-stock observed minimum as its displayed pack price. If no eligible summary price exists, its rate is unavailable. Individual retailer rows can show a rate derived from a stale or unavailable listed observation alongside its existing stock/date warnings. This does not make the observation eligible again. Basket rates appear only for included offers; stale, missing, out-of-stock, unknown-stock, unresolved and area-ambiguous lines remain excluded.

Unit pricing provides a common denominator for judging pack value. It does not assert that different brands, variants, packaging or quality are equivalent. Delivery-area verification, best-price eligibility and savings rules remain in place. Demo rates stay fictional; collected rates remain dated observations before delivery and checkout charges. No new winner or cheapest-basket ranking is introduced.

## API

Product list/detail responses include `standard_unit_price` at the product level and within each listing. Basket retailer lines include the same field alongside the existing `unit_price` (price of one canonical pack) and `line_total`.

```json
{
  "amount": "340.00",
  "unit": "L",
  "less_than": null,
  "display": "Rs. 340.00/L"
}
```

The entire field is `null` when no rate is available. For a positive rate rounding to zero, `amount` is `null`, `less_than` is `"0.01"`, and `display` is `"< Rs. 0.01/L"` (or `/kg`, `/item`). `amount` is a rounded PKR string, not a basket calculation input. Check the original listing's freshness, stock and delivery-area fields when using a listing rate.

Rates are computed for display, without model fields, migrations, new dependencies or database writes. Shopping-list JSON files and cached product descriptors exclude prices, including these derived rates. Price-history charts retain original observed pack prices.

## Validation, 29 October 2026

All 240 offline automated tests passed on SQLite under Windows/Python 3.13, including 11 new calculation/integration tests. These cover liquids, weights, piece counts, multipacks, Decimal rounding, tiny rates, unknown/invalid dimensions, card/detail/API rendering, basket quantity independence, stale/stock exclusions, source/area safeguards, unchanged listed-price sorting, unresolved imports and no writes or retailer requests. The migration-drift check found no changes.

Eighteen Chrome checks passed for the new unit-rate displays at 1280px and 390px, with temporary QA packs for each dimension, stale and unknown-size products, basket quantity edits and print selection. The existing 24 list-transfer checks and 21 print/PDF checks also passed; the print run passed on an isolated retry after a browser-navigation timeout. Actual PDF checks retained a one-page two-item checklist and a five-page 50-item checklist. Disposable browser servers confirmed the development database and `.env` were unchanged.

The SQLite production HTTP smoke check passed through Waitress and WhiteNoise, including the product and basket API rates, production assets, list-preview endpoint and server shutdown. QA screenshots and generated PDFs remain ignored local artifacts.
