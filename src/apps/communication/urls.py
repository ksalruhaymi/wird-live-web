from django.urls import path
from . import views

app_name = "apps.communication"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("new/", views.create_campaign, name="create"),
    path("campaigns/", views.campaigns, name="campaigns"),
    path("campaigns/<int:pk>/send/", views.send_campaign, name="send_campaign"),
    path("logs/", views.logs, name="logs"),
]
