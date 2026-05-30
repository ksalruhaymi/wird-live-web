# apps/core/models.py (أو أي app مناسب)
from django.db import models


class SiteStat(models.Model):
    key = models.CharField(max_length=50, unique=True)
    value = models.PositiveBigIntegerField(default=0)

    def __str__(self):
        return f"{self.key}: {self.value}"
