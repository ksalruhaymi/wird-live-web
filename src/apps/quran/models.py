from django.db import models
from django.conf import settings


class Surah(models.Model):
    MECCAN = "meccan"
    MEDINAN = "medinan"

    REVELATION_CHOICES = [
        (MECCAN, "مكية"),
        (MEDINAN, "مدنية"),
    ]

    surah_number = models.PositiveSmallIntegerField(
        unique=True,
        db_index=True,
    )
    surah_name_ar = models.CharField(max_length=100)
    surah_name_en = models.CharField(max_length=100, blank=True)

    page_start = models.PositiveSmallIntegerField(db_index=True)
    page_end = models.PositiveSmallIntegerField(db_index=True)

    ayah_count = models.PositiveSmallIntegerField()

    revelation_type = models.CharField(
        max_length=10,
        choices=REVELATION_CHOICES,
    )

    class Meta:
        ordering = ["surah_number"]
        indexes = [
            models.Index(fields=["page_start", "page_end"]),
        ]

    def __str__(self):
        return f"{self.surah_number} - {self.surah_name_ar}"


class Ayah(models.Model):
    surah = models.ForeignKey(
        "Surah",
        on_delete=models.CASCADE,
        related_name="ayat",
        null=True,
        blank=True,
    )

    surah_number = models.PositiveSmallIntegerField(db_index=True)
    ayah_number = models.PositiveSmallIntegerField(db_index=True)

    page_number = models.PositiveSmallIntegerField(db_index=True)
    juz_number = models.PositiveSmallIntegerField(db_index=True)

    text = models.TextField()

    class Meta:
        unique_together = ("surah_number", "ayah_number")
        ordering = ["surah_number", "ayah_number"]
        indexes = [
            models.Index(fields=["surah_number", "ayah_number"]),
            models.Index(fields=["page_number"]),
            models.Index(fields=["juz_number"]),
        ]

    def __str__(self):
        return f"{self.surah_number}:{self.ayah_number}"

    def save(self, *args, **kwargs):
        if self.surah and not self.surah_number:
            self.surah_number = self.surah.surah_number
        super().save(*args, **kwargs)


class AyahPosition(models.Model):
    ayah = models.ForeignKey(
        "Ayah",
        on_delete=models.CASCADE,
        related_name="positions",
        null=True,
        blank=True,
    )

    mushaf_key = models.CharField(
        max_length=20,
        default="hafs",
        db_index=True,
    )

    surah_number = models.SmallIntegerField(db_index=True)
    ayah_number = models.PositiveSmallIntegerField(db_index=True, null=True, blank=True)
    page_number = models.SmallIntegerField(db_index=True)

    x = models.FloatField()
    y = models.FloatField()
    width = models.FloatField()
    height = models.FloatField()

    polygon = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["mushaf_key", "page_number", "surah_number", "ayah_number"]
        indexes = [
            models.Index(fields=["mushaf_key", "page_number"]),
            models.Index(fields=["mushaf_key", "surah_number", "ayah_number"]),
            models.Index(fields=["page_number"]),
            models.Index(fields=["surah_number", "ayah_number"]),
        ]

    def __str__(self):
        return f"{self.mushaf_key} - {self.surah_number}:{self.ayah_number} (page {self.page_number})"


class Qurra(models.Model):
    code = models.CharField(max_length=100, unique=True)
    name_ar = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100)
    image = models.CharField(max_length=255)
    is_visible = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name_ar


class AudioListenEvent(models.Model):
    EVENT_PLAY = "play"
    EVENT_PAUSE = "pause"
    EVENT_ENDED = "ended"
    EVENT_PROGRESS_50 = "progress_50"

    EVENT_CHOICES = [
        (EVENT_PLAY, "Play"),
        (EVENT_PAUSE, "Pause"),
        (EVENT_ENDED, "Ended"),
        (EVENT_PROGRESS_50, "Progress 50%"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audio_listen_events",
        null=True,
        blank=True,
    )
    session_key = models.CharField(max_length=80, blank=True, db_index=True)

    mushaf_key = models.CharField(max_length=40, blank=True, db_index=True)
    qari_code = models.CharField(max_length=120, blank=True, db_index=True)

    surah_number = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    ayah_number = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    page_number = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)

    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES, db_index=True)
    current_time = models.FloatField(default=0)
    duration = models.FloatField(default=0)
    percent = models.PositiveSmallIntegerField(default=0, db_index=True)

    audio_src = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    country = models.CharField(max_length=2, blank=True, db_index=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at", "event_type"]),
            models.Index(fields=["qari_code", "event_type"]),
            models.Index(fields=["mushaf_key", "page_number"]),
            models.Index(fields=["surah_number", "ayah_number"]),
        ]

    def __str__(self):
        return f"{self.event_type} - {self.qari_code} - {self.surah_number}:{self.ayah_number}"


