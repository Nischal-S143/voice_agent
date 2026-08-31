from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CallbackAttempt, CallbackAttemptStatus


class CallbackAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        callback_id: int,
        attempt_number: int,
        status: CallbackAttemptStatus,
        call_id: int | None = None,
        provider_attempt_id: str | None = None,
        error: str | None = None,
        retryable: bool = False,
    ) -> CallbackAttempt:
        attempt = CallbackAttempt(
            callback_id=callback_id,
            attempt_number=attempt_number,
            status=status,
            call_id=call_id,
            provider_attempt_id=provider_attempt_id,
            error=error,
            retryable=retryable,
        )
        self._session.add(attempt)
        await self._session.flush()
        return attempt
