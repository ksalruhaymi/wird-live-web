import json

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings

from identity.accounts.user_types import USER_TYPE_ADMIN, USER_TYPE_STUDENT
from identity.rbac.models import Role

User = get_user_model()

MOBILE_API_HEADERS = {
    "HTTP_X_APP_VERSION": "99.0.0",
    "HTTP_X_APP_BUILD": "99999",
    "HTTP_X_APP_PLATFORM": "android",
}


@override_settings(AXES_ENABLED=False)
class SingleActiveSessionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = User.objects.create_user(
            username="single_sess_student",
            password="test-pass-123",
            user_type=USER_TYPE_STUDENT,
        )
        cls.admin = User.objects.create_user(
            username="single_sess_admin",
            password="test-pass-123",
            user_type=USER_TYPE_ADMIN,
            is_staff=True,
        )
        admin_role = Role.objects.filter(slug="admin").first()
        if admin_role:
            cls.admin.roles.set([admin_role])

    def _login(self, client: Client, username: str, password: str = "test-pass-123"):
        return client.post(
            "/api/v1/auth/login/",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )

    def _me(self, client: Client):
        return client.get("/api/v1/auth/me/", **MOBILE_API_HEADERS)

    def test_second_login_invalidates_first_student_session(self):
        client_a = Client()
        client_b = Client()

        response_a = self._login(client_a, "single_sess_student")
        self.assertEqual(response_a.status_code, 200, response_a.content)
        key_a = client_a.session.session_key
        self.assertTrue(key_a)
        self.student.refresh_from_db()
        self.assertEqual(self.student.active_session_key, key_a)

        me_a = self._me(client_a)
        self.assertEqual(me_a.status_code, 200)
        self.assertTrue(me_a.json().get("authenticated"))

        response_b = self._login(client_b, "single_sess_student")
        self.assertEqual(response_b.status_code, 200, response_b.content)
        key_b = client_b.session.session_key
        self.assertTrue(key_b)
        self.assertNotEqual(key_a, key_b)
        self.assertFalse(Session.objects.filter(session_key=key_a).exists())

        me_a_after = self._me(client_a)
        self.assertEqual(me_a_after.status_code, 401)
        body = me_a_after.json()
        self.assertFalse(body.get("authenticated", True))

        me_b = self._me(client_b)
        self.assertEqual(me_b.status_code, 200)
        self.assertTrue(me_b.json().get("authenticated"))

    def test_admin_can_keep_multiple_sessions(self):
        client_a = Client()
        client_b = Client()

        self.assertEqual(self._login(client_a, "single_sess_admin").status_code, 200)
        key_a = client_a.session.session_key
        self.assertEqual(self._login(client_b, "single_sess_admin").status_code, 200)
        key_b = client_b.session.session_key
        self.assertNotEqual(key_a, key_b)
        self.assertTrue(Session.objects.filter(session_key=key_a).exists())
        self.assertTrue(Session.objects.filter(session_key=key_b).exists())

        self.assertEqual(self._me(client_a).status_code, 200)
        self.assertEqual(self._me(client_b).status_code, 200)