class TafsirBook(models.Model):
    number = models.PositiveSmallIntegerField(db_index=True)
    name = models.CharField(max_length=100)
    lang = models.CharField(max_length=100)
    api = models.CharField(max_length=100)
    image = models.CharField(
        max_length=255,
        blank=True,
    )
    author = models.CharField(max_length=255, blank=True)
    info = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=1, db_index=True)

    class Meta:
        ordering = ["sort_order", "number"]
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
        ]

    def __str__(self):
        return self.name


class Tafsir(models.Model):
    book = models.ForeignKey(
        "TafsirBook",
        on_delete=models.CASCADE,
        related_name="tafaseer",
    )

    ayah = models.ForeignKey(
        "Ayah",
        on_delete=models.CASCADE,
        related_name="tafaseer",
        null=True,
        blank=True,
    )

    surah_id = models.PositiveSmallIntegerField(db_index=True)
    ayah_number = models.PositiveSmallIntegerField(db_index=True)

    text = models.TextField()

    class Meta:
        unique_together = ("book", "surah_id", "ayah_number")
        indexes = [
            models.Index(fields=["book", "surah_id", "ayah_number"]),
            models.Index(fields=["book", "ayah"]),
        ]

    def __str__(self):
        return f"{self.book.lang} - {self.surah_id}:{self.ayah_number}"


class AyahWordMeaning(models.Model):
    ayah = models.ForeignKey(
        "Ayah",
        on_delete=models.CASCADE,
        related_name="word_meanings",
        null=True,
        blank=True,
    )

    surah_number = models.PositiveSmallIntegerField(db_index=True)
    ayah_number = models.PositiveSmallIntegerField(db_index=True)

    word = models.CharField(max_length=255)
    word_plain = models.CharField(max_length=255, blank=True)
    meaning = models.TextField()

    sort_order = models.PositiveSmallIntegerField(default=1, db_index=True)

    class Meta:
        ordering = ["surah_number", "ayah_number", "sort_order", "id"]
        indexes = [
            models.Index(fields=["surah_number", "ayah_number"]),
            models.Index(fields=["ayah"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["surah_number", "ayah_number", "sort_order"],
                name="unique_word_meaning_order_per_ayah",
            )
        ]

    def __str__(self):
        return f"{self.surah_number}:{self.ayah_number} - {self.word}"


class AyahTranslation(models.Model):
    surah_number = models.PositiveSmallIntegerField(db_index=True)
    ayah_number = models.PositiveSmallIntegerField(db_index=True)
    language = models.CharField(max_length=10, db_index=True)
    translation = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["surah_number", "ayah_number", "language"],
                name="unique_ayah_translation",
            )
        ]
        indexes = [
            models.Index(fields=["language"]),
            models.Index(fields=["surah_number", "ayah_number"]),
            models.Index(fields=["language", "surah_number"]),
        ]
        ordering = ["surah_number", "ayah_number"]

    def __str__(self):
        return f"{self.language} - {self.surah_number}:{self.ayah_number}"


