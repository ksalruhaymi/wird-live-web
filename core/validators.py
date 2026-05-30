from django.core.exceptions import ValidationError
from core.services.phone_service import normalize_phone_number


def validate_phone(value):
    if not value:
        return

    try:
        normalize_phone_number(value, region="SA")
    except ValueError as e:
        raise ValidationError(str(e))