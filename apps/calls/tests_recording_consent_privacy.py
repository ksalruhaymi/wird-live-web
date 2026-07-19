"""Recording consent, recording delete, and account deletion tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.calls.models import (
    RECORDING_CONSENT_VERSION,
    CallRecording,
    CallRecordingConsent,
    CallSession,
)
from apps.calls.recording_consent import (
    both_parties_have_recording_consent,
    record_call_recording_consent,
)
from apps.calls.services import _activate_call_session
from identity.accounts.account_deletion import (
    AccountDeletionError,
    delete_user_account,
)
from identity.accounts.user_types import USER_TYPE_STUDENT

User = get_user_model()


class RecordingConsentTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="c_student", password="Pass1234!", user_type=USER_TYPE_STUDENT
        )
        self.teacher = User.objects.create_user(
            username="c_teacher", password="Pass1234!", user_type=USER_TYPE_STUDENT
        )
        # teacher type optional for consent tests
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.PENDING,
            channel_name="ch_consent_1",
        )
        self.client = Client()

    def test_activate_does_not_start_recording_without_consent(self):
        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as start:
            _activate_call_session(self.call)
            start.assert_not_called()

    def test_recording_starts_only_after_both_consents_and_media_ready(self):
        from apps.calls.recording_consent import mark_participant_media_ready

        self.call.status = CallSession.Status.ACTIVE
        self.call.started_at = timezone.now()
        self.call.save(update_fields=["status", "started_at"])

        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            record_call_recording_consent(self.call, self.student, platform="android")
            mock_start.assert_not_called()
            self.assertFalse(both_parties_have_recording_consent(self.call))

            record_call_recording_consent(self.call, self.teacher, platform="ios")
            mock_start.assert_not_called()
            self.assertTrue(both_parties_have_recording_consent(self.call))

            mark_participant_media_ready(
                self.call, self.student, agora_uid=self.student.id
            )
            mock_start.assert_not_called()

            mark_participant_media_ready(
                self.call, self.teacher, agora_uid=self.teacher.id
            )
            mock_start.assert_called_once()
            self.assertEqual(
                CallRecordingConsent.objects.filter(call_session=self.call).count(),
                2,
            )
            self.assertEqual(
                CallRecordingConsent.objects.get(
                    call_session=self.call, user=self.student
                ).consent_version,
                RECORDING_CONSENT_VERSION,
            )

    def test_non_participant_cannot_consent(self):
        other = User.objects.create_user(
            username="c_other", password="Pass1234!", user_type=USER_TYPE_STUDENT
        )
        self.call.status = CallSession.Status.ACTIVE
        self.call.started_at = timezone.now()
        self.call.save(update_fields=["status", "started_at"])
        self.client.force_login(other)
        url = reverse("calls_api:recording-consent", kwargs={"pk": self.call.pk})
        resp = self.client.post(
            url,
            data=json.dumps({"platform": "android"}),
            content_type="application/json",
            HTTP_X_APP_VERSION="1.0.0",
            HTTP_X_APP_BUILD="1",
            HTTP_X_APP_PLATFORM="android",
        )
        self.assertIn(resp.status_code, {403, 404})

    def test_consent_idempotent(self):
        self.call.status = CallSession.Status.ACTIVE
        self.call.started_at = timezone.now()
        self.call.save(update_fields=["status", "started_at"])
        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ):
            record_call_recording_consent(self.call, self.student)
            record_call_recording_consent(self.call, self.student)
        self.assertEqual(
            CallRecordingConsent.objects.filter(
                call_session=self.call, user=self.student
            ).count(),
            1,
        )

    def test_test_call_consent_alone_does_not_start_recording(self):
        from apps.calls.recording_consent import (
            is_test_call_session,
            mark_participant_media_ready,
            maybe_start_recording_if_consents_ready,
            recording_consent_payload,
        )
        from apps.tutoring.models import TeacherProfile

        TeacherProfile.objects.create(user=self.teacher, is_demo_teacher=True)
        self.call.is_test_call = True
        self.call.status = CallSession.Status.ACTIVE
        self.call.started_at = timezone.now()
        self.call.save(update_fields=["is_test_call", "status", "started_at"])
        self.call = CallSession.objects.select_related("student", "teacher").get(
            pk=self.call.pk
        )
        self.assertTrue(is_test_call_session(self.call))

        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            record_call_recording_consent(
                self.call, self.student, platform="ios"
            )
            mock_start.assert_not_called()
            self.assertFalse(maybe_start_recording_if_consents_ready(self.call))
            mock_start.assert_not_called()

            mark_participant_media_ready(self.call, self.student, agora_uid=self.student.id)
            mock_start.assert_called_once()

        payload = recording_consent_payload(
            CallSession.objects.select_related("student", "teacher").get(pk=self.call.pk),
            self.student,
        )
        self.assertTrue(payload["recording_allowed"])
        self.assertTrue(payload["consent_ready"])
        self.assertTrue(payload["participant_media_ready"])
        self.assertTrue(payload["is_test_call"])
        self.assertEqual(
            CallRecordingConsent.objects.filter(
                call_session=self.call, platform="demo_system"
            ).count(),
            0,
        )

    def test_start_cloud_recording_does_not_skip_test_call(self):
        from apps.calls.cloud_recording.service import start_cloud_recording_for_call
        from apps.tutoring.models import TeacherProfile

        TeacherProfile.objects.create(user=self.teacher, is_demo_teacher=True)
        self.call.is_test_call = True
        self.call.status = CallSession.Status.ACTIVE
        self.call.started_at = timezone.now()
        self.call.provider = CallSession.Provider.AGORA
        self.call.channel_name = "ch_test"
        self.call.save(
            update_fields=[
                "is_test_call",
                "status",
                "started_at",
                "provider",
                "channel_name",
            ]
        )
        self.call = CallSession.objects.select_related("student", "teacher").get(
            pk=self.call.pk
        )

        with patch(
            "apps.calls.cloud_recording.service.uses_agora_rtc", return_value=True
        ), patch(
            "apps.calls.cloud_recording.service.cloud_recording_configured",
            return_value=True,
        ), patch(
            "apps.calls.cloud_recording.service.AgoraCloudRecordingClient"
        ) as client_cls:
            instance = client_cls.return_value
            instance.acquire.return_value = "r1"
            instance.start.return_value = "s1"
            start_cloud_recording_for_call(self.call)
            client_cls.assert_called()
            instance.start.assert_called_once()
            start_kwargs = instance.start.call_args.kwargs
            self.assertEqual(
                start_kwargs.get("subscribe_audio_uids"),
                [self.student.id, self.teacher.id],
            )

        rec = CallRecording.objects.get(call_session=self.call)
        self.assertNotEqual(rec.recording_status, CallRecording.RecordingStatus.SKIPPED)
        payload = __import__(
            "apps.calls.recording_consent", fromlist=["recording_consent_payload"]
        ).recording_consent_payload(self.call, self.student)
        self.assertTrue(payload["recording_allowed"])


class RecordingDeleteApiTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="d_student", password="Pass1234!", user_type=USER_TYPE_STUDENT
        )
        self.teacher = User.objects.create_user(
            username="d_teacher", password="Pass1234!", user_type=USER_TYPE_STUDENT
        )
        self.other = User.objects.create_user(
            username="d_other", password="Pass1234!", user_type=USER_TYPE_STUDENT
        )
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ENDED,
            channel_name="ch_del_1",
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )
        self.rec = CallRecording.objects.create(
            call_session=self.call,
            student=self.student,
            teacher=self.teacher,
            session_type="audio",
            recording_status=CallRecording.RecordingStatus.COMPLETED,
            recording_object_key="wird-live/call_call_1/x.mp4",
        )
        self.client = Client()

    @patch("apps.calls.recording_storage.delete_recording_prefix")
    def test_owner_can_delete(self, mock_del):
        mock_del.return_value = (1, [])
        self.client.force_login(self.student)
        url = reverse("calls_api:recording-delete", kwargs={"pk": self.rec.pk})
        resp = self.client.post(
            url,
            HTTP_X_APP_VERSION="1.0.0",
            HTTP_X_APP_BUILD="1",
            HTTP_X_APP_PLATFORM="android",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CallRecording.objects.filter(pk=self.rec.pk).exists())

    def test_non_owner_cannot_delete(self):
        self.client.force_login(self.other)
        url = reverse("calls_api:recording-delete", kwargs={"pk": self.rec.pk})
        resp = self.client.post(
            url,
            HTTP_X_APP_VERSION="1.0.0",
            HTTP_X_APP_BUILD="1",
            HTTP_X_APP_PLATFORM="android",
        )
        self.assertEqual(resp.status_code, 403)


class AccountDeletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="del_user", password="Pass1234!", user_type=USER_TYPE_STUDENT
        )
        self.admin = User.objects.create_superuser(
            username="del_admin", email="a@test.com", password="Pass1234!"
        )

    def test_wrong_password_rejected(self):
        with self.assertRaises(AccountDeletionError):
            delete_user_account(
                self.user, password="wrong", confirmation="DELETE"
            )

    def test_admin_protected(self):
        with self.assertRaises(AccountDeletionError):
            delete_user_account(
                self.admin, password="Pass1234!", confirmation="DELETE"
            )

    @patch("identity.accounts.account_deletion.delete_recording_prefix")
    @patch("identity.accounts.account_deletion.delete_recording_object")
    def test_user_hard_deleted(self, mock_obj, mock_prefix):
        mock_prefix.return_value = (0, [])
        uid = self.user.id
        delete_user_account(self.user, password="Pass1234!", confirmation="DELETE")
        self.assertFalse(User.objects.filter(pk=uid).exists())


class PublicPagesTests(TestCase):
    def test_privacy_and_account_deletion_pages(self):
        c = Client()
        r1 = c.get(reverse("web:privacy_policy"))
        r2 = c.get(reverse("web:account_deletion"))
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertContains(r2, "username")
        self.assertContains(r2, "csrfmiddlewaretoken")

    @patch("web.views.send_mail")
    def test_account_deletion_form_sends_request_email(self, mock_mail):
        c = Client()
        url = reverse("web:account_deletion")
        resp = c.post(
            url,
            data={
                "username": "review_student",
                "email": "review@example.com",
                "notes": "Please delete",
                "company": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        mock_mail.assert_called_once()
        message = mock_mail.call_args.kwargs.get("message")
        if message is None and mock_mail.call_args.args:
            message = mock_mail.call_args.args[1] if len(mock_mail.call_args.args) > 1 else ""
        self.assertIn("review_student", message)
        self.assertNotIn('name="password"', resp.content.decode().lower())

    @patch("web.views.send_mail")
    def test_account_deletion_form_rate_limited(self, mock_mail):
        c = Client()
        url = reverse("web:account_deletion")
        c.post(
            url,
            data={
                "username": "u1",
                "email": "a@example.com",
                "notes": "",
                "company": "",
            },
        )
        mock_mail.reset_mock()
        resp = c.post(
            url,
            data={
                "username": "u1",
                "email": "a@example.com",
                "notes": "",
                "company": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        mock_mail.assert_not_called()
