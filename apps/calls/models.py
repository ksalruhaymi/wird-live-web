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
        ENDING = "ending", "جاري الإنهاء"
        ENDED = "ended", "منتهي"
        REJECTED = "rejected", "مرفوض"
        MISSED = "missed", "لم يتم الرد"
        CANCELLED = "cancelled", "ملغي"
        FAILED = "failed", "فشل"

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
    end_requested_at = models.DateTimeField(null=True, blank=True)
    end_reason = models.CharField(max_length=64, blank=True, default="")
    end_error = models.CharField(max_length=255, blank=True, default="")
    last_heartbeat_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_interview_call = models.BooleanField(
        default=False,
        verbose_name="مقابلة إدارة (مكالمة معلم جديد)",
    )
    minutes_charged = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="دقائق مخصومة من الرصيد",
    )

    TERMINAL_STATUSES = frozenset(
        {
            Status.ENDED,
            Status.REJECTED,
            Status.MISSED,
            Status.CANCELLED,
            Status.FAILED,
        }
    )

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    @property
    def blocks_new_calls(self) -> bool:
        """Whether this session should keep the teacher busy."""
        return self.status in {self.Status.ACTIVE, self.Status.ENDING}

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


class CallPeerRating(models.Model):
    class RaterRole(models.TextChoices):
        STUDENT = "student", "طالب"
        TEACHER = "teacher", "معلّم"

    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار التقييم"
        COMPLETED = "completed", "تم التقييم"

    call_session = models.ForeignKey(
        CallSession,
        on_delete=models.CASCADE,
        related_name="peer_ratings",
    )
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_ratings_given",
    )
    rated = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_ratings_received",
    )
    rater_role = models.CharField(
        max_length=10,
        choices=RaterRole.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    competence = models.PositiveSmallIntegerField(null=True, blank=True)
    clarity = models.PositiveSmallIntegerField(null=True, blank=True)
    audio_quality = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "تقييم طرف المكالمة"
        verbose_name_plural = "تقييمات أطراف المكالمات"
        constraints = [
            models.UniqueConstraint(
                fields=["call_session", "rater"],
                name="calls_callpeerrating_unique_call_rater",
            ),
        ]

    def __str__(self):
        return f"rating_call_{self.call_session_id}_{self.rater_role}"


class RatingQuestion(models.Model):
    class Category(models.TextChoices):
        TEACHER = "teacher", "تقييم المعلم"
        STUDENT = "student", "تقييم الطالب"
        DEMO_TEACHER = "demo_teacher", "تقييم المعلم التجريبي"

    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        verbose_name="نوع التقييم",
    )
    question_text = models.CharField(max_length=500, verbose_name="نص السؤال")
    order = models.PositiveSmallIntegerField(default=1, verbose_name="الترتيب")
    is_active = models.BooleanField(default=True, verbose_name="مفعّل")
    max_stars = models.PositiveSmallIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "order", "id"]
        verbose_name = "سؤال تقييم"
        verbose_name_plural = "أسئلة التقييم"

    def __str__(self):
        return f"{self.get_category_display()}: {self.question_text[:40]}"


class RatingCategoryConfig(models.Model):
    category = models.CharField(
        max_length=20,
        choices=RatingQuestion.Category.choices,
        unique=True,
        verbose_name="نوع التقييم",
    )
    is_active = models.BooleanField(default=True, verbose_name="مفعّل")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعداد نوع التقييم"
        verbose_name_plural = "إعدادات أنواع التقييم"

    def __str__(self):
        return f"{self.get_category_display()} ({'active' if self.is_active else 'inactive'})"


