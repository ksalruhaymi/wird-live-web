from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AnalyticsIPAddress(models.Model):
    ip_address = models.GenericIPAddressField(unique=True)
    country_code = models.CharField(max_length=8, blank=True)
    country_name = models.CharField(max_length=128, blank=True)
    last_language = models.CharField(max_length=16, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    hits_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return self.ip_address or "-"


class AnalyticsVisitor(models.Model):
    session_key = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analytics_visits",
    )
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    os_name = models.CharField(max_length=64, blank=True)
    os_version = models.CharField(max_length=64, blank=True)
    browser_name = models.CharField(max_length=64, blank=True)
    browser_version = models.CharField(max_length=64, blank=True)
    device_type = models.CharField(max_length=32, blank=True)
    last_language = models.CharField(max_length=16, blank=True)
    client_source = models.CharField(max_length=16, blank=True, default="web")
    device_id = models.CharField(max_length=64, blank=True)
    app_version = models.CharField(max_length=32, blank=True)
    user_agent = models.TextField(blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    visits_count = models.PositiveIntegerField(default=0)
    total_active_seconds = models.PositiveIntegerField(default=0)
    is_authenticated = models.BooleanField(default=False)

    class Meta:
        ordering = ["-last_seen_at"]

    def __str__(self):
        return self.session_key


class PageView(models.Model):
    visitor = models.ForeignKey(
        AnalyticsVisitor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="page_views",
    )
    path = models.CharField(max_length=255)
    full_path = models.CharField(max_length=500, blank=True)
    page_title = models.CharField(max_length=255, blank=True)
    method = models.CharField(max_length=10, default="GET")
    referrer = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["path", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.path


class InteractionEvent(models.Model):
    EVENT_PAGE_FLIP = "page_flip"
    EVENT_AUDIO_PLAY = "audio_play"
    EVENT_AUDIO_COMPLETE = "audio_complete"
    EVENT_AUDIO_PAUSE = "audio_pause"
    EVENT_AUDIO_PROGRESS_50 = "audio_progress_50"
    EVENT_TAFSIR_OPEN = "tafsir_open"
    EVENT_WORD_MEANINGS_OPEN = "word_meanings_open"
    EVENT_SESSION_ACTIVE = "session_active"
    EVENT_RECITATION_CORRECTION = "recitation_correction"
    EVENT_DAILY_WIRD_OPEN = "daily_wird_open"
    EVENT_LANGUAGE_CHANGE = "language_change"
    EVENT_TRANSLATION_TEXT_VIEW = "translation_text_view"
    EVENT_TRANSLATION_AUDIO_PLAY = "translation_audio_play"
    EVENT_TRANSLATION_LANG_CHANGE = "translation_lang_change"
    EVENT_CLIENT_ERROR = "client_error"
    EVENT_AUDIO_ERROR = "audio_error"
    EVENT_API_ERROR = "api_error"
    EVENT_PAGE_LOAD_ERROR = "page_load_error"
    EVENT_SCREEN_VIEW = "screen_view"
    EVENT_MEDIA_PLAY = "media_play"
    EVENT_MEDIA_ERROR = "media_error"
    EVENT_MOBILE_EVENT = "mobile_event"

    EVENT_CHOICES = [
        (EVENT_PAGE_FLIP, _("analytics_event_page_flip")),
        (EVENT_AUDIO_PLAY, _("analytics_event_audio_play")),
        (EVENT_AUDIO_COMPLETE, _("analytics_event_audio_complete")),
        (EVENT_AUDIO_PAUSE, _("analytics_event_audio_pause")),
        (EVENT_AUDIO_PROGRESS_50, _("analytics_event_audio_progress_50")),
        (EVENT_TAFSIR_OPEN, _("analytics_event_tafsir_open")),
        (EVENT_WORD_MEANINGS_OPEN, _("analytics_event_word_meanings_open")),
        (EVENT_SESSION_ACTIVE, _("analytics_event_session_active")),
        (EVENT_RECITATION_CORRECTION, _("analytics_event_recitation_correction")),
        (EVENT_DAILY_WIRD_OPEN, _("analytics_event_daily_wird_open")),
        (EVENT_LANGUAGE_CHANGE, _("analytics_event_language_change")),
        (EVENT_TRANSLATION_TEXT_VIEW, _("analytics_event_translation_text_view")),
        (EVENT_TRANSLATION_AUDIO_PLAY, _("analytics_event_translation_audio_play")),
        (EVENT_TRANSLATION_LANG_CHANGE, _("analytics_event_translation_lang_change")),
        (EVENT_CLIENT_ERROR, _("analytics_event_client_error")),
        (EVENT_AUDIO_ERROR, _("analytics_event_audio_error")),
        (EVENT_API_ERROR, _("analytics_event_api_error")),
        (EVENT_PAGE_LOAD_ERROR, _("analytics_event_page_load_error")),
        (EVENT_SCREEN_VIEW, _("analytics_event_screen_view")),
        (EVENT_MEDIA_PLAY, _("analytics_event_media_play")),
        (EVENT_MEDIA_ERROR, _("analytics_event_media_error")),
        (EVENT_MOBILE_EVENT, _("analytics_event_mobile_event")),
    ]

    visitor = models.ForeignKey(
        AnalyticsVisitor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES)
    source_platform = models.CharField(max_length=16, blank=True, default="web")
    path = models.CharField(max_length=255)
    page_number = models.PositiveIntegerField(blank=True, null=True)
    surah_number = models.PositiveIntegerField(blank=True, null=True)
    ayah_number = models.PositiveIntegerField(blank=True, null=True)
    qari = models.CharField(max_length=100, blank=True)
    duration_seconds = models.PositiveIntegerField(blank=True, null=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["path", "created_at"]),
            models.Index(fields=["source_platform", "created_at"]),
        ]

    def __str__(self):
        return self.event_type
