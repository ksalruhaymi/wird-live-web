from django.contrib import admin

from .models import AnalyticsVisitor, InteractionEvent


@admin.register(AnalyticsVisitor)
class AnalyticsVisitorAdmin(admin.ModelAdmin):
    list_display = ("session_key", "client_source", "app_version", "device_id", "last_seen_at")
    search_fields = ("session_key", "device_id")
    list_filter = ("client_source",)


@admin.register(InteractionEvent)
class InteractionEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "source_platform", "path", "created_at")
    list_filter = ("event_type", "source_platform")
    search_fields = ("path",)
