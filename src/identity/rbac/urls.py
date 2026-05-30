# src/identity/rbac/urls.py
from django.urls import path
from . import views

app_name = "rbac"

urlpatterns = [

    path("", views.rabc_overview, name="rabc_overview"),

    # ===== Users =====
    path("users/", views.users_list, name="users_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/toggle-active/", views.user_toggle_active, name="user_toggle_active"),
    path("users/<int:pk>/roles/update/", views.user_update_roles, name="user_update_roles"),

    # ===== Roles CRUD =====
    path("roles/", views.roles_list, name="roles_list"),
    path("roles/create/", views.role_create, name="role_create"),
    path("roles/<int:pk>/edit/", views.role_update, name="role_update"),
    path("roles/<int:pk>/delete/", views.role_delete, name="role_delete"),

    # ===== Permissions CRUD =====
    path("permissions/", views.permissions_list, name="permissions_list"),
    path("permissions/create/", views.permission_create, name="permission_create"),
    path("permissions/<int:pk>/edit/", views.permission_update, name="permission_update"),
    path("permissions/<int:pk>/delete/", views.permission_delete, name="permission_delete"),

    # ===== linking =====
    path("linking/", views.linking_list, name="linking_list"),

]
