from django.contrib import admin

from .models import Announcement, CommunicationCampaign, CommunicationCampaignChannel


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "display_format",
        "title",
        "announcement_type",
        "is_active",
        "link_url",
        "created_at",
    )
    list_filter = ("is_active", "display_format", "announcement_type")
    search_fields = ("title", "message", "target_group")


admin.site.register(CommunicationCampaign)
admin.site.register(CommunicationCampaignChannel)
