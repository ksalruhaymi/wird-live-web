from django.contrib import messages
from django.shortcuts import redirect


def register(request):
    """Public web registration is disabled; mobile app only."""
    messages.info(request, "التسجيل متاح فقط عبر تطبيق الجوال.")
    return redirect("accounts:login")
