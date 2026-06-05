from calendar import monthrange
from datetime import date

from django.db import migrations


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    max_day = monthrange(year, month)[1]
    day = min(start.day, max_day)
    return date(year, month, day)


def backfill_balances(apps, schema_editor):
    StudentSubscription = apps.get_model("subscription", "StudentSubscription")
    StudentSubscriptionBalance = apps.get_model(
        "subscription", "StudentSubscriptionBalance"
    )
    SubscriptionPlan = apps.get_model("subscription", "SubscriptionPlan")

    paid_status = "paid"
    active_status = "active"
    cancelled_status = "cancelled"

    user_ids = (
        StudentSubscription.objects.filter(payment_status=paid_status)
        .values_list("user_id", flat=True)
        .distinct()
    )

    for user_id in user_ids:
        subs = (
            StudentSubscription.objects.filter(
                user_id=user_id,
                payment_status=paid_status,
            )
            .select_related("plan")
            .order_by("created_at", "id")
        )

        remaining = 0
        expires_at = None
        status = "expired"
        plan_title = ""
        last_purchase_at = None

        for sub in subs:
            plan_minutes = 0
            if sub.plan_id:
                try:
                    plan = SubscriptionPlan.objects.get(pk=sub.plan_id)
                    plan_minutes = plan.minutes or 0
                except SubscriptionPlan.DoesNotExist:
                    plan_minutes = 0

            purchase_date = sub.start_date
            balance_active = (
                status == active_status
                and expires_at is not None
                and expires_at >= purchase_date
            )

            minutes_before = remaining
            expiry_before = expires_at

            if balance_active:
                extend_from = expires_at
                remaining += plan_minutes
                transaction_type = "renewal"
            else:
                extend_from = purchase_date
                remaining = plan_minutes
                transaction_type = "purchase"

            new_expires = add_months(extend_from, sub.duration_months)
            if sub.status == cancelled_status:
                status = cancelled_status
            else:
                status = active_status

            expires_at = new_expires
            plan_title = sub.plan_title
            last_purchase_at = sub.created_at

            updates = {}
            if not sub.plan_minutes_added:
                updates["plan_minutes_added"] = plan_minutes
            if sub.minutes_before is None:
                updates["minutes_before"] = minutes_before
            if sub.minutes_after is None:
                updates["minutes_after"] = remaining
            if sub.expiry_before is None:
                updates["expiry_before"] = expiry_before
            if sub.expiry_after is None:
                updates["expiry_after"] = new_expires
            if not sub.transaction_type or sub.transaction_type == "purchase":
                updates["transaction_type"] = transaction_type
            if updates:
                StudentSubscription.objects.filter(pk=sub.pk).update(**updates)

        today = date.today()
        if expires_at and expires_at < today and status != cancelled_status:
            status = "expired"

        StudentSubscriptionBalance.objects.update_or_create(
            user_id=user_id,
            defaults={
                "current_plan_title": plan_title,
                "remaining_minutes": remaining,
                "used_minutes": 0,
                "expires_at": expires_at,
                "status": status,
                "last_purchase_at": last_purchase_at,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("subscription", "0006_subscription_balance_and_ledger"),
    ]

    operations = [
        migrations.RunPython(backfill_balances, migrations.RunPython.noop),
    ]
