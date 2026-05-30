from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='AnalyticsVisitor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(max_length=64, unique=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('first_seen_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
                ('visits_count', models.PositiveIntegerField(default=0)),
                ('is_authenticated', models.BooleanField(default=False)),
            ],
            options={'ordering': ['-last_seen_at']},
        ),
        migrations.CreateModel(
            name='InteractionEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('event_type', models.CharField(choices=[('page_flip', 'Page Flip'), ('audio_play', 'Audio Play'), ('audio_complete', 'Audio Complete'), ('tafsir_open', 'Tafsir Open'), ('word_meanings_open', 'Word Meanings Open')], max_length=50)),
                ('path', models.CharField(max_length=255)),
                ('page_number', models.PositiveIntegerField(blank=True, null=True)),
                ('surah_number', models.PositiveIntegerField(blank=True, null=True)),
                ('ayah_number', models.PositiveIntegerField(blank=True, null=True)),
                ('qari', models.CharField(blank=True, max_length=100)),
                ('duration_seconds', models.PositiveIntegerField(blank=True, null=True)),
                ('payload', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('visitor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='events', to='analytics.analyticsvisitor')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='PageView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('path', models.CharField(max_length=255)),
                ('full_path', models.CharField(blank=True, max_length=500)),
                ('page_title', models.CharField(blank=True, max_length=255)),
                ('method', models.CharField(default='GET', max_length=10)),
                ('referrer', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('visitor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='page_views', to='analytics.analyticsvisitor')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddIndex(
            model_name='interactionevent',
            index=models.Index(fields=['event_type', 'created_at'], name='analytics_i_event_t_e601d8_idx'),
        ),
        migrations.AddIndex(
            model_name='interactionevent',
            index=models.Index(fields=['path', 'created_at'], name='analytics_i_path_a_3d5b9b_idx'),
        ),
        migrations.AddIndex(
            model_name='pageview',
            index=models.Index(fields=['path', 'created_at'], name='analytics_p_path_8c989f_idx'),
        ),
        migrations.AddIndex(
            model_name='pageview',
            index=models.Index(fields=['created_at'], name='analytics_p_create_8cc7fa_idx'),
        ),
    ]
