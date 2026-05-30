from django.conf import settings
from django.db import models


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

    EVENT_CHOICES = [
        (EVENT_PAGE_FLIP, "Page Flip"),
        (EVENT_AUDIO_PLAY, "Audio Play"),
        (EVENT_AUDIO_COMPLETE, "Audio Complete"),
        (EVENT_AUDIO_PAUSE, "Audio Pause"),
        (EVENT_AUDIO_PROGRESS_50, "Audio Progress 50%"),
        (EVENT_TAFSIR_OPEN, "Tafsir Open"),
        (EVENT_WORD_MEANINGS_OPEN, "Word Meanings Open"),
        (EVENT_SESSION_ACTIVE, "Session Active"),
        (EVENT_RECITATION_CORRECTION, "Recitation Correction"),
        (EVENT_DAILY_WIRD_OPEN, "Daily Wird Open"),
        (EVENT_LANGUAGE_CHANGE, "Language Change"),
    ]

    visitor = models.ForeignKey(
        AnalyticsVisitor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    event_type = models.CharField(max_length=50, choices=EVENT_CHOICES)
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
        ]

    def __str__(self):
        return self.event_type
