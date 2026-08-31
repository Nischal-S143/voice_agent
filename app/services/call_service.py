from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.models import CallDirection, EventType
from app.schemas.complete_call import CompleteCallRequest
from app.services.message_builder import build_final_followup


class CallService:
    """Closes out a finished call: persist it, close its callback, follow up."""

    def __init__(
        self,
        session: Any,
        lead_service: Any,
        calls: Any,
        callbacks: Any,
        events: Any,
        followup: Any,
        developer_name: str,
        developer_phone: str = "",
    ) -> None:
        self._session = session
        self._lead_service = lead_service
        self._calls = calls
        self._callbacks = callbacks
        self._events = events
        self._followup = followup
        self._developer_name = developer_name
        self._developer_phone = developer_phone

    async def complete_call(self, request: CompleteCallRequest) -> Any:
        lead = await self._lead_service.upsert_from_complete_call(request)
        # A callback the worker placed already has a call row carrying its
        # direction and callback link; re-deriving them from this payload would
        # relabel the callback as an initial call and orphan the callback row.
        existing = await self._calls.get_by_sarvam_call_id(request.call_id)
        call = await self._calls.upsert_by_sarvam_call_id(
            request.call_id,
            lead_id=lead.id,
            direction=existing.direction if existing else CallDirection.INITIAL,
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
        await self._close_callback(lead.id, call)
        await self._session.commit()
        return await self._followup.send_for_call(
            lead.id,
            call.id,
            request.phone,
            build_final_followup(
                request, self._developer_name, self._developer_phone
            ),
        )

    async def _close_callback(self, lead_id: int, call: Any) -> None:
        """Mark the originating callback COMPLETED now that its call has ended."""
        callback_id = getattr(call, "callback_id", None)
        if callback_id is None:
            return
        completed = await self._callbacks.mark_completed(
            callback_id, now=datetime.now(UTC)
        )
        if completed is None:
            return
        await self._events.append(
            lead_id=lead_id,
            call_id=call.id,
            event_type=EventType.CALLBACK_COMPLETED,
            payload={"callback_id": callback_id},
        )
