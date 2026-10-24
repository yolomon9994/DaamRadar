"""Disposable CI configuration; never selects the development DATABASE_URL."""
import os
from pathlib import Path

import dj_database_url

from .settings import *  # noqa: F403


SECRET_KEY = "ci-only-public-key-never-use-for-a-deployed-application"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
CSRF_TRUSTED_ORIGINS = []
DATABASES = {"default": dj_database_url.parse(os.environ.get("CI_DATABASE_URL") or "sqlite:///:memory:")}
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SCRAPING_ENABLED = False
SCRAPER_CONTACT = "ci@example.invalid"
PRICE_STALE_HOURS = 48
STATIC_ROOT = Path(os.environ.get("CI_STATIC_ROOT") or BASE_DIR / "staticfiles")  # noqa: F405
TEST_RUNNER = "config.test_runner.OfflineDiscoverRunner"
