
from django.conf import settings
from django.db import models
from django.utils import timezone


class MessageChannel(models.TextChoices):
    EMAIL = "email", "بريد إلكتروني"
    SMS = "sms", "رسالة جوال"
    WHATSAPP = "whatsapp", "واتساب"


class MessageLevel(models.TextChoices):
    INFO = "info", "Info"
    SUCCESS = "success", "Success"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


class MessageStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending"
    SENDING = "sending", "Sending"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"


class MessageBroadcast(models.Model):
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    channel = models.CharField(
        max_length=20,
        choices=MessageChannel.choices,
        default=MessageChannel.EMAIL,
    )
    level = models.CharField(
        max_length=20,
        choices=MessageLevel.choices,
        default=MessageLevel.INFO,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_broadcasts_created",
    )
    recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="message_broadcasts_received",
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=MessageStatus.choices,
        default=MessageStatus.DRAFT,
    )
    failed_recipients = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "رسالة جماعية"
        verbose_name_plural = "الرسائل الجماعية"
        db_table = "notification_notificationbroadcast"

    def __str__(self):
        return self.title


class MessageDelivery(models.Model):
    broadcast = models.ForeignKey(
        MessageBroadcast,
        on_delete=models.CASCADE,
        related_name="deliveries",
        db_column="broadcast_id",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_deliveries_received",
    )
    email = models.EmailField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )
    error_message = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "تسليم رسالة"
        verbose_name_plural = "تسليمات الرسائل"
        unique_together = ("broadcast", "user")
        db_table = "notification_notificationdelivery"

    def __str__(self):
        return f"{self.email or self.user_id} - {self.status}"

    def save(self, *args, **kwargs):
        if not self.email and self.user_id and getattr(self.user, "email", None):
            self.email = self.user.email
        super().save(*args, **kwargs)

