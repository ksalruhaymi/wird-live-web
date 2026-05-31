from django.conf import settings
from django.db import models


class CallSession(models.Model):
    class SessionType(models.TextChoices):
        AUDIO = "audio", "صوتي"
        VIDEO = "video", "مرئي"

    class Provider(models.TextChoices):
        MOCK = "mock", "Mock"
        AGORA = "agora", "Agora"
        LIVEKIT = "livekit", "LiveKit"
        JITSI = "jitsi", "Jitsi"
        WEBRTC = "webrtc", "WebRTC"

    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار المعلم"
        ACTIVE = "active", "نشط"
        ENDED = "ended", "منتهي"
        REJECTED = "rejected", "مرفوض"
        MISSED = "missed", "لم يتم الرد"
        CANCELLED = "cancelled", "ملغي"

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_sessions_as_student",
        verbose_name="الطالب",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="call_sessions_as_teacher",
        verbose_name="المعلّم",
    )
    session_type = models.CharField(
        max_length=10,
        choices=SessionType.choices,
        verbose_name="نوع الاتصال",
    )
    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        default=Provider.MOCK,
        verbose_name="المزود",
    )
    room_name = models.CharField(max_length=128, blank=True, default="")
    channel_name = models.CharField(max_length=128, blank=True, default="")
    token = models.CharField(max_length=512, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="الحالة",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "جلسة اتصال"
        verbose_name_plural = "جلسات الاتصال"

    def __str__(self):
        return f"call_{self.pk} ({self.session_type})"


class SessionEvaluation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار التقييم"
        COMPLETED = "completed", "تم التقييم"

    call_session = models.OneToOneField(
        CallSession,
        on_delete=models.CASCADE,
        related_name="evaluation",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="session_evaluations_as_student",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="session_evaluations_as_teacher",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    focus_level = models.PositiveSmallIntegerField(null=True, blank=True)
    pages_count = models.CharField(max_length=255, blank=True, default="")
    surah = models.CharField(max_length=255, blank=True, default="")
    memorization = models.TextField(blank=True, default="")
    consolidation = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "تقييم جلسة"
        verbose_name_plural = "تقييمات الجلسات"

    def __str__(self):
        return f"eval_call_{self.call_session_id}"


class CallRecording(models.Model):
    call_session = models.OneToOneField(
        CallSession,
        on_delete=models.CASCADE,
        related_name="recording",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_recordings_as_student",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_recordings_as_teacher",
    )
    session_type = models.CharField(max_length=10)
    recording_url = models.URLField(max_length=500, blank=True, default="")
    duration_seconds = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    provider_recording_id = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "تسجيل مكالمة"
        verbose_name_plural = "تسجيلات المكالمات"

    def __str__(self):
        return f"recording_call_{self.call_session_id}"
