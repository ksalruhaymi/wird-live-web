from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.calls.services import student_display_name
from apps.maqraa.teacher_services import resolve_user_type_slug, teacher_display_name

from .models import Conversation, Message

User = get_user_model()


def _other_party_name(conversation: Conversation, viewer) -> str:
    if viewer.id == conversation.student_id:
        return teacher_display_name(conversation.teacher)
    return student_display_name(conversation.student)


def conversation_to_payload(conversation: Conversation, viewer) -> dict:
    last_msg = (
        conversation.messages.select_related("sender").order_by("-created_at").first()
    )
    return {
        "id": conversation.id,
        "student_id": conversation.student_id,
        "teacher_id": conversation.teacher_id,
        "other_party_name": _other_party_name(conversation, viewer),
        "last_message": last_msg.body if last_msg else "",
        "last_message_at": (
            last_msg.created_at.isoformat() if last_msg else conversation.updated_at.isoformat()
        ),
        "message_count": conversation.messages.count(),
    }


def message_to_payload(message: Message) -> dict:
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "body": message.body,
        "read_at": message.read_at.isoformat() if message.read_at else None,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def list_conversations_for_user(user, *, q: str = "") -> list[dict]:
    if resolve_user_type_slug(user) == "teacher":
        qs = Conversation.objects.filter(teacher=user)
    else:
        qs = Conversation.objects.filter(student=user)

    if q:
        qs = qs.filter(
            Q(student__full_name__icontains=q)
            | Q(student__username__icontains=q)
            | Q(teacher__full_name__icontains=q)
            | Q(teacher__username__icontains=q)
            | Q(teacher__teacher_profile__display_name__icontains=q)
        )

    qs = qs.select_related("student", "teacher").order_by("-updated_at", "-id")
    return [conversation_to_payload(c, user) for c in qs]


def get_or_create_conversation(*, student, teacher) -> Conversation:
    conv, _ = Conversation.objects.get_or_create(
        student=student,
        teacher=teacher,
    )
    return conv


def create_conversation_between(user, other_user_id: int) -> tuple[Conversation | None, str | None]:
    other = User.objects.select_related("teacher_profile", "student_profile").filter(
        pk=other_user_id
    ).first()
    if other is None:
        return None, "المستخدم غير موجود."

    if resolve_user_type_slug(user) == "student":
        if not hasattr(other, "teacher_profile"):
            return None, "يجب اختيار معلّم."
        return get_or_create_conversation(student=user, teacher=other), None

    if resolve_user_type_slug(user) == "teacher":
        if not hasattr(other, "student_profile"):
            return None, "يجب اختيار طالب."
        return get_or_create_conversation(student=other, teacher=user), None

    return None, "نوع الحساب غير مدعوم."


def list_chat_contacts(user) -> list[dict]:
    """Return users the current user may start a chat with."""
    if resolve_user_type_slug(user) == "teacher":
        qs = User.objects.filter(student_profile__isnull=False).order_by(
            "student_profile__display_name", "username"
        )[:500]
        return [
            {
                "id": u.id,
                "full_name": student_display_name(u),
                "user_type": "student",
            }
            for u in qs
        ]

    from apps.maqraa.teacher_services import list_teachers_payload

    teachers = list_teachers_payload(approved_only=True)
    return [
        {
            "id": t["id"],
            "full_name": t["full_name"],
            "user_type": "teacher",
        }
        for t in teachers
    ]


def send_message(conversation: Conversation, sender, body: str) -> tuple[Message | None, str | None]:
    text = (body or "").strip()
    if not text:
        return None, "نص الرسالة مطلوب."

    if sender.id not in {conversation.student_id, conversation.teacher_id}:
        return None, "غير مصرح."

    msg = Message.objects.create(
        conversation=conversation,
        sender=sender,
        body=text,
    )
    conversation.updated_at = timezone.now()
    conversation.save(update_fields=["updated_at"])
    return msg, None
