import json
import logging

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.quran.api.auth import require_api_key
from apps.push.models import UserDevice

logger = logging.getLogger(__name__)

_ALLOWED_PLATFORMS = {"android", "ios"}
_MAX_TOKEN_LENGTH = 500
_MAX_DEVICE_ID_LENGTH = 255

User = get_user_model()


@csrf_exempt
@require_api_key
@require_POST
def register_device(request):
    if len(request.body) > 4_096:
        return JsonResponse({"detail": "الطلب كبير جداً."}, status=413)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "JSON غير صالح."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"detail": "تنسيق البيانات غير صحيح."}, status=400)

    # ── Validation ─────────────────────────────────────────────────────────────
    fcm_token = str(data.get("fcm_token") or "").strip()
    platform = str(data.get("platform") or "").strip().lower()
    device_id = str(data.get("device_id") or "").strip()[:_MAX_DEVICE_ID_LENGTH]

    errors = {}

    if not fcm_token:
        errors["fcm_token"] = "التوكن مطلوب."
    elif len(fcm_token) > _MAX_TOKEN_LENGTH:
        errors["fcm_token"] = "التوكن طويل جداً."

    if not platform:
        errors["platform"] = "المنصة مطلوبة."
    elif platform not in _ALLOWED_PLATFORMS:
        errors["platform"] = "المنصة يجب أن تكون android أو ios."

    if errors:
        return JsonResponse({"errors": errors}, status=422)

    # ── User lookup (اختياري — Flutter يرسل user_id إن كان المستخدم مسجلاً) ──
    user = _resolve_user(data.get("user_id"))

    # ── Save ───────────────────────────────────────────────────────────────────
    try:
        defaults = {
            "platform": platform,
            "device_id": device_id,
            "is_active": True,
            "last_seen_at": timezone.now(),
        }
        if user is not None:
            defaults["user"] = user

        device, created = UserDevice.objects.update_or_create(
            fcm_token=fcm_token,
            defaults=defaults,
        )

        # تعطيل التوكنات القديمة لنفس الجهاز ونفس المستخدم فقط
        if device_id and user is not None:
            deactivated = (
                UserDevice.objects.filter(
                    user=user,
                    device_id=device_id,
                    is_active=True,
                )
                .exclude(fcm_token=fcm_token)
                .update(is_active=False)
            )
            if deactivated:
                logger.info(
                    "push_api: deactivated %d old tokens for user=%s device_id=%s",
                    deactivated,
                    user.pk,
                    device_id,
                )

    except Exception:
        logger.exception("push_api: failed to register device")
        return JsonResponse({"detail": "خطأ في الخادم."}, status=500)

    status_code = 201 if created else 200
    logger.info(
        "push_api: device %s id=%d user=%s",
        "created" if created else "updated",
        device.id,
        user.pk if user else "anonymous",
    )

    return JsonResponse(
        {
            "success": True,
            "message": "تم تسجيل التوكن بنجاح.",
            "id": device.id,
            "created": created,
        },
        status=status_code,
    )


def _resolve_user(user_id_raw):
    """محاولة إيجاد المستخدم بناءً على user_id الواصل من Flutter."""
    if not user_id_raw:
        return None
    try:
        return User.objects.get(pk=int(user_id_raw))
    except (User.DoesNotExist, (ValueError, TypeError)):
        return None
