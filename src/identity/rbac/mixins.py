from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import redirect_to_login


class PermissionRequiredMixin:
    """
    Mixin للتحقق من صلاحية المستخدم داخل CBV
    """
    permission_code = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())

        if self.permission_code and not request.user.has_permission(self.permission_code):
            raise PermissionDenied()

        return super().dispatch(request, *args, **kwargs)
