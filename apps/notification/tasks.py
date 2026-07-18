"""No Celery tasks in this app.

Broadcast email tasks live in ``apps.messaging.tasks``.
This module exists so Celery ``autodiscover_tasks`` can import it safely.
"""
