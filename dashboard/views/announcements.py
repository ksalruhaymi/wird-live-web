from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.communication.models import Announcement
from identity.rbac.decorators import permissions_required


def _parse_announcement_form(post, files, *, instance: Announcement | None = None):
    errors = []
    is_active = post.get("is_active") == "on"
    image = files.get("image")

    is_create = instance is None
    has_existing_image = bool(instance and instance.image)

    if is_create and not image:
        errors.append("صورة الإعلان مطلوبة.")
    if not is_create and not image and not has_existing_image:
        errors.append("صورة الإعلان مطلوبة.")

    return {
        "is_active": is_active,
        "image": image,
    }, errors


def _apply_announcement(
    instance: Announcement,
    data: dict,
    *,
    is_create: bool,
) -> Announcement:
    instance.is_active = data["is_active"]
    if data["image"]:
        instance.image = data["image"]
    if is_create:
        instance.announcement_date = timezone.localdate()
    instance.save()
    return instance


@login_required
@permissions_required("dashboard.access", "announcements.view")
def announcement_list(request):
    qs = Announcement.objects.all().order_by("-created_at", "-id")
    return render(
        request,
        "dashboard/pages/announcements/list.html",
        {"announcements": qs},
    )


@login_required
@permissions_required("dashboard.access", "announcements.view")
def announcement_detail(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    return render(
        request,
        "dashboard/pages/announcements/detail.html",
        {"announcement": announcement},
    )


@login_required
@permissions_required("dashboard.access", "announcements.create")
def announcement_create(request):
    initial = {"is_active": True}

    if request.method == "POST":
        data, errors = _parse_announcement_form(request.POST, request.FILES)
        initial = {"is_active": data["is_active"]}
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            _apply_announcement(Announcement(), data, is_create=True)
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
        },
    )


@login_required
@permissions_required("dashboard.access", "announcements.update")
def announcement_update(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    initial = {"is_active": announcement.is_active}

    if request.method == "POST":
        data, errors = _parse_announcement_form(
            request.POST,
            request.FILES,
            instance=announcement,
        )
        initial = {"is_active": data["is_active"]}
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            _apply_announcement(announcement, data, is_create=False)
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
        messages.success(request, "تم تفعيل الإعلان.")
    else:
        messages.success(request, "تم تعطيل الإعلان.")
    return redirect("dashboard:announcement_list")
