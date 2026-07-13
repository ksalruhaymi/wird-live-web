from functools import wraps

from django.conf import settings
from django.http import JsonResponse


def _extract_api_key(request) -> str | None:
    return request.headers.get("X-API-KEY") or request.GET.get("api_key")


def _is_valid_api_key(key: str | None) -> bool:
    if not key:
        return False
    valid_keys = getattr(settings, "QURAN_API_KEYS", [])
    return key in valid_keys


def allow_public_analytics_ingest(request) -> bool:
    if _is_valid_api_key(_extract_api_key(request)):
        return True
    return getattr(settings, "ALLOW_PUBLIC_ANALYTICS_INGEST", True)
