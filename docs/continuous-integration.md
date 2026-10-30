# Automated checks

The `CI` workflow in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on pushes, pull requests and manual dispatch. Four jobs cover Python 3.12/3.13 with SQLite and PostgreSQL 17. PostgreSQL jobs use a disposable, health-checked service container; SQLite jobs do not start it. Every job performs the same checks:

1. Install `requirements.lock.txt` using pip, with a cache keyed by that file.
2. Run `pip check`, Django system checks (warnings fail), and `makemigrations --check --dry-run`.
3. Apply all committed migrations to an empty database.
4. Run the full test suite through the HTTP-blocking runner.
5. Run `collectstatic` with debug disabled, exercising the production compressed manifest storage.
6. Start the production Waitress server with disposable data and check real HTTP responses using `scripts/smoke_production.py` (see the [deployment guide](deployment.md)).

Jobs have a fifteen-minute timeout, continue independently if a different matrix job fails, and cancel superseded runs for the same branch/PR. The workflow uses read-only repository permissions and does not retain checkout credentials. It performs validation only; it does not deploy, schedule collection or push commits. No project secrets are needed. The database password and Django key in the YAML are public, disposable CI values and must never be used in a deployment.

## Isolation and fixtures

[`config/ci.py`](../config/ci.py) uses **`CI_DATABASE_URL`**, independently of the development `DATABASE_URL`. Its default is in-memory SQLite. It forces collection off, uses a test contact identity, fixes freshness at 48 hours, and disables HTTPS redirects/secure cookies for local Django test requests. Static output can be directed to a temporary directory using `CI_STATIC_ROOT`. The workflow never copies `.env` or imports the ignored development database.

Tests can temporarily override collection settings to exercise command behavior, but [`OfflineDiscoverRunner`](../config/test_runner.py) patches `requests.sessions.Session.send` for the entire run. An unmocked requests HTTP call raises an assertion before transport. Existing adapter tests use minimal saved factual fixtures and mocked responses, including timeout/access-denial cases. Database connections remain available for actual PostgreSQL testing. This guard targets the application's requests client; it is not an operating-system network sandbox or a restriction on pip/GitHub Actions downloads.

Three CI-specific tests check database isolation/configuration, rejection of real HTTP while normal fixture mocks work, and restoration of the patch if test setup fails. As of 30 October 2026, the full suite contains 384 tests. The subsequent production smoke script is a separate process that makes loopback HTTP requests only; it does not run inside the unit-test HTTP guard.

## Running locally

SQLite requires no extra service and does not use or alter your local catalog:

```powershell
.\.venv\Scripts\python.exe manage.py check --settings=config.ci --fail-level WARNING
.\.venv\Scripts\python.exe manage.py makemigrations --settings=config.ci --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate --settings=config.ci --noinput
.\.venv\Scripts\python.exe manage.py test --settings=config.ci --noinput
.\.venv\Scripts\python.exe -m pip check
```

The in-memory migration smoke check and test database are separate: the test runner applies committed migrations again to its fresh test database. The PostgreSQL CI job checks migrations against a persistent disposable service database, then creates/destroys the separate Django test database.

To reproduce PostgreSQL checks with an existing local PostgreSQL server, create a **disposable** database named `daamradar_ci` and a role authorized to create Django's `test_daamradar_ci` database. Set `CI_DATABASE_URL` only for the commands below; do not change your development `.env`. Replace the example credentials and port with your disposable test setup.

```powershell
$ciPreviousDatabaseUrl = $env:CI_DATABASE_URL
$env:CI_DATABASE_URL = 'postgresql://ci_user:TEST_PASSWORD@127.0.0.1:5432/daamradar_ci'
try {
    .\.venv\Scripts\python.exe manage.py migrate --settings=config.ci --noinput
    .\.venv\Scripts\python.exe manage.py test --settings=config.ci --noinput
} finally {
    $env:CI_DATABASE_URL = $ciPreviousDatabaseUrl
}
```

For the production static-file check, use a temporary process environment and output directory. The CI workflow sets `DJANGO_DEBUG=false`, a disposable Django secret and `CI_STATIC_ROOT` on that step, then runs `manage.py collectstatic --noinput` with `config.ci`. This exercises compressed, hashed assets, not the debug storage backend. Deployment checks such as HTTPS proxy/HSTS configuration require the real hosting environment and are outside this workflow.

## Local validation, 24 October 2026

- All **157 tests passed on SQLite** with Python 3.13 and the HTTP-blocking CI runner.
- All **157 tests passed on PostgreSQL 17.11**, using the same Python version and a clean temporary install of `requirements.lock.txt`. The database used the actual PostgreSQL backend and migrations, not a mocked connection or URL-only configuration check.
- Django checks, missing-migration checks and full empty-database migrations passed for both backends. `pip check` found no broken requirements; the separate clean locked-dependency installation succeeded.
- Production static collection passed with compressed manifest storage. Both output manifests contained 170 asset entries, including the app CSS, app JavaScript and Django admin CSS.
- `actionlint` 1.7.12 accepted the workflow syntax and expressions. Its optional ShellCheck integration was disabled; workflow shell steps only invoke fixed Python commands.
- An audit verified that the existing development catalog's products, listings, history, retailers, categories and scrape runs were unchanged. No retailer requests were made.

PostgreSQL was not previously installed here. The validation used portable EDB binaries from the [download linked by PostgreSQL](https://www.postgresql.org/download/windows/), an isolated cluster bound to `127.0.0.1`, a generated temporary password and a disposable database. No Windows service was installed and `.env` was not edited. A Windows output-pipe issue in the temporary logging helper was corrected by writing controller output to a file; the subsequent captured test run succeeded and the server was stopped. Downloads, tools, database clusters and validation logs remain local under ignored `reports/`.

Those checks established Windows/Python 3.13 behavior at that date. Subsequent local and hosted validation is recorded below.

## GitHub results

On **30 October 2026**, [CI run 41072212310](https://github.com/yolomon9994/DaamRadar/actions/runs/41072212310) completed successfully for commit `f82bee6de40a4aab468b8d2449684bc16e77582c` on `main`. All four jobs passed: Python 3.12/SQLite, Python 3.12/PostgreSQL, Python 3.13/SQLite and Python 3.13/PostgreSQL. One workflow run expands into four matrix jobs; open the run to inspect them individually.

The same application commit passed a clean source export with a newly installed locked-dependency environment on Windows/Python 3.13.0: migrations, repeatable Demo seeding, eleven page/API routes, all 384 offline tests and production HTTP smoke checks. See the [release verification and reproduction commands](releases/v1.0.0.md).

These results apply to that exact commit. After committing/pushing the release files, inspect the new run under **Actions / CI** and confirm all four jobs passed before tagging. A local run does not establish hosted success for a later revision. No deployment or branch-protection setting was configured by this release preparation.

References: [GitHub PostgreSQL service containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers), [conditional service images](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idservicesservice_idimage), [setup-python](https://github.com/actions/setup-python).
