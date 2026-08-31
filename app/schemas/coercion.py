"""Accept the shapes the voice agent actually sends for list fields.

Sarvam's extracted variables are flat strings: required_features arrives as
"payment gateway, COD, inventory management" rather than an array. Rejecting
that costs the whole call -- the lead is never saved and no WhatsApp is sent --
so the API takes either shape and normalizes here.
"""
from __future__ import annotations

from typing import Any


def _clean(items: list[Any]) -> list[str]:
    return [text for text in (str(item).strip() for item in items if item is not None) if text]


def split_list(value: Any) -> Any:
    """Short tags: split a comma-separated string into separate entries."""
    if value is None:
        return []
    if isinstance(value, str):
        return _clean(value.split(","))
    if isinstance(value, (list, tuple)):
        return _clean(list(value))
    return value


def wrap_list(value: Any) -> Any:
    """Whole sentences: keep a string intact.

    A quoted customer statement routinely contains commas, so splitting one
    would shred the very words the follow-up quotes back to them.
    """
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return _clean(list(value))
    return value
