from django.shortcuts import render

from core.models import SiteStat


def home(request):
    visitors = SiteStat.objects.filter(key="visitors").first()
    return render(
        request,
        "web/pages/home.html",
        {
            "visitors_count": visitors.value if visitors else 0,
        },
    )


def about(request):
    return render(request, "web/pages/about.html")


def privacy_policy(request):
    return render(request, "web/pages/privacy_policy.html")
