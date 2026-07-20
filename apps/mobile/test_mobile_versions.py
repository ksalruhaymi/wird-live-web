from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.mobile.models import BlockedMobileAppVersion, MobileAppVersion, MobilePlatform, UpdateMode
from apps.mobile.version_services import (
    activate_mobile_app_version,
    compare_semantic_versions,
    deactivate_mobile_app_version,
    evaluate_app_version_check,
)
from identity.accounts.user_types import USER_TYPE_ADMIN, USER_TYPE_STUDENT
from identity.rbac.models import Role

User = get_user_model()

CHECK_URL = "/api/v1/mobile/app-version/check/"

MOBILE_API_HEADERS = {
    "HTTP_X_APP_VERSION": "99.0.0",
    "HTTP_X_APP_BUILD": "99999",
    "HTTP_X_APP_PLATFORM": "android",
}


def _make_student(username: str):
    return User.objects.create_user(
        username=username,
        password="pass12345",
        user_type=USER_TYPE_STUDENT,
        full_name=f"Student {username}",
    )


def _make_admin(username: str):
    return User.objects.create_user(
        username=username,
        password="pass12345",
        user_type=USER_TYPE_ADMIN,
        full_name=f"Admin {username}",
    )


def _make_version(**overrides):
    defaults = dict(
        platform=MobilePlatform.ANDROID,
        version_name="1.2.0",
        build_number=10,
        update_mode=UpdateMode.NONE,
    )
    defaults.update(overrides)
    return MobileAppVersion.objects.create(**defaults)


@override_settings(AXES_ENABLED=False)
class MobileAppVersionModelTests(TestCase):
    def test_create_android_version(self):
        version = _make_version(platform=MobilePlatform.ANDROID, version_name="2.0.0", build_number=20)
        self.assertEqual(version.platform, MobilePlatform.ANDROID)
        self.assertEqual(version.version_name, "2.0.0")
        self.assertEqual(version.build_number, 20)

    def test_create_ios_version(self):
        version = _make_version(platform=MobilePlatform.IOS, version_name="3.1.0", build_number=31)
        self.assertEqual(version.platform, MobilePlatform.IOS)
        self.assertEqual(version.build_number, 31)

    def test_invalid_build_number_rejected(self):
        with self.assertRaises(ValidationError):
            _make_version(build_number=0)

    def test_minimum_build_greater_than_build_rejected(self):
        with self.assertRaises(ValidationError):
            _make_version(build_number=10, minimum_build_number=11)

    def test_allow_later_with_required_mode_rejected(self):
        # save() normalizes allow_later/later_reminder_hours before validating,
        # so exercise Model.clean() directly to assert the raw validation rule.
        version = MobileAppVersion(
            platform=MobilePlatform.ANDROID,
            version_name="1.0.0",
            build_number=1,
            update_mode=UpdateMode.REQUIRED,
            allow_later=True,
        )
        with self.assertRaises(ValidationError):
            version.full_clean()

    def test_required_mode_forces_allow_later_false_on_valid_save(self):
        version = MobileAppVersion(
            platform=MobilePlatform.ANDROID,
            version_name="1.0.0",
            build_number=1,
            update_mode=UpdateMode.REQUIRED,
            allow_later=False,
            later_reminder_hours=None,
        )
        version.save()
        self.assertFalse(version.allow_later)
        self.assertIsNone(version.later_reminder_hours)

    def test_activate_deactivates_previous_for_same_platform(self):
        old = _make_version(version_name="1.0.0", build_number=1)
        activate_mobile_app_version(old)
        new = _make_version(version_name="1.1.0", build_number=2)

        activate_mobile_app_version(new)

        old.refresh_from_db()
        new.refresh_from_db()
        self.assertFalse(old.is_active)
        self.assertIsNotNone(old.deactivated_at)
        self.assertTrue(new.is_active)
        self.assertIsNotNone(new.activated_at)

    def test_activate_does_not_affect_other_platform(self):
        android = _make_version(platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=1)
        ios = _make_version(platform=MobilePlatform.IOS, version_name="1.0.0", build_number=1)
        activate_mobile_app_version(android)
        activate_mobile_app_version(ios)

        android.refresh_from_db()
        ios.refresh_from_db()
        self.assertTrue(android.is_active)
        self.assertTrue(ios.is_active)

    def test_compare_semantic_versions(self):
        self.assertGreater(compare_semantic_versions("1.10.0", "1.9.0"), 0)
        self.assertLess(compare_semantic_versions("1.9.0", "1.10.0"), 0)
        self.assertEqual(compare_semantic_versions("1.2.3", "1.2.3"), 0)


