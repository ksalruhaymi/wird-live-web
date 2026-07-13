from django import forms

from apps.appointments.constants import (
    DEFAULT_BREAK_MINUTES,
    DEFAULT_CANCELLATION_DEADLINE_MINUTES,
    DEFAULT_MAXIMUM_BOOKING_WINDOW_DAYS,
    DEFAULT_MINIMUM_BOOKING_NOTICE_MINUTES,
    DEFAULT_SLOT_DURATION_MINUTES,
)
from apps.appointments.models import (
    AppointmentStatus,
    ExceptionType,
    RecurrenceType,
    SessionType,
)

WEEKDAY_CHOICES = [
    (1, "الإثنين"),
    (2, "الثلاثاء"),
    (3, "الأربعاء"),
    (4, "الخميس"),
    (5, "الجمعة"),
    (6, "السبت"),
    (7, "الأحد"),
]


class AvailabilityRuleForm(forms.Form):
    start_date = forms.DateField(label="تاريخ البداية")
    end_date = forms.DateField(label="تاريخ النهاية", required=False)
    recurrence_type = forms.ChoiceField(
        label="نوع التكرار",
        choices=RecurrenceType.choices,
    )
    recurrence_days = forms.MultipleChoiceField(
        label="أيام الأسبوع",
        choices=WEEKDAY_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    start_time = forms.TimeField(label="وقت البداية")
    end_time = forms.TimeField(label="وقت النهاية")
    slot_duration_minutes = forms.IntegerField(
        label="مدة الجلسة (دقائق)",
        min_value=5,
        max_value=240,
        initial=DEFAULT_SLOT_DURATION_MINUTES,
    )
    break_minutes = forms.IntegerField(
        label="استراحة بين الجلسات (دقائق)",
        min_value=0,
        max_value=120,
        initial=DEFAULT_BREAK_MINUTES,
    )
    session_types = forms.MultipleChoiceField(
        label="أنواع الجلسات",
        choices=SessionType.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def clean_recurrence_days(self):
        return [int(d) for d in self.cleaned_data.get("recurrence_days") or []]

    def clean_session_types(self):
        return list(self.cleaned_data.get("session_types") or [])

    def to_service_data(self) -> dict:
        data = self.cleaned_data
        return {
            "start_date": data["start_date"].isoformat(),
            "end_date": data["end_date"].isoformat() if data.get("end_date") else None,
            "recurrence_type": data["recurrence_type"],
            "recurrence_days": data.get("recurrence_days") or [],
            "start_time": data["start_time"].strftime("%H:%M"),
            "end_time": data["end_time"].strftime("%H:%M"),
            "slot_duration_minutes": data["slot_duration_minutes"],
            "break_minutes": data["break_minutes"],
            "session_types": data.get("session_types") or [],
        }


class BookingSettingsForm(forms.Form):
    booking_enabled = forms.BooleanField(label="استقبال الحجوزات", required=False)
    default_slot_duration_minutes = forms.IntegerField(
        label="مدة الجلسة الافتراضية (دقائق)",
        min_value=5,
        max_value=240,
        initial=DEFAULT_SLOT_DURATION_MINUTES,
    )
    default_break_minutes = forms.IntegerField(
        label="الاستراحة الافتراضية (دقائق)",
        min_value=0,
        max_value=120,
        initial=DEFAULT_BREAK_MINUTES,
    )
    minimum_booking_notice_minutes = forms.IntegerField(
        label="أقل مهلة قبل الحجز (دقائق)",
        min_value=0,
        initial=DEFAULT_MINIMUM_BOOKING_NOTICE_MINUTES,
    )
    maximum_booking_window_days = forms.IntegerField(
        label="أقصى نافذة حجز (أيام)",
        min_value=1,
        max_value=365,
        initial=DEFAULT_MAXIMUM_BOOKING_WINDOW_DAYS,
    )
    cancellation_deadline_minutes = forms.IntegerField(
        label="مهلة إلغاء الطالب (دقائق قبل البداية)",
        min_value=0,
        initial=DEFAULT_CANCELLATION_DEADLINE_MINUTES,
    )
    max_active_bookings_per_student = forms.IntegerField(
        label="أقصى حجوزات نشطة للطالب",
        required=False,
        min_value=1,
        max_value=100,
    )
    timezone = forms.CharField(label="المنطقة الزمنية", max_length=64, initial="Asia/Riyadh")
    allowed_session_types = forms.MultipleChoiceField(
        label="أنواع الجلسات المسموحة",
        choices=SessionType.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def clean_allowed_session_types(self):
        return list(self.cleaned_data.get("allowed_session_types") or [])

    def clean_max_active_bookings_per_student(self):
        value = self.cleaned_data.get("max_active_bookings_per_student")
        return value if value else None

    def to_service_kwargs(self) -> dict:
        data = self.cleaned_data
        return {
            "booking_enabled": bool(data.get("booking_enabled")),
            "default_slot_duration_minutes": data["default_slot_duration_minutes"],
            "default_break_minutes": data["default_break_minutes"],
            "minimum_booking_notice_minutes": data["minimum_booking_notice_minutes"],
            "maximum_booking_window_days": data["maximum_booking_window_days"],
            "cancellation_deadline_minutes": data["cancellation_deadline_minutes"],
            "max_active_bookings_per_student": data.get("max_active_bookings_per_student"),
            "timezone": (data.get("timezone") or "Asia/Riyadh").strip(),
            "allowed_session_types": data.get("allowed_session_types") or [],
        }


class ExceptionForm(forms.Form):
    exception_type = forms.ChoiceField(label="نوع الاستثناء", choices=ExceptionType.choices)
    date = forms.DateField(label="التاريخ")
    start_time = forms.TimeField(label="وقت البداية", required=False)
    end_time = forms.TimeField(label="وقت النهاية", required=False)
    reason = forms.CharField(label="السبب", max_length=255, required=False)
    cancel_affected_bookings = forms.BooleanField(
        label="إلغاء الحجوزات المتأثرة",
        required=False,
    )
    cancellation_reason = forms.CharField(
        label="سبب إلغاء الحجوزات",
        max_length=255,
        required=False,
    )

    def to_service_data(self) -> dict:
        data = self.cleaned_data
        return {
            "exception_type": data["exception_type"],
            "date": data["date"].isoformat(),
            "start_time": data["start_time"].strftime("%H:%M") if data.get("start_time") else None,
            "end_time": data["end_time"].strftime("%H:%M") if data.get("end_time") else None,
            "reason": (data.get("reason") or "").strip(),
        }


class AppointmentCancelForm(forms.Form):
    reason = forms.CharField(label="سبب الإلغاء", max_length=255, required=False)
    reopen_slot = forms.BooleanField(label="إعادة فتح الفترة", required=False)


class AppointmentStatusForm(forms.Form):
    status = forms.ChoiceField(
        label="الحالة",
        choices=[
            (AppointmentStatus.COMPLETED, "مكتمل"),
            (AppointmentStatus.NO_SHOW_STUDENT, "غياب الطالب"),
            (AppointmentStatus.NO_SHOW_TEACHER, "غياب المعلم"),
        ],
    )
