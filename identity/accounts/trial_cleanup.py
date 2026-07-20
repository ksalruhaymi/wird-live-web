"""Superuser trial tools: purge non-protected users safely."""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.utils.postgres_sequences import reset_sequence
from identity.accounts.account_deletion import hard_delete_user_account
from identity.accounts.demo_accounts import (
    DEMO_STUDENT_USERNAME,
    DEMO_SUPERVISOR_USERNAME,
    DEMO_TEACHER_USERNAME,
)

logger = logging.getLogger(__name__)
User = get_user_model()

PROTECTED_DEMO_USERNAMES = frozenset(
    {
        DEMO_SUPERVISOR_USERNAME,
        DEMO_STUDENT_USERNAME,
        DEMO_TEACHER_USERNAME,
        "super",
        "student",
        "teacher",
    }
)


def is_protected_from_bulk_purge(user, *, actor) -> bool:
    if user is None:
        return True
    if actor is not None and user.pk == getattr(actor, "pk", None):
        return True
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "is_demo_account", False):
        return True
    username = (getattr(user, "username", None) or "").strip().lower()
    if username in {u.lower() for u in PROTECTED_DEMO_USERNAMES}:
        return True
    return False


def protected_users_queryset():
    return User.objects.filter(
        Q(is_superuser=True)
        | Q(is_demo_account=True)
        | Q(username__iexact=DEMO_SUPERVISOR_USERNAME)
        | Q(username__iexact=DEMO_STUDENT_USERNAME)
        | Q(username__iexact=DEMO_TEACHER_USERNAME)
    )


def non_protected_users_queryset(*, actor):
    qs = User.objects.exclude(is_superuser=True).exclude(is_demo_account=True)
    qs = qs.exclude(username__iexact=DEMO_SUPERVISOR_USERNAME)
    qs = qs.exclude(username__iexact=DEMO_STUDENT_USERNAME)
    qs = qs.exclude(username__iexact=DEMO_TEACHER_USERNAME)
    if actor is not None and getattr(actor, "pk", None):
        qs = qs.exclude(pk=actor.pk)
    return qs.order_by("id")


def purge_non_protected_users(*, actor) -> dict:
    """
    Delete every user except superusers, demo accounts, and the acting user.
    """
    actor_username = getattr(actor, "username", "") or ""
    started_at = timezone.now()

    victims = list(non_protected_users_queryset(actor=actor))
    deleted_users = []
    totals = {
        "users": 0,
        "recordings_removed": 0,
        "r2_deleted": 0,
        "r2_failed": 0,
    }

    for user in victims:
        if is_protected_from_bulk_purge(user, actor=actor):
            continue
        stats = hard_delete_user_account(user)
        totals["users"] += 1
        totals["recordings_removed"] += int(stats.get("recordings_removed") or 0)
        totals["r2_deleted"] += int(stats.get("r2_deleted") or 0)
        totals["r2_failed"] += int(stats.get("r2_failed") or 0)
        deleted_users.append(
            {"id": stats.get("user_id"), "username": stats.get("username")}
        )

    with transaction.atomic():
        next_user_id = reset_sequence(User._meta.db_table)

    preserved = list(
        protected_users_queryset()
        .order_by("id")
        .values_list("id", "username", "is_superuser", "is_demo_account")
    )
    if actor is not None and not any(row[0] == actor.pk for row in preserved):
        preserved.append(
            (actor.pk, actor.username, actor.is_superuser, actor.is_demo_account)
        )

    result = {
        "deleted_users_count": totals["users"],
        "deleted_users": deleted_users[:50],
        "recordings_removed": totals["recordings_removed"],
        "r2_deleted": totals["r2_deleted"],
        "r2_failed": totals["r2_failed"],
        "next_user_id": next_user_id,
        "preserved_count": User.objects.count(),
        "actor": actor_username,
        "started_at": started_at.isoformat(),
        "finished_at": timezone.now().isoformat(),
    }

    logger.info(
        "trial_purge_non_protected_users actor=%s deleted_users=%s "
        "recordings_removed=%s r2_deleted=%s r2_failed=%s remaining_users=%s",
        actor_username,
        totals["users"],
        totals["recordings_removed"],
        totals["r2_deleted"],
        totals["r2_failed"],
        result["preserved_count"],
    )
    return result
