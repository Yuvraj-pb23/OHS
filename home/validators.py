import re
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

def is_valid_email(email_str):
    if not email_str:
        return False
    try:
        validate_email(email_str)
        return True
    except ValidationError:
        return False

def is_valid_phone(phone_str):
    if not phone_str:
        return False
    # Accepts optional '+' followed by digits, spaces, dots, hyphens, min 7, max 15 numeric digits
    return bool(re.match(r"^\+?([0-9]{1,3})?[-. ]?([0-9]{7,15})$", phone_str))

def is_valid_name(name_str, min_len=2, max_len=100):
    if not name_str or len(name_str) < min_len or len(name_str) > max_len:
        return False
    # Allow letters, spaces, hyphens, apostrophes, and dots
    return bool(re.match(r"^[A-Za-z\s\-'\.]+$", name_str))

def is_valid_numeric(val, min_val=0, max_val=None):
    try:
        num = int(val)
        if num < min_val:
            return False
        if max_val is not None and num > max_val:
            return False
        return True
    except (ValueError, TypeError):
        return False

def validate_required_fields(data, required_fields):
    """
    Checks if all required fields are present in the data dict and not empty.
    Returns (True, None) if valid, (False, field_name) if a field is missing/empty.
    """
    for field in required_fields:
        val = data.get(field)
        if val is None or str(val).strip() == "":
            return False, field
    return True, None
