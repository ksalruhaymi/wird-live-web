"""Central permission resolver with explicit alias groups (dual-read)."""

from __future__ import annotations

from identity.rbac.permission_aliases import ALIAS_INDEX


def resolve_permission_codes(code: str) -> frozenset[str]:
    """
    Return the codes to check for a permission request.

    Known codes expand to their alias group; unknown codes resolve to themselves only.
    """
    normalized = (code or "").strip()
    if not normalized:
        return frozenset()
    return ALIAS_INDEX.get(normalized, frozenset({normalized}))


def user_has_permission(user, code: str) -> bool:
    """True if the user holds any permission in the resolved alias group."""
    codes = resolve_permission_codes(code)
    if not codes:
        return False
    return user.roles.filter(permissions__code__in=codes).exists()
