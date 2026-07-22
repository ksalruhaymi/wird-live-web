from django.conf import settings
from django.db import models


class UserDevice(models.Model):
    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="devices",
        verbose_name="المستخدم",
    )
    fcm_token = models.TextField(unique=True, verbose_name="FCM Token")
    voip_token = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        verbose_name="VoIP Token (iOS PushKit)",
    )
    platform = models.CharField(
        max_length=10,
        choices=Platform.choices,
        verbose_name="المنصة",
    )
    device_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="معرّف الجهاز",
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name="آخر ظهور")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "جهاز"
        verbose_name_plural = "الأجهزة"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_active"], name="push_dev_user_active_idx"),
            models.Index(fields=["user", "device_id"], name="push_dev_user_devid_idx"),
            models.Index(fields=["is_active", "last_seen_at"], name="push_dev_active_seen_idx"),
        ]

    def __str__(self):
        return f"{self.get_platform_display()} — {self.fcm_token[:24]}…"


class PushBroadcast(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "في الانتظار"
        SENT = "sent", "تم الإرسال"
        FAILED = "failed", "فشل"

    title = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    total_devices = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    removed_count = models.PositiveIntegerField(default=0)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="push_broadcasts",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "بث إشعار"
        verbose_name_plural = "سجل الإشعارات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
