# core/media_views.py
import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, JsonResponse


_PUBLIC_MEDIA_PREFIXES = ("images/", "mushaf/", "mushaf_full/", "audio/", "audio-surahs/")


def protected_media(request, path: str):
    """
    يُقدّم ملفات /media/ المحمية بعد التحقق من api_key.
    يقبل المفتاح من:
      - Header:        X-API-KEY
      - Query param:   ?api_key=...
    المسارات في _PUBLIC_MEDIA_PREFIXES لا تحتاج مفتاحاً.
    """
    # ── المسارات العامة لا تحتاج مفتاحاً ───────────────────────────────────
    is_public = any(path.startswith(prefix) for prefix in _PUBLIC_MEDIA_PREFIXES)

    if not is_public:
        # ── التحقق من المفتاح ────────────────────────────────────────────────
        key = request.headers.get("X-API-KEY") or request.GET.get("api_key")
        valid_keys = getattr(settings, "QURAN_API_KEYS", [])

        if not key or key not in valid_keys:
            return JsonResponse({"detail": "Invalid or missing API key."}, status=401)

    # ── إيجاد الملف ─────────────────────────────────────────────────────────
    file_path = Path(settings.MEDIA_ROOT) / path

    if not file_path.exists() or not file_path.is_file():
        return JsonResponse({"detail": "File not found."}, status=404)

    # منع path traversal
    try:
        file_path.resolve().relative_to(Path(settings.MEDIA_ROOT).resolve())
    except ValueError:
        return JsonResponse({"detail": "Forbidden."}, status=403)

    content_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(open(file_path, "rb"), content_type=content_type or "application/octet-stream")
