from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as auth_login

from identity.accounts.auth.settings_service import is_db_login_allowed
from identity.accounts.auth.teacher_login_guard import teacher_login_block_message

User = get_user_model()


def _resolve_user(identifier: str):
    value = (identifier or "").strip()
    if not value:
        return None
    if "@" in value:
        return User.objects.filter(email__iexact=value).select_related(
            "teacher_profile"
        ).first()
    user = User.objects.filter(username__iexact=value).select_related(
        "teacher_profile"
    ).first()
    if user:
        return user
    return User.objects.filter(email__iexact=value).select_related(
        "teacher_profile"
    ).first()


def _password_valid(user_obj, password: str) -> bool:
    return bool(user_obj and user_obj.check_password(password))


def login_user(request, identifier, password):
    user_obj = _resolve_user(identifier)
    if user_obj is None:
        return "invalid"

    # Superuser emergency access (always allowed unless rejected teacher path)
    if user_obj.is_superuser:
        if not _password_valid(user_obj, password):
            return "invalid"
        user = authenticate(
            request, username=user_obj.username, password=password
        )
        if user and user.is_superuser:
            if not user.is_active:
                return "inactive"
            auth_login(
                request, user, backend="django.contrib.auth.backends.ModelBackend"
            )
            return "ok"
        return "invalid"

    if not is_db_login_allowed():
        return "invalid"

    if not _password_valid(user_obj, password):
        return "invalid"

    if teacher_login_block_message(user_obj):
        return "rejected"

    if not user_obj.is_active:
        return "inactive"

    auth_login(
        request,
        user_obj,
        backend="django.contrib.auth.backends.ModelBackend",
    )
    return "ok"
