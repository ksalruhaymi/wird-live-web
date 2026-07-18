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
    path(
        "password-reset/request/",
        views.password_reset_request_api,
        name="password_reset_request",
    ),
    path(
        "password-reset/resend/",
        views.password_reset_resend_api,
        name="password_reset_resend",
    ),
    path(
        "password-reset/verify/",
        views.password_reset_verify_api,
        name="password_reset_verify",
    ),
    path(
        "password-reset/confirm/",
        views.password_reset_confirm_api,
        name="password_reset_confirm",
    ),
    path("profile/", views.profile_api, name="profile"),
    path("profile/update/", views.profile_update_api, name="profile_update"),
    path("profile/avatar/", views.profile_avatar_api, name="profile_avatar"),
    path(
        "profile/teacher-files/ijazah/",
        views.profile_teacher_ijazah_api,
        name="profile_teacher_ijazah",
    ),
]
