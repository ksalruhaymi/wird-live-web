"""Unit tests for minute-package consumable catalog + Apple JWS gate."""

from django.test import SimpleTestCase, override_settings

from apps.subscription.store_verification.apple import decode_and_verify_signed_transaction
from apps.subscription.store_verification.catalog import (
    PRODUCT_KIND_CONSUMABLE,
    android_product_id_for_minutes,
    expected_product_id,
    ios_product_id_for_minutes,
    minutes_from_product_id,
)
from apps.subscription.store_verification.types import StoreVerificationError


class StoreCatalogTests(SimpleTestCase):
    def test_product_ids_are_minutes_consumables(self):
        self.assertEqual(
            ios_product_id_for_minutes(30),
            "com.kslabs.wirdlive.minutes.30",
        )
        self.assertEqual(android_product_id_for_minutes(30), "wird_live_minutes_30")
        self.assertEqual(
            expected_product_id(minutes=30, payment_method="app_store"),
            "com.kslabs.wirdlive.minutes.30",
        )
        self.assertEqual(
            expected_product_id(minutes=30, payment_method="play_store"),
            "wird_live_minutes_30",
        )
        self.assertEqual(PRODUCT_KIND_CONSUMABLE, "consumable")

    def test_minutes_from_product_id(self):
        self.assertEqual(
            minutes_from_product_id("com.kslabs.wirdlive.minutes.60"),
            60,
        )
        self.assertEqual(minutes_from_product_id("wird_live_minutes_15"), 15)
        self.assertIsNone(minutes_from_product_id("com.kslabs.wirdlive.plan.3"))
        self.assertIsNone(minutes_from_product_id("wird_live_plan_3"))


class AppleJwsGateTests(SimpleTestCase):
    def test_rejects_non_jws_payload(self):
        with self.assertRaises(StoreVerificationError):
            decode_and_verify_signed_transaction("not-a-jws")

    def test_rejects_malformed_jws(self):
        with self.assertRaises(StoreVerificationError):
            decode_and_verify_signed_transaction("aaa.bbb.ccc")


@override_settings(STORE_BILLING_ENV="sandbox")
class StoreEnvironmentTests(SimpleTestCase):
    def test_expected_environment_sandbox(self):
        from apps.subscription.store_verification.service import expected_store_environment

        self.assertEqual(expected_store_environment(), "sandbox")
