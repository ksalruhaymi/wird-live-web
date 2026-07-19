from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VerifiedStorePurchase:
    """Result of a successful App Store / Play consumable purchase verification."""

    payment_method: str
    product_id: str
    transaction_id: str
    environment: str  # "sandbox" | "production"
    product_kind: str  # always "consumable"
    package_or_bundle_id: str
    minutes: int
    needs_google_consume: bool = False
    google_purchase_token: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def needs_google_acknowledge(self) -> bool:
        """Alias kept for older call sites; consumables use consume."""
        return self.needs_google_consume


class StoreVerificationError(Exception):
    """Raised when a store purchase cannot be verified."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
