# apps/quran_studio/urls.py

from django.urls import path
from . import views

app_name = "quran_studio"

urlpatterns = [
    path("ayah-editor/<int:page_number>/", views.ayah_editor, name="ayah_editor"),
    path("ayah-editor/<str:mushaf_key>/<int:page_number>/", views.ayah_editor, name="ayah_editor_mushaf"),
    path("api/save-ayah/", views.save_ayah_position, name="save_ayah"),
    path("api/get-ayah/", views.get_ayah_position, name="get_ayah_position"),
    path("qurra/", views.qurra_list, name="qurra_list"),
    path("qurra/delete/<int:pk>/", views.qari_delete, name="qari_delete"),
    path("qurra/toggle-visibility/<int:pk>/", views.qari_toggle_visibility, name="qari_toggle_visibility"),
]
