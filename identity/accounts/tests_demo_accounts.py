"""Tests for protected demo accounts and demo-teacher visibility."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.appointments.models import AppointmentSlot, SlotStatus, TeacherBookingSettings
from apps.calls.exceptions import CallValidationError
from apps.calls.models import CallSession
from apps.calls.services import request_call_session
from apps.tutoring.models import TeacherFavorite, TeacherProfile
from apps.tutoring.teacher_services import get_teacher_user, list_teachers_payload
from identity.accounts.demo_accounts import (
    DEMO_ROLE_ADMIN,
    DEMO_ROLE_STUDENT,
    DEMO_ROLE_TEACHER,
    can_viewer_see_teacher,
    exclude_hidden_demo_teachers,
    get_visible_teacher_or_404,
    is_demo_student_account,
    is_demo_teacher_account,
)
from identity.accounts.user_role_sync import teacher_users_queryset
from identity.accounts.user_types import (
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Role
from django.http import Http404
from django.utils import timezone
from datetime import timedelta

User = get_user_model()


def _ensure_role(slug: str) -> Role:
    role, _ = Role.objects.get_or_create(slug=slug, defaults={"name": slug})
    return role


def _make_teacher(*, username: str, demo: bool = False) -> User:
    user = User.objects.create_user(
        username=username,
        password="Pass1234!",
        user_type=USER_TYPE_TEACHER,
        email=f"{username}@example.com",
        is_demo_account=demo,
        demo_role=DEMO_ROLE_TEACHER if demo else None,
    )
    user.roles.set([_ensure_role("teacher")])
    TeacherProfile.objects.create(
        user=user,
        display_name=username,
        is_approved=True,
        approval_status=TeacherProfile.ApprovalStatus.APPROVED,
        can_audio=True,
        can_video=True,
        auto_accept_calls=True,
    )
    return user


def _make_student(*, username: str, demo: bool = False) -> User:
    user = User.objects.create_user(
        username=username,
        password="Pass1234!",
        user_type=USER_TYPE_STUDENT,
        email=f"{username}@example.com",
        is_demo_account=demo,
        demo_role=DEMO_ROLE_STUDENT if demo else None,
    )
    user.roles.set([_ensure_role("student")])
    return user


class DemoAccountModelTests(TestCase):
    def test_unique_demo_role_constraint(self):
        User.objects.create_user(
            username="demo_a",
            password="Pass1234!",
            is_demo_account=True,
            demo_role=DEMO_ROLE_STUDENT,
            user_type=USER_TYPE_STUDENT,
        )
        with self.assertRaises(Exception):
            User.objects.create_user(
                username="demo_b",
                password="Pass1234!",
                is_demo_account=True,
                demo_role=DEMO_ROLE_STUDENT,
                user_type=USER_TYPE_STUDENT,
            )

    def test_clear_demo_role_when_flag_off(self):
        user = User.objects.create_user(
            username="demo_clear",
            password="Pass1234!",
            is_demo_account=True,
            demo_role=DEMO_ROLE_ADMIN,
            user_type=USER_TYPE_SUPERVISOR,
        )
        user.is_demo_account = False
        user.save()
        user.refresh_from_db()
        self.assertIsNone(user.demo_role)


class DemoTeacherVisibilityHelpersTests(TestCase):
    def setUp(self):
        self.demo_teacher = _make_teacher(username="vis_demo_teacher", demo=True)
        self.normal_teacher = _make_teacher(username="vis_normal_teacher", demo=False)
        self.demo_student = _make_student(username="vis_demo_student", demo=True)
        self.normal_student = _make_student(username="vis_normal_student", demo=False)
        self.superuser = User.objects.create_superuser(
            username="vis_super",
            email="vis_super@example.com",
            password="Pass1234!",
        )
        self.supervisor = User.objects.create_user(
            username="vis_supervisor",
            password="Pass1234!",
            user_type=USER_TYPE_SUPERVISOR,
            email="vis_supervisor@example.com",
        )
        self.supervisor.roles.set([_ensure_role("supervisor")])

    def test_helpers(self):
        self.assertTrue(is_demo_teacher_account(self.demo_teacher))
        self.assertTrue(is_demo_student_account(self.demo_student))
        self.assertFalse(is_demo_teacher_account(self.normal_teacher))

    def test_can_viewer_see_teacher(self):
        self.assertTrue(can_viewer_see_teacher(self.superuser, self.demo_teacher))
        self.assertTrue(can_viewer_see_teacher(self.demo_student, self.demo_teacher))
        self.assertTrue(can_viewer_see_teacher(self.supervisor, self.demo_teacher))
        self.assertFalse(can_viewer_see_teacher(self.normal_student, self.demo_teacher))
        self.assertTrue(can_viewer_see_teacher(self.normal_student, self.normal_teacher))

    def test_exclude_hidden_demo_teachers(self):
        qs = User.objects.filter(teacher_profile__isnull=False)
        hidden = exclude_hidden_demo_teachers(qs, self.normal_student)
        self.assertFalse(hidden.filter(pk=self.demo_teacher.pk).exists())
        self.assertTrue(hidden.filter(pk=self.normal_teacher.pk).exists())

        visible = exclude_hidden_demo_teachers(qs, self.demo_student)
        self.assertTrue(visible.filter(pk=self.demo_teacher.pk).exists())

        staff_visible = exclude_hidden_demo_teachers(qs, self.supervisor)
        self.assertTrue(staff_visible.filter(pk=self.demo_teacher.pk).exists())
        self.assertTrue(staff_visible.filter(pk=self.normal_teacher.pk).exists())

    def test_get_visible_teacher_or_404(self):
        get_visible_teacher_or_404(self.demo_student, self.demo_teacher.id)
        with self.assertRaises(Http404):
            get_visible_teacher_or_404(self.normal_student, self.demo_teacher.id)

    def test_list_teachers_payload_hides_demo_teacher(self):
        class R:
            def __init__(self, user):
                self.user = user

        payloads = list_teachers_payload(request=R(self.normal_student))
        ids = {p["id"] for p in payloads}
        self.assertNotIn(self.demo_teacher.id, ids)
        self.assertIn(self.normal_teacher.id, ids)

        payloads_demo = list_teachers_payload(request=R(self.demo_student))
        ids_demo = {p["id"] for p in payloads_demo}
        self.assertIn(self.demo_teacher.id, ids_demo)

        payloads_su = list_teachers_payload(request=R(self.superuser))
        self.assertIn(self.demo_teacher.id, {p["id"] for p in payloads_su})

    def test_get_teacher_user_respects_viewer(self):
        self.assertIsNone(
            get_teacher_user(self.demo_teacher.id, viewer=self.normal_student)
        )
        self.assertEqual(
            get_teacher_user(self.demo_teacher.id, viewer=self.demo_student).id,
            self.demo_teacher.id,
        )

    def test_dashboard_queryset_hides_for_non_superuser(self):
        qs = teacher_users_queryset(viewer=self.normal_student)
        self.assertFalse(qs.filter(pk=self.demo_teacher.pk).exists())
        qs_su = teacher_users_queryset(viewer=self.superuser)
        self.assertTrue(qs_su.filter(pk=self.demo_teacher.pk).exists())


class DemoTeacherCallAccessTests(TestCase):
    def setUp(self):
        self.demo_teacher = _make_teacher(username="call_demo_teacher", demo=True)
        self.normal_teacher = _make_teacher(username="call_normal_teacher", demo=False)
        self.demo_student = _make_student(username="call_demo_student", demo=True)
        self.normal_student = _make_student(username="call_normal_student", demo=False)

    def test_normal_student_cannot_call_demo_teacher(self):
        with self.assertRaises(CallValidationError) as ctx:
            request_call_session(
                self.normal_student,
                session_type=CallSession.SessionType.AUDIO,
                teacher_id=self.demo_teacher.id,
            )
        self.assertEqual(ctx.exception.status, 404)

    def test_demo_student_can_call_demo_teacher(self):
        from unittest.mock import patch

        with patch(
            "apps.calls.services.student_can_request_call",
            return_value=(True, ""),
        ), patch(
            "apps.calls.services.validate_teacher_for_call",
            return_value=None,
        ), patch(
            "apps.calls.services.provider_name_for_new_call",
            return_value=CallSession.Provider.AGORA,
        ), patch("apps.calls.services.assign_channel_name"):
            call = request_call_session(
                self.demo_student,
                session_type=CallSession.SessionType.AUDIO,
                teacher_id=self.demo_teacher.id,
            )
        self.assertEqual(call.teacher_id, self.demo_teacher.id)
        self.assertEqual(call.student_id, self.demo_student.id)


class DemoTeacherApiAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("seed_rbac")

    def setUp(self):
        self.demo_teacher = _make_teacher(username="api_demo_teacher", demo=True)
        self.normal_teacher = _make_teacher(username="api_normal_teacher", demo=False)
        self.demo_student = _make_student(username="api_demo_student", demo=True)
        self.normal_student = _make_student(username="api_normal_student", demo=False)
        self.client = Client()
        self.headers = {
            "HTTP_X_APP_VERSION": "1.0.0",
            "HTTP_X_APP_BUILD": "1",
            "HTTP_X_APP_PLATFORM": "android",
        }
        TeacherBookingSettings.objects.get_or_create(
            teacher=self.demo_teacher,
            defaults={"booking_enabled": True},
        )
        AppointmentSlot.objects.create(
            teacher=self.demo_teacher,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1),
            status=SlotStatus.AVAILABLE,
        )

    def test_available_teachers_api_hides_demo(self):
        self.client.force_login(self.normal_student)
        url = reverse("tutoring_api:teachers-available")
        resp = self.client.get(url, **self.headers)
        self.assertEqual(resp.status_code, 200)
        ids = {t["id"] for t in resp.json()["teachers"]}
        self.assertNotIn(self.demo_teacher.id, ids)
        self.assertIn(self.normal_teacher.id, ids)

        self.client.force_login(self.demo_student)
        resp = self.client.get(url, **self.headers)
        ids = {t["id"] for t in resp.json()["teachers"]}
        self.assertIn(self.demo_teacher.id, ids)

    def test_appointment_summary_404_for_normal_student(self):
        self.client.force_login(self.normal_student)
        url = reverse(
            "appointments_api:teacher-summary",
            kwargs={"teacher_id": self.demo_teacher.id},
        )
        resp = self.client.get(url, **self.headers)
        self.assertEqual(resp.status_code, 404)

    def test_appointment_summary_ok_for_demo_student(self):
        self.client.force_login(self.demo_student)
        url = reverse(
            "appointments_api:teacher-summary",
            kwargs={"teacher_id": self.demo_teacher.id},
        )
        resp = self.client.get(url, **self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_favorite_toggle_404_for_normal_student(self):
        self.client.force_login(self.normal_student)
        url = reverse(
            "tutoring_api:teachers-favorite-toggle",
            kwargs={"teacher_id": self.demo_teacher.id},
        )
        resp = self.client.post(url, data="{}", content_type="application/json", **self.headers)
        self.assertEqual(resp.status_code, 404)

    def test_favorite_list_excludes_hidden_demo(self):
        TeacherFavorite.objects.create(
            student=self.normal_student, teacher=self.demo_teacher
        )
        TeacherFavorite.objects.create(
            student=self.normal_student, teacher=self.normal_teacher
        )
        self.client.force_login(self.normal_student)
        url = reverse("tutoring_api:teachers-favorites")
        resp = self.client.get(url, **self.headers)
        self.assertEqual(resp.status_code, 200)
        ids = set(resp.json()["teacher_ids"])
        self.assertNotIn(self.demo_teacher.id, ids)
        self.assertIn(self.normal_teacher.id, ids)


class SeedDemoAccountsCommandTests(TestCase):
    def test_seed_creates_three_accounts(self):
        from django.core.management import call_command

        _ensure_role("supervisor")
        _ensure_role("student")
        _ensure_role("teacher")
        call_command("seed_demo_accounts")

        supervisor = User.objects.get(username="super")
        student = User.objects.get(username="student")
        teacher = User.objects.get(username="teacher")

        self.assertTrue(supervisor.is_demo_account)
        self.assertEqual(supervisor.demo_role, DEMO_ROLE_ADMIN)
        self.assertFalse(supervisor.is_superuser)
        self.assertEqual(supervisor.user_type, USER_TYPE_SUPERVISOR)
        self.assertEqual(supervisor.full_name, "مشرف - اختبار")
        self.assertTrue(supervisor.roles.filter(slug="supervisor").exists())

        self.assertTrue(student.is_demo_account)
        self.assertEqual(student.demo_role, DEMO_ROLE_STUDENT)
        self.assertEqual(student.full_name, "طالب - اختبار")
        self.assertTrue(hasattr(student, "student_profile"))
        self.assertEqual(student.student_profile.display_name, "طالب - اختبار")

        self.assertTrue(teacher.is_demo_account)
        self.assertEqual(teacher.demo_role, DEMO_ROLE_TEACHER)
        self.assertEqual(teacher.full_name, "معلم - اختبار")
        self.assertEqual(
            teacher.teacher_profile.approval_status,
            TeacherProfile.ApprovalStatus.APPROVED,
        )
        self.assertEqual(teacher.teacher_profile.display_name, "معلم - اختبار")

        # Idempotent
        call_command("seed_demo_accounts")
        self.assertEqual(
            User.objects.filter(is_demo_account=True, demo_role=DEMO_ROLE_TEACHER).count(),
            1,
        )
        self.assertEqual(User.objects.filter(username="teacher").count(), 1)

    def test_seed_renames_legacy_usernames(self):
        from django.core.management import call_command

        _ensure_role("supervisor")
        _ensure_role("student")
        _ensure_role("teacher")

        legacy_teacher = User.objects.create_user(
            username="demo_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            is_demo_account=True,
            demo_role=DEMO_ROLE_TEACHER,
            full_name="old",
        )
        TeacherProfile.objects.create(
            user=legacy_teacher,
            display_name="old",
            is_approved=True,
            approval_status=TeacherProfile.ApprovalStatus.APPROVED,
        )

        call_command("seed_demo_accounts")
        legacy_teacher.refresh_from_db()
        self.assertEqual(legacy_teacher.username, "teacher")
        self.assertEqual(legacy_teacher.full_name, "معلم - اختبار")
        self.assertEqual(
            User.objects.filter(username__in=["demo_teacher", "teacher"]).count(),
            1,
        )
