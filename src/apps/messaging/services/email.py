from django.conf import settings
from django.core.mail import send_mass_mail

def send_email(broadcast, recipients):
    messages = []
    for u in recipients:
        if u.email:
            messages.append(
                (broadcast.title, broadcast.body, settings.DEFAULT_FROM_EMAIL, [u.email])
            )
    if messages:
        send_mass_mail(messages, fail_silently=False)
