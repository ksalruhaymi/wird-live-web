from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.subscription.models import SubscriptionPlan
from identity.rbac.decorators import permissions_required


def _parse_plan_form(post):
    """Return (data dict, errors list) from POST."""
    errors = []
    title = (post.get("title") or "").strip()
    duration_raw = (post.get("duration_months") or "").strip()
    price_raw = (post.get("price") or "").strip()
    minutes_raw = (post.get("minutes") or "0").strip()
    description = (post.get("description") or "").strip()
    sort_raw = (post.get("sort_order") or "0").strip()
    is_active = post.get("is_active") == "on"

    if not title:
        errors.append("الرجاء إدخال اسم الباقة.")

    duration_months = None
    if not duration_raw:
        errors.append("الرجاء إدخال مدة الاشتراك بالأشهر.")
    else:
        try:
            duration_months = int(duration_raw)
            if duration_months < 1:
                errors.append("مدة الاشتراك يجب أن تكون شهرًا واحدًا على الأقل.")
        except ValueError:
            errors.append("مدة الاشتراك يجب أن تكون رقمًا صحيحًا.")

    price = None
    if not price_raw:
        errors.append("الرجاء إدخال المبلغ.")
    else:
        try:
            price = Decimal(price_raw)
            if price < 0:
                errors.append("المبلغ لا يمكن أن يكون سالبًا.")
        except InvalidOperation:
            errors.append("المبلغ غير صالح.")

    minutes = 0
    if not minutes_raw:
        errors.append("الرجاء إدخال دقائق الباقة.")
    else:
        try:
            minutes = int(minutes_raw)
            if minutes < 0:
                errors.append("دقائق الباقة لا يمكن أن تكون سالبة.")
        except ValueError:
            errors.append("دقائق الباقة يجب أن تكون رقمًا صحيحًا.")

    sort_order = 0
    try:
        sort_order = int(sort_raw) if sort_raw else 0
        if sort_order < 0:
            errors.append("ترتيب العرض لا يمكن أن يكون سالبًا.")
    except ValueError:
        errors.append("ترتيب العرض يجب أن يكون رقمًا صحيحًا.")

    data = {
        "title": title,
        "duration_months": duration_months,
        "price": price,
        "minutes": minutes,
        "description": description,
        "sort_order": sort_order,
        "is_active": is_active,
    }
    return data, errors


@login_required
@permissions_required("dashboard.access", "subscriptions.view")
def subscription_plan_list(request):
    plans = SubscriptionPlan.objects.all().order_by("sort_order", "id")
    return render(
        request,
        "dashboard/pages/subscription_plans/list.html",
        {"plans": plans},
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.create")
def subscription_plan_create(request):
    initial = {
        "title": "",
        "duration_months": "",
        "price": "",
        "minutes": "0",
        "description": "",
        "sort_order": "0",
        "is_active": True,
    }

    if request.method == "POST":
        data, errors = _parse_plan_form(request.POST)
        initial = {**data, "duration_months": request.POST.get("duration_months", "")}
        initial["price"] = request.POST.get("price", "")
        initial["minutes"] = request.POST.get("minutes", "0")
        initial["description"] = request.POST.get("description", "")
        initial["sort_order"] = request.POST.get("sort_order", "0")

        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            SubscriptionPlan.objects.create(
                title=data["title"],
                duration_months=data["duration_months"],
                price=data["price"],
                minutes=data["minutes"],
                description=data["description"],
                sort_order=data["sort_order"],
                is_active=data["is_active"],
            )
            messages.success(request, "تم إنشاء الباقة بنجاح.")
            return redirect("dashboard:subscription_plan_list")

    return render(
        request,
        "dashboard/pages/subscription_plans/form.html",
        {
            "title": "إضافة باقة اشتراك",
            "mode": "create",
            "initial": initial,
            "plan": None,
        },
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.update")
def subscription_plan_update(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    initial = {
        "title": plan.title,
        "duration_months": str(plan.duration_months),
        "price": str(plan.price),
        "minutes": str(plan.minutes),
        "description": plan.description,
        "sort_order": str(plan.sort_order),
        "is_active": plan.is_active,
    }

    if request.method == "POST":
        data, errors = _parse_plan_form(request.POST)
        initial = {**data, "duration_months": request.POST.get("duration_months", "")}
        initial["price"] = request.POST.get("price", "")
        initial["minutes"] = request.POST.get("minutes", "0")
        initial["description"] = request.POST.get("description", "")
        initial["sort_order"] = request.POST.get("sort_order", "0")

        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            plan.title = data["title"]
            plan.duration_months = data["duration_months"]
            plan.price = data["price"]
            plan.minutes = data["minutes"]
            plan.description = data["description"]
            plan.sort_order = data["sort_order"]
            plan.is_active = data["is_active"]
            plan.save()
            messages.success(request, "تم تحديث الباقة بنجاح.")
            return redirect("dashboard:subscription_plan_list")

    return render(
        request,
        "dashboard/pages/subscription_plans/form.html",
        {
            "title": "تعديل باقة اشتراك",
            "mode": "edit",
            "initial": initial,
            "plan": plan,
        },
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.delete")
def subscription_plan_delete(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)

    if request.method == "POST":
        plan.delete()
        messages.success(request, "تم حذف الباقة بنجاح.")
        return redirect("dashboard:subscription_plan_list")

    return render(
        request,
        "dashboard/pages/subscription_plans/confirm_delete.html",
        {"plan": plan},
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.update")
@require_POST
def subscription_plan_toggle_active(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    plan.is_active = not plan.is_active
    plan.save(update_fields=["is_active", "updated_at"])
    if plan.is_active:
        messages.success(request, f"تم تفعيل «{plan.title}».")
    else:
        messages.success(request, f"تم تعطيل «{plan.title}».")
    return redirect("dashboard:subscription_plan_list")
