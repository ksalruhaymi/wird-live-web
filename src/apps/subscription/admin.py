from django.contrib import admin
from .models import NewsletterSubscriber


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "is_active", "subscribed_at")
    list_filter = ("is_active", "subscribed_at")
    search_fields = ("email",)
    list_display = ("id", "email", "is_active", "is_confirmed", "subscribed_at")
    list_filter = ("is_active", "is_confirmed", "subscribed_at")
