from django.contrib import admin

from .models import StudentProfile, TeacherAvailability, TeacherFavorite, TeacherProfile, TutoringSession


@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "display_name",
        "is_available",
        "is_approved",
        "approval_status",
        "auto_accept_calls",
        "can_audio",
        "can_video",
    )
    list_filter = (
        "is_available",
        "is_approved",
        "approval_status",
        "auto_accept_calls",
        "can_audio",
        "can_video",
    )
    search_fields = ("user__username", "display_name")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "created_at")
    search_fields = ("user__username", "display_name")


@admin.register(TeacherAvailability)
class TeacherAvailabilityAdmin(admin.ModelAdmin):
    list_display = ("teacher", "status", "last_seen", "updated_at")
    list_filter = ("status",)
    search_fields = ("teacher__username", "teacher__full_name")


@admin.register(TutoringSession)
class TutoringSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "student",
        "teacher",
        "session_type",
        "status",
        "created_at",
    )
    list_filter = ("session_type", "status")
    search_fields = ("student__username", "teacher__username")
