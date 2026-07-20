from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from apps.mobile.models import (
    BlockedMobileAppVersion,
    MobileAppConfig,
    MobileAppVersion,
    MobilePlatform,
    UpdateMode,
)
from apps.mobile.version_services import (
    activate_mobile_app_version,
    deactivate_mobile_app_version,
    is_valid_version_name,
)
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from identity.rbac.decorators import permissions_required

VALID_PLATFORMS = {MobilePlatform.ANDROID, MobilePlatform.IOS}
VALID_UPDATE_MODES = {UpdateMode.NONE, UpdateMode.OPTIONAL, UpdateMode.REQUIRED}


def _parse_optional_int(raw, *, field_label, errors, minimum=None):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        errors.append(f"{field_label} يجب أن يكون عدداً صحيحاً.")
        return None
    if minimum is not None and value < minimum:
        errors.append(f"{field_label} يجب أن يكون {minimum} أو أكثر.")
        return None
    return value


def _parse_starts_at(raw, errors):
    raw = (raw or "").strip()
    if not raw:
        return None
    value = parse_datetime(raw)
    if value is None:
        errors.append("تاريخ بدء التطبيق غير صالح.")
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _parse_mobile_version_form(post, *, existing: MobileAppVersion | None = None):
    errors = []
    simplified = (post.get("simplified_form") or "").strip() == "1"

    platform = (post.get("platform") or "").strip().lower()
    if platform not in VALID_PLATFORMS:
        errors.append("المنصة غير صالحة.")

    # Checkbox: present+on → enabled; absent → disabled.
    platform_app_enabled = post.get("platform_app_enabled") == "on"

    version_name = (post.get("version_name") or "").strip()
    if not is_valid_version_name(version_name):
        errors.append("رقم الإصدار غير صالح. مثال: 1.2.3")

    build_number = _parse_optional_int(
        post.get("build_number"), field_label="رقم البناء", errors=errors, minimum=1
    )
    if build_number is None and not (post.get("build_number") or "").strip():
        errors.append("رقم البناء مطلوب.")

    if simplified:
        minimum_version_name = (
            existing.minimum_version_name if existing is not None else ""
        )
        minimum_build_number = _parse_optional_int(
            post.get("minimum_build_number"),
            field_label="أقل رقم بناء مسموح",
            errors=errors,
            minimum=1,
        )
        if minimum_build_number is None and not (
            post.get("minimum_build_number") or ""
        ).strip():
            # Default: same as this release build when omitted.
            minimum_build_number = build_number

        force_update = post.get("force_update") == "on"
        update_mode = UpdateMode.REQUIRED if force_update else UpdateMode.NONE

        update_title_ar = existing.update_title_ar if existing is not None else ""
        update_title_en = existing.update_title_en if existing is not None else ""
        update_message_ar = (post.get("update_message_ar") or "").strip()
        update_message_en = (post.get("update_message_en") or "").strip()
        release_notes_ar = (post.get("release_notes_ar") or "").strip()
        release_notes_en = (post.get("release_notes_en") or "").strip()
        store_url = (post.get("store_url") or "").strip()
        allow_later = False
        later_reminder_hours = None
        starts_at = existing.starts_at if existing is not None else None
        starts_at_raw = (
            timezone.localtime(existing.starts_at).strftime("%Y-%m-%dT%H:%M")
            if existing is not None and existing.starts_at
            else ""
        )
        is_active = post.get("is_active") == "on"
    else:
        minimum_version_name = (post.get("minimum_version_name") or "").strip()

        minimum_build_number = _parse_optional_int(
            post.get("minimum_build_number"),
            field_label="أقل رقم بناء مدعوم",
            errors=errors,
            minimum=1,
        )

        update_mode = (post.get("update_mode") or "").strip().lower()
        if update_mode not in VALID_UPDATE_MODES:
            errors.append("نوع التحديث غير صالح.")

        allow_later = post.get("allow_later") == "on"
        later_reminder_hours = _parse_optional_int(
            post.get("later_reminder_hours"),
            field_label="ساعات إعادة التذكير",
            errors=errors,
            minimum=1,
        )

        if update_mode == UpdateMode.REQUIRED:
            allow_later = False
            later_reminder_hours = None
        elif update_mode == UpdateMode.NONE:
            allow_later = False
            later_reminder_hours = None
        elif not allow_later:
            later_reminder_hours = None

        store_url = (post.get("store_url") or "").strip()
        starts_at = _parse_starts_at(post.get("starts_at"), errors)
        starts_at_raw = (post.get("starts_at") or "").strip()
        is_active = post.get("is_active") == "on"
        update_title_ar = (post.get("update_title_ar") or "").strip()
        update_title_en = (post.get("update_title_en") or "").strip()
        update_message_ar = (post.get("update_message_ar") or "").strip()
        update_message_en = (post.get("update_message_en") or "").strip()
        release_notes_ar = (post.get("release_notes_ar") or "").strip()
        release_notes_en = (post.get("release_notes_en") or "").strip()

    if (
        minimum_build_number is not None
        and build_number is not None
        and minimum_build_number > build_number
    ):
        errors.append("أقل رقم بناء لا يمكن أن يكون أكبر من رقم البناء.")

    data = {
        "platform": platform,
        "version_name": version_name,
        "build_number": build_number,
        "minimum_version_name": minimum_version_name,
        "minimum_build_number": minimum_build_number,
        "update_mode": update_mode,
        "update_title_ar": update_title_ar,
        "update_title_en": update_title_en,
        "update_message_ar": update_message_ar,
        "update_message_en": update_message_en,
        "release_notes_ar": release_notes_ar,
        "release_notes_en": release_notes_en,
        "store_url": store_url,
        "allow_later": allow_later,
        "later_reminder_hours": later_reminder_hours,
        "starts_at": starts_at,
        "starts_at_raw": starts_at_raw,
        "is_active": is_active,
        "force_update": update_mode == UpdateMode.REQUIRED,
        "platform_app_enabled": platform_app_enabled,
    }
    return data, errors


