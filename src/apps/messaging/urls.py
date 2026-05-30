from django.urls import path
from . import views

app_name = "apps.messaging"

urlpatterns = [
    path("", views.overview_messaging, name="overview_messaging"),
    path("create/", views.messaging_create, name="messaging_create"),
    path("email/", views.email, name="email"),
    path("email/<int:pk>/", views.email_detail, name="email_detail"),
    path("email/<int:pk>/send/", views.send_email_broadcast, name="send_email_broadcast"),
    path("whatsapp/", views.whatsapp_list, name="whatsapp_list"),
    path("whatsapp/<int:pk>/", views.whatsapp_detail, name="whatsapp_detail"),
    path("sms/", views.sms_list, name="sms_list"),
    path("sms/<int:pk>/", views.sms_detail, name="sms_detail"),
    path("general-email/", views.general_email, name="general_email"),
    path("deliveries/", views.messaging_deliveries, name="deliveries"),
]