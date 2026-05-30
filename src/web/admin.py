from django.contrib import admin
from .models import Support


@admin.register(Support)
class SupportAdmin(admin.ModelAdmin):
    list_display = ("title", "order", "is_active")
    list_filter = ("is_active",)
    ordering = ("order",)
    search_fields = ("title",)
