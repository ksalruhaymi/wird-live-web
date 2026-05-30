from django.db import models


class Support(models.Model):
    title = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    url = models.CharField(max_length=200)

    image = models.ImageField(
        upload_to="supports/",
        blank=True,
        null=True,
    )

    order = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title
