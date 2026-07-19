"""Minute credit pack purchase, expiry, and multi-pack deduction tests."""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.calls.models import CallSession
from apps.subscription.credit_packs import (
    available_minutes_for_user,
    deduct_minutes_from_packs,
)
from apps.subscription.models import MinuteCreditPack, SubscriptionPlan
from apps.subscription.services import (
    add_months,
    create_student_subscription,
    deduct_call_minutes_for_session,
    get_user_subscription_balance,
)
from apps.subscription.store_verification.types import (
    StoreVerificationError,
    VerifiedStorePurchase,
)
from identity.accounts.user_types import USER_TYPE_STUDENT

User = get_user_model()


class MinuteCreditPackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.plan_60_month = SubscriptionPlan.objects.create(
            title="60 دقيقة / شهر",
            duration_months=1,
            validity_value=1,
            validity_unit=SubscriptionPlan.ValidityUnit.MONTHS,
            price=Decimal("49.00"),
            minutes=60,
            is_active=True,
        )
        cls.plan_open = SubscriptionPlan.objects.create(
            title="باقة مفتوحة",
            duration_months=0,
            validity_value=None,
            validity_unit=None,
            price=Decimal("99.00"),
            minutes=40,
            is_active=True,
        )
        cls.plan_30_month = SubscriptionPlan.objects.create(
            title="30 دقيقة / شهر",
            duration_months=1,
            validity_value=1,
            validity_unit=SubscriptionPlan.ValidityUnit.MONTHS,
            price=Decimal("29.00"),
            minutes=30,
            is_active=True,
        )
        cls.free_plan = SubscriptionPlan.objects.create(
            title="مجانية",
            duration_months=1,
            validity_value=1,
            validity_unit=SubscriptionPlan.ValidityUnit.MONTHS,
            price=Decimal("0.00"),
            minutes=10,
            is_active=True,
        )
        cls.student = User.objects.create_user(
            username="pack_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )

    def _verified(self, plan, *, tx: str, method="play_store"):
        product_id = (
            f"wird_live_minutes_{plan.minutes}"
            if method == "play_store"
            else f"com.kslabs.wirdlive.minutes.{plan.minutes}"
        )
        return VerifiedStorePurchase(
            payment_method=method,
            product_id=product_id,
            transaction_id=tx,
            environment="sandbox",
            product_kind="consumable",
            package_or_bundle_id="com.kslabs.wirdlive",
            minutes=plan.minutes,
            needs_google_consume=(method == "play_store"),
            google_purchase_token=f"token-{tx}",
        )

    def _purchase(self, plan, *, tx: str):
        verified = self._verified(plan, tx=tx)
        with patch(
            "apps.subscription.store_verification.verify_store_purchase",
            return_value=verified,
        ), patch(
            "apps.subscription.store_verification.schedule_google_consume",
        ):
            sub, err = create_student_subscription(
                self.student,
                plan_id=plan.id,
                payment_method="play_store",
                purchase_token=f"token-{tx}",
                store_product_id=verified.product_id,
                transaction_reference=tx,
                require_store_purchase=True,
            )
        self.assertIsNone(err)
        assert sub is not None
        return sub

    def test_timed_60_minute_pack_has_correct_expiry(self):
        self._purchase(self.plan_60_month, tx="tx-60")
        pack = MinuteCreditPack.objects.get(user=self.student)
        self.assertEqual(pack.purchased_minutes, Decimal("60"))
        self.assertEqual(pack.remaining_minutes, Decimal("60"))
        self.assertEqual(
            pack.expires_at,
            add_months(timezone.localdate(), 1),
        )
        self.assertEqual(pack.status, MinuteCreditPack.Status.ACTIVE)
        balance = get_user_subscription_balance(self.student)
        self.assertEqual(balance.remaining_minutes, Decimal("60"))

    def test_open_pack_has_null_expires_at(self):
        self._purchase(self.plan_open, tx="tx-open")
        pack = MinuteCreditPack.objects.get(user=self.student)
        self.assertIsNone(pack.expires_at)
        self.assertEqual(pack.remaining_minutes, Decimal("40"))
        self.assertEqual(available_minutes_for_user(self.student), Decimal("40"))

    def test_exhausting_minutes_ends_pack_before_expiry(self):
        self._purchase(self.plan_60_month, tx="tx-exh")
        deducted = deduct_minutes_from_packs(self.student, Decimal("60"))
        self.assertEqual(deducted, Decimal("60"))
        pack = MinuteCreditPack.objects.get(user=self.student)
        self.assertEqual(pack.status, MinuteCreditPack.Status.EXHAUSTED)
        self.assertEqual(pack.remaining_minutes, Decimal("0"))
        self.assertEqual(available_minutes_for_user(self.student), Decimal("0"))

    def test_date_expiry_voids_remaining_minutes(self):
        self._purchase(self.plan_60_month, tx="tx-exp")
        pack = MinuteCreditPack.objects.get(user=self.student)
        pack.expires_at = timezone.localdate() - timedelta(days=1)
        pack.save(update_fields=["expires_at"])
        self.assertEqual(available_minutes_for_user(self.student), Decimal("0"))
        pack.refresh_from_db()
        self.assertEqual(pack.status, MinuteCreditPack.Status.EXPIRED)

    def test_deduct_prefers_nearest_expiry_then_open(self):
        self._purchase(self.plan_60_month, tx="tx-near")
        self._purchase(self.plan_open, tx="tx-open2")
        near = MinuteCreditPack.objects.get(store_transaction_id="tx-near")
        open_pack = MinuteCreditPack.objects.get(store_transaction_id="tx-open2")
        near.expires_at = timezone.localdate() + timedelta(days=5)
        near.save(update_fields=["expires_at"])

        deduct_minutes_from_packs(self.student, Decimal("10"))
        near.refresh_from_db()
        open_pack.refresh_from_db()
        self.assertEqual(near.remaining_minutes, Decimal("50"))
        self.assertEqual(open_pack.remaining_minutes, Decimal("40"))

    def test_single_session_can_span_two_packs(self):
        self._purchase(self.plan_30_month, tx="tx-p1")
        self._purchase(self.plan_60_month, tx="tx-p2")
        p1 = MinuteCreditPack.objects.get(store_transaction_id="tx-p1")
        p2 = MinuteCreditPack.objects.get(store_transaction_id="tx-p2")
        # Make p1 expire sooner so it is consumed first.
        p1.expires_at = timezone.localdate() + timedelta(days=3)
        p2.expires_at = timezone.localdate() + timedelta(days=20)
        p1.save(update_fields=["expires_at"])
        p2.save(update_fields=["expires_at"])

        deducted = deduct_minutes_from_packs(self.student, Decimal("45"))
        self.assertEqual(deducted, Decimal("45"))
        p1.refresh_from_db()
        p2.refresh_from_db()
        self.assertEqual(p1.status, MinuteCreditPack.Status.EXHAUSTED)
        self.assertEqual(p1.remaining_minutes, Decimal("0"))
        self.assertEqual(p2.remaining_minutes, Decimal("45"))

    def test_same_transaction_does_not_double_credit(self):
        self._purchase(self.plan_60_month, tx="tx-dup")
        self._purchase(self.plan_60_month, tx="tx-dup")
        self.assertEqual(
            MinuteCreditPack.objects.filter(user=self.student).count(),
            1,
        )
        self.assertEqual(available_minutes_for_user(self.student), Decimal("60"))

    def test_same_sku_new_transaction_adds_new_pack(self):
        self._purchase(self.plan_60_month, tx="tx-a")
        self._purchase(self.plan_60_month, tx="tx-b")
        self.assertEqual(
            MinuteCreditPack.objects.filter(user=self.student).count(),
            2,
        )
        self.assertEqual(available_minutes_for_user(self.student), Decimal("120"))

    def test_verification_failure_creates_no_pack(self):
        with patch(
            "apps.subscription.store_verification.verify_store_purchase",
            side_effect=StoreVerificationError("فشل التحقق"),
        ):
            sub, err = create_student_subscription(
                self.student,
                plan_id=self.plan_60_month.id,
                payment_method="play_store",
                purchase_token="bad",
                require_store_purchase=True,
            )
        self.assertIsNone(sub)
        self.assertEqual(err, "فشل التحقق")
        self.assertEqual(MinuteCreditPack.objects.filter(user=self.student).count(), 0)

    def test_free_plan_unaffected_creates_pack_without_store(self):
        sub, err = create_student_subscription(
            self.student,
            plan_id=self.free_plan.id,
            payment_method="manual",
            require_store_purchase=True,
        )
        self.assertIsNone(err)
        assert sub is not None
        pack = MinuteCreditPack.objects.get(user=self.student)
        self.assertEqual(pack.store, "manual")
        self.assertEqual(pack.purchased_minutes, Decimal("10"))

    def test_call_deduction_uses_packs_without_changing_billing_math(self):
        self._purchase(self.plan_60_month, tx="tx-call")
        now = timezone.now()
        teacher = User.objects.create_user(
            username="pack_teacher",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )
        call = CallSession.objects.create(
            student=self.student,
            teacher=teacher,
            session_type=CallSession.SessionType.AUDIO,
            status=CallSession.Status.ENDED,
            started_at=now,
            ended_at=now + timedelta(minutes=2),
            student_media_ready_at=now,
        )
        charged = deduct_call_minutes_for_session(call)
        self.assertEqual(charged, Decimal("2"))
        pack = MinuteCreditPack.objects.get(user=self.student)
        self.assertEqual(pack.remaining_minutes, Decimal("58"))
        balance = get_user_subscription_balance(self.student)
        self.assertEqual(balance.remaining_minutes, Decimal("58"))

    def test_pending_consume_flag_set_for_google(self):
        self._purchase(self.plan_60_month, tx="tx-consume")
        pack = MinuteCreditPack.objects.get(store_transaction_id="tx-consume")
        self.assertTrue(pack.google_consume_pending)


class PlanValidityExpiryTests(TestCase):
    """Validity days/months/open-ended expiry calculation and migration mapping."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.student = User.objects.create_user(
            username="validity_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )

    def _verified(self, plan, *, tx: str):
        return VerifiedStorePurchase(
            payment_method="play_store",
            product_id=f"wird_live_minutes_{plan.minutes}",
            transaction_id=tx,
            environment="sandbox",
            product_kind="consumable",
            package_or_bundle_id="com.kslabs.wirdlive",
            minutes=plan.minutes,
            needs_google_consume=True,
            google_purchase_token=f"token-{tx}",
        )

    def _purchase(self, plan, *, tx: str):
        verified = self._verified(plan, tx=tx)
        with patch(
            "apps.subscription.store_verification.verify_store_purchase",
            return_value=verified,
        ), patch(
            "apps.subscription.store_verification.schedule_google_consume",
        ):
            sub, err = create_student_subscription(
                self.student,
                plan_id=plan.id,
                payment_method="play_store",
                purchase_token=f"token-{tx}",
                store_product_id=verified.product_id,
                transaction_reference=tx,
                require_store_purchase=True,
            )
        self.assertIsNone(err)
        assert sub is not None
        return sub

    def test_seven_day_pack_expires_after_seven_days(self):
        from apps.subscription.credit_packs import compute_pack_expires_at

        plan = SubscriptionPlan.objects.create(
            title="7 أيام",
            duration_months=0,
            validity_value=7,
            validity_unit=SubscriptionPlan.ValidityUnit.DAYS,
            price=Decimal("19.00"),
            minutes=20,
            is_active=True,
        )
        purchased_at = timezone.now().replace(
            year=2026, month=3, day=10, hour=12, minute=0, second=0, microsecond=0
        )
        expires = compute_pack_expires_at(plan=plan, purchased_at=purchased_at)
        self.assertEqual(expires, purchased_at.date() + timedelta(days=7))

        self._purchase(plan, tx="tx-7d")
        pack = MinuteCreditPack.objects.filter(user=self.student, plan=plan).latest("id")
        self.assertEqual(
            pack.expires_at,
            timezone.localdate() + timedelta(days=7),
        )

    def test_one_month_from_january_31_uses_calendar_months(self):
        from apps.subscription.credit_packs import compute_pack_expires_at
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        plan = SubscriptionPlan.objects.create(
            title="شهر من 31 يناير",
            duration_months=1,
            validity_value=1,
            validity_unit=SubscriptionPlan.ValidityUnit.MONTHS,
            price=Decimal("29.00"),
            minutes=30,
            is_active=True,
        )
        purchased_at = timezone.make_aware(datetime(2026, 1, 31, 15, 0, 0))
        expires = compute_pack_expires_at(plan=plan, purchased_at=purchased_at)
        expected = (purchased_at.date() + relativedelta(months=1))
        self.assertEqual(expires, expected)
        self.assertEqual(expires, date(2026, 2, 28))

    def test_two_months_uses_calendar_not_fixed_60_days(self):
        from apps.subscription.credit_packs import compute_pack_expires_at
        from datetime import datetime
        from dateutil.relativedelta import relativedelta

        plan = SubscriptionPlan.objects.create(
            title="شهران",
            duration_months=2,
            validity_value=2,
            validity_unit=SubscriptionPlan.ValidityUnit.MONTHS,
            price=Decimal("39.00"),
            minutes=40,
            is_active=True,
        )
        purchased_at = timezone.make_aware(datetime(2026, 1, 15, 10, 0, 0))
        expires = compute_pack_expires_at(plan=plan, purchased_at=purchased_at)
        self.assertEqual(expires, purchased_at.date() + relativedelta(months=2))
        self.assertNotEqual(expires, purchased_at.date() + timedelta(days=60))
        self.assertEqual(expires, date(2026, 3, 15))

    def test_open_ended_pack_has_null_expires_at(self):
        plan = SubscriptionPlan.objects.create(
            title="مفتوحة",
            duration_months=0,
            validity_value=None,
            validity_unit=None,
            price=Decimal("9.00"),
            minutes=15,
            is_active=True,
        )
        self.assertTrue(plan.is_open_ended)
        self._purchase(plan, tx="tx-open-v")
        pack = MinuteCreditPack.objects.filter(user=self.student, plan=plan).latest("id")
        self.assertIsNone(pack.expires_at)

    def test_duration_months_migration_maps_to_months_unit(self):
        import importlib.util
        from pathlib import Path

        timed = SubscriptionPlan.objects.create(
            title="legacy timed",
            duration_months=3,
            validity_value=None,
            validity_unit=None,
            price=Decimal("10.00"),
            minutes=10,
        )
        open_plan = SubscriptionPlan.objects.create(
            title="legacy open",
            duration_months=0,
            validity_value=None,
            validity_unit=None,
            price=Decimal("10.00"),
            minutes=10,
        )

        migration_path = (
            Path(__file__).resolve().parent
            / "migrations"
            / "0012_subscriptionplan_validity_fields.py"
        )
        spec = importlib.util.spec_from_file_location(
            "subscription_validity_migration",
            migration_path,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Reset to pre-migration shape then run data migration.
        SubscriptionPlan.objects.filter(pk=timed.pk).update(
            validity_value=None,
            validity_unit=None,
            duration_months=3,
        )
        SubscriptionPlan.objects.filter(pk=open_plan.pk).update(
            validity_value=None,
            validity_unit=None,
            duration_months=0,
        )
        module.forwards_migrate_duration_months(django_apps, None)

        timed.refresh_from_db()
        open_plan.refresh_from_db()
        self.assertEqual(timed.validity_value, 3)
        self.assertEqual(timed.validity_unit, SubscriptionPlan.ValidityUnit.MONTHS)
        self.assertIsNone(open_plan.validity_value)
        self.assertIsNone(open_plan.validity_unit)

    def test_list_plans_api_returns_validity_fields(self):
        from django.urls import reverse

        from apps.subscription.tests import MOBILE_API_HEADERS

        plan = SubscriptionPlan.objects.create(
            title="API validity",
            duration_months=0,
            validity_value=15,
            validity_unit=SubscriptionPlan.ValidityUnit.DAYS,
            price=Decimal("12.00"),
            minutes=25,
            is_active=True,
        )
        response = self.client.get(
            reverse("subscription_api:list-plans"),
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        match = next(p for p in payload["plans"] if p["id"] == plan.id)
        self.assertEqual(match["validity_value"], 15)
        self.assertEqual(match["validity_unit"], "days")
        self.assertFalse(match["is_open_ended"])

        open_plan = SubscriptionPlan.objects.create(
            title="API open",
            duration_months=0,
            validity_value=None,
            validity_unit=None,
            price=Decimal("5.00"),
            minutes=5,
            is_active=True,
        )
        response = self.client.get(
            reverse("subscription_api:list-plans"),
            **MOBILE_API_HEADERS,
        )
        match_open = next(p for p in response.json()["plans"] if p["id"] == open_plan.id)
        self.assertIsNone(match_open["validity_value"])
        self.assertIsNone(match_open["validity_unit"])
        self.assertTrue(match_open["is_open_ended"])

