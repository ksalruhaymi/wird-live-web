from django.contrib import admin

from .models import CallPeerRatingAnswer, CallSession, RatingQuestion


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


@admin.register(RatingQuestion)
class RatingQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "category",
        "question_text",
        "order",
        "is_active",
        "max_stars",
    )
    list_filter = ("category", "is_active")
    search_fields = ("question_text",)


@admin.register(CallPeerRatingAnswer)
class CallPeerRatingAnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "rating", "question", "stars", "created_at")
    raw_id_fields = ("rating", "question")
