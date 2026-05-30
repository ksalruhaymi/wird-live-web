import requests
from django.conf import settings

from core.services.phone_service import format_phone_for_sms


def send_sms(mobile, body):
    try:
        mobile = format_phone_for_sms(mobile)
    except ValueError as e:
        return False, str(e)

    url = settings.SMS_API_URL
    payload = {
        "mobile": mobile,
        "sms": body,
        "token": settings.SMS_TOKEN,
    }

    # DEBUG: اطبع الطلب كما يذهب للمزوّد
    print("=== SMS REQUEST ===")
    print("URL:", url)
    print("PAYLOAD:", payload)

    r = requests.post(
        url,
        data=payload,
        timeout=getattr(settings, "SMS_TIMEOUT", 15),
    )

    # DEBUG: اطبع الرد الخام
    print("=== SMS RESPONSE ===")
    print("STATUS:", r.status_code)
    print("TEXT:", repr(r.text))

    if r.status_code != 200:
        return False, f"HTTP {r.status_code} - {r.text}"

    try:
        data = r.json()
    except Exception:
        if r.text.strip() in ("1", "OK", "ok"):
            return True, r.text.strip()
        return False, r.text

    if isinstance(data, list) and data:
        data = data[0]

    msg_type = str(data.get("type", "")).lower()
    msg_text = data.get("msg", r.text)

    if msg_type != "success":
        return False, f"type={msg_type} msg={msg_text}"

    return True, msg_text or "OK"