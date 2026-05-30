# File: apps/contact/urls.py
# Description: Handles public contact and dashboard contact routes

from django.urls import path
from .views.contact_views import contact_view, contact_success
from .views.dashboard_views import (
    list_messages,
    detail_message,
    mark_replied,
)

app_name = "contact"

urlpatterns = [

    #Contact 
    path("", contact_view, name="contact"),
    path("success/", contact_success, name="success"),
    
    
    # Dashboard 
    path("dashboard/", list_messages, name="dashboard_list"),
    path("dashboard/<int:pk>/", detail_message, name="dashboard_detail"),
    path("dashboard/<int:pk>/replied/", mark_replied, name="dashboard_replied"),
]