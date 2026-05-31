from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.communication.announcement_services import deactivate_other_announcements
from apps.communication.models import Announcement
from identity.rbac.decorators import permissions_required


def _choice_context():
    return {
        "type_choices": Announcement.AnnouncementType.choices,
        "announced_by_choices": Announcement.AnnouncedBy.choices,
        "target_type_choices": Announcement.TargetType.choices,
    }


def _parse_announcement_form(post):
    errors = []
    title = (post.get("title") or "").strip()
    message = (post.get("message") or "").strip()
    announcement_type = (post.get("announcement_type") or "").strip()
    announced_by = (post.get("announced_by") or "").strip()
    target_type = (post.get("target_type") or "").strip()
    target_group = (post.get("target_group") or "").strip()
    date_raw = (post.get("announcement_date") or "").strip()
    is_active = post.get("is_active") == "on"

    if not message:
        errors.append("نص الإعلان مطلوب.")

    valid_types = {c[0] for c in Announcement.AnnouncementType.choices}
    if announcement_type not in valid_types:
        errors.append("نوع الإعلان غير صالح.")

    valid_announcers = {c[0] for c in Announcement.AnnouncedBy.choices}
    if announced_by not in valid_announcers:
        errors.append("حقل «من الإعلان» غير صالح.")

    valid_targets = {c[0] for c in Announcement.TargetType.choices}
    if target_type not in valid_targets:
        errors.append("حقل «لمن الإعلان» غير صالح.")

    announcement_date = None
    if not date_raw:
        errors.append("تاريخ الإعلان مطلوب.")
    else:
        try:
            announcement_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append("تاريخ الإعلان غير صالح.")

    data = {
        "title": title,
        "message": message,
        "announcement_type": announcement_type,
        "announced_by": announced_by,
        "target_type": target_type,
        "target_group": target_group,
        "announcement_date": announcement_date,
        "is_active": is_active,
    }
    return data, errors


def _apply_announcement(instance: Announcement, data: dict) -> Announcement:
    instance.title = data["title"]
    instance.message = data["message"]
    instance.announcement_type = data["announcement_type"]
    instance.announced_by = data["announced_by"]
    instance.target_type = data["target_type"]
    instance.target_group = data["target_group"]
    instance.announcement_date = data["announcement_date"]
    instance.is_active = data["is_active"]
    instance.save()
    if instance.is_active:
        deactivate_other_announcements(exclude_pk=instance.pk)
    return instance


@login_required
@permissions_required("dashboard.access", "announcements.view")
def announcement_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = Announcement.objects.all().order_by("-created_at", "-id")
    if q:
        qs = qs.filter(
            Q(message__icontains=q)
            | Q(title__icontains=q)
            | Q(announcement_type__icontains=q)
            | Q(announced_by__icontains=q)
            | Q(target_type__icontains=q)
            | Q(target_group__icontains=q)
        )
    return render(
        request,
        "dashboard/pages/announcements/list.html",
        {"announcements": qs, "q": q},
    )


@login_required
@permissions_required("dashboard.access", "announcements.create")
def announcement_create(request):
    today = timezone.localdate().isoformat()
    initial = {
        "title": "",
        "message": "",
        "announcement_type": Announcement.AnnouncementType.INFO,
        "announced_by": Announcement.AnnouncedBy.ADMIN,
        "target_type": Announcement.TargetType.ALL,
        "target_group": "",
        "announcement_date": today,
        "is_active": True,
    }

    if request.method == "POST":
        data, errors = _parse_announcement_form(request.POST)
        initial = {**data, "announcement_date": request.POST.get("announcement_date", today)}
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            ann = _apply_announcement(Announcement(), data)
            messages.success(request, "تم إنشاء الإعلان بنجاح.")
            return redirect("dashboard:announcement_list")

    return render(
        request,
        "dashboard/pages/announcements/form.html",
        {
            "title": "إضافة إعلان",
            "mode": "create",
            "initial": initial,
            "announcement": None,
            **_choice_context(),
        },
    )


@login_required
@permissions_required("dashboard.access", "announcements.update")
def announcement_update(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    initial = {
        "title": announcement.title,
        "message": announcement.message,
        "announcement_type": announcement.announcement_type,
        "announced_by": announcement.announced_by,
        "target_type": announcement.target_type,
        "target_group": announcement.target_group,
        "announcement_date": announcement.announcement_date.isoformat(),
        "is_active": announcement.is_active,
    }

    if request.method == "POST":
        data, errors = _parse_announcement_form(request.POST)
        initial = {**data, "announcement_date": request.POST.get("announcement_date", "")}
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            _apply_announcement(announcement, data)
            messages.success(request, "تم تحديث الإعلان بنجاح.")
            return redirect("dashboard:announcement_list")

    return render(
        request,
        "dashboard/pages/announcements/form.html",
        {
            "title": "تعديل إعلان",
            "mode": "edit",
            "initial": initial,
            "announcement": announcement,
            **_choice_context(),
        },
    )


@login_required
@permissions_required("dashboard.access", "announcements.delete")
def announcement_delete(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == "POST":
        announcement.delete()
        messages.success(request, "تم حذف الإعلان بنجاح.")
        return redirect("dashboard:announcement_list")

    return render(
        request,
        "dashboard/pages/announcements/confirm_delete.html",
        {"announcement": announcement},
    )


@login_required
@permissions_required("dashboard.access", "announcements.update")
@require_POST
def announcement_toggle_active(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    announcement.is_active = not announcement.is_active
    announcement.save(update_fields=["is_active", "updated_at"])
    if announcement.is_active:
        deactivate_other_announcements(exclude_pk=announcement.pk)
        messages.success(request, "تم تفعيل الإعلان (ويظهر في التطبيق).")
    else:
        messages.success(request, "تم تعطيل الإعلان.")
    return redirect("dashboard:announcement_list")
