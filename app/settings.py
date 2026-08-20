import os
import sys
from functools import partial
from pathlib import Path

from authlib.roles import allow_deny_globs
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from speckenv import env
from speckenv_django import (
    django_database_url,
    django_email_url,
    django_storage_url,
)


DEBUG = env("DEBUG", required=True)
TESTING = env("TESTING", default="test" in sys.argv)
SECURE_SSL_HOST = env("SECURE_SSL_HOST")
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", default=False)
ALLOWED_HOSTS = env("ALLOWED_HOSTS", required=True)
DEBUG_TOOLBAR = DEBUG and not TESTING

FORMS_URLFIELD_ASSUME_HTTPS = True

BASE_DIR = Path(__file__).resolve().parent.parent

# These values may be overridden using environment variables. ADMINS as is,
# DEFAULT_FROM_EMAIL and SERVER_EMAIL using EMAIL_URL
ADMINS = MANAGERS = env("ADMINS", default=[("FEINHEIT Developers", "dev@feinheit.ch")])
SERVER_EMAIL = DEFAULT_FROM_EMAIL = "no-reply@feinheit.ch"

DATABASES = {"default": django_database_url(env("DATABASE_URL", required=True))}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SECRET_KEY = env("SECRET_KEY", required=True)

TIME_ZONE = "Europe/Zurich"
LANGUAGE_CODE = "en"
LANGUAGES = (
    ("en", _("English")),
    ("de", _("German")),
    ("fr", _("French")),
    # ("it", _("Italian")),
)

USE_I18N = True
USE_TZ = True

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

STATIC_ROOT = BASE_DIR / "static"
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    # BASE_DIR / "frontend" / "static"
]

STORAGES = {
    "default": django_storage_url(
        env(
            "STORAGE_URL",
            default="file:./media/?base_url=/media/",
            warn=True,
        ),
        base_dir=BASE_DIR,
    ),
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}

MIDDLEWARE = [
    m
    for m in [
        "debug_toolbar.middleware.DebugToolbarMiddleware" if DEBUG_TOOLBAR else "",
        "canonical_domain.middleware.canonical_domain",
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.middleware.locale.LocaleMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]
    if m
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "app" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "builtins": [
                "form_rendering",
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "app.context_processors.site_context",
            ],
        },
    }
]

ROOT_URLCONF = "app.urls"
WSGI_APPLICATION = "wsgi.application"

LOCALE_PATHS = [BASE_DIR / "conf" / "locale"]

INSTALLED_APPS = [
    app
    for app in [
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "django.forms",
        "django.contrib.admin",
        "app",
        "accounts",
        "projects",
        "canonical_domain",
        "debug_toolbar" if DEBUG_TOOLBAR else "",
    ]
    if app
]

AUTH_USER_MODEL = "accounts.user"
AUTHENTICATION_BACKENDS = [
    "authlib.backends.PermissionsBackend",
    "authlib.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 16},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET")
MICROSOFT_CLIENT_ID = env("MICROSOFT_CLIENT_ID")
MICROSOFT_CLIENT_SECRET = env("MICROSOFT_CLIENT_SECRET")

if SENTRY_DSN := env("SENTRY_DSN"):  # pragma: no cover
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(dsn=SENTRY_DSN, integrations=[DjangoIntegration()])

if DEBUG:  # pragma: no cover
    INTERNAL_IPS = ["127.0.0.1"]

globals().update(
    django_email_url(env("EMAIL_URL", default="console:" if DEBUG else "smtp:"))
)

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

if SECURE_SSL_REDIRECT:  # pragma: no cover
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # SECURE_HSTS_SECONDS = 30 * 86400
    # SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
else:
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

STAFF_EMAIL_DOMAINS = env("STAFF_EMAIL_DOMAINS", default=["feinheit.ch", "406.ch"])
AUTHLIB_ROLES = {
    "default": {"title": _("default")},
    "manager": {
        "title": _("projects manager"),
        "callback": partial(
            allow_deny_globs,
            allow={
                "*.view_*",
                "projects.*",
            },
        ),
    },
}

LOGIN_URL = reverse_lazy("login")
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = reverse_lazy("login")

FORM_RENDERER = "form_rendering.FormRendering"

DEEPL_AUTH_KEY = env("DEEPL_AUTH_KEY")

CLI_API = "1"  # Bump this when changing the API in incompatible ways
