"""
Django base settings for core project.

Shared settings between dev and prod.
"""

from pathlib import Path
import os

import dj_database_url
from dotenv import load_dotenv


# ------------------------------------------------------------------------------
# Core paths and environment
# ------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

app_env = os.getenv("APP_ENV", "dev").lower()

if app_env == "prod":
    env_path = BASE_DIR / ".env.prod"
else:
    env_path = BASE_DIR / ".env.dev"

load_dotenv(env_path)


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("true", "1", "yes", "on")


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.getenv(name, "")
    if not value:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


# ------------------------------------------------------------------------------
# Security
# ------------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set in environment variables.")

DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    default=[
        "wird.me",
        "www.wird.me",
        "127.0.0.1",
        "localhost",
        "0.0.0.0",
        "10.0.2.2",
    ],
)


# ------------------------------------------------------------------------------
# Authentication
# ------------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS: list[str] = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]


# ------------------------------------------------------------------------------
# Applications
# ------------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    'django.contrib.sitemaps',
]

LOCAL_APPS = [
    "config",
    "core",
    "identity.accounts",
    "identity.rbac",
    "dashboard",
    "web",
    "apps.notification",
    "apps.messaging",
    "apps.communication",
    "apps.contact",
    "apps.subscription",
    "apps.tutoring",
    "apps.push",
    "apps.calls",
    "apps.appointments",
    "apps.mobile",
    "apps.analytics",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "axes",
    "csp",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS + THIRD_PARTY_APPS


# ------------------------------------------------------------------------------
# Middleware
# ------------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.mobile.middleware.MobileAppVersionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.force_logout_inactive.ForceLogoutInactiveUserMiddleware",
    "core.middleware.single_active_session.SingleActiveSessionMiddleware",
    "core.middleware.visitor_counter.VisitorCounterMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]


# ------------------------------------------------------------------------------
# URLs / WSGI / ASGI
# ------------------------------------------------------------------------------
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ------------------------------------------------------------------------------
# Templates
# ------------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.media",
                "apps.notification.context_processors.notifications_counts",
                "apps.notification.context_processors.messages_counts",
            ],
        },
    },
]


# ------------------------------------------------------------------------------
# Database
# ------------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=False,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB", "quran"),
            "USER": os.getenv("POSTGRES_USER", "postgres"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "localhost"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
        }
    }


# ------------------------------------------------------------------------------
# Password validation
# ------------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ------------------------------------------------------------------------------
# Languages and localization
# ------------------------------------------------------------------------------
LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGES = [
    ("ar", "العربية"),
    ("en", "English"),
    ("de", "Deutsch"),
    ("es", "Español"),
    ("hi", "हिन्दी"),
    ("ur", "اردو"),
    ("fa", "فارسی"),
    ("id", "Indonesia"),
    ("fr", "Français"),
    ("ja", "日本語"),
    ("zh", "中文"),
    ("nl", "Nederlands"),
    ("fil", "Filipino"),
    ("vi", "Tiếng Việt"),
    ("as", "অসমীয়া"),
    ("si", "සිංහල"),
    ("so", "Soomaali"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]


# ------------------------------------------------------------------------------
# Static / Media
# ------------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_SOURCE = os.getenv("MEDIA_SOURCE", "local").strip().lower()
if MEDIA_SOURCE not in ("local", "server"):
    MEDIA_SOURCE = "local"

LOCAL_MEDIA_URL = os.getenv("LOCAL_MEDIA_URL", "/media/").strip() or "/media/"
SERVER_MEDIA_URL = os.getenv("SERVER_MEDIA_URL", "https://wird.me/media/").strip()

MEDIA_URL = SERVER_MEDIA_URL if MEDIA_SOURCE == "server" else LOCAL_MEDIA_URL
MEDIA_ROOT = BASE_DIR.parent / "media"

AUDIO_CATALOG_URL = os.getenv("AUDIO_CATALOG_URL", "").strip()
AUDIO_CATALOG_API_KEY = os.getenv("AUDIO_CATALOG_API_KEY", "").strip()
AUDIO_CATALOG_TIMEOUT = int(os.getenv("AUDIO_CATALOG_TIMEOUT", "5"))
AUDIO_CATALOG_CACHE_SECONDS = int(os.getenv("AUDIO_CATALOG_CACHE_SECONDS", "60"))

# ------------------------------------------------------------------------------
# Default primary key field type
# ------------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ------------------------------------------------------------------------------
# Quran API keys
# ------------------------------------------------------------------------------
QURAN_API_KEYS = env_list("QURAN_API_KEYS", default=[])
ALLOW_PUBLIC_ANALYTICS_INGEST = env_bool("ALLOW_PUBLIC_ANALYTICS_INGEST", True)


# ------------------------------------------------------------------------------
# Email Hostinger
# ------------------------------------------------------------------------------
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.hostinger.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))

EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", True)

EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "20"))

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
CONTACT_RECIPIENT_EMAIL = os.getenv("CONTACT_RECIPIENT_EMAIL", DEFAULT_FROM_EMAIL)



# ------------------------------------------------------------------------------
# Telegram Bot
# ------------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_CHANNEL_USERNAME = os.environ.get("TELEGRAM_CHANNEL_USERNAME", "")
# ------------------------------------------------------------------------------
# WhatsApp
# ------------------------------------------------------------------------------
WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "https://graph.facebook.com/v19.0")
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ENABLED = env_bool("WHATSAPP_ENABLED", False)


# ------------------------------------------------------------------------------
# SMS
# ------------------------------------------------------------------------------
SMS_API_URL = os.getenv("SMS_API_URL", "")
SMS_TOKEN = os.getenv("SMS_TOKEN", "")
SMS_TIMEOUT = int(os.getenv("SMS_TIMEOUT", "10"))


# ------------------------------------------------------------------------------
# Axes
# ------------------------------------------------------------------------------
AXES_ENABLED = env_bool("AXES_ENABLED", True)
AXES_FAILURE_LIMIT = int(os.getenv("AXES_FAILURE_LIMIT", "5"))
AXES_COOLOFF_TIME = int(os.getenv("AXES_COOLOFF_TIME", "1"))
AXES_RESET_ON_SUCCESS = True


# ------------------------------------------------------------------------------
# Firebase / FCM
# ------------------------------------------------------------------------------
FIREBASE_CREDENTIALS_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "")

# ------------------------------------------------------------------------------
# Apple PushKit VoIP (incoming calls on locked / killed iOS)
# Same .p8 Auth Key can be reused if APNs is enabled for the key.
# Never commit key files — path/env only.
# ------------------------------------------------------------------------------
APNS_TEAM_ID = (os.getenv("APNS_TEAM_ID", "") or "").strip()
APNS_KEY_ID = (os.getenv("APNS_KEY_ID", "") or os.getenv("APPLE_KEY_ID", "") or "").strip()
APNS_BUNDLE_ID = (
    os.getenv("APNS_BUNDLE_ID", "") or os.getenv("APPLE_BUNDLE_ID", "com.kslabs.wirdlive") or ""
).strip()
APNS_PRIVATE_KEY_PATH = (
    os.getenv("APNS_PRIVATE_KEY_PATH", "") or os.getenv("APPLE_PRIVATE_KEY_PATH", "") or ""
).strip()
APNS_PRIVATE_KEY = (os.getenv("APNS_PRIVATE_KEY", "") or os.getenv("APPLE_PRIVATE_KEY", "") or "").strip()
APNS_USE_SANDBOX = env_bool(
    "APNS_USE_SANDBOX",
    app_env not in {"prod", "production"},
)


# ------------------------------------------------------------------------------
# Store billing verification (App Store / Google Play)
# ------------------------------------------------------------------------------
# STORE_BILLING_ENV must match mobile --dart-define=STORE_ENV (sandbox|production).
STORE_BILLING_ENV = (os.getenv("STORE_BILLING_ENV", "sandbox") or "sandbox").strip().lower()
APPLE_BUNDLE_ID = (os.getenv("APPLE_BUNDLE_ID", "com.kslabs.wirdlive") or "").strip()
APPLE_ISSUER_ID = (os.getenv("APPLE_ISSUER_ID", "") or "").strip()
APPLE_KEY_ID = (os.getenv("APPLE_KEY_ID", "") or "").strip()
APPLE_PRIVATE_KEY_PATH = (os.getenv("APPLE_PRIVATE_KEY_PATH", "") or "").strip()
APPLE_PRIVATE_KEY = (os.getenv("APPLE_PRIVATE_KEY", "") or "").strip()
GOOGLE_PLAY_PACKAGE_NAME = (
    os.getenv("GOOGLE_PLAY_PACKAGE_NAME", "com.kslabs.wirdlive") or ""
).strip()
GOOGLE_PLAY_SERVICE_ACCOUNT_PATH = (
    os.getenv("GOOGLE_PLAY_SERVICE_ACCOUNT_PATH", "") or ""
).strip()


