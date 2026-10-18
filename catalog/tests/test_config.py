import os
import subprocess
import sys

from django.test import SimpleTestCase


class DatabaseConfigurationTests(SimpleTestCase):
    def test_empty_database_url_uses_sqlite_and_postgres_url_parses(self):
        # A clean settings import catches .env defaults without mutating Django's
        # global test connection or making a PostgreSQL network connection.
        for url, engine in [("", "django.db.backends.sqlite3"),
                            ("postgresql://example:example@localhost:5432/daamradar", "django.db.backends.postgresql")]:
            with self.subTest(engine=engine):
                environment = {**os.environ, "DATABASE_URL": url, "DJANGO_DEBUG": "true"}
                result = subprocess.run([sys.executable, "-c", "from config.settings import DATABASES; print(DATABASES['default']['ENGINE'])"],
                    capture_output=True, text=True, env=environment, check=True, timeout=15)
                self.assertEqual(result.stdout.strip(), engine)
