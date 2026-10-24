# Production startup and readiness

DaamRadar now has a production profile and a Waitress startup command for Windows or Linux. A hosting service, domain, TLS certificate, reverse proxy and process supervisor have not been provisioned. The commands below prepare a separate staging/production checkout; they do not replace the working development environment.

## Verify locally without editing .env

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe scripts/smoke_production.py
```

The smoke script generates a temporary secret, SQLite database and static directory, loads labeled demo data, and starts Waitress on a temporary loopback port with `DEBUG=false`. It checks database readiness, HTTP-to-HTTPS redirection, homepage/detail/history/API rendering, hashed CSS/JS delivery through WhiteNoise, the admin CSRF cookie's Secure flag, and generic 400/404 responses. It also verifies a SQLite backup. The server stops and the temporary files are removed when the script exits, including on failure. Your `.env` and collected database are not used.

For CI's PostgreSQL service, `SMOKE_DATABASE_URL` selects the already disposable `daamradar_ci` database. Only a loopback database named `daamradar_ci` or `daamradar_smoke` is accepted. Other environments should use their own disposable setup; never point this script at collected data. The script seeds demo data and applies migrations there. All four CI matrix jobs now include the production smoke check after the normal tests/static checks.

The HTTPS portion simulates an identified loopback reverse proxy sending `X-Forwarded-Proto: https`; it does not issue certificates or test a real TLS handshake. Real HTTPS and proxy behavior must be checked on the chosen staging host.

## Configure a separate deployment

Use [`.env.production.example`](../.env.production.example) as the configuration reference. Set the variables through the hosting environment, or copy the example to `.env` **in a new deployment checkout**. Keep the development checkout's `.env` intact.

- Set `DJANGO_DEBUG=false`, generate a unique `DJANGO_SECRET_KEY`, and configure explicit `DJANGO_ALLOWED_HOSTS`. The production profile rejects debug mode, missing secrets, empty hosts and a wildcard host entry.
- Replace `daamradar.example` with the actual domain, including the appropriate HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS` for admin forms.
- Configure a PostgreSQL database/role and an appropriately URL-encoded `DATABASE_URL`. SQLite remains available for local staging, but a database on ephemeral hosting storage will not survive replacement of the instance.
- Configure `DJANGO_STATIC_ROOT` if static output belongs outside the checkout. WhiteNoise uses compressed manifest storage with debug disabled.
- Keep `DJANGO_SECURE_SSL_REDIRECT=true` and `DJANGO_SECURE_COOKIES=true` behind verified HTTPS. Production defaults to these values, but explicit environment values take precedence; a development `.env` must not be reused as a production profile.
- Keep collection disabled initially. Publishing the application does not activate a scheduler or establish a new retailer access/reuse basis.

Generate a secret on the destination machine and store it privately:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
```

The explicit production settings flag below matters: placing `DJANGO_SETTINGS_MODULE` in `.env` alone does not override `manage.py`'s initial default. Hosting process environment variables can select it; the startup entry point selects it unconditionally.

After the database is provisioned, back it up before applying changes to an existing deployment. In a new checkout/database:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe manage.py migrate --settings=config.production --noinput
.\.venv\Scripts\python.exe manage.py collectstatic --settings=config.production --noinput
.\.venv\Scripts\python.exe manage.py check --settings=config.production --deploy
.\.venv\Scripts\python.exe -m config.serve --host 127.0.0.1 --port 8080 --trusted-proxy 127.0.0.1
```

The final command assumes a single reverse proxy on loopback. Use its actual peer IP instead. On Linux, use `.venv/bin/python` in place of the Windows executable. A hosting platform that supplies a port through `PORT` can omit `--port`; platforms requiring a network bind may need `--host 0.0.0.0`, with ingress restricted to the configured proxy. Keep the process under the host's service manager with restart policy and stdout/stderr capture. Waitress itself does not provide TLS, run migrations at startup or create admin credentials. Create your own admin account separately if required.

## Reverse proxy and HTTPS

The server trusts no forwarded headers unless `--trusted-proxy` or `WAITRESS_TRUSTED_PROXY` specifies an exact IP. It clears untrusted proxy headers and never exposes Waitress tracebacks. For the configured single hop it trusts only `X-Forwarded-Proto` and `X-Forwarded-For`; Waitress validates the peer and updates the WSGI scheme/client address. Django does not separately trust a raw proxy header.

The proxy must accept the intended domain, terminate HTTPS, preserve Host and overwrite client-supplied forwarding headers. For example, the forwarding portion of an nginx location behind an already configured TLS listener is:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
}
```

This is a single-hop example, not a complete nginx/TLS configuration. A CDN plus proxy requires a separately reviewed trust chain. Test real client-address handling, CSRF submissions and HTTPS redirects on staging before serving visitors. Multiple app processes/instances also need shared caching for consistent API rate limiting; the current default cache is local to each process.

HSTS is deliberately **off** until the actual HTTPS domain and subdomain policy are established. `check --deploy` therefore reports `security.W004`. The smoke script expects exactly this documented warning and rejects additional check warnings/errors. After HTTPS validation, choose an appropriate `DJANGO_SECURE_HSTS_SECONDS`; `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` and `DJANGO_SECURE_HSTS_PRELOAD` remain explicit opt-ins. Django may report additional HSTS warnings when these are false; assess them against the domain rather than enabling preload/subdomain coverage merely to remove warnings.

## Database readiness

`GET /health/` and `HEAD /health/` execute a single `SELECT 1` against the configured default database. Success returns HTTP 200 with `{"status":"ok"}`; a database/interface error returns 503 with `{"status":"unavailable"}`. Responses are not cached and reveal no connection details. Only GET/HEAD are supported; unsupported methods are rejected (CSRF middleware can reject POST before the view's 405 response). Invalid hosts are rejected before querying the database. HTTPS redirect policy still applies.

Configure probes through the correct HTTPS/proxy route. This is a database-connectivity readiness check, not proof of applied migrations, retailer freshness, source availability or final delivery coverage. Apply migrations before routing traffic. Production PostgreSQL connections have a default five-second connection timeout, unless explicitly configured otherwise.

## Validation, 24 October 2026

All **168 tests passed on SQLite and PostgreSQL 17.11** with Python 3.13 on Windows, including eleven new readiness/configuration/server/backup tests. Both backends passed the real Waitress production smoke script. SQLite backup tests cover committed WAL data, non-overwrite behavior, unsupported/missing databases and cleanup after failure. PostgreSQL custom-format dump/restore preserved every row in every public table of a disposable database. A real local SQLite backup and its separate restored copy matched the original database's complete logical data; the collected catalog remained unchanged.

Dependencies, migration consistency and workflow syntax checks passed. No schema migrations were added. The new hosted CI smoke step, real hosting/TLS, service-manager behavior, shared production caching and off-machine backup storage still need validation in their actual environments. See [backup/restore procedures](backups.md) and [CI setup](continuous-integration.md).

References: [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/), [Waitress usage](https://docs.pylonsproject.org/projects/waitress/en/stable/usage.html), [Waitress proxy configuration](https://docs.pylonsproject.org/projects/waitress/en/stable/reverse-proxy.html).
