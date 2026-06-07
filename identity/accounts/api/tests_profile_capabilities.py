from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from identity.accounts.auth.profile_service import build_profile_payload
from identity.accounts.user_types import (
    USER_TYPE_ADMIN,
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
)
from identity.rbac.mobile_capabilities import (
    MOBILE_CAPABILITY_PERMISSIONS,
    build_mobile_capabilities,
)
from identity.rbac.models import Role

User = get_user_model()

ME_URL = reverse("accounts_auth_api:me")
PROFILE_URL = reverse("accounts_auth_api:profile")

LEGACY_PROFILE_KEYS = {
    "id",
    "username",
    "full_name",
    "display_name",
    "gender",
    "gender_label",
    "mobile",
    "email",
    "riwayat",
    "profile_image_url",
    "user_type",
    "teacher_files",
    "management",
}

LEGACY_MANAGEMENT_KEYS = {
    "can_view_pending_teachers",
    "can_approve_teachers",
    "can_reject_teachers",
}

LEGACY_USER_KEYS = {"id", "username", "email", "display_name", "user_type"}

MOBILE_API_HEADERS = {
    "HTTP_X_APP_VERSION": "99.0.0",
    "HTTP_X_APP_BUILD": "99999",
    "HTTP_X_APP_PLATFORM": "android",
}


def _expected_structure() -> dict[str, set[str]]:
    return {
        group: set(keys.keys()) for group, keys in MOBILE_CAPABILITY_PERMISSIONS.items()
    }


def _all_capability_paths() -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    for group, keys in MOBILE_CAPABILITY_PERMISSIONS.items():
        for key in keys:
            paths.append((group, key))
    return paths


class ProfileCapabilitiesTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.role_admin = Role.objects.get(slug="admin")
        cls.role_supervisor = Role.objects.get(slug="supervisor")
        cls.role_teacher = Role.objects.get(slug="teacher")
        cls.role_student = Role.objects.get(slug="student")

        cls.admin_user = User.objects.create_user(
            username="cap_test_admin",
            password="test-pass",
            user_type=USER_TYPE_ADMIN,
        )
        cls.admin_user.roles.set([cls.role_admin])

        cls.supervisor_user = User.objects.create_user(
            username="cap_test_supervisor",
            password="test-pass",
            user_type=USER_TYPE_SUPERVISOR,
        )
        cls.supervisor_user.roles.set([cls.role_supervisor])

        cls.teacher_user = User.objects.create_user(
            username="cap_test_teacher",
            password="test-pass",
            user_type=USER_TYPE_TEACHER,
        )
        cls.teacher_user.roles.set([cls.role_teacher])

        cls.student_user = User.objects.create_user(
            username="cap_test_student",
            password="test-pass",
            user_type=USER_TYPE_STUDENT,
        )
        cls.student_user.roles.set([cls.role_student])

        cls.no_role_user = User.objects.create_user(
            username="cap_test_no_role",
            password="test-pass",
            user_type=USER_TYPE_STUDENT,
        )

        cls.superuser = User.objects.create_superuser(
            username="cap_test_superuser",
            password="test-pass",
            email="cap_super@test.local",
        )

    def _assert_capabilities_structure(self, capabilities: dict):
        self.assertEqual(set(capabilities.keys()), set(_expected_structure().keys()))
        for group, expected_keys in _expected_structure().items():
            self.assertEqual(set(capabilities[group].keys()), expected_keys)
            for value in capabilities[group].values():
                self.assertIsInstance(value, bool)

    def _assert_all_capabilities(self, capabilities: dict, expected: bool):
        for group, key in _all_capability_paths():
            self.assertEqual(
                capabilities[group][key],
                expected,
                msg=f"{group}.{key}",
            )

    def _api_get(self, url: str, *, user=None):
        if user is not None:
            self.client.force_login(user)
        return self.client.get(url, **MOBILE_API_HEADERS)


