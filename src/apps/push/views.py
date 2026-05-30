import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from identity.rbac.decorators import permission_required

from .models import PushBroadcast, UserDevice
from .services import send_push_to_all

logger = logging.getLogger(__name__)

_MAX_TITLE = 255
_MAX_BODY = 1000
_ALLOWED_TABS = {"summary", "send", "history"}
_STALE_DAYS = 90


@never_cache
@login_required
@permission_required("push.access")
@require_http_methods(["GET", "POST"])
def push_dashboard(request):
    tab = request.GET.get("tab", "summary").strip()
    if tab not in _ALLOWED_TABS:
        tab = "summary"

    result = None

    if request.method == "POST" and request.POST.get("action") == "cleanup_stale":
        cutoff = timezone.now() - timedelta(days=_STALE_DAYS)
        count = UserDevice.objects.filter(is_active=True, last_seen_at__lt=cutoff).update(is_active=False)
        messages.success(request, f"تم تعطيل {count} توكن لم يُستخدم منذ {_STALE_DAYS} يوماً.")
        return redirect(f"{request.path}?tab=summary")

    if request.method == "POST":
        title = request.POST.get("title", "").strip()[:_MAX_TITLE]
        body  = request.POST.get("body",  "").strip()[:_MAX_BODY]

        if not title or not body:
            messages.error(request, "العنوان والنص مطلوبان.")
            tab = "send"
        else:
            try:
                result = send_push_to_all(title, body)

                PushBroadcast.objects.create(
                    title=title,
                    body=body,
                    status=PushBroadcast.Status.SENT if result["sent"] > 0 else PushBroadcast.Status.FAILED,
                    total_devices=result["total"],
                    success_count=result["sent"],
                    failure_count=result["failed"],
                    removed_count=result["removed"],
                    sent_by=request.user,
                )

                messages.success(
                    request,
                    f"تم الإرسال — وصل: {result['sent']} | فشل: {result['failed']}",
                )
                tab = "history"

            except Exception:
                logger.exception("push_dashboard: send failed")
                messages.error(request, "حدث خطأ أثناء الإرسال. تحقق من إعدادات Firebase.")
                tab = "send"

    active_devices = UserDevice.objects.filter(is_active=True)
    all_devices = UserDevice.objects.all().order_by("-created_at")
    cutoff = timezone.now() - timedelta(days=_STALE_DAYS)
    stale_count = UserDevice.objects.filter(is_active=True, last_seen_at__lt=cutoff).count()

    return render(
        request,
        "push/dashboard.html",
        {
            "tab": tab,
            "device_count":         active_devices.count(),
            "android_count":        active_devices.filter(platform="android").count(),
            "ios_count":            active_devices.filter(platform="ios").count(),
            "inactive_count":       UserDevice.objects.filter(is_active=False).count(),
            "stale_count":          stale_count,
            "stale_days":           _STALE_DAYS,
            "devices":              all_devices[:50],
            "broadcasts":           PushBroadcast.objects.select_related("sent_by").order_by("-created_at")[:20],
            "result":               result,
        },
    )
