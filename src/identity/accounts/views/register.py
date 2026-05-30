from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from identity.rbac.models import Role

User = get_user_model()


def register(request):
    errors = {}
    data = {}

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        data = {
            "username": username,
            "email": email,
        }

        if not username:
            errors["username"] = _("username_required")
        elif User.objects.filter(username=username).exists():
            errors["username"] = _("username_taken")

        if not email:
            errors["email"] = _("email_required")
        elif User.objects.filter(email=email).exists():
            errors["email"] = _("email_taken")

        if not password:
            errors["password"] = _("password_required")

        if "password" not in errors and password:
            try:
                validate_password(password)
            except ValidationError as e:
                errors["password"] = " ".join(e.messages)

        if not errors:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                user_type=9,
                created_by=None,
            )

            participant_role = Role.objects.filter(slug="participant").first()
            if participant_role:
                user.roles.add(participant_role)

            login(
                request,
                user,
                backend="django.contrib.auth.backends.ModelBackend",
            )

            messages.success(
                request,
                _("register_success")
            )

            if user.has_permission("dashboard.access"):
                return redirect("dashboard:home")
            return redirect("web:home")

    return render(
        request,
        "accounts/auth.html",
        {
            "errors": errors,
            "data": data,
            "active_tab": "register",
        },
    )