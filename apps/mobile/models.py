from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class MobileAppConfig(models.Model):
    """Singleton remote control settings for legacy mobile clients / middleware."""

    # Legacy shared flag — kept for older rows/clients; not the decision source.
    app_enabled = models.BooleanField(default=True)
    android_app_enabled = models.BooleanField(default=True)
    ios_app_enabled = models.BooleanField(default=True)
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

    def is_enabled_for_platform(self, platform: str) -> bool:
        """Return the kill-switch for one platform (never the shared legacy flag)."""
        value = (platform or "").strip().lower()
        if value == MobilePlatform.ANDROID:
            return bool(self.android_app_enabled)
        if value == MobilePlatform.IOS:
            return bool(self.ios_app_enabled)
        # Unknown platform: fall back to legacy field for old clients only.
        return bool(self.app_enabled)

    def set_enabled_for_platform(self, platform: str, enabled: bool) -> None:
        value = (platform or "").strip().lower()
        if value == MobilePlatform.ANDROID:
            self.android_app_enabled = bool(enabled)
            self.save(update_fields=["android_app_enabled", "updated_at"])
            return
        if value == MobilePlatform.IOS:
            self.ios_app_enabled = bool(enabled)
            self.save(update_fields=["ios_app_enabled", "updated_at"])
            return
        raise ValueError(f"unsupported platform: {platform}")


class MobilePlatform(models.TextChoices):
    ANDROID = "android", "Android"
    IOS = "ios", "iOS"


class UpdateMode(models.TextChoices):
    NONE = "none", "بدون تحديث"
    OPTIONAL = "optional", "تحديث اختياري"
    REQUIRED = "required", "تحديث إجباري"


class MobileAppVersion(models.Model):
    """Published mobile app version policy per platform."""

    platform = models.CharField(
        max_length=16,
        choices=MobilePlatform.choices,
        db_index=True,
        verbose_name="المنصة",
    )
    version_name = models.CharField(max_length=32, verbose_name="رقم الإصدار")
    build_number = models.PositiveIntegerField(verbose_name="رقم البناء")
    minimum_version_name = models.CharField(
        max_length=32,
        blank=True,
        default="",
        verbose_name="أقل إصدار مدعوم",
    )
    minimum_build_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="أقل رقم بناء مدعوم",
    )
    update_mode = models.CharField(
        max_length=16,
        choices=UpdateMode.choices,
        default=UpdateMode.NONE,
        verbose_name="نوع التحديث",
    )
    is_active = models.BooleanField(default=False, verbose_name="نشط", db_index=True)
    update_title_ar = models.CharField(max_length=255, blank=True, default="")
    update_title_en = models.CharField(max_length=255, blank=True, default="")
    update_message_ar = models.TextField(blank=True, default="")
    update_message_en = models.TextField(blank=True, default="")
    release_notes_ar = models.TextField(blank=True, default="")
    release_notes_en = models.TextField(blank=True, default="")
    store_url = models.URLField(max_length=500, blank=True, default="")
    allow_later = models.BooleanField(default=True, verbose_name="السماح بالتأجيل")
    later_reminder_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        default=24,
        verbose_name="ساعات إعادة التذكير",
    )
    starts_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="تاريخ بدء التطبيق",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_mobile_app_versions",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_mobile_app_versions",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "إصدار تطبيق"
        verbose_name_plural = "إصدارات التطبيق"
        indexes = [
            models.Index(fields=["platform", "is_active"]),
            models.Index(fields=["platform", "-build_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.platform} {self.version_name} ({self.build_number})"

    def clean(self):
        errors = {}
        if self.build_number is None or self.build_number < 1:
            errors["build_number"] = "رقم البناء يجب أن يكون 1 أو أكثر."

        if self.minimum_build_number is not None:
            if self.minimum_build_number < 1:
                errors["minimum_build_number"] = "أقل رقم بناء يجب أن يكون 1 أو أكثر."
            elif self.build_number is not None and self.minimum_build_number > self.build_number:
                errors["minimum_build_number"] = (
                    "أقل رقم بناء لا يمكن أن يكون أكبر من رقم البناء."
                )

        if self.update_mode == UpdateMode.REQUIRED:
            if self.allow_later:
                errors["allow_later"] = "لا يمكن السماح بالتأجيل مع التحديث الإجباري."
            if self.later_reminder_hours:
                errors["later_reminder_hours"] = (
                    "ساعات التذكير لا تُستخدم مع التحديث الإجباري."
                )

        if self.update_mode != UpdateMode.OPTIONAL:
            # Allow empty later hours for required/none.
            pass
        elif not self.allow_later and self.later_reminder_hours:
            errors["later_reminder_hours"] = (
                "لا تستخدم ساعات التذكير إلا عند تفعيل السماح بالتأجيل."
            )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.update_mode == UpdateMode.REQUIRED:
            self.allow_later = False
            self.later_reminder_hours = None
        elif self.update_mode == UpdateMode.NONE:
            self.allow_later = False
            self.later_reminder_hours = None
        elif not self.allow_later:
            self.later_reminder_hours = None
        self.full_clean()
        return super().save(*args, **kwargs)


class BlockedMobileAppVersion(models.Model):
    """Specific build numbers that must be blocked from using the app."""

    platform = models.CharField(
        max_length=16,
        choices=MobilePlatform.choices,
        db_index=True,
        verbose_name="المنصة",
    )
    version_name = models.CharField(max_length=32, blank=True, default="")
    build_number = models.PositiveIntegerField(verbose_name="رقم البناء")
    reason_ar = models.TextField(blank=True, default="")
    reason_en = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_blocked_mobile_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "إصدار محظور"
        verbose_name_plural = "الإصدارات المحظورة"
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "build_number"],
                name="uniq_blocked_mobile_platform_build",
            ),
        ]

    def __str__(self) -> str:
        return f"blocked {self.platform} build={self.build_number}"

    def clean(self):
        if self.build_number is None or self.build_number < 1:
            raise ValidationError({"build_number": "رقم البناء يجب أن يكون 1 أو أكثر."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
