from django.urls import path

from . import views
from .favorite_views import favorite_teacher_ids, toggle_favorite

app_name = "maqraa_api"

urlpatterns = [
    path("teachers/available/", views.available_teachers, name="teachers-available"),
    path("teachers/heartbeat/", views.teacher_heartbeat, name="teachers-heartbeat"),
    path("teachers/favorites/", favorite_teacher_ids, name="teachers-favorites"),
    path(
        "teachers/<int:teacher_id>/favorite/",
        toggle_favorite,
        name="teachers-favorite-toggle",
    ),
]
