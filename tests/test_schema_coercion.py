"""The agent sends flat strings where the schema declares lists.

Sarvam's extracted variables are comma-separated text, not arrays. Every one
of those rejections cost a whole call: 422 before the handler ran, so no lead
was saved and no WhatsApp was sent.
"""
from __future__ import annotations

import pytest

from app.schemas.complete_call import CompleteCallRequest
from app.schemas.whatsapp import HighIntentWhatsAppRequest

PHONE = "+917887083856"


def _complete(**values: object) -> CompleteCallRequest:
    return CompleteCallRequest(call_id="c1", phone=PHONE, **values)


def test_a_comma_separated_feature_string_becomes_separate_features() -> None:
    """Catches the exact 422 a live call hit: required_features sent as text."""
    request = HighIntentWhatsAppRequest(
        call_id="c1", phone=PHONE,
        required_features="payment gateway, COD, inventory management",
    )
    assert request.required_features == ["payment gateway", "COD", "inventory management"]


def test_complete_call_splits_features_and_objections() -> None:
    """Catches a completion losing every feature and objection the lead named."""
    request = _complete(
        required_features="payment gateway, COD",
        objections="maintenance cost, delivery time",
    )
    assert request.required_features == ["payment gateway", "COD"]
    assert request.objections == ["maintenance cost", "delivery time"]


def test_a_quoted_statement_containing_a_comma_is_not_shredded() -> None:
    """Catches splitting a customer's sentence into fragments quoted back at them."""
    said = "mujhe do hafte mein launch karna hai, budget 80k tak hai"

    request = _complete(important_statements=said)

    assert request.important_statements == [said]


def test_arrays_are_left_exactly_as_they_arrive() -> None:
    """Catches the coercion mangling a correctly configured tool."""
    request = _complete(
        required_features=["payment gateway", "COD"],
        objections=["price"],
        important_statements=["pehla", "doosra"],
    )
    assert request.required_features == ["payment gateway", "COD"]
    assert request.objections == ["price"]
    assert request.important_statements == ["pehla", "doosra"]


@pytest.mark.parametrize("empty", ["", "   ", ",", " , , ", None])
def test_an_empty_value_becomes_an_empty_list_not_a_blank_entry(empty: object) -> None:
    """Catches a blank string becoming [''], which reads as a missing feature."""
    request = _complete(required_features=empty, important_statements=empty)

    assert request.required_features == []
    assert request.important_statements == []


def test_surrounding_whitespace_is_trimmed_from_each_entry() -> None:
    """Catches ' COD' and 'COD' being stored as different features."""
    request = _complete(required_features="  payment gateway ,COD ,  inventory  ")

    assert request.required_features == ["payment gateway", "COD", "inventory"]


def test_a_single_feature_with_no_comma_still_becomes_a_list() -> None:
    """Catches the one-item case regressing to a bare string."""
    assert _complete(required_features="payment gateway").required_features == [
        "payment gateway"
    ]
