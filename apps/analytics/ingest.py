import hashlib
import re
from datetime import timedelta

from django.db.models import F
from django.http import JsonResponse
from django.utils import timezone

from .errors_analytics import ERROR_EVENT_TYPES, sanitize_error_payload
from .models import AnalyticsVisitor, InteractionEvent

MOBILE_PLATFORMS = {"android", "ios"}
MAX_DEVICE_ID_LENGTH = 64
MAX_BATCH_SIZE = 40
MAX_BODY_BYTES = 64_000
MEDIA_HOST_HINTS = (
    "live.wird.me",
    "r2.cloudflarestorage.com",
)

LIVE_EVENT_MAP = {
    "screen_view": InteractionEvent.EVENT_SCREEN_VIEW,
    "call_requested": InteractionEvent.EVENT_MOBILE_EVENT,
    "call_waiting": InteractionEvent.EVENT_MOBILE_EVENT,
    "call_accepted": InteractionEvent.EVENT_MOBILE_EVENT,
    "call_rejected": InteractionEvent.EVENT_MOBILE_EVENT,
    "call_cancelled": InteractionEvent.EVENT_MOBILE_EVENT,
    "call_ended": InteractionEvent.EVENT_MOBILE_EVENT,
    "agora_joined": InteractionEvent.EVENT_MOBILE_EVENT,
    "agora_join_failed": InteractionEvent.EVENT_AUDIO_ERROR,
    "demo_call_started": InteractionEvent.EVENT_MOBILE_EVENT,
    "demo_call_ended": InteractionEvent.EVENT_MOBILE_EVENT,
    "recording_play_started": InteractionEvent.EVENT_MEDIA_PLAY,
    "recording_play_completed": InteractionEvent.EVENT_MEDIA_PLAY,
    "recording_play_failed": InteractionEvent.EVENT_MEDIA_ERROR,
    "post_call_rating_shown": InteractionEvent.EVENT_MOBILE_EVENT,
    "post_call_rating_submitted": InteractionEvent.EVENT_MOBILE_EVENT,
    "subscription_call_blocked": InteractionEvent.EVENT_MOBILE_EVENT,
    "teacher_selected": InteractionEvent.EVENT_MOBILE_EVENT,
    "media_play": InteractionEvent.EVENT_MEDIA_PLAY,
    "media_error": InteractionEvent.EVENT_MEDIA_ERROR,
    "client_error": InteractionEvent.EVENT_CLIENT_ERROR,
    "audio_error": InteractionEvent.EVENT_AUDIO_ERROR,
    "api_error": InteractionEvent.EVENT_API_ERROR,
}


def normalize_platform(value):
    platform = str(value or "").strip().lower()
    return platform if platform in MOBILE_PLATFORMS else ""


def sanitize_device_id(value):
    return re.sub(r"[^a-zA-Z0-9:_-]", "", str(value or ""))[:MAX_DEVICE_ID_LENGTH]


def mobile_session_key(device_id):
    digest = hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:48]
    return f"m:{digest}"


def is_r2_media_url(url):
    text = str(url or "").lower()
    if not text:
        return False
    return any(hint in text for hint in MEDIA_HOST_HINTS)


def resolve_visitor(request, platform, device_id, app_version):
    clean_device_id = sanitize_device_id(device_id)
    if not clean_device_id:
        return None
    ip_address = _client_ip(request)
    session_key = mobile_session_key(clean_device_id)
    visitor, created = AnalyticsVisitor.objects.get_or_create(
        session_key=session_key,
        defaults={
            "ip_address": ip_address,
            "device_type": "mobile",
            "os_name": "Android" if platform == "android" else "iOS",
            "client_source": platform,
            "device_id": clean_device_id,
            "app_version": str(app_version or "")[:32],
            "last_language": (request.headers.get("Accept-Language") or "")[:16],
            "visits_count": 1,
        },
    )
    if not created:
        AnalyticsVisitor.objects.filter(pk=visitor.pk).update(
            visits_count=F("visits_count") + 1,
            ip_address=ip_address,
            client_source=platform,
            device_id=clean_device_id,
            app_version=str(app_version or "")[:32],
            last_language=(request.headers.get("Accept-Language") or "")[:16],
        )
    return visitor


