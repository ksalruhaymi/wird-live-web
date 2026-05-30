from django.urls import path
from . import views

app_name = "contact_api"

urlpatterns = [
    path("messages/", views.submit_message, name="submit-message"),
]
