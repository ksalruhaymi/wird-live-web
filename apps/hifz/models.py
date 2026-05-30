from django.conf import settings
from django.db import models
from apps.quran.models import Ayah


class MemorizationStatus(models.TextChoices):
    NEW = "new", "New"
    MEMORIZED = "memorized", "Memorized"
    REVIEW = "review", "Review"


class MemorizedAyah(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memorized_ayahs",
    )
    ayah = models.ForeignKey(
        Ayah,
        on_delete=models.CASCADE,
        related_name="memorization_records",
    )

    status = models.CharField(
        max_length=20,
        choices=MemorizationStatus.choices,
        default=MemorizationStatus.NEW,
    )
    revealed = models.BooleanField(default=False)
    reveal_count = models.PositiveIntegerField(default=0)
    last_revealed_at = models.DateTimeField(null=True, blank=True)
    memorized_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "ayah")
        ordering = ["ayah__surah_number", "ayah__ayah_number"]

    def __str__(self):
        return f"{self.user} - {self.ayah}"


class RecitationAttempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recitation_attempts",
    )
    ayah = models.ForeignKey(
        Ayah,
        on_delete=models.CASCADE,
        related_name="recitation_attempts",
    )
    expected_text = models.TextField()
    recognized_text = models.TextField(blank=True, default="")
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_correct = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ThematicTopic(models.Model):
    source_id = models.PositiveSmallIntegerField(unique=True, db_index=True)
    color_id = models.PositiveSmallIntegerField(db_index=True)
    color_name_ar = models.CharField(max_length=50)
    color_hex = models.CharField(max_length=20)
    topic_id = models.PositiveSmallIntegerField(unique=True, db_index=True)
    topic_ar = models.CharField(max_length=255)

    class Meta:
        ordering = ["color_id", "topic_id"]
        indexes = [
            models.Index(fields=["color_id", "topic_id"]),
            models.Index(fields=["topic_id"]),
        ]
        verbose_name = "Thematic Topic"
        verbose_name_plural = "Thematic Topics"

    def __str__(self):
        return f"{self.topic_id} - {self.topic_ar}"


class AyahThematicClassification(models.Model):
    topic = models.ForeignKey(
        ThematicTopic,
        on_delete=models.PROTECT,
        related_name="ayah_classifications",
    )
    surah_number = models.PositiveSmallIntegerField(db_index=True)
    ayah_from = models.PositiveSmallIntegerField(db_index=True)
    ayah_to = models.PositiveSmallIntegerField(db_index=True)
    topic_text = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["surah_number", "ayah_from", "ayah_to", "topic__topic_id"]
        indexes = [
            models.Index(fields=["surah_number", "ayah_from", "ayah_to"]),
            models.Index(fields=["surah_number", "ayah_from"]),
            models.Index(fields=["topic", "surah_number"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["surah_number", "ayah_from", "ayah_to", "topic"],
                name="unique_hifz_ayah_thematic_range",
            ),
            models.CheckConstraint(
                condition=models.Q(ayah_to__gte=models.F("ayah_from")),
                name="hifz_ayah_thematic_valid_range",
            ),
        ]
        verbose_name = "Ayah Thematic Classification"
        verbose_name_plural = "Ayah Thematic Classifications"

    def __str__(self):
        return f"{self.surah_number}:{self.ayah_from}-{self.ayah_to} - {self.topic.topic_ar}"
