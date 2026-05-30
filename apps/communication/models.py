from django.conf import settings
from django.db import models


class CommunicationChannel(models.TextChoices):
    X = "x", "منصة X"
    FACEBOOK = "facebook", "فيسبوك"
    TELEGRAM_GROUP = "telegram_group", "تيليجرام - قروب"
    TELEGRAM_CHANNEL = "telegram_channel", "تيليجرام - قناة"


class CommunicationCampaign(models.Model):
    title = models.CharField(max_length=255)
    message = models.TextField()
    image = models.ImageField(upload_to="campaigns/", null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="communication_campaigns",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    scheduled_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        SCHEDULED = "scheduled", "مجدولة"
        SENDING = "sending", "قيد الإرسال"
        SENT = "sent", "تم الإرسال"
        FAILED = "failed", "فشل"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    def __str__(self):
        return self.title


class CommunicationCampaignChannel(models.Model):
    campaign = models.ForeignKey(
        CommunicationCampaign,
        on_delete=models.CASCADE,
        related_name="channels",
    )
    channel = models.CharField(
        max_length=30,
        choices=CommunicationChannel.choices,
    )

    is_enabled = models.BooleanField(default=True)

    class SendStatus(models.TextChoices):
        PENDING = "pending", "في الانتظار"
        SENT = "sent", "أُرسلت"
        FAILED = "failed", "فشل الإرسال"

    send_status = models.CharField(
        max_length=20,
        choices=SendStatus.choices,
        default=SendStatus.PENDING,
    )

    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    def __str__(self):
        return f"{self.campaign.title} → {self.get_channel_display()}"