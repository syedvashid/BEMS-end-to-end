"""BEMS settings. Secrets and environment values come from backend/.env only."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and (value is None or value == ""):
        raise ImproperlyConfigured(f"Environment variable {name} is required (see backend/.env.example).")
    return value


def env_bool(name, default=False):
    return str(os.environ.get(name, str(default))).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("DJANGO_SECRET_KEY", required=True)
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

# --- DEV ONLY: acting-user header. The project refuses to start if enabled without DEBUG. ---
BEMS_DEV_AUTH = env_bool("BEMS_DEV_AUTH", False)
if BEMS_DEV_AUTH and not DEBUG:
    raise ImproperlyConfigured("BEMS_DEV_AUTH=true is only allowed with DJANGO_DEBUG=true. Refusing to start.")

INSTALLED_APPS = [
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.foundation",
    "apps.masters",
    "apps.documents",
]

MIDDLEWARE = [
    "apps.core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
}]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", required=True),
        "USER": env("DB_USER", required=True),
        "PASSWORD": env("DB_PASSWORD", required=True),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5433"),
        "CONN_MAX_AGE": 0,
        # NOTE: no ATOMIC_REQUESTS. Audited writes use an explicit transaction.atomic()
        # so an ACCESS_DENIED audit row is not rolled back by the 403 response.
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 1_000_000


# --- Documents (Phase 3) ---
BEMS_STORAGE_ROOT = env("BEMS_STORAGE_ROOT", "")   # absolute path OUTSIDE the project folder
BEMS_UPLOAD_MAX_MB = int(env("BEMS_UPLOAD_MAX_MB", "20"))
BEMS_DOWNLOAD_LINK_TTL_SECONDS = int(env("BEMS_DOWNLOAD_LINK_TTL_SECONDS", "120"))

REST_FRAMEWORK = {
    # DEV ONLY authentication; the future real auth replaces this one line + dev_auth.py.
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.foundation.dev_auth.DevHeaderAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["apps.foundation.permissions.BemsPermission"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.errors.exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "UNAUTHENTICATED_USER": None,   # django.contrib.auth is not installed
    "UNAUTHENTICATED_TOKEN": None,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "BEMS API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}