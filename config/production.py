"""Explicit production profile; HTTPS terminates at a configured reverse proxy."""
import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403


if DEBUG:  # noqa: F405
    raise ImproperlyConfigured("Set DJANGO_DEBUG=false to use production settings.")
if not os.getenv("DJANGO_ALLOWED_HOSTS", "").strip() or "*" in ALLOWED_HOSTS:  # noqa: F405
    raise ImproperlyConfigured("Production requires explicit DJANGO_ALLOWED_HOSTS without a wildcard.")

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)  # noqa: F405
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)  # noqa: F405
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
if SECURE_HSTS_SECONDS < 0:
    raise ImproperlyConfigured("DJANGO_SECURE_HSTS_SECONDS must be nonnegative.")
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS")  # noqa: F405
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD")  # noqa: F405
# Waitress validates the configured proxy and updates wsgi.url_scheme itself.
# Do not additionally trust a raw client-controlled proxy header in Django.
SECURE_PROXY_SSL_HEADER = None
if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":  # noqa: F405
    DATABASES["default"].setdefault("OPTIONS", {}).setdefault("connect_timeout", 5)  # noqa: F405
