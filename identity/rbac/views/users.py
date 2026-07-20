import mimetypes

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.services.phone_service import normalize_phone_number
from core.utils.pagination import paginate_with_smart_pages
from identity.accounts.auth.profile_service import build_profile_payload
from identity.accounts.auth.registration_service import username_from_email
from identity.accounts.user_role_sync import apply_user_roles
from identity.accounts.user_types import USER_TYPE_TEACHER, USER_TYPE_SUPERVISOR
from identity.rbac.decorators import permission_required

from ..models import Role
from .common import users_qs

import secrets
import string


User = get_user_model()

PROTECTED_USERNAMES = ("admin",)

_GENDER_LABELS = {
    "male": "ذكر",
    "female": "أنثى",
}


def _gender_label(user) -> str:
    gender = (getattr(user, "gender", None) or "").strip()
    return _GENDER_LABELS.get(gender, "-")


def _ijazah_file_kind(filename: str) -> str:
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if ext in {"png", "jpg", "jpeg", "gif", "webp"}:
        return "image"
    if ext == "pdf":
        return "pdf"
    return "file"


@permission_required("users.list")
def users_list(request):
    tab = "users"

    users_queryset = users_qs()

    page_obj, users_page_numbers, per_page_param, total_users = paginate_with_smart_pages(
        request=request,
        queryset=users_queryset,
    )

    roles = Role.objects.order_by("name")

    context = {
        "tab": tab,
        "users": page_obj,
        "users_page_numbers": users_page_numbers,
        "roles": roles,
        "permissions": None,
        "per_page": per_page_param,
        "total_users": total_users,
        "selected_role": None,
        "selected_role_perm_ids": [],
        "message": None,
    }
    return render(request, "rbac/users/users.html", context)


def generate_password(length: int = 10) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


@permission_required("users.create")
def user_create(request):
    """
    Admin-only: create a supervisor account for dashboard access.
    Students and teachers register via the mobile app only.
    """
    title = "إضافة مشرف"
    initial = {}
    errors = {}

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        mobile_raw = (request.POST.get("mobile") or "").strip()
        is_active = request.POST.get("is_active") == "on"

        username = username_from_email(email) if email else ""

        initial = {
            "full_name": full_name,
            "email": email,
            "mobile": mobile_raw,
            "is_active": is_active,
        }

        if not full_name:
            errors["full_name"] = "الاسم الكامل مطلوب."

        if not email:
            errors["email"] = "البريد الإلكتروني مطلوب لإرسال بيانات الدخول."
        elif "@" not in email:
            errors["email"] = "البريد الإلكتروني غير صالح."
        elif User.objects.filter(email__iexact=email).exists():
            errors["email"] = "البريد الإلكتروني مستخدم من قبل."
        elif username and User.objects.filter(username__iexact=username).exists():
            errors["email"] = (
                "اسم المستخدم المستخرج من هذا البريد مستخدم من قبل."
            )

        mobile_db = None
        if mobile_raw:
            try:
                mobile_db = normalize_phone_number(mobile_raw, "SA")
            except ValueError as e:
                errors["mobile"] = str(e)
            if (
                not errors.get("mobile")
                and mobile_db
                and User.objects.filter(mobile=mobile_db).exists()
            ):
                errors["mobile"] = "رقم الجوال مستخدم من قبل."

        if not errors:
            password = generate_password()

            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    is_active=is_active,
                    is_staff=False,
                    is_superuser=False,
                )
                user.full_name = full_name
                user.mobile = mobile_db
                user.user_type = USER_TYPE_SUPERVISOR
                if request.user.is_authenticated:
                    user.created_by = request.user.id
                user.save()

                supervisor_role = Role.objects.filter(slug="supervisor").first()
                if supervisor_role:
                    user.roles.set([supervisor_role])

            try:
                send_mail(
                    subject="بيانات حسابك في المنصة",
                    message=(
                        f"مرحبًا {full_name}\n\n"
                        f"تم إنشاء حساب مشرف في لوحة التحكم.\n\n"
                        f"البريد / اسم المستخدم: {username}\n"
                        f"كلمة المرور: {password}\n\n"
                        f"ننصح بتغيير كلمة المرور بعد تسجيل الدخول."
                    ),
                    from_email=None,
                    recipient_list=[email],
                    fail_silently=False,
                )
                messages.success(
                    request,
                    "تم إنشاء المشرف بنجاح، وتم إرسال بيانات الدخول إلى بريده الإلكتروني.",
                )
            except Exception:
                messages.warning(
                    request,
                    "تم إنشاء المشرف بنجاح، ولكن تعذّر إرسال البريد الإلكتروني.",
                )

            return redirect("rbac:users_list")

    return render(
        request,
        "rbac/users/user_form.html",
        {
            "tab": "users",
            "title": title,
            "initial": initial,
            "errors": errors,
        },
    )


