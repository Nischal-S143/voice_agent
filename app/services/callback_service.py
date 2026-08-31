from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.models import Call, CallbackAttemptStatus, CallDirection, EventType, Lead
from app.schemas.callback import ScheduleCallbackRequest
from app.services.outbound_caller import OutboundCallRequest, SarvamOutboundCaller

RETRY_DELAY = timedelta(minutes=5)


class CallbackService:
    """Schedules callbacks and, on the worker tick, dials the due ones."""

    def __init__(
        self,
        session: Any,
        lead_service: Any,
        calls: Any,
        callbacks: Any,
        attempts: Any,
        events: Any,
        outbound: SarvamOutboundCaller,
    ) -> None:
        self._session = session
        self._lead_service = lead_service
        self._calls = calls
        self._callbacks = callbacks
        self._attempts = attempts
        self._events = events
        self._outbound = outbound

    async def schedule(self, request: ScheduleCallbackRequest) -> dict[str, object]:
        if request.callback_time is None:
            return {"success": False, "error": "callback_time_required"}
        lead = await self._lead_service.upsert_from_callback(request)
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
        """Dial one due callback. Returns whether there was one to dial."""
        now = datetime.now(UTC)
        callback = await self._callbacks.claim_due(now=now)
        if callback is None:
            return False
        await self._events.append(
            lead_id=callback.lead_id,
            call_id=callback.source_call_id,
            event_type=EventType.CALLBACK_ATTEMPTED,
            payload={"callback_id": callback.id, "attempt": callback.attempt_count},
        )
        # Commit the claim before dialling: the row is now IN_PROGRESS, so a
        # crash mid-call leaves it owned rather than dialled twice.
        await self._session.commit()

        lead = await self._session.get(Lead, callback.lead_id)
        source_call = await self._session.get(Call, callback.source_call_id)
        result = await self._outbound.place_call(
            OutboundCallRequest(
                callback_id=callback.id,
                phone=lead.normalized_phone,
                context=_previous_context(lead, source_call),
            )
        )

        if result.success and result.call_id:
            call = await self._calls.upsert_by_sarvam_call_id(
                result.call_id,
                lead_id=lead.id,
                direction=CallDirection.CALLBACK,
                status="active",
                callback_id=callback.id,
            )
            await self._callbacks.mark_dialled(callback)
            await self._attempts.record(
                callback_id=callback.id,
                attempt_number=callback.attempt_count,
                status=CallbackAttemptStatus.PLACED,
                call_id=call.id,
                provider_attempt_id=result.provider_attempt_id,
            )
            event_type = EventType.CALLBACK_TRIGGERED
        else:
            error = result.error or "outbound_call_failed"
            await self._callbacks.mark_failed(
                callback,
                error=error,
                next_attempt_at=now + RETRY_DELAY if result.retryable else None,
            )
            await self._attempts.record(
                callback_id=callback.id,
                attempt_number=callback.attempt_count,
                status=CallbackAttemptStatus.FAILED,
                error=error,
                retryable=result.retryable,
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


def _previous_context(lead: Any, source_call: Any) -> dict[str, object]:
    """Compact recap the callback agent opens with, so the lead is not re-qualified."""
    return {
        "is_callback": True,
        "previous_business_type": getattr(lead, "business_type", None),
        "previous_product_count": getattr(lead, "product_count", None),
        "previous_budget": getattr(lead, "budget", None),
        "previous_timeline": getattr(lead, "timeline", None),
        "previous_features": getattr(lead, "required_features", None) or [],
        "previous_objection": (getattr(lead, "objections", None) or [None])[0],
        "previous_summary": getattr(source_call, "summary", None),
    }
