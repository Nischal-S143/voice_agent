from __future__ import annotations

from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from app.models import EventType
from app.services.storage_service import StorageServiceError
from app.services.whapi_service import WhapiProviderError, WhapiResult


class FollowupResult(BaseModel):
    success: bool
    text_sent: bool
    resume_sent: bool
    architecture_sent: bool


class FollowupService:
    def __init__(
        self,
        whapi: Any,
        storage: Any,
        events: Any,
        session: Any,
        resume_object_path: str,
        architecture_object_path: str,
    ) -> None:
        self._whapi = whapi
        self._storage = storage
        self._events = events
        self._session = session
        self._resume_path = resume_object_path
        self._architecture_path = architecture_object_path

    async def send_for_call(
        self, lead_id: int, call_id: int, phone: str, message: str
    ) -> FollowupResult:
        text_sent = await self._attempt(
            lead_id,
            call_id,
            EventType.FOLLOWUP_TEXT_SENT,
            lambda: self._whapi.send_text(phone, message),
        )
        resume_sent = await self._attempt(
            lead_id,
            call_id,
            EventType.FOLLOWUP_RESUME_SENT,
            lambda: self._send_resume(phone),
        )
        architecture_sent = await self._attempt(
            lead_id,
            call_id,
            EventType.FOLLOWUP_ARCHITECTURE_SENT,
            lambda: self._send_architecture(phone),
        )
        return FollowupResult(
            success=text_sent and resume_sent and architecture_sent,
            text_sent=text_sent,
            resume_sent=resume_sent,
            architecture_sent=architecture_sent,
        )

    async def _attempt(
        self,
        lead_id: int,
        call_id: int,
        event_type: EventType,
        operation: Callable[[], Awaitable[WhapiResult]],
    ) -> bool:
        reserved = await self._events.reserve_delivery(
            lead_id=lead_id,
            call_id=call_id,
            target_event_type=event_type,
        )
        await self._session.commit()
        if not reserved:
            return True
        try:
            result = await operation()
        except (WhapiProviderError, StorageServiceError):
            await self._events.release_delivery(
                lead_id=lead_id,
                call_id=call_id,
                target_event_type=event_type,
                payload={"error": "followup_component_failed"},
            )
            await self._session.commit()
            return False
        await self._events.complete_delivery(
            lead_id=lead_id,
            call_id=call_id,
            target_event_type=event_type,
            payload={"provider_message_id": result.message_id},
        )
        await self._session.commit()
        return True

    async def _send_resume(self, phone: str) -> WhapiResult:
        url = await self._storage.create_signed_url(self._resume_path)
        return await self._whapi.send_document(
            phone, url, filename="Parv_Agarwal_Resume.pdf"
        )

    async def _send_architecture(self, phone: str) -> WhapiResult:
        url = await self._storage.create_signed_url(self._architecture_path)
        return await self._whapi.send_image(
            phone,
            url,
            caption="Architecture overview of the voice sales agent.",
        )
