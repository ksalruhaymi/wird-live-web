from django.contrib import admin

from .models import AnalyticsIPAddress, AnalyticsVisitor, InteractionEvent, PageView


@admin.register(AnalyticsVisitor)
class AnalyticsVisitorAdmin(admin.ModelAdmin):
    list_display = (
        "session_key",
        "user",
        "ip_address",
        "os_name",
        "os_version",
        "browser_name",
        "browser_version",
        "device_type",
        "visits_count",
        "total_active_seconds",
        "is_authenticated",
        "last_seen_at",
    )
    search_fields = ("session_key", "ip_address", "user_agent", "user__username")
    list_filter = ("is_authenticated", "os_name", "last_seen_at")


@admin.register(AnalyticsIPAddress)
class AnalyticsIPAddressAdmin(admin.ModelAdmin):
    list_display = (
        "ip_address",
        "country_code",
        "country_name",
        "last_language",
        "hits_count",
        "first_seen_at",
        "last_seen_at",
    )
    search_fields = ("ip_address",)
    list_filter = ("last_seen_at",)


@admin.register(PageView)
class PageViewAdmin(admin.ModelAdmin):
    list_display = ("path", "visitor", "method", "created_at")
    search_fields = ("path", "full_path", "page_title")
    list_filter = ("method", "created_at")


@admin.register(InteractionEvent)
class InteractionEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "path", "page_number", "surah_number", "ayah_number", "qari", "created_at")
    search_fields = ("path", "qari")
    list_filter = ("event_type", "created_at")
