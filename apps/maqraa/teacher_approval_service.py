from django.utils import timezone

from .models import TeacherProfile

APPROVAL_STATUS_LABELS_AR = {
    TeacherProfile.ApprovalStatus.PENDING: "قيد المراجعة",
    TeacherProfile.ApprovalStatus.APPROVED: "مقبول",
    TeacherProfile.ApprovalStatus.REJECTED: "مرفوض",
}


def approval_status_label(status: str) -> str:
    return APPROVAL_STATUS_LABELS_AR.get(status, status)


def is_teacher_list_visible(profile: TeacherProfile | None) -> bool:
    if profile is None:
        return False
    return profile.approval_status == TeacherProfile.ApprovalStatus.APPROVED


def approve_teacher_profile(profile: TeacherProfile, reviewer) -> None:
    now = timezone.now()
    profile.approval_status = TeacherProfile.ApprovalStatus.APPROVED
    profile.is_approved = True
    profile.rejection_reason = ""
    profile.approved_at = now
    profile.approved_by = reviewer
    profile.rejected_at = None
    profile.rejected_by = None
    profile.save(
        update_fields=[
            "approval_status",
            "is_approved",
            "rejection_reason",
            "approved_at",
            "approved_by",
            "rejected_at",
            "rejected_by",
            "updated_at",
        ]
    )


def reject_teacher_profile(profile: TeacherProfile, reviewer, reason: str) -> None:
    now = timezone.now()
    profile.approval_status = TeacherProfile.ApprovalStatus.REJECTED
    profile.is_approved = False
    profile.rejection_reason = reason.strip()
    profile.rejected_at = now
    profile.rejected_by = reviewer
    profile.save(
        update_fields=[
            "approval_status",
            "is_approved",
            "rejection_reason",
            "rejected_at",
            "rejected_by",
            "updated_at",
        ]
    )


def teacher_approval_payload(profile: TeacherProfile | None) -> dict:
    if profile is None:
        return {
            "approval_status": TeacherProfile.ApprovalStatus.PENDING,
            "approval_status_label": approval_status_label(
                TeacherProfile.ApprovalStatus.PENDING
            ),
            "rejection_reason": "",
        }
    status = profile.approval_status or TeacherProfile.ApprovalStatus.PENDING
    reason = ""
    if status == TeacherProfile.ApprovalStatus.REJECTED:
        reason = (profile.rejection_reason or "").strip()
    return {
        "approval_status": status,
        "approval_status_label": approval_status_label(status),
        "rejection_reason": reason,
    }
