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
    is_interview_call = models.BooleanField(
        default=False,
        verbose_name="مقابلة إدارة (مكالمة معلم جديد)",
    )
    minutes_charged = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="دقائق مخصومة من الرصيد",
    )

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
        STOPPING = "stopping", "Stopping"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "تسجيل مكالمة"
        verbose_name_plural = "تسجيلات المكالمات"

    def __str__(self):
        return f"recording_call_{self.call_session_id}"
