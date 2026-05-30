from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "email",
        "status",
        "replied_by",
        "replied_at",
        "created_at",
    )
    list_filter = ("status", "created_at", "replied_at")
    search_fields = (
        "full_name",
        "email",
        "phone",
        "message",
        "reply_subject",
        "reply_body",
    )
    ordering = ("-created_at",)
