from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from core.services.phone_service import normalize_phone_number


@login_required
def profile_view(request):
    user = request.user

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        mobile = (request.POST.get("mobile") or "").strip()
        job_title = (request.POST.get("job_title") or "").strip()
        new_password1 = (request.POST.get("new_password1") or "").strip()
        new_password2 = (request.POST.get("new_password2") or "").strip()

        form_data = {
            "full_name": full_name,
            "mobile": mobile,
            "job_title": job_title,
        }

        if mobile:
            try:
                mobile = normalize_phone_number(mobile, "SA")
            except ValueError as e:
                messages.error(request, str(e))
                return render(
                    request,
                    "accounts/profile.html",
                    {"form_data": form_data},
                )

            if user.__class__.objects.filter(mobile=mobile).exclude(id=user.id).exists():
                messages.error(request, "رقم الجوال مستخدم مسبقًا.")
                return render(
                    request,
                    "accounts/profile.html",
                    {"form_data": form_data},
                )

        user.full_name = full_name
        user.mobile = mobile
        user.job_title = job_title

        if new_password1 or new_password2:
            if new_password1 != new_password2:
                messages.error(request, "كلمتا المرور غير متطابقتين.")
                return render(
                    request,
                    "accounts/profile.html",
                    {"form_data": form_data},
                )

            if len(new_password1) < 8:
                messages.error(request, "كلمة المرور يجب أن تكون 8 أحرف على الأقل.")
                return render(
                    request,
                    "accounts/profile.html",
                    {"form_data": form_data},
                )

            user.set_password(new_password1)
            user.save()
            update_session_auth_hash(request, user)
            messages.success(request, "تم حفظ البيانات وتحديث كلمة المرور بنجاح.")
            return redirect("accounts:profile")

        user.save()
        messages.success(request, "تم حفظ التعديلات بنجاح.")
        return redirect("accounts:profile")

    return render(request, "accounts/profile.html")