def _apply_mobile_version(instance: MobileAppVersion, data: dict) -> MobileAppVersion:
    instance.platform = data["platform"]
    instance.version_name = data["version_name"]
    instance.build_number = data["build_number"]
    instance.minimum_version_name = data["minimum_version_name"]
    instance.minimum_build_number = data["minimum_build_number"]
    instance.update_mode = data["update_mode"]
    instance.update_title_ar = data["update_title_ar"]
    instance.update_title_en = data["update_title_en"]
    instance.update_message_ar = data["update_message_ar"]
    instance.update_message_en = data["update_message_en"]
    instance.release_notes_ar = data["release_notes_ar"]
    instance.release_notes_en = data["release_notes_en"]
    instance.store_url = data["store_url"]
    instance.allow_later = data["allow_later"]
    instance.later_reminder_hours = data["later_reminder_hours"]
    instance.starts_at = data["starts_at"]
    instance.save()
    return instance


def _apply_platform_app_enabled(platform: str, enabled: bool) -> None:
    config = MobileAppConfig.get_settings()
    config.set_enabled_for_platform(platform, enabled)


def _platform_app_enabled_initial(platform: str) -> bool:
    config = MobileAppConfig.get_settings()
    return config.is_enabled_for_platform(platform)


@login_required
@permissions_required("dashboard.access", "mobile_versions.view")
def mobile_version_list(request):
    platform_filter = (request.GET.get("platform") or "all").strip()

    qs = MobileAppVersion.objects.all().order_by("-created_at", "-id")
    if platform_filter in VALID_PLATFORMS:
        qs = qs.filter(platform=platform_filter)

    page_obj, page_numbers, per_page_param, total_versions = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="10",
    )

    pagination_qs = build_pagination_query_string(
        platform=platform_filter,
        per_page=per_page_param,
    )

    hidden_fields = []
    if platform_filter != "all":
        hidden_fields.append({"name": "platform", "value": platform_filter})

    active_android = (
        MobileAppVersion.objects.filter(
            platform=MobilePlatform.ANDROID, is_active=True
        )
        .order_by("-activated_at", "-id")
        .first()
    )
    active_ios = (
        MobileAppVersion.objects.filter(platform=MobilePlatform.IOS, is_active=True)
        .order_by("-activated_at", "-id")
        .first()
    )

    return render(
        request,
        "dashboard/pages/mobile_versions/list.html",
        {
            "can_manage_mobile_versions": request.user.has_permission(
                "mobile_versions.manage"
            ),
            "active_android": active_android,
            "active_ios": active_ios,
            "versions": page_obj.object_list,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_versions": total_versions,
            "platform_filter": platform_filter,
            "platform_choices": MobilePlatform.choices,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": hidden_fields,
        },
    )


