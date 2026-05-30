import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_FCM_BATCH_SIZE = 500

# رموز أخطاء FCM التي تدل على أن التوكن لم يعد صالحاً
_INVALID_TOKEN_CODES = frozenset({
    "registration-token-not-registered",
    "invalid-registration-token",
    "UNREGISTERED",
})


def _get_firebase_app():
    """تهيئة Firebase مرة واحدة فقط طوال عمر العملية."""
    import firebase_admin
    from firebase_admin import credentials

    try:
        return firebase_admin.get_app()
    except ValueError:
        cred_path = getattr(settings, "FIREBASE_CREDENTIALS_PATH", None)
        if not cred_path:
            raise RuntimeError("FIREBASE_CREDENTIALS_PATH غير محدد في الإعدادات.")
        cred = credentials.Certificate(cred_path)
        return firebase_admin.initialize_app(cred)


def _deactivate_invalid_tokens(token_list: list[str]) -> int:
    """تعطيل التوكنات غير الصالحة في قاعدة البيانات بدلاً من حذفها."""
    from .models import UserDevice

    if not token_list:
        return 0
    count = UserDevice.objects.filter(fcm_token__in=token_list).update(is_active=False)
    if count:
        logger.info("FCM: deactivated %d invalid tokens", count)
    return count


def _build_multicast(tokens: list[str], title: str, body: str, data: dict | None):
    from firebase_admin import messaging

    notification = messaging.Notification(title=title, body=body)
    kwargs: dict = {"notification": notification, "tokens": tokens}
    if data:
        kwargs["data"] = {k: str(v) for k, v in data.items()}
    return messaging.MulticastMessage(**kwargs)


def send_push_notification_to_tokens(
    tokens: list[str],
    title: str,
    body: str,
    data: dict | None = None,
) -> dict:
    """
    يرسل إشعاراً لقائمة توكنات محددة.
    يعطّل أي توكن غير صالح تلقائياً.
    يُرجع: { sent, failed, deactivated, total }
    """
    from firebase_admin import messaging
    from firebase_admin.exceptions import FirebaseError

    if not tokens:
        return {"sent": 0, "failed": 0, "deactivated": 0, "total": 0}

    app = _get_firebase_app()
    total = len(tokens)
    total_sent = 0
    total_failed = 0
    tokens_to_deactivate: list[str] = []

    for i in range(0, total, _FCM_BATCH_SIZE):
        batch = tokens[i : i + _FCM_BATCH_SIZE]
        multicast = _build_multicast(batch, title, body, data)

        try:
            response = messaging.send_each_for_multicast(multicast, app=app)
        except FirebaseError as exc:
            logger.error("FCM batch error: %s", exc)
            total_failed += len(batch)
            continue

        total_sent += response.success_count
        total_failed += response.failure_count

        for idx, resp in enumerate(response.responses):
            if resp.success:
                continue
            exc = resp.exception
            error_code = getattr(exc, "code", None) or ""
            if error_code in _INVALID_TOKEN_CODES:
                tokens_to_deactivate.append(batch[idx])

    deactivated = _deactivate_invalid_tokens(tokens_to_deactivate)

    logger.info(
        "FCM send done — total=%d sent=%d failed=%d deactivated=%d",
        total,
        total_sent,
        total_failed,
        deactivated,
    )
    return {
        "total": total,
        "sent": total_sent,
        "failed": total_failed,
        "deactivated": deactivated,
    }


def send_push_notification_to_user(
    user,
    title: str,
    body: str,
    data: dict | None = None,
) -> dict:
    """
    يرسل إشعاراً لجميع أجهزة مستخدم معين النشطة.
    يُرجع: { sent, failed, deactivated, total }
    """
    from .models import UserDevice

    tokens = list(
        UserDevice.objects.filter(user=user, is_active=True).values_list(
            "fcm_token", flat=True
        )
    )
    if not tokens:
        logger.debug("FCM: no active tokens for user=%s", getattr(user, "pk", user))
        return {"sent": 0, "failed": 0, "deactivated": 0, "total": 0}

    return send_push_notification_to_tokens(tokens, title, body, data)


def send_push_to_all(title: str, body: str) -> dict:
    """
    يرسل إشعاراً لجميع الأجهزة النشطة المسجلة.
    يعطّل التوكنات المنتهية الصلاحية تلقائياً.
    يُرجع: { sent, failed, removed, total }
    متوافق مع الاستدعاءات السابقة (removed = deactivated).
    """
    from .models import UserDevice

    tokens = list(
        UserDevice.objects.filter(is_active=True).values_list("fcm_token", flat=True)
    )
    result = send_push_notification_to_tokens(tokens, title, body)
    # إعادة التسمية للتوافق مع الكود القديم
    result["removed"] = result.pop("deactivated")
    return result
