from identity.accounts.auth.session_policy import (
    SESSION_REPLACED_MESSAGE,
    revoke_session_if_superseded,
)


class SingleActiveSessionMiddleware:
    """End non-admin sessions that were replaced by a newer login elsewhere."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if revoke_session_if_superseded(request):
            request._single_session_replaced = True  # noqa: SLF001
        response = self.get_response(request)
        return response


def single_session_replaced_payload() -> dict:
    return {
        "success": False,
        "message": SESSION_REPLACED_MESSAGE,
        "code": "session_replaced",
    }
