from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DeliveryReservation, Event, EventType


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        lead_id: int,
        event_type: EventType,
        call_id: int | None = None,
        payload: dict[str, object] | None = None,
    ) -> Event:
        event = Event(
            lead_id=lead_id,
            call_id=call_id,
            event_type=event_type,
            payload=payload or {},
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def reserve_delivery(
        self,
        *,
        lead_id: int,
        call_id: int,
        target_event_type: EventType,
    ) -> bool:
        statement = (
            insert(DeliveryReservation)
            .values(call_id=call_id, target_event_type=target_event_type.value)
            .on_conflict_do_nothing(
                index_elements=[
                    DeliveryReservation.call_id,
                    DeliveryReservation.target_event_type,
                ]
            )
            .returning(DeliveryReservation.call_id)
        )
        result = await self._session.execute(statement)
        if result.scalar_one_or_none() is None:
            return False
        await self.append(
            lead_id=lead_id,
            call_id=call_id,
            event_type=_requested_event(target_event_type),
        )
        return True

    async def complete_delivery(
        self,
        *,
        lead_id: int,
        call_id: int,
        target_event_type: EventType,
        payload: dict[str, object] | None = None,
    ) -> bool:
        statement = (
            sa.update(DeliveryReservation)
            .where(
                DeliveryReservation.call_id == call_id,
                DeliveryReservation.target_event_type == target_event_type.value,
                DeliveryReservation.completed_at.is_(None),
            )
            .values(completed_at=sa.func.now())
            .returning(DeliveryReservation.call_id)
        )
        result = await self._session.execute(statement)
        if result.scalar_one_or_none() is None:
            return False
        await self.append(
            lead_id=lead_id,
            call_id=call_id,
            event_type=target_event_type,
            payload=payload,
        )
        return True

    async def release_delivery(
        self,
        *,
        lead_id: int,
        call_id: int,
        target_event_type: EventType,
        payload: dict[str, object] | None = None,
    ) -> bool:
        statement = (
            sa.delete(DeliveryReservation)
            .where(
                DeliveryReservation.call_id == call_id,
                DeliveryReservation.target_event_type == target_event_type.value,
                DeliveryReservation.completed_at.is_(None),
            )
            .returning(DeliveryReservation.call_id)
        )
        result = await self._session.execute(statement)
        if result.scalar_one_or_none() is None:
            return False
        await self.append(
            lead_id=lead_id,
            call_id=call_id,
            event_type=_failed_event(target_event_type),
            payload=payload,
        )
        return True


def _requested_event(target: EventType) -> EventType:
    if target is EventType.HIGH_INTENT_WHATSAPP_SENT:
        return EventType.HIGH_INTENT_WHATSAPP_REQUESTED
    return EventType.HIGH_INTENT_WHATSAPP_RESERVED


def _failed_event(target: EventType) -> EventType:
    mapping = {
        EventType.HIGH_INTENT_WHATSAPP_SENT: EventType.HIGH_INTENT_WHATSAPP_FAILED,
        EventType.FOLLOWUP_TEXT_SENT: EventType.FOLLOWUP_TEXT_FAILED,
        EventType.FOLLOWUP_RESUME_SENT: EventType.FOLLOWUP_RESUME_FAILED,
        EventType.FOLLOWUP_ARCHITECTURE_SENT: EventType.FOLLOWUP_ARCHITECTURE_FAILED,
    }
    return mapping[target]