# ------------------------------------------------------------------------------
# Voice / video calls (Agora)
# ------------------------------------------------------------------------------
APP_ENV = app_env
# Empty = auto (Agora when AGORA_* env vars are set; mock only in non-prod dev).
CALL_PROVIDER = (os.getenv("CALL_PROVIDER", "") or "").strip().lower()
AGORA_APP_ID = (os.getenv("AGORA_APP_ID", "") or "").strip()
AGORA_APP_CERTIFICATE = (os.getenv("AGORA_APP_CERTIFICATE", "") or "").strip()
CALL_TOKEN_TTL_SECONDS = int(os.getenv("CALL_TOKEN_TTL_SECONDS", "3600"))

# Agora Cloud Recording (REST; separate from RTC App ID credentials above)
AGORA_CUSTOMER_ID = (os.getenv("AGORA_CUSTOMER_ID", "") or "").strip()
AGORA_CUSTOMER_SECRET = (os.getenv("AGORA_CUSTOMER_SECRET", "") or "").strip()
AGORA_RECORDING_UID = int(os.getenv("AGORA_RECORDING_UID", "900000001") or "900000001")
AGORA_RECORDING_MODE = (os.getenv("AGORA_RECORDING_MODE", "mix") or "mix").strip().lower()
AGORA_RECORDING_RESOURCE_EXPIRED_HOUR = int(
    os.getenv("AGORA_RECORDING_RESOURCE_EXPIRED_HOUR", "24") or "24"
)
AGORA_RECORDING_STORAGE_VENDOR = int(os.getenv("AGORA_RECORDING_STORAGE_VENDOR", "0") or "0")
AGORA_RECORDING_STORAGE_REGION = int(os.getenv("AGORA_RECORDING_STORAGE_REGION", "0") or "0")
# Required for vendor 11 (S3-compatible, e.g. Cloudflare R2); passed as extensionParams.endpoint.
AGORA_RECORDING_STORAGE_ENDPOINT = (
    os.getenv("AGORA_RECORDING_STORAGE_ENDPOINT", "") or ""
).strip()
AGORA_RECORDING_STORAGE_BUCKET = (
    os.getenv("AGORA_RECORDING_STORAGE_BUCKET", "") or ""
).strip()
AGORA_RECORDING_STORAGE_ACCESS_KEY = (
    os.getenv("AGORA_RECORDING_STORAGE_ACCESS_KEY", "") or ""
).strip()
AGORA_RECORDING_STORAGE_SECRET_KEY = (
    os.getenv("AGORA_RECORDING_STORAGE_SECRET_KEY", "") or ""
).strip()
AGORA_RECORDING_FILE_PREFIX = (
    os.getenv("AGORA_RECORDING_FILE_PREFIX", "wird-live") or "wird-live"
).strip()
# Optional public base URL for recorded files (legacy DB rows only; not exposed to clients)
AGORA_RECORDING_PUBLIC_BASE_URL = (
    os.getenv("AGORA_RECORDING_PUBLIC_BASE_URL", "") or ""
).strip()
# Agora Notifications secret (Console → Project → Notifications).
# Used only for HMAC-SHA1 / HMAC-SHA256 signature verification of webhooks.
# Never accept query-string or plain-text token auth for this endpoint.
AGORA_WEBHOOK_SECRET = (os.getenv("AGORA_WEBHOOK_SECRET", "") or "").strip()
# Max allowed |now - notifyMs| skew for webhook replay protection (seconds).
AGORA_WEBHOOK_MAX_SKEW_SECONDS = int(
    os.getenv("AGORA_WEBHOOK_MAX_SKEW_SECONDS", "600") or "600"
)
# Presigned GET URL lifetime for private call recordings (seconds).
RECORDING_SIGNED_URL_EXPIRES_SECONDS = int(
    os.getenv("RECORDING_SIGNED_URL_EXPIRES_SECONDS", "600") or "600"
)

# ------------------------------------------------------------------------------
# Celery (shared: dev + prod). Broker via env; no secrets in code.
# Tasks do not require a result backend — omit unless you add result consumers.
# ------------------------------------------------------------------------------
CELERY_BROKER_URL = (
    os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0") or ""
).strip() or "redis://127.0.0.1:6379/0"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = int(
    os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "90") or "90"
)
CELERY_TASK_TIME_LIMIT = int(
    os.getenv("CELERY_TASK_TIME_LIMIT", "120") or "120"
)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
# Never leave retries unbounded at the app level; per-task max_retries apply.
CELERY_TASK_DEFAULT_RETRY_DELAY = 20
# Eager mode only when explicitly enabled (tests/local); never default in prod.
CELERY_TASK_ALWAYS_EAGER = (
    (os.getenv("CELERY_TASK_ALWAYS_EAGER", "") or "").strip().lower()
    in {"1", "true", "yes", "on"}
)
CELERY_TASK_EAGER_PROPAGATES = True
