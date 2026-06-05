from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationChannel(models.TextChoices):
    IN_APP = "in_app", "داخل النظام"


class NotificationLevel(models.TextChoices):
    INFO = "info", "Info"
    SUCCESS = "success", "Success"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications_received",
    )
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True, default="")
    channel = models.CharField(
        max_length=20,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
    )
    level = models.CharField(
        max_length=20,
        choices=NotificationLevel.choices,
        default=NotificationLevel.INFO,
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تنبيه"
        verbose_name_plural = "التنبيهات"

    def __str__(self):
        return self.title

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])


class AppNotificationTargetType(models.TextChoices):
    ALL = "all", "جميع المستخدمين"


class AppNotification(models.Model):
    """Admin-defined in-app notification shown to mobile users."""

    title = models.CharField(max_length=255)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    target_type = models.CharField(
        max_length=20,
        choices=AppNotificationTargetType.choices,
        default=AppNotificationTargetType.ALL,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="app_notifications_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "تنبيه التطبيق"
        verbose_name_plural = "تنبيهات التطبيق"

    def __str__(self):
        return self.title


class AppNotificationRead(models.Model):
    """Per-user read state for app notifications."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="app_notification_reads",
    )
    notification = models.ForeignKey(
        AppNotification,
        on_delete=models.CASCADE,
        related_name="reads",
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "notification"],
                name="uniq_app_notification_read_user_notification",
            ),
        ]
        verbose_name = "قراءة تنبيه التطبيق"
        verbose_name_plural = "قراءات تنبيهات التطبيق"

    def __str__(self):
        return f"{self.user_id} read {self.notification_id}"