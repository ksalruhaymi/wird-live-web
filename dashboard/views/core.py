from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from identity.rbac.decorators import permission_required, permissions_required


@login_required
@permission_required("dashboard.access")
def home(request):
    return render(request, "dashboard/pages/home.html")


@login_required
@permissions_required("dashboard.access", "overview.access")
def overview(request):
    User = get_user_model()
    users_count = User.objects.count()

    return render(
        request,
        "dashboard/pages/overview.html",
        {
            "users_count": users_count,
        },
    )


@login_required
@permission_required("dashboard.access")
def dashboard(request):
    """RBAC entry point — redirects to main dashboard home."""
    return redirect("dashboard:home")
