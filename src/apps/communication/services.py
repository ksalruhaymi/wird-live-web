import requests
from django.conf import settings


def send_telegram_message(text, image_path=None, target="group"):
    token = settings.TELEGRAM_BOT_TOKEN

    if target == "channel":
        chat_id = settings.TELEGRAM_CHANNEL_USERNAME
    else:
        chat_id = settings.TELEGRAM_CHAT_ID

    try:
        # ✔ إذا فيه صورة → استخدم sendPhoto (للقروب والقناة)
        if image_path:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"

            with open(image_path, "rb") as photo:
                response = requests.post(
                    url,
                    data={
                        "chat_id": chat_id,
                        "caption": text,
                        "parse_mode": "HTML",
                    },
                    files={"photo": photo},
                    timeout=20,
                )

        # ✔ إذا ما فيه صورة → sendMessage
        else:
            url = f"https://api.telegram.org/bot{token}/sendMessage"

            response = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
                timeout=20,
            )

        data = response.json()

        if response.status_code == 200 and data.get("ok"):
            return True, ""

        return False, str(data)

    except Exception as e:
        return False, str(e)