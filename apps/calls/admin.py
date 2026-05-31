from django.contrib import admin

from .models import CallSession


@admin.register(CallSession)
class CallSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "student",
        "teacher",
        "session_type",
        "provider",
        "status",
        "started_at",
        "ended_at",
        "created_at",
    )
    list_filter = ("session_type", "provider", "status", "created_at")
    search_fields = (
        "student__username",
        "student__email",
        "teacher__username",
        "channel_name",
    )
    raw_id_fields = ("student", "teacher")
