from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.subscription.models import StudentSubscription
from apps.subscription.services import display_status, display_status_label
from identity.rbac.decorators import permissions_required

User = get_user_model()

FILTER_ALL = "all"
FILTER_ACTIVE = "active"
FILTER_EXPIRED = "expired"
FILTER_CANCELLED = "cancelled"


def _annotate_rows(queryset):
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


def _filter_rows(rows, status_filter: str):
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

    qs = StudentSubscription.objects.all().order_by("-created_at", "-id")

    if q:
        qs = qs.filter(
            Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
            | Q(user__full_name__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(plan_title__icontains=q)
            | Q(transaction_reference__icontains=q)
            | Q(id__icontains=q)
        )

    rows = _filter_rows(_annotate_rows(qs[:500]), status_filter)

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


def _parse_date(value: str, label: str, errors: list) -> datetime.date | None:
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
    }


@login_required
@permissions_required("dashboard.access", "subscriptions.update")
def student_subscription_update(request, pk):
    sub = get_object_or_404(
        StudentSubscription.objects.select_related("user", "plan"),
        pk=pk,
    )
    initial = _subscription_initial(sub)

    if request.method == "POST":
        data, errors = _parse_subscription_form(request.POST)
        initial = {
            **data,
            "duration_months": request.POST.get("duration_months", ""),
            "amount": request.POST.get("amount", ""),
            "start_date": request.POST.get("start_date", ""),
            "end_date": request.POST.get("end_date", ""),
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
            sub.save()
            messages.success(request, "تم تحديث سجل الاشتراك بنجاح.")
            return redirect("dashboard:student_subscription_list")

    return render(
        request,
        "dashboard/pages/student_subscriptions/form.html",
        {
            "title": "تعديل سجل اشتراك",
            "subscription": sub,
            "initial": initial,
            "status_choices": StudentSubscription.Status.choices,
            "payment_status_choices": StudentSubscription.PaymentStatus.choices,
        },
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.delete")
def student_subscription_delete(request, pk):
    sub = get_object_or_404(
        StudentSubscription.objects.select_related("user"),
        pk=pk,
    )

    if request.method == "POST":
        sub.delete()
        messages.success(request, "تم حذف سجل الاشتراك بنجاح.")
        return redirect("dashboard:student_subscription_list")

    return render(
        request,
        "dashboard/pages/student_subscriptions/confirm_delete.html",
        {"subscription": sub},
    )
