from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("contact", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="contactmessage",
            name="reply_body",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="reply_subject",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="contactmessage",
            name="replied_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="contact_replies",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
