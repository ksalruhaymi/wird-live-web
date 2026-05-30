from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth import login as auth_login

from identity.accounts.auth.settings_service import is_db_login_allowed

User = get_user_model()


def login_user(request, username, password):
    # Superuser emergency access (always allowed)
    user = authenticate(request, username=username, password=password)
    if user and user.is_superuser:
        if not user.is_active:
            return "inactive"

        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return "ok"

    if not is_db_login_allowed():
        return "invalid"

    user = authenticate(request, username=username, password=password)
    if user:
        if not user.is_active:
            return "inactive"

        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return "ok"

    return "invalid"
