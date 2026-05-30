from django.contrib import admin
from .models import MessageBroadcast, MessageDelivery




@admin.register(MessageBroadcast)
class MessageBroadcastAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "channel",
        "status",
        "created_by",
        "failed_recipients",
        "created_at",
        "sent_at",
    )
    list_filter = ("channel", "status", "created_at", "sent_at")
    search_fields = ("title", "body", "created_by__username", "created_by__email")


@admin.register(MessageDelivery)
class MessageDeliveryAdmin(admin.ModelAdmin):
    list_display = ("id", "broadcast", "user", "email", "status", "sent_at", "delivered_at")
    list_filter = ("status", "delivered_at", "sent_at")
    search_fields = ("broadcast__title", "user__username", "user__email", "email", "error_message")