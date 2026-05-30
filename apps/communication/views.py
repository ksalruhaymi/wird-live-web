from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from django.contrib import messages

from identity.rbac.decorators import permission_required

from .models import (
    CommunicationCampaign,
    CommunicationCampaignChannel,
    CommunicationChannel,
)
from .services import send_telegram_message


@login_required
@permission_required("communication.access")
def overview(request):
    total_campaigns = CommunicationCampaign.objects.count()
    sent_campaigns = CommunicationCampaign.objects.filter(status="sent").count()
    draft_campaigns = CommunicationCampaign.objects.filter(status="draft").count()

    context = {
        "tab": "overview",
        "total_campaigns": total_campaigns,
        "sent_campaigns": sent_campaigns,
        "draft_campaigns": draft_campaigns,
    }
    return render(request, "communication/overview.html", context)


@login_required
@permission_required("communication.create")
def create_campaign(request):
    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        message = (request.POST.get("message") or "").strip()
        channels = request.POST.getlist("channels")
        image = request.FILES.get("image")

        campaign = CommunicationCampaign.objects.create(
            title=title,
            message=message,
            created_by=request.user,
            image=image if image else None,
        )

        for ch in channels:
            CommunicationCampaignChannel.objects.create(
                campaign=campaign,
                channel=ch,
            )

        messages.success(request, "تم إنشاء الحملة بنجاح.")
        return redirect("apps.communication:campaigns")

    context = {
        "tab": "create",
        "channels": CommunicationChannel.choices,
    }
    return render(request, "communication/create.html", context)


@login_required
@permission_required("communication.campaigns")
def campaigns(request):
    per_page = int(request.GET.get("per_page", 10))
    search = request.GET.get("campaigns", "").strip()

    qs = CommunicationCampaign.objects.all().order_by("-created_at")

    if search:
        qs = qs.filter(
            Q(title__icontains=search) |
            Q(message__icontains=search)
        )

    total_campaigns = qs.count()

    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page")
    campaigns_page = paginator.get_page(page_number)

    page_numbers = range(
        max(campaigns_page.number - 2, 1),
        min(campaigns_page.number + 3, paginator.num_pages + 1),
    )

    context = {
        "tab": "campaigns",
        "campaigns": campaigns_page,
        "total_campaigns": total_campaigns,
        "per_page": per_page,
        "campaigns_page_numbers": page_numbers,
    }
    return render(request, "communication/campaigns.html", context)


@login_required
@permission_required("communication.campaigns")
def send_campaign(request, pk):
    campaign = get_object_or_404(CommunicationCampaign, pk=pk)

    telegram_channels = campaign.channels.filter(
        channel__in=[
            CommunicationChannel.TELEGRAM_GROUP,
            CommunicationChannel.TELEGRAM_CHANNEL,
        ]
    )

    if not telegram_channels.exists():
        messages.error(request, "لا توجد قناة تيليجرام أو قروب مفعّل لهذه الحملة.")
        return redirect("apps.communication:campaigns")

    text = campaign.message
    image_path = campaign.image.path if campaign.image else None

    for ch in telegram_channels:
        if ch.send_status == ch.SendStatus.SENT:
            continue

        if ch.channel == CommunicationChannel.TELEGRAM_CHANNEL:
            ok, error = send_telegram_message(
                text=text,
                image_path=image_path,
                target="channel",
            )
        else:
            ok, error = send_telegram_message(
                text=text,
                image_path=image_path,
                target="group",
            )

        if ok:
            ch.send_status = ch.SendStatus.SENT
            ch.sent_at = timezone.now()
            ch.error_message = ""
        else:
            ch.send_status = ch.SendStatus.FAILED
            ch.error_message = error or "Unknown error"

        ch.save(update_fields=["send_status", "sent_at", "error_message"])

    if campaign.channels.filter(send_status=CommunicationCampaignChannel.SendStatus.FAILED).exists():
        campaign.status = CommunicationCampaign.Status.FAILED
    elif campaign.channels.filter(send_status=CommunicationCampaignChannel.SendStatus.PENDING).exists():
        campaign.status = CommunicationCampaign.Status.SENDING
    else:
        campaign.status = CommunicationCampaign.Status.SENT

    campaign.sent_at = timezone.now()
    campaign.save(update_fields=["status", "sent_at"])

    messages.success(request, "تم إرسال الحملة بنجاح.")
    return redirect("apps.communication:campaigns")


@login_required
@permission_required("communication.logs")
def logs(request):
    per_page = int(request.GET.get("per_page", 10))
    search = request.GET.get("logs", "").strip()

    qs = CommunicationCampaignChannel.objects.select_related("campaign").order_by(
        "-sent_at", "-campaign__created_at"
    )

    if search:
        qs = qs.filter(
            Q(campaign__title__icontains=search)
            | Q(channel__icontains=search)
            | Q(campaign__message__icontains=search)
        )

    total_logs = qs.count()

    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page")
    logs_page = paginator.get_page(page_number)

    page_numbers = range(
        max(logs_page.number - 2, 1),
        min(logs_page.number + 3, paginator.num_pages + 1),
    )

    context = {
        "tab": "logs",
        "logs": logs_page,
        "total_logs": total_logs,
        "per_page": per_page,
        "logs_page_numbers": page_numbers,
    }
    return render(request, "communication/logs.html", context)