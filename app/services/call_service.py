from __future__ import annotations

from typing import Any

from app.models import CallDirection, EventType
from app.schemas.complete_call import CompleteCallRequest
from app.services.message_builder import build_final_followup
from app.utils.phone import normalize_indian_phone


class CallService:
    def __init__(
        self,
        session: Any,
        leads: Any,
        calls: Any,
        events: Any,
        followup: Any,
        developer_name: str,
    ) -> None:
        self._session = session
        self._leads = leads
        self._calls = calls
        self._events = events
        self._followup = followup
        self._developer_name = developer_name

    async def complete_call(self, request: CompleteCallRequest) -> Any:
        products = request.products_sold
        if isinstance(products, str):
            products = [products]
        product_count = (
            int(request.product_count)
            if request.product_count and request.product_count.isdigit()
            else None
        )
        lead = await self._leads.upsert_by_phone(
            normalize_indian_phone(request.phone),
            business_type=request.business_type,
            products_sold=products,
            product_count=product_count,
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
        call = await self._calls.upsert_by_sarvam_call_id(
            request.call_id,
            lead_id=lead.id,
            direction=CallDirection.INITIAL,
            status="completed",
            language=request.language,
            summary=request.summary,
            important_statements=request.important_statements,
            transcript=request.transcript,
            started_at=request.started_at,
            ended_at=request.ended_at,
        )
        await self._events.append(
            lead_id=lead.id,
            call_id=call.id,
            event_type=EventType.CALL_COMPLETED,
            payload={"sarvam_call_id": request.call_id},
        )
        await self._session.commit()
        return await self._followup.send_for_call(
            lead.id,
            call.id,
            request.phone,
            build_final_followup(request, self._developer_name),
        )
