from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from apps.chat.models import Conversation, Message
from identity.rbac.decorators import permissions_required


@login_required
@permissions_required("dashboard.access", "chat.view")
def chat_conversation_list(request):
    q = (request.GET.get("q") or "").strip()
    qs = Conversation.objects.select_related("student", "teacher").order_by(
        "-updated_at", "-id"
    )
    if q:
        qs = qs.filter(
            Q(student__username__icontains=q)
            | Q(teacher__username__icontains=q)
        )

    rows = []
    for conv in qs[:200]:
        last = conv.messages.order_by("-created_at").first()
        rows.append(
            {
                "conversation": conv,
                "last_message": last,
                "message_count": conv.messages.count(),
            }
        )

    return render(
        request,
        "dashboard/pages/chat/list.html",
        {"rows": rows, "q": q},
    )


@login_required
@permissions_required("dashboard.access", "chat.view")
def chat_conversation_detail(request, pk):
    conv = get_object_or_404(
        Conversation.objects.select_related("student", "teacher"),
        pk=pk,
    )
    messages = conv.messages.select_related("sender").order_by("created_at", "id")
    return render(
        request,
        "dashboard/pages/chat/detail.html",
        {"conversation": conv, "messages": messages},
    )
