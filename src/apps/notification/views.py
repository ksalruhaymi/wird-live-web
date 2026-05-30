from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from .models import Notification, NotificationChannel
from identity.rbac.decorators import permission_required
from .models import Notification

User = get_user_model()


@permission_required("notification.create")
@login_required
def notification_create(request):
    tab = "center"

    if request.method == "GET":
        users = User.objects.filter(
            is_active=True,
            is_superuser=False,
        ).order_by("username")

        return render(
            request,
            "notification/create/notification_create.html",
            {
                "tab": tab,
                "users": users,
            },
        )

    title = (request.POST.get("title") or "").strip()
    message_text = (request.POST.get("body") or request.POST.get("message") or "").strip()
    target_type = (request.POST.get("target_type") or "all").strip()
    recipient_ids = request.POST.getlist("recipients")

    if not title or not message_text:
        messages.error(request, "يجب إدخال العنوان ونص الرسالة.")
        return redirect("apps.notification:notification_create")

    base_qs = User.objects.filter(
        is_active=True,
        is_superuser=False,
    ).order_by("username")

    if target_type == "selected":
        recipients_qs = base_qs.filter(id__in=recipient_ids)
    else:
        recipients_qs = base_qs

    recipients = list(recipients_qs)

    if not recipients:
        messages.error(request, "لا يوجد مستلمون مطابقون.")
        return redirect("apps.notification:notification_create")

    notifications = [
    Notification(
        user=user,
        title=title,
        message=message_text,
        channel=NotificationChannel.IN_APP,
    )
    for user in recipients
]
    Notification.objects.bulk_create(notifications)

    messages.success(request, "تم الإرسال بنجاح.")
    return redirect("apps.notification:notification_create")


@login_required
def my_notifications(request):
    notifications = (
        Notification.objects
        .filter(user=request.user)
        .order_by("-created_at")[:10]
    )

    unread_ids = list(
        Notification.objects
        .filter(user=request.user, is_read=False)
        .values_list("id", flat=True)
    )

    if unread_ids:
        Notification.objects.filter(id__in=unread_ids).update(is_read=True)

    return render(
        request,
        "dashboard/notification_inapp.html",
        {
            "notification": notifications,
            "unread_ids": unread_ids,
        },
    )


@login_required
def notifications_inbox(request):
    user = request.user

    unread_ids = list(
        Notification.objects.filter(
            user=user,
            is_read=False,
        ).values_list("id", flat=True)
    )

    if unread_ids:
        Notification.objects.filter(id__in=unread_ids).update(is_read=True)

    notifications = (
        Notification.objects
        .filter(user=user)
        .order_by("-created_at")[:10]
    )

    return render(
        request,
        "notification/inbox/notification_inbox.html",
        {
            "notification": notifications,
            "unread_ids": unread_ids,
        },
    )


@permission_required("notification.access")
@login_required
def overview_notifications(request):
    latest_notifications = (
        Notification.objects
        .select_related("user")
        .order_by("-created_at")[:10]
    )

    stats = {
        "total": Notification.objects.count(),
        "unread": Notification.objects.filter(is_read=False).count(),
        "read": Notification.objects.filter(is_read=True).count(),
    }

    return render(
        request,
        "notification/overview/notification_overview.html",
        {
            "tab": "overview_notifications",
            "notifications": latest_notifications,
            "stats": stats,
        },
    )


@permission_required("notification.inapp")
@login_required
def notifications_inapp(request):
    tab = "notifications_inapp"

    notifications_qs = (
        Notification.objects
        .select_related("user")
        .order_by("-created_at")
    )

    paginator = Paginator(notifications_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "notification/inapp/notification_inapp.html",
        {
            "tab": tab,
            "notification": page_obj,
            "page_obj": page_obj,
            "total_notifications": paginator.count,
        },
    )


@permission_required("notification.inapp")
@login_required
def notification_detail(request, pk):
    tab = "notifications_inapp"

    notification = get_object_or_404(
        Notification.objects.select_related("user"),
        pk=pk,
    )

    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    return render(
        request,
        "notification/inapp/notification_detail.html",
        {
            "tab": tab,
            "message": notification,
        },
    )