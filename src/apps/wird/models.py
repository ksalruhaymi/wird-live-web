from django.db import models
from django.conf import settings


class ReminderSetting(models.Model):
    DAILY_WIRD       = "daily_wird"
    MORNING_ADHKAR   = "morning_adhkar"
    EVENING_ADHKAR   = "evening_adhkar"
    KAHF_FRIDAY      = "kahf_friday"

    REMINDER_TYPES = [
        (DAILY_WIRD,     "الورد اليومي"),
        (MORNING_ADHKAR, "أذكار الصباح"),
        (EVENING_ADHKAR, "أذكار المساء"),
        (KAHF_FRIDAY,    "سورة الكهف - الجمعة"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reminder_settings",
    )
    reminder_type = models.CharField(max_length=30, choices=REMINDER_TYPES)
    is_enabled    = models.BooleanField(default=False)
    reminder_time = models.TimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "reminder_type")
        ordering = ["reminder_type"]

    def __str__(self):
        return f"{self.user} — {self.get_reminder_type_display()}"
