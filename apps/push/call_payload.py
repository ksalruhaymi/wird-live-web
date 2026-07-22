"""Pure helpers for incoming-call push payloads (no secrets / Agora tokens)."""

from __future__ import annotations

import uuid

_CALL_UUID_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def call_kit_uuid(call_id: int) -> str:
    """Stable UUID for CallKit / Android CallStyle so cancel matches ring."""
    return str(uuid.uuid5(_CALL_UUID_NS, f"wird.live/call/{int(call_id)}"))


def build_incoming_call_data(
    *,
    call_id: int,
    caller_name: str,
    caller_id: int | None,
    session_type: str,
    action: str = "ring",
) -> dict[str, str]:
    """FCM / APNs data map — all values are strings (FCM requirement)."""
    st = (session_type or "audio").strip().lower()
    if st not in {"audio", "video"}:
        st = "audio"
    act = (action or "ring").strip().lower()
    if act not in {"ring", "cancel"}:
        act = "ring"
    payload = {
        "type": "incoming_call",
        "action": act,
        "call_id": str(int(call_id)),
        "call_uuid": call_kit_uuid(call_id),
        "session_type": st,
        "caller_name": (caller_name or "طالب").strip()[:80] or "طالب",
    }
    if caller_id is not None:
        payload["caller_id"] = str(int(caller_id))
    return payload


def parse_incoming_call_data(raw: dict | None) -> dict | None:
    """Validate an incoming_call data map. Returns None if incomplete."""
    if not isinstance(raw, dict):
        return None
    type_ = str(raw.get("type") or "").strip().lower()
    if type_ != "incoming_call":
        return None
    call_id_raw = str(raw.get("call_id") or "").strip()
    if not call_id_raw.isdigit():
        return None
    call_id = int(call_id_raw)
    if call_id <= 0:
        return None
    action = str(raw.get("action") or "ring").strip().lower()
    if action not in {"ring", "cancel"}:
        return None
    call_uuid = str(raw.get("call_uuid") or "").strip() or call_kit_uuid(call_id)
    session_type = str(raw.get("session_type") or "audio").strip().lower()
    if session_type not in {"audio", "video"}:
        session_type = "audio"
    caller_name = str(raw.get("caller_name") or "طالب").strip() or "طالب"
    caller_id = None
    caller_id_raw = str(raw.get("caller_id") or "").strip()
    if caller_id_raw.isdigit():
        caller_id = int(caller_id_raw)
    return {
        "type": "incoming_call",
        "action": action,
        "call_id": call_id,
        "call_uuid": call_uuid,
        "session_type": session_type,
        "caller_name": caller_name,
        "caller_id": caller_id,
    }
