from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "full_name", "email", "user_type", "is_active", "is_staff")
    search_fields = ("username", "name", "email")