class BuildMobileCapabilitiesTests(ProfileCapabilitiesTestBase):
    def test_structure_is_identical_for_all_roles(self):
        users = [
            self.admin_user,
            self.supervisor_user,
            self.teacher_user,
            self.student_user,
            self.no_role_user,
            self.superuser,
        ]
        structures = []
        for user in users:
            capabilities = build_mobile_capabilities(user)
            self._assert_capabilities_structure(capabilities)
            structures.append(
                tuple(
                    (group, tuple(sorted(keys.keys())))
                    for group, keys in sorted(MOBILE_CAPABILITY_PERMISSIONS.items())
                )
            )
        self.assertEqual(len(set(structures)), 1)

    def test_admin_capabilities(self):
        capabilities = build_mobile_capabilities(self.admin_user)
        self._assert_all_capabilities(capabilities, True)

    def test_supervisor_capabilities(self):
        capabilities = build_mobile_capabilities(self.supervisor_user)
        self.assertTrue(capabilities["nav"]["home"])
        self.assertTrue(capabilities["nav"]["teachers"])
        self.assertTrue(capabilities["nav"]["recordings"])
        self.assertTrue(capabilities["nav"]["management"])
        self.assertTrue(capabilities["nav"]["settings"])
        self.assertFalse(capabilities["nav"]["subscriptions"])
        self.assertTrue(capabilities["management"]["view_pending_teachers"])
        self.assertTrue(capabilities["management"]["approve_teachers"])
        self.assertTrue(capabilities["management"]["reject_teachers"])
        self.assertTrue(capabilities["management"]["interview_call"])
        self.assertTrue(capabilities["recordings"]["play_all"])
        self.assertFalse(capabilities["recordings"]["play_own"])
        self.assertFalse(capabilities["recordings"]["list_own"])
        self.assertFalse(capabilities["teacher"]["home"])
        self.assertFalse(capabilities["calls"]["request"])
        self.assertTrue(capabilities["profile"]["view"])
        self.assertFalse(capabilities["profile"]["update"])

    def test_teacher_capabilities(self):
        capabilities = build_mobile_capabilities(self.teacher_user)
        self.assertTrue(capabilities["nav"]["home"])
        self.assertTrue(capabilities["nav"]["recordings"])
        self.assertTrue(capabilities["nav"]["settings"])
        self.assertFalse(capabilities["nav"]["teachers"])
        self.assertFalse(capabilities["nav"]["management"])
        self.assertFalse(capabilities["nav"]["subscriptions"])
        self.assertTrue(capabilities["teacher"]["home"])
        self.assertTrue(capabilities["teacher"]["availability_update"])
        self.assertTrue(capabilities["teacher"]["heartbeat"])
        self.assertTrue(capabilities["calls"]["incoming"])
        self.assertTrue(capabilities["calls"]["accept"])
        self.assertTrue(capabilities["calls"]["reject"])
        self.assertFalse(capabilities["calls"]["request"])
        self.assertTrue(capabilities["recordings"]["list_own"])
        self.assertTrue(capabilities["recordings"]["play_own"])
        self.assertTrue(capabilities["recordings"]["download_own"])
        self.assertFalse(capabilities["recordings"]["play_all"])
        self.assertFalse(capabilities["recordings"]["download_all"])
        self.assertFalse(capabilities["management"]["view_pending_teachers"])
        self.assertTrue(capabilities["profile"]["view"])
        self.assertTrue(capabilities["profile"]["update"])
        self.assertTrue(capabilities["profile"]["avatar_update"])

    def test_student_capabilities(self):
        capabilities = build_mobile_capabilities(self.student_user)
        self.assertTrue(capabilities["nav"]["home"])
        self.assertTrue(capabilities["nav"]["teachers"])
        self.assertTrue(capabilities["nav"]["recordings"])
        self.assertTrue(capabilities["nav"]["settings"])
        self.assertTrue(capabilities["nav"]["subscriptions"])
        self.assertFalse(capabilities["nav"]["management"])
        self.assertTrue(capabilities["teachers"]["list"])
        self.assertTrue(capabilities["teachers"]["profile"])
        self.assertTrue(capabilities["teachers"]["favorite_toggle"])
        self.assertTrue(capabilities["subscriptions"]["packages"])
        self.assertTrue(capabilities["subscriptions"]["status"])
        self.assertTrue(capabilities["subscriptions"]["checkout"])
        self.assertTrue(capabilities["calls"]["request"])
        self.assertFalse(capabilities["calls"]["incoming"])
        self.assertTrue(capabilities["recordings"]["play_own"])
        self.assertTrue(capabilities["recordings"]["download_own"])
        self.assertFalse(capabilities["recordings"]["play_all"])
        # Alias: play_own ↔ list_own.view — student has play_own permission.
        self.assertTrue(capabilities["recordings"]["list_own"])
        self.assertFalse(capabilities["teacher"]["home"])
        self.assertFalse(capabilities["management"]["view_pending_teachers"])

    def test_user_without_roles_denied(self):
        capabilities = build_mobile_capabilities(self.no_role_user)
        self._assert_all_capabilities(capabilities, False)

    def test_superuser_all_capabilities_true(self):
        capabilities = build_mobile_capabilities(self.superuser)
        self._assert_all_capabilities(capabilities, True)


