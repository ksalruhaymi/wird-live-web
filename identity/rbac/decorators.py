# src/identity/rbac/decorators.py
from functools import wraps

from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import redirect_to_login


def permissions_required(*codes: str):
    """Require all listed RBAC permission codes."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            for code in codes:
                if not user.has_permission(code):
                    raise PermissionDenied()
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def permission_required(code: str):
    """
    Decorator to check if the user has a specific RBAC permission.

    Usage:
        @permission_required("dashboard.access")
        def some_view(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user

            # If user is not authenticated -> redirect to login
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())

            # If user is authenticated but does NOT have the permission -> 403
            if not user.has_permission(code):
                raise PermissionDenied()

            # User is allowed
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
