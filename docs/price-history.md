# Product price-history charts

Product pages show a separate series for each retailer listing, using only stored `PriceHistory` observations. No retailer requests or additional observations are made when someone opens a page. Source links, availability, delivery-area cautions and current-price comparison rules keep their existing behavior.

## Reading the chart

- Each dot is an actual recorded price at its check time. Time spacing reflects elapsed time, not observation order. Dates and times are explicitly Pakistan time, including seconds for nearby checks.
- Two or more observations are connected in chronological order. These segments do not claim prices were known between checks. Unchanged recorded prices form a flat line.
- A single observation appears as one dot with “One observation; no trend yet.” Missing history displays an empty message; the current listing price is never used to invent a historical dot.
- Each listing has a distinct color and line pattern. Checkboxes show or hide series; selecting none displays a prompt. These controls keep the shared axes fixed and do not change the underlying records table. Multiple areas/listings from the same retailer keep distinct labels rather than joining their histories.
- Focus a dot or hover over it to inspect its retailer, recorded price and check time. The expandable table contains exact values and ISO-formatted `<time>` attributes. On small screens, scroll the chart/table within their containers.
- The price axis adjusts to the recorded range and may start above zero; this is disclosed next to the chart. Axis tick labels are scale references, not additional observations. Time-axis tick labels likewise do not add checks.

Demo products show conspicuous fictional-data labels in the chart title, notice, series metadata and table. Demo and collected history are selected separately, including rejection of mismatched listing source flags. No dates or trends are manufactured to fill a sparse chart. Charts will become more informative as real manual refreshes accumulate observations.

## Implementation

`catalog/services/history.py` reads up to the latest 120 observations per compatible listing, ordered by check time and ID, then plots them oldest first. A single window query retrieves those records and one extra per listing to detect truncation. A busy retailer cannot crowd another retailer out of the chart. The limit is disclosed when reached; the existing paginated listing-history API retains older records. This limit bounds page markup and keyboard focus targets without deleting data. History remains tied to the listing as in the existing data model.

SVG geometry is rendered by Django, with labels escaped by the template system. The SVG, table, legend and API links work without JavaScript. `static/js/app.js` enhances retailer selection and point inspection, using text content rather than HTML interpolation. Empty series have no active chart checkbox. There are no chart-library, CDN, npm or Python dependency additions, no schema migration, and no collection or scheduling changes.

## Validation

All 91 Django tests passed, including 12 history-specific tests: chronological/time-scaled geometry, decimal prices, flat prices, equal timestamps, empty/single histories, independent retailer/area series, demo separation, mismatched source flags, per-listing bounds, one-query retrieval, escaping and read-only page loads. Existing matching, ingestion, collection and API tests still pass. Django checks and migration checks passed, and `node --check static/js/app.js` passed.

Headless Chrome checked rendered local page snapshots with the real local database and local static assets at exact 1280px and 390px viewports. Checks exercised series toggles, restoration, the all-hidden prompt, keyboard focus, pointer/focus price descriptions, table expansion, point/table agreement, overall page width and mobile chart scrolling. Desktop demo data was checked separately. Screenshots and browser QA artifacts stay under ignored `reports/`; they do not ship as application code. This phase did not run PostgreSQL or perform a full browser audit of unrelated pages. No new retailer collection was needed.
