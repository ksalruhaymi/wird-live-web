from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.mobile.models import MobileAppConfig
from identity.rbac.decorators import permissions_required


@login_required
@permissions_required("dashboard.access", "mobile_app_config.view")
def mobile_app_config_settings(request):
    """Legacy settings URL — redirected to the unified versions page."""
    return redirect("dashboard:mobile_version_list")


@login_required
@permissions_required("dashboard.access", "mobile_app_config.update")
@require_POST
def mobile_app_toggle_enabled(request):
    """Kill-switch only: keep app_enabled without duplicating version settings."""
    config = MobileAppConfig.get_settings()
    config.app_enabled = request.POST.get("app_enabled") == "on"
    config.save(update_fields=["app_enabled", "updated_at"])
    if config.app_enabled:
        messages.success(request, "تم تفعيل التطبيق.")
    else:
        messages.success(request, "تم إيقاف التطبيق — سيُحظر الدخول من النسخ الحالية.")
    return redirect("dashboard:mobile_version_list")
