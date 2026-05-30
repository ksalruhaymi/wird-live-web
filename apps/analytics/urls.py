from django.urls import path
from . import views

app_name = "analytics"

urlpatterns = [
    path("", views.overview_dashboard, name="dashboard"),
    path("pages/", views.pages_dashboard, name="pages_dashboard"),
    path("audio/", views.audio_dashboard, name="audio_dashboard"),
    path("mushaf/", views.mushaf_dashboard, name="mushaf_dashboard"),
    path("visitors/", views.visitors_dashboard, name="visitors_dashboard"),
    path("events/", views.events_dashboard, name="events_dashboard"),
    path("track-event/", views.track_event, name="track_event"),
    path("tafsir/", views.tafsir_dashboard, name="tafsir_dashboard"),
]