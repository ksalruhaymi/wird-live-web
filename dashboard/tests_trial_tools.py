"""Tests for superuser-only trial purge tools (calls + users)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.appointments.models import (
    Appointment,
    AppointmentSlot,
    AppointmentStatus,
    SessionType,
    SlotStatus,
)
from apps.calls.models import (
    CallPeerRating,
    CallPeerRatingAnswer,
    CallRecording,
    CallRecordingConsent,
    CallSession,
    RatingCategoryConfig,
    RatingQuestion,
    SessionEvaluation,
)
from apps.calls.trial_cleanup import CALL_TABLES_FOR_SEQUENCE_RESET, purge_all_call_data
from core.utils.postgres_sequences import reset_sequence
from identity.accounts.demo_accounts import (
    DEMO_ROLE_ADMIN,
    DEMO_ROLE_STUDENT,
    DEMO_ROLE_TEACHER,
    DEMO_STUDENT_USERNAME,
    DEMO_SUPERVISOR_USERNAME,
    DEMO_TEACHER_USERNAME,
)
from identity.accounts.trial_cleanup import purge_non_protected_users
from identity.accounts.user_types import (
    USER_TYPE_ADMIN,
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Role

User = get_user_model()


class TrialToolsAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.superuser = User.objects.create_superuser(
            username="trial_super",
            email="trial_super@example.com",
            password="Pass1234!",
        )
        cls.admin = User.objects.create_user(
            username="trial_admin",
            password="Pass1234!",
            user_type=USER_TYPE_ADMIN,
            email="trial_admin@example.com",
        )
        cls.admin.roles.set([Role.objects.get(slug="admin")])
        cls.supervisor = User.objects.create_user(
            username="trial_supervisor",
            password="Pass1234!",
            user_type=USER_TYPE_SUPERVISOR,
            email="trial_supervisor@example.com",
            is_superuser=False,
        )
        cls.supervisor.roles.set([Role.objects.get(slug="supervisor")])

    def setUp(self):
        self.client = Client()

    def test_purge_calls_button_hidden_for_non_superuser(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:call_session_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "حذف جميع المكالمات")
        self.assertNotContains(response, reverse("dashboard:purge_all_calls"))

    def test_purge_calls_button_visible_for_superuser(self):
        # call_hub tab checks use resolver (roles), not User.has_permission.
        self.superuser.roles.set([Role.objects.get(slug="admin")])
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("dashboard:call_session_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "حذف جميع المكالمات")
        self.assertContains(response, reverse("dashboard:purge_all_calls"))

    def test_purge_users_button_hidden_for_non_superuser(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:dashboard_users_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "حذف جميع المستخدمين غير المحميين")
        self.assertNotContains(
            response, reverse("dashboard:purge_non_protected_users")
        )

    def test_purge_users_button_visible_for_superuser(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("dashboard:dashboard_users_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "حذف جميع المستخدمين غير المحميين")
        self.assertContains(
            response, reverse("dashboard:purge_non_protected_users")
        )

    def test_purge_calls_403_for_non_superuser(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:purge_all_calls"))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            reverse("dashboard:purge_all_calls"),
            {"confirmation": "DELETE ALL CALLS"},
        )
        self.assertEqual(response.status_code, 403)

    def test_purge_users_403_for_non_superuser(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:purge_non_protected_users"))
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            reverse("dashboard:purge_non_protected_users"),
            {"confirmation": "DELETE ALL USERS"},
        )
        self.assertEqual(response.status_code, 403)

    def test_supervisor_non_superuser_cannot_see_or_access_purge_tools(self):
        self.assertFalse(self.supervisor.is_superuser)
        self.client.force_login(self.supervisor)

        calls_page = self.client.get(reverse("dashboard:call_session_list"))
        self.assertEqual(calls_page.status_code, 200)
        self.assertNotContains(calls_page, "حذف جميع المكالمات")
        self.assertNotContains(calls_page, reverse("dashboard:purge_all_calls"))

        users_page = self.client.get(reverse("dashboard:dashboard_users_list"))
        self.assertEqual(users_page.status_code, 200)
        self.assertNotContains(users_page, "حذف جميع المستخدمين غير المحميين")
        self.assertNotContains(
            users_page, reverse("dashboard:purge_non_protected_users")
        )

        self.assertEqual(
            self.client.get(reverse("dashboard:purge_all_calls")).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("dashboard:purge_all_calls"),
                {"confirmation": "DELETE ALL CALLS"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                reverse("dashboard:purge_non_protected_users")
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("dashboard:purge_non_protected_users"),
                {"confirmation": "DELETE ALL USERS"},
            ).status_code,
            403,
        )


class TrialPurgeCallsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="purge_calls_super",
            email="purge_calls_super@example.com",
            password="Pass1234!",
        )
        self.student = User.objects.create_user(
            username="purge_calls_student",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
        )
        self.teacher = User.objects.create_user(
            username="purge_calls_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
        )
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.MOCK,
            status=CallSession.Status.ENDED,
            channel_name="ch_purge_1",
        )
        self.recording = CallRecording.objects.create(
            call_session=self.call,
            student=self.student,
            teacher=self.teacher,
            session_type="audio",
            recording_status=CallRecording.RecordingStatus.COMPLETED,
            recording_object_key="wird-live/call_purge/1.m3u8",
        )
        self.rating = CallPeerRating.objects.create(
            call_session=self.call,
            rater=self.student,
            rated=self.teacher,
            rater_role=CallPeerRating.RaterRole.STUDENT,
            status=CallPeerRating.Status.COMPLETED,
            competence=5,
        )
        self.question = RatingQuestion.objects.create(
            category=RatingQuestion.Category.TEACHER,
            question_text="هل كان المعلم واضحًا؟",
            order=1,
        )
        self.category_config = RatingCategoryConfig.objects.create(
            category=RatingQuestion.Category.TEACHER,
            is_active=True,
        )
        CallPeerRatingAnswer.objects.create(
            rating=self.rating,
            question=self.question,
            stars=5,
        )
        CallRecordingConsent.objects.create(
            call_session=self.call,
            user=self.student,
            platform="android",
            consented_at=timezone.now(),
        )
        SessionEvaluation.objects.create(
            call_session=self.call,
            student=self.student,
            teacher=self.teacher,
            status=SessionEvaluation.Status.COMPLETED,
        )
        slot = AppointmentSlot.objects.create(
            teacher=self.teacher,
            start_at=timezone.now() + timedelta(days=1),
            end_at=timezone.now() + timedelta(days=1, hours=1),
            status=SlotStatus.RESERVED,
        )
        self.appointment = Appointment.objects.create(
            teacher=self.teacher,
            student=self.student,
            slot=slot,
            session_type=SessionType.RECITATION,
            status=AppointmentStatus.CONFIRMED,
            booked_at=timezone.now(),
            call_session=self.call,
        )

    def test_get_shows_confirm_page_without_deleting(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("dashboard:purge_all_calls"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DELETE ALL CALLS")
        self.assertEqual(CallSession.objects.count(), 1)

    def test_wrong_confirmation_rejected(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("dashboard:purge_all_calls"),
            {"confirmation": "delete all calls"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CallSession.objects.count(), 1)
        msgs = [m.message for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("نص التأكيد غير صحيح" in m for m in msgs))

    @patch("apps.calls.trial_cleanup.delete_recording_prefix", return_value=(2, []))
    @patch("apps.calls.trial_cleanup.delete_recording_object")
    def test_purge_deletes_calls_keeps_rating_settings(self, _obj, _prefix):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("dashboard:purge_all_calls"),
            {"confirmation": "DELETE ALL CALLS"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CallSession.objects.count(), 0)
        self.assertEqual(CallRecording.objects.count(), 0)
        self.assertEqual(CallPeerRating.objects.count(), 0)
        self.assertEqual(CallPeerRatingAnswer.objects.count(), 0)
        self.assertEqual(CallRecordingConsent.objects.count(), 0)
        self.assertEqual(SessionEvaluation.objects.count(), 0)
        self.assertEqual(RatingQuestion.objects.count(), 1)
        self.assertEqual(RatingCategoryConfig.objects.count(), 1)
        self.appointment.refresh_from_db()
        self.assertIsNone(self.appointment.call_session_id)
        msgs = [m.message for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("تم حذف بيانات المكالمات" in m for m in msgs))

    @patch("apps.calls.trial_cleanup.delete_recording_prefix", return_value=(1, []))
    def test_sequence_reset_called_for_call_tables(self, _prefix):
        with patch(
            "apps.calls.trial_cleanup.reset_sequence", return_value=1
        ) as mock_reset:
            purge_all_call_data(actor=self.superuser)
        called_tables = {c.args[0] for c in mock_reset.call_args_list}
        self.assertTrue(set(CALL_TABLES_FOR_SEQUENCE_RESET).issubset(called_tables))
        self.assertEqual(CallSession.objects.count(), 0)


class TrialPurgeUsersTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="purge_users_super",
            email="purge_users_super@example.com",
            password="Pass1234!",
        )
        self.demo_super = User.objects.create_user(
            username=DEMO_SUPERVISOR_USERNAME,
            password="Pass1234!",
            user_type=USER_TYPE_ADMIN,
            is_demo_account=True,
            demo_role=DEMO_ROLE_ADMIN,
            email="demo_super@example.com",
        )
        self.demo_student = User.objects.create_user(
            username=DEMO_STUDENT_USERNAME,
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
            is_demo_account=True,
            demo_role=DEMO_ROLE_STUDENT,
            email="demo_student@example.com",
        )
        self.demo_teacher = User.objects.create_user(
            username=DEMO_TEACHER_USERNAME,
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            is_demo_account=True,
            demo_role=DEMO_ROLE_TEACHER,
            email="demo_teacher@example.com",
        )
        self.other_super = User.objects.create_superuser(
            username="other_super",
            email="other_super@example.com",
            password="Pass1234!",
        )
        self.victim = User.objects.create_user(
            username="victim_user",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
            email="victim@example.com",
        )
        self.victim_teacher = User.objects.create_user(
            username="victim_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            email="victim_teacher@example.com",
        )
        call = CallSession.objects.create(
            student=self.victim,
            teacher=self.victim_teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.MOCK,
            status=CallSession.Status.ENDED,
            channel_name="ch_purge_user",
        )
        CallRecording.objects.create(
            call_session=call,
            student=self.victim,
            teacher=self.victim_teacher,
            session_type="audio",
            recording_status=CallRecording.RecordingStatus.COMPLETED,
            recording_object_key="wird-live/call_victim/1.m3u8",
        )

    def test_get_does_not_delete_users(self):
        self.client.force_login(self.superuser)
        before = User.objects.count()
        response = self.client.get(reverse("dashboard:purge_non_protected_users"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DELETE ALL USERS")
        self.assertEqual(User.objects.count(), before)

    def test_wrong_confirmation_rejected(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("dashboard:purge_non_protected_users"),
            {"confirmation": "WRONG"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="victim_user").exists())
        msgs = [m.message for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("نص التأكيد غير صحيح" in m for m in msgs))

    @patch(
        "identity.accounts.account_deletion.delete_recording_prefix",
        return_value=(1, []),
    )
    @patch("identity.accounts.account_deletion.delete_recording_object")
    def test_purge_keeps_protected_deletes_victims(self, _obj, _prefix):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("dashboard:purge_non_protected_users"),
            {"confirmation": "DELETE ALL USERS"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(username="victim_user").exists())
        self.assertFalse(User.objects.filter(username="victim_teacher").exists())
        self.assertTrue(
            User.objects.filter(username=DEMO_SUPERVISOR_USERNAME).exists()
        )
        self.assertTrue(User.objects.filter(username=DEMO_STUDENT_USERNAME).exists())
        self.assertTrue(User.objects.filter(username=DEMO_TEACHER_USERNAME).exists())
        self.assertTrue(User.objects.filter(username="purge_users_super").exists())
        self.assertTrue(User.objects.filter(username="other_super").exists())
        self.assertEqual(CallSession.objects.count(), 0)
        msgs = [m.message for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("تم حذف المستخدمين غير المحميين" in m for m in msgs))

    @patch(
        "identity.accounts.account_deletion.delete_recording_prefix",
        return_value=(0, []),
    )
    def test_user_sequence_reset_invoked(self, _prefix):
        with patch(
            "identity.accounts.trial_cleanup.reset_sequence", return_value=10
        ) as mock_reset:
            result = purge_non_protected_users(actor=self.superuser)
        mock_reset.assert_called_once_with(User._meta.db_table)
        self.assertEqual(result["next_user_id"], 10)
        self.assertGreaterEqual(result["deleted_users_count"], 2)


class PostgresSequenceHelperTests(TestCase):
    def test_reset_sequence_non_postgres_returns_none(self):
        if connection.vendor == "postgresql":
            self.skipTest("Uses SQLite-style assertion path")
        self.assertIsNone(reset_sequence("auth_user"))

    def test_reset_sequence_postgres_empty_and_max(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL only")
        User.objects.all().delete()
        self.assertEqual(reset_sequence(User._meta.db_table), 1)
        u = User.objects.create_user(username="seq_u1", password="Pass1234!")
        self.assertEqual(reset_sequence(User._meta.db_table), u.id + 1)
