from functools import wraps

from django.conf import settings
from django.http import JsonResponse


def require_api_key(view_func):
    """Protect API endpoints with X-API-KEY (settings.QURAN_API_KEYS)."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        key = request.headers.get("X-API-KEY") or request.GET.get("api_key")
        valid_keys = getattr(settings, "QURAN_API_KEYS", [])
        if not key or key not in valid_keys:
            return JsonResponse(
                {"detail": "Invalid or missing API key."},
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return _wrapped
