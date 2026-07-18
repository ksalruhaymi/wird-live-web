from django.contrib import admin

from .models import PasswordResetCode, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "username",
        "full_name",
        "national_id",
        "email",
        "enrollment_track",
        "user_type",
        "is_active",
        "is_staff",
    )
    search_fields = ("username", "full_name", "national_id", "email")
    readonly_fields = ("date_joined", "last_login")
    fieldsets = (
        (None, {"fields": ("username", "password", "email", "is_active", "is_staff", "is_superuser")}),
        (
            "Profile",
            {
                "fields": (
                    "full_name",
                    "national_id",
                    "qualification",
                    "birth_date",
                    "enrollment_track",
                    "mobile",
                    "job_title",
                    "gender",
                    "user_type",
                ),
            },
        ),
        ("RBAC", {"fields": ("roles",)}),
        ("Meta", {"fields": ("created_by", "date_joined", "last_login")}),
    )
    filter_horizontal = ("roles",)


@admin.register(PasswordResetCode)
class PasswordResetCodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "expires_at",
        "verified_at",
        "used_at",
        "attempts_count",
        "created_at",
    )
    list_filter = ("used_at", "verified_at")
    search_fields = ("user__username", "user__email")
    raw_id_fields = ("user",)
    readonly_fields = (
        "code_hash",
        "reset_token_hash",
        "created_at",
        "updated_at",
    )

