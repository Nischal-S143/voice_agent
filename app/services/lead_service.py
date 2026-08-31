from __future__ import annotations

from typing import Any

from app.schemas.callback import ScheduleCallbackRequest
from app.schemas.complete_call import CompleteCallRequest
from app.schemas.whatsapp import HighIntentWhatsAppRequest
from app.utils.phone import normalize_indian_phone


def _product_count(raw: str | None) -> int | None:
    """The agent sends product counts as free text; keep only a clean integer."""
    return int(raw) if raw and raw.isdigit() else None


def _products(raw: str | list[str] | None) -> list[str] | None:
    return [raw] if isinstance(raw, str) else raw


class LeadService:
    """Single owner of how a tool payload turns into the lead record.

    Every endpoint reaches the lead through here, so the three tools cannot
    drift in how they normalize a phone number or read a product count. The
    repository only writes the keys it is given, so a mid-call payload never
    erases qualification captured later by a fuller one.
    """

    def __init__(self, leads: Any) -> None:
        self._leads = leads

    async def upsert_from_high_intent(self, request: HighIntentWhatsAppRequest) -> Any:
        return await self._leads.upsert_by_phone(
            normalize_indian_phone(request.phone),
            business_type=request.business_type,
            product_count=_product_count(request.product_count),
            required_features=request.required_features,
            budget=request.budget_range,
            timeline=request.timeline,
        )

    async def upsert_from_callback(self, request: ScheduleCallbackRequest) -> Any:
        return await self._leads.upsert_by_phone(
            normalize_indian_phone(request.phone),
            classification=request.lead_classification,
        )

    async def upsert_from_complete_call(self, request: CompleteCallRequest) -> Any:
        return await self._leads.upsert_by_phone(
            normalize_indian_phone(request.phone),
            business_type=request.business_type,
            products_sold=_products(request.products_sold),
            product_count=_product_count(request.product_count),
            required_features=request.required_features,
            budget=request.budget_range,
            timeline=request.timeline,
            urgency=request.urgency,
            decision_maker=request.decision_maker,
            objections=request.objections,
            preferred_language=request.language,
            classification=request.lead_classification,
            classification_reason=request.classification_reason,
        )
