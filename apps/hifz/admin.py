from django.contrib import admin

from .models import (
    AyahThematicClassification,
    MemorizedAyah,
    RecitationAttempt,
    ThematicTopic,
)


@admin.register(MemorizedAyah)
class MemorizedAyahAdmin(admin.ModelAdmin):
    list_display = ("user", "ayah", "status", "revealed", "reveal_count", "updated_at")
    list_filter = ("status", "revealed")
    search_fields = ("user__username", "ayah__text")
    autocomplete_fields = ("user", "ayah")


@admin.register(RecitationAttempt)
class RecitationAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "ayah", "score", "is_correct", "created_at")
    list_filter = ("is_correct", "created_at")
    search_fields = ("user__username", "expected_text", "recognized_text")
    autocomplete_fields = ("user", "ayah")


@admin.register(ThematicTopic)
class ThematicTopicAdmin(admin.ModelAdmin):
    list_display = ("topic_id", "topic_ar", "color_name_ar", "color_hex", "color_id")
    list_filter = ("color_id", "color_name_ar")
    search_fields = ("topic_ar", "topic_id", "color_name_ar")
    ordering = ("color_id", "topic_id")


@admin.register(AyahThematicClassification)
class AyahThematicClassificationAdmin(admin.ModelAdmin):
    list_display = ("surah_number", "ayah_from", "ayah_to", "topic", "notes")
    list_filter = ("topic__color_id", "topic")
    search_fields = ("topic__topic_ar", "topic_text", "notes")
    autocomplete_fields = ("topic",)
    ordering = ("surah_number", "ayah_from", "ayah_to")
