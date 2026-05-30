from django.contrib import admin
from .models import Surah, Ayah, AyahTranslation, AudioListenEvent


@admin.register(Surah)
class SurahAdmin(admin.ModelAdmin):
    list_display = ("surah_number", "surah_name_ar", "page_start", "page_end", "ayah_count", "revelation_type")
    list_filter = ("revelation_type",)
    search_fields = ("surah_name_ar", "surah_name_en")


@admin.register(Ayah)
class AyahAdmin(admin.ModelAdmin):
    list_display = ("surah_number", "ayah_number", "page_number", "juz_number")
    list_filter = ("juz_number", "page_number")
    search_fields = ("text",)


@admin.register(AyahTranslation)
class AyahTranslationAdmin(admin.ModelAdmin):
    list_display = ("language", "surah_number", "ayah_number")
    list_filter = ("language", "surah_number")
    search_fields = ("translation",)
    ordering = ("language", "surah_number", "ayah_number")


@admin.register(AudioListenEvent)
class AudioListenEventAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "event_type",
        "qari_code",
        "mushaf_key",
        "surah_number",
        "ayah_number",
        "page_number",
        "percent",
        "user",
        "country",
    )
    list_filter = ("event_type", "mushaf_key", "qari_code", "country", "created_at")
    search_fields = ("qari_code", "mushaf_key", "audio_src", "session_key", "user_agent")
    readonly_fields = (
        "user",
        "session_key",
        "mushaf_key",
        "qari_code",
        "surah_number",
        "ayah_number",
        "page_number",
        "event_type",
        "current_time",
        "duration",
        "percent",
        "audio_src",
        "ip_address",
        "country",
        "user_agent",
        "created_at",
    )
    date_hierarchy = "created_at"
