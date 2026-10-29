"""Check the production WSGI path using disposable data and loopback requests."""
from contextlib import closing
import json
import os
import re
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import threading
from tempfile import TemporaryDirectory
import time
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    with TemporaryDirectory(prefix="daamradar-production-") as directory:
        temporary = Path(directory)
        database_url = os.getenv("SMOKE_DATABASE_URL") or "sqlite:///" + (temporary / "catalog.sqlite3").as_posix()
        if not database_url.startswith("sqlite:"):
            database = urlparse(database_url)
            if database.hostname not in {"127.0.0.1", "localhost"} or database.path not in {"/daamradar_ci", "/daamradar_smoke"}:
                raise ValueError("SMOKE_DATABASE_URL must select a disposable loopback CI/smoke database.")
        elif os.getenv("SMOKE_DATABASE_URL"):
            raise ValueError("Leave SMOKE_DATABASE_URL empty for an automatically isolated SQLite file.")
        environment = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.production", "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(64), "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://localhost", "DATABASE_URL": database_url,
            "DJANGO_STATIC_ROOT": str(temporary / "staticfiles"), "DJANGO_SECURE_SSL_REDIRECT": "true",
            "DJANGO_SECURE_COOKIES": "true", "DJANGO_SECURE_HSTS_SECONDS": "0",
            "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS": "false", "DJANGO_SECURE_HSTS_PRELOAD": "false",
            "SCRAPING_ENABLED": "false", "WAITRESS_TRUSTED_PROXY": "", "PYTHONUNBUFFERED": "1"}
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        def command(*arguments, env=None):
            result = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env or environment,
                                    capture_output=True, text=True, timeout=120, creationflags=flags)
            if result.returncode:
                raise RuntimeError(f"Command failed: {arguments}\n{result.stdout}\n{result.stderr}")
            return result

        checks = []

        def check(condition, label):
            if not condition:
                raise AssertionError(label)
            checks.append(label)

        deploy = command("manage.py", "check", "--deploy")
        # HSTS must be chosen for the actual HTTPS domain, not invented here.
        check(re.findall(r"\(([a-zA-Z_]+\.[WE]\d+)\)", deploy.stderr) == ["security.W004"],
              "Deployment checks report only the documented, deferred HSTS policy")
        command("manage.py", "migrate", "--noinput")
        command("manage.py", "seed_demo")
        command("manage.py", "collectstatic", "--noinput")
        manifest = json.loads((temporary / "staticfiles/staticfiles.json").read_text(encoding="utf-8"))["paths"]

        if database_url.startswith("sqlite:"):
            backup = temporary / "backup.sqlite3"
            command("manage.py", "backup_sqlite", str(backup))
            with closing(sqlite3.connect(backup)) as restored:
                check(restored.execute("PRAGMA quick_check").fetchall() == [("ok",)], "SQLite backup passes integrity check")
                check(restored.execute("SELECT COUNT(*) FROM catalog_product").fetchone() == (12,), "SQLite restore preserves all demo products")
                check(restored.execute("SELECT COUNT(*) FROM catalog_pricehistory").fetchone() == (36,), "SQLite restore preserves all observations")

        with socket.socket() as port_socket:
            port_socket.bind(("127.0.0.1", 0))
            port = port_socket.getsockname()[1]
        process = None
        # Files avoid inherited Windows pipe handles keeping a server call open.
        with (temporary / "server.log").open("w", encoding="utf-8") as log:
            try:
                process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve", "--port", str(port), "--trusted-proxy", "127.0.0.1"],
                    cwd=ROOT, env=environment, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
                base = f"http://127.0.0.1:{port}"
                with requests.Session() as client:
                    client.trust_env = False
                    # This is a trusted local proxy simulation, not an actual TLS handshake.
                    headers = {"X-Forwarded-Proto": "https"}
                    deadline = time.monotonic() + 30
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError("Waitress exited before becoming ready.")
                        try:
                            ready = client.get(base + "/health/", headers=headers, timeout=2)
                            if ready.status_code == 200:
                                break
                        except requests.ConnectionError:
                            pass
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Waitress startup timed out.")
                        time.sleep(0.2)
                    check(ready.json() == {"status": "ok"} and "no-store" in ready.headers["Cache-Control"], "Database readiness through Waitress")
                    redirect = client.get(base + "/health/", allow_redirects=False, timeout=5)
                    check(redirect.status_code == 301 and redirect.headers["Location"].startswith("https://"), "HTTP redirects to HTTPS")
                    home = client.get(base + "/?source=demo", headers=headers, timeout=5)
                    check(home.status_code == 200 and "fictional" in home.text, "Production homepage with explicit demo data")
                    sources = client.get(base + "/sources/", headers=headers, timeout=5)
                    check(sources.status_code == 200 and 'data-source-health' in sources.text
                          and 'data-source-total="live">0<' in sources.text
                          and 'data-source-management' not in sources.text
                          and 'no-store' in sources.headers.get("Cache-Control", ""),
                          "Production public freshness snapshot excludes demo and operator controls")
                    source_post = client.post(base + "/sources/", headers=headers, timeout=5)
                    check(source_post.status_code in (403, 405), "Public source page rejects collection POSTs")
                    for asset in ("css/app.css", "js/app.js", "js/list-transfer.js", "js/shopping-list.js", "js/watchlist.js"):
                        path = "/static/" + manifest[asset]
                        check(path in home.text, f"Homepage references hashed {asset}")
                        response = client.get(base + path, headers=headers, timeout=5)
                        check(response.status_code == 200 and len(response.content) > 0, f"WhiteNoise serves {asset}")
                    detail = client.get(base + "/products/demo-olpers-milk-1l/", headers=headers, timeout=5)
                    check(detail.status_code == 200 and "Demo comparison" in detail.text, "Production comparison and history render")
                    api = client.get(base + "/api/products/?source=demo", headers=headers, timeout=5)
                    check(api.status_code == 200 and api.json()["count"] == 12, "Production product API")
                    milk = next(product for product in api.json()["results"] if product["slug"] == "demo-olpers-milk-1l")
                    check(milk["standard_unit_price"]["amount"] == "325.00" and milk["standard_unit_price"]["unit"] == "L",
                          "Production API standard-unit prices")
                    check(all(offer["price_change"]["status"] == "no_previous" for offer in milk["listings"]),
                          "Single-observation demo prices do not invent changes")
                    suggested = client.get(base + "/api/search-suggestions/?source=demo&q=Olpers+Milk+1L&fresh=1&in_stock=1&max_price=325", headers=headers, timeout=5)
                    check(suggested.status_code == 200 and suggested.json()["source"] == "demo"
                          and [row["slug"] for row in suggested.json()["results"]] == ["demo-olpers-milk-1l"]
                          and "no-store" in suggested.headers.get("Cache-Control", ""), "Production local search suggestions respect offer filters")
                    filtered = client.get(base + "/api/products/?source=demo&q=Olpers+Milk+1L&min_price=340", headers=headers, timeout=5)
                    check(filtered.status_code == 200 and filtered.json()["count"] == 1
                          and filtered.json()["results"][0]["best_price"] == "325.00"
                          and len(filtered.json()["results"][0]["listings"]) == 3,
                          "Production offer filters preserve full comparison context")
                    invalid_filter = client.get(base + "/api/products/?source=demo&min_price=500&max_price=100", headers=headers, timeout=5)
                    check(invalid_filter.status_code == 400, "Production rejects reversed pack-price ranges")
                    observed = client.get(base + f"/api/listings/{milk['listings'][0]['id']}/history/", headers=headers, timeout=5)
                    check(observed.status_code == 200 and all(row["context_status"] == "captured"
                          and row["is_demo"] is True and row["context"]["product"]["quantity"] == "1000.000"
                          for row in observed.json()["results"]), "Production observation-context capture and API")
                    shopping = client.get(base + "/shopping-list/?source=demo", headers=headers, timeout=5)
                    check(shopping.status_code == 200 and "Fictional demo basket" in shopping.text, "Production shopping list page")
                    basket = client.get(base + "/api/basket/?source=demo&item=demo-olpers-milk-1l:2", headers=headers, timeout=5)
                    check(basket.status_code == 200 and all(row["is_complete"] for row in basket.json()["retailers"]), "Production basket estimates")
                    check(all(line["standard_unit_price"]["amount"] == line["unit_price"]
                              and line["standard_unit_price"]["unit"] == "L"
                              for row in basket.json()["retailers"] for line in row["lines"]),
                          "Production basket standard-unit prices")
                    budgeted = client.get(base + "/api/basket/?source=demo&item=demo-olpers-milk-1l:2&budget=700.00", headers=headers, timeout=5)
                    assessment = next(row for row in budgeted.json()["retailers"] if row["slug"] == "naheed")["budget_assessment"]
                    check(budgeted.status_code == 200 and assessment["status"] == "within_budget"
                          and assessment["remaining"] == "50.00", "Production complete-basket budget assessment")
                    partial = client.get(base + "/api/basket/?source=demo&item=missing-product:1&budget=700.00", headers=headers, timeout=5)
                    check(partial.status_code == 200 and all(row["budget_assessment"]["status"] == "incomplete"
                          for row in partial.json()["retailers"]), "Production incomplete baskets withhold budget assessment")
                    preview = client.post(base + "/api/shopping-list/preview/", headers=headers, timeout=5, json={
                        "format": "daamradar-shopping-list", "version": 1, "source": "demo",
                        "exported_at": basket.json()["estimated_at"], "items": [{
                            "slug": "remote-generated-product-id", "quantity": 2,
                            "product": basket.json()["items"][0]["product"]}]})
                    check(preview.status_code == 200 and preview.json()["items"][0]["slug"] == "demo-olpers-milk-1l"
                          and "no-store" in preview.headers["Cache-Control"], "Production read-only list import preview")
                    watchlist = client.get(base + "/watchlist/?source=demo", headers=headers, timeout=5)
                    check(watchlist.status_code == 200 and "Your price watchlist" in watchlist.text, "Production watchlist page")
                    targets = client.get(base + "/api/watchlist/?source=demo&item=demo-olpers-milk-1l:325.00", headers=headers, timeout=5)
                    check(targets.status_code == 200 and targets.json()["items"][0]["status"] == "target_met"
                          and "no-store" in targets.headers["Cache-Control"], "Production read-only target-price checks")
                    login = client.get(base + "/admin/login/", headers=headers, timeout=5)
                    check(login.status_code == 200 and "Secure" in login.headers.get("Set-Cookie", ""), "Admin CSRF cookie uses Secure")
                    missing = client.get(base + "/does-not-exist/", headers=headers, timeout=5)
                    check(missing.status_code == 404 and "Traceback" not in missing.text, "Debug-free 404 response")
                    bad_host = client.get(base + "/health/", headers={**headers, "Host": "untrusted.invalid"}, timeout=5)
                    check(bad_host.status_code == 400 and "Traceback" not in bad_host.text, "Untrusted host rejected")
            finally:
                if process is not None:
                    # Closing this private parent pipe stops the actual server,
                    # including when a Windows venv launcher sits between us.
                    if process.stdin is not None:
                        process.stdin.close()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        with socket.socket() as probe:
            probe.settimeout(1)
            check(probe.connect_ex(("127.0.0.1", port)) != 0, "Waitress listening socket closed after shutdown")
        print(json.dumps({"database": "sqlite" if database_url.startswith("sqlite:") else "postgresql", "checks": checks, "server_stopped": True}, indent=2))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--serve"]:
        # This watcher exists only in the disposable smoke-test child. No HTTP
        # shutdown route or parent watcher is added to the deployed application.
        def stop_with_parent():
            sys.stdin.buffer.read(1)
            os._exit(0)

        threading.Thread(target=stop_with_parent, daemon=True).start()
        sys.path.insert(0, str(ROOT))
        from config.serve import main as serve
        serve(sys.argv[2:])
    else:
        main()
