import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat


def normalize_phone_number(phone: str, region: str = "SA") -> str:
    phone = (phone or "").strip()

    if not phone:
        raise ValueError("رقم الهاتف مطلوب")

    phone = phone.replace(" ", "").replace("-", "")

    if phone.startswith("00"):
        phone = f"+{phone[2:]}"

    if phone.startswith("966") and not phone.startswith("+966"):
        phone = f"+{phone}"

    if phone.startswith("05"):
        phone = f"+966{phone[1:]}"
    elif phone.startswith("5") and len(phone) == 9:
        phone = f"+966{phone}"

    try:
        parsed = phonenumbers.parse(phone, region)
    except NumberParseException:
        raise ValueError("صيغة رقم الهاتف غير صحيحة")

    if not phonenumbers.is_possible_number(parsed):
        raise ValueError("رقم الهاتف غير ممكن")

    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("رقم الهاتف غير صحيح")

    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def validate_phone_number(phone: str, region: str = "SA") -> None:
    normalize_phone_number(phone, region=region)


def format_phone_for_display(phone: str, region: str = "SA") -> str:
    phone = normalize_phone_number(phone, region=region)
    return phonenumbers.format_number(
        phonenumbers.parse(phone, region),
        PhoneNumberFormat.INTERNATIONAL,
    )


def format_phone_for_sms(phone: str) -> str:
    return normalize_phone_number(phone).replace("+", "")