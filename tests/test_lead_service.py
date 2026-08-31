from __future__ import annotations

from typing import Any

import pytest

from app.models import Lead
from app.schemas.callback import ScheduleCallbackRequest
from app.schemas.complete_call import CompleteCallRequest
from app.schemas.whatsapp import HighIntentWhatsAppRequest
from app.services.lead_service import LeadService
from app.utils.phone import PhoneNumberError


class Leads:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    async def upsert_by_phone(self, normalized_phone: str, **values: Any) -> Lead:
        self.values = {"normalized_phone": normalized_phone, **values}
        return Lead(id=7, normalized_phone=normalized_phone)


async def test_every_tool_reaches_the_lead_through_one_normalized_phone() -> None:
    """Catches the three tools disagreeing on the phone format and creating three leads."""
    written: list[str] = []
    for request in (
        HighIntentWhatsAppRequest(call_id="c", phone="8688664337"),
        ScheduleCallbackRequest(
            call_id="c", phone="+91 86886-64337", requested_expression="tomorrow"
        ),
        CompleteCallRequest(call_id="c", phone="918688664337"),
    ):
        leads = Leads()
        service = LeadService(leads)
        if isinstance(request, HighIntentWhatsAppRequest):
            await service.upsert_from_high_intent(request)
        elif isinstance(request, ScheduleCallbackRequest):
            await service.upsert_from_callback(request)
        else:
            await service.upsert_from_complete_call(request)
        written.append(leads.values["normalized_phone"])

    assert written == ["918688664337"] * 3


async def test_a_free_text_product_count_becomes_an_integer_or_nothing() -> None:
    """Catches 'around 200' being written into an integer column and failing the insert."""
    leads = Leads()
    service = LeadService(leads)

    await service.upsert_from_high_intent(
        HighIntentWhatsAppRequest(call_id="c", phone="8688664337", product_count="200")
    )
    assert leads.values["product_count"] == 200

    await service.upsert_from_high_intent(
        HighIntentWhatsAppRequest(call_id="c", phone="8688664337", product_count="around 200")
    )
    assert leads.values["product_count"] is None


async def test_a_single_product_string_is_stored_as_a_list() -> None:
    """Catches the agent's singular products_sold value breaking the JSONB list column."""
    leads = Leads()

    await LeadService(leads).upsert_from_complete_call(
        CompleteCallRequest(call_id="c", phone="8688664337", products_sold="sarees")
    )

    assert leads.values["products_sold"] == ["sarees"]


async def test_a_mid_call_write_only_touches_what_that_call_knows() -> None:
    """Catches an early high-intent payload blanking qualification a later call captured."""
    leads = Leads()

    await LeadService(leads).upsert_from_high_intent(
        HighIntentWhatsAppRequest(call_id="c", phone="8688664337", business_type="jewellery")
    )

    assert "objections" not in leads.values
    assert "classification" not in leads.values
    assert "transcript" not in leads.values


async def test_an_unusable_phone_number_is_rejected_before_any_write() -> None:
    """Catches a malformed number reaching the database and later failing the WhatsApp send."""
    leads = Leads()

    with pytest.raises(PhoneNumberError):
        await LeadService(leads).upsert_from_complete_call(
            CompleteCallRequest(call_id="c", phone="12345")
        )

    assert leads.values == {}
