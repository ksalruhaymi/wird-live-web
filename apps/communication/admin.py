from django.contrib import admin

from .models import Announcement, CommunicationCampaign, CommunicationCampaignChannel


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "announcement_type",
        "announced_by",
        "target_type",
        "announcement_date",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "announcement_type", "announced_by", "target_type")
    search_fields = ("title", "message", "target_group")


admin.site.register(CommunicationCampaign)
admin.site.register(CommunicationCampaignChannel)
