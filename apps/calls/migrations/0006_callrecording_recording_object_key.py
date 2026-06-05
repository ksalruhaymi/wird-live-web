from django.db import migrations, models


def _known_bases(apps):
    from django.conf import settings

    bases = []
    configured = (getattr(settings, "AGORA_RECORDING_PUBLIC_BASE_URL", "") or "").strip()
    if configured:
        bases.append(configured if configured.endswith("/") else f"{configured}/")
    for base in (
        "https://media.wird.me/",
        "https://recordings.wird.me/",
    ):
        if base not in bases:
            bases.append(base)
    return bases


def _object_key_from_url(url, bases):
    from urllib.parse import urlparse

    raw = (url or "").strip()
    if not raw:
        return ""
    for base in bases:
        if raw.startswith(base):
            return raw[len(base) :].lstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.path:
        return parsed.path.lstrip("/")
    if not raw.startswith("http"):
        return raw.lstrip("/")
    return ""


def backfill_recording_object_keys(apps, schema_editor):
    CallRecording = apps.get_model("calls", "CallRecording")
    bases = _known_bases(apps)
    for rec in CallRecording.objects.exclude(recording_url="").iterator():
        if (rec.recording_object_key or "").strip():
            continue
        key = _object_key_from_url(rec.recording_url, bases)
        if key:
            rec.recording_object_key = key
            rec.save(update_fields=["recording_object_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0005_alter_callrecording_agora_resource_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="callrecording",
            name="recording_object_key",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
        migrations.RunPython(
            backfill_recording_object_keys,
            migrations.RunPython.noop,
        ),
    ]
