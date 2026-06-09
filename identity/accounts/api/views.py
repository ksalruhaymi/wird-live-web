import json
import mimetypes

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.http import FileResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from identity.accounts.auth.email_verification_service import (
    check_email_available,
    send_registration_code,
    verify_registration_code,
)
from identity.accounts.auth.google_auth_service import authenticate_with_google
from identity.accounts.auth.login_service import login_user
from identity.accounts.auth.registration_service import (
    register_account,
    validate_registration_payload,
)
from identity.accounts.auth.teacher_login_guard import (
    INACTIVE_ACCOUNT_MESSAGE,
    REJECTED_TEACHER_LOGIN_MESSAGE,
    session_access_block_message,
)
from identity.accounts.auth.profile_service import (
    build_profile_payload,
    get_teacher_ijazah_file,
    ijazah_file_kind,
    update_profile_avatar,
    update_profile_fields,
)
from identity.accounts.auth.settings_service import is_db_login_allowed
from identity.accounts.user_types import resolve_user_type_slug

User = get_user_model()


def _logout_if_session_blocked(request) -> JsonResponse | None:
    if not request.user.is_authenticated:
        return None
    message = session_access_block_message(request.user)
    if not message:
        return None
    logout(request)
    return JsonResponse(
        {"success": False, "authenticated": False, "message": message},
        status=401,
    )


def _display_name(user) -> str:
    name = (getattr(user, "full_name", None) or "").strip()
    if name:
        return name
    full = (user.get_full_name() or "").strip()
    return full or user.username


def _user_payload(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": _display_name(user),
        "user_type": resolve_user_type_slug(user),
    }


def _csrf_token(request) -> str:
    return (request.META.get("CSRF_COOKIE") or "").strip() or get_token(request)


def _session_tokens(request) -> dict[str, str]:
    tokens: dict[str, str] = {}
    if not request.session.session_key:
        request.session.save()
    session_key = request.session.session_key
    if session_key:
        tokens["session_id"] = session_key
    csrf = _csrf_token(request)
    if csrf:
        tokens["csrf_token"] = csrf
    return tokens


def _attach_session_tokens(payload: dict, request) -> dict:
    payload.update(_session_tokens(request))
    return payload


def _clear_auth_cookies(response: JsonResponse) -> JsonResponse:
    cookie_kwargs: dict = {"path": "/"}
    session_domain = getattr(settings, "SESSION_COOKIE_DOMAIN", None)
    csrf_domain = getattr(settings, "CSRF_COOKIE_DOMAIN", None)
    if session_domain:
        response.delete_cookie(
            settings.SESSION_COOKIE_NAME,
            domain=session_domain,
            **cookie_kwargs,
        )
    else:
        response.delete_cookie(settings.SESSION_COOKIE_NAME, **cookie_kwargs)
    if csrf_domain:
        response.delete_cookie(
            settings.CSRF_COOKIE_NAME,
            domain=csrf_domain,
            **cookie_kwargs,
        )
    else:
        response.delete_cookie(settings.CSRF_COOKIE_NAME, **cookie_kwargs)
    return response


def _success(user, request, status: int = 200) -> JsonResponse:
    payload: dict = {"success": True, "user": _user_payload(user)}
    _attach_session_tokens(payload, request)
    return JsonResponse(payload, status=status)


def _error(message: str, status: int = 400, code: str | None = None) -> JsonResponse:
    payload = {"success": False, "message": message}
    if code:
        payload["code"] = code
    return JsonResponse(payload, status=status)


def _parse_json(request) -> tuple[dict | None, JsonResponse | None]:
    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _error("Invalid JSON.", 400)

    if not isinstance(data, dict):
        return None, _error("Invalid JSON.", 400)

    return data, None


def _parse_request_data(request) -> tuple[dict | None, object | None, JsonResponse | None]:
    content_type = (request.content_type or "").lower()
    if "multipart/form-data" in content_type:
        return request.POST.dict(), request.FILES.get("ijazah"), None

    data, err = _parse_json(request)
    return data, None, err


@ensure_csrf_cookie
@require_GET
def me(request):
    blocked = _logout_if_session_blocked(request)
    if blocked:
        return blocked

    if request.user.is_authenticated:
        payload = {
            "authenticated": True,
            "user": _user_payload(request.user),
            "profile": build_profile_payload(request.user, request),
        }
        _attach_session_tokens(payload, request)
        return JsonResponse(payload)

    payload = {
        "authenticated": False,
        "message": "Not authenticated.",
    }
    csrf = _csrf_token(request)
    if csrf:
        payload["csrf_token"] = csrf
    return JsonResponse(payload, status=401)


@csrf_exempt
@require_POST
def login_api(request):
    data, err = _parse_json(request)
    if err:
        return err

    identifier = (data.get("username") or data.get("email") or "").strip()
    password = data.get("password") or ""

    if not identifier or not password:
        return _error(
            "اسم المستخدم أو البريد الإلكتروني وكلمة المرور مطلوبان.",
            400,
        )

    result = login_user(request, identifier, password)

    if result == "ok":
        return _success(request.user, request)

    if result == "rejected":
        return _error(REJECTED_TEACHER_LOGIN_MESSAGE, 403)

    if result == "inactive":
        return _error(INACTIVE_ACCOUNT_MESSAGE, 403)

    return _error(
        "اسم المستخدم أو البريد الإلكتروني أو كلمة المرور غير صحيحة.",
        401,
    )


