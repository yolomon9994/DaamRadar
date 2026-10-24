# Automated checks

The `CI` workflow in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) runs on pushes, pull requests and manual dispatch. Four jobs cover Python 3.12/3.13 with SQLite and PostgreSQL 17. PostgreSQL jobs use a disposable, health-checked service container; SQLite jobs do not start it. Every job performs the same checks:

1. Install `requirements.lock.txt` using pip, with a cache keyed by that file.
2. Run `pip check`, Django system checks (warnings fail), and `makemigrations --check --dry-run`.
3. Apply all committed migrations to an empty database.
4. Run the full test suite through the HTTP-blocking runner.
5. Run `collectstatic` with debug disabled, exercising the production compressed manifest storage.

Jobs have a fifteen-minute timeout, continue independently if a different matrix job fails, and cancel superseded runs for the same branch/PR. The workflow uses read-only repository permissions and does not retain checkout credentials. It performs validation only; it does not deploy, schedule collection or push commits. No project secrets are needed. The database password and Django key in the YAML are public, disposable CI values and must never be used in a deployment.

## Isolation and fixtures

[`config/ci.py`](../config/ci.py) uses **`CI_DATABASE_URL`**, independently of the development `DATABASE_URL`. Its default is in-memory SQLite. It forces collection off, uses a test contact identity, fixes freshness at 48 hours, and disables HTTPS redirects/secure cookies for local Django test requests. Static output can be directed to a temporary directory using `CI_STATIC_ROOT`. The workflow never copies `.env` or imports the ignored development database.

Tests can temporarily override collection settings to exercise command behavior, but [`OfflineDiscoverRunner`](../config/test_runner.py) patches `requests.sessions.Session.send` for the entire run. An unmocked requests HTTP call raises an assertion before transport. Existing adapter tests use minimal saved factual fixtures and mocked responses, including timeout/access-denial cases. Database connections remain available for actual PostgreSQL testing. This guard targets the application's requests client; it is not an operating-system network sandbox or a restriction on pip/GitHub Actions downloads.

Three CI-specific tests check database isolation/configuration, rejection of real HTTP while normal fixture mocks work, and restoration of the patch if test setup fails. The full suite currently contains 157 tests.

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

These local checks establish Windows/Python 3.13 behavior. Python 3.12 and the Ubuntu/GitHub-hosted service-container matrix have not yet been executed in this session; inspect their actual job results after pushing. No GitHub success badge or hosted-run claim is made here.

## GitHub results

After pushing the workflow, open the repository's **Actions → CI** page and inspect all four job results. A pull request also displays these checks. A local test run or actionlint validation does not establish that GitHub's hosted jobs have run. The workflow must reach GitHub first; this change does not commit/push it or configure branch protection.

References: [GitHub PostgreSQL service containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers), [conditional service images](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idservicesservice_idimage), [setup-python](https://github.com/actions/setup-python).
