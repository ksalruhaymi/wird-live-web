from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.calls.exceptions import CallValidationError
from apps.calls.services import create_scheduled_call_session
from apps.tutoring.models import TeacherProfile
from identity.accounts.user_types import USER_TYPE_STUDENT, USER_TYPE_TEACHER

User = get_user_model()


class CreateScheduledCallSessionTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="sched_call_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )
        self.teacher = User.objects.create_user(
            username="sched_call_teacher",
            password="pass12345",
            user_type=USER_TYPE_TEACHER,
        )
        TeacherProfile.objects.create(
            user=self.teacher,
            display_name="Sched Teacher",
            approval_status=TeacherProfile.ApprovalStatus.APPROVED,
            is_approved=True,
            can_audio=True,
            can_video=False,
        )

    def test_invalid_session_type_raises(self):
        with self.assertRaises(CallValidationError):
            create_scheduled_call_session(
                student=self.student,
                teacher=self.teacher,
                session_type="fax",
            )

    def test_video_capability_enforced(self):
        with self.assertRaises(CallValidationError):
            create_scheduled_call_session(
                student=self.student,
                teacher=self.teacher,
                session_type="video",
            )
