from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.calls.models import CallRecording, CallSession
from identity.accounts.user_types import USER_TYPE_STUDENT, USER_TYPE_TEACHER
from identity.rbac.decorators import permission_required, permissions_required


@login_required
@permission_required("dashboard.access")
def home(request):
    return render(request, "dashboard/pages/home.html")


@login_required
@permissions_required("dashboard.access", "overview.access")
def overview(request):
    User = get_user_model()
    teachers_count = User.objects.filter(
        user_type=USER_TYPE_TEACHER,
        teacher_profile__isnull=False,
    ).count()
    students_count = User.objects.filter(user_type=USER_TYPE_STUDENT).count()
    calls_count = CallSession.objects.count()
    recordings_count = CallRecording.objects.count()

    return render(
        request,
        "dashboard/pages/overview.html",
        {
            "teachers_count": teachers_count,
            "students_count": students_count,
            "calls_count": calls_count,
            "recordings_count": recordings_count,
        },
    )


@login_required
@permission_required("dashboard.access")
def dashboard(request):
    """RBAC entry point — redirects to main dashboard home."""
    return redirect("dashboard:home")
