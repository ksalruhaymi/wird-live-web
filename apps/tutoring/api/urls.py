from django.urls import path

from . import management_views, views
from .favorite_views import favorite_teacher_ids, toggle_favorite

app_name = "tutoring_api"

urlpatterns = [
    path("teachers/available/", views.available_teachers, name="teachers-available"),
    path("teachers/heartbeat/", views.teacher_heartbeat, name="teachers-heartbeat"),
    path("teachers/favorites/", favorite_teacher_ids, name="teachers-favorites"),
    path(
        "teachers/<int:teacher_id>/favorite/",
        toggle_favorite,
        name="teachers-favorite-toggle",
    ),
    path(
        "management/teachers/pending/",
        management_views.pending_teachers_list,
        name="management-pending-teachers",
    ),
    path(
        "management/teachers/<int:teacher_id>/",
        management_views.pending_teacher_detail,
        name="management-teacher-detail",
    ),
    path(
        "management/teachers/<int:teacher_id>/approve/",
        management_views.pending_teacher_approve,
        name="management-teacher-approve",
    ),
    path(
        "management/teachers/<int:teacher_id>/reject/",
        management_views.pending_teacher_reject,
        name="management-teacher-reject",
    ),
    path(
        "management/teachers/<int:teacher_id>/profile-image/",
        management_views.management_teacher_profile_image,
        name="management-teacher-profile-image",
    ),
    path(
        "management/teachers/<int:teacher_id>/ijazah/",
        management_views.management_teacher_ijazah,
        name="management-teacher-ijazah",
    ),
]
