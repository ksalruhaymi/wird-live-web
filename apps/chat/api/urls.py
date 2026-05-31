from django.urls import path

from . import views

app_name = "chat_api"

urlpatterns = [
    path("chat/contacts/", views.chat_contacts, name="contacts"),
    path(
        "chat/conversations/",
        views.conversations_endpoint,
        name="conversations",
    ),
    path(
        "chat/conversations/<int:pk>/messages/",
        views.messages_endpoint,
        name="messages",
    ),
]
