
from django.urls import path
from django.contrib.auth.views import LogoutView
from .views.login import login_view
from .views.profile import profile_view
from .views.register import register
from .views.login_settings import login_settings
app_name = "accounts" 

urlpatterns = [
    path("login/", login_view, name="login"),
    path("profile/", profile_view, name="profile"),
    path("register/", register, name="register"),
    path("logout/",LogoutView.as_view(next_page="web:home"),name="logout"),
    path("settings/auth/", login_settings, name="login_settings"),

]



