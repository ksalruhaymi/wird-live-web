from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from apps.notification.models import Notification
from identity.rbac.decorators import permission_required
from .tasks import send_broadcast_emails

from .models import (
    MessageBroadcast,
    MessageChannel,
    MessageDelivery,
    DeliveryStatus,
)


User = get_user_model()



@permission_required("messaging.access")
@login_required
def overview_messaging(request):
    messages_list = (
        MessageBroadcast.objects.select_related("created_by").order_by("-created_at")[:10]
    )

    stats = {
        "email": MessageBroadcast.objects.filter(channel=MessageChannel.EMAIL).count(),
        "sms": MessageBroadcast.objects.filter(channel=MessageChannel.SMS).count(),
        "whatsapp": MessageBroadcast.objects.filter(channel=MessageChannel.WHATSAPP).count(),
    }

    return render(
        request,
        "messaging/overview/messaging_overview.html",
        {
            "tab": "overview_messaging",
            "messages_list": messages_list,
            "stats": stats,
        },
    )


@permission_required("messaging.create")
@login_required
def messaging_create(request):
    tab = "create"

    if request.method == "GET":
        users = User.objects.filter(
            is_active=True,
            is_superuser=False,
        ).order_by("username")

        return render(
            request,
            "messaging/create/messaging_create.html",
            {
                "tab": tab,
                "users": users,
            },
        )

    title = (request.POST.get("title") or "").strip()
    message_text = (request.POST.get("body") or request.POST.get("message") or "").strip()
    channel = (request.POST.get("channel") or MessageChannel.IN_APP).strip()
    target_type = (request.POST.get("target_type") or "all").strip()
    recipient_ids = request.POST.getlist("recipients")

    if not title or not message_text:
        messages.error(request, "يجب إدخال العنوان ونص الرسالة.")
        return redirect("apps.messaging:messaging_create")

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
        messages.error(request, "لا يوجد مستلمون مطابقون للمعايير المحددة.")
        return redirect("apps.messaging:messaging_create")

    if channel == MessageChannel.EMAIL:
        recipients_with_email = [user for user in recipients if (user.email or "").strip()]

        if not recipients_with_email:
            messages.error(request, "لا يوجد مستلمون لديهم بريد إلكتروني.")
            return redirect("apps.messaging:messaging_create")

        broadcast = MessageBroadcast.objects.create(
            title=title,
            body=message_text,
            channel=MessageChannel.EMAIL,
            created_by=request.user,
        )

        MessageDelivery.objects.bulk_create(
            [
                MessageDelivery(
                    broadcast=broadcast,
                    user=user,
                    email=user.email.strip(),
                    status=DeliveryStatus.PENDING,
                )
                for user in recipients_with_email
            ]
        )

        messages.success(request, "تم إنشاء الرسالة البريدية وهي بانتظار الإرسال.")
        return redirect("apps.messaging:email")

    notifications = [
        Notification(
            user=user,
            title=title,
            message=message_text,
            channel=MessageChannel.IN_APP,
        )
        for user in recipients
    ]
    Notification.objects.bulk_create(notifications)

    messages.success(request, "تم إرسال التنبيه داخل النظام بنجاح.")
    return redirect("apps.messaging:messaging_create")


