from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from identity.accounts.user_types import (
    USER_TYPE_ADMIN,
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Permission, Role
from identity.rbac.resolver import resolve_permission_codes

User = get_user_model()


class ResolvePermissionCodesTests(TestCase):
    def test_known_code_expands_to_group(self):
        codes = resolve_permission_codes("dashboard.access")
        self.assertIn("web.dashboard.access", codes)
        self.assertIn("dashboard.access", codes)

    def test_unknown_code_resolves_to_itself_only(self):
        self.assertEqual(
            resolve_permission_codes("totally.unknown.permission"),
            frozenset({"totally.unknown.permission"}),
        )

    def test_interview_call_has_no_alias(self):
        self.assertEqual(
            resolve_permission_codes("mobile.management.teachers.interview_call"),
            frozenset({"mobile.management.teachers.interview_call"}),
        )


class DualReadPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.role_admin = Role.objects.get(slug="admin")
        cls.role_supervisor = Role.objects.get(slug="supervisor")
        cls.role_teacher = Role.objects.get(slug="teacher")
        cls.role_student = Role.objects.get(slug="student")

        cls.admin_user = User.objects.create_user(
            username="rbac_test_admin",
            password="test-pass",
            user_type=USER_TYPE_ADMIN,
        )
        cls.admin_user.roles.set([cls.role_admin])

        cls.supervisor_user = User.objects.create_user(
            username="rbac_test_supervisor",
            password="test-pass",
            user_type=USER_TYPE_SUPERVISOR,
        )
        cls.supervisor_user.roles.set([cls.role_supervisor])

        cls.teacher_user = User.objects.create_user(
            username="rbac_test_teacher",
            password="test-pass",
            user_type=USER_TYPE_TEACHER,
        )
        cls.teacher_user.roles.set([cls.role_teacher])

        cls.student_user = User.objects.create_user(
            username="rbac_test_student",
            password="test-pass",
            user_type=USER_TYPE_STUDENT,
        )
        cls.student_user.roles.set([cls.role_student])

        cls.no_role_user = User.objects.create_user(
            username="rbac_test_no_role",
            password="test-pass",
            user_type=USER_TYPE_STUDENT,
        )

        cls.superuser = User.objects.create_superuser(
            username="rbac_test_superuser",
            password="test-pass",
            email="super@test.local",
        )

    def test_admin_permissions(self):
        user = self.admin_user
        self.assertTrue(user.has_permission("dashboard.access"))
        self.assertTrue(user.has_permission("web.dashboard.access"))
        self.assertTrue(user.has_permission("web.rbac.access"))
        self.assertTrue(user.has_permission("mobile.nav.management.view"))

    def test_supervisor_permissions(self):
        user = self.supervisor_user
        self.assertTrue(user.has_permission("dashboard.access"))
        self.assertTrue(user.has_permission("web.dashboard.access"))
        self.assertTrue(user.has_permission("subscriptions.view"))
        self.assertTrue(user.has_permission("web.subscriptions.students.view"))
        self.assertFalse(user.has_permission("subscriptions.delete"))
        self.assertFalse(user.has_permission("web.rbac.access"))
        self.assertTrue(user.has_permission("recordings.view"))
        self.assertTrue(user.has_permission("shared.recordings.play_all"))

    def test_teacher_permissions(self):
        user = self.teacher_user
        self.assertFalse(user.has_permission("dashboard.access"))
        self.assertFalse(user.has_permission("web.dashboard.access"))
        self.assertTrue(user.has_permission("mobile.teacher.home.view"))
        self.assertTrue(user.has_permission("shared.profile.update"))
        self.assertFalse(user.has_permission("management.teachers.view"))
        self.assertFalse(user.has_permission("recordings.view"))
        self.assertFalse(user.has_permission("shared.recordings.play_all"))

    def test_student_permissions(self):
        user = self.student_user
        self.assertFalse(user.has_permission("dashboard.access"))
        self.assertFalse(user.has_permission("web.dashboard.access"))
        self.assertTrue(user.has_permission("mobile.calls.request"))
        self.assertTrue(user.has_permission("shared.recordings.play_own"))
        self.assertFalse(user.has_permission("shared.recordings.play_all"))

    def test_user_without_roles_denied(self):
        user = self.no_role_user
        self.assertFalse(user.has_permission("dashboard.access"))
        self.assertFalse(user.has_permission("web.dashboard.access"))
        self.assertFalse(user.has_permission("mobile.calls.request"))

    def test_unknown_permission_checks_literal_code_only(self):
        user = self.admin_user
        self.assertFalse(user.has_permission("totally.unknown.permission"))

    def test_superuser_bypasses_all_checks(self):
        user = self.superuser
        self.assertTrue(user.has_permission("dashboard.access"))
        self.assertTrue(user.has_permission("web.rbac.access"))
        self.assertTrue(user.has_permission("totally.unknown.permission"))

    def test_delete_not_linked_to_non_delete(self):
        supervisor = self.supervisor_user
        self.assertFalse(supervisor.has_permission("web.recordings.delete"))
        self.assertFalse(supervisor.has_permission("shared.recordings.download_all"))

        admin = self.admin_user
        self.assertTrue(admin.has_permission("web.recordings.delete"))
        # Admin has download_all as a separate seeded permission, not via delete alias.
        self.assertTrue(admin.has_permission("shared.recordings.download_all"))

        delete_only_user = User.objects.create_user(
            username="rbac_test_delete_only",
            password="test-pass",
        )
        delete_perm = Permission.objects.get(code="web.recordings.delete")
        delete_role = Role.objects.create(slug="delete_only_test", name="Delete Only Test")
        delete_role.permissions.set([delete_perm])
        delete_only_user.roles.set([delete_role])
        self.assertTrue(delete_only_user.has_permission("web.recordings.delete"))
        self.assertFalse(delete_only_user.has_permission("shared.recordings.download_all"))
        self.assertFalse(delete_only_user.has_permission("recordings.view"))

    def test_play_own_not_linked_to_recordings_view(self):
        teacher = self.teacher_user
        self.assertTrue(teacher.has_permission("shared.recordings.play_own"))
        self.assertFalse(teacher.has_permission("recordings.view"))
