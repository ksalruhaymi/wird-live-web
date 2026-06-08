from django.db import migrations, models


def set_display_format_from_image(apps, schema_editor):
    Announcement = apps.get_model("communication", "Announcement")
    for row in Announcement.objects.all().iterator():
        if row.image:
            row.display_format = "image"
        elif row.message:
            row.display_format = "text"
        else:
            row.display_format = "image"
        row.save(update_fields=["display_format"])


class Migration(migrations.Migration):

    dependencies = [
        ("communication", "0005_announcement_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="display_format",
            field=models.CharField(
                choices=[("text", "نص"), ("image", "صورة")],
                default="image",
                max_length=10,
                verbose_name="شكل الإعلان",
            ),
        ),
        migrations.AddField(
            model_name="announcement",
            name="link_url",
            field=models.URLField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="رابط عند الضغط",
            ),
        ),
        migrations.RunPython(set_display_format_from_image, migrations.RunPython.noop),
    ]
