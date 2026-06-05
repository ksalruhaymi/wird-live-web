from django.contrib import admin

from .models import NewsletterSubscriber, StudentSubscription, SubscriptionPlan


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "duration_months",
        "price",
        "minutes",
        "is_active",
        "sort_order",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("title",)
    ordering = ("sort_order", "id")


@admin.register(StudentSubscription)
class StudentSubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "plan_title",
        "amount",
        "start_date",
        "end_date",
        "status",
        "payment_status",
        "created_at",
    )
    list_filter = ("status", "payment_status", "created_at")
    search_fields = (
        "user__username",
        "user__email",
        "plan_title",
        "transaction_reference",
    )
    raw_id_fields = ("user", "plan")
    ordering = ("-created_at", "-id")


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "is_active", "is_confirmed", "subscribed_at")
    list_filter = ("is_active", "is_confirmed", "subscribed_at")
    search_fields = ("email",)
