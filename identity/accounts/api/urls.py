from django.urls import path

from . import views

app_name = "accounts_auth_api"

urlpatterns = [
    path("register/", views.register_api, name="register"),
    path("login/", views.login_api, name="login"),
    path("google/", views.google_auth_api, name="google"),
    path("logout/", views.logout_api, name="logout"),
    path("me/", views.me, name="me"),
    path("check-email/", views.check_email_api, name="check_email"),
    path("send-email-code/", views.send_email_code_api, name="send_email_code"),
    path("verify-email-code/", views.verify_email_code_api, name="verify_email_code"),
]
