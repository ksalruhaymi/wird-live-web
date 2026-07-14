"""API tests for simplified month-calendar availability UX."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from apps.appointments.models import (
    AppointmentSlot,
    AppointmentStatus,
    SessionType,
    SlotStatus,
)
from apps.appointments.services.booking import book_slot
from apps.appointments.services.calendar import create_availability_for_dates
from apps.appointments.services.settings_service import (
    get_or_create_booking_settings,
    update_booking_settings,
)
from apps.subscription.models import SubscriptionPlan
from apps.subscription.services import create_student_subscription
from apps.tutoring.models import TeacherProfile as TutoringTeacherProfile
from identity.accounts.user_types import USER_TYPE_STUDENT, USER_TYPE_TEACHER
from identity.rbac.models import Role

User = get_user_model()
MOBILE_API_HEADERS = {
    "HTTP_X_APP_VERSION": "99.0.0",
    "HTTP_X_APP_BUILD": "99999",
    "HTTP_X_APP_PLATFORM": "android",
}


def _make_teacher(username: str):
    teacher = User.objects.create_user(
        username=username,
        password="pass12345",
        user_type=USER_TYPE_TEACHER,
        full_name=f"Teacher {username}",
    )
    TutoringTeacherProfile.objects.create(
        user=teacher,
        display_name=f"المعلم {username}",
        approval_status=TutoringTeacherProfile.ApprovalStatus.APPROVED,
        is_approved=True,
        can_audio=True,
        can_video=True,
    )
    return teacher


def _make_student_with_balance(username: str):
    student = User.objects.create_user(
        username=username,
        password="pass12345",
        user_type=USER_TYPE_STUDENT,
        full_name=f"Student {username}",
    )
    plan = SubscriptionPlan.objects.create(
        title=f"plan-{username}",
        duration_months=1,
        price=Decimal("50.00"),
        minutes=120,
        is_active=True,
    )
    create_student_subscription(student, plan_id=plan.id)
    return student


@override_settings(AXES_ENABLED=False)
class CalendarAvailabilityApiTests(TestCase):
    def setUp(self):
        call_command("seed_rbac")
        self.teacher = _make_teacher("cal_t1")
        self.student = _make_student_with_balance("cal_s1")
        self.student2 = _make_student_with_balance("cal_s2")
        call_command("seed_rbac")
        role = Role.objects.get(slug="teacher")
        self.teacher.roles.set([role])
        self.client = Client()
        self.day = timezone.localdate() + timedelta(days=5)
        self.month = f"{self.day.year:04d}-{self.day.month:02d}"

    def _login(self, user):
        self.client.force_login(user)

    def test_create_single_day_availability_and_month_summary(self):
        self._login(self.teacher)
        create = self.client.post(
            "/api/v1/appointments/teacher/availability/create/",
            data={
                "dates": [self.day.isoformat()],
                "start_time": "16:00",
                "end_time": "18:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
            },
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(create.status_code, 201, create.content)
        self.assertEqual(create.json()["created_count"], 1)

        available = AppointmentSlot.objects.filter(
            teacher=self.teacher,
            status=SlotStatus.AVAILABLE,
            start_at__date=self.day,
        ).count()
        self.assertEqual(available, 4)

        cal = self.client.get(
            f"/api/v1/appointments/teacher/calendar/?month={self.month}",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(cal.status_code, 200, cal.content)
        body = cal.json()
        self.assertEqual(body["month"], self.month)
        day_row = next(d for d in body["days"] if d["date"] == self.day.isoformat())
        self.assertTrue(day_row["has_availability"])
        self.assertEqual(day_row["available_count"], 4)
        self.assertFalse(day_row["has_bookings"])

    def test_create_multi_day_same_month(self):
        self._login(self.teacher)
        day2 = self.day + timedelta(days=2)
        # keep within same month
        if day2.month != self.day.month:
            day2 = self.day + timedelta(days=1)
        resp = self.client.post(
            "/api/v1/appointments/teacher/availability/create/",
            data={
                "dates": [self.day.isoformat(), day2.isoformat()],
                "start_time": "17:00",
                "end_time": "18:00",
                "slot_duration_minutes": 30,
            },
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["created_count"], 2)
        self.assertEqual(
            AppointmentSlot.objects.filter(
                teacher=self.teacher, status=SlotStatus.AVAILABLE
            ).count(),
            4,
        )

    def test_reject_past_date_and_invalid_duration(self):
        self._login(self.teacher)
        past = timezone.localdate() - timedelta(days=1)
        past_resp = self.client.post(
            "/api/v1/appointments/teacher/availability/create/",
            data={
                "dates": [past.isoformat()],
                "start_time": "10:00",
                "end_time": "11:00",
                "slot_duration_minutes": 30,
            },
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(past_resp.status_code, 400)
        self.assertEqual(past_resp.json()["code"], "past_date")

        bad = self.client.post(
            "/api/v1/appointments/teacher/availability/create/",
            data={
                "dates": [self.day.isoformat()],
                "start_time": "10:00",
                "end_time": "11:00",
                "slot_duration_minutes": 25,
            },
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["code"], "invalid_duration")

    def test_day_schedule_and_cancel_available_slot(self):
        self._login(self.teacher)
        create_availability_for_dates(
            self.teacher,
            {
                "dates": [self.day.isoformat()],
                "start_time": "10:00",
                "end_time": "11:00",
                "slot_duration_minutes": 30,
            },
        )
        day = self.client.get(
            f"/api/v1/appointments/teacher/day/?date={self.day.isoformat()}",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(day.status_code, 200, day.content)
        items = day.json()["items"]
        self.assertEqual(len(items), 2)
        slot_id = items[0]["slot"]["id"]

        cancel = self.client.post(
            f"/api/v1/appointments/teacher/slots/{slot_id}/cancel/",
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(cancel.status_code, 200, cancel.content)
        self.assertEqual(
            AppointmentSlot.objects.get(pk=slot_id).status, SlotStatus.CANCELLED
        )

    def test_cannot_cancel_booked_slot_directly(self):
        self._login(self.teacher)
        create_availability_for_dates(
            self.teacher,
            {
                "dates": [self.day.isoformat()],
                "start_time": "10:00",
                "end_time": "11:00",
                "slot_duration_minutes": 30,
            },
        )
        slot = AppointmentSlot.objects.filter(
            teacher=self.teacher, status=SlotStatus.AVAILABLE
        ).first()
        book_slot(
            student=self.student,
            slot_id=slot.id,
            session_type=SessionType.RECITATION,
        )
        resp = self.client.post(
            f"/api/v1/appointments/teacher/slots/{slot.id}/cancel/",
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "slot_booked")

    def test_clear_day_keeps_booked(self):
        self._login(self.teacher)
        create_availability_for_dates(
            self.teacher,
            {
                "dates": [self.day.isoformat()],
                "start_time": "10:00",
                "end_time": "12:00",
                "slot_duration_minutes": 30,
            },
        )
        slot = (
            AppointmentSlot.objects.filter(
                teacher=self.teacher, status=SlotStatus.AVAILABLE
            )
            .order_by("start_at")
            .first()
        )
        appt = book_slot(
            student=self.student,
            slot_id=slot.id,
            session_type=SessionType.RECITATION,
        )
        clear = self.client.post(
            "/api/v1/appointments/teacher/day/clear/",
            data={"date": self.day.isoformat()},
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(clear.status_code, 200, clear.content)
        self.assertGreater(clear.json()["cleared_count"], 0)
        slot.refresh_from_db()
        appt.refresh_from_db()
        self.assertEqual(slot.status, SlotStatus.RESERVED)
        self.assertEqual(appt.status, AppointmentStatus.CONFIRMED)
        self.assertEqual(
            AppointmentSlot.objects.filter(
                teacher=self.teacher,
                status=SlotStatus.AVAILABLE,
                start_at__date=self.day,
            ).count(),
            0,
        )

    def test_student_calendar_and_booking_pause(self):
        create_availability_for_dates(
            self.teacher,
            {
                "dates": [self.day.isoformat()],
                "start_time": "10:00",
                "end_time": "11:00",
                "slot_duration_minutes": 30,
            },
        )
        self._login(self.student)
        cal = self.client.get(
            f"/api/v1/appointments/teachers/{self.teacher.id}/calendar/?month={self.month}",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(cal.status_code, 200, cal.content)
        day_row = next(
            d for d in cal.json()["days"] if d["date"] == self.day.isoformat()
        )
        self.assertTrue(day_row["has_availability"])

        update_booking_settings(self.teacher, booking_enabled=False)
        paused = self.client.get(
            f"/api/v1/appointments/teachers/{self.teacher.id}/calendar/?month={self.month}",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(paused.status_code, 200)
        body = paused.json()
        self.assertFalse(body["booking_enabled"])
        self.assertIn("لا يستقبل", body["message"])
        self.assertFalse(any(d["has_availability"] for d in body["days"]))

        # Existing bookings remain when pausing
        settings = get_or_create_booking_settings(self.teacher)
        self.assertFalse(settings.booking_enabled)
        remaining = AppointmentSlot.objects.filter(
            teacher=self.teacher, status=SlotStatus.AVAILABLE
        ).count()
        self.assertGreater(remaining, 0)

    def test_student_book_then_calendar_updates(self):
        create_availability_for_dates(
            self.teacher,
            {
                "dates": [self.day.isoformat()],
                "start_time": "10:00",
                "end_time": "10:30",
                "slot_duration_minutes": 30,
            },
        )
        slot = AppointmentSlot.objects.filter(
            teacher=self.teacher, status=SlotStatus.AVAILABLE
        ).first()
        self._login(self.student)
        book = self.client.post(
            "/api/v1/appointments/book/",
            data={"slot_id": slot.id, "session_type": SessionType.RECITATION},
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(book.status_code, 201, book.content)

        cal = self.client.get(
            f"/api/v1/appointments/teachers/{self.teacher.id}/calendar/?month={self.month}",
            **MOBILE_API_HEADERS,
        )
        day_row = next(
            d for d in cal.json()["days"] if d["date"] == self.day.isoformat()
        )
        self.assertFalse(day_row["has_availability"])

        self._login(self.student2)
        slots = self.client.get(
            f"/api/v1/appointments/teachers/{self.teacher.id}/slots/?date={self.day.isoformat()}",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(slots.status_code, 200)
        self.assertEqual(slots.json()["slots"], [])
