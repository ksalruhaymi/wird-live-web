import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.calls.models import CallSession
from apps.subscription.models import StudentSubscription, StudentSubscriptionBalance, SubscriptionPlan
from apps.subscription.services import (
    add_months,
    call_duration_minutes,
    call_eligibility_payload,
    can_use_subscription_packages,
    create_student_subscription,
    current_subscription_payload,
    deduct_call_minutes_for_session,
    get_user_subscription_balance,
    student_can_request_call,
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
        self.assertEqual(second.transaction_type, "renewal")
        self.assertEqual(balance.remaining_minutes, first_minutes + self.plan_b.minutes)
        self.assertEqual(balance.expires_at, add_months(first_expires, self.plan_b.duration_months))
        self.assertEqual(second.start_date, first_expires)
        self.assertEqual(second.end_date, balance.expires_at)
        self.assertEqual(second.minutes_before, first_minutes)
        self.assertEqual(second.minutes_after, balance.remaining_minutes)
        self.assertEqual(second.expiry_before, first_expires)
        self.assertEqual(second.expiry_after, balance.expires_at)
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
        )

    def test_call_duration_minutes_rounds_up(self):
        call = self._create_ended_call(seconds=61)
        self.assertEqual(call_duration_minutes(call), 2)

    def test_deducts_minutes_when_call_ends(self):
        create_student_subscription(self.student, plan_id=self.plan.id)
        call = self._create_ended_call(seconds=120)

        charged = deduct_call_minutes_for_session(call)
        self.assertEqual(charged, 2)

        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        self.assertEqual(balance.remaining_minutes, 58)
        self.assertEqual(balance.used_minutes, 2)

        call.refresh_from_db()
        self.assertEqual(call.minutes_charged, 2)

    def test_deduction_is_idempotent(self):
        create_student_subscription(self.student, plan_id=self.plan.id)
        call = self._create_ended_call(seconds=60)

        first = deduct_call_minutes_for_session(call)
        second = deduct_call_minutes_for_session(call)
        self.assertEqual(first, 1)
        self.assertEqual(second, 1)

        balance = get_user_subscription_balance(self.student)
        assert balance is not None
        self.assertEqual(balance.remaining_minutes, 59)
        self.assertEqual(balance.used_minutes, 1)
