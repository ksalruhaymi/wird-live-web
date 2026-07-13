from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.appointments.constants import (
    DEFAULT_BREAK_MINUTES,
    DEFAULT_CANCELLATION_DEADLINE_MINUTES,
    DEFAULT_MAXIMUM_BOOKING_WINDOW_DAYS,
    DEFAULT_MINIMUM_BOOKING_NOTICE_MINUTES,
    DEFAULT_SLOT_DURATION_MINUTES,
)


class SessionType(models.TextChoices):
    NEW_MEMORIZATION = "new_memorization", "حفظ جديد"
    RECITATION = "recitation", "تسميع"
    NEAR_REVISION = "near_revision", "مراجعة قريبة"
    CUMULATIVE_REVISION = "cumulative_revision", "مراجعة شاملة"
    RECITATION_CORRECTION = "recitation_correction", "تصحيح تلاوة"
    MEMORIZATION_TEST = "memorization_test", "اختبار حفظ"
    PLAN_FOLLOW_UP = "plan_follow_up", "متابعة خطة الحفظ"
    INTRODUCTORY_SESSION = "introductory_session", "جلسة تعريفية"
    OTHER = "other", "أخرى"


class RecurrenceType(models.TextChoices):
    NONE = "none", "بدون تكرار"
    DAILY = "daily", "يوميًا"
    WEEKLY = "weekly", "أسبوعيًا"
    WEEKLY_SELECTED = "weekly_selected", "أيام محددة من الأسبوع"
    BIWEEKLY = "biweekly", "كل أسبوعين"
    MONTHLY = "monthly", "شهريًا"


class ExceptionType(models.TextChoices):
    CLOSED_DAY = "closed_day", "إغلاق يوم كامل"
    CLOSED_RANGE = "closed_range", "إغلاق فترة"
    CANCEL_OCCURRENCE = "cancel_occurrence", "إلغاء تكرار واحد"
    ADD_SLOTS = "add_slots", "إضافة وقت استثنائي"


class SlotStatus(models.TextChoices):
    AVAILABLE = "available", "متاح"
    RESERVED = "reserved", "محجوز"
    BLOCKED = "blocked", "محظور"
    CANCELLED = "cancelled", "ملغى"
    EXPIRED = "expired", "منتهي"


class AppointmentStatus(models.TextChoices):
    PENDING_APPROVAL = "pending_approval", "بانتظار موافقة المعلم"
    CONFIRMED = "confirmed", "مؤكد"
    IN_PROGRESS = "in_progress", "جارٍ"
    COMPLETED = "completed", "مكتمل"
    CANCELLED_BY_STUDENT = "cancelled_by_student", "ألغاه الطالب"
    CANCELLED_BY_TEACHER = "cancelled_by_teacher", "ألغاه المعلم"
    REJECTED_BY_TEACHER = "rejected_by_teacher", "رفضه المعلم"
    NO_SHOW_STUDENT = "no_show_student", "غياب الطالب"
    NO_SHOW_TEACHER = "no_show_teacher", "غياب المعلم"
    EXPIRED = "expired", "فائت"


# Bookings that occupy a slot / block overlapping times.
ACTIVE_APPOINTMENT_STATUSES = (
    AppointmentStatus.PENDING_APPROVAL,
    AppointmentStatus.CONFIRMED,
    AppointmentStatus.IN_PROGRESS,
)

DEFAULT_ALLOWED_SESSION_TYPES = [choice.value for choice in SessionType]


class TeacherBookingSettings(models.Model):
    teacher = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="booking_settings",
        verbose_name="المعلم",
    )
    booking_enabled = models.BooleanField(default=True, verbose_name="استقبال الحجوزات")
    approval_required = models.BooleanField(
        default=False,
        verbose_name="يتطلب موافقة المعلم",
        help_text="Reserved for future use; v1 always confirms immediately.",
    )
    default_slot_duration_minutes = models.PositiveSmallIntegerField(
        default=DEFAULT_SLOT_DURATION_MINUTES,
    )
    default_break_minutes = models.PositiveSmallIntegerField(
        default=DEFAULT_BREAK_MINUTES,
    )
    minimum_booking_notice_minutes = models.PositiveIntegerField(
        default=DEFAULT_MINIMUM_BOOKING_NOTICE_MINUTES,
    )
    maximum_booking_window_days = models.PositiveSmallIntegerField(
        default=DEFAULT_MAXIMUM_BOOKING_WINDOW_DAYS,
    )
    cancellation_deadline_minutes = models.PositiveIntegerField(
        default=DEFAULT_CANCELLATION_DEADLINE_MINUTES,
        help_text="Student may cancel until this many minutes before start.",
    )
    max_active_bookings_per_student = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Null means unlimited upcoming active bookings with this teacher.",
    )
    allowed_session_types = models.JSONField(default=list, blank=True)
    timezone = models.CharField(max_length=64, default="Asia/Riyadh")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات حجز المعلم"
        verbose_name_plural = "إعدادات حجز المعلمين"

    def __str__(self):
        return f"booking_settings:{self.teacher_id}"

    def save(self, *args, **kwargs):
        if not self.allowed_session_types:
            self.allowed_session_types = list(DEFAULT_ALLOWED_SESSION_TYPES)
        super().save(*args, **kwargs)


