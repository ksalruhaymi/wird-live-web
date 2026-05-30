import re
from django.conf import settings
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.core.exceptions import ValidationError


def handle_contact_form(post_data):
    data = {
        "full_name": (post_data.get("full_name") or "").strip(),
        "email": (post_data.get("email") or "").strip(),
        "phone": (post_data.get("phone") or "").strip(),
        "message": (post_data.get("message") or "").strip(),
    }
    errors = {}

    if not data["full_name"]:
        errors["full_name"] = "الاسم مطلوب"

    if not data["email"]:
        errors["email"] = "البريد الإلكتروني مطلوب"
    else:
        try:
            validate_email(data["email"])
        except ValidationError:
            errors["email"] = "صيغة البريد الإلكتروني غير صحيحة"

    if data["phone"]:
        if not re.fullmatch(r"5\d{8}", data["phone"]):
            errors["phone"] = "صيغة رقم الجوال غير صحيحة"

    if not data["message"]:
        errors["message"] = "الرسالة مطلوبة"

    if not errors:
        _send_contact_email(data)

    return data, errors


def _send_contact_email(data):
    subject = "رسالة جديدة من نموذج اتصل بنا"

    body_lines = [
        f"الاسم: {data['full_name']}",
        f"البريد الإلكتروني: {data['email']}",
    ]

    if data.get("phone"):
        body_lines.append(f"رقم الجوال: +966{data['phone']}")

    body_lines.append("")
    body_lines.append("نص الرسالة:")
    body_lines.append(data["message"])

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
    recipient_email = getattr(settings, "CONTACT_RECIPIENT_EMAIL", from_email)

    if not from_email or not recipient_email:
        raise ValueError("Email settings are not configured correctly.")

    send_mail(
        subject=subject,
        message="\n".join(body_lines),
        from_email=from_email,
        recipient_list=[recipient_email],
        fail_silently=False,
    )