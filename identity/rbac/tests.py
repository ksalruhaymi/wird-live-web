from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.tutoring.models import StudentProfile, TeacherProfile
from identity.accounts.user_role_sync import (
    apply_user_roles,
    student_users_queryset,
    supervisor_users_queryset,
    teacher_users_queryset,
)
from identity.accounts.user_types import (
    USER_TYPE_ADMIN,
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
    primary_user_type_label,
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
        self.assertTrue(user.has_permission("appointments.view_all"))
        self.assertTrue(user.has_permission("web.appointments.view_all"))

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
        self.assertTrue(user.has_permission("appointments.view_all"))
        self.assertTrue(user.has_permission("web.appointments.view_all"))
        self.assertFalse(user.has_permission("appointments.manage_schedule"))
        self.assertFalse(user.has_permission("appointments.manage_bookings"))
        self.assertFalse(user.has_permission("appointments.override_status"))
        self.assertTrue(user.has_permission("mobile.teachers.list.view"))
        self.assertTrue(user.has_permission("mobile.calls.request"))
        self.assertTrue(user.has_permission("mobile.management.teachers.interview_call"))
        self.assertTrue(user.has_permission("mobile.nav.subscriptions.view"))
        self.assertTrue(user.has_permission("mobile.subscriptions.packages.view"))
        self.assertTrue(user.has_permission("mobile.subscriptions.checkout.create"))

    def test_teacher_permissions(self):
        user = self.teacher_user
        # Teachers manage appointments from mobile only — no dashboard access.
        self.assertFalse(user.has_permission("dashboard.access"))
        self.assertFalse(user.has_permission("web.dashboard.access"))
        self.assertFalse(user.has_permission("appointments.view"))
        self.assertFalse(user.has_permission("appointments.view_all"))
        self.assertFalse(user.has_permission("appointments.manage_schedule"))
        self.assertFalse(user.has_permission("appointments.manage_bookings"))
        self.assertTrue(user.has_permission("mobile.nav.appointments.view"))
        self.assertTrue(user.has_permission("mobile.teacher.home.view"))
        self.assertTrue(user.has_permission("shared.profile.update"))
        self.assertFalse(user.has_permission("management.teachers.view"))
        self.assertFalse(user.has_permission("recordings.view"))
        self.assertFalse(user.has_permission("shared.recordings.play_all"))
        self.assertFalse(user.has_permission("users.view"))
        self.assertFalse(user.has_permission("calls.view"))

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


class UserRoleSyncTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.role_student = Role.objects.get(slug="student")
        cls.role_teacher = Role.objects.get(slug="teacher")
        cls.role_supervisor = Role.objects.get(slug="supervisor")

    def _create_user(self, username: str, *, user_type=USER_TYPE_SUPERVISOR):
        return User.objects.create_user(
            username=username,
            password="test-pass",
            email=f"{username}@test.local",
            user_type=user_type,
        )

    def test_student_only_sets_type_and_profile(self):
        user = self._create_user("sync_student_only")
        ok, err = apply_user_roles(user, [self.role_student])
        self.assertTrue(ok, err)
        user.refresh_from_db()
        self.assertEqual(user.user_type, USER_TYPE_STUDENT)
        self.assertTrue(StudentProfile.objects.filter(user=user).exists())
        self.assertEqual(primary_user_type_label(user), "طالب")

    def test_student_plus_supervisor_keeps_student_type(self):
        user = self._create_user("sync_student_supervisor")
        ok, err = apply_user_roles(
            user, [self.role_student, self.role_supervisor]
        )
        self.assertTrue(ok, err)
        user.refresh_from_db()
        self.assertEqual(user.user_type, USER_TYPE_STUDENT)
        self.assertEqual(primary_user_type_label(user), "طالب")
        slugs = set(user.roles.values_list("slug", flat=True))
        self.assertEqual(slugs, {"student", "supervisor"})

    def test_teacher_plus_supervisor_keeps_teacher_type(self):
        user = self._create_user("sync_teacher_supervisor")
        ok, err = apply_user_roles(
            user, [self.role_teacher, self.role_supervisor]
        )
        self.assertTrue(ok, err)
        user.refresh_from_db()
        self.assertEqual(user.user_type, USER_TYPE_TEACHER)
        self.assertTrue(TeacherProfile.objects.filter(user=user).exists())
        self.assertEqual(primary_user_type_label(user), "معلم")

    def test_supervisor_only_sets_supervisor_type(self):
        user = self._create_user("sync_supervisor_only")
        ok, err = apply_user_roles(user, [self.role_supervisor])
        self.assertTrue(ok, err)
        user.refresh_from_db()
        self.assertEqual(user.user_type, USER_TYPE_SUPERVISOR)
        self.assertEqual(primary_user_type_label(user), "مشرف")

    def test_student_and_teacher_roles_rejected(self):
        user = self._create_user("sync_conflict")
        ok, err = apply_user_roles(
            user, [self.role_student, self.role_teacher]
        )
        self.assertFalse(ok)
        self.assertIsNotNone(err)

    def test_student_converted_to_supervisor_only_keeps_profile_hidden_from_tab(self):
        user = self._create_user("was_student", user_type=USER_TYPE_STUDENT)
        ok, err = apply_user_roles(user, [self.role_student])
        self.assertTrue(ok, err)
        ok, err = apply_user_roles(user, [self.role_supervisor])
        self.assertTrue(ok, err)
        user.refresh_from_db()
        self.assertEqual(user.user_type, USER_TYPE_SUPERVISOR)
        self.assertTrue(StudentProfile.objects.filter(user=user).exists())
        self.assertFalse(student_users_queryset().filter(pk=user.pk).exists())
        self.assertEqual(primary_user_type_label(user), "مشرف")

    def test_teacher_converted_to_supervisor_only_keeps_profile_hidden_from_tab(self):
        user = self._create_user("was_teacher", user_type=USER_TYPE_TEACHER)
        ok, err = apply_user_roles(user, [self.role_teacher])
        self.assertTrue(ok, err)
        ok, err = apply_user_roles(user, [self.role_supervisor])
        self.assertTrue(ok, err)
        user.refresh_from_db()
        self.assertEqual(user.user_type, USER_TYPE_SUPERVISOR)
        self.assertTrue(TeacherProfile.objects.filter(user=user).exists())
        self.assertFalse(teacher_users_queryset().filter(pk=user.pk).exists())
        self.assertEqual(primary_user_type_label(user), "مشرف")

    def test_student_supervisor_still_in_students_tab(self):
        user = self._create_user("student_super_tab")
        ok, err = apply_user_roles(
            user, [self.role_student, self.role_supervisor]
        )
        self.assertTrue(ok, err)
        self.assertTrue(student_users_queryset().filter(pk=user.pk).exists())
        self.assertEqual(primary_user_type_label(user), "طالب")

    def test_supervisor_role_appears_in_supervisors_tab(self):
        user = self._create_user("supervisor_tab_only")
        ok, err = apply_user_roles(user, [self.role_supervisor])
        self.assertTrue(ok, err)
        self.assertTrue(supervisor_users_queryset().filter(pk=user.pk).exists())

    def test_student_supervisor_also_in_supervisors_tab(self):
        user = self._create_user("student_super_both_tabs")
        ok, err = apply_user_roles(
            user, [self.role_student, self.role_supervisor]
        )
        self.assertTrue(ok, err)
        self.assertTrue(supervisor_users_queryset().filter(pk=user.pk).exists())
        self.assertTrue(student_users_queryset().filter(pk=user.pk).exists())