class AvailabilityRule(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability_rules",
    )
    start_date = models.DateField()
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text="Inclusive end date; null means open-ended within generation window.",
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    recurrence_type = models.CharField(
        max_length=32,
        choices=RecurrenceType.choices,
        default=RecurrenceType.NONE,
    )
    recurrence_interval = models.PositiveSmallIntegerField(default=1)
    # ISO weekdays: 1=Monday … 7=Sunday (Python datetime.isoweekday()).
    recurrence_days = models.JSONField(default=list, blank=True)
    slot_duration_minutes = models.PositiveSmallIntegerField(
        default=DEFAULT_SLOT_DURATION_MINUTES,
    )
    break_minutes = models.PositiveSmallIntegerField(default=DEFAULT_BREAK_MINUTES)
    session_types = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    internal_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_date", "start_time", "id"]
        verbose_name = "قاعدة توفر"
        verbose_name_plural = "قواعد التوفر"
        indexes = [
            models.Index(
                fields=["teacher", "is_active", "start_date"],
                name="appt_rule_teacher_active_idx",
            ),
        ]

    def __str__(self):
        return f"rule:{self.pk} teacher={self.teacher_id}"


class AvailabilityException(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability_exceptions",
    )
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    exception_type = models.CharField(max_length=32, choices=ExceptionType.choices)
    reason = models.CharField(max_length=255, blank=True, default="")
    source_rule = models.ForeignKey(
        AvailabilityRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exceptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        verbose_name = "استثناء توفر"
        verbose_name_plural = "استثناءات التوفر"
        indexes = [
            models.Index(
                fields=["teacher", "date"],
                name="appt_exc_teacher_date_idx",
            ),
        ]

    def __str__(self):
        return f"exception:{self.pk} {self.date} {self.exception_type}"


class AppointmentSlot(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appointment_slots",
    )
    source_rule = models.ForeignKey(
        AvailabilityRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="slots",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=SlotStatus.choices,
        default=SlotStatus.AVAILABLE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at", "id"]
        verbose_name = "فترة متاحة"
        verbose_name_plural = "الفترات المتاحة"
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "start_at", "end_at"],
                name="uniq_appt_slot_teacher_start_end",
            ),
            models.CheckConstraint(
                condition=Q(end_at__gt=models.F("start_at")),
                name="appt_slot_end_after_start",
            ),
        ]
        indexes = [
            models.Index(
                fields=["teacher", "status", "start_at"],
                name="appt_slot_teacher_status_idx",
            ),
            models.Index(
                fields=["start_at", "end_at"],
                name="appt_slot_range_idx",
            ),
        ]

    def __str__(self):
        return f"slot:{self.pk} {self.start_at} ({self.status})"


class Appointment(models.Model):
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appointments_as_teacher",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appointments_as_student",
    )
    slot = models.ForeignKey(
        AppointmentSlot,
        on_delete=models.PROTECT,
        related_name="appointments",
    )
    session_type = models.CharField(max_length=40, choices=SessionType.choices)
    session_type_other = models.CharField(max_length=120, blank=True, default="")
    student_notes = models.CharField(max_length=500, blank=True, default="")
    teacher_notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=32,
        choices=AppointmentStatus.choices,
        default=AppointmentStatus.CONFIRMED,
        db_index=True,
    )
    booked_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointments_cancelled",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    call_session = models.OneToOneField(
        "calls.CallSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment",
    )
    reminder_24h_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_1h_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_10m_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-booked_at", "-id"]
        verbose_name = "موعد"
        verbose_name_plural = "المواعيد"
        constraints = [
            models.UniqueConstraint(
                fields=["slot"],
                condition=Q(
                    status__in=[
                        AppointmentStatus.PENDING_APPROVAL,
                        AppointmentStatus.CONFIRMED,
                        AppointmentStatus.IN_PROGRESS,
                    ]
                ),
                name="uniq_active_appointment_per_slot",
            ),
        ]
        indexes = [
            models.Index(
                fields=["teacher", "status", "booked_at"],
                name="appt_teacher_status_idx",
            ),
            models.Index(
                fields=["student", "status", "booked_at"],
                name="appt_student_status_idx",
            ),
        ]

    def __str__(self):
        return f"appointment:{self.pk} ({self.status})"


class AppointmentStatusHistory(models.Model):
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    old_status = models.CharField(max_length=32, blank=True, default="")
    new_status = models.CharField(max_length=32)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="appointment_status_changes",
    )
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "سجل حالة موعد"
        verbose_name_plural = "سجلات حالات المواعيد"

    def __str__(self):
        return f"{self.appointment_id}: {self.old_status} → {self.new_status}"
