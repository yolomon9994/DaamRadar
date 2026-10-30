"""Verify a Git revision in a clean export, new venv and disposable databases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def check_demo(project):
    """Run only inside the exported project's freshly installed interpreter."""
    sys.path.insert(0, str(project))
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django
    django.setup()
    from django.conf import settings
    from django.test import Client, override_settings
    from unittest.mock import patch
    from catalog.models import AdminPriceRefresh, PriceHistory, Product, RetailerListing, ScrapeRun
    assert Path(settings.BASE_DIR).resolve() == project
    assert not settings.SCRAPING_ENABLED
    assert sys.prefix != sys.base_prefix
    assert Product.objects.filter(is_demo=False).count() == RetailerListing.objects.filter(is_demo=False).count() == 0
    assert Product.objects.count() == 12 and RetailerListing.objects.count() == PriceHistory.objects.count() == 36
    assert not ScrapeRun.objects.exists() and not AdminPriceRefresh.objects.exists()
    routes = ["/", "/?source=demo&q=Olpers+Milk+1L", "/products/demo-olpers-milk-1l/",
              "/products/demo-olpers-milk-1l/pack-comparison/", "/shopping-list/?source=demo",
              "/watchlist/?source=demo", "/sources/", "/health/", "/api/products/?source=demo",
              "/api/basket/?source=demo&item=demo-olpers-milk-1l:2&budget=700.00",
              "/api/watchlist/?source=demo&item=demo-olpers-milk-1l:325.00"]
    with patch("requests.sessions.Session.send", side_effect=AssertionError("No retailer HTTP")), override_settings(ALLOWED_HOSTS=["testserver"]):
        client = Client()
        for route in routes:
            response = client.get(route)
            assert response.status_code == 200, route
        assert client.get("/api/products/?source=live").json()["count"] == 0
        assert "Fictional demo basket" in client.get("/shopping-list/?source=demo").content.decode()
        assert "Demo purchase link disabled" in client.get("/products/demo-olpers-milk-1l/pack-comparison/").content.decode()
    assert not ScrapeRun.objects.exists() and not AdminPriceRefresh.objects.exists()
    print(json.dumps({"routes_passed": len(routes), "demo_products": 12, "demo_listings": 36,
                      "demo_history": 36, "collected_products": 0, "collection_jobs": 0}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="Committed revision to verify; requires Git.")
    parser.add_argument("--check-demo", type=Path, help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.check_demo:
        check_demo(options.check_demo.resolve())
        return
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    original = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in ("db.sqlite3", ".env") if (ROOT / name).is_file()}
    revision = subprocess.check_output(["git", "rev-parse", "--verify", "--end-of-options", options.ref + "^{commit}"], cwd=ROOT, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", revision):
        raise RuntimeError("Git must resolve the reference to a commit hash.")
    files = subprocess.check_output(["git", "ls-tree", "-rz", "--name-only", revision], cwd=ROOT).decode("utf-8").split("\0")
    forbidden = {".git", ".venv", "reports", "backups", "logs", "staticfiles", "__pycache__"}
    for name in filter(None, files):
        parts = Path(name).parts
        if any(part in forbidden for part in parts) or re.search(r"\.sqlite3(?:-|$)", name):
            raise RuntimeError("Private/runtime path in source export: " + name)
        if Path(name).name.startswith(".env") and name not in {".env.example", ".env.production.example"}:
            raise RuntimeError("Private environment file in source export.")
    result = {"revision": revision, "python": sys.version.split()[0], "checks": []}
    # The only recursive cleanup is tempfile's newly created directory, verified
    # to be directly inside this workspace's reports directory.
    with tempfile.TemporaryDirectory(prefix="fresh-install-", dir=reports) as directory:
        temporary = Path(directory).resolve()
        assert temporary.parent == reports.resolve() and temporary.name.startswith("fresh-install-")
        archive, project = temporary / "source.zip", temporary / "source"
        subprocess.run(["git", "archive", "--format=zip", "--output=" + str(archive), revision], cwd=ROOT, check=True)
        project.mkdir()
        with zipfile.ZipFile(archive) as exported:
            for name in exported.namelist():
                if Path(name).is_absolute() or ".." in Path(name).parts:
                    raise RuntimeError("Unexpected archive path.")
            exported.extractall(project)
        assert not (project / ".git").exists() and not (project / "db.sqlite3").exists() and not (project / ".env").exists()
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("DJANGO_", "CI_", "SCRAPER_", "WAITRESS_", "PIP_"))
                       and key not in {"DATABASE_URL", "SCRAPING_ENABLED", "PRICE_STALE_HOURS", "SMOKE_DATABASE_URL", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}
        environment.update(PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_CONFIG_FILE=os.devnull, PYTHONUNBUFFERED="1")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        def run(label, command, *, env=None, timeout=240):
            print("CHECK " + label, flush=True)
            completed = subprocess.run(command, cwd=project, env=env or environment, creationflags=flags,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            (reports / ("fresh-install-" + label + ".log")).write_text(completed.stdout, encoding="utf-8")
            if completed.returncode:
                raise RuntimeError(label + " failed:\n" + completed.stdout[-4000:])
            result["checks"].append(label)
            return completed.stdout

        run("create-venv", [sys.executable, "-m", "venv", str(project / ".venv")])
        python = project / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run("install-lock", [str(python), "-m", "pip", "install", "--no-cache-dir", "--index-url", "https://pypi.org/simple", "-r", "requirements.lock.txt"], timeout=300)
        run("pip-check", [str(python), "-m", "pip", "check"])
        shutil.copyfile(project / ".env.example", project / ".env")
        run("django-check", [str(python), "manage.py", "check", "--fail-level", "WARNING"])
        run("migration-drift", [str(python), "manage.py", "makemigrations", "--check", "--dry-run"])
        run("migrate", [str(python), "manage.py", "migrate", "--noinput"])
        run("seed-demo", [str(python), "manage.py", "seed_demo"])
        run("seed-demo-repeat", [str(python), "manage.py", "seed_demo"])
        result["demo"] = json.loads(run("demo-routes", [str(python), str(Path(__file__).resolve()), "--check-demo", str(project)]))
        quality = json.loads(run("catalog-quality", [str(python), "manage.py", "catalog_quality", "--source", "demo", "--format", "json"]))
        assert quality["complete"] and not quality["findings"]
        tests = run("offline-tests", [str(python), "manage.py", "test", "--settings=config.ci", "--noinput"])
        count = re.search(r"Ran (\d+) tests", tests)
        assert count and re.search(r"\nOK\s*\n", tests)
        result["tests_passed"] = int(count[1])
        result["production"] = json.loads(run("production-smoke", [str(python), "scripts/smoke_production.py"]))
    assert original == {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in original}
    result["development_files_unchanged"] = True
    result["temporary_export_removed"] = True
    (reports / "fresh-install-validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "production"}, indent=2))


if __name__ == "__main__":
    main()
