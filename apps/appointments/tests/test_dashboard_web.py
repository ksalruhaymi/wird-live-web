from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import (
    Appointment,
    AppointmentSlot,
    AppointmentStatus,
    AvailabilityRule,
    ExceptionType,
    RecurrenceType,
    SessionType,
    SlotStatus,
)
from apps.appointments.services.booking import book_slot
from apps.appointments.services.rules import create_availability_rule
from apps.appointments.services.settings_service import get_or_create_booking_settings
from apps.calls.models import CallSession
from apps.subscription.models import SubscriptionPlan
from apps.subscription.services import create_student_subscription
from apps.tutoring.models import TeacherProfile as TutoringTeacherProfile
from identity.accounts.user_types import (
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Role

User = get_user_model()
RIYADH = ZoneInfo("Asia/Riyadh")


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


def _make_supervisor(username: str):
    return User.objects.create_user(
        username=username,
        password="pass12345",
        user_type=USER_TYPE_SUPERVISOR,
        full_name=f"Supervisor {username}",
    )


def _rule_day_ahead(days: int = 2):
    return timezone.localdate() + timedelta(days=days)


@override_settings(AXES_ENABLED=False)
class AppointmentDashboardWebTests(TestCase):
    def setUp(self):
        call_command("seed_rbac")
        self.teacher = _make_teacher("dash_appt_t1")
        self.teacher2 = _make_teacher("dash_appt_t2")
        self.student = _make_student_with_balance("dash_appt_s1")
        self.supervisor = _make_supervisor("dash_appt_sv")
        call_command("seed_rbac")

        self.teacher_role = Role.objects.get(slug="teacher")
        self.supervisor_role = Role.objects.get(slug="supervisor")
        self.teacher.roles.set([self.teacher_role])
        self.teacher2.roles.set([self.teacher_role])
        self.supervisor.roles.set([self.supervisor_role])

        start = _rule_day_ahead(3)
        self.rule = create_availability_rule(
            self.teacher,
            {
                "start_date": start.isoformat(),
                "start_time": "10:00",
                "end_time": "12:00",
                "slot_duration_minutes": 30,
                "break_minutes": 0,
                "recurrence_type": RecurrenceType.NONE,
            },
        )
        self.slot = (
            AppointmentSlot.objects.filter(teacher=self.teacher, status=SlotStatus.AVAILABLE)
            .order_by("start_at")
            .first()
        )
        self.appt = book_slot(
            student=self.student,
            slot_id=self.slot.id,
            session_type=SessionType.RECITATION,
        )
        self.client = Client()

    def _login(self, user):
        self.client.force_login(user)

    def test_teacher_can_open_overview(self):
        self._login(self.teacher)
        resp = self.client.get(reverse("dashboard:appointment_overview"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "المواعيد")

    def test_student_forbidden_on_overview(self):
        self._login(self.student)
        resp = self.client.get(reverse("dashboard:appointment_overview"))
        self.assertEqual(resp.status_code, 403)

    def test_teacher_cannot_see_other_teacher_appointment(self):
        self._login(self.teacher2)
        resp = self.client.get(
            reverse("dashboard:appointment_detail", kwargs={"pk": self.appt.id})
        )
        self.assertEqual(resp.status_code, 404)

    def test_supervisor_with_view_all_sees_all(self):
        self._login(self.supervisor)
        resp = self.client.get(reverse("dashboard:appointment_all_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, str(self.appt.id))

        detail = self.client.get(
            reverse("dashboard:appointment_detail", kwargs={"pk": self.appt.id})
        )
        self.assertEqual(detail.status_code, 200)

    def test_create_rule(self):
        self._login(self.teacher)
        day = _rule_day_ahead(10)
        resp = self.client.post(
            reverse("dashboard:appointment_rule_create"),
            data={
                "start_date": day.isoformat(),
                "start_time": "14:00",
                "end_time": "15:00",
                "recurrence_type": RecurrenceType.NONE,
                "slot_duration_minutes": 30,
                "break_minutes": 0,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            AvailabilityRule.objects.filter(
                teacher=self.teacher,
                start_date=day,
                start_time=time(14, 0),
            ).exists()
        )

    def test_overlap_rejected(self):
        self._login(self.teacher)
        day = self.rule.start_date
        resp = self.client.post(
            reverse("dashboard:appointment_rule_create"),
            data={
                "start_date": day.isoformat(),
                "start_time": "10:30",
                "end_time": "11:30",
                "recurrence_type": RecurrenceType.NONE,
                "slot_duration_minutes": 30,
                "break_minutes": 0,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "تتداخل")

    def test_deactivate_rule(self):
        self._login(self.teacher)
        resp = self.client.post(
            reverse("dashboard:appointment_rule_deactivate", kwargs={"pk": self.rule.id})
        )
        self.assertEqual(resp.status_code, 302)
        self.rule.refresh_from_db()
        self.assertFalse(self.rule.is_active)

    def test_settings_toggle(self):
        self._login(self.teacher)
        settings_obj = get_or_create_booking_settings(self.teacher)
        self.assertTrue(settings_obj.booking_enabled)
        resp = self.client.post(
            reverse("dashboard:appointment_settings"),
            data={
                "default_slot_duration_minutes": 30,
                "default_break_minutes": 5,
                "minimum_booking_notice_minutes": 60,
                "maximum_booking_window_days": 90,
                "cancellation_deadline_minutes": 120,
                "timezone": "Asia/Riyadh",
                "allowed_session_types": [SessionType.RECITATION],
            },
        )
        self.assertEqual(resp.status_code, 302)
        settings_obj.refresh_from_db()
        self.assertFalse(settings_obj.booking_enabled)

    def test_exception_preview_then_confirm(self):
        self._login(self.teacher)
        day = self.slot.start_at.astimezone(RIYADH).date()
        url = reverse("dashboard:appointment_exceptions")
        preview = self.client.post(
            url,
            data={
                "exception_type": ExceptionType.CLOSED_DAY,
                "date": day.isoformat(),
                "reason": "إجازة",
            },
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "حجزًا متأثرًا")

        confirm = self.client.post(
            url,
            data={
                "exception_type": ExceptionType.CLOSED_DAY,
                "date": day.isoformat(),
                "reason": "إجازة",
                "confirm_cancel": "1",
                "cancellation_reason": "إجازة مؤكدة",
            },
        )
        self.assertEqual(confirm.status_code, 302)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, AppointmentStatus.CANCELLED_BY_TEACHER)

    def test_cancel_appointment(self):
        self._login(self.teacher)
        resp = self.client.post(
            reverse("dashboard:appointment_cancel", kwargs={"pk": self.appt.id}),
            data={"reason": "تعارض", "reopen_slot": "on"},
        )
        self.assertEqual(resp.status_code, 302)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, AppointmentStatus.CANCELLED_BY_TEACHER)

    def test_start_call_window_mocked(self):
        self._login(self.teacher)
        fake_now = self.slot.start_at - timedelta(minutes=5)
        call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.MOCK,
            status=CallSession.Status.PENDING,
            channel_name="dash-appt-channel",
        )
        with patch("apps.appointments.services.call_link.timezone.now", return_value=fake_now):
            with patch(
                "apps.appointments.services.call_link.create_scheduled_call_session",
                return_value=call,
            ):
                resp = self.client.post(
                    reverse("dashboard:appointment_start_call", kwargs={"pk": self.appt.id})
                )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            reverse("dashboard:call_session_detail", kwargs={"session_id": call.id}),
        )

    def test_mark_status(self):
        self._login(self.teacher)
        resp = self.client.post(
            reverse("dashboard:appointment_mark_status", kwargs={"pk": self.appt.id}),
            data={"status": AppointmentStatus.COMPLETED},
        )
        self.assertEqual(resp.status_code, 302)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, AppointmentStatus.COMPLETED)

    def test_idor_other_teacher_cancel(self):
        self._login(self.teacher2)
        resp = self.client.post(
            reverse("dashboard:appointment_cancel", kwargs={"pk": self.appt.id}),
            data={"reason": "hack"},
        )
        self.assertEqual(resp.status_code, 404)
        self.appt.refresh_from_db()
        self.assertEqual(self.appt.status, AppointmentStatus.CONFIRMED)

    def test_csrf_required_on_post(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.teacher)
        resp = csrf_client.post(
            reverse("dashboard:appointment_cancel", kwargs={"pk": self.appt.id}),
            data={"reason": "no csrf"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_booking_list_query_bound(self):
        self._login(self.teacher)
        url = reverse("dashboard:appointment_booking_list")
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            list(resp.context["appointments"])
        self.assertLessEqual(len(ctx.captured_queries), 40)
