from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q

from core.services.phone_service import normalize_phone_number
from core.validators import validate_phone
from identity.accounts.user_types import USER_TYPE_SUPERVISOR


class User(AbstractUser):
    """
    Custom User model.
    """

    class DemoRole(models.TextChoices):
        ADMIN = "admin", "مشرف تجريبي"
        STUDENT = "student", "طالب تجريبي"
        TEACHER = "teacher", "معلم تجريبي"

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

    active_session_key = models.CharField(
        max_length=40,
        blank=True,
        default="",
        db_index=True,
        help_text="Current Django session key for single-device login (admins exempt).",
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

    is_demo_account = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Protected trial/demo account; excluded from bulk trial cleanup.",
    )
    demo_role = models.CharField(
        max_length=20,
        choices=DemoRole.choices,
        blank=True,
        null=True,
        help_text="Demo account kind when is_demo_account=True.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["demo_role"],
                condition=Q(is_demo_account=True, demo_role__isnull=False),
                name="uniq_demo_account_per_role",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.mobile:
            self.mobile = normalize_phone_number(self.mobile, "SA")
        if not self.is_demo_account:
            self.demo_role = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username

    def has_role(self, slug: str) -> bool:
        return self.roles.filter(slug=slug).exists()

    def has_permission(self, code: str) -> bool:
        if self.is_superuser:
            return True
        from identity.rbac.resolver import user_has_permission

        return user_has_permission(self, code)


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


class PasswordResetCode(models.Model):
    """One-time password-reset OTP + temporary reset token (hashed at rest)."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="password_reset_codes",
        verbose_name="المستخدم",
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(blank=True, null=True)
    used_at = models.DateTimeField(blank=True, null=True)
    attempts_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    reset_token_hash = models.CharField(max_length=128, blank=True, default="")
    reset_token_expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["expires_at"]),
        ]
        verbose_name = "رمز استعادة كلمة المرور"
        verbose_name_plural = "رموز استعادة كلمة المرور"

    def __str__(self):
        return f"Password reset for user={self.user_id}"

