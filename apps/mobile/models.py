from django.db import models


class MobileAppConfig(models.Model):
    """Singleton remote control settings for test APK builds."""

    app_enabled = models.BooleanField(default=True)
    min_supported_version = models.CharField(max_length=32, default="1.0.0")
    min_supported_build = models.PositiveIntegerField(default=1)
    force_update = models.BooleanField(default=False)
    message = models.TextField(
        default="هذه النسخة التجريبية انتهت. فضلاً حمّل النسخة الجديدة.",
    )
    update_url = models.URLField(max_length=500, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mobile app config"
        verbose_name_plural = "Mobile app config"

    def __str__(self) -> str:
        return "Mobile app config"

    @classmethod
    def get_settings(cls) -> "MobileAppConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
