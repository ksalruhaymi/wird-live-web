from django.urls import path

from . import views

app_name = "communication_api"

urlpatterns = [
    path("announcements/current/", views.current_announcement, name="current"),
]
