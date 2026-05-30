from django.contrib.auth import get_user_model
from ..models import Role, Permission

User = get_user_model()

def users_qs():
    """
    Base queryset for users with their roles preloaded.
    - Used for RBAC dashboards (listing and pagination)
    """
    return (
        User.objects
        .prefetch_related("roles")
        .order_by("username")
    )


def roles_qs():
    """
    Base queryset for roles with their permissions preloaded.
    - Helps avoid N+1 queries when listing roles and their permissions
    """
    return (
        Role.objects
        .prefetch_related("permissions")
        .order_by("name")
    )


def permissions_qs():
    """
    Base queryset for permissions ordered by module then code.
    - Useful for grouping permissions by module in the UI
    """
    return Permission.objects.order_by("module", "code")
