"""Appointment domain constants (v1 product rules)."""

from __future__ import annotations

# How far ahead slots are materialized for each teacher.
SLOT_GENERATION_WINDOW_DAYS = 90

# Call button: open before start, and remain startable until this after start.
CALL_WINDOW_BEFORE_MINUTES = 10
CALL_WINDOW_AFTER_START_MINUTES = 10

# Default booking settings for new teachers.
DEFAULT_SLOT_DURATION_MINUTES = 30
DEFAULT_BREAK_MINUTES = 5
DEFAULT_MINIMUM_BOOKING_NOTICE_MINUTES = 60
DEFAULT_MAXIMUM_BOOKING_WINDOW_DAYS = 90
DEFAULT_CANCELLATION_DEADLINE_MINUTES = 120  # student cancel until 2h before start

BOOKING_COST_NOTICE_AR = (
    "تُحتسب تكلفة الجلسة بالدقيقة عند بدء الاتصال الفعلي، وليس عند الحجز."
)

SLOT_ALREADY_BOOKED_MESSAGE = (
    "عذرًا، تم حجز هذا الموعد قبل إتمام طلبك. اختر وقتًا آخر."
)
