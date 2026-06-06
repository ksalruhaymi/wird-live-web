from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0007_callpeerrating"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DROP TABLE IF EXISTS chat_message CASCADE;
            DROP TABLE IF EXISTS chat_conversation CASCADE;
            DELETE FROM django_migrations WHERE app = 'chat';
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
