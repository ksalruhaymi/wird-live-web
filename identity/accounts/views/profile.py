from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import redirect, render

from core.services.phone_service import normalize_phone_number


def _profile_error_response(request, form_data):
    return render(
        request,
        "accounts/profile.html",
        {"form_data": form_data},
    )


@login_required
def profile_view(request):
    user = request.user

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        mobile_raw = (request.POST.get("mobile") or "").strip()
        job_title = (request.POST.get("job_title") or "").strip()
        current_password = (request.POST.get("current_password") or "").strip()
        new_password1 = (request.POST.get("new_password1") or "").strip()
        new_password2 = (request.POST.get("new_password2") or "").strip()

        form_data = {
            "full_name": full_name,
            "mobile": mobile_raw,
            "job_title": job_title,
        }

        def password_error(message):
            messages.error(request, message)
            form_data["open_password"] = True
            return _profile_error_response(request, form_data)

        mobile_db = None
        if mobile_raw:
            try:
                mobile_db = normalize_phone_number(mobile_raw, "SA")
            except ValueError as e:
                messages.error(request, str(e))
                return _profile_error_response(request, form_data)

            if user.__class__.objects.filter(mobile=mobile_db).exclude(id=user.id).exists():
                messages.error(request, "رقم الجوال مستخدم مسبقًا.")
                return _profile_error_response(request, form_data)

        user.full_name = full_name
        user.mobile = mobile_db
        user.job_title = job_title or None

        if new_password1 or new_password2:
            if not current_password:
                return password_error("كلمة المرور الحالية مطلوبة.")

            if not user.check_password(current_password):
                return password_error("كلمة المرور الحالية غير صحيحة.")

            if new_password1 != new_password2:
                return password_error("كلمتا المرور غير متطابقتين.")

            if len(new_password1) < 8:
                return password_error("كلمة المرور يجب أن تكون 8 أحرف على الأقل.")

            user.set_password(new_password1)
            try:
                user.save()
            except IntegrityError:
                messages.error(request, "رقم الجوال مستخدم مسبقًا.")
                return _profile_error_response(request, form_data)
            update_session_auth_hash(request, user)
            messages.success(request, "تم حفظ البيانات وتحديث كلمة المرور بنجاح.")
            return redirect("accounts:profile")

        try:
            user.save()
        except IntegrityError:
            messages.error(request, "رقم الجوال مستخدم مسبقًا.")
            return _profile_error_response(request, form_data)

        messages.success(request, "تم حفظ التعديلات بنجاح.")
        return redirect("accounts:profile")

    return render(request, "accounts/profile.html")