@override_settings(AXES_ENABLED=False)
class EvaluateAppVersionCheckTests(TestCase):
    def test_no_update_when_no_active_version(self):
        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=1
        )
        self.assertEqual(result["action"], "no_update")
        self.assertFalse(result["update_available"])

    def test_no_update_when_starts_at_in_future(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            update_mode=UpdateMode.OPTIONAL,
            starts_at=timezone.now() + timezone.timedelta(days=1),
        )
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=1
        )
        self.assertEqual(result["action"], "no_update")

    def test_no_update_when_build_equal_or_newer(self):
        active = _make_version(version_name="2.0.0", build_number=20, update_mode=UpdateMode.REQUIRED)
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="2.0.0", build_number=20
        )
        self.assertEqual(result["action"], "no_update")

        result_newer = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="2.1.0", build_number=21
        )
        self.assertEqual(result_newer["action"], "no_update")

    def test_optional_update(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            update_mode=UpdateMode.OPTIONAL,
            allow_later=True,
            later_reminder_hours=12,
        )
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=1
        )
        self.assertEqual(result["action"], "optional_update")
        self.assertTrue(result["update_available"])
        self.assertFalse(result["update_required"])
        self.assertTrue(result["allow_later"])
        self.assertEqual(result["later_reminder_hours"], 12)

    def test_required_update(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            update_mode=UpdateMode.REQUIRED,
        )
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=1
        )
        self.assertEqual(result["action"], "required_update")
        self.assertTrue(result["update_required"])
        self.assertFalse(result["allow_later"])

    def test_required_via_minimum_build_even_if_optional_mode(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            update_mode=UpdateMode.OPTIONAL,
            minimum_build_number=15,
            allow_later=True,
        )
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=10
        )
        self.assertEqual(result["action"], "required_update")
        self.assertTrue(result["update_required"])

    def test_blocked_version(self):
        active = _make_version(
            version_name="2.0.0", build_number=20, update_mode=UpdateMode.OPTIONAL
        )
        activate_mobile_app_version(active)
        BlockedMobileAppVersion.objects.create(
            platform=MobilePlatform.ANDROID,
            build_number=5,
            reason_ar="إصدار قديم به مشاكل أمنية",
        )

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="0.9.0", build_number=5
        )
        self.assertEqual(result["action"], "blocked_version")
        self.assertTrue(result["blocked"])
        self.assertTrue(result["update_required"])

    def test_arabic_locale_text(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            update_mode=UpdateMode.REQUIRED,
        )
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID,
            version_name="1.0.0",
            build_number=1,
            locale="ar",
        )
        self.assertEqual(result["title"], "يجب تحديث التطبيق")

    def test_english_locale_text(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            update_mode=UpdateMode.REQUIRED,
        )
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID,
            version_name="1.0.0",
            build_number=1,
            locale="en",
        )
        self.assertEqual(result["title"], "Update Required")

    def test_locale_fallback_to_arabic_when_english_missing(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            update_mode=UpdateMode.OPTIONAL,
            allow_later=True,
            update_title_ar="عنوان مخصص",
            update_title_en="",
        )
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID,
            version_name="1.0.0",
            build_number=1,
            locale="en",
        )
        self.assertEqual(result["title"], "عنوان مخصص")


@override_settings(AXES_ENABLED=False)
class MobileAppVersionCheckApiTests(TestCase):
    def test_invalid_platform_returns_400(self):
        response = self.client.get(
            CHECK_URL,
            {"platform": "windows", "version_name": "1.0.0", "build_number": "1"},
        )
        self.assertEqual(response.status_code, 400)

    def test_invalid_build_number_returns_400(self):
        response = self.client.get(
            CHECK_URL,
            {"platform": "android", "version_name": "1.0.0", "build_number": "abc"},
        )
        self.assertEqual(response.status_code, 400)

    def test_check_endpoint_is_public_without_login(self):
        response = self.client.get(
            CHECK_URL,
            {"platform": "android", "version_name": "1.0.0", "build_number": "1"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])

    def test_response_has_no_created_by_field(self):
        active = _make_version(version_name="2.0.0", build_number=20, update_mode=UpdateMode.OPTIONAL)
        activate_mobile_app_version(active)

        response = self.client.get(
            CHECK_URL,
            {"platform": "android", "version_name": "1.0.0", "build_number": "1"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("created_by", body)


@override_settings(AXES_ENABLED=False)
class MobileVersionDashboardPermissionTests(TestCase):
    def setUp(self):
        call_command("seed_rbac")
        self.student = _make_student("mv_student")
        self.admin = _make_admin("mv_admin")
        call_command("seed_rbac")
        self.admin.roles.set([Role.objects.get(slug="admin")])

    def test_student_cannot_access_list(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("dashboard:mobile_version_list"))
        self.assertEqual(response.status_code, 403)

    def test_admin_with_permission_can_access(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:mobile_version_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نسخ التطبيقات")
        self.assertContains(response, "إضافة Android")
        self.assertContains(response, "إضافة iOS")
