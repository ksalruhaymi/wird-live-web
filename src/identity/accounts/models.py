from django.contrib.auth.models import AbstractUser
from django.db import models

from core.services.phone_service import normalize_phone_number
from core.validators import validate_phone


class User(AbstractUser):
    """
    Custom User model.
    """

    GENDER_CHOICES = (
        ("male", "ذكر"),
        ("female", "أنثى"),
    )

    full_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Full legal name of the user",
    )

    mobile = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        validators=[validate_phone],
    )

    job_title = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        blank=True,
        null=True,
    )

    user_type = models.PositiveSmallIntegerField(
        default=3,
    )

    created_by = models.IntegerField(
        blank=True,
        null=True,
    )

    roles = models.ManyToManyField(
        "rbac.Role",
        related_name="users",
        blank=True,
    )

    def save(self, *args, **kwargs):
        if self.mobile:
            self.mobile = normalize_phone_number(self.mobile, "SA")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username

    def has_role(self, slug: str) -> bool:
        return self.roles.filter(slug=slug).exists()

    def has_permission(self, code: str) -> bool:
        if self.is_superuser:
            return True
        return self.roles.filter(permissions__code=code).exists()


class SystemAuthSettings(models.Model):
    allow_db_login = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "System Authentication Settings"

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj