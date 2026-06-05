from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("communication", "0004_announcement"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="announcements/",
                verbose_name="صورة الإعلان",
            ),
        ),
        migrations.AlterField(
            model_name="announcement",
            name="announcement_date",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="تاريخ الإعلان",
            ),
        ),
        migrations.AlterField(
            model_name="announcement",
            name="message",
            field=models.TextField(blank=True, default="", verbose_name="نص الإعلان"),
        ),
    ]
