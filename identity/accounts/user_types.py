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
    value = getattr(user, "user_type", None)
    if value in USER_TYPE_SLUG_BY_VALUE:
        return USER_TYPE_SLUG_BY_VALUE[value]
    if hasattr(user, "teacher_profile"):
        return "teacher"
    if hasattr(user, "student_profile"):
        return "student"
    if getattr(user, "is_superuser", False):
        return "admin"
    return "unknown"


def user_type_label(user) -> str:
    value = getattr(user, "user_type", None)
    if value in USER_TYPE_LABEL_AR:
        return USER_TYPE_LABEL_AR[value]
    slug = resolve_user_type_slug(user)
    return {
        "admin": USER_TYPE_LABEL_AR[USER_TYPE_ADMIN],
        "supervisor": USER_TYPE_LABEL_AR[USER_TYPE_SUPERVISOR],
        "teacher": USER_TYPE_LABEL_AR[USER_TYPE_TEACHER],
        "student": USER_TYPE_LABEL_AR[USER_TYPE_STUDENT],
    }.get(slug, slug)


def user_list_type_label(user) -> str:
    """
    Primary user-type column for RBAC users list (display only).

    Roles are shown separately; this label must not let an extra supervisor role
    override a student/teacher base type.
    """
    if getattr(user, "is_superuser", False):
        return USER_TYPE_LABEL_AR[USER_TYPE_ADMIN]

    role_slugs = {role.slug for role in user.roles.all()}

    if "admin" in role_slugs:
        return USER_TYPE_LABEL_AR[USER_TYPE_ADMIN]

    user_type = getattr(user, "user_type", None)

    if user_type == USER_TYPE_STUDENT:
        return USER_TYPE_LABEL_AR[USER_TYPE_STUDENT]

    if user_type == USER_TYPE_TEACHER:
        return USER_TYPE_LABEL_AR[USER_TYPE_TEACHER]

    if user_type == USER_TYPE_ADMIN:
        return USER_TYPE_LABEL_AR[USER_TYPE_ADMIN]

    if user_type == USER_TYPE_SUPERVISOR or "supervisor" in role_slugs:
        return USER_TYPE_LABEL_AR[USER_TYPE_SUPERVISOR]

    return "unknown"
