from django.contrib import admin

from .models import AppNotification, AppNotificationRead, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "level", "is_read", "created_at")
    list_filter = ("level", "is_read", "created_at")
    search_fields = ("title", "message", "user__username", "user__email")


@admin.register(AppNotification)
class AppNotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "is_active", "target_type", "created_at")
    list_filter = ("is_active", "target_type", "created_at")
    search_fields = ("title", "body")


@admin.register(AppNotificationRead)
class AppNotificationReadAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "notification", "read_at")
    list_filter = ("read_at",)