@csrf_exempt
@require_POST
def check_email_api(request):
    data, err = _parse_json(request)
    if err:
        return err

    email = (data.get("email") or "").strip()
    available, message = check_email_available(email)
    if not available:
        return _error(message or "هذا البريد مستخدم مسبقًا", 400)

    return JsonResponse({"success": True, "available": True})


@csrf_exempt
@require_POST
def send_email_code_api(request):
    if not is_db_login_allowed():
        return _error("Registration is disabled.", 403)

    data, err = _parse_json(request)
    if err:
        return err

    email = (data.get("email") or "").strip()
    sent, message = send_registration_code(email)
    if not sent:
        return _error(message or "تعذر إرسال رمز التحقق.", 400)

    return JsonResponse({"success": True})


@csrf_exempt
@require_POST
def verify_email_code_api(request):
    data, err = _parse_json(request)
    if err:
        return err

    email = (data.get("email") or "").strip()
    code = (data.get("code") or "").strip()
    token, message = verify_registration_code(email, code)
    if not token:
        return _error(message or "رمز التحقق غير صالح.", 400)

    return JsonResponse({"success": True, "verification_token": token})


@csrf_exempt
@require_POST
def register_api(request):
    if not is_db_login_allowed():
        return _error("Registration is disabled.", 403)

    data, ijazah_file, err = _parse_request_data(request)
    if err:
        return err

    payload, message = validate_registration_payload(
        data,
        ijazah_file=ijazah_file,
        require_verification_token=True,
    )
    if message:
        return _error(message, 400)

    user = register_account(
        full_name=payload["full_name"],
        email=payload["email"],
        password=payload["password"],
        user_type_value=payload["user_type_value"],
        gender=payload["gender"],
        riwayat=payload["riwayat"],
        ijazah_file=payload["ijazah_file"],
    )

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return _success(user, request, status=201)


@csrf_exempt
@require_POST
def google_auth_api(request):
    data, ijazah_file, err = _parse_request_data(request)
    if err:
        return err

    outcome = authenticate_with_google(request, data, ijazah_file=ijazah_file)

    if outcome.status == "ok" and outcome.user is not None:
        return _success(outcome.user, request, status=outcome.http_status)

    if outcome.status == "account_type_required":
        return _error(
            outcome.message or "نوع الحساب مطلوب",
            status=outcome.http_status,
            code=outcome.code,
        )

    return _error(
        outcome.message or "Google authentication failed.",
        status=outcome.http_status,
        code=outcome.code,
    )


@csrf_exempt
@require_POST
def logout_api(request):
    logout(request)
    return _clear_auth_cookies(JsonResponse({"success": True}))


def _require_authenticated(request) -> JsonResponse | None:
    blocked = _logout_if_session_blocked(request)
    if blocked:
        return blocked
    if not request.user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": "Not authenticated."},
            status=401,
        )
    return None


@require_http_methods(["GET"])
def profile_api(request):
    auth_error = _require_authenticated(request)
    if auth_error:
        return auth_error
    return JsonResponse(
        {
            "success": True,
            "profile": build_profile_payload(request.user, request),
        }
    )


@require_http_methods(["PATCH"])
def profile_update_api(request):
    auth_error = _require_authenticated(request)
    if auth_error:
        return auth_error

    data, err = _parse_json(request)
    if err:
        return err

    allowed_keys = {"mobile", "riwayat"}
    payload = {key: data[key] for key in allowed_keys if key in data}
    if not payload:
        return _error("لا توجد حقول للتحديث.", 400)

    profile, message = update_profile_fields(request.user, payload, request=request)
    if message:
        return _error(message, 400)
    return JsonResponse(
        {
            "success": True,
            "profile": build_profile_payload(request.user, request),
        }
    )


@require_POST
def profile_avatar_api(request):
    auth_error = _require_authenticated(request)
    if auth_error:
        return auth_error

    uploaded = request.FILES.get("profile_image")
    profile, message = update_profile_avatar(request.user, uploaded, request)
    if message:
        return _error(message, 400)
    return JsonResponse({"success": True, "profile": profile})


@require_GET
def profile_teacher_ijazah_api(request):
    auth_error = _require_authenticated(request)
    if auth_error:
        return auth_error

    if resolve_user_type_slug(request.user) != "teacher":
        return _error("هذا الملف للمعلّمين فقط.", 403)

    ijazah = get_teacher_ijazah_file(request.user)
    if ijazah is None:
        return _error("لا يوجد ملف إجازة.", 404)

    content_type, _ = mimetypes.guess_type(ijazah.name)
    filename = ijazah.name.rsplit("/", 1)[-1]
    try:
        response = FileResponse(
            ijazah.open("rb"),
            content_type=content_type or "application/octet-stream",
        )
        disposition = (
            "inline"
            if ijazah_file_kind(filename) in {"image", "pdf"}
            else "attachment"
        )
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response
    except (ValueError, FileNotFoundError):
        return _error("تعذر فتح الملف.", 404)

