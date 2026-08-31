from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent, EventType


class AuditEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        lead_id: int,
        event_type: EventType,
        call_id: int | None = None,
        payload: dict[str, object] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            lead_id=lead_id,
            call_id=call_id,
            event_type=event_type,
            payload=payload or {},
        )
        self._session.add(event)
        await self._session.flush()
        return event
