import json

from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect

from ..models import AudioListenEvent


VALID_AUDIO_EVENTS = {
    AudioListenEvent.EVENT_PLAY,
    AudioListenEvent.EVENT_PAUSE,
    AudioListenEvent.EVENT_ENDED,
    AudioListenEvent.EVENT_PROGRESS_50,
}


def _to_int(value, default=None):
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default=0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _client_ip(request):
    cf_ip = request.META.get("HTTP_CF_CONNECTING_IP")
    if cf_ip:
        return cf_ip

    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


@require_POST
@csrf_protect
def record_audio_listen_event(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "invalid_json"}, status=400)

    event_type = str(payload.get("event_type") or "").strip()
    if event_type not in VALID_AUDIO_EVENTS:
        return JsonResponse({"success": False, "error": "invalid_event_type"}, status=400)

    if not request.session.session_key:
        request.session.save()

    duration = max(_to_float(payload.get("duration"), 0), 0)
    current_time = max(_to_float(payload.get("current_time"), 0), 0)

    percent = _to_int(payload.get("percent"), 0) or 0
    if percent < 0:
        percent = 0
    if percent > 100:
        percent = 100

    AudioListenEvent.objects.create(
        user=request.user if request.user.is_authenticated else None,
        session_key=request.session.session_key or "",
        mushaf_key=str(payload.get("mushaf_key") or "")[:40],
        qari_code=str(payload.get("qari_code") or "")[:120],
        surah_number=_to_int(payload.get("surah_number")),
        ayah_number=_to_int(payload.get("ayah_number")),
        page_number=_to_int(payload.get("page_number")),
        event_type=event_type,
        current_time=current_time,
        duration=duration,
        percent=percent,
        audio_src=str(payload.get("audio_src") or "")[:2000],
        ip_address=_client_ip(request),
        country=str(request.META.get("HTTP_CF_IPCOUNTRY") or "")[:2],
        user_agent=str(request.META.get("HTTP_USER_AGENT") or "")[:1000],
    )

    return JsonResponse({"success": True})
