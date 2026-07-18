"""Email OTP send/verify expiry and resend cooldown tests."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from identity.accounts.auth.email_verification_service import (
    OTP_EXPIRED_CODE,
    OTP_EXPIRED_MESSAGE,
    OTP_RESEND_COOLDOWN_CODE,
    _CODE_TTL_MINUTES,
    _RESEND_COOLDOWN_SECONDS,
    send_registration_code,
    verify_registration_code,
)
from identity.accounts.models import EmailRegistrationVerification


class EmailOtpExpiryApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.email = "otp.user@example.com"
        self.headers = {
            "HTTP_X_APP_VERSION": "1.0.0",
            "HTTP_X_APP_BUILD": "1",
            "HTTP_X_APP_PLATFORM": "android",
        }
        self.send_url = reverse("accounts_auth_api:send_email_code")
        self.verify_url = reverse("accounts_auth_api:verify_email_code")

    @patch("identity.accounts.auth.email_verification_service.send_mail")
    def test_send_returns_expiry_fields_without_otp(self, mock_mail):
        with patch(
            "identity.accounts.auth.email_verification_service._generate_code",
            return_value="1234",
        ):
            resp = self.client.post(
                self.send_url,
                data=json.dumps({"email": self.email}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertIn("expires_at", body)
        self.assertIn("expires_in_seconds", body)
        self.assertIn("server_time", body)
        self.assertIn("resend_available_in_seconds", body)
        self.assertEqual(body["expires_in_seconds"], _CODE_TTL_MINUTES * 60)
        self.assertEqual(body["resend_available_in_seconds"], _RESEND_COOLDOWN_SECONDS)
        self.assertNotIn("code", body)  # must not expose OTP
        self.assertNotIn("otp", body)
        blob = json.dumps(body)
        self.assertNotIn("1234", blob)
        mock_mail.assert_called_once()
        # Mail args must contain code, but response/logs path must not.
        mail_kwargs = mock_mail.call_args.kwargs
        self.assertIn("1234", mail_kwargs["message"])

    @patch("identity.accounts.auth.email_verification_service.send_mail")
    def test_otp_expires_by_server_clock(self, _mail):
        with patch(
            "identity.accounts.auth.email_verification_service._generate_code",
            return_value="9999",
        ):
            send_registration_code(self.email)

        row = EmailRegistrationVerification.objects.get(email=self.email)
        row.expires_at = timezone.now() - timedelta(seconds=1)
        row.save(update_fields=["expires_at"])

        token, message, code = verify_registration_code(self.email, "9999")
        self.assertIsNone(token)
        self.assertEqual(message, OTP_EXPIRED_MESSAGE)
        self.assertEqual(code, OTP_EXPIRED_CODE)

        resp = self.client.post(
            self.verify_url,
            data=json.dumps({"email": self.email, "code": "9999"}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body.get("code"), OTP_EXPIRED_CODE)
        self.assertNotIn("9999", json.dumps(body))

    @patch("identity.accounts.auth.email_verification_service.send_mail")
    def test_resend_invalidates_previous_otp(self, _mail):
        with patch(
            "identity.accounts.auth.email_verification_service._generate_code",
            return_value="1111",
        ):
            first = send_registration_code(self.email)
        self.assertTrue(first.ok)
        first_hash = EmailRegistrationVerification.objects.get(
            email=self.email
        ).code_hash

        # Bypass cooldown for the second send.
        EmailRegistrationVerification.objects.filter(email=self.email).update(
            created_at=timezone.now() - timedelta(seconds=_RESEND_COOLDOWN_SECONDS + 1)
        )

        with patch(
            "identity.accounts.auth.email_verification_service._generate_code",
            return_value="2222",
        ):
            second = send_registration_code(self.email)
        self.assertTrue(second.ok)

        rows = EmailRegistrationVerification.objects.filter(
            email=self.email, verified_at__isnull=True
        )
        self.assertEqual(rows.count(), 1)
        self.assertNotEqual(rows.first().code_hash, first_hash)

        token_old, _, _ = verify_registration_code(self.email, "1111")
        self.assertIsNone(token_old)
        token_new, err, _ = verify_registration_code(self.email, "2222")
        self.assertIsNone(err)
        self.assertTrue(token_new)

    @patch("identity.accounts.auth.email_verification_service.send_mail")
    def test_resend_rate_limit(self, _mail):
        with patch(
            "identity.accounts.auth.email_verification_service._generate_code",
            return_value="3333",
        ):
            first = self.client.post(
                self.send_url,
                data=json.dumps({"email": self.email}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            self.send_url,
            data=json.dumps({"email": self.email}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(second.status_code, 429)
        body = second.json()
        self.assertFalse(body["success"])
        self.assertEqual(body.get("code"), OTP_RESEND_COOLDOWN_CODE)
        self.assertGreater(body.get("resend_available_in_seconds", 0), 0)
        self.assertIn("server_time", body)
        self.assertNotIn("3333", json.dumps(body))

class EmailAlreadyRegisteredTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.headers = {
            "HTTP_X_APP_VERSION": "1.0.0",
            "HTTP_X_APP_BUILD": "1",
            "HTTP_X_APP_PLATFORM": "android",
        }
        self.send_url = reverse("accounts_auth_api:send_email_code")

    @patch("identity.accounts.auth.email_verification_service.send_mail")
    def test_existing_email_rejected_without_otp(self, mock_mail):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        email = "taken@example.com"
        User.objects.create_user(username="taken_user", email=email, password="Str0ngPass!9")

        before = EmailRegistrationVerification.objects.count()
        resp = self.client.post(
            self.send_url,
            data=json.dumps({"email": email}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertFalse(body.get("success", True))
        self.assertEqual(body.get("code"), "email_already_registered")
        self.assertIn("مسجل مسبقًا", body.get("message", ""))
        mock_mail.assert_not_called()
        self.assertEqual(EmailRegistrationVerification.objects.count(), before)
        self.assertNotIn("otp", json.dumps(body).lower())

    @patch("identity.accounts.auth.email_verification_service.send_mail")
    def test_existing_email_case_insensitive(self, mock_mail):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        User.objects.create_user(
            username="case_user",
            email="user@email.com",
            password="Str0ngPass!9",
        )
        resp = self.client.post(
            self.send_url,
            data=json.dumps({"email": "USER@EMAIL.COM"}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json().get("code"), "email_already_registered")
        mock_mail.assert_not_called()

    def test_register_integrity_error_maps_to_email_already_registered(self):
        from django.contrib.auth import get_user_model
        from django.db import IntegrityError

        from identity.accounts.auth.registration_service import (
            RegistrationFailed,
            register_account,
        )
        from identity.accounts.user_types import USER_TYPE_STUDENT

        User = get_user_model()
        email = "race@example.com"
        User.objects.create_user(
            username="race_user",
            email=email,
            password="Str0ngPass!9",
        )

        with patch(
            "identity.accounts.auth.registration_service.User.objects.create_user",
            side_effect=IntegrityError("duplicate"),
        ):
            with self.assertRaises(RegistrationFailed) as ctx:
                register_account(
                    full_name="متسابق",
                    email=email,
                    password="Str0ngPass!9",
                    user_type_value=USER_TYPE_STUDENT,
                    gender="male",
                    verification_token="",
                )
        self.assertEqual(ctx.exception.code, "email_already_registered")
        self.assertNotIn("Traceback", str(ctx.exception))
