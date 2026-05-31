import json
from datetime import datetime

from django.contrib.auth import get_user_model, login, logout
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from identity.accounts.auth.login_service import login_user
from identity.accounts.auth.registration_service import (
    register_account,
    validate_registration_payload,
)
from identity.accounts.user_types import resolve_user_type_slug
from identity.accounts.auth.settings_service import is_db_login_allowed

User = get_user_model()


def _display_name(user) -> str:
    name = (getattr(user, "full_name", None) or "").strip()
    if name:
        return name
    full = (user.get_full_name() or "").strip()
    return full or user.username


def _user_type_slug(user) -> str:
    if getattr(user, "user_type", None) == USER_TYPE_TEACHER:
        return "teacher"
    if getattr(user, "user_type", None) == USER_TYPE_STUDENT:
        return "student"
    if hasattr(user, "teacher_profile"):
        return "teacher"
    if hasattr(user, "student_profile"):
        return "student"
    return "student"


def _user_payload(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": _display_name(user),
        "user_type": resolve_user_type_slug(user),
    }


def _success(user, status: int = 200) -> JsonResponse:
    return JsonResponse(
        {"success": True, "user": _user_payload(user)},
        status=status,
    )


def _error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"success": False, "message": message}, status=status)


def _parse_json(request) -> tuple[dict | None, JsonResponse | None]:
    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _error("Invalid JSON.", 400)

    if not isinstance(data, dict):
        return None, _error("Invalid JSON.", 400)

    return data, None


@ensure_csrf_cookie
@require_GET
def me(request):
    if request.user.is_authenticated:
        return JsonResponse(
            {
                "authenticated": True,
                "user": _user_payload(request.user),
            }
        )

    return JsonResponse(
        {
            "authenticated": False,
            "message": "Not authenticated.",
        },
        status=401,
    )


@require_POST
def login_api(request):
    data, err = _parse_json(request)
    if err:
        return err

    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return _error("اسم المستخدم وكلمة المرور مطلوبان.", 400)

    if "@" in username:
        return _error(
            "أدخل اسم المستخدم فقط (الجزء قبل @) وليس البريد الإلكتروني كاملاً.",
            400,
        )

    result = login_user(request, username, password)

    if result == "ok":
        return _success(request.user)

    if result == "inactive":
        return _error("Account is inactive.", 403)

    return _error("اسم المستخدم أو كلمة المرور غير صحيحة.", 401)


@require_POST
def register_api(request):
    if not is_db_login_allowed():
        return _error("Registration is disabled.", 403)

    data, err = _parse_json(request)
    if err:
        return err

    payload, message = validate_registration_payload(data)
    if message:
        return _error(message, 400)

    user = register_account(
        full_name=payload["full_name"],
        email=payload["email"],
        password=payload["password"],
        user_type_value=payload["user_type_value"],
    )

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return _success(user, status=201)


@require_POST
def logout_api(request):
    logout(request)
    return JsonResponse({"success": True})