class CallPeerRatingAnswer(models.Model):
    rating = models.ForeignKey(
        CallPeerRating,
        on_delete=models.CASCADE,
        related_name="answers",
    )
    question = models.ForeignKey(
        RatingQuestion,
        on_delete=models.PROTECT,
        related_name="answers",
    )
    stars = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "إجابة تقييم"
        verbose_name_plural = "إجابات التقييم"
        constraints = [
            models.UniqueConstraint(
                fields=["rating", "question"],
                name="calls_callpeerratinganswer_unique_rating_question",
            ),
        ]

    def __str__(self):
        return f"answer_rating_{self.rating_id}_q{self.question_id}"


class CallRecording(models.Model):
    class RecordingStatus(models.TextChoices):
        IDLE = "idle", "Idle"
        STARTING = "starting", "Starting"
        RECORDING = "recording", "Recording"
        STOP_REQUESTED = "stop_requested", "Stop requested"
        STOPPING = "stopping", "Stopping"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"  # sole playable terminal status
        NO_MEDIA = "no_media", "No media"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        SKIPPED = "skipped", "Skipped"
        CANCELLED = "cancelled", "Cancelled"

    TERMINAL_STATUSES = frozenset(
        {
            RecordingStatus.COMPLETED,
            RecordingStatus.NO_MEDIA,
            RecordingStatus.FAILED,
            RecordingStatus.EXPIRED,
            RecordingStatus.SKIPPED,
            RecordingStatus.CANCELLED,
        }
    )
    PREPARING_STATUSES = frozenset(
        {
            RecordingStatus.STARTING,
            RecordingStatus.RECORDING,
            RecordingStatus.STOP_REQUESTED,
            RecordingStatus.STOPPING,
            RecordingStatus.PROCESSING,
        }
    )

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
    recording_object_key = models.CharField(max_length=512, blank=True, default="")
    duration_seconds = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    provider_recording_id = models.TextField(blank=True, default="")
    agora_resource_id = models.TextField(blank=True, default="")
    agora_sid = models.TextField(blank=True, default="")
    recording_uid = models.CharField(max_length=32, blank=True, default="")
    recording_status = models.CharField(
        max_length=20,
        choices=RecordingStatus.choices,
        default=RecordingStatus.IDLE,
    )
    recording_error = models.TextField(blank=True, default="")
    stop_requested_at = models.DateTimeField(null=True, blank=True)
    stopped_at = models.DateTimeField(null=True, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=64, blank=True, default="")
    last_query_at = models.DateTimeField(null=True, blank=True)
    query_attempts = models.PositiveSmallIntegerField(default=0)
    stop_attempts = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "تسجيل مكالمة"
        verbose_name_plural = "تسجيلات المكالمات"

    def __str__(self):
        return f"recording_call_{self.call_session_id}"

    @property
    def is_terminal(self) -> bool:
        return self.recording_status in self.TERMINAL_STATUSES

    @property
    def is_preparing(self) -> bool:
        return self.recording_status in self.PREPARING_STATUSES

    @property
    def is_playable(self) -> bool:
        from apps.calls.recording_storage import (
            is_playable_object_key,
            object_key_for_recording,
        )

        if self.recording_status != self.RecordingStatus.COMPLETED:
            return False
        return is_playable_object_key(object_key_for_recording(self))



RECORDING_CONSENT_VERSION = "recording-consent-v1"


class CallRecordingConsent(models.Model):
    """Explicit per-user consent to record a call session."""

    call_session = models.ForeignKey(
        CallSession,
        on_delete=models.CASCADE,
        related_name="recording_consents",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="call_recording_consents",
    )
    consent_given = models.BooleanField(default=True)
    consented_at = models.DateTimeField()
    consent_version = models.CharField(max_length=64, default=RECORDING_CONSENT_VERSION)
    platform = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["call_session", "user"],
                name="uniq_call_recording_consent_user_session",
            )
        ]
        indexes = [
            models.Index(fields=["call_session", "consent_given"]),
        ]
        verbose_name = "موافقة تسجيل مكالمة"
        verbose_name_plural = "موافقات تسجيل المكالمات"

    def __str__(self):
        return f"consent_call_{self.call_session_id}_user_{self.user_id}"
