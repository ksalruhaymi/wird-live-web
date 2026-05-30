import requests

def send_sms(mobile, body):
    payload = {
        "username": "SMS_USERNAME",
        "password": "SMS_PASSWORD",
        "sender": "TEST",
        "mobile": mobile,
        "message": body,
    }

    try:
        response = requests.post(
            "https://sms-provider.example/api/send",
            data=payload,
            timeout=10,
        )

        if response.status_code != 200:
            return False, f"HTTP {response.status_code}"

        # حاول JSON أولًا
        try:
            data = response.json()
            if not data.get("success"):
                return False, data.get("message", "Unknown API error")
        except Exception:
            # لو الرد نصي
            if "error" in response.text.lower():
                return False, response.text

        return True, "OK"

    except Exception as e:
        return False, str(e)
