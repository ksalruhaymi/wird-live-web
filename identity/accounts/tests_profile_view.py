from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()
PROFILE_URL = reverse("accounts:profile")


class ProfileViewTests(TestCase):
    def setUp(self):
        self.client = Client(HTTP_HOST="localhost")
        self.user = User.objects.create_user(
            username="profile_user",
            email="profile@example.com",
            password="pass12345",
            full_name="اسم أولي",
            job_title="مشرف",
        )
        self.other_user = User.objects.create_user(
            username="profile_other",
            email="other@example.com",
            password="pass12345",
        )
        self.client.force_login(self.user)

    def test_get_profile_without_form_data(self):
        response = self.client.get(PROFILE_URL)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("form_data", response.context)

    def test_post_update_full_name_only(self):
        response = self.client.post(
            PROFILE_URL,
            {
                "full_name": "اسم محدّث",
                "mobile": "",
                "job_title": "مشرف",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.full_name, "اسم محدّث")
        self.assertIsNone(self.user.mobile)

    def test_post_update_job_title_only(self):
        response = self.client.post(
            PROFILE_URL,
            {
                "full_name": "اسم أولي",
                "mobile": "",
                "job_title": "مدير جديد",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.job_title, "مدير جديد")
        self.assertIsNone(self.user.mobile)

    def test_post_empty_mobile_stores_none_not_blank(self):
        response = self.client.post(
            PROFILE_URL,
            {
                "full_name": "اسم أولي",
                "mobile": "",
                "job_title": "مشرف",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.mobile)

        response = self.client.post(
            PROFILE_URL,
            {
                "full_name": "اسم آخر",
                "mobile": "",
                "job_title": "مشرف",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.other_user.refresh_from_db()
        self.assertIsNone(self.other_user.mobile)

    def test_post_valid_mobile(self):
        response = self.client.post(
            PROFILE_URL,
            {
                "full_name": "اسم أولي",
                "mobile": "0512345678",
                "job_title": "مشرف",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.mobile, "+966512345678")

    def test_post_invalid_mobile_returns_error_without_500(self):
        response = self.client.post(
            PROFILE_URL,
            {
                "full_name": "اسم أولي",
                "mobile": "123",
                "job_title": "مشرف",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("form_data", response.context)
        self.assertContains(response, "رقم الهاتف")
