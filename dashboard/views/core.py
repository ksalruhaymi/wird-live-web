from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.calls.models import CallRecording, CallSession
from identity.accounts.user_role_sync import student_users_queryset, teacher_users_queryset
from identity.rbac.decorators import permission_required, permissions_required


@login_required
@permission_required("dashboard.access")
def home(request):
    return render(request, "dashboard/pages/home.html")


@login_required
@permissions_required("dashboard.access", "overview.access")
def overview(request):
    teachers_count = teacher_users_queryset(viewer=request.user).count()
    students_count = student_users_queryset().count()
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
