from django.urls import path

from . import views

app_name = "analytics_api"

urlpatterns = [
    path("events/", views.ingest_mobile_events, name="ingest-events"),
]
