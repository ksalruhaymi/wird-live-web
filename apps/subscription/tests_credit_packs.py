"""Minute credit pack purchase, expiry, and multi-pack deduction tests."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

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
            price=Decimal("49.00"),
            minutes=60,
            is_active=True,
        )
        cls.plan_open = SubscriptionPlan.objects.create(
            title="باقة مفتوحة",
            duration_months=0,
            price=Decimal("99.00"),
            minutes=40,
            is_active=True,
        )
        cls.plan_30_month = SubscriptionPlan.objects.create(
            title="30 دقيقة / شهر",
            duration_months=1,
            price=Decimal("29.00"),
            minutes=30,
            is_active=True,
        )
        cls.free_plan = SubscriptionPlan.objects.create(
            title="مجانية",
            duration_months=1,
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