class KhatmaProgress(models.Model):
    START_FROM_BEGINNING = "beginning"
    START_CHOICES = [(START_FROM_BEGINNING, "Beginning of Mushaf")]

    # Daily amount types — rub3-level and juz-level
    DAILY_AMOUNT_CHOICES = [
        ("rub3",  "ربع"),
        ("2rub3", "ربعان"),
        ("3rub3", "3 أرباع"),
        ("hizb",  "حزب"),
        ("5rub3", "5 أرباع"),
        ("6rub3", "6 أرباع"),
        ("7rub3", "7 أرباع"),
        ("juz",   "جزء"),
        ("2juz",  "جزءان"),
        ("3juz",  "3 أجزاء"),
        ("4juz",  "4 أجزاء"),
        ("5juz",  "5 أجزاء"),
        ("6juz",  "6 أجزاء"),
        ("7juz",  "7 أجزاء"),
        ("8juz",  "8 أجزاء"),
        ("9juz",  "9 أجزاء"),
        ("10juz", "10 أجزاء"),
    ]

    # Pages per wird for each amount type (Hafs = 604 pages)
    AMOUNT_PAGES = {
        "rub3": 3, "2rub3": 5, "3rub3": 8, "hizb": 10,
        "5rub3": 13, "6rub3": 15, "7rub3": 18,
        "juz": 20, "2juz": 40, "3juz": 60, "4juz": 80,
        "5juz": 100, "6juz": 120, "7juz": 140,
        "8juz": 160, "9juz": 180, "10juz": 200,
    }

    TRACKING_AUTO   = "auto"
    TRACKING_MANUAL = "manual"
    TRACKING_CHOICES = [
        (TRACKING_AUTO,   "Auto"),
        (TRACKING_MANUAL, "Manual"),
    ]

    WIRD_NOT_STARTED = "not_started"
    WIRD_IN_PROGRESS = "in_progress"
    WIRD_COMPLETED   = "completed"
    WIRD_STATUS_CHOICES = [
        (WIRD_NOT_STARTED, "Not Started"),
        (WIRD_IN_PROGRESS, "In Progress"),
        (WIRD_COMPLETED,   "Completed"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="khatma_progress",
    )

    khatma_count      = models.PositiveIntegerField(default=0)
    is_active         = models.BooleanField(default=False)
    tracking_mode     = models.CharField(max_length=10, choices=TRACKING_CHOICES, default=TRACKING_MANUAL)
    wird_status       = models.CharField(max_length=20, choices=WIRD_STATUS_CHOICES, default=WIRD_NOT_STARTED)

    start_mode        = models.CharField(max_length=30, choices=START_CHOICES, default=START_FROM_BEGINNING)
    duration_days     = models.PositiveSmallIntegerField(default=30)
    daily_amount_type = models.CharField(max_length=10, choices=DAILY_AMOUNT_CHOICES, default="juz")
    daily_amount_value = models.PositiveSmallIntegerField(default=1)

    current_wird_number    = models.PositiveSmallIntegerField(default=1)
    total_wirds            = models.PositiveSmallIntegerField(default=30)
    current_wird_start_page = models.PositiveSmallIntegerField(default=1)
    current_wird_end_page  = models.PositiveSmallIntegerField(default=20)
    current_page           = models.PositiveSmallIntegerField(default=1)

    start_surah_number = models.PositiveSmallIntegerField(default=1)
    start_ayah_number  = models.PositiveSmallIntegerField(default=1)
    end_surah_number   = models.PositiveSmallIntegerField(default=2)
    end_ayah_number    = models.PositiveSmallIntegerField(default=141)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Khatma Progress"
        verbose_name_plural = "Khatma Progress"

    def __str__(self):
        return f"{self.user} - Khatma #{self.khatma_count + 1}"

    @classmethod
    def pages_for_amount(cls, amount_type):
        return cls.AMOUNT_PAGES.get(amount_type, 20)

    @classmethod
    def amount_label_for_days(cls, duration_days):
        """Return the closest daily_amount_type label for a given duration."""
        import math
        pages = math.ceil(604 / max(duration_days, 1))
        best = "juz"
        best_diff = float("inf")
        for key, page_val in cls.AMOUNT_PAGES.items():
            diff = abs(page_val - pages)
            if diff < best_diff:
                best_diff = diff
                best = key
        return best

    @property
    def current_khatma_percent(self):
        if self.total_wirds <= 0:
            return 0
        completed = max(self.current_wird_number - 1, 0)
        return int((completed / self.total_wirds) * 100)

    @property
    def wird_progress_percent(self):
        """Completion % of the current wird based on current_page."""
        span = self.current_wird_end_page - self.current_wird_start_page
        if span <= 0:
            return 100 if self.wird_status == self.WIRD_COMPLETED else 0
        done = max(self.current_page - self.current_wird_start_page, 0)
        return min(int((done / span) * 100), 100)