# apps/quran/api/auth.py

from functools import wraps

from django.conf import settings
from django.http import JsonResponse


def require_api_key(view_func):
    """
    Decorator to protect API endpoints with an API key.
    - Reads key from X-API-KEY header.
    - Optionally reads from ?api_key=... query param (for testing).
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        # 1) Read API key from header
        key = request.headers.get("X-API-KEY")

        # 2) Optional: allow ?api_key=... for quick testing
        if not key:
            key = request.GET.get("api_key")

        # 3) Valid keys from settings
        valid_keys = getattr(settings, "QURAN_API_KEYS", [])

        # 4) Check key
        if not key or key not in valid_keys:
            return JsonResponse(
                {"detail": "Invalid or missing API key."},
                status=401,
            )

        return view_func(request, *args, **kwargs)

    return _wrapped