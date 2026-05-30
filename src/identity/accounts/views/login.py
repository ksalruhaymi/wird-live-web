# identity/accounts/views/login.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils.translation import gettext as _
from identity.accounts.auth.login_service import login_user


def login_view(request):
    if request.method != "POST":
        # show unified auth page with login tab active
        return render(request, "accounts/auth.html", {"active_tab": "login"})

    username = (request.POST.get("username") or "").strip()
    password = (request.POST.get("password") or "").strip()

    if not username or not password:
        messages.error(request, _("account_needs_activation"))
        return render(
            request,
            "accounts/auth.html",
            {
                "active_tab": "login",
                "username": username,
            },
        )

    result = login_user(request, username, password)

    if result == "ok":
        if request.user.has_permission("dashboard.access"):
            return redirect("dashboard:home")
        return redirect("web:home")

    if result == "inactive":
        messages.error(request, _("account_needs_activation"))
    else:
        messages.error(request, _("invalid_login_credentials"))

    return render(
        request,
        "accounts/auth.html",
        {
            "active_tab": "login",
            "username": username,
        },
    )