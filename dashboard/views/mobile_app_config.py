from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.mobile.models import MobileAppConfig
from identity.rbac.decorators import permissions_required


@login_required
@permissions_required("dashboard.access", "mobile_app_config.view")
def mobile_app_config_settings(request):
    config = MobileAppConfig.get_settings()

    if request.method == "POST":
        if not request.user.has_permission("mobile_app_config.update"):
            messages.error(request, "ليس لديك صلاحية تعديل إعدادات تطبيق الجوال.")
            return redirect("dashboard:mobile_app_config_settings")

        config.app_enabled = "app_enabled" in request.POST
        config.force_update = "force_update" in request.POST
        config.min_supported_version = (
            request.POST.get("min_supported_version") or "1.0.0"
        ).strip()
        config.message = (request.POST.get("message") or "").strip()
        config.update_url = (request.POST.get("update_url") or "").strip()

        build_raw = (request.POST.get("min_supported_build") or "1").strip()
        try:
            config.min_supported_build = max(1, int(build_raw))
        except ValueError:
            messages.error(request, "رقم البناء يجب أن يكون عدداً صحيحاً.")
            return redirect("dashboard:mobile_app_config_settings")

        config.save()
        messages.success(request, "تم تحديث إعدادات تطبيق الجوال بنجاح.")
        return redirect("dashboard:mobile_app_config_settings")

    return render(
        request,
        "dashboard/pages/mobile_app_config/form.html",
        {"config": config},
    )
