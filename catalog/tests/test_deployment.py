import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import InterfaceError, OperationalError, connections
from django.test import SimpleTestCase, TestCase, override_settings

from config.serve import main


class HealthTests(TestCase):
    def test_health_and_head_check_database_without_exposing_details(self):
        with self.assertNumQueries(1):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.head("/health/").content, b"")
        self.assertEqual(self.client.post("/health/").status_code, 405)

    def test_database_failure_is_uncached_generic_503(self):
        for error in (OperationalError, InterfaceError):
            with self.subTest(error=error), patch.object(connections["default"], "cursor", side_effect=error("secret-host/password")):
                response = self.client.get("/health/")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"status": "unavailable"})
            self.assertNotIn(b"secret-host", response.content)
            self.assertIn("no-store", response["Cache-Control"])

    @override_settings(ALLOWED_HOSTS=["testserver"])
    def test_invalid_host_rejected_before_database_access(self):
        with patch.object(connections["default"], "cursor") as cursor:
            self.assertEqual(self.client.get("/health/", HTTP_HOST="untrusted.invalid").status_code, 400)
            cursor.assert_not_called()


class ProductionConfigurationTests(SimpleTestCase):
    def import_profile(self, **changes):
        environment = {**os.environ, "DJANGO_DEBUG": "false", "DJANGO_SECRET_KEY": "testing-production-settings-only-0123456789-abcdefghijklmnopqrstuvwxyz",
                       "DJANGO_ALLOWED_HOSTS": "staging.example", "DJANGO_SECURE_SSL_REDIRECT": "true", "DJANGO_SECURE_COOKIES": "true",
                       "DATABASE_URL": "", **changes}
        code = "from config import production as p; import json; print(json.dumps({'debug':p.DEBUG, 'redirect':p.SECURE_SSL_REDIRECT, 'secure_cookie':p.SESSION_COOKIE_SECURE, 'storage':p.STORAGES['staticfiles']['BACKEND'], 'proxy':p.SECURE_PROXY_SSL_HEADER}))"
        return subprocess.run([sys.executable, "-c", code], env=environment, capture_output=True, text=True, timeout=15)

    def test_production_requires_debug_off_secret_and_explicit_hosts(self):
        for change in ({"DJANGO_DEBUG": "true"}, {"DJANGO_SECRET_KEY": ""}, {"DJANGO_ALLOWED_HOSTS": ""}, {"DJANGO_ALLOWED_HOSTS": "*"}):
            with self.subTest(change=change):
                result = self.import_profile(**change)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)

    def test_production_uses_manifest_and_secure_settings(self):
        result = self.import_profile()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"debug": False, "redirect": True, "secure_cookie": True,
            "storage": "whitenoise.storage.CompressedManifestStaticFilesStorage", "proxy": None})

    def test_server_uses_production_profile_and_conservative_proxy_defaults(self):
        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "config.ci", "WAITRESS_TRUSTED_PROXY": ""}), \
             patch("django.core.wsgi.get_wsgi_application", return_value="wsgi app"), patch("waitress.serve") as serve:
            main(["--port", "8088"])
            self.assertEqual(os.environ["DJANGO_SETTINGS_MODULE"], "config.production")
            self.assertEqual(serve.call_args.args, ("wsgi app",))
            self.assertEqual(serve.call_args.kwargs["host"], "127.0.0.1")
            self.assertTrue(serve.call_args.kwargs["clear_untrusted_proxy_headers"])
            self.assertFalse(serve.call_args.kwargs["expose_tracebacks"])
            self.assertNotIn("trusted_proxy", serve.call_args.kwargs)

    def test_server_accepts_only_an_explicit_proxy_ip(self):
        with patch.dict(os.environ), patch("django.core.wsgi.get_wsgi_application"), patch("waitress.serve") as serve:
            main(["--trusted-proxy", "127.0.0.1"])
            self.assertEqual(serve.call_args.kwargs["trusted_proxy_headers"], {"x-forwarded-for", "x-forwarded-proto"})
            self.assertEqual(serve.call_args.kwargs["trusted_proxy_count"], 1)
        for arguments in (["--trusted-proxy", "*"], ["--port", "0"], ["--port", "65536"], ["--threads", "-1"]):
            with self.subTest(arguments=arguments), patch("sys.stderr", new=StringIO()), self.assertRaises(SystemExit):
                main(arguments)


class SQLiteBackupTests(SimpleTestCase):
    def test_backup_captures_committed_wal_data_and_restores_into_new_file(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "catalog.sqlite3"
            target = Path(directory) / "backups/catalog.sqlite3"
            with closing(sqlite3.connect(source)) as writer:
                writer.execute("PRAGMA journal_mode=WAL")
                writer.execute("CREATE TABLE observations (price INTEGER)")
                writer.execute("INSERT INTO observations VALUES (350)")
                writer.commit()
                with patch.dict(connections["default"].settings_dict, {"ENGINE": "django.db.backends.sqlite3", "NAME": source}):
                    call_command("backup_sqlite", str(target), stdout=StringIO())
                with closing(sqlite3.connect(target)) as restored:
                    self.assertEqual(restored.execute("SELECT price FROM observations").fetchall(), [(350,)])
                    self.assertEqual(restored.execute("PRAGMA quick_check").fetchall(), [("ok",)])
                self.assertEqual(writer.execute("SELECT COUNT(*) FROM observations").fetchone(), (1,))

    def test_backup_rejects_existing_destination_and_source_path(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "catalog.sqlite3"
            target = Path(directory) / "existing.sqlite3"
            source.write_bytes(b"original source")
            target.write_bytes(b"original backup")
            with patch.dict(connections["default"].settings_dict, {"ENGINE": "django.db.backends.sqlite3", "NAME": source}):
                for output in (target, source):
                    with self.subTest(output=output), self.assertRaises(CommandError):
                        call_command("backup_sqlite", str(output))
            self.assertEqual(target.read_bytes(), b"original backup")
            self.assertEqual(source.read_bytes(), b"original source")

    def test_backup_rejects_non_sqlite_missing_and_memory_databases(self):
        for engine, name in (("django.db.backends.postgresql", "daamradar"), ("django.db.backends.sqlite3", ":memory:"),
                             ("django.db.backends.sqlite3", "/missing/database.sqlite3")):
            with self.subTest(engine=engine, name=name), TemporaryDirectory() as directory:
                output = Path(directory) / "backup.sqlite3"
                with patch.dict(connections["default"].settings_dict, {"ENGINE": engine, "NAME": name}), self.assertRaises(CommandError):
                    call_command("backup_sqlite", str(output))
                self.assertFalse(output.exists())

    def test_failed_backup_removes_only_its_new_output(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "corrupt.sqlite3"
            output = Path(directory) / "backup.sqlite3"
            source.write_bytes(b"not a database")
            with patch.dict(connections["default"].settings_dict, {"ENGINE": "django.db.backends.sqlite3", "NAME": source}), self.assertRaises(CommandError):
                call_command("backup_sqlite", str(output))
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), b"not a database")
