"""Agora Cloud Recording / Notifications webhook.

Configure the callback URL in Agora Console → Notifications.
Verification follows Agora's official HMAC signature scheme:
  - Agora-Signature     = HMAC-SHA1(secret, raw body) as hex
  - Agora-Signature-V2  = HMAC-SHA256(secret, raw body) as hex

See: https://docs.agora.io/en/cloud-recording/develop/receive-notifications
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.calls.cloud_recording.service import try_finalize_recording_files
from apps.calls.models import CallRecording

logger = logging.getLogger(__name__)

# Idempotency / replay window for seen noticeIds (seconds).
_SEEN_NOTICE_TTL_SECONDS = 60 * 60
_DEFAULT_MAX_SKEW_SECONDS = 10 * 60


def _redact(value: str, *, keep: int = 4) -> str:
    """Log-safe truncation; never emit the full secret or signature."""
    text = (value or "").strip()
    if not text:
        return "<empty>"
    if len(text) <= keep * 2:
        return f"<len={len(text)}>"
    return f"{text[:keep]}…<len={len(text)}>"


def _webhook_secret() -> str:
    return (getattr(settings, "AGORA_WEBHOOK_SECRET", "") or "").strip()


def _max_skew_seconds() -> int:
    raw = getattr(settings, "AGORA_WEBHOOK_MAX_SKEW_SECONDS", _DEFAULT_MAX_SKEW_SECONDS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_SKEW_SECONDS
    return max(60, value)


def _normalize_hex(signature: str) -> str:
    return (signature or "").strip().lower().removeprefix("sha1=").removeprefix(
        "sha256="
    )


def verify_agora_request_signature(
    *,
    secret: str,
    body: bytes,
    signature_sha1: str,
    signature_sha256: str = "",
) -> bool:
    """Return True if Agora-Signature and/or Agora-Signature-V2 match the body."""
    if not secret or body is None:
        return False

    secret_bytes = secret.encode("utf-8")

    sig_v1 = _normalize_hex(signature_sha1)
    if sig_v1:
        expected_v1 = hmac.new(secret_bytes, body, hashlib.sha1).hexdigest()
        if hmac.compare_digest(expected_v1, sig_v1):
            return True

    sig_v2 = _normalize_hex(signature_sha256)
    if sig_v2:
        expected_v2 = hmac.new(secret_bytes, body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected_v2, sig_v2):
            return True

    return False


def _extract_nested(payload: dict, *keys: str) -> str:
    """Read a string field from the root or nested ``payload`` object."""
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    for key in keys:
        for source in (payload, inner):
            value = source.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _event_timestamp_ms(payload: dict) -> int | None:
    """Prefer notifyMs (delivery time); fall back to payload.sendts."""
    for key in ("notifyMs", "notify_ms"):
        raw = payload.get(key)
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    for key in ("sendts", "sendTs", "timestamp"):
        raw = inner.get(key) if key in inner else payload.get(key)
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
    return None


def _is_replay_or_stale(payload: dict) -> tuple[bool, str]:
    """
    Replay / freshness checks.

    Returns (reject, reason). Duplicate noticeId is handled separately as
    idempotent success so Agora stops retrying.
    """
    ts_ms = _event_timestamp_ms(payload)
    if ts_ms is None:
        # Signature already verified; allow missing timestamp but log.
        return False, "missing_timestamp"

    now_ms = int(time.time() * 1000)
    skew_ms = abs(now_ms - ts_ms)
    max_skew_ms = _max_skew_seconds() * 1000
    if skew_ms > max_skew_ms:
        return True, "stale_or_future_timestamp"
    return False, "ok"


def _notice_cache_key(notice_id: str) -> str:
    return f"agora_webhook:notice:{notice_id}"


def _mark_notice_seen(notice_id: str) -> bool:
    """
    Atomically mark noticeId as seen.

    Returns True if this is the first time we see it (should process).
    """
    if not notice_id:
        return True
    key = _notice_cache_key(notice_id)
    # cache.add is atomic: True only when the key did not exist.
    return bool(cache.add(key, "1", timeout=_SEEN_NOTICE_TTL_SECONDS))


@csrf_exempt
@require_POST
def agora_recording_webhook(request):
    secret = _webhook_secret()
    if not secret:
        logger.error("agora_webhook_rejected reason=secret_not_configured")
        return JsonResponse(
            {"success": False, "message": "webhook_not_configured"},
            status=503,
        )

    body: bytes = request.body or b""
    signature_v1 = (
        request.headers.get("Agora-Signature")
        or request.headers.get("agora-signature")
        or ""
    )
    signature_v2 = (
        request.headers.get("Agora-Signature-V2")
        or request.headers.get("agora-signature-v2")
        or ""
    )

    # Never accept query-token / Bearer / plain-secret shortcuts.
    if request.GET.get("token") or request.GET.get("secret"):
        logger.warning(
            "agora_webhook_rejected reason=query_auth_not_allowed has_sig_v1=%s has_sig_v2=%s",
            bool(signature_v1),
            bool(signature_v2),
        )
        return JsonResponse({"success": False, "message": "unauthorized"}, status=401)

    if not signature_v1 and not signature_v2:
        logger.warning("agora_webhook_rejected reason=missing_signature")
        return JsonResponse({"success": False, "message": "unauthorized"}, status=401)

    if not verify_agora_request_signature(
        secret=secret,
        body=body,
        signature_sha1=signature_v1,
        signature_sha256=signature_v2,
    ):
        logger.warning(
            "agora_webhook_rejected reason=bad_signature sig_v1=%s sig_v2=%s body_len=%s",
            _redact(signature_v1),
            _redact(signature_v2),
            len(body),
        )
        return JsonResponse({"success": False, "message": "unauthorized"}, status=401)

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("agora_webhook_rejected reason=invalid_json")
        return JsonResponse({"success": False, "message": "invalid_json"}, status=400)

    reject_stale, stale_reason = _is_replay_or_stale(payload)
    if reject_stale:
        logger.warning(
            "agora_webhook_rejected reason=%s notice=%s",
            stale_reason,
            _redact(_extract_nested(payload, "noticeId", "notice_id"), keep=6),
        )
        return JsonResponse({"success": False, "message": "stale_event"}, status=401)

    notice_id = _extract_nested(payload, "noticeId", "notice_id")
    if notice_id and not _mark_notice_seen(notice_id):
        logger.info(
            "agora_webhook_duplicate notice=%s",
            _redact(notice_id, keep=6),
        )
        return JsonResponse(
            {"success": True, "duplicate": True, "matched": False},
            status=200,
        )

    event = (
        payload.get("eventType")
        or payload.get("event")
        or ""
    )
    sid = _extract_nested(payload, "sid", "SID")
    resource_id = _extract_nested(payload, "resourceId", "resource_id")

    rec = None
    if sid:
        rec = (
            CallRecording.objects.filter(agora_sid=sid)
            .select_related("call_session")
            .first()
        )
    if rec is None and resource_id:
        rec = (
            CallRecording.objects.filter(agora_resource_id=resource_id)
            .select_related("call_session")
            .first()
        )

    if rec is None:
        logger.info(
            "agora_webhook_unmatched event=%s has_sid=%s has_resource=%s notice=%s",
            str(event)[:64],
            bool(sid),
            bool(resource_id),
            _redact(notice_id, keep=6) if notice_id else "<none>",
        )
        return JsonResponse({"success": True, "matched": False})

    if rec.is_terminal and rec.is_playable:
        return JsonResponse(
            {
                "success": True,
                "matched": True,
                "recording_status": rec.recording_status,
            }
        )

    try:
        try_finalize_recording_files(rec, allow_expire=True)
        rec.refresh_from_db()
    except Exception:
        logger.exception(
            "agora_webhook_finalize_failed recording_id=%s", rec.id
        )

    rec.last_query_at = timezone.now()
    rec.save(update_fields=["last_query_at"])

    return JsonResponse(
        {
            "success": True,
            "matched": True,
            "recording_id": rec.id,
            "call_id": rec.call_session_id,
            "recording_status": rec.recording_status,
            "is_playable": rec.is_playable,
        }
    )