@permission_required("messaging.email")
@login_required
def email(request):
    deliveries_prefetch = Prefetch(
    "deliveries",
    queryset=MessageDelivery.objects.select_related("user").order_by("id"),
    to_attr="deliveries_list",
    )

    broadcasts_qs = (
        MessageBroadcast.objects.select_related("created_by")
        .prefetch_related(deliveries_prefetch)
        .filter(channel=MessageChannel.EMAIL)
        .annotate(recipients_count=Count("deliveries"))
        .order_by("-created_at", "-id")
    )
    paginator = Paginator(broadcasts_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for broadcast in page_obj:
        deliveries = getattr(broadcast, "deliveries_list", [])
        broadcast.recipient_emails = [d.email for d in deliveries if (d.email or "").strip()]
        broadcast.is_bulk = broadcast.recipients_count > 1
        broadcast.has_pending = any(d.status == DeliveryStatus.PENDING for d in deliveries)
        broadcast.has_sent = any(d.status == DeliveryStatus.SENT for d in deliveries)
        broadcast.has_failed = any(d.status == DeliveryStatus.FAILED for d in deliveries)

    return render(
        request,
        "messaging/email/email.html",
        {
            "tab": "email",
            "emails": page_obj,
            "page_obj": page_obj,
            "total_messages": paginator.count,
            "per_page": 10,
            "messages_page_numbers": range(
                max(page_obj.number - 2, 1),
                min(page_obj.number + 3, paginator.num_pages + 1),
            ),
        },
    )


@permission_required("messaging.email")
@login_required
def email_detail(request, pk):
    broadcast = get_object_or_404(
    MessageBroadcast.objects.select_related("created_by").prefetch_related(
        Prefetch(
            "deliveries",
            queryset=MessageDelivery.objects.select_related("user").order_by("id"),
            to_attr="deliveries_list",
        )
    ),
    pk=pk,
    channel=MessageChannel.EMAIL,
)

    deliveries = getattr(broadcast, "deliveries_list", [])
    broadcast.recipient_emails = [d.email for d in deliveries if (d.email or "").strip()]
    broadcast.recipients_count = len(broadcast.recipient_emails)
    broadcast.is_bulk = broadcast.recipients_count > 1
    broadcast.has_pending = any(d.status == DeliveryStatus.PENDING for d in deliveries)
    broadcast.has_sent = any(d.status == DeliveryStatus.SENT for d in deliveries)
    broadcast.has_failed = any(d.status == DeliveryStatus.FAILED for d in deliveries)

    return render(
        request,
        "messaging/email/email_detail.html",
        {
            "tab": "email",
            "broadcast": broadcast,
            "deliveries": deliveries,
        },
    )


@permission_required("messaging.email")
@login_required
def send_email_broadcast(request, pk):
    if request.method != "POST":
        return redirect("apps.messaging:email")

    broadcast = get_object_or_404(
        MessageBroadcast,
        pk=pk,
        channel=MessageChannel.EMAIL,
    )

    has_pending = MessageDelivery.objects.filter(
        broadcast=broadcast,
        status=DeliveryStatus.PENDING,
    ).exists()

    if not has_pending:
        messages.info(request, "لا يوجد مستلمون بانتظار الإرسال.")
        return redirect("apps.messaging:email_detail", pk=pk)

    send_broadcast_emails(broadcast.id)

    messages.success(request, "تم إرسال الرسالة البريدية.")
    return redirect("apps.messaging:email_detail", pk=pk)

@permission_required("messaging.whatsapp")
@login_required
def whatsapp_list(request):
    deliveries_qs = (
        MessageDelivery.objects.select_related("broadcast", "broadcast__created_by", "user")
        .filter(broadcast__channel=MessageChannel.WHATSAPP)
        .order_by("-sent_at", "-delivered_at", "-id")
    )

    paginator = Paginator(deliveries_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "messaging/whatsapp/whatsapp_list.html",
        {
            "tab": "whatsapp",
            whatsapp_list: page_obj,
            "page_obj": page_obj,
            "total_whatsapp_list": paginator.count,
        },
    )


@permission_required("messaging.whatsapp")
@login_required
def whatsapp_detail(request, pk):
    delivery = get_object_or_404(
        MessageDelivery.objects.select_related("broadcast", "broadcast__created_by", "user"),
        pk=pk,
        broadcast__channel=MessageChannel.WHATSAPP,
    )

    return render(
        request,
        "messaging/whatsapp/whatsapp_detail.html",
        {
            "tab": "whatsapp",
            "delivery": delivery,
        },
    )


@permission_required("messaging.sms")
@login_required
def sms_list(request):
    deliveries_qs = (
        MessageDelivery.objects.select_related("broadcast", "broadcast__created_by", "user")
        .filter(broadcast__channel=MessageChannel.SMS)
        .order_by("-sent_at", "-delivered_at", "-id")
    )

    paginator = Paginator(deliveries_qs, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "messaging/sms/sms_list.html",
        {
            "tab": "sms",
            "sms_list": page_obj,
            "page_obj": page_obj,
            "total_messaging_sms": paginator.count,
        },
    )


@permission_required("messaging.sms")
@login_required
def sms_detail(request, pk):
    delivery = get_object_or_404(
        MessageDelivery.objects.select_related("broadcast", "broadcast__created_by", "user"),
        pk=pk,
        broadcast__channel=MessageChannel.SMS,
    )

    return render(
        request,
        "messaging/sms/sms_detail.html",
        {
            "tab": "sms",
            "delivery": delivery,
        },
    )


@login_required
@permission_required("messaging.manage_newsletter")
def general_email(request):
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        body = (request.POST.get("body") or "").strip()
        include_all_users = "include_all_users" in request.POST

        if not title or not body:
            messages.error(request, "العنوان ونص الرسالة مطلوبان.")
            return redirect("apps.messaging:general_email")

        newsletter_emails = list(
            NewsletterSubscriber.objects.filter(is_active=True).values_list("email", flat=True)
        )

        users_by_email = {}
        user_emails = []

        if include_all_users:
            user_qs = User.objects.filter(is_active=True).exclude(email__isnull=True).exclude(email="")
            user_emails = list(user_qs.values_list("email", flat=True))
            users_by_email = {u.email: u for u in user_qs}

        recipients = sorted(
            {
                (email or "").strip()
                for email in (newsletter_emails + user_emails)
                if (email or "").strip()
            }
        )

        if not recipients:
            messages.warning(request, "لا يوجد مستلمون لإرسال الرسالة.")
            return redirect("apps.messaging:general_email")

        broadcast = MessageBroadcast.objects.create(
            title=title,
            body=body,
            channel=MessageChannel.EMAIL,
            created_by=request.user,
        )

        MessageDelivery.objects.bulk_create(
            [
                MessageDelivery(
                    broadcast=broadcast,
                    user=users_by_email.get(email),
                    email=email,
                    status=DeliveryStatus.PENDING,
                )
                for email in recipients
            ]
        )

        messages.success(request, "تم إنشاء الرسالة البريدية وهي بانتظار الإرسال.")
        return redirect("apps.messaging:email")

    return render(request, "messaging/general/general_email.html", {"tab": "newsletter"})


@login_required
@permission_required("messaging.create")
def messaging_deliveries(request):
    deliveries = (
        MessageDelivery.objects.select_related("broadcast", "user")
        .order_by("-id")
    )

    return render(
        request,
        "messaging/deliveries/deliveries_list.html",
        {
            "tab": "deliveries",
            "deliveries": deliveries,
        },
    )