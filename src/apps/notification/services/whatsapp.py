from django.conf import settings

def send_whatsapp(broadcast, recipients):
    for u in recipients:
        print(f"[DEV WHATSAPP] To:{u.username} | {broadcast.body}")
