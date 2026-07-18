"""Central helpers for subscription plan / charge amount display."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.utils.translation import gettext_lazy as _

FREE_PRICE_LABEL = _("مجاني")
CURRENCY_LABEL = "ريال"


def is_free_amount(amount) -> bool:
    """True when amount is a numeric zero (free package / complimentary charge)."""
    if amount is None:
        return False
    try:
        return Decimal(str(amount)) == 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def format_display_price(amount, *, with_currency: bool = False) -> str:
    """
    User-facing price label.

    Free (zero) amounts return only «مجاني» — never «0», currency, or both.
    Paid amounts keep the project's existing numeric style; optionally append ريال.
    """
    if is_free_amount(amount):
        return str(FREE_PRICE_LABEL)

    text = str(amount)
    if with_currency:
        return f"{text} {CURRENCY_LABEL}"
    return text
