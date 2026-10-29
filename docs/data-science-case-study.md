# DaamRadar: data science portfolio case study

## Problem and current delivery

Pakistani grocery retailers use different titles, units and packaging descriptions for similar products. A useful comparison needs both trustworthy observations and conservative identity matching. DaamRadar stores dated listed prices, matches compatible products and exposes the results through a locally runnable Django website and read-only API. People can download the GitHub project and try labeled demo data without a hosting account or live collection.

The current priority is reproducible local use and analytical evidence. Hosting is deferred. The existing production server, backup and CI work remains useful supporting infrastructure; it is not the principal data science result.

## Implemented data work

| Skill | Implementation | Evidence and limits |
| --- | --- | --- |
| Data acquisition | Reviewed retailer adapters, identified requests, robots/delay handling, strict factual-price extraction and audit runs. | Minimal source-format fixtures and dated source reviews. Two retailers currently support limited manual collection; this is not broad market coverage. |
| Cleaning and validation | Unicode/punctuation normalization, brand aliases, PKR/stock validation, quantity/unit conversion, pack and packaging extraction. | For example, compatible `1L`/`1000ml` titles can share an identity; `250ml`, flavored products and multipacks are guarded. Parsing failure preserves previous observations. |
| Derived measures | Decimal price-per-litre, kilogram or item using total normalized pack contents. | Multipacks are included; unknown or unsupported sizes remain unavailable. Rates retain freshness, stock and delivery caveats and do not establish equivalence across brands or variants. See [unit pricing](unit-pricing.md). |
| Entity resolution | Hard compatibility checks followed by RapidFuzz name scoring, a threshold and ambiguity margin. | Rules cover brand, size, unit, pack, known variants, packaging and GTIN disagreements. Unknown or ambiguous identities remain separate. The finite vocabulary needs evaluation on new products. |
| Data modeling and provenance | Canonical products, original retailer titles, listing URLs, availability, check times, observation history and scrape audit outcomes. | Demo and collected data remain separate. Every completed check appends history, even when price is unchanged. |
| Decision rules | Freshness/stock eligibility and explicit delivery-area evidence before a winning comparison. | A numerical observed minimum is not automatically a delivered-price saving. All currently collected areas remain unverified. |
| Visualization and quality | Dated price-history charts, exact-value tables, local APIs and source-health diagnostics. | Single observations are points; sparse history is not filled into an invented trend. Automated tests cover behavior and failure cases. |

Relevant code: [`normalization.py`](../catalog/matching/normalization.py), [`ingestion.py`](../catalog/services/ingestion.py), [`catalog.py`](../catalog/services/catalog.py), [`history.py`](../catalog/services/history.py), and the [source fixtures](../catalog/tests/fixtures/README.md).

## Dataset and what it supports

The dated 24 October 2026 development snapshot contains nine real canonical products, seventeen retailer listings, eight cross-retailer pairs and thirty-four real historical observations. Five pairs are milk products and three are pantry products. The collection is small and manually selected, with unequal history per listing. It cannot support a representative statement about grocery inflation, the cheapest retailer across Pakistan, a reliable forecast, or product availability at a particular address.

The development SQLite database is ignored and is not distributed with the GitHub project. A clean setup loads twelve fictional demo products and thirty-six fictional listings for application exploration. Minimal factual HTML extracts are included for offline parser tests, with provenance. A future analysis dataset needs explicit scope, dates, a data dictionary and a documented reuse basis; the code's open-source intent does not itself establish rights in retailer content.

Current test results are software-quality evidence. The implementation was validated with 168 automated tests on SQLite and PostgreSQL 17.11 under Windows/Python 3.13, plus production smoke and backup/restore checks. **This is not 168 labeled matching examples and is not a matching-accuracy score.** No held-out precision, recall or F1 result has been reported. See [validation](deployment.md#validation-24-october-2026) and [collection outcomes](pantry-catalog.md).

## Reproduce the local demonstration

Follow the [README quick start](../README.md#quick-start-windows--powershell). With a new SQLite database, migrate, run `seed_demo` and start `runserver` on `127.0.0.1:8000`. Explore search, category/brand/retailer filters, product comparisons and price history. Demo prices and disabled purchase links are labeled explicitly. Page views and searches use the local database and do not collect retailer pages.

On 25 October 2026, a disposable copy of tracked source files was checked without the author's database or `.env`. Using the existing Windows/Python 3.13 dependencies, Django checks, migrations and demo seeding succeeded: twelve demo products, thirty-six listings and thirty-six observations, with zero live products. Ten page/API routes returned HTTP 200 through Django's test client with requests HTTP transport blocked. The original database and configuration were unchanged. This checked clean-source/database initialization, not a new dependency installation or a macOS/Linux runtime.

Run offline validation:

```powershell
.\.venv\Scripts\python.exe manage.py test --settings=config.ci --noinput
```

This uses in-memory SQLite, disables collection by default and rejects unmocked requests HTTP calls. It does not modify the local catalog. The reviewed manual collection path is documented separately in the [collection runbook](collection-workflow.md); a reviewer does not need to enable it to explore the application or source-format tests.

## Next analytical milestones

1. **Reproducible analysis export and EDA.** Export only relevant catalog/observation fields into local analysis files, excluding Django accounts and operational secrets. Document schema, provenance, demo/live separation and timestamps. Analyze coverage, missingness, stock/freshness and observed price differences within compatible products. Use explicit as-of times, show sample sizes and retain delivery-area caveats. Add a small pandas analysis workflow and exportable charts once this path exists.
2. **Measured matching evaluation.** Curate independently reviewed matching/non-matching title pairs, preserve their provenance and include difficult size/variant/packaging negatives. Split evaluation by product identity so aliases for the same product do not leak across development and held-out evaluation. Compare simple baselines against the existing rules-plus-fuzzy method. Report precision, recall, F1, false merges, missed matches, ambiguity/abstention and error examples. Treat a small or synthetic-only benchmark as limited evidence.
3. **A concise findings report.** Connect each chart or metric to a specific question, explain cleaning and eligibility choices, and state what the data cannot establish. Add screenshots, exact reproduction commands and actual measured results to the repository. Consider forecasting or other machine learning only after adequate repeated observations and an evaluation design exist.

These are future milestones. There is no pandas notebook, statistical model, forecast or held-out matching benchmark in the current implementation.

## Describing the project on a CV

Choose statements supported by the code and artifacts, for example:

- Built a Python grocery-price collection pipeline with source-specific HTML validation, normalized quantities and provenance-tracked price history.
- Implemented conservative cross-retailer entity resolution using brand, size, variant and packaging rules with RapidFuzz similarity scoring.
- Developed a locally runnable Django comparison application with explicit data-quality safeguards and automated SQLite/PostgreSQL validation.

After the analysis/evaluation milestones are completed, add their measured dataset sizes, baseline comparisons and findings. Do not claim a deployed public service, machine-learning model, representative market study or percentage matching accuracy before those results exist.
