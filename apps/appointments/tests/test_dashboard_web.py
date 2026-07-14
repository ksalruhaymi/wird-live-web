from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from apps.appointments.models import (
    AppointmentSlot,
    RecurrenceType,
    SessionType,
    SlotStatus,
)
from apps.appointments.services.booking import book_slot
from apps.appointments.services.rules import create_availability_rule
from apps.subscription.models import SubscriptionPlan
from apps.subscription.services import create_student_subscription
from apps.tutoring.models import TeacherProfile as TutoringTeacherProfile
from identity.accounts.user_types import (
    USER_TYPE_ADMIN,
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Role

User = get_user_model()
RIYADH = ZoneInfo("Asia/Riyadh")

REMOVED_WRITE_URL_NAMES = (
    "dashboard:appointment_booking_list",
    "dashboard:appointment_cancel",
    "dashboard:appointment_mark_status",
    "dashboard:appointment_start_call",
    "dashboard:appointment_schedule_list",
    "dashboard:appointment_rule_create",
    "dashboard:appointment_rule_deactivate",
    "dashboard:appointment_exceptions",
    "dashboard:appointment_settings",
)


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


def _make_admin(username: str):
    return User.objects.create_user(
        username=username,
        password="pass12345",
        user_type=USER_TYPE_ADMIN,
        full_name=f"Admin {username}",
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
        self.admin = _make_admin("dash_appt_ad")
        call_command("seed_rbac")

        self.teacher_role = Role.objects.get(slug="teacher")
        self.supervisor_role = Role.objects.get(slug="supervisor")
        self.admin_role = Role.objects.get(slug="admin")
        self.teacher.roles.set([self.teacher_role])
        self.teacher2.roles.set([self.teacher_role])
        self.supervisor.roles.set([self.supervisor_role])
        self.admin.roles.set([self.admin_role])

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

    def test_teacher_forbidden_on_overview(self):
        self._login(self.teacher)
        resp = self.client.get(reverse("dashboard:appointment_overview"))
        self.assertEqual(resp.status_code, 403)

    def test_teacher_forbidden_on_all_list_and_detail(self):
        self._login(self.teacher)
        self.assertEqual(
            self.client.get(reverse("dashboard:appointment_all_list")).status_code, 403
        )
        self.assertEqual(
            self.client.get(
                reverse("dashboard:appointment_detail", kwargs={"pk": self.appt.id})
            ).status_code,
            403,
        )

    def test_student_forbidden_on_overview(self):
        self._login(self.student)
        resp = self.client.get(reverse("dashboard:appointment_overview"))
        self.assertEqual(resp.status_code, 403)

    def test_supervisor_can_view_only(self):
        self._login(self.supervisor)
        overview = self.client.get(reverse("dashboard:appointment_overview"))
        self.assertEqual(overview.status_code, 200)
        self.assertContains(overview, "المواعيد")
        self.assertNotContains(overview, "إضافة قاعدة")

        all_list = self.client.get(reverse("dashboard:appointment_all_list"))
        self.assertEqual(all_list.status_code, 200)
        self.assertContains(all_list, str(self.appt.id))

        detail = self.client.get(
            reverse("dashboard:appointment_detail", kwargs={"pk": self.appt.id})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "سجل الحالات")
        self.assertNotContains(detail, "إلغاء الموعد")
        self.assertNotContains(detail, "بدء مكالمة")
        self.assertNotContains(detail, "تحديث الحالة")

    def test_admin_can_view_only(self):
        self._login(self.admin)
        overview = self.client.get(reverse("dashboard:appointment_overview"))
        self.assertEqual(overview.status_code, 200)
        detail = self.client.get(
            reverse("dashboard:appointment_detail", kwargs={"pk": self.appt.id})
        )
        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "إلغاء الموعد")

    def test_all_list_search_and_filters(self):
        self._login(self.supervisor)
        resp = self.client.get(
            reverse("dashboard:appointment_all_list"),
            {"q": self.teacher.full_name, "bucket": "upcoming"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, str(self.appt.id))

    def test_write_url_names_removed(self):
        for name in REMOVED_WRITE_URL_NAMES:
            with self.assertRaises(NoReverseMatch):
                reverse(name)

    def test_legacy_write_paths_return_404(self):
        self._login(self.supervisor)
        legacy_paths = [
            "/dashboard/appointments/bookings/",
            f"/dashboard/appointments/bookings/{self.appt.id}/cancel/",
            f"/dashboard/appointments/bookings/{self.appt.id}/status/",
            f"/dashboard/appointments/bookings/{self.appt.id}/start-call/",
            "/dashboard/appointments/schedule/",
            "/dashboard/appointments/schedule/rules/create/",
            f"/dashboard/appointments/schedule/rules/{self.rule.id}/deactivate/",
            "/dashboard/appointments/exceptions/",
            "/dashboard/appointments/settings/",
        ]
        for path in legacy_paths:
            for method in ("get", "post"):
                resp = getattr(self.client, method)(path)
                self.assertEqual(
                    resp.status_code,
                    404,
                    msg=f"{method.upper()} {path} expected 404, got {resp.status_code}",
                )

    def test_remaining_pages_reject_post(self):
        self._login(self.supervisor)
        pages = [
            reverse("dashboard:appointment_overview"),
            reverse("dashboard:appointment_all_list"),
            reverse("dashboard:appointment_detail", kwargs={"pk": self.appt.id}),
        ]
        for url in pages:
            resp = self.client.post(url, data={"status": "completed"})
            self.assertIn(
                resp.status_code,
                (403, 405),
                msg=f"POST {url} expected 403/405, got {resp.status_code}",
            )

    def test_teacher_cannot_access_dashboard_home(self):
        self._login(self.teacher)
        resp = self.client.get(reverse("dashboard:overview_dashboard"))
        self.assertEqual(resp.status_code, 403)
        # Appointment pages remain forbidden.
        self.assertEqual(
            self.client.get(reverse("dashboard:appointment_overview")).status_code, 403
        )

    def test_all_list_query_bound(self):
        self._login(self.supervisor)
        url = reverse("dashboard:appointment_all_list")
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            list(resp.context["appointments"])
        self.assertLessEqual(len(ctx.captured_queries), 40)
