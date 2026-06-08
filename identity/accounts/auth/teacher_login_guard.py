"""Block rejected teachers from signing in or using an existing session."""

from apps.tutoring.models import TeacherProfile
from identity.accounts.user_types import resolve_user_type_slug

REJECTED_TEACHER_LOGIN_MESSAGE = (
    "تم رفض طلبك كمعلّم ولا يمكنك تسجيل الدخول إلى التطبيق."
)

INACTIVE_ACCOUNT_MESSAGE = "الحساب غير مفعّل."


def teacher_login_block_message(user) -> str | None:
    """Return an Arabic login block message for rejected teachers."""
    if user is None:
        return None
    if resolve_user_type_slug(user) != "teacher":
        return None
    try:
        profile = user.teacher_profile
    except TeacherProfile.DoesNotExist:
        return None
    status = profile.approval_status or TeacherProfile.ApprovalStatus.PENDING
    if status == TeacherProfile.ApprovalStatus.REJECTED:
        return REJECTED_TEACHER_LOGIN_MESSAGE
    return None


def session_access_block_message(user) -> str | None:
    """Return a block message for authenticated users who may no longer use the app."""
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    rejected = teacher_login_block_message(user)
    if rejected:
        return rejected
    if not user.is_active:
        return INACTIVE_ACCOUNT_MESSAGE
    return None
