from django.urls import path

from . import views

app_name = "mobile_api"

urlpatterns = [
    path("mobile/app-config/", views.app_config, name="app_config"),
    path(
        "mobile/app-version/check/",
        views.app_version_check,
        name="app_version_check",
    ),
]
