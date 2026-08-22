from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models import Call, CallDirection, EventType, Lead
from app.schemas.callback import ScheduleCallbackRequest
from app.services.outbound_caller import OutboundCallRequest, SarvamOutboundCaller
from app.utils.phone import normalize_indian_phone


class CallbackService:
    def __init__(
        self,
        session: Any,
        leads: Any,
        calls: Any,
        callbacks: Any,
        events: Any,
        outbound: SarvamOutboundCaller,
    ) -> None:
        self._session = session
        self._leads = leads
        self._calls = calls
        self._callbacks = callbacks
        self._events = events
        self._outbound = outbound

    async def schedule(self, request: ScheduleCallbackRequest) -> dict[str, object]:
        if request.callback_time is None:
            return {"success": False, "error": "callback_time_required"}
        lead = await self._leads.upsert_by_phone(
            normalize_indian_phone(request.phone),
            classification=request.lead_classification,
        )
        call = await self._calls.upsert_by_sarvam_call_id(
            request.call_id,
            lead_id=lead.id,
            direction=CallDirection.INITIAL,
            status="active",
            summary=request.summary,
        )
        callback = await self._callbacks.schedule(
            lead_id=lead.id,
            source_call_id=call.id,
            requested_expression=request.requested_expression,
            scheduled_at=request.callback_time,
            timezone=request.timezone,
            reason=request.reason,
        )
        await self._events.append(
            lead_id=lead.id,
            call_id=call.id,
            event_type=EventType.CALLBACK_SCHEDULED,
            payload={"callback_id": callback.id},
        )
        await self._session.commit()
        return {
            "success": True,
            "callback_id": str(callback.id),
            "scheduled_for": request.callback_time.isoformat(),
        }

    async def process_due(self) -> bool:
        now = datetime.now(UTC)
        callback = await self._callbacks.claim_due(now=now)
        if callback is None:
            return False
        await self._session.commit()

        lead = await self._session.get(Lead, callback.lead_id)
        source_call = await self._session.get(Call, callback.source_call_id)
        context = {
            "is_callback": True,
            "previous_business_type": getattr(lead, "business_type", None),
            "previous_product_count": getattr(lead, "product_count", None),
            "previous_budget": getattr(lead, "budget", None),
            "previous_timeline": getattr(lead, "timeline", None),
            "previous_features": getattr(lead, "required_features", None) or [],
            "previous_objection": (getattr(lead, "objections", None) or [None])[0],
            "previous_summary": getattr(source_call, "summary", None),
        }
        result = await self._outbound.place_call(
            OutboundCallRequest(
                callback_id=callback.id,
                phone=lead.normalized_phone,
                context=context,
            )
        )
        if result.success and result.call_id:
            await self._calls.upsert_by_sarvam_call_id(
                result.call_id,
                lead_id=lead.id,
                direction=CallDirection.CALLBACK,
                status="triggered",
            )
            await self._callbacks.mark_triggered(callback, now=now)
            event_type = EventType.CALLBACK_TRIGGERED
        else:
            retry_at = now + timedelta(minutes=5) if result.retryable else None
            await self._callbacks.mark_failed(
                callback,
                error=result.error or "outbound_call_failed",
                next_attempt_at=retry_at,
            )
            event_type = EventType.CALLBACK_FAILED
        await self._events.append(
            lead_id=lead.id,
            call_id=source_call.id,
            event_type=event_type,
            payload={"callback_id": callback.id, "error": result.error},
        )
        await self._session.commit()
        return True
