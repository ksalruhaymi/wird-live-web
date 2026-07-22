"""Notify teacher devices about incoming / cancelled calls via FCM + VoIP."""

from __future__ import annotations

import logging

from django.conf import settings

from apps.push.call_payload import build_incoming_call_data, call_kit_uuid
from apps.push.services import _deactivate_invalid_tokens, _get_firebase_app

logger = logging.getLogger(__name__)

INCOMING_CALLS_CHANNEL = "incoming_calls"


def _caller_label(call) -> str:
    from apps.calls.services import student_display_name

    student = getattr(call, "student", None)
    if student is None:
        return "طالب"
    try:
        return student_display_name(student) or "طالب"
    except Exception:
        return "طالب"


def _teacher_user(call):
    return getattr(call, "teacher", None)


def notify_incoming_call(call) -> dict:
    """High-priority ring push to all active teacher devices."""
    teacher = _teacher_user(call)
    if teacher is None:
        return {"sent": 0, "skipped": "no_teacher"}

    data = build_incoming_call_data(
        call_id=call.id,
        caller_name=_caller_label(call),
        caller_id=getattr(call, "student_id", None),
        session_type=getattr(call, "session_type", "audio") or "audio",
        action="ring",
    )
    title = "مكالمة واردة"
    body = f"{data['caller_name']} يتصل بك"
    return _send_call_push(teacher, title=title, body=body, data=data, ring=True)


def notify_call_cancelled(call, *, reason: str = "cancelled") -> dict:
    """Dismiss ringing UI / CallKit on teacher devices."""
    teacher = _teacher_user(call)
    if teacher is None:
        return {"sent": 0, "skipped": "no_teacher"}

    data = build_incoming_call_data(
        call_id=call.id,
        caller_name=_caller_label(call),
        caller_id=getattr(call, "student_id", None),
        session_type=getattr(call, "session_type", "audio") or "audio",
        action="cancel",
    )
    data["reason"] = str(reason or "cancelled")[:40]
    # Silent-ish cancel; still high priority so devices wake briefly.
    return _send_call_push(
        teacher,
        title="انتهت المكالمة",
        body="لم تعد المكالمة متاحة",
        data=data,
        ring=False,
    )


def _send_call_push(user, *, title: str, body: str, data: dict, ring: bool) -> dict:
    from apps.push.apns_voip import send_voip_push
    from apps.push.models import UserDevice

    devices = list(
        UserDevice.objects.filter(user=user, is_active=True).only(
            "fcm_token", "voip_token", "platform", "id"
        )
    )
    if not devices:
        logger.info("call_push: no devices user=%s call_id=%s", user.pk, data.get("call_id"))
        return {"sent": 0, "failed": 0, "voip": 0, "total": 0}

    fcm_tokens = [d.fcm_token for d in devices if (d.fcm_token or "").strip()]
    voip_tokens = [
        d.voip_token
        for d in devices
        if d.platform == UserDevice.Platform.IOS and (d.voip_token or "").strip()
    ]

    fcm_result = _send_fcm_call(fcm_tokens, title=title, body=body, data=data, ring=ring)

    voip_ok = 0
    for vt in voip_tokens:
        if send_voip_push(vt, data):
            voip_ok += 1

    logger.info(
        "call_push action=%s call_id=%s fcm_sent=%s voip_ok=%s/%s",
        data.get("action"),
        data.get("call_id"),
        fcm_result.get("sent"),
        voip_ok,
        len(voip_tokens),
    )
    return {
        **fcm_result,
        "voip": voip_ok,
        "voip_total": len(voip_tokens),
        "call_uuid": data.get("call_uuid") or call_kit_uuid(int(data["call_id"])),
    }


def _send_fcm_call(
    tokens: list[str],
    *,
    title: str,
    body: str,
    data: dict,
    ring: bool,
) -> dict:
    """Data-first high-priority FCM so Android background handlers can show CallStyle."""
    from firebase_admin import messaging
    from firebase_admin.exceptions import FirebaseError

    from apps.push.services import _INVALID_TOKEN_CODES

    if not tokens:
        return {"sent": 0, "failed": 0, "deactivated": 0, "total": 0}

    try:
        app = _get_firebase_app()
    except Exception:
        logger.exception("call_push: Firebase not configured")
        return {"sent": 0, "failed": len(tokens), "deactivated": 0, "total": len(tokens)}

    str_data = {k: str(v) for k, v in data.items()}
    android_notification = None
    if ring:
        android_notification = messaging.AndroidNotification(
            title=title,
            body=body,
            channel_id=INCOMING_CALLS_CHANNEL,
            priority="max",
            sound="default",
            default_vibrate_timings=True,
            visibility="public",
        )

    android = messaging.AndroidConfig(
        priority="high",
        ttl=60 if ring else 10,
        notification=android_notification,
    )
    aps_kwargs: dict = {"content_available": True}
    if ring:
        aps_kwargs["alert"] = messaging.ApsAlert(title=title, body=body)
        aps_kwargs["sound"] = "default"
        aps_kwargs["mutable_content"] = True
    apns = messaging.APNSConfig(
        headers={
            "apns-priority": "10",
            "apns-push-type": "alert" if ring else "background",
        },
        payload=messaging.APNSPayload(aps=messaging.Aps(**aps_kwargs)),
    )

    # Prefer data so Flutter background isolate can present CallKit / CallStyle.
    # Include notification for Android lock-screen visibility when the handler is delayed.
    notification = messaging.Notification(title=title, body=body) if ring else None

    total_sent = 0
    total_failed = 0
    to_deactivate: list[str] = []
    batch_size = 500
    for i in range(0, len(tokens), batch_size):
        batch = tokens[i : i + batch_size]
        message = messaging.MulticastMessage(
            tokens=batch,
            data=str_data,
            notification=notification,
            android=android,
            apns=apns,
        )
        try:
            response = messaging.send_each_for_multicast(message, app=app)
        except FirebaseError:
            logger.exception("call_push FCM batch error")
            total_failed += len(batch)
            continue
        total_sent += response.success_count
        total_failed += response.failure_count
        for idx, resp in enumerate(response.responses):
            if resp.success:
                continue
            code = getattr(resp.exception, "code", None) or ""
            if code in _INVALID_TOKEN_CODES:
                to_deactivate.append(batch[idx])

    deactivated = _deactivate_invalid_tokens(to_deactivate)
    return {
        "sent": total_sent,
        "failed": total_failed,
        "deactivated": deactivated,
        "total": len(tokens),
    }