@login_required
@permissions_required("dashboard.access", "mobile_versions.view")
def mobile_version_detail(request, pk):
    version = get_object_or_404(MobileAppVersion, pk=pk)
    return render(
        request,
        "dashboard/pages/mobile_versions/detail.html",
        {
            "version": version,
            "can_manage_mobile_versions": request.user.has_permission(
                "mobile_versions.manage"
            ),
        },
    )


@login_required
@permissions_required("dashboard.access", "mobile_versions.manage")
def mobile_version_create(request):
    prefill_platform = (request.GET.get("platform") or "").strip().lower()
    if prefill_platform not in VALID_PLATFORMS:
        prefill_platform = MobilePlatform.ANDROID

    initial = {
        "platform": prefill_platform,
        "version_name": "",
        "build_number": "",
        "minimum_version_name": "",
        "minimum_build_number": "",
        "update_mode": UpdateMode.NONE,
        "force_update": False,
        "update_title_ar": "",
        "update_title_en": "",
        "update_message_ar": "",
        "update_message_en": "",
        "release_notes_ar": "",
        "release_notes_en": "",
        "store_url": "",
        "allow_later": False,
        "later_reminder_hours": "",
        "starts_at_raw": "",
        "is_active": False,
        "platform_app_enabled": _platform_app_enabled_initial(prefill_platform),
    }

    if request.method == "POST":
        data, errors = _parse_mobile_version_form(request.POST, existing=None)
        initial = data
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            try:
                version = MobileAppVersion(created_by=request.user, updated_by=request.user)
                _apply_mobile_version(version, data)
                _apply_platform_app_enabled(data["platform"], data["platform_app_enabled"])
                if data["is_active"]:
                    activate_mobile_app_version(version, actor=request.user)
            except ValidationError as exc:
                for msg in exc.messages:
                    messages.error(request, msg)
            else:
                messages.success(request, "تم إنشاء إصدار التطبيق بنجاح.")
                return redirect("dashboard:mobile_version_list")

    return render(
        request,
        "dashboard/pages/mobile_versions/form.html",
        {
            "title": "إضافة نسخة تطبيق",
            "mode": "create",
            "initial": initial,
            "version": None,
            "platform_choices": MobilePlatform.choices,
        },
    )


