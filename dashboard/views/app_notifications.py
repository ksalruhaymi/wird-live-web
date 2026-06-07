from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.notification.models import AppNotification, AppNotificationTargetType
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from identity.rbac.decorators import permissions_required


def _parse_app_notification_form(post):
    errors = []
    title = (post.get("title") or "").strip()
    body = (post.get("body") or "").strip()
    target_type = (post.get("target_type") or "").strip()
    is_active = post.get("is_active") == "on"

    if not title:
        errors.append("عنوان التنبيه مطلوب.")
    if not body:
        errors.append("نص التنبيه مطلوب.")

    valid_targets = {c[0] for c in AppNotificationTargetType.choices}
    if target_type not in valid_targets:
        target_type = AppNotificationTargetType.ALL

    return {
        "title": title,
        "body": body,
        "target_type": target_type,
        "is_active": is_active,
    }, errors


def _apply_app_notification(instance: AppNotification, data: dict) -> AppNotification:
    instance.title = data["title"]
    instance.body = data["body"]
    instance.target_type = data["target_type"]
    instance.is_active = data["is_active"]
    instance.save()
    return instance


@login_required
@permissions_required("dashboard.access", "app_notifications.view")
def app_notification_list(request):
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "all").strip()
    target_filter = (request.GET.get("target") or "all").strip()

    qs = AppNotification.objects.all().order_by("-created_at", "-id")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))

    if status_filter == "active":
        qs = qs.filter(is_active=True)
    elif status_filter == "inactive":
        qs = qs.filter(is_active=False)

    valid_targets = {c[0] for c in AppNotificationTargetType.choices}
    if target_filter in valid_targets:
        qs = qs.filter(target_type=target_filter)

    page_obj, page_numbers, per_page_param, total_notifications = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="5",
    )

    pagination_qs = build_pagination_query_string(
        q=q,
        status=status_filter,
        target=target_filter,
        per_page=per_page_param,
    )

    hidden_fields = []
    if q:
        hidden_fields.append({"name": "q", "value": q})
    if status_filter != "all":
        hidden_fields.append({"name": "status", "value": status_filter})
    if target_filter != "all":
        hidden_fields.append({"name": "target", "value": target_filter})
    return render(
        request,
        "dashboard/pages/app_notifications/list.html",
        {
            "notifications": page_obj.object_list,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_notifications": total_notifications,
            "q": q,
            "status_filter": status_filter,
            "target_filter": target_filter,
            "target_choices": AppNotificationTargetType.choices,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": hidden_fields,
        },
    )


@login_required
@permissions_required("dashboard.access", "app_notifications.view")
def app_notification_detail(request, pk):
    notification = get_object_or_404(AppNotification, pk=pk)
    return render(
        request,
        "dashboard/pages/app_notifications/detail.html",
        {"notification": notification},
    )


@login_required
@permissions_required("dashboard.access", "app_notifications.create")
def app_notification_create(request):
    initial = {
        "title": "",
        "body": "",
        "target_type": AppNotificationTargetType.ALL,
        "is_active": True,
    }

    if request.method == "POST":
        data, errors = _parse_app_notification_form(request.POST)
        initial = data
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            notification = AppNotification(created_by=request.user)
            _apply_app_notification(notification, data)
            messages.success(request, "تم إنشاء تنبيه التطبيق بنجاح.")
            return redirect("dashboard:app_notification_list")

    return render(
        request,
        "dashboard/pages/app_notifications/form.html",
        {
            "title": "إضافة تنبيه تطبيق",
            "mode": "create",
            "initial": initial,
            "notification": None,
            "target_type_choices": AppNotificationTargetType.choices,
        },
    )


@login_required
@permissions_required("dashboard.access", "app_notifications.update")
def app_notification_update(request, pk):
    notification = get_object_or_404(AppNotification, pk=pk)
    initial = {
        "title": notification.title,
        "body": notification.body,
        "target_type": notification.target_type,
        "is_active": notification.is_active,
    }

    if request.method == "POST":
        data, errors = _parse_app_notification_form(request.POST)
        initial = data
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            _apply_app_notification(notification, data)
            messages.success(request, "تم تحديث تنبيه التطبيق بنجاح.")
            return redirect("dashboard:app_notification_list")

    return render(
        request,
        "dashboard/pages/app_notifications/form.html",
        {
            "title": "تعديل تنبيه تطبيق",
            "mode": "edit",
            "initial": initial,
            "notification": notification,
            "target_type_choices": AppNotificationTargetType.choices,
        },
    )


@login_required
@permissions_required("dashboard.access", "app_notifications.delete")
def app_notification_delete(request, pk):
    notification = get_object_or_404(AppNotification, pk=pk)
    if request.method == "POST":
        notification.delete()
        messages.success(request, "تم حذف تنبيه التطبيق بنجاح.")
        return redirect("dashboard:app_notification_list")

    return render(
        request,
        "dashboard/pages/app_notifications/confirm_delete.html",
        {"notification": notification},
    )


@login_required
@permissions_required("dashboard.access", "app_notifications.update")
@require_POST
def app_notification_toggle_active(request, pk):
    notification = get_object_or_404(AppNotification, pk=pk)
    notification.is_active = not notification.is_active
    notification.save(update_fields=["is_active", "updated_at"])
    if notification.is_active:
        messages.success(request, "تم تفعيل التنبيه.")
    else:
        messages.success(request, "تم تعطيل التنبيه.")
    return redirect("dashboard:app_notification_list")
