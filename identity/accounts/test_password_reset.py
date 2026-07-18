import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from identity.accounts.auth.password_reset_service import (
    GENERIC_REQUEST_MESSAGE,
    MAX_ATTEMPTS,
    RESEND_COOLDOWN_SECONDS,
    _hash_secret,
    confirm_password_reset,
    request_password_reset,
    resend_password_reset_code,
    verify_password_reset_code,
)
from identity.accounts.models import PasswordResetCode
from identity.accounts.user_types import USER_TYPE_STUDENT

User = get_user_model()

MOBILE_API_HEADERS = {
    "HTTP_X_APP_VERSION": "99.0.0",
    "HTTP_X_APP_BUILD": "99999",
    "HTTP_X_APP_PLATFORM": "android",
}

REQUEST_URL = reverse("accounts_auth_api:password_reset_request")
RESEND_URL = reverse("accounts_auth_api:password_reset_resend")
VERIFY_URL = reverse("accounts_auth_api:password_reset_verify")
CONFIRM_URL = reverse("accounts_auth_api:password_reset_confirm")


@override_settings(
    AXES_ENABLED=False,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PasswordResetApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="reset_user",
            email="Reset.User@Example.com",
            password="OldPassword123!",
            user_type=USER_TYPE_STUDENT,
        )
        self.user_no_email = User.objects.create_user(
            username="no_email_user",
            email="",
            password="OldPassword123!",
            user_type=USER_TYPE_STUDENT,
        )

    def _post(self, url, payload):
        return self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )

    def _latest_code_record(self, user=None):
        user = user or self.user
        return (
            PasswordResetCode.objects.filter(user=user)
            .order_by("-created_at")
            .first()
        )

    def _raw_code_from_email(self):
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        for token in body.split():
            if token.isdigit() and len(token) == 6:
                return token
        self.fail(f"No 6-digit code found in email body: {body!r}")

    def test_request_by_email_sends_hashed_code(self):
        response = self._post(REQUEST_URL, {"identifier": "reset.user@example.com"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["message"], GENERIC_REQUEST_MESSAGE)
        self.assertNotIn("user", data)
        self.assertNotIn("email", data)

        record = self._latest_code_record()
        self.assertIsNotNone(record)
        code = self._raw_code_from_email()
        self.assertEqual(record.code_hash, _hash_secret(code))
        self.assertNotEqual(record.code_hash, code)
        self.assertIn("رمز استعادة كلمة المرور", mail.outbox[0].subject)

    def test_request_by_username(self):
        response = self._post(REQUEST_URL, {"identifier": "reset_user"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], GENERIC_REQUEST_MESSAGE)
        self.assertEqual(len(mail.outbox), 1)

    def test_request_unknown_account_same_response(self):
        response = self._post(REQUEST_URL, {"identifier": "nobody@example.com"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["message"], GENERIC_REQUEST_MESSAGE)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(PasswordResetCode.objects.exists())

    def test_request_user_without_email_same_response(self):
        response = self._post(REQUEST_URL, {"identifier": "no_email_user"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], GENERIC_REQUEST_MESSAGE)
        self.assertEqual(len(mail.outbox), 0)

    def test_verify_correct_code_returns_reset_token(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        code = self._raw_code_from_email()
        response = self._post(
            VERIFY_URL,
            {"identifier": self.user.username, "code": code},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["reset_token"])
        record = self._latest_code_record()
        self.assertIsNotNone(record.verified_at)
        self.assertEqual(record.reset_token_hash, _hash_secret(data["reset_token"]))
        self.assertNotEqual(record.reset_token_hash, data["reset_token"])

    def test_verify_wrong_code_increments_attempts(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        response = self._post(
            VERIFY_URL,
            {"identifier": self.user.email, "code": "000000"},
        )
        self.assertEqual(response.status_code, 400)
        record = self._latest_code_record()
        self.assertEqual(record.attempts_count, 1)
        self.assertIsNone(record.verified_at)

    def test_verify_expired_code(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        code = self._raw_code_from_email()
        record = self._latest_code_record()
        record.expires_at = timezone.now() - timedelta(minutes=1)
        record.save(update_fields=["expires_at"])
        response = self._post(
            VERIFY_URL,
            {"identifier": self.user.email, "code": code},
        )
        self.assertEqual(response.status_code, 400)

    def test_max_attempts_invalidates_code(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        for _ in range(MAX_ATTEMPTS):
            response = self._post(
                VERIFY_URL,
                {"identifier": self.user.email, "code": "111111"},
            )
            self.assertEqual(response.status_code, 400)
        record = self._latest_code_record()
        self.assertIsNotNone(record.used_at)
        self.assertEqual(record.attempts_count, MAX_ATTEMPTS)

    def test_confirm_success_logs_in_and_sends_confirmation(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        code = self._raw_code_from_email()
        verify = self._post(
            VERIFY_URL,
            {"identifier": self.user.email, "code": code},
        )
        reset_token = verify.json()["reset_token"]
        mail.outbox.clear()

        response = self._post(
            CONFIRM_URL,
            {
                "reset_token": reset_token,
                "new_password": "BrandNewPass99!",
                "new_password_confirmation": "BrandNewPass99!",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["username"], self.user.username)
        self.assertIn("session_id", data)
        self.assertIn("csrf_token", data)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNewPass99!"))
        self.assertFalse(self.user.check_password("OldPassword123!"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("تم تحديث كلمة المرور", mail.outbox[0].subject)

        record = self._latest_code_record()
        self.assertIsNotNone(record.used_at)

    def test_confirm_password_mismatch(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        code = self._raw_code_from_email()
        reset_token = self._post(
            VERIFY_URL,
            {"identifier": self.user.email, "code": code},
        ).json()["reset_token"]
        response = self._post(
            CONFIRM_URL,
            {
                "reset_token": reset_token,
                "new_password": "BrandNewPass99!",
                "new_password_confirmation": "DifferentPass99!",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("غير متطابق", response.json()["message"])

    def test_confirm_weak_password(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        code = self._raw_code_from_email()
        reset_token = self._post(
            VERIFY_URL,
            {"identifier": self.user.email, "code": code},
        ).json()["reset_token"]
        response = self._post(
            CONFIRM_URL,
            {
                "reset_token": reset_token,
                "new_password": "123",
                "new_password_confirmation": "123",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_confirm_invalid_reset_token(self):
        response = self._post(
            CONFIRM_URL,
            {
                "reset_token": "not-a-real-token",
                "new_password": "BrandNewPass99!",
                "new_password_confirmation": "BrandNewPass99!",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_confirm_expired_reset_token(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        code = self._raw_code_from_email()
        reset_token = self._post(
            VERIFY_URL,
            {"identifier": self.user.email, "code": code},
        ).json()["reset_token"]
        record = self._latest_code_record()
        record.reset_token_expires_at = timezone.now() - timedelta(minutes=1)
        record.save(update_fields=["reset_token_expires_at"])
        response = self._post(
            CONFIRM_URL,
            {
                "reset_token": reset_token,
                "new_password": "BrandNewPass99!",
                "new_password_confirmation": "BrandNewPass99!",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_code_and_token_are_single_use(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        code = self._raw_code_from_email()
        reset_token = self._post(
            VERIFY_URL,
            {"identifier": self.user.email, "code": code},
        ).json()["reset_token"]

        # Code cannot be verified again
        again = self._post(
            VERIFY_URL,
            {"identifier": self.user.email, "code": code},
        )
        self.assertEqual(again.status_code, 400)

        self._post(
            CONFIRM_URL,
            {
                "reset_token": reset_token,
                "new_password": "BrandNewPass99!",
                "new_password_confirmation": "BrandNewPass99!",
            },
        )
        reuse = self._post(
            CONFIRM_URL,
            {
                "reset_token": reset_token,
                "new_password": "AnotherPass99!",
                "new_password_confirmation": "AnotherPass99!",
            },
        )
        self.assertEqual(reuse.status_code, 400)

    def test_resend_cooldown(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        response = self._post(RESEND_URL, {"identifier": self.user.email})
        self.assertEqual(response.status_code, 429)

        record = self._latest_code_record()
        record.created_at = timezone.now() - timedelta(
            seconds=RESEND_COOLDOWN_SECONDS + 1
        )
        record.save(update_fields=["created_at"])
        mail.outbox.clear()
        response = self._post(RESEND_URL, {"identifier": self.user.email})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_request_invalidates_previous_unused_codes(self):
        self._post(REQUEST_URL, {"identifier": self.user.email})
        first = self._latest_code_record()
        # Bypass cooldown by backdating
        first.created_at = timezone.now() - timedelta(minutes=2)
        first.save(update_fields=["created_at"])
        self._post(REQUEST_URL, {"identifier": self.user.email})
        first.refresh_from_db()
        self.assertIsNotNone(first.used_at)
        self.assertEqual(
            PasswordResetCode.objects.filter(user=self.user, used_at__isnull=True).count(),
            1,
        )

    def test_service_confirm_uses_transaction_and_login(self):
        ok, _ = request_password_reset(self.user.email)
        self.assertTrue(ok)
        code = self._raw_code_from_email()
        token, err = verify_password_reset_code(self.user.email, code)
        self.assertIsNone(err)
        self.assertTrue(token)

        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.post("/api/v1/auth/password-reset/confirm/")
        request.session = self.client.session
        user, message = confirm_password_reset(
            request,
            reset_token=token,
            new_password="ServiceConfirm99!",
            new_password_confirmation="ServiceConfirm99!",
        )
        self.assertIsNone(message)
        self.assertEqual(user.pk, self.user.pk)