@login_required
@permissions_required("dashboard.access", "mobile_versions.manage")
def mobile_version_update(request, pk):
    version = get_object_or_404(MobileAppVersion, pk=pk)
    initial = {
        "platform": version.platform,
        "version_name": version.version_name,
        "build_number": version.build_number,
        "minimum_version_name": version.minimum_version_name,
        "minimum_build_number": version.minimum_build_number or "",
        "update_mode": version.update_mode,
        "force_update": version.update_mode == UpdateMode.REQUIRED,
        "update_title_ar": version.update_title_ar,
        "update_title_en": version.update_title_en,
        "update_message_ar": version.update_message_ar,
        "update_message_en": version.update_message_en,
        "release_notes_ar": version.release_notes_ar,
        "release_notes_en": version.release_notes_en,
        "store_url": version.store_url,
        "allow_later": version.allow_later,
        "later_reminder_hours": version.later_reminder_hours or "",
        "starts_at_raw": (
            timezone.localtime(version.starts_at).strftime("%Y-%m-%dT%H:%M")
            if version.starts_at
            else ""
        ),
        "is_active": version.is_active,
        "platform_app_enabled": _platform_app_enabled_initial(version.platform),
    }

    if request.method == "POST":
        data, errors = _parse_mobile_version_form(request.POST, existing=version)
        initial = data
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            try:
                was_active = version.is_active
                _apply_mobile_version(version, data)
                version.updated_by = request.user
                version.save(update_fields=["updated_by", "updated_at"])
                _apply_platform_app_enabled(data["platform"], data["platform_app_enabled"])
                if data["is_active"]:
                    activate_mobile_app_version(version, actor=request.user)
                elif was_active:
                    deactivate_mobile_app_version(version, actor=request.user)
            except ValidationError as exc:
                for msg in exc.messages:
                    messages.error(request, msg)
            else:
                messages.success(request, "تم تحديث إصدار التطبيق بنجاح.")
                return redirect("dashboard:mobile_version_list")

    return render(
        request,
        "dashboard/pages/mobile_versions/form.html",
        {
            "title": "تعديل نسخة تطبيق",
            "mode": "edit",
            "initial": initial,
            "version": version,
            "platform_choices": MobilePlatform.choices,
        },
    )


@login_required
@permissions_required("dashboard.access", "mobile_versions.manage")
@require_POST
def mobile_version_activate(request, pk):
    version = get_object_or_404(MobileAppVersion, pk=pk)
    activate_mobile_app_version(version, actor=request.user)
    messages.success(request, "تم تفعيل إصدار التطبيق.")
    return redirect("dashboard:mobile_version_list")


@login_required
@permissions_required("dashboard.access", "mobile_versions.manage")
@require_POST
def mobile_version_deactivate(request, pk):
    version = get_object_or_404(MobileAppVersion, pk=pk)
    deactivate_mobile_app_version(version, actor=request.user)
    messages.success(request, "تم تعطيل إصدار التطبيق.")
    return redirect("dashboard:mobile_version_list")


def _parse_blocked_version_form(post):
    errors = []

    platform = (post.get("platform") or "").strip().lower()
    if platform not in VALID_PLATFORMS:
        errors.append("المنصة غير صالحة.")

    version_name = (post.get("version_name") or "").strip()

    build_number = _parse_optional_int(
        post.get("build_number"), field_label="رقم البناء", errors=errors, minimum=1
    )
    if build_number is None and not (post.get("build_number") or "").strip():
        errors.append("رقم البناء مطلوب.")

    reason_ar = (post.get("reason_ar") or "").strip()
    reason_en = (post.get("reason_en") or "").strip()
    is_active = post.get("is_active") == "on"

    data = {
        "platform": platform,
        "version_name": version_name,
        "build_number": build_number,
        "reason_ar": reason_ar,
        "reason_en": reason_en,
        "is_active": is_active,
    }
    return data, errors


def _apply_blocked_version(instance: BlockedMobileAppVersion, data: dict) -> BlockedMobileAppVersion:
    instance.platform = data["platform"]
    instance.version_name = data["version_name"]
    instance.build_number = data["build_number"]
    instance.reason_ar = data["reason_ar"]
    instance.reason_en = data["reason_en"]
    instance.is_active = data["is_active"]
    instance.save()
    return instance


