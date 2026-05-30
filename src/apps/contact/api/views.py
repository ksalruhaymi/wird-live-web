import json
import logging
import re

from django.core.cache import cache
from django.core.validators import EmailValidator, ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.contact.models import ContactMessage
from apps.quran.api.auth import require_api_key

logger = logging.getLogger(__name__)

# ── Limits ─────────────────────────────────────────────────────────────────────
_MAX_NAME = 150
_MAX_EMAIL = 254
_MAX_MESSAGE = 3000
_MIN_MESSAGE = 10

# ── Rate limit: 5 requests per IP per 10 minutes ───────────────────────────────
_RATE_LIMIT = 5
_RATE_WINDOW = 60 * 10

_HTML_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_email_validator = EmailValidator()


def _clean(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    return _SPACE_RE.sub(" ", _HTML_RE.sub("", text)).strip()


def _get_client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def _is_rate_limited(request) -> bool:
    key = f"contact_api_rl:{_get_client_ip(request)}"
    count = cache.get(key, 0)
    if count >= _RATE_LIMIT:
        return True
    cache.set(key, count + 1, _RATE_WINDOW)
    return False


def _validate(data: dict) -> tuple[dict, dict]:
    """Returns (cleaned_data, errors)."""
    errors: dict = {}
    cleaned: dict = {}

    name = _clean(str(data.get("name", "") or ""))
    if not name:
        errors["name"] = "الاسم مطلوب."
    elif len(name) > _MAX_NAME:
        errors["name"] = f"الاسم يجب ألا يتجاوز {_MAX_NAME} حرفاً."
    else:
        cleaned["name"] = name

    email = _clean(str(data.get("email", "") or "")).lower()
    if not email:
        errors["email"] = "البريد الإلكتروني مطلوب."
    elif len(email) > _MAX_EMAIL:
        errors["email"] = "البريد الإلكتروني غير صالح."
    else:
        try:
            _email_validator(email)
            cleaned["email"] = email
        except ValidationError:
            errors["email"] = "البريد الإلكتروني غير صالح."

    message = _clean(str(data.get("message", "") or ""))
    if not message:
        errors["message"] = "الرسالة مطلوبة."
    elif len(message) < _MIN_MESSAGE:
        errors["message"] = "الرسالة قصيرة جداً."
    elif len(message) > _MAX_MESSAGE:
        errors["message"] = f"الرسالة يجب ألا تتجاوز {_MAX_MESSAGE} حرفاً."
    else:
        cleaned["message"] = message

    return cleaned, errors


@csrf_exempt
@require_api_key
@require_POST
def submit_message(request):
    if _is_rate_limited(request):
        return JsonResponse(
            {"detail": "طلبات كثيرة. حاول مجدداً بعد قليل."},
            status=429,
        )

    if len(request.body) > 20_000:
        return JsonResponse({"detail": "الطلب كبير جداً."}, status=413)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "JSON غير صالح."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"detail": "تنسيق البيانات غير صحيح."}, status=400)

    cleaned, errors = _validate(data)
    if errors:
        return JsonResponse({"errors": errors}, status=422)

    try:
        msg = ContactMessage.objects.create(
            full_name=cleaned["name"],
            email=cleaned["email"],
            message=cleaned["message"],
            source=ContactMessage.Source.APP,
        )
    except Exception:
        logger.exception("contact_api: failed to save message from %s", cleaned.get("email"))
        return JsonResponse({"detail": "خطأ في الخادم. حاول مجدداً."}, status=500)

    logger.info("contact_api: message saved id=%s email=%s", msg.id, cleaned["email"])

    return JsonResponse({"detail": "تم إرسال رسالتك بنجاح.", "id": msg.id}, status=201)
