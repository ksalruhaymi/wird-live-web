"""
Explicit permission alias groups for dual-read during legacy → web/mobile/shared migration.

Each group is a set of equivalent codes: holding ANY member satisfies a check for ANY
member in the same group. Codes not listed here resolve to themselves only.
"""

from __future__ import annotations

# Each frozenset is one equivalence group (ANY semantics within the group).
PERMISSION_ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    # Dashboard / settings
    frozenset({"dashboard.access", "web.dashboard.access"}),
    frozenset({"overview.access", "web.dashboard.overview.view"}),
    frozenset(
        {
            "settings.access",
            "web.settings.login.view",
            "web.settings.login.update",
        }
    ),
    # Subscriptions (transitional broad view group)
    frozenset(
        {
            "subscriptions.view",
            "web.subscriptions.plans.view",
            "web.subscriptions.students.view",
        }
    ),
    frozenset({"subscriptions.create", "web.subscriptions.plans.create"}),
    frozenset(
        {
            "subscriptions.update",
            "web.subscriptions.plans.update",
            "web.subscriptions.students.update",
            "web.subscriptions.plans.toggle",
        }
    ),
    frozenset(
        {
            "subscriptions.delete",
            "web.subscriptions.plans.delete",
            "web.subscriptions.students.delete",
        }
    ),
    # Announcements
    frozenset({"announcements.view", "web.announcements.view"}),
    frozenset({"announcements.create", "web.announcements.create"}),
    frozenset(
        {
            "announcements.update",
            "web.announcements.update",
            "web.announcements.toggle",
        }
    ),
    frozenset({"announcements.delete", "web.announcements.delete"}),
    # App notifications
    frozenset({"app_notifications.view", "web.app_notifications.view"}),
    frozenset({"app_notifications.create", "web.app_notifications.create"}),
    frozenset(
        {
            "app_notifications.update",
            "web.app_notifications.update",
            "web.app_notifications.toggle",
        }
    ),
    frozenset({"app_notifications.delete", "web.app_notifications.delete"}),
    # Mobile app config
    frozenset({"mobile_app_config.view", "web.mobile_app_config.view"}),
    frozenset({"mobile_app_config.update", "web.mobile_app_config.update"}),
    # Dashboard users
    frozenset(
        {
            "users.view",
            "web.users.teachers.view",
            "web.users.students.view",
        }
    ),
    frozenset({"users.teachers.view", "web.users.teachers.view"}),
    frozenset({"users.students.view", "web.users.students.view"}),
    # Calls / teachers / evaluations
    frozenset({"calls.view", "web.calls.view"}),
    frozenset({"appointments.view", "web.appointments.view"}),
    frozenset({"appointments.manage_schedule", "web.appointments.manage_schedule"}),
    frozenset({"appointments.manage_bookings", "web.appointments.manage_bookings"}),
    frozenset({"appointments.view_all", "web.appointments.view_all"}),
    frozenset({"appointments.override_status", "web.appointments.override_status"}),
    frozenset({"teachers.availability.view", "web.teachers.availability.view"}),
    frozenset({"evaluations.view", "web.evaluations.view"}),
    frozenset({"evaluations.create", "web.evaluations.questions.create"}),
    frozenset(
        {
            "evaluations.update",
            "web.evaluations.questions.update",
            "web.evaluations.questions.toggle",
        }
    ),
    frozenset({"evaluations.delete", "web.evaluations.questions.delete"}),
    # Recordings (transitional monitoring view group; delete stays delete-only)
    frozenset(
        {
            "recordings.view",
            "web.recordings.view",
            "shared.recordings.play_all",
        }
    ),
    frozenset({"recordings.delete", "web.recordings.delete"}),
    # Mobile teacher management (cross-scope)
    frozenset({"management.teachers.view", "mobile.management.teachers.view"}),
    frozenset({"management.teachers.approve", "mobile.management.teachers.approve"}),
    frozenset({"management.teachers.reject", "mobile.management.teachers.reject"}),
    # RBAC admin UI
    frozenset({"rbac.access", "web.rbac.access"}),
    frozenset({"users.list", "users.detail", "web.rbac.users.view"}),
    frozenset({"users.create", "web.rbac.users.create"}),
    frozenset({"users.update", "web.rbac.users.update"}),
    frozenset({"users.delete", "web.rbac.users.delete"}),
    frozenset({"roles.list", "roles.view", "web.rbac.roles.view"}),
    frozenset({"roles.create", "web.rbac.roles.create"}),
    frozenset({"roles.update", "web.rbac.roles.update"}),
    frozenset({"roles.delete", "web.rbac.roles.delete"}),
    frozenset({"permissions.list", "permissions.view", "web.rbac.permissions.view"}),
    frozenset({"permissions.create", "web.rbac.permissions.create"}),
    frozenset({"permissions.update", "web.rbac.permissions.update"}),
    frozenset({"permissions.delete", "web.rbac.permissions.delete"}),
    frozenset(
        {
            "permissions.assign_roles",
            "permissions.assign",
            "web.rbac.permissions.assign",
        }
    ),
    # Shared / mobile (own recordings; not linked to recordings.view)
    frozenset({"shared.recordings.play_own", "mobile.recordings.list_own.view"}),
)


def build_alias_index(
    groups: tuple[frozenset[str], ...] = PERMISSION_ALIAS_GROUPS,
) -> dict[str, frozenset[str]]:
    """Map each known code to its full equivalence group."""
    index: dict[str, frozenset[str]] = {}
    for group in groups:
        for code in group:
            index[code] = group
    return index


ALIAS_INDEX: dict[str, frozenset[str]] = build_alias_index()
