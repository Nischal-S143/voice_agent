from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Callback, CallbackStatus


class CallbackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def schedule(
        self,
        *,
        lead_id: int,
        source_call_id: int,
        requested_expression: str,
        scheduled_at: datetime,
        timezone: str,
        reason: str | None = None,
    ) -> Callback:
        statement = (
            insert(Callback)
            .values(
                lead_id=lead_id,
                source_call_id=source_call_id,
                requested_expression=requested_expression,
                scheduled_at=scheduled_at,
                timezone=timezone,
                reason=reason,
                status=CallbackStatus.PENDING.value,
            )
            .on_conflict_do_nothing(
                index_elements=[Callback.source_call_id, Callback.scheduled_at]
            )
            .returning(Callback)
        )
        result = await self._session.execute(statement)
        callback = result.scalar_one_or_none()
        if callback is not None:
            return callback
        existing = await self._session.execute(
            sa.select(Callback).where(
                Callback.source_call_id == source_call_id,
                Callback.scheduled_at == scheduled_at,
            )
        )
        return existing.scalar_one()

    async def claim_due(self, *, now: datetime) -> Callback | None:
        execution_at = sa.func.coalesce(Callback.next_attempt_at, Callback.scheduled_at)
        statement = (
            sa.select(Callback)
            .where(
                Callback.status == CallbackStatus.PENDING.value,
                Callback.claimed_at.is_(None),
                execution_at <= now,
            )
            .order_by(execution_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(statement)
        callback = result.scalar_one_or_none()
        if callback is None:
            return None
        callback.claimed_at = now
        callback.attempt_count += 1
        await self._session.flush()
        return callback

    async def mark_failed(
        self,
        callback: Callback,
        *,
        error: str,
        next_attempt_at: datetime | None = None,
    ) -> None:
        callback.status = (
            CallbackStatus.PENDING if next_attempt_at is not None else CallbackStatus.FAILED
        )
        callback.last_error = error
        callback.next_attempt_at = next_attempt_at
        callback.claimed_at = None
        await self._session.flush()

    async def mark_triggered(self, callback: Callback, *, now: datetime) -> None:
        callback.status = CallbackStatus.TRIGGERED
        callback.completed_at = now
        callback.last_error = None
        callback.next_attempt_at = None
        callback.claimed_at = None
        await self._session.flush()
