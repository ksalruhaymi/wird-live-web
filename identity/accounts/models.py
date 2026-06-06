from django.contrib.auth.models import AbstractUser
from django.db import models

from core.services.phone_service import normalize_phone_number
from core.validators import validate_phone
from identity.accounts.user_types import USER_TYPE_SUPERVISOR


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

    national_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text="National ID (رقم الهوية); mobile may use username until sent explicitly",
    )

    qualification = models.CharField(
        max_length=255,
        blank=True,
        help_text="Educational qualification (المؤهل الدراسي)",
    )

    birth_date = models.DateField(
        null=True,
        blank=True,
        help_text="Date of birth (تاريخ الميلاد)",
    )

    enrollment_track = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Enrollment track index 0–4 from mobile register step 2",
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
        default=USER_TYPE_SUPERVISOR,
        help_text="1=admin, 3=supervisor, 5=teacher, 9=student",
    )

    firebase_uid = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        unique=True,
        help_text="Firebase Authentication UID for Google/mobile sign-in",
    )

    profile_image = models.ImageField(
        upload_to="profile_images/",
        blank=True,
        null=True,
        help_text="User profile photo",
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


class EmailRegistrationVerification(models.Model):
    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=128)
    verification_token = models.CharField(max_length=64, blank=True, null=True, unique=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(blank=True, null=True)
    token_expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["email", "-created_at"]),
        ]

    def __str__(self):
        return f"Email verification for {self.email}"