from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.mobile.app_config_services import (
    app_config_to_payload,
    evaluate_mobile_api_access,
)
from apps.mobile.models import MobileAppConfig, MobileAppVersion, MobilePlatform, UpdateMode
from apps.mobile.version_services import (
    activate_mobile_app_version,
    compare_semantic_versions,
    evaluate_app_version_check,
)
from identity.accounts.user_types import USER_TYPE_ADMIN, USER_TYPE_STUDENT
from identity.rbac.models import Role

User = get_user_model()

CHECK_URL = "/api/v1/mobile/app-version/check/"
CONFIG_URL = "/api/v1/mobile/app-config/"


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

    def test_one_active_version_per_platform(self):
        first = _make_version(platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=1)
        second = _make_version(platform=MobilePlatform.ANDROID, version_name="2.0.0", build_number=2)
        activate_mobile_app_version(first)
        activate_mobile_app_version(second)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_active)
        self.assertTrue(second.is_active)
        self.assertEqual(
            MobileAppVersion.objects.filter(
                platform=MobilePlatform.ANDROID, is_active=True
            ).count(),
            1,
        )

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

    def test_no_update_when_build_equal_or_newer(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            minimum_build_number=15,
            update_mode=UpdateMode.REQUIRED,
        )
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="2.0.0", build_number=20
        )
        self.assertEqual(result["action"], "no_update")

        result_newer = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="2.1.0", build_number=21
        )
        self.assertEqual(result_newer["action"], "no_update")

    def test_optional_update_does_not_block_entry(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            minimum_build_number=15,
            update_mode=UpdateMode.NONE,
        )
        activate_mobile_app_version(active)

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=10
        )
        self.assertEqual(result["action"], "optional_update")
        self.assertTrue(result["update_available"])
        self.assertFalse(result["update_required"])
        self.assertFalse(result["blocked"])

    def test_required_update_only_when_force_and_below_minimum(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            minimum_build_number=15,
            update_mode=UpdateMode.REQUIRED,
        )
        activate_mobile_app_version(active)

        blocked = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=10
        )
        self.assertEqual(blocked["action"], "required_update")
        self.assertTrue(blocked["update_required"])

        optional_above_min = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="1.5.0", build_number=16
        )
        self.assertEqual(optional_above_min["action"], "optional_update")
        self.assertFalse(optional_above_min["update_required"])

    def test_non_forced_below_minimum_is_optional_not_required(self):
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
        self.assertEqual(result["action"], "optional_update")
        self.assertFalse(result["update_required"])

    def test_blocked_rows_do_not_affect_decision(self):
        from apps.mobile.models import BlockedMobileAppVersion

        active = _make_version(
            version_name="2.0.0", build_number=20, update_mode=UpdateMode.NONE
        )
        activate_mobile_app_version(active)
        BlockedMobileAppVersion.objects.create(
            platform=MobilePlatform.ANDROID,
            build_number=5,
            reason_ar="قديم",
        )

        result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="0.9.0", build_number=5
        )
        self.assertEqual(result["action"], "optional_update")
        self.assertFalse(result["blocked"])

    def test_android_policy_does_not_affect_ios(self):
        android = _make_version(
            platform=MobilePlatform.ANDROID,
            version_name="2.0.0",
            build_number=20,
            minimum_build_number=15,
            update_mode=UpdateMode.REQUIRED,
        )
        ios = _make_version(
            platform=MobilePlatform.IOS,
            version_name="2.0.0",
            build_number=20,
            update_mode=UpdateMode.NONE,
        )
        activate_mobile_app_version(android)
        activate_mobile_app_version(ios)

        android_result = evaluate_app_version_check(
            platform=MobilePlatform.ANDROID, version_name="1.0.0", build_number=10
        )
        ios_result = evaluate_app_version_check(
            platform=MobilePlatform.IOS, version_name="2.0.0", build_number=20
        )
        self.assertEqual(android_result["action"], "required_update")
        self.assertEqual(ios_result["action"], "no_update")

    def test_arabic_locale_text(self):
        active = _make_version(
            version_name="2.0.0",
            build_number=20,
            minimum_build_number=15,
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


@override_settings(AXES_ENABLED=False)
class AppEnabledNotDecisionSourceTests(TestCase):
    def setUp(self):
        self.config = MobileAppConfig.get_settings()
        self.config.app_enabled = False
        self.config.android_app_enabled = False
        self.config.ios_app_enabled = False
        self.config.force_update = False
        self.config.min_supported_build = 1
        self.config.save()

    def test_app_enabled_false_does_not_block_access(self):
        denial = evaluate_mobile_api_access(
            app_version="1.0.0",
            app_build=10,
            platform="android",
            config=self.config,
        )
        self.assertIsNone(denial)

    def test_payload_always_reports_app_enabled_true(self):
        payload = app_config_to_payload(self.config, platform="android")
        self.assertTrue(payload["app_enabled"])

        response = self.client.get(CONFIG_URL, {"platform": "android"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["app_enabled"])

    def test_force_update_below_minimum_still_blocks_api(self):
        self.config.force_update = True
        self.config.min_supported_build = 15
        self.config.save()
        denial = evaluate_mobile_api_access(
            app_version="1.0.0",
            app_build=10,
            platform="android",
            config=self.config,
        )
        self.assertIsNotNone(denial)
        self.assertEqual(denial["payload"]["code"], "app_update_required")


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

    def test_admin_list_is_simple_without_blocked_or_kill_switch(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dashboard:mobile_version_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "نسخ التطبيقات")
        self.assertContains(response, "إضافة Android")
        self.assertContains(response, "إضافة iOS")
        self.assertNotContains(response, "المحظورة")
        self.assertNotContains(response, "إضافة حظر")
        self.assertNotContains(response, "تشغيل التطبيق")
        self.assertNotContains(response, "تشغيل تطبيق Android")
        self.assertNotContains(response, "تشغيل تطبيق iOS")
        self.assertNotContains(response, "app_enabled")

    def test_form_has_no_platform_kill_switch(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("dashboard:mobile_version_create") + "?platform=android"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "آخر إصدار")
        self.assertContains(
            response,
            "عند تفعيل هذه النسخة سيتم تعطيل النسخة الفعّالة السابقة لنفس المنصة تلقائيًا.",
        )
        self.assertNotContains(response, "تشغيل تطبيق Android")
        self.assertNotContains(response, "تشغيل تطبيق iOS")
        self.assertNotContains(response, "platform_app_enabled")

    def test_blocked_urls_redirect_without_error(self):
        self.client.force_login(self.admin)
        for name in (
            "dashboard:blocked_mobile_version_list",
            "dashboard:blocked_mobile_version_create",
        ):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse("dashboard:mobile_version_list"))
