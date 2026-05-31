from django.urls import path

from . import evaluation_views, recording_views, views

app_name = "calls_api"

urlpatterns = [
    path("calls/request/", views.request_call, name="request"),
    path("calls/incoming/", views.incoming_calls, name="incoming"),
    path("calls/my/", views.my_calls, name="my"),
    path("calls/start-audio/", views.start_audio, name="start-audio"),
    path("calls/start-video/", views.start_video, name="start-video"),
    path("calls/<int:pk>/", views.call_detail, name="detail"),
    path("calls/<int:pk>/accept/", views.accept_call, name="accept"),
    path("calls/<int:pk>/reject/", views.reject_call, name="reject"),
    path("calls/<int:pk>/cancel/", views.cancel_call, name="cancel"),
    path("calls/<int:pk>/end/", views.end_call, name="end"),
    path("evaluations/pending/", evaluation_views.pending_evaluations, name="eval-pending"),
    path("evaluations/my/", evaluation_views.my_evaluations, name="eval-my"),
    path("evaluations/", evaluation_views.submit_evaluation, name="eval-submit"),
    path("recordings/my/", recording_views.my_recordings, name="recordings-my"),
]
