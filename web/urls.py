from django.urls import path

from . import views

app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
]
