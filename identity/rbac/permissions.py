"""RBAC permission codes used across dashboard and RBAC UI."""

# Dashboard
DASHBOARD_ACCESS = "dashboard.access"
OVERVIEW_ACCESS = "overview.access"
RBAC_ACCESS = "rbac.access"

# Users / roles / permissions (legacy list.* codes kept for decorators)
USERS_LIST = "users.list"
USERS_DETAIL = "users.detail"
USERS_CREATE = "users.create"
USERS_UPDATE = "users.update"
USERS_DELETE = "users.delete"

ROLES_LIST = "roles.list"
ROLES_CREATE = "roles.create"
ROLES_UPDATE = "roles.update"
ROLES_DELETE = "roles.delete"

PERMISSIONS_LIST = "permissions.list"
PERMISSIONS_CREATE = "permissions.create"
PERMISSIONS_UPDATE = "permissions.update"
PERMISSIONS_DELETE = "permissions.delete"
PERMISSIONS_ASSIGN = "permissions.assign_roles"

# Feature modules (dashboard)
TEACHERS_VIEW = "teachers.view"
TEACHERS_UPDATE = "teachers.update"
TEACHERS_AVAILABILITY_VIEW = "teachers.availability.view"

CALLS_VIEW = "calls.view"

SUBSCRIPTIONS_VIEW = "subscriptions.view"
SUBSCRIPTIONS_CREATE = "subscriptions.create"
SUBSCRIPTIONS_UPDATE = "subscriptions.update"
SUBSCRIPTIONS_DELETE = "subscriptions.delete"

ANNOUNCEMENTS_VIEW = "announcements.view"
ANNOUNCEMENTS_CREATE = "announcements.create"
ANNOUNCEMENTS_UPDATE = "announcements.update"
ANNOUNCEMENTS_DELETE = "announcements.delete"

EVALUATIONS_VIEW = "evaluations.view"
RECORDINGS_VIEW = "recordings.view"
CHAT_VIEW = "chat.view"
