from django.conf import settings
from django.db import models


class ContactMessage(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "جديدة"
        READ = "read", "تمت القراءة"
        REPLIED = "replied", "تم الرد"

    class Source(models.TextChoices):
        WEB = "web", "موقع الويب"
        APP = "app", "تطبيق جوال"

    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    message = models.TextField()

    source = models.CharField(
        max_length=10,
        choices=Source.choices,
        default=Source.WEB,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )

    is_read = models.BooleanField(default=False)
    reply_subject = models.CharField(max_length=200, blank=True)
    reply_body = models.TextField(blank=True)
    replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contact_replies",
    )
    replied_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.full_name} - {self.email}"
