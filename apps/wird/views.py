import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import ReminderSetting

REMINDER_ORDER = [
    ReminderSetting.DAILY_WIRD,
    ReminderSetting.MORNING_ADHKAR,
    ReminderSetting.EVENING_ADHKAR,
    ReminderSetting.KAHF_FRIDAY,
]


def _get_or_init_reminders(user):
    """Return a list of ReminderSetting rows for the user, creating missing ones."""
    existing = {r.reminder_type: r for r in ReminderSetting.objects.filter(user=user)}
    result = []
    to_create = []

    for rtype in REMINDER_ORDER:
        if rtype in existing:
            result.append(existing[rtype])
        else:
            obj = ReminderSetting(user=user, reminder_type=rtype, is_enabled=False)
            to_create.append(obj)
            result.append(obj)

    if to_create:
        ReminderSetting.objects.bulk_create(to_create, ignore_conflicts=True)
        # Re-fetch to get PKs
        existing = {r.reminder_type: r for r in ReminderSetting.objects.filter(user=user)}
        result = [existing[rtype] for rtype in REMINDER_ORDER if rtype in existing]

    return result


@login_required
def reminders(request):
    reminder_list = _get_or_init_reminders(request.user)
    return render(request, "wird/reminders.html", {"reminders": reminder_list})


@require_POST
@login_required
def toggle_reminder(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        reminder_type = data.get("reminder_type")
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    valid_types = {t for t, _ in ReminderSetting.REMINDER_TYPES}
    if reminder_type not in valid_types:
        return JsonResponse({"ok": False, "error": "invalid_type"}, status=400)

    obj, _ = ReminderSetting.objects.get_or_create(
        user=request.user,
        reminder_type=reminder_type,
    )
    obj.is_enabled = not obj.is_enabled
    obj.save(update_fields=["is_enabled"])

    return JsonResponse({"ok": True, "is_enabled": obj.is_enabled})


@require_POST
@login_required
def save_reminder_time(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
        reminder_type  = data.get("reminder_type")
        reminder_time  = data.get("reminder_time")  # "HH:MM" string or null
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    valid_types = {t for t, _ in ReminderSetting.REMINDER_TYPES}
    if reminder_type not in valid_types:
        return JsonResponse({"ok": False, "error": "invalid_type"}, status=400)

    # Validate / normalize time string
    parsed_time = None
    if reminder_time:
        try:
            from datetime import time as dt_time
            parts = str(reminder_time).split(":")
            parsed_time = dt_time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            return JsonResponse({"ok": False, "error": "invalid_time"}, status=400)

    obj, _ = ReminderSetting.objects.get_or_create(
        user=request.user,
        reminder_type=reminder_type,
    )
    obj.reminder_time = parsed_time
    obj.save(update_fields=["reminder_time"])

    return JsonResponse({"ok": True, "reminder_time": str(parsed_time) if parsed_time else None})
