from django.conf import settings
from django.db import models


class TeacherProfile(models.Model):
    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "قيد المراجعة"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_profile",
    )
    display_name = models.CharField(max_length=255, blank=True)
    bio = models.TextField(blank=True)
    is_available = models.BooleanField(default=False)
    is_approved = models.BooleanField(
        default=False,
        help_text="Legacy flag; kept in sync with approval_status=approved.",
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )
    rejection_reason = models.TextField(blank=True, default="")
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_approvals_granted",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teacher_approvals_rejected",
    )
    can_audio = models.BooleanField(default=True)
    can_video = models.BooleanField(default=True)
    auto_accept_calls = models.BooleanField(
        default=False,
        help_text="When true, student calls are accepted immediately without teacher action.",
    )
    riwayat = models.TextField(blank=True, help_text="Quranic recitation traditions the teacher knows")
    ijazah = models.FileField(
        upload_to="teacher_ijazah/",
        blank=True,
        null=True,
        help_text="Teacher Quran ijazah certificate",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tutoring_teacherprofile"
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
    riwayat = models.TextField(
        blank=True,
        help_text="Quranic recitation tradition (الرواية)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tutoring_studentprofile"
        verbose_name = "Student profile"
        verbose_name_plural = "Student profiles"

    def __str__(self):
        return self.display_name or self.user.username


class TutoringSession(models.Model):
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
        related_name="tutoring_sessions_as_student",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tutoring_sessions_as_teacher",
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
        db_table = "tutoring_session"
        ordering = ["-created_at"]
        verbose_name = "Tutoring session"
        verbose_name_plural = "Tutoring sessions"

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
        db_table = "tutoring_teacheravailability"
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
        db_table = "tutoring_teacherfavorite"
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
