import json

from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from identity.accounts.auth.login_service import login_user
from identity.accounts.auth.settings_service import is_db_login_allowed
from identity.rbac.models import Role

User = get_user_model()


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
        "display_name": _display_name(user),
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
        return _error("Username and password are required.", 400)

    result = login_user(request, username, password)

    if result == "ok":
        return _success(request.user)

    if result == "inactive":
        return _error("Account is inactive.", 403)

    return _error("Invalid username or password.", 401)


@require_POST
def register_api(request):
    if not is_db_login_allowed():
        return _error("Registration is disabled.", 403)

    data, err = _parse_json(request)
    if err:
        return err

    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip()
    mobile = (data.get("mobile") or "").strip()

    if not username:
        return _error("Username is required.", 400)
    if not email:
        return _error("Email is required.", 400)
    if not password:
        return _error("Password is required.", 400)

    if User.objects.filter(username=username).exists():
        return _error("Username is already taken.", 400)
    if User.objects.filter(email=email).exists():
        return _error("Email is already taken.", 400)

    try:
        validate_password(password)
    except ValidationError as exc:
        return _error(" ".join(exc.messages), 400)

    extra: dict = {"user_type": 9, "created_by": None}
    if full_name:
        extra["full_name"] = full_name
    if mobile:
        extra["mobile"] = mobile

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        **extra,
    )

    participant_role = Role.objects.filter(slug="participant").first()
    if participant_role:
        user.roles.add(participant_role)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return _success(user, status=201)


@require_POST
def logout_api(request):
    logout(request)
    return JsonResponse({"success": True})