@login_required
@permissions_required("dashboard.access", "mobile_versions.view")
def blocked_mobile_version_list(request):
    platform_filter = (request.GET.get("platform") or "all").strip()
    status_filter = (request.GET.get("status") or "all").strip()

    qs = BlockedMobileAppVersion.objects.all().order_by("-created_at", "-id")

    if platform_filter in VALID_PLATFORMS:
        qs = qs.filter(platform=platform_filter)

    if status_filter == "active":
        qs = qs.filter(is_active=True)
    elif status_filter == "inactive":
        qs = qs.filter(is_active=False)

    page_obj, page_numbers, per_page_param, total_blocked = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="10",
    )

    pagination_qs = build_pagination_query_string(
        platform=platform_filter,
        status=status_filter,
        per_page=per_page_param,
    )

    hidden_fields = []
    if platform_filter != "all":
        hidden_fields.append({"name": "platform", "value": platform_filter})
    if status_filter != "all":
        hidden_fields.append({"name": "status", "value": status_filter})

    return render(
        request,
        "dashboard/pages/mobile_versions/blocked_list.html",
        {
            "can_manage_mobile_versions": request.user.has_permission(
                "mobile_versions.manage"
            ),
            "blocked_versions": page_obj.object_list,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_blocked": total_blocked,
            "platform_filter": platform_filter,
            "status_filter": status_filter,
            "platform_choices": MobilePlatform.choices,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": hidden_fields,
        },
    )


@login_required
@permissions_required("dashboard.access", "mobile_versions.manage")
def blocked_mobile_version_create(request):
    initial = {
        "platform": MobilePlatform.ANDROID,
        "version_name": "",
        "build_number": "",
        "reason_ar": "",
        "reason_en": "",
        "is_active": True,
    }

    if request.method == "POST":
        data, errors = _parse_blocked_version_form(request.POST)
        initial = data
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            try:
                blocked = BlockedMobileAppVersion(created_by=request.user)
                _apply_blocked_version(blocked, data)
            except ValidationError as exc:
                for msg in exc.messages:
                    messages.error(request, msg)
            else:
                messages.success(request, "تم إضافة الإصدار المحظور بنجاح.")
                return redirect("dashboard:blocked_mobile_version_list")

    return render(
        request,
        "dashboard/pages/mobile_versions/blocked_form.html",
        {
            "title": "إضافة إصدار محظور",
            "mode": "create",
            "initial": initial,
            "blocked_version": None,
            "platform_choices": MobilePlatform.choices,
        },
    )


@login_required
@permissions_required("dashboard.access", "mobile_versions.manage")
def blocked_mobile_version_update(request, pk):
    blocked = get_object_or_404(BlockedMobileAppVersion, pk=pk)
    initial = {
        "platform": blocked.platform,
        "version_name": blocked.version_name,
        "build_number": blocked.build_number,
        "reason_ar": blocked.reason_ar,
        "reason_en": blocked.reason_en,
        "is_active": blocked.is_active,
    }

    if request.method == "POST":
        data, errors = _parse_blocked_version_form(request.POST)
        initial = data
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            try:
                _apply_blocked_version(blocked, data)
            except ValidationError as exc:
                for msg in exc.messages:
                    messages.error(request, msg)
            else:
                messages.success(request, "تم تحديث الإصدار المحظور بنجاح.")
                return redirect("dashboard:blocked_mobile_version_list")

    return render(
        request,
        "dashboard/pages/mobile_versions/blocked_form.html",
        {
            "title": "تعديل إصدار محظور",
            "mode": "edit",
            "initial": initial,
            "blocked_version": blocked,
            "platform_choices": MobilePlatform.choices,
        },
    )


@login_required
@permissions_required("dashboard.access", "mobile_versions.manage")
@require_POST
def blocked_mobile_version_toggle_active(request, pk):
    blocked = get_object_or_404(BlockedMobileAppVersion, pk=pk)
    blocked.is_active = not blocked.is_active
    blocked.save(update_fields=["is_active", "updated_at"])
    if blocked.is_active:
        messages.success(request, "تم تفعيل الحظر.")
    else:
        messages.success(request, "تم إلغاء الحظر.")
    return redirect("dashboard:blocked_mobile_version_list")
