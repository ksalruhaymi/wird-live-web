import json
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.calls.models import CallSession
from apps.subscription.models import StudentSubscription, StudentSubscriptionBalance, SubscriptionPlan
from apps.notification.models import Notification
from apps.subscription.services import (
    LOW_MINUTES_MESSAGE,
    add_months,
    call_billable_minutes,
    call_duration_minutes,
    call_eligibility_payload,
    can_use_subscription_packages,
    create_student_subscription,
    current_subscription_payload,
    deduct_call_minutes_for_session,
    get_user_subscription_balance,
    maybe_send_low_minutes_notification,
    student_can_request_call,
    subscription_minutes_flags,
    sync_balance_status_from_expiry,
    subscription_to_payload,
)
from identity.accounts.user_types import (
    USER_TYPE_ADMIN,
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
)
from identity.rbac.models import Role

User = get_user_model()

SUBSCRIBE_URL = reverse("subscription_api:subscribe")
CURRENT_URL = reverse("subscription_api:current")
CALL_ELIGIBILITY_URL = reverse("subscription_api:call-eligibility")

MOBILE_API_HEADERS = {
    "HTTP_X_APP_VERSION": "99.0.0",
    "HTTP_X_APP_BUILD": "99999",
    "HTTP_X_APP_PLATFORM": "android",
}


class AdminSubscriptionAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.plan = SubscriptionPlan.objects.create(
            title="باقة تجريبية",
            duration_months=1,
            price=Decimal("99.00"),
            minutes=30,
            is_active=True,
        )
        cls.admin_user = User.objects.create_user(
            username="sub_admin",
            password="pass12345",
            user_type=USER_TYPE_ADMIN,
        )
        cls.student_user = User.objects.create_user(
            username="sub_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )
        cls.role_admin = Role.objects.get(slug="admin")
        cls.rbac_admin_user = User.objects.create_user(
            username="sub_rbac_admin",
            password="pass12345",
            user_type=USER_TYPE_SUPERVISOR,
        )
        cls.rbac_admin_user.roles.set([cls.role_admin])
        cls.role_supervisor = Role.objects.get(slug="supervisor")
        cls.supervisor_user = User.objects.create_user(
            username="sub_supervisor",
            password="pass12345",
            user_type=USER_TYPE_SUPERVISOR,
        )
        cls.supervisor_user.roles.set([cls.role_supervisor])

    def test_admin_current_subscription_is_applicable(self):
        payload = current_subscription_payload(self.admin_user)
        self.assertTrue(payload["applicable"])
        self.assertFalse(payload["has_active_subscription"])

    def test_admin_subscribe_records_zero_amount(self):
        sub, error = create_student_subscription(self.admin_user, plan_id=self.plan.id)
        self.assertIsNone(error)
        self.assertIsNotNone(sub)
        assert sub is not None
        self.assertEqual(sub.amount, Decimal("0"))
        self.assertEqual(sub.payment_method, "complimentary")
        self.assertEqual(sub.plan_minutes_added, self.plan.minutes)

    def test_student_subscribe_records_plan_price(self):
        sub, error = create_student_subscription(self.student_user, plan_id=self.plan.id)
        self.assertIsNone(error)
        self.assertIsNotNone(sub)
        assert sub is not None
        self.assertEqual(sub.amount, self.plan.price)
        self.assertEqual(sub.payment_method, "manual")

    def test_admin_subscribe_api_succeeds(self):
        self.client.force_login(self.admin_user)
        response = self.client.post(
            SUBSCRIBE_URL,
            data=json.dumps({"plan_id": self.plan.id}),
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(Decimal(body["subscription"]["amount"]), Decimal("0"))
        self.assertEqual(
            StudentSubscription.objects.filter(user=self.admin_user).count(),
            1,
        )

    def test_admin_current_api_is_applicable(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(CURRENT_URL, **MOBILE_API_HEADERS)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["applicable"])

    def test_admin_call_eligibility_is_applicable(self):
        payload = call_eligibility_payload(self.admin_user)
        self.assertTrue(payload["applicable"])
        self.assertFalse(payload["can_call"])

    def test_admin_can_call_after_complimentary_subscription(self):
        sub, error = create_student_subscription(self.admin_user, plan_id=self.plan.id)
        self.assertIsNone(error)
        assert sub is not None

        can_call, message = student_can_request_call(self.admin_user)
        self.assertTrue(can_call)
        self.assertEqual(message, "")

    def test_rbac_admin_with_supervisor_user_type_can_subscribe(self):
        self.assertTrue(can_use_subscription_packages(self.rbac_admin_user))

        sub, error = create_student_subscription(
            self.rbac_admin_user,
            plan_id=self.plan.id,
        )
        self.assertIsNone(error)
        assert sub is not None
        self.assertEqual(sub.amount, Decimal("0"))
        self.assertEqual(sub.payment_method, "complimentary")

    def test_supervisor_can_access_packages_but_not_complimentary(self):
        """Supervisor sees packages and must pay via store like a student."""
        from apps.subscription.services import is_complimentary_subscription_user
        from apps.subscription.store_verification.types import VerifiedStorePurchase

        self.assertTrue(can_use_subscription_packages(self.supervisor_user))
        self.assertFalse(is_complimentary_subscription_user(self.supervisor_user))

        payload = current_subscription_payload(self.supervisor_user)
        self.assertTrue(payload["applicable"])
        self.assertFalse(payload["has_active_subscription"])
        self.assertFalse(payload["can_call"])

        # Without store verification, paid checkout must be rejected.
        sub, error = create_student_subscription(
            self.supervisor_user,
            plan_id=self.plan.id,
            require_store_purchase=True,
        )
        self.assertIsNone(sub)
        self.assertIsNotNone(error)
        self.assertIn("متجر", error)

        product_id = f"wird_live_minutes_{self.plan.minutes}"
        verified = VerifiedStorePurchase(
            payment_method="play_store",
            product_id=product_id,
            transaction_id="sv_tx_supervisor_1",
            environment="sandbox",
            product_kind="consumable",
            package_or_bundle_id="com.kslabs.wirdlive",
            minutes=self.plan.minutes,
            needs_google_consume=True,
            google_purchase_token="token-supervisor-1",
        )
        with patch(
            "apps.subscription.store_verification.verify_store_purchase",
            return_value=verified,
        ), patch(
            "apps.subscription.store_verification.schedule_google_consume"
        ):
            sub, error = create_student_subscription(
                self.supervisor_user,
                plan_id=self.plan.id,
                payment_method="play_store",
                transaction_reference="sv_tx_supervisor_1",
                store_product_id=product_id,
                purchase_token="token-supervisor-1",
                require_store_purchase=True,
            )
        self.assertIsNone(error)
        assert sub is not None
        self.assertEqual(sub.payment_method, "play_store")
        self.assertEqual(sub.amount, self.plan.price)
        self.assertNotEqual(sub.payment_method, "complimentary")

        balance = get_user_subscription_balance(self.supervisor_user)
        assert balance is not None
        self.assertEqual(balance.remaining_minutes, self.plan.minutes)

        can_call, message = student_can_request_call(self.supervisor_user)
        self.assertTrue(can_call)
        self.assertEqual(message, "")

    def test_admin_call_eligibility_api_after_subscription(self):
        create_student_subscription(self.admin_user, plan_id=self.plan.id)
        self.client.force_login(self.admin_user)
        response = self.client.get(CALL_ELIGIBILITY_URL, **MOBILE_API_HEADERS)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["applicable"])
        self.assertTrue(body["can_call"])


class SubscriptionRenewalStackingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.plan_a = SubscriptionPlan.objects.create(
            title="باقة شهرية",
            duration_months=1,
            price=Decimal("50.00"),
            minutes=60,
            is_active=True,
        )
        cls.plan_b = SubscriptionPlan.objects.create(
            title="باقة ربع سنوية",
            duration_months=3,
            price=Decimal("120.00"),
            minutes=120,
            is_active=True,
        )
        cls.student = User.objects.create_user(
            username="renew_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )

    def test_renewal_stacks_minutes_and_extends_duration(self):
        """Each purchase creates its own pack; wallet = sum of active packs."""
        from apps.subscription.models import MinuteCreditPack

        first, err = create_student_subscription(self.student, plan_id=self.plan_a.id)
        self.assertIsNone(err)
        assert first is not None

        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        first_expires = balance.expires_at
        first_minutes = balance.remaining_minutes

        second, err = create_student_subscription(self.student, plan_id=self.plan_b.id)
        self.assertIsNone(err)
        assert second is not None

        balance.refresh_from_db()
        self.assertEqual(
            MinuteCreditPack.objects.filter(user=self.student).count(),
            2,
        )
        self.assertEqual(balance.remaining_minutes, first_minutes + self.plan_b.minutes)
        # Nearest expiry is the first (1-month) pack, not extended by the second.
        self.assertEqual(balance.expires_at, first_expires)
        pack_b = MinuteCreditPack.objects.get(student_subscription=second)
        self.assertEqual(
            pack_b.expires_at,
            add_months(timezone.localdate(), self.plan_b.duration_months),
        )
        self.assertEqual(second.minutes_before, first_minutes)
        self.assertEqual(second.minutes_after, balance.remaining_minutes)
        self.assertEqual(second.expiry_after, pack_b.expires_at)
        self.assertEqual(
            StudentSubscription.objects.filter(user=self.student).count(),
            2,
        )


class SubscriptionCallMinuteDeductionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.plan = SubscriptionPlan.objects.create(
            title="باقة دقائق",
            duration_months=1,
            price=Decimal("50.00"),
            minutes=60,
            is_active=True,
        )
        cls.student = User.objects.create_user(
            username="deduct_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )
        cls.teacher = User.objects.create_user(
            username="deduct_teacher",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )

    def _create_ended_call(self, *, seconds: int) -> CallSession:
        from datetime import timedelta

        started = timezone.now() - timedelta(seconds=seconds)
        ended = timezone.now()
        return CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            status=CallSession.Status.ENDED,
            started_at=started,
            ended_at=ended,
            student_media_ready_at=started,
        )

    def test_call_billable_minutes_uses_seconds_not_ceiling(self):
        call = self._create_ended_call(seconds=61)
        self.assertEqual(call_billable_minutes(call), Decimal("1.0167"))

    def test_short_call_charges_fractional_minute(self):
        call = self._create_ended_call(seconds=30)
        self.assertEqual(call_billable_minutes(call), Decimal("0.5"))

    def test_one_second_call_charges_fraction(self):
        call = self._create_ended_call(seconds=1)
        self.assertEqual(call_billable_minutes(call), Decimal("0.0167"))

    def test_deducts_minutes_when_call_ends(self):
        create_student_subscription(self.student, plan_id=self.plan.id)
        call = self._create_ended_call(seconds=120)

        charged = deduct_call_minutes_for_session(call)
        self.assertEqual(charged, Decimal("2"))

        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        self.assertEqual(balance.remaining_minutes, Decimal("58"))
        self.assertEqual(balance.used_minutes, Decimal("2"))

        call.refresh_from_db()
        self.assertEqual(call.minutes_charged, Decimal("2"))

    def test_deducts_fractional_minutes_for_short_call(self):
        create_student_subscription(self.student, plan_id=self.plan.id)
        call = self._create_ended_call(seconds=30)

        charged = deduct_call_minutes_for_session(call)
        self.assertEqual(charged, Decimal("0.5"))

        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        self.assertEqual(balance.remaining_minutes, Decimal("59.5"))
        self.assertEqual(balance.used_minutes, Decimal("0.5"))

    def test_deduction_is_idempotent(self):
        create_student_subscription(self.student, plan_id=self.plan.id)
        call = self._create_ended_call(seconds=60)

        first = deduct_call_minutes_for_session(call)
        second = deduct_call_minutes_for_session(call)
        self.assertEqual(first, Decimal("1"))
        self.assertEqual(second, Decimal("1"))

        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        self.assertEqual(balance.remaining_minutes, Decimal("59"))
        self.assertEqual(balance.used_minutes, Decimal("1"))


class SubscriptionLowMinutesWarningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.plan = SubscriptionPlan.objects.create(
            title="باقة تنبيه",
            duration_months=1,
            price=Decimal("50.00"),
            minutes=60,
            is_active=True,
        )
        cls.student = User.objects.create_user(
            username="low_minutes_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )

    def test_subscription_minutes_flags_low_warning(self):
        create_student_subscription(self.student, plan_id=self.plan.id)
        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        balance.remaining_minutes = Decimal("4.5")
        balance.save()

        flags = subscription_minutes_flags(balance)
        self.assertTrue(flags["low_minutes_warning"])
        self.assertFalse(flags["minutes_expired"])
        self.assertEqual(flags["low_minutes_message"], LOW_MINUTES_MESSAGE)

    def test_low_minutes_notification_sent_once_per_balance_cycle(self):
        create_student_subscription(self.student, plan_id=self.plan.id)
        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        balance.remaining_minutes = Decimal("4")
        balance.save()

        maybe_send_low_minutes_notification(self.student, balance)
        maybe_send_low_minutes_notification(self.student, balance)

        self.assertEqual(
            Notification.objects.filter(
                user=self.student,
                message=LOW_MINUTES_MESSAGE,
            ).count(),
            1,
        )
        balance.refresh_from_db()
        self.assertIsNotNone(balance.low_minutes_warning_sent_at)

    def test_current_subscription_payload_includes_minute_flags(self):
        create_student_subscription(self.student, plan_id=self.plan.id)
        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        balance.remaining_minutes = Decimal("0")
        balance.save()

        payload = current_subscription_payload(self.student)
        self.assertTrue(payload["minutes_expired"])
        self.assertEqual(payload["expired_message"], "لقد انتهت دقائق اتصالك")

    def test_new_purchase_resets_low_minutes_warning_flag(self):
        create_student_subscription(self.student, plan_id=self.plan.id)
        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        balance.remaining_minutes = Decimal("3")
        balance.low_minutes_warning_sent_at = timezone.now()
        balance.save()

        plan_b = SubscriptionPlan.objects.create(
            title="تجديد",
            duration_months=1,
            price=Decimal("50.00"),
            minutes=30,
            is_active=True,
        )
        create_student_subscription(self.student, plan_id=plan_b.id)
        balance.refresh_from_db()
        self.assertIsNone(balance.low_minutes_warning_sent_at)


class SubscriptionExpiryEligibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.plan = SubscriptionPlan.objects.create(
            title="باقة",
            duration_months=1,
            price=Decimal("99.00"),
            minutes=60,
            is_active=True,
        )
        cls.student = User.objects.create_user(
            username="expiry_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )

    def test_expired_balance_blocks_calls(self):
        from datetime import timedelta

        from apps.subscription.models import MinuteCreditPack

        create_student_subscription(self.student, plan_id=self.plan.id)
        pack = MinuteCreditPack.objects.get(user=self.student)
        pack.expires_at = timezone.localdate() - timedelta(days=1)
        pack.save(update_fields=["expires_at"])

        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        from apps.subscription.credit_packs import sync_wallet_from_packs

        sync_wallet_from_packs(self.student)
        balance.refresh_from_db()

        can_call, message = student_can_request_call(self.student)
        self.assertFalse(can_call)
        self.assertIn("اشتراك", message)

        payload = call_eligibility_payload(self.student)
        self.assertFalse(payload["can_call"])
        self.assertFalse(payload["has_active_subscription"])


class FreePlanDisplayTests(TestCase):
    """Zero-price packages must display only «مجاني» (no currency / zeros)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.free_plan = SubscriptionPlan.objects.create(
            title="باقة مجانية",
            duration_months=1,
            price=Decimal("0.00"),
            minutes=15,
            is_active=True,
            sort_order=1,
        )
        cls.paid_plan = SubscriptionPlan.objects.create(
            title="باقة مدفوعة",
            duration_months=1,
            price=Decimal("99.00"),
            minutes=60,
            is_active=True,
            sort_order=2,
        )
        cls.student = User.objects.create_user(
            username="free_plan_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )

    def test_plan_is_free_and_display_price(self):
        self.assertTrue(self.free_plan.is_free)
        self.assertEqual(self.free_plan.display_price, "مجاني")
        self.assertNotIn("ريال", self.free_plan.display_price)
        self.assertNotIn("0", self.free_plan.display_price)

        self.assertFalse(self.paid_plan.is_free)
        self.assertEqual(self.paid_plan.display_price, "99.00 ريال")

    def test_list_plans_api_exposes_free_fields(self):
        response = self.client.get(
            reverse("subscription_api:list-plans"),
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(response.status_code, 200)
        plans = {p["title"]: p for p in response.json()["plans"]}

        free = plans["باقة مجانية"]
        self.assertTrue(free["is_free"])
        self.assertEqual(free["display_price"], "مجاني")
        self.assertEqual(free["price"], "0.00")

        paid = plans["باقة مدفوعة"]
        self.assertFalse(paid["is_free"])
        self.assertEqual(paid["display_price"], "99.00 ريال")
        self.assertEqual(paid["price"], "99.00")

    def test_subscription_payload_for_free_plan(self):
        sub, error = create_student_subscription(
            self.student, plan_id=self.free_plan.id
        )
        self.assertIsNone(error)
        assert sub is not None
        self.assertTrue(sub.is_free)
        self.assertEqual(sub.display_price, "مجاني")

        payload = subscription_to_payload(sub, include_display=True)
        self.assertTrue(payload["is_free"])
        self.assertEqual(payload["display_price"], "مجاني")
        self.assertEqual(payload["amount"], "0.00")


class StorePurchaseSubscribeApiTests(TestCase):
    """Paid plans via mobile API require verified store purchases."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.paid_plan = SubscriptionPlan.objects.create(
            title="باقة متجر",
            duration_months=1,
            price=Decimal("49.00"),
            minutes=20,
            is_active=True,
        )
        cls.free_plan = SubscriptionPlan.objects.create(
            title="باقة مجانية متجر",
            duration_months=1,
            price=Decimal("0.00"),
            minutes=5,
            is_active=True,
        )
        cls.student = User.objects.create_user(
            username="store_student",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )
        cls.other_student = User.objects.create_user(
            username="store_student_other",
            password="pass12345",
            user_type=USER_TYPE_STUDENT,
        )

    def _verified(self, *, method="play_store", tx="gp-verified-001"):
        from apps.subscription.store_verification.types import VerifiedStorePurchase

        product_id = (
            f"wird_live_minutes_{self.paid_plan.minutes}"
            if method == "play_store"
            else f"com.kslabs.wirdlive.minutes.{self.paid_plan.minutes}"
        )
        return VerifiedStorePurchase(
            payment_method=method,
            product_id=product_id,
            transaction_id=tx,
            environment="sandbox",
            product_kind="consumable",
            package_or_bundle_id="com.kslabs.wirdlive",
            minutes=self.paid_plan.minutes,
            needs_google_consume=(method == "play_store"),
            google_purchase_token="token-abc" if method == "play_store" else "",
        )

    def test_paid_plan_rejects_manual_without_store_reference(self):
        self.client.force_login(self.student)
        response = self.client.post(
            SUBSCRIBE_URL,
            data=json.dumps(
                {"plan_id": self.paid_plan.id, "payment_method": "manual"}
            ),
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertEqual(
            StudentSubscription.objects.filter(user=self.student).count(),
            0,
        )

    def test_paid_plan_rejects_transaction_reference_without_token(self):
        self.client.force_login(self.student)
        response = self.client.post(
            SUBSCRIBE_URL,
            data=json.dumps(
                {
                    "plan_id": self.paid_plan.id,
                    "payment_method": "play_store",
                    "transaction_reference": "client-only-tx",
                }
            ),
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("التحقق", response.json()["message"])
        self.assertEqual(
            StudentSubscription.objects.filter(user=self.student).count(),
            0,
        )

    @patch("apps.subscription.store_verification.verify_store_purchase")
    def test_paid_plan_rejects_when_verification_fails(self, mock_verify):
        from apps.subscription.store_verification.types import StoreVerificationError

        mock_verify.side_effect = StoreVerificationError("تحقق فاشل")
        self.client.force_login(self.student)
        response = self.client.post(
            SUBSCRIBE_URL,
            data=json.dumps(
                {
                    "plan_id": self.paid_plan.id,
                    "payment_method": "play_store",
                    "purchase_token": "fake-token",
                    "store_product_id": f"wird_live_minutes_{self.paid_plan.minutes}",
                }
            ),
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "تحقق فاشل")
        self.assertEqual(
            StudentSubscription.objects.filter(user=self.student).count(),
            0,
        )

    def test_paid_plan_activates_after_verified_store_purchase(self):
        verified = self._verified(method="play_store", tx="gp-verified-001")
        with patch(
            "apps.subscription.store_verification.verify_store_purchase",
            return_value=verified,
        ), patch(
            "apps.subscription.store_verification.schedule_google_consume",
        ) as consume:
            self.client.force_login(self.student)
            response = self.client.post(
                SUBSCRIBE_URL,
                data=json.dumps(
                    {
                        "plan_id": self.paid_plan.id,
                        "payment_method": "play_store",
                        "transaction_reference": "ignored-client-tx",
                        "purchase_token": "real-play-token",
                        "store_product_id": f"wird_live_minutes_{self.paid_plan.minutes}",
                    }
                ),
                content_type="application/json",
                **MOBILE_API_HEADERS,
            )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["success"])
        sub = StudentSubscription.objects.get(user=self.student)
        self.assertEqual(sub.payment_method, "play_store")
        self.assertEqual(sub.transaction_reference, "gp-verified-001")
        self.assertEqual(sub.plan_minutes_added, self.paid_plan.minutes)
        consume.assert_called_once()

    def test_same_minute_sku_can_be_purchased_again_with_new_transaction(self):
        first = self._verified(method="play_store", tx="gp-tx-a")
        second = self._verified(method="play_store", tx="gp-tx-b")
        payload_base = {
            "plan_id": self.paid_plan.id,
            "payment_method": "play_store",
            "purchase_token": "real-play-token",
            "store_product_id": f"wird_live_minutes_{self.paid_plan.minutes}",
        }
        with patch(
            "apps.subscription.store_verification.schedule_google_consume",
        ):
            with patch(
                "apps.subscription.store_verification.verify_store_purchase",
                return_value=first,
            ):
                self.client.force_login(self.student)
                r1 = self.client.post(
                    SUBSCRIBE_URL,
                    data=json.dumps(payload_base),
                    content_type="application/json",
                    **MOBILE_API_HEADERS,
                )
            with patch(
                "apps.subscription.store_verification.verify_store_purchase",
                return_value=second,
            ):
                r2 = self.client.post(
                    SUBSCRIBE_URL,
                    data=json.dumps(payload_base),
                    content_type="application/json",
                    **MOBILE_API_HEADERS,
                )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(
            StudentSubscription.objects.filter(user=self.student).count(),
            2,
        )

    def test_store_transaction_is_idempotent(self):
        verified = self._verified(method="app_store", tx="ios-tx-dup-1")
        payload = {
            "plan_id": self.paid_plan.id,
            "payment_method": "app_store",
            "transaction_reference": "ios-tx-dup-1",
            "purchase_token": "signed.jws.token",
            "store_product_id": f"com.kslabs.wirdlive.minutes.{self.paid_plan.minutes}",
        }
        with patch(
            "apps.subscription.store_verification.verify_store_purchase",
            return_value=verified,
        ):
            self.client.force_login(self.student)
            first = self.client.post(
                SUBSCRIBE_URL,
                data=json.dumps(payload),
                content_type="application/json",
                **MOBILE_API_HEADERS,
            )
            second = self.client.post(
                SUBSCRIBE_URL,
                data=json.dumps(payload),
                content_type="application/json",
                **MOBILE_API_HEADERS,
            )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(
            StudentSubscription.objects.filter(user=self.student).count(),
            1,
        )

    def test_store_transaction_cannot_be_reused_by_another_user(self):
        verified = self._verified(method="app_store", tx="ios-shared-tx")
        payload = {
            "plan_id": self.paid_plan.id,
            "payment_method": "app_store",
            "purchase_token": "signed.jws.token",
            "store_product_id": f"com.kslabs.wirdlive.minutes.{self.paid_plan.minutes}",
        }
        with patch(
            "apps.subscription.store_verification.verify_store_purchase",
            return_value=verified,
        ):
            self.client.force_login(self.student)
            first = self.client.post(
                SUBSCRIBE_URL,
                data=json.dumps(payload),
                content_type="application/json",
                **MOBILE_API_HEADERS,
            )
            self.client.force_login(self.other_student)
            second = self.client.post(
                SUBSCRIBE_URL,
                data=json.dumps(payload),
                content_type="application/json",
                **MOBILE_API_HEADERS,
            )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertIn("مستخدمة", second.json()["message"])

    def test_free_plan_still_allows_manual(self):
        self.client.force_login(self.student)
        response = self.client.post(
            SUBSCRIBE_URL,
            data=json.dumps(
                {"plan_id": self.free_plan.id, "payment_method": "manual"}
            ),
            content_type="application/json",
            **MOBILE_API_HEADERS,
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["success"])
