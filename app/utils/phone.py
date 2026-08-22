import re


class PhoneNumberError(ValueError):
    """Raised when a phone number cannot be normalized for Whapi."""


def normalize_indian_phone(phone: str) -> str:
    raw = phone.strip()
    if not raw:
        raise PhoneNumberError("invalid_indian_phone")

    compact = re.sub(r"[\s()-]", "", raw)
    if compact.startswith("+"):
        compact = compact[1:]
    if not compact.isdigit():
        raise PhoneNumberError("invalid_indian_phone")

    if len(compact) == 10:
        compact = f"91{compact}"
    if len(compact) != 12 or not compact.startswith("91"):
        raise PhoneNumberError("invalid_indian_phone")

    subscriber = compact[2:]
    if subscriber[0] not in "6789":
        raise PhoneNumberError("invalid_indian_phone")
    return compact
