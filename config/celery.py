import os

from celery import Celery

# Matches config.settings.__init__ which selects prod/dev via APP_ENV.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
