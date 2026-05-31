import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.chat.models import Conversation
from apps.chat.services import (
    conversation_to_payload,
    create_conversation_between,
    list_chat_contacts,
    list_conversations_for_user,
    message_to_payload,
    send_message,
)


def _require_auth(request):
    if request.user.is_authenticated:
        return None
    return JsonResponse(
        {"success": False, "message": "يجب تسجيل الدخول."},
        status=401,
    )


def _parse_json(request) -> dict:
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


@csrf_exempt
@require_GET
def chat_contacts(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    return JsonResponse(
        {"success": True, "contacts": list_chat_contacts(request.user)}
    )


@csrf_exempt
def conversations_endpoint(request):
    if request.method == "GET":
        return conversation_list(request)
    if request.method == "POST":
        return conversation_create(request)
    return JsonResponse({"success": False, "message": "Method not allowed."}, status=405)


@require_GET
def conversation_list(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    q = (request.GET.get("q") or "").strip()
    items = list_conversations_for_user(request.user, q=q)
    return JsonResponse({"success": True, "conversations": items})


@require_POST
def conversation_create(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    data = _parse_json(request)
    other_id = data.get("other_user_id") or data.get("teacher_id") or data.get("student_id")
    try:
        other_id = int(other_id)
    except (TypeError, ValueError):
        other_id = None

    if not other_id:
        return JsonResponse(
            {"success": False, "message": "معرّف الطرف الآخر مطلوب."},
            status=400,
        )

    conv, err = create_conversation_between(request.user, other_id)
    if err:
        return JsonResponse({"success": False, "message": err}, status=400)

    return JsonResponse(
        {
            "success": True,
            "conversation": conversation_to_payload(conv, request.user),
        },
        status=201,
    )


@csrf_exempt
def messages_endpoint(request, pk):
    if request.method == "GET":
        return message_list(request, pk)
    if request.method == "POST":
        return message_create(request, pk)
    return JsonResponse({"success": False, "message": "Method not allowed."}, status=405)


@require_GET
def message_list(request, pk):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    conv = get_object_or_404(
        Conversation.objects.select_related("student", "teacher"),
        pk=pk,
    )
    if request.user.id not in {conv.student_id, conv.teacher_id}:
        return JsonResponse({"success": False, "message": "غير مصرح."}, status=403)

    messages = conv.messages.select_related("sender").order_by("created_at", "id")
    return JsonResponse(
        {
            "success": True,
            "conversation": conversation_to_payload(conv, request.user),
            "messages": [message_to_payload(m) for m in messages],
        }
    )


@require_POST
def message_create(request, pk):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    conv = get_object_or_404(Conversation, pk=pk)
    if request.user.id not in {conv.student_id, conv.teacher_id}:
        return JsonResponse({"success": False, "message": "غير مصرح."}, status=403)

    data = _parse_json(request)
    msg, err = send_message(conv, request.user, data.get("body", ""))
    if err:
        return JsonResponse({"success": False, "message": err}, status=400)

    return JsonResponse(
        {"success": True, "message": message_to_payload(msg)},
        status=201,
    )
