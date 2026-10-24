import json
import os
import subprocess
import sys
from unittest.mock import patch

import requests
from django.test import SimpleTestCase
from django.test.runner import DiscoverRunner

from config.test_runner import OfflineDiscoverRunner


class CIConfigurationTests(SimpleTestCase):
    def test_ci_database_is_isolated_from_development_configuration(self):
        code = "from config import ci; import json; print(json.dumps({'engine': ci.DATABASES['default']['ENGINE'], 'name': ci.DATABASES['default']['NAME'], 'scraping': ci.SCRAPING_ENABLED, 'runner': ci.TEST_RUNNER}))"
        for ci_url, engine, name in [("", "django.db.backends.sqlite3", ":memory:"),
                                     ("postgresql://ci:ci@127.0.0.1:55439/daamradar_ci", "django.db.backends.postgresql", "daamradar_ci")]:
            environment = {**os.environ, "DJANGO_DEBUG": "true", "DATABASE_URL": "postgresql://unused:unused@production.invalid/never_connect",
                           "CI_DATABASE_URL": ci_url, "SCRAPING_ENABLED": "true"}
            with self.subTest(engine=engine):
                result = subprocess.run([sys.executable, "-c", code], env=environment, check=True,
                                        capture_output=True, text=True, timeout=15)
                data = json.loads(result.stdout)
                self.assertEqual((data["engine"], data["name"]), (engine, name))
                self.assertFalse(data["scraping"])
                self.assertEqual(data["runner"], "config.test_runner.OfflineDiscoverRunner")

    def test_ci_runner_rejects_real_http_before_transport(self):
        original_send = requests.sessions.Session.send

        def exercise_guard(*args, **kwargs):
            with patch("requests.adapters.HTTPAdapter.send") as transport:
                with self.assertRaisesMessage(AssertionError, "Unmocked HTTP is disabled"):
                    requests.get("https://retailer.invalid/product", timeout=1)
                transport.assert_not_called()
            # Normal fixture mocks still work inside the guard.
            with patch("requests.Session.get", return_value="saved fixture"):
                self.assertEqual(requests.Session().get("https://retailer.invalid/product"), "saved fixture")
            return 0

        with patch.object(DiscoverRunner, "run_tests", side_effect=exercise_guard):
            self.assertEqual(OfflineDiscoverRunner().run_tests([]), 0)
        self.assertIs(requests.sessions.Session.send, original_send)

    def test_ci_runner_restores_http_after_failure(self):
        original_send = requests.sessions.Session.send
        with patch.object(DiscoverRunner, "run_tests", side_effect=RuntimeError("test setup failed")):
            with self.assertRaisesMessage(RuntimeError, "test setup failed"):
                OfflineDiscoverRunner().run_tests([])
        self.assertIs(requests.sessions.Session.send, original_send)
