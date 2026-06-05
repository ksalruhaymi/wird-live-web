from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.subscription.models import StudentSubscription, StudentSubscriptionBalance
from apps.subscription.services import (
    balance_display_status,
    display_status,
    display_status_label,
    get_user_subscription_balance,
)
from identity.accounts.user_types import USER_TYPE_STUDENT
from identity.rbac.decorators import permissions_required

User = get_user_model()

FILTER_ALL = "all"
FILTER_ACTIVE = "active"
FILTER_EXPIRED = "expired"
FILTER_CANCELLED = "cancelled"


def _user_display_name(user) -> str:
    return user.get_full_name() or user.username


def _annotate_history_rows(queryset):
    rows = []
    for sub in queryset.select_related("user", "plan"):
        computed = display_status(sub)
        rows.append(
            {
                "subscription": sub,
                "display_status": computed,
                "display_label": display_status_label(computed),
            }
        )
    return rows


def _balance_summary_row(user, balance: StudentSubscriptionBalance | None):
    if balance is None:
        return {
            "user": user,
            "balance": None,
            "display_status": StudentSubscription.DisplayStatus.EXPIRED,
            "display_label": display_status_label(
                StudentSubscription.DisplayStatus.EXPIRED
            ),
            "current_plan_title": "—",
            "remaining_minutes": 0,
            "expires_at": None,
        }

    display = balance_display_status(balance)
    return {
        "user": user,
        "balance": balance,
        "display_status": display,
        "display_label": display_status_label(display),
        "current_plan_title": balance.current_plan_title or "—",
        "remaining_minutes": balance.remaining_minutes,
        "expires_at": balance.expires_at,
    }


def _filter_summary_rows(rows, status_filter: str):
    if status_filter == FILTER_ALL:
        return rows
    return [r for r in rows if r["display_status"] == status_filter]


