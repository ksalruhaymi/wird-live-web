from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.services.phone_service import normalize_phone_number
from core.utils.pagination import paginate_with_smart_pages
from identity.rbac.decorators import permission_required

from ..models import Role
from .common import users_qs

import secrets
import string


User = get_user_model()

# Protected usernames that should not be created/modified from this UI
PROTECTED_USERNAMES = ("",)


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
    """
    Generate a random password of given length.
    Letters + digits only.
    """
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


@permission_required("users.create")
def user_create(request):
    """
    Create a new user:
    - required: username, full_name, email
    - password: generated automatically and sent by email
    - role: participant (fixed)
    """
    title = "إضافة مستخدم"
    initial = {}
    errors = {}

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip().lower()
        full_name = (request.POST.get("full_name") or "").strip()
        email = (request.POST.get("email") or "").strip()
        mobile_raw = (request.POST.get("mobile") or "").strip()
        is_active = request.POST.get("is_active") == "on"

        initial = {
            "username": username,
            "full_name": full_name,
            "email": email,
            "mobile": mobile_raw,
            "is_active": is_active,
        }

        # Username
        if not username:
            errors["username"] = "اسم المستخدم مطلوب."
        elif "PROTECTED_USERNAMES" in globals() and username in PROTECTED_USERNAMES:
            errors["username"] = "اسم المستخدم هذا محجوز ولا يمكن استخدامه."
        elif User.objects.filter(username=username).exists():
            errors["username"] = "اسم المستخدم مستخدم من قبل."

        # Full name
        if not full_name:
            errors["full_name"] = "الاسم الكامل مطلوب."

        # Email
        if not email:
            errors["email"] = "البريد الإلكتروني مطلوب لإرسال بيانات الدخول."
        elif User.objects.filter(email=email).exists():
            errors["email"] = "البريد الإلكتروني مستخدم من قبل."

        # Mobile
        mobile_db = None
        if mobile_raw:
            try:
                mobile_db = normalize_phone_number(mobile_raw, "SA")
            except ValueError as e:
                errors["mobile"] = str(e)
            else:
                if User.objects.filter(mobile=mobile_db).exists():
                    errors["mobile"] = "رقم الجوال مستخدم من قبل."

       
        # Create user
        if not errors:
            password = generate_password()

            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    is_active=is_active,
                )

                if hasattr(user, "full_name"):
                    user.full_name = full_name

                if hasattr(user, "mobile"):
                    user.mobile = mobile_db

                if hasattr(user, "user_type"):
                    user.user_type = 5

                if hasattr(user, "created_by") and request.user.is_authenticated:
                    user.created_by = request.user.id

                user.save()

                participant_role = Role.objects.filter(slug="participant").first()
                if participant_role:
                    user.roles.add(participant_role)

            try:
                send_mail(
                    subject="بيانات حسابك في المنصة",
                    message=(
                        f"مرحبًا {full_name}\n\n"
                        f"تم إنشاء حسابك في المنصة.\n\n"
                        f"اسم المستخدم: {username}\n"
                        f"كلمة المرور: {password}\n\n"
                        f"ننصح بتغيير كلمة المرور بعد تسجيل الدخول."
                    ),
                    from_email=None,
                    recipient_list=[email],
                    fail_silently=False,
                )
                messages.success(
                    request,
                    "تم إنشاء المستخدم بنجاح، وتم إرسال بيانات الدخول إلى بريده الإلكتروني."
                )
            except Exception:
                messages.warning(
                    request,
                    "تم إنشاء المستخدم بنجاح، ولكن تعذّر إرسال البريد الإلكتروني. تأكّد من إعدادات البريد."
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
        User.objects.prefetch_related("roles"),
        pk=pk,
    )

    roles = Role.objects.order_by("name")
    selected_roles = [str(r.id) for r in user_obj.roles.all()]

    context = {
        "tab": "users",
        "user_obj": user_obj,
        "roles": roles,
        "selected_roles": selected_roles,
    }
    return render(request, "rbac/users/user_detail.html", context)


@permission_required("users.update")
def user_toggle_active(request, pk):
    user_obj = get_object_or_404(User, pk=pk)

    if request.method != "POST":
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

    if user_obj.username in PROTECTED_USERNAMES:
        messages.error(
            request,
            "لا يمكن تعديل أدوار هذا المستخدم الأساسي من هذه الواجهة."
        )
        return redirect("rbac:user_detail", pk=user_obj.pk)

    role_ids = request.POST.getlist("roles")
    user_obj.roles.set(role_ids)

    messages.success(request, "تم تحديث أدوار المستخدم بنجاح.")
    return redirect("rbac:user_detail", pk=user_obj.pk)