# apps/core/middleware.py
from ..models import SiteStat


class VisitorCounterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # نعدّ فقط الزيارات العامة (مثلاً الصفحة الرئيسية)
        if request.path == "/" and not request.session.get("counted"):
            stat, _ = SiteStat.objects.get_or_create(key="visitors")
            stat.value += 1
            stat.save(update_fields=["value"])
            request.session["counted"] = True

        return self.get_response(request)
