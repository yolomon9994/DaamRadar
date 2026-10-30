# Changelog

## v1.0.0 — prepared 30 October 2026; tag pending

First local release of DaamRadar. Release files still need to be committed and the final commit validated before creating the `v1.0.0` tag. See the [release guide](docs/releases/v1.0.0.md).

- Search, filter and compare grocery observations, standard-unit rates, compatible pack sizes and recorded price history.
- Save separate Demo/Collected shopping lists, quantities, budgets and target-price watchlists in the browser; print checklists and transfer validated JSON backups.
- Inspect public source freshness and authorized admin collection-health/catalog-quality reports. Explicit manual collection uses reviewed, bounded source batches and audit records.
- Withhold unsupported comparisons, expired claims, incomplete basket totals and unverified delivery savings. Demo purchase links remain disabled.
- Run locally with SQLite and twelve fictional products; PostgreSQL and production Waitress tooling are available. Hosting remains deferred.
- Include locked dependencies, a fresh-install verifier, six Demo screenshots, release instructions and the MIT license.

Validation of application commit `f82bee6de40a4aab468b8d2449684bc16e77582c`: a clean Windows/Python 3.13 dependency installation, migrations, repeatable seeding, eleven page/API routes, 384 offline tests and production HTTP checks passed. All four Python 3.12/3.13 × SQLite/PostgreSQL GitHub CI jobs passed. Twelve additional Chrome checks covered the release demonstration.

The author's collected database is excluded. Listed prices are dated observations; coverage is limited, delivery areas are unverified and real histories are sparse. No representative market, forecasting or matching-accuracy result is claimed. The analysis notebook and measured matching benchmark are outside v1 scope.
