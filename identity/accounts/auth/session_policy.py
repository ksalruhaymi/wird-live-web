"""Single active session policy: one device at a time except admins."""

from __future__ import annotations

from django.contrib.auth import logout
from django.contrib.sessions.models import Session

from identity.accounts.user_types import USER_TYPE_ADMIN, resolve_user_type_slug


SESSION_REPLACED_MESSAGE = (
    "تم تسجيل الدخول من جهاز آخر. تم إنهاء هذه الجلسة."
)


def is_multi_device_login_allowed(user) -> bool:
    """Admins may stay signed in on multiple devices at once."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "user_type", None) == USER_TYPE_ADMIN:
        return True
    if resolve_user_type_slug(user) == "admin":
        return True
    roles = getattr(user, "roles", None)
    if roles is not None and roles.filter(slug="admin").exists():
        return True
    return False


def enforce_single_active_session(request, user) -> None:
    """Keep only the current Django session for non-admin users.

    Call immediately after a successful ``login()``.
    """
    if is_multi_device_login_allowed(user):
        # Clear any previous single-session marker so admin is never blocked.
        if getattr(user, "active_session_key", None):
            type(user).objects.filter(pk=user.pk).update(active_session_key="")
            user.active_session_key = ""
        return

    if not request.session.session_key:
        request.session.save()

    current_key = request.session.session_key
    if not current_key:
        return

    previous_key = (getattr(user, "active_session_key", None) or "").strip()
    if previous_key and previous_key != current_key:
        Session.objects.filter(session_key=previous_key).delete()

    # Also drop any other decoded sessions for this user (legacy / race safety).
    _delete_other_user_sessions(user_id=user.pk, keep_session_key=current_key)

    if previous_key != current_key:
        type(user).objects.filter(pk=user.pk).update(active_session_key=current_key)
        user.active_session_key = current_key


def _delete_other_user_sessions(*, user_id: int, keep_session_key: str) -> None:
    user_id_str = str(user_id)
    to_delete: list[str] = []
    for session in Session.objects.exclude(session_key=keep_session_key).iterator(
        chunk_size=200
    ):
        try:
            data = session.get_decoded()
        except Exception:
            continue
        if data.get("_auth_user_id") == user_id_str:
            to_delete.append(session.session_key)
    if to_delete:
        Session.objects.filter(session_key__in=to_delete).delete()


def revoke_session_if_superseded(request) -> bool:
    """Logout when this request's session is no longer the user's active one.

    Returns True if the session was revoked.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    if is_multi_device_login_allowed(user):
        return False

    active_key = (getattr(user, "active_session_key", None) or "").strip()
    if not active_key:
        return False

    current_key = getattr(request.session, "session_key", None) or ""
    if current_key and current_key == active_key:
        return False

    logout(request)
    return True
