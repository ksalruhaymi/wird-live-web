from uuid import uuid4

from django.db import models


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True, verbose_name="البريد الإلكتروني")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_confirmed = models.BooleanField(default=True, verbose_name="تم التأكيد")
    unsubscribe_token = models.UUIDField(default=uuid4, unique=True, editable=False)
    subscribed_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الاشتراك")
    unsubscribed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ إلغاء الاشتراك")

    class Meta:
        ordering = ["-subscribed_at"]
        verbose_name = "مشترك نشرة بريدية"
        verbose_name_plural = "مشتركو النشرة البريدية"

    def __str__(self):
        return self.email