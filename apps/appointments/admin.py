from django.contrib import admin

from .models import (
    Appointment,
    AppointmentSlot,
    AppointmentStatusHistory,
    AvailabilityException,
    AvailabilityRule,
    TeacherBookingSettings,
)


@admin.register(TeacherBookingSettings)
class TeacherBookingSettingsAdmin(admin.ModelAdmin):
    list_display = ("teacher", "booking_enabled", "approval_required", "updated_at")
    list_filter = ("booking_enabled", "approval_required")
    search_fields = ("teacher__username", "teacher__full_name")
    raw_id_fields = ("teacher",)


@admin.register(AvailabilityRule)
class AvailabilityRuleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "teacher",
        "start_date",
        "end_date",
        "start_time",
        "end_time",
        "recurrence_type",
        "is_active",
    )
    list_filter = ("recurrence_type", "is_active")
    search_fields = ("teacher__username",)
    raw_id_fields = ("teacher",)


@admin.register(AvailabilityException)
class AvailabilityExceptionAdmin(admin.ModelAdmin):
    list_display = ("id", "teacher", "date", "exception_type", "start_time", "end_time")
    list_filter = ("exception_type",)
    raw_id_fields = ("teacher", "source_rule")


@admin.register(AppointmentSlot)
class AppointmentSlotAdmin(admin.ModelAdmin):
    list_display = ("id", "teacher", "start_at", "end_at", "status")
    list_filter = ("status",)
    search_fields = ("teacher__username",)
    raw_id_fields = ("teacher", "source_rule")


class AppointmentStatusHistoryInline(admin.TabularInline):
    model = AppointmentStatusHistory
    extra = 0
    readonly_fields = ("old_status", "new_status", "changed_by", "note", "created_at")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "teacher",
        "student",
        "session_type",
        "status",
        "booked_at",
    )
    list_filter = ("status", "session_type")
    search_fields = ("teacher__username", "student__username")
    raw_id_fields = ("teacher", "student", "slot", "call_session", "cancelled_by")
    inlines = [AppointmentStatusHistoryInline]
