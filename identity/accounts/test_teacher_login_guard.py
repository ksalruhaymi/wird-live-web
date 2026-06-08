from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.tutoring.models import TeacherProfile
from apps.tutoring.teacher_approval_service import reject_teacher_profile
from identity.accounts.auth.login_service import login_user
from identity.accounts.auth.teacher_login_guard import (
    REJECTED_TEACHER_LOGIN_MESSAGE,
    teacher_login_block_message,
)
from identity.accounts.user_types import USER_TYPE_TEACHER

User = get_user_model()


class TeacherLoginGuardTests(TestCase):
    def setUp(self):
        self.reviewer = User.objects.create_user(
            username="reviewer",
            email="reviewer@example.com",
            password="pass12345",
        )
        self.teacher_user = User.objects.create_user(
            username="teacher1",
            email="teacher1@example.com",
            password="pass12345",
            user_type=USER_TYPE_TEACHER,
        )
        self.profile = TeacherProfile.objects.create(
            user=self.teacher_user,
            display_name="Teacher One",
        )

    def test_reject_deactivates_teacher_and_blocks_login(self):
        reject_teacher_profile(self.profile, self.reviewer, "سبب الرفض")

        self.teacher_user.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertEqual(
            self.profile.approval_status,
            TeacherProfile.ApprovalStatus.REJECTED,
        )
        self.assertFalse(self.teacher_user.is_active)
        self.assertEqual(
            teacher_login_block_message(self.teacher_user),
            REJECTED_TEACHER_LOGIN_MESSAGE,
        )

        request = RequestFactory().post("/api/v1/auth/login/")
        result = login_user(request, "teacher1@example.com", "pass12345")
        self.assertEqual(result, "rejected")
