import pytest

from app.utils.phone import PhoneNumberError, normalize_indian_phone


@pytest.mark.parametrize(
    "raw",
    ["+91 86886 64337", "8688664337", "918688664337", "(86886) 64337"],
)
def test_normalizes_supported_indian_formats(raw: str) -> None:
    assert normalize_indian_phone(raw) == "918688664337"


@pytest.mark.parametrize(
    "raw", ["", "12345", "108688664337", "+1 8688664337", "91abcdefghij"]
)
def test_rejects_malformed_or_non_indian_numbers(raw: str) -> None:
    with pytest.raises(PhoneNumberError):
        normalize_indian_phone(raw)
