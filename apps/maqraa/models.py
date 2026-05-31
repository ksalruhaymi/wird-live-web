from django.conf import settings
from django.db import models


class TeacherProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
    )
    display_name = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)
    is_available = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    can_audio = models.BooleanField(default=True)
    can_video = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Teacher profile"
        verbose_name_plural = "Teacher profiles"

    def __str__(self):
        return self.display_name or self.user.username


class StudentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    display_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student profile"
        verbose_name_plural = "Student profiles"

    def __str__(self):
        return self.display_name or self.user.username


class MaqraaSession(models.Model):
    class SessionType(models.TextChoices):
        AUDIO = "audio", "Audio"
        VIDEO = "video", "Video"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        ACCEPTED = "accepted", "Accepted"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REJECTED = "rejected", "Rejected"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="maqraa_sessions_as_student",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="maqraa_sessions_as_teacher",
    )
    session_type = models.CharField(
        max_length=10,
        choices=SessionType.choices,
        default=SessionType.AUDIO,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.REQUESTED,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Maqraa session"
        verbose_name_plural = "Maqraa sessions"

    def __str__(self):
        return f"{self.student_id} → {self.teacher_id} ({self.status})"


class TeacherAvailability(models.Model):
    class Status(models.TextChoices):
        ONLINE = "online", "متاح"
        BUSY = "busy", "مشغول"
        OFFLINE = "offline", "غير متصل"

    teacher = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_availability",
        verbose_name="المعلّم",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OFFLINE,
        verbose_name="الحالة",
    )
    last_seen = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "حالة المعلّم"
        verbose_name_plural = "حالات المعلّمين"

    def __str__(self):
        return f"{self.teacher_id} ({self.status})"


class TeacherFavorite(models.Model):
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorite_teachers",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorited_by_students",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "معلّم مفضّل"
        verbose_name_plural = "المعلّمون المفضّلون"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "teacher"],
                name="uniq_student_teacher_favorite",
            )
        ]

    def __str__(self):
        return f"student={self.student_id} teacher={self.teacher_id}"
