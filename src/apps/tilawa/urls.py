# apps/tilawa/urls.py

from django.urls import path
from . import views

app_name = "tilawa"

urlpatterns = [
    path("quraa/", views.qari_list, name="qari_list"),
    path("quraa/listen/<str:qari_code>/", views.qari_listen, name="qari_listen"),
]