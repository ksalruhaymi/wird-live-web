from .base import *
import os

DEBUG = False

_raw_hosts = os.getenv(
    "ALLOWED_HOSTS",
    "wird.me,www.wird.me,187.124.177.246,localhost,127.0.0.1"
)
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]

_raw_csrf = os.getenv("CSRF_TRUSTED_ORIGINS", "")
CSRF_TRUSTED_ORIGINS = [h.strip() for h in _raw_csrf.split(",") if h.strip()]

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

AXES_ENABLED = True
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "img-src": ("'self'", "data:", "https:", "blob:"),
        "script-src": ("'self'", "https:", "'unsafe-inline'"),
        "style-src": ("'self'", "'unsafe-inline'", "https:"),
        "connect-src": ("'self'", "https:", "blob:"),
        "font-src": ("'self'", "data:", "https:"),
        "media-src": ("'self'", "blob:", "data:", "https:"),
    }
}