from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path

from .models import PushBroadcast, UserDevice
from .services import send_push_to_all


# ── UserDevice ─────────────────────────────────────────────────────────────────

@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "id", "short_token", "platform", "user", "device_id",
        "is_active", "last_seen_at", "created_at",
    )
    list_filter = ("platform", "is_active")
    search_fields = ("fcm_token", "device_id", "user__username", "user__email")
    readonly_fields = (
        "fcm_token", "platform", "user", "device_id",
        "is_active", "last_seen_at", "created_at", "updated_at",
    )
    actions = ["deactivate_selected"]

    def short_token(self, obj):
        return obj.fcm_token[:32] + "…"
    short_token.short_description = "FCM Token"

    def has_add_permission(self, request):
        return False

    @admin.action(description="تعطيل التوكنات المحددة")
    def deactivate_selected(self, request, queryset):
        count = queryset.filter(is_active=True).update(is_active=False)
        self.message_user(request, f"تم تعطيل {count} توكن.", messages.SUCCESS)


# ── PushBroadcast ──────────────────────────────────────────────────────────────

@admin.register(PushBroadcast)
class PushBroadcastAdmin(admin.ModelAdmin):
    list_display = (
        "id", "title", "status", "total_devices",
        "success_count", "failure_count", "removed_count",
        "sent_by", "created_at",
    )
    list_filter = ("status",)
    readonly_fields = (
        "status", "total_devices", "success_count",
        "failure_count", "removed_count", "sent_by", "created_at",
    )

    def get_urls(self):
        return [
            path(
                "send/",
                self.admin_site.admin_view(self._send_view),
                name="push_send",
            ),
        ] + super().get_urls()

    def _send_view(self, request):
        result = None

        if request.method == "POST":
            title = request.POST.get("title", "").strip()
            body = request.POST.get("body", "").strip()

            if not title or not body:
                messages.error(request, "العنوان والنص مطلوبان.")
            else:
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
                    f"✅ تم الإرسال — نجح: {result['sent']} | فشل: {result['failed']} | معطّل: {result['removed']}",
                )

        context = {
            **self.admin_site.each_context(request),
            "title": "إرسال إشعار لجميع المستخدمين",
            "device_count": UserDevice.objects.filter(is_active=True).count(),
            "last_broadcasts": PushBroadcast.objects.select_related("sent_by")[:5],
            "result": result,
        }
        return render(request, "admin/push/send_push.html", context)