@login_required
@permissions_required("dashboard.access", "subscriptions.view")
def student_subscription_list(request):
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or FILTER_ALL).strip()

    if status_filter not in {
        FILTER_ALL,
        FILTER_ACTIVE,
        FILTER_EXPIRED,
        FILTER_CANCELLED,
    }:
        status_filter = FILTER_ALL

    users_qs = (
        User.objects.filter(
            user_type=USER_TYPE_STUDENT,
            student_subscriptions__isnull=False,
        )
        .distinct()
        .select_related("subscription_balance")
        .order_by("username")
    )

    if q:
        users_qs = users_qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(full_name__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(subscription_balance__current_plan_title__icontains=q)
        )

    rows = [
        _balance_summary_row(user, getattr(user, "subscription_balance", None))
        for user in users_qs[:500]
    ]
    rows = _filter_summary_rows(rows, status_filter)

    return render(
        request,
        "dashboard/pages/student_subscriptions/list.html",
        {
            "rows": rows,
            "q": q,
            "status_filter": status_filter,
            "filter_all": FILTER_ALL,
            "filter_active": FILTER_ACTIVE,
            "filter_expired": FILTER_EXPIRED,
            "filter_cancelled": FILTER_CANCELLED,
        },
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.view")
def student_subscription_detail(request, user_id):
    user = get_object_or_404(User, pk=user_id, user_type=USER_TYPE_STUDENT)
    balance = get_user_subscription_balance(user)
    summary = _balance_summary_row(user, balance)

    history_qs = StudentSubscription.objects.filter(user=user).order_by(
        "-created_at", "-id"
    )
    history_rows = _annotate_history_rows(history_qs)

    return render(
        request,
        "dashboard/pages/student_subscriptions/detail.html",
        {
            "user": user,
            "summary": summary,
            "history_rows": history_rows,
        },
    )


def _parse_date(value: str, label: str, errors: list) -> date | None:
    if not value:
        errors.append(f"الرجاء إدخال {label}.")
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{label} غير صالح.")
        return None


def _parse_subscription_form(post):
    """Return (data dict, errors list) from POST."""
    errors = []
    plan_title = (post.get("plan_title") or "").strip()
    duration_raw = (post.get("duration_months") or "").strip()
    amount_raw = (post.get("amount") or "").strip()
    start_raw = (post.get("start_date") or "").strip()
    end_raw = (post.get("end_date") or "").strip()
    status = (post.get("status") or "").strip()
    payment_status = (post.get("payment_status") or "").strip()
    payment_method = (post.get("payment_method") or "").strip()
    transaction_reference = (post.get("transaction_reference") or "").strip()
    notes = (post.get("notes") or "").strip()
    minutes_added_raw = (post.get("plan_minutes_added") or "0").strip()

    if not plan_title:
        errors.append("اسم الباقة مطلوب.")

    duration_months = None
    if not duration_raw:
        errors.append("مدة الاشتراك مطلوبة.")
    else:
        try:
            duration_months = int(duration_raw)
            if duration_months < 1:
                errors.append("مدة الاشتراك يجب أن تكون شهرًا واحدًا على الأقل.")
        except ValueError:
            errors.append("مدة الاشتراك يجب أن تكون رقمًا صحيحًا.")

    amount = None
    if not amount_raw:
        errors.append("المبلغ مطلوب.")
    else:
        try:
            amount = Decimal(amount_raw)
            if amount < 0:
                errors.append("المبلغ لا يمكن أن يكون سالبًا.")
        except InvalidOperation:
            errors.append("المبلغ غير صالح.")

    plan_minutes_added = 0
    try:
        plan_minutes_added = int(minutes_added_raw) if minutes_added_raw else 0
        if plan_minutes_added < 0:
            errors.append("الدقائق المضافة لا يمكن أن تكون سالبة.")
    except ValueError:
        errors.append("الدقائق المضافة يجب أن تكون رقمًا صحيحًا.")

    valid_status = {c[0] for c in StudentSubscription.Status.choices}
    if status not in valid_status:
        errors.append("حالة الاشتراك غير صالحة.")

    valid_payment = {c[0] for c in StudentSubscription.PaymentStatus.choices}
    if payment_status not in valid_payment:
        errors.append("حالة الدفع غير صالحة.")

    start_date = _parse_date(start_raw, "تاريخ البداية", errors)
    end_date = _parse_date(end_raw, "تاريخ النهاية", errors)
    if start_date and end_date and end_date < start_date:
        errors.append("تاريخ النهاية يجب أن يكون بعد تاريخ البداية.")

    data = {
        "plan_title": plan_title,
        "duration_months": duration_months,
        "amount": amount,
        "start_date": start_date,
        "end_date": end_date,
        "status": status,
        "payment_status": payment_status,
        "payment_method": payment_method,
        "transaction_reference": transaction_reference,
        "notes": notes,
        "plan_minutes_added": plan_minutes_added,
    }
    return data, errors


def _subscription_initial(sub: StudentSubscription) -> dict:
    return {
        "plan_title": sub.plan_title,
        "duration_months": str(sub.duration_months),
        "amount": str(sub.amount),
        "start_date": sub.start_date.isoformat(),
        "end_date": sub.end_date.isoformat(),
        "status": sub.status,
        "payment_status": sub.payment_status,
        "payment_method": sub.payment_method,
        "transaction_reference": sub.transaction_reference,
        "notes": sub.notes,
        "plan_minutes_added": str(sub.plan_minutes_added),
    }


@login_required
@permissions_required("dashboard.access", "subscriptions.update")
def student_subscription_update(request, pk):
    sub = get_object_or_404(
        StudentSubscription.objects.select_related("user", "plan"),
        pk=pk,
    )
    initial = _subscription_initial(sub)
    detail_url = "dashboard:student_subscription_detail"

    if request.method == "POST":
        data, errors = _parse_subscription_form(request.POST)
        initial = {
            **data,
            "duration_months": request.POST.get("duration_months", ""),
            "amount": request.POST.get("amount", ""),
            "start_date": request.POST.get("start_date", ""),
            "end_date": request.POST.get("end_date", ""),
            "plan_minutes_added": request.POST.get("plan_minutes_added", "0"),
        }

        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            sub.plan_title = data["plan_title"]
            sub.duration_months = data["duration_months"]
            sub.amount = data["amount"]
            sub.start_date = data["start_date"]
            sub.end_date = data["end_date"]
            sub.status = data["status"]
            sub.payment_status = data["payment_status"]
            sub.payment_method = data["payment_method"]
            sub.transaction_reference = data["transaction_reference"]
            sub.notes = data["notes"]
            sub.plan_minutes_added = data["plan_minutes_added"]
            sub.save()
            messages.success(request, "تم تحديث سجل الاشتراك بنجاح.")
            return redirect(detail_url, user_id=sub.user_id)

    return render(
        request,
        "dashboard/pages/student_subscriptions/form.html",
        {
            "title": "تعديل سجل اشتراك",
            "subscription": sub,
            "initial": initial,
            "status_choices": StudentSubscription.Status.choices,
            "payment_status_choices": StudentSubscription.PaymentStatus.choices,
            "cancel_url": detail_url,
            "cancel_user_id": sub.user_id,
        },
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.delete")
def student_subscription_delete(request, pk):
    sub = get_object_or_404(
        StudentSubscription.objects.select_related("user"),
        pk=pk,
    )
    user_id = sub.user_id
    detail_url = "dashboard:student_subscription_detail"

    if request.method == "POST":
        sub.delete()
        messages.success(request, "تم حذف سجل الاشتراك بنجاح.")
        return redirect(detail_url, user_id=user_id)

    return render(
        request,
        "dashboard/pages/student_subscriptions/confirm_delete.html",
        {
            "subscription": sub,
            "cancel_url": detail_url,
            "cancel_user_id": user_id,
        },
    )


def _parse_balance_form(post):
    errors = []
    plan_title = (post.get("current_plan_title") or "").strip()
    minutes_raw = (post.get("remaining_minutes") or "0").strip()
    used_raw = (post.get("used_minutes") or "0").strip()
    expires_raw = (post.get("expires_at") or "").strip()
    status = (post.get("status") or "").strip()

    remaining_minutes = 0
    try:
        remaining_minutes = int(minutes_raw)
        if remaining_minutes < 0:
            errors.append("الدقائق المتبقية لا يمكن أن تكون سالبة.")
    except ValueError:
        errors.append("الدقائق المتبقية يجب أن تكون رقمًا صحيحًا.")

    used_minutes = 0
    try:
        used_minutes = int(used_raw)
        if used_minutes < 0:
            errors.append("الدقائق المستخدمة لا يمكن أن تكون سالبة.")
    except ValueError:
        errors.append("الدقائق المستخدمة يجب أن تكون رقمًا صحيحًا.")

    expires_at = None
    if expires_raw:
        expires_at = _parse_date(expires_raw, "تاريخ الانتهاء", errors)

    valid_status = {c[0] for c in StudentSubscriptionBalance.Status.choices}
    if status not in valid_status:
        errors.append("حالة الاشتراك غير صالحة.")

    return {
        "current_plan_title": plan_title,
        "remaining_minutes": remaining_minutes,
        "used_minutes": used_minutes,
        "expires_at": expires_at,
        "status": status,
    }, errors


@login_required
@permissions_required("dashboard.access", "subscriptions.update")
def student_subscription_balance_update(request, user_id):
    user = get_object_or_404(User, pk=user_id, user_type=USER_TYPE_STUDENT)
    balance, _ = StudentSubscriptionBalance.objects.get_or_create(
        user=user,
        defaults={"status": StudentSubscriptionBalance.Status.EXPIRED},
    )
    initial = {
        "current_plan_title": balance.current_plan_title,
        "remaining_minutes": str(balance.remaining_minutes),
        "used_minutes": str(balance.used_minutes),
        "expires_at": balance.expires_at.isoformat() if balance.expires_at else "",
        "status": balance.status,
    }

    if request.method == "POST":
        data, errors = _parse_balance_form(request.POST)
        initial = {
            **data,
            "remaining_minutes": request.POST.get("remaining_minutes", "0"),
            "used_minutes": request.POST.get("used_minutes", "0"),
            "expires_at": request.POST.get("expires_at", ""),
        }

        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            balance.current_plan_title = data["current_plan_title"]
            balance.remaining_minutes = data["remaining_minutes"]
            balance.used_minutes = data["used_minutes"]
            balance.expires_at = data["expires_at"]
            balance.status = data["status"]
            balance.save()
            messages.success(request, "تم تحديث الاشتراك الحالي بنجاح.")
            return redirect("dashboard:student_subscription_detail", user_id=user.id)

    return render(
        request,
        "dashboard/pages/student_subscriptions/balance_form.html",
        {
            "user": user,
            "balance": balance,
            "initial": initial,
            "status_choices": StudentSubscriptionBalance.Status.choices,
        },
    )