def enrich_payload(payload):
    payload = dict(payload or {})
    media_url = payload.get("media_url") or payload.get("url") or payload.get("src") or ""
    if media_url and is_r2_media_url(media_url):
        payload["media_source"] = "r2"
        payload["media_url"] = str(media_url)[:500]
        try:
            from urllib.parse import urlparse

            parsed = urlparse(str(media_url))
            payload["media_path"] = (parsed.path or "").lstrip("/")[:300]
        except ValueError:
            pass
    return payload


def create_event(*, visitor, event_type, payload, path, source_platform):
    allowed = {choice[0] for choice in InteractionEvent.EVENT_CHOICES}
    if event_type not in allowed:
        return None

    payload = enrich_payload(payload)
    payload["platform"] = source_platform
    payload["product"] = "wird_live"

    if event_type in ERROR_EVENT_TYPES:
        payload = sanitize_error_payload(payload)
        if visitor:
            recent = InteractionEvent.objects.filter(
                visitor=visitor,
                event_type__in=ERROR_EVENT_TYPES,
                created_at__gte=timezone.now() - timedelta(minutes=1),
            ).count()
            if recent >= 25:
                return None

    InteractionEvent.objects.create(
        visitor=visitor,
        event_type=event_type,
        source_platform=source_platform,
        path=str(path or "/mobile")[:255],
        page_number=_as_int(payload.get("page") or payload.get("page_number")),
        surah_number=_as_int(payload.get("surah") or payload.get("surah_number")),
        ayah_number=_as_int(payload.get("ayah") or payload.get("ayah_number")),
        qari=str(payload.get("qari") or payload.get("reader") or "")[:100],
        duration_seconds=_as_int(payload.get("duration") or payload.get("duration_seconds")),
        payload=payload,
    )
    return True


def ingest_item(visitor, platform, item):
    if not isinstance(item, dict):
        return False

    direct_type = str(item.get("type") or "").strip()
    allowed = {choice[0] for choice in InteractionEvent.EVENT_CHOICES}
    if direct_type:
        if direct_type not in allowed:
            return False
        payload = item.get("data") or {}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        create_event(
            visitor=visitor,
            event_type=direct_type,
            payload=payload,
            path=item.get("path") or "/mobile",
            source_platform=platform,
        )
        return True

    name = str(item.get("name") or item.get("event") or "").strip()
    event_type = LIVE_EVENT_MAP.get(name)
    if not event_type:
        return False

    parameters = item.get("parameters") or item.get("data") or {}
    if not isinstance(parameters, dict):
        parameters = {"value": parameters}
    parameters["firebase_event"] = name
    path = item.get("path") or parameters.get("screen_name") or f"/mobile/{name}"
    if event_type == InteractionEvent.EVENT_AUDIO_ERROR and name.endswith("_failed"):
        parameters.setdefault("message", str(parameters.get("reason") or name)[:300])

    create_event(
        visitor=visitor,
        event_type=event_type,
        payload=parameters,
        path=path,
        source_platform=platform,
    )
    return True


def ingest_mobile_payload(request, data):
    platform = normalize_platform(data.get("platform"))
    if not platform:
        return JsonResponse({"detail": "platform must be android or ios."}, status=422)

    device_id = sanitize_device_id(data.get("device_id"))
    if not device_id:
        return JsonResponse({"detail": "device_id is required."}, status=422)

    app_version = str(data.get("app_version") or data.get("app_build") or "")[:32]
    events = data.get("events")
    if events is None:
        events = [data.get("event") or data]
    if not isinstance(events, list) or not events:
        return JsonResponse({"detail": "events must be a non-empty list."}, status=422)
    if len(events) > MAX_BATCH_SIZE:
        return JsonResponse({"detail": f"max {MAX_BATCH_SIZE} events per request."}, status=413)

    visitor = resolve_visitor(request, platform, device_id, app_version)
    accepted = sum(1 for item in events if ingest_item(visitor, platform, item))
    return JsonResponse({"status": "ok", "accepted": accepted})


def _as_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _client_ip(request):
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR")
