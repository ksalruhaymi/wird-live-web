import json
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.push.models import UserDevice

logger = logging.getLogger(__name__)

_ALLOWED_PLATFORMS = {"android", "ios"}
_MAX_TOKEN_LENGTH = 500
_MAX_DEVICE_ID_LENGTH = 255

User = get_user_model()


def _has_valid_api_key(request) -> bool:
    key = request.headers.get("X-API-KEY") or request.GET.get("api_key")
    valid_keys = getattr(settings, "QURAN_API_KEYS", []) or []
    return bool(key) and key in valid_keys


def _authorize_device_request(request):
    """Allow session cookie (mobile) or X-API-KEY (legacy clients)."""
    if request.user.is_authenticated:
        return None
    if _has_valid_api_key(request):
        return None
    return JsonResponse(
        {"detail": "يجب تسجيل الدخول أو توفير مفتاح API صالح."},
        status=401,
    )


def _parse_json_body(request):
    if len(request.body) > 4_096:
        return None, JsonResponse({"detail": "الطلب كبير جداً."}, status=413)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"detail": "JSON غير صالح."}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse({"detail": "تنسيق البيانات غير صحيح."}, status=400)
    return data, None


def _resolve_user(user_id_raw):
    if not user_id_raw:
        return None
    try:
        return User.objects.get(pk=int(user_id_raw))
    except (User.DoesNotExist, (ValueError, TypeError)):
        return None


@csrf_exempt
@require_POST
def register_device(request):
    auth_err = _authorize_device_request(request)
    if auth_err:
        return auth_err

    data, err = _parse_json_body(request)
    if err:
        return err

    fcm_token = str(data.get("fcm_token") or "").strip()
    voip_token = str(data.get("voip_token") or "").strip()[:255]
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

    if request.user.is_authenticated:
        user = request.user
    else:
        user = _resolve_user(data.get("user_id"))

    try:
        defaults = {
            "platform": platform,
            "device_id": device_id,
            "is_active": True,
            "last_seen_at": timezone.now(),
        }
        if user is not None:
            defaults["user"] = user
        # Only overwrite VoIP token when the client sends one (iOS PushKit).
        if voip_token:
            defaults["voip_token"] = voip_token

        device, created = UserDevice.objects.update_or_create(
            fcm_token=fcm_token,
            defaults=defaults,
        )

        # After the new token is saved, safely deactivate prior tokens for
        # the same user+device (token refresh / reinstall).
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

        # Keep at most one active VoIP token per iOS device_id.
        if voip_token and device_id and user is not None:
            UserDevice.objects.filter(
                user=user,
                device_id=device_id,
                platform=UserDevice.Platform.IOS,
                is_active=True,
            ).exclude(pk=device.pk).update(voip_token="")

    except Exception:
        logger.exception("push_api: failed to register device")
        return JsonResponse({"detail": "خطأ في الخادم."}, status=500)

    status_code = 201 if created else 200
    return JsonResponse(
        {
            "success": True,
            "message": "تم تسجيل التوكن بنجاح.",
            "id": device.id,
            "created": created,
            "voip_registered": bool(voip_token or device.voip_token),
        },
        status=status_code,
    )


@csrf_exempt
@require_POST
def deactivate_device(request):
    """Best-effort logout / revoke: mark token inactive for this user."""
    auth_err = _authorize_device_request(request)
    if auth_err:
        return auth_err

    data, err = _parse_json_body(request)
    if err:
        return err

    fcm_token = str(data.get("fcm_token") or "").strip()
    device_id = str(data.get("device_id") or "").strip()[:_MAX_DEVICE_ID_LENGTH]

    if not fcm_token and not device_id:
        return JsonResponse(
            {"errors": {"fcm_token": "التوكن أو معرّف الجهاز مطلوب."}},
            status=422,
        )

    qs = UserDevice.objects.filter(is_active=True)
    if request.user.is_authenticated:
        qs = qs.filter(user=request.user)
    elif fcm_token:
        qs = qs.filter(fcm_token=fcm_token)
    else:
        return JsonResponse({"detail": "غير مصرح."}, status=403)

    if fcm_token:
        qs = qs.filter(fcm_token=fcm_token)
    if device_id:
        qs = qs.filter(device_id=device_id)

    updated = qs.update(is_active=False)
    return JsonResponse(
        {
            "success": True,
            "message": "تم تعطيل التوكن.",
            "deactivated": updated,
        }
    )
