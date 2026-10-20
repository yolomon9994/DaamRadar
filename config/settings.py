import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"true", "1", "yes"}

DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY before disabling DEBUG.")
    # Ephemeral local secret; never shared with a production environment.
    import secrets
    SECRET_KEY = secrets.token_urlsafe(50)
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [h.strip() for h in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if h.strip()]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework", "catalog",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"],
              "APP_DIRS": True, "OPTIONS": {"context_processors": [
                  "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
                  "django.contrib.messages.context_processors.messages",
              ]}}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASES = {"default": dj_database_url.parse(os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=60)}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer", "rest_framework.renderers.BrowsableAPIRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "120/min"},
}
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT")
SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES")
CSRF_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SCRAPING_ENABLED = env_bool("SCRAPING_ENABLED")
SCRAPER_CONTACT = os.getenv("SCRAPER_CONTACT", "")
SCRAPER_DELAY_SECONDS = max(5, float(os.getenv("SCRAPER_DELAY_SECONDS", "5")))
SCRAPER_CONNECT_TIMEOUT = min(30, max(1, float(os.getenv("SCRAPER_CONNECT_TIMEOUT", "10"))))
SCRAPER_READ_TIMEOUT = min(30, max(1, float(os.getenv("SCRAPER_READ_TIMEOUT", "20"))))
# At most one additional attempt for timeout exceptions only, never HTTP errors.
SCRAPER_TIMEOUT_RETRIES = min(1, max(0, int(os.getenv("SCRAPER_TIMEOUT_RETRIES", "1"))))
SCRAPER_RETRY_DELAY_SECONDS = min(30, max(5, float(os.getenv("SCRAPER_RETRY_DELAY_SECONDS", "10"))))
PRICE_STALE_HOURS = int(os.getenv("PRICE_STALE_HOURS", "48"))
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "loggers": {"catalog": {"handlers": ["console"], "level": "INFO"}}}