class ProfilePayloadTests(ProfileCapabilitiesTestBase):
    def test_build_profile_payload_includes_mobile_capabilities(self):
        profile = build_profile_payload(self.supervisor_user)
        self.assertIn("mobile_capabilities", profile)
        self._assert_capabilities_structure(profile["mobile_capabilities"])

    def test_legacy_management_unchanged(self):
        profile = build_profile_payload(self.supervisor_user)
        self.assertEqual(set(profile["management"].keys()), LEGACY_MANAGEMENT_KEYS)
        self.assertTrue(profile["management"]["can_view_pending_teachers"])
        self.assertTrue(profile["management"]["can_approve_teachers"])
        self.assertTrue(profile["management"]["can_reject_teachers"])

    def test_management_matches_mobile_capabilities_for_supervisor(self):
        profile = build_profile_payload(self.supervisor_user)
        management = profile["management"]
        mobile_mgmt = profile["mobile_capabilities"]["management"]
        self.assertEqual(
            management["can_view_pending_teachers"],
            mobile_mgmt["view_pending_teachers"],
        )
        self.assertEqual(
            management["can_approve_teachers"],
            mobile_mgmt["approve_teachers"],
        )
        self.assertEqual(
            management["can_reject_teachers"],
            mobile_mgmt["reject_teachers"],
        )

    def test_legacy_profile_fields_preserved(self):
        profile = build_profile_payload(self.student_user)
        for key in LEGACY_PROFILE_KEYS:
            self.assertIn(key, profile)
        self.assertIsInstance(profile["teacher_files"], list)
        self.assertIsInstance(profile["management"], dict)


class AuthMeApiTests(ProfileCapabilitiesTestBase):
    def test_me_includes_mobile_capabilities_in_profile(self):
        response = self._api_get(ME_URL, user=self.teacher_user)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["authenticated"])
        self.assertIn("profile", body)
        self.assertIn("mobile_capabilities", body["profile"])
        self._assert_capabilities_structure(body["profile"]["mobile_capabilities"])

    def test_me_user_object_unchanged(self):
        response = self._api_get(ME_URL, user=self.supervisor_user)
        body = response.json()
        self.assertEqual(set(body["user"].keys()), LEGACY_USER_KEYS)
        self.assertNotIn("mobile_capabilities", body["user"])

    def test_me_profile_matches_build_profile_payload(self):
        response = self._api_get(ME_URL, user=self.student_user)
        expected = build_profile_payload(self.student_user, response.wsgi_request)
        self.assertEqual(response.json()["profile"], expected)

    def test_me_unauthenticated_still_401(self):
        response = self.client.get(ME_URL, **MOBILE_API_HEADERS)
        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertFalse(body["authenticated"])


class AuthProfileApiTests(ProfileCapabilitiesTestBase):
    def test_profile_includes_mobile_capabilities(self):
        response = self._api_get(PROFILE_URL, user=self.admin_user)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertIn("mobile_capabilities", body["profile"])
        self._assert_all_capabilities(body["profile"]["mobile_capabilities"], True)

    def test_profile_matches_build_profile_payload(self):
        response = self._api_get(PROFILE_URL, user=self.no_role_user)
        expected = build_profile_payload(self.no_role_user, response.wsgi_request)
        self.assertEqual(response.json()["profile"], expected)

    def test_profile_legacy_fields_preserved(self):
        response = self._api_get(PROFILE_URL, user=self.supervisor_user)
        profile = response.json()["profile"]
        for key in LEGACY_PROFILE_KEYS:
            self.assertIn(key, profile)
        self.assertEqual(set(profile["management"].keys()), LEGACY_MANAGEMENT_KEYS)

    def test_profile_unauthenticated_still_401(self):
        response = self.client.get(PROFILE_URL, **MOBILE_API_HEADERS)
        self.assertEqual(response.status_code, 401)