@permission_required("users.detail")
def user_detail(request, pk):
    user_obj = get_object_or_404(
        User.objects.prefetch_related("roles").select_related("teacher_profile"),
        pk=pk,
    )

    roles = Role.objects.order_by("name")
    selected_roles = [str(r.id) for r in user_obj.roles.all()]

    teacher_ijazah = None
    is_teacher = getattr(user_obj, "user_type", None) == USER_TYPE_TEACHER
    if is_teacher:
        profile = getattr(user_obj, "teacher_profile", None)
        ijazah_field = getattr(profile, "ijazah", None) if profile else None
        if ijazah_field and ijazah_field.name:
            filename = ijazah_field.name.rsplit("/", 1)[-1]
            teacher_ijazah = {
                "filename": filename,
                "kind": _ijazah_file_kind(filename),
                "url_name": "rbac:user_teacher_ijazah",
            }

    has_profile_image = bool(getattr(user_obj, "profile_image", None))

    teacher_auto_accept = False
    if is_teacher:
        profile = getattr(user_obj, "teacher_profile", None)
        if profile:
            teacher_auto_accept = profile.auto_accept_calls

    context = {
        "tab": "users",
        "user_obj": user_obj,
        "roles": roles,
        "selected_roles": selected_roles,
        "gender_label": _gender_label(user_obj),
        "riwayat_value": build_profile_payload(user_obj).get("riwayat") or "-",
        "is_teacher": is_teacher,
        "teacher_ijazah": teacher_ijazah,
        "teacher_auto_accept": teacher_auto_accept,
        "has_profile_image": has_profile_image,
    }
    return render(request, "rbac/users/user_detail.html", context)


@permission_required("users.detail")
def user_profile_image(request, pk):
    user_obj = get_object_or_404(User, pk=pk)
    image = getattr(user_obj, "profile_image", None)
    if not image or not image.name:
        raise Http404
    content_type, _ = mimetypes.guess_type(image.name)
    try:
        return FileResponse(
            image.open("rb"),
            content_type=content_type or "image/jpeg",
        )
    except (ValueError, FileNotFoundError) as exc:
        raise Http404 from exc


@permission_required("users.detail")
def user_teacher_ijazah(request, pk):
    user_obj = get_object_or_404(
        User.objects.select_related("teacher_profile"),
        pk=pk,
    )
    if getattr(user_obj, "user_type", None) != USER_TYPE_TEACHER:
        raise Http404
    profile = getattr(user_obj, "teacher_profile", None)
    ijazah = getattr(profile, "ijazah", None) if profile else None
    if not ijazah or not ijazah.name:
        raise Http404
    content_type, _ = mimetypes.guess_type(ijazah.name)
    filename = ijazah.name.rsplit("/", 1)[-1]
    try:
        response = FileResponse(
            ijazah.open("rb"),
            content_type=content_type or "application/octet-stream",
        )
        disposition = "inline" if _ijazah_file_kind(filename) in {"image", "pdf"} else "attachment"
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response
    except (ValueError, FileNotFoundError) as exc:
        raise Http404 from exc


@permission_required("users.update")
def user_toggle_active(request, pk):
    user_obj = get_object_or_404(User, pk=pk)

    if request.method != "POST":
        return redirect("rbac:user_detail", pk=pk)

    if user_obj.username in PROTECTED_USERNAMES and not request.user.is_superuser:
        messages.error(request, "لا يمكن تعديل حالة المستخدم الأساسي.")
        return redirect("rbac:user_detail", pk=pk)

    is_active = bool(request.POST.get("is_active"))
    user_obj.is_active = is_active
    user_obj.save()

    messages.success(request, "تم تحديث حالة المستخدم.")
    return redirect("rbac:user_detail", pk=pk)


@permission_required("users.update")
@require_POST
def user_update_roles(request, pk):
    user_obj = get_object_or_404(
        User.objects.prefetch_related("roles"),
        pk=pk,
    )

    if user_obj.username in PROTECTED_USERNAMES and not request.user.is_superuser:
        messages.error(
            request,
            "لا يمكن تعديل أدوار المستخدم الأساسي من هذه الواجهة.",
        )
        return redirect("rbac:user_detail", pk=user_obj.pk)

    role_ids = request.POST.getlist("roles")
    roles = list(Role.objects.filter(pk__in=role_ids))
    ok, error = apply_user_roles(user_obj, roles)
    if not ok:
        messages.error(request, error or "تعذّر تحديث أدوار المستخدم.")
        return redirect("rbac:user_detail", pk=user_obj.pk)

    messages.success(request, "تم تحديث أدوار المستخدم بنجاح.")
    return redirect("rbac:user_detail", pk=user_obj.pk)
