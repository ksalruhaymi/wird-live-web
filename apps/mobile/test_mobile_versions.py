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
        self.assertNotContains(response, "تشغيل التطبيق")


@override_settings(AXES_ENABLED=False)
class PlatformAppEnabledTests(TestCase):
    CONFIG_URL = "/api/v1/mobile/app-config/"

    def setUp(self):
        from apps.mobile.models import MobileAppConfig

        self.config = MobileAppConfig.get_settings()
        self.config.app_enabled = True
        self.config.android_app_enabled = True
        self.config.ios_app_enabled = True
        self.config.min_supported_version = "1.0.0"
        self.config.min_supported_build = 1
        self.config.force_update = False
        self.config.save()

    def test_defaults_are_enabled(self):
        from apps.mobile.models import MobileAppConfig

        row = MobileAppConfig(pk=2)
        self.assertTrue(row.android_app_enabled)
        self.assertTrue(row.ios_app_enabled)

    def test_android_disabled_ios_enabled(self):
        from apps.mobile.app_config_services import (
            app_config_to_payload,
            evaluate_mobile_api_access,
        )

        self.config.android_app_enabled = False
        self.config.ios_app_enabled = True
        self.config.save()

        self.assertFalse(self.config.is_enabled_for_platform("android"))
        self.assertTrue(self.config.is_enabled_for_platform("ios"))

        android_denial = evaluate_mobile_api_access(
            app_version="9.0.0",
            app_build=900,
            platform="android",
            config=self.config,
        )
        self.assertIsNotNone(android_denial)
        self.assertEqual(android_denial["payload"]["code"], "app_disabled")

        ios_ok = evaluate_mobile_api_access(
            app_version="9.0.0",
            app_build=900,
            platform="ios",
            config=self.config,
        )
        self.assertIsNone(ios_ok)

        self.assertFalse(
            app_config_to_payload(self.config, platform="android")["app_enabled"]
        )
        self.assertTrue(
            app_config_to_payload(self.config, platform="ios")["app_enabled"]
        )

    def test_ios_disabled_android_enabled(self):
        from apps.mobile.app_config_services import (
            app_config_to_payload,
            evaluate_mobile_api_access,
        )

        self.config.android_app_enabled = True
        self.config.ios_app_enabled = False
        self.config.save()

        self.assertTrue(self.config.is_enabled_for_platform("android"))
        self.assertFalse(self.config.is_enabled_for_platform("ios"))

        android_ok = evaluate_mobile_api_access(
            app_version="9.0.0",
            app_build=900,
            platform="android",
            config=self.config,
        )
        self.assertIsNone(android_ok)

        ios_denial = evaluate_mobile_api_access(
            app_version="9.0.0",
            app_build=900,
            platform="ios",
            config=self.config,
        )
        self.assertIsNotNone(ios_denial)
        self.assertEqual(ios_denial["payload"]["code"], "app_disabled")

        self.assertTrue(
            app_config_to_payload(self.config, platform="android")["app_enabled"]
        )
        self.assertFalse(
            app_config_to_payload(self.config, platform="ios")["app_enabled"]
        )

    def test_api_returns_platform_specific_enabled_state(self):
        self.config.android_app_enabled = False
        self.config.ios_app_enabled = True
        self.config.save()

        android_response = self.client.get(
            self.CONFIG_URL,
            {"platform": "android"},
        )
        self.assertEqual(android_response.status_code, 200)
        self.assertFalse(android_response.json()["app_enabled"])

        ios_response = self.client.get(
            self.CONFIG_URL,
            HTTP_X_APP_PLATFORM="ios",
        )
        self.assertEqual(ios_response.status_code, 200)
        self.assertTrue(ios_response.json()["app_enabled"])

    def test_legacy_app_enabled_is_not_decision_source(self):
        from apps.mobile.app_config_services import evaluate_mobile_api_access

        self.config.app_enabled = False
        self.config.android_app_enabled = True
        self.config.ios_app_enabled = True
        self.config.save()

        self.assertIsNone(
            evaluate_mobile_api_access(
                app_version="9.0.0",
                app_build=900,
                platform="android",
                config=self.config,
            )
        )

    def test_force_update_and_blocked_unaffected_by_platform_toggle(self):
        self.config.android_app_enabled = False
        self.config.ios_app_enabled = True
        self.config.save()

        active = _make_version(
            platform=MobilePlatform.ANDROID,
            version_name="2.0.0",
            build_number=20,
            minimum_build_number=15,
            update_mode=UpdateMode.REQUIRED,
            store_url="https://example.com/android",
        )
        activate_mobile_app_version(active)
        BlockedMobileAppVersion.objects.create(
            platform=MobilePlatform.ANDROID,
            build_number=5,
            reason_ar="محظور",
            is_active=True,
        )

        blocked = evaluate_app_version_check(
            platform="android",
            version_name="1.0.0",
            build_number=5,
            locale="ar",
        )
        self.assertEqual(blocked["action"], "blocked_version")

        required = evaluate_app_version_check(
            platform="android",
            version_name="1.0.0",
            build_number=10,
            locale="ar",
        )
        self.assertEqual(required["action"], "required_update")

        ios_active = _make_version(
            platform=MobilePlatform.IOS,
            version_name="2.0.0",
            build_number=20,
            update_mode=UpdateMode.NONE,
        )
        activate_mobile_app_version(ios_active)
        ios_ok = evaluate_app_version_check(
            platform="ios",
            version_name="2.0.0",
            build_number=20,
            locale="ar",
        )
        self.assertEqual(ios_ok["action"], "no_update")


@override_settings(AXES_ENABLED=False)
class PlatformAppEnabledMigrationTests(TestCase):
    def test_data_migration_preserves_old_value(self):
        import importlib

        from django.apps import apps as django_apps

        from apps.mobile.models import MobileAppConfig

        migration = importlib.import_module(
            "apps.mobile.migrations.0003_platform_app_enabled"
        )

        config = MobileAppConfig.get_settings()
        config.app_enabled = False
        config.android_app_enabled = True
        config.ios_app_enabled = True
        config.save()

        migration.copy_legacy_app_enabled(django_apps, None)

        config.refresh_from_db()
        self.assertFalse(config.android_app_enabled)
        self.assertFalse(config.ios_app_enabled)
        self.assertFalse(config.app_enabled)
