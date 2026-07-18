"""Email OTP + registration session completion tests."""

from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from identity.accounts.auth.email_verification_service import (
    REGISTRATION_SESSION_EXPIRED_CODE,
    REGISTRATION_SESSION_EXPIRED_MESSAGE,
    consume_verification_token,
    validate_registration_session,
    verify_registration_code,
)
from identity.accounts.auth.registration_service import (
    register_account,
    validate_registration_payload,
)
from identity.accounts.models import EmailRegistrationVerification
from identity.accounts.user_types import USER_TYPE_STUDENT

User = get_user_model()


class RegistrationSessionFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.email = "new.student@example.com"
        self.headers = {
            "HTTP_X_APP_VERSION": "1.0.0",
            "HTTP_X_APP_BUILD": "1",
            "HTTP_X_APP_PLATFORM": "android",
        }

    def _create_pending_otp(self, code: str = "1234") -> EmailRegistrationVerification:
        import hashlib

        return EmailRegistrationVerification.objects.create(
            email=self.email,
            code_hash=hashlib.sha256(code.encode("utf-8")).hexdigest(),
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def test_otp_success_then_complete_registration(self):
        self._create_pending_otp("4321")
        token, err = verify_registration_code(self.email, "4321")
        self.assertIsNone(err)
        self.assertTrue(token)

        # OTP must not be reusable after verify.
        token2, err2 = verify_registration_code(self.email, "4321")
        self.assertIsNone(token2)
        self.assertIsNotNone(err2)

        payload, message, code = validate_registration_payload(
            {
                "full_name": "طالب جديد",
                "email": self.email,
                "password": "Str0ngPass!9",
                "confirm_password": "Str0ngPass!9",
                "user_type": "student",
                "gender": "male",
                "verification_token": token,
            },
            require_verification_token=True,
        )
        self.assertIsNone(message)
        self.assertIsNone(code)
        self.assertIsNotNone(payload)

        # Peek does not consume.
        self.assertTrue(
            EmailRegistrationVerification.objects.filter(
                email=self.email, verification_token=token
            ).exists()
        )

        user = register_account(
            full_name=payload["full_name"],
            email=payload["email"],
            password=payload["password"],
            user_type_value=payload["user_type_value"],
            gender=payload["gender"],
            verification_token=token,
        )
        self.assertEqual(user.email, self.email)
        self.assertFalse(
            EmailRegistrationVerification.objects.filter(
                email=self.email, verification_token=token
            ).exists()
        )

    def test_otp_not_reused_after_verify(self):
        self._create_pending_otp("1111")
        verify_registration_code(self.email, "1111")
        again, message = verify_registration_code(self.email, "1111")
        self.assertIsNone(again)
        self.assertEqual(message, "رمز التحقق غير صالح.")

    def test_registration_session_expired(self):
        self._create_pending_otp("2222")
        token, _ = verify_registration_code(self.email, "2222")
        row = EmailRegistrationVerification.objects.get(verification_token=token)
        row.token_expires_at = timezone.now() - timedelta(seconds=1)
        row.save(update_fields=["token_expires_at"])

        payload, message, code = validate_registration_payload(
            {
                "full_name": "طالب",
                "email": self.email,
                "password": "Str0ngPass!9",
                "confirm_password": "Str0ngPass!9",
                "user_type": "student",
                "gender": "male",
                "verification_token": token,
            },
            require_verification_token=True,
        )
        self.assertIsNone(payload)
        self.assertEqual(message, REGISTRATION_SESSION_EXPIRED_MESSAGE)
        self.assertEqual(code, REGISTRATION_SESSION_EXPIRED_CODE)

    def test_session_cannot_be_reused_after_account_created(self):
        self._create_pending_otp("3333")
        token, _ = verify_registration_code(self.email, "3333")
        register_account(
            full_name="طالب",
            email=self.email,
            password="Str0ngPass!9",
            user_type_value=USER_TYPE_STUDENT,
            gender="male",
            verification_token=token,
        )
        self.assertFalse(consume_verification_token(self.email, token))
        with self.assertRaises(Exception):
            validate_registration_session(self.email, token)

    def test_validation_failure_does_not_consume_session(self):
        self._create_pending_otp("4444")
        token, _ = verify_registration_code(self.email, "4444")
        payload, message, _code = validate_registration_payload(
            {
                "full_name": "طالب",
                "email": self.email,
                "password": "password",  # common / weak
                "confirm_password": "password",
                "user_type": "student",
                "gender": "male",
                "verification_token": token,
            },
            require_verification_token=True,
        )
        self.assertIsNone(payload)
        self.assertIsNotNone(message)
        self.assertNotEqual(message, REGISTRATION_SESSION_EXPIRED_MESSAGE)
        self.assertTrue(
            EmailRegistrationVerification.objects.filter(
                verification_token=token
            ).exists()
        )

        # Retry with strong password still works.
        payload2, message2, _ = validate_registration_payload(
            {
                "full_name": "طالب",
                "email": self.email,
                "password": "Str0ngPass!9",
                "confirm_password": "Str0ngPass!9",
                "user_type": "student",
                "gender": "male",
                "verification_token": token,
            },
            require_verification_token=True,
        )
        self.assertIsNone(message2)
        self.assertIsNotNone(payload2)
        register_account(
            full_name=payload2["full_name"],
            email=payload2["email"],
            password=payload2["password"],
            user_type_value=payload2["user_type_value"],
            gender=payload2["gender"],
            verification_token=token,
        )

    @patch("identity.accounts.auth.email_verification_service.send_mail")
    def test_api_verify_then_register(self, _mail):
        send_url = reverse("accounts_auth_api:send_email_code")
        verify_url = reverse("accounts_auth_api:verify_email_code")
        register_url = reverse("accounts_auth_api:register")

        with patch(
            "identity.accounts.auth.email_verification_service._generate_code",
            return_value="5555",
        ):
            resp = self.client.post(
                send_url,
                data=json.dumps({"email": self.email}),
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(
            verify_url,
            data=json.dumps({"email": self.email, "code": "5555"}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        token = body["verification_token"]
        self.assertEqual(body.get("registration_session_token"), token)

        resp = self.client.post(
            register_url,
            data=json.dumps(
                {
                    "full_name": "طالب API",
                    "email": self.email,
                    "password": "Str0ngPass!9",
                    "confirm_password": "Str0ngPass!9",
                    "user_type": "student",
                    "gender": "male",
                    "verification_token": token,
                }
            ),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(User.objects.filter(email=self.email).exists())

        # Second register with same session token fails (not as OTP expiry).
        resp2 = self.client.post(
            register_url,
            data=json.dumps(
                {
                    "full_name": "طالب 2",
                    "email": self.email,
                    "password": "Str0ngPass!9",
                    "confirm_password": "Str0ngPass!9",
                    "user_type": "student",
                    "gender": "male",
                    "verification_token": token,
                }
            ),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp2.status_code, 400)
        data2 = resp2.json()
        self.assertNotEqual(
            data2.get("message"),
            "انتهت صلاحية التحقق من البريد. أعد المحاولة.",
        )
