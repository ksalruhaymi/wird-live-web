# identity/accounts/views/login_settings.py

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from identity.rbac.decorators import permission_required
from identity.accounts.models import SystemAuthSettings


@permission_required("settings.access")
def login_settings(request):
    settings_obj = SystemAuthSettings.get_settings()

    if request.method == "POST":
        # checkboxes: لو غير مؤشرة لا تُرسل في POST
        settings_obj.allow_db_login = "allow_db_login" in request.POST
        settings_obj.save()

        messages.success(request, "تم تحديث إعدادات تسجيل الدخول بنجاح.")
        return redirect("accounts:login_settings")

    return render(
        request,
        "accounts/settings/login_settings.html",
        {"settings": settings_obj},
    )
