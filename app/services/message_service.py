from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from app.models import MessageKind
from app.services.storage_service import StorageServiceError
from app.services.whapi_service import WhapiProviderError, WhapiResult


class DeliveryOutcome(BaseModel):
    sent: bool
    already_sent: bool = False
    provider_message_id: str | None = None
    error: str | None = None


class MessageService:
    """Sends one WhatsApp message per (call, kind), exactly once.

    The messages row is reserved and committed before the provider is called,
    so a duplicate tool call for the same call_id finds the row taken and
    returns without sending. A provider failure marks the row FAILED, which is
    the only state a later retry can re-claim.
    """

    def __init__(
        self,
        messages: Any,
        events: Any,
        session: Any,
    ) -> None:
        self._messages = messages
        self._events = events
        self._session = session

    async def deliver(
        self,
        *,
        lead_id: int,
        call_id: int,
        kind: MessageKind,
        send: Callable[[], Awaitable[WhapiResult]],
    ) -> DeliveryOutcome:
        message = await self._messages.reserve(
            lead_id=lead_id, call_id=call_id, kind=kind
        )
        if message is None:
            await self._session.commit()
            return DeliveryOutcome(sent=True, already_sent=True)
        await self._events.append(
            lead_id=lead_id, call_id=call_id, event_type=kind.requested_event
        )
        await self._session.commit()

        try:
            result = await send()
        except (WhapiProviderError, StorageServiceError, ValueError) as error:
            reason = _reason(error)
            await self._messages.mark_failed(message, error=reason)
            await self._events.append(
                lead_id=lead_id,
                call_id=call_id,
                event_type=kind.failed_event,
                payload={"error": reason},
            )
            await self._session.commit()
            return DeliveryOutcome(sent=False, error=reason)

        await self._messages.mark_sent(
            message, provider_message_id=result.message_id, now=datetime.now(UTC)
        )
        await self._events.append(
            lead_id=lead_id,
            call_id=call_id,
            event_type=kind.sent_event,
            payload={"provider_message_id": result.message_id},
        )
        await self._session.commit()
        return DeliveryOutcome(sent=True, provider_message_id=result.message_id)


def _reason(error: Exception) -> str:
    if isinstance(error, StorageServiceError):
        return "asset_url_failed"
    if isinstance(error, WhapiProviderError):
        return "whapi_send_failed"
    return "invalid_phone"
