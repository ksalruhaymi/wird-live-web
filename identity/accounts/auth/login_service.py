from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as auth_login

from identity.accounts.auth.settings_service import is_db_login_allowed

User = get_user_model()


def _resolve_user(identifier: str):
    value = (identifier or "").strip()
    if not value:
        return None
    if "@" in value:
        return User.objects.filter(email__iexact=value).first()
    user = User.objects.filter(username=value).first()
    if user:
        return user
    return User.objects.filter(email__iexact=value).first()


def login_user(request, identifier, password):
    user_obj = _resolve_user(identifier)
    if user_obj is None:
        return "invalid"

    # Superuser emergency access (always allowed)
    if user_obj.is_superuser:
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

    user = authenticate(request, username=user_obj.username, password=password)
    if user:
        if not user.is_active:
            return "inactive"
        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return "ok"

    return "invalid"
