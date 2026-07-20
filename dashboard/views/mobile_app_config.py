from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

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
    """Deprecated global toggle — platform enablement lives on version forms."""
    messages.info(
        request,
        "تفعيل التطبيق أصبح مستقلاً لكل منصة من نموذج إضافة/تعديل النسخة.",
    )
    return redirect("dashboard:mobile_version_list")
