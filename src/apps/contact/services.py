from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email

from core.services.phone_service import normalize_phone_number

from .models import ContactMessage


def handle_contact(data):
    errors = {}

    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("phone") or "").strip()
    message = (data.get("message") or "").strip()

    if not full_name:
        errors["full_name"] = "الاسم مطلوب"

    if not email:
        errors["email"] = "البريد مطلوب"
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors["email"] = "بريد غير صحيح"

    if phone:
        try:
            phone = normalize_phone_number(phone, "SA")
        except ValueError as e:
            errors["phone"] = str(e)

    if not message:
        errors["message"] = "الرسالة مطلوبة"

    if errors:
        return None, errors

    contact = ContactMessage.objects.create(
        full_name=full_name,
        email=email,
        phone=phone,
        message=message,
    )

    # _send_new_contact_email(contact)

    return contact, None


def _send_new_contact_email(contact):
    send_mail(
        subject="رسالة جديدة من تواصل معنا",
        message=f"""
الاسم: {contact.full_name}
البريد: {contact.email}
الهاتف: {contact.phone or "-"}

{contact.message}
""".strip(),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.CONTACT_RECIPIENT_EMAIL],
        fail_silently=False,
    )


def send_contact_reply(contact, subject, body):
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[contact.email],
        fail_silently=False,
    )