from django.urls import path

from . import views

app_name = "appointments_api"

urlpatterns = [
    path("appointments/session-types/", views.session_types, name="session-types"),
    path(
        "appointments/teachers/<int:teacher_id>/summary/",
        views.teacher_summary,
        name="teacher-summary",
    ),
    path(
        "appointments/teachers/<int:teacher_id>/calendar/",
        views.student_teacher_calendar,
        name="teacher-calendar",
    ),
    path(
        "appointments/teachers/<int:teacher_id>/days/",
        views.teacher_days,
        name="teacher-days",
    ),
    path(
        "appointments/teachers/<int:teacher_id>/slots/",
        views.teacher_day_slots,
        name="teacher-slots",
    ),
    path("appointments/book/", views.book, name="book"),
    path("appointments/my/", views.my_appointments, name="my"),
    path("appointments/my/upcoming-count/", views.my_upcoming_count, name="upcoming-count"),
    path("appointments/<int:pk>/", views.appointment_detail, name="detail"),
    path("appointments/<int:pk>/cancel/", views.cancel_appointment, name="cancel"),
    path("appointments/<int:pk>/start-call/", views.start_call, name="start-call"),
    # Teacher calendar UX
    path(
        "appointments/teacher/calendar/",
        views.teacher_own_calendar,
        name="teacher-own-calendar",
    ),
    path(
        "appointments/teacher/day/",
        views.teacher_own_day,
        name="teacher-own-day",
    ),
    path(
        "appointments/teacher/availability/create/",
        views.teacher_create_availability,
        name="teacher-availability-create",
    ),
    path(
        "appointments/teacher/slots/<int:slot_id>/cancel/",
        views.teacher_cancel_slot,
        name="teacher-slot-cancel",
    ),
    path(
        "appointments/teacher/day/clear/",
        views.teacher_clear_day,
        name="teacher-day-clear",
    ),
    # Teacher
    path("appointments/teacher/settings/", views.teacher_settings, name="teacher-settings"),
    path(
        "appointments/teacher/settings/toggle/",
        views.teacher_toggle_booking,
        name="teacher-toggle",
    ),
    path("appointments/teacher/bookings/", views.teacher_bookings, name="teacher-bookings"),
    path("appointments/teacher/rules/", views.teacher_rules, name="teacher-rules"),
    path(
        "appointments/teacher/rules/create/",
        views.teacher_create_rule,
        name="teacher-create-rule",
    ),
    path(
        "appointments/teacher/rules/<int:rule_id>/deactivate/",
        views.teacher_deactivate_rule,
        name="teacher-deactivate-rule",
    ),
    path(
        "appointments/teacher/exceptions/preview/",
        views.teacher_preview_exception,
        name="teacher-exception-preview",
    ),
    path(
        "appointments/teacher/exceptions/",
        views.teacher_add_exception,
        name="teacher-exception",
    ),
    path(
        "appointments/<int:pk>/mark-status/",
        views.teacher_mark_status,
        name="mark-status",
    ),
]
