"""User type constants and helpers (admin, supervisor, student, teacher)."""

USER_TYPE_ADMIN = 1
USER_TYPE_SUPERVISOR = 3
USER_TYPE_TEACHER = 5
USER_TYPE_STUDENT = 9

USER_TYPE_SLUG_BY_VALUE = {
    USER_TYPE_ADMIN: "admin",
    USER_TYPE_SUPERVISOR: "supervisor",
    USER_TYPE_TEACHER: "teacher",
    USER_TYPE_STUDENT: "student",
}

USER_TYPE_LABEL_AR = {
    USER_TYPE_ADMIN: "مدير النظام",
    USER_TYPE_SUPERVISOR: "مشرف",
    USER_TYPE_TEACHER: "معلم",
    USER_TYPE_STUDENT: "طالب",
}

MOBILE_REGISTRATION_SLUGS = frozenset({"student", "teacher"})

BLOCKED_REGISTRATION_SLUGS = frozenset(
    {
        "admin",
        "supervisor",
        "superuser",
        "staff",
        "مشرف",
        "مدير",
        "مشرفة",
    }
)


def resolve_user_type_slug(user) -> str:
    """API/mobile slug; user_type field is authoritative when set."""
    if getattr(user, "is_superuser", False):
        return "admin"
    value = getattr(user, "user_type", None)
    if value in USER_TYPE_SLUG_BY_VALUE:
        return USER_TYPE_SLUG_BY_VALUE[value]
    role_slugs = {role.slug for role in user.roles.all()}
    if "admin" in role_slugs:
        return "admin"
    if "teacher" in role_slugs:
        return "teacher"
    if "student" in role_slugs:
        return "student"
    if "supervisor" in role_slugs:
        return "supervisor"
    return "unknown"


def primary_user_type_label(user) -> str:
    """
    Dashboard display label for the account's primary type.

    user_type wins over roles so supervisor never overrides student/teacher identity.
    """
    if getattr(user, "is_superuser", False):
        return USER_TYPE_LABEL_AR[USER_TYPE_ADMIN]

    user_type = getattr(user, "user_type", None)
    if user_type in USER_TYPE_LABEL_AR:
        return USER_TYPE_LABEL_AR[user_type]

    return {
        "admin": USER_TYPE_LABEL_AR[USER_TYPE_ADMIN],
        "teacher": USER_TYPE_LABEL_AR[USER_TYPE_TEACHER],
        "student": USER_TYPE_LABEL_AR[USER_TYPE_STUDENT],
        "supervisor": USER_TYPE_LABEL_AR[USER_TYPE_SUPERVISOR],
    }.get(resolve_user_type_slug(user), "unknown")


def user_type_label(user) -> str:
    return primary_user_type_label(user)


def user_list_type_label(user) -> str:
    return primary_user_type_label(user)
