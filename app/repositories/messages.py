from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, MessageChannel, MessageKind, MessageStatus


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        lead_id: int,
        call_id: int,
        kind: MessageKind,
        channel: MessageChannel = MessageChannel.WHATSAPP,
    ) -> Message | None:
        """Claim the right to send this message, or return None if it is taken.

        PostgreSQL settles the race on ``uq_messages_call_id_kind``. The
        conditional DO UPDATE re-claims a previously FAILED row so a retry is
        possible, while a RESERVED (in flight) or SENT row matches no rows,
        returns nothing, and leaves the caller a non-owner.
        """
        statement = (
            insert(Message)
            .values(
                lead_id=lead_id,
                call_id=call_id,
                kind=kind.value,
                channel=channel.value,
                status=MessageStatus.RESERVED.value,
                attempt_count=1,
            )
            .on_conflict_do_update(
                index_elements=[Message.call_id, Message.kind],
                set_={
                    "status": MessageStatus.RESERVED.value,
                    "attempt_count": Message.attempt_count + 1,
                    "last_error": None,
                },
                where=Message.status == MessageStatus.FAILED.value,
            )
            .returning(Message)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def mark_sent(
        self, message: Message, *, provider_message_id: str, now: datetime
    ) -> None:
        message.status = MessageStatus.SENT
        message.provider_message_id = provider_message_id
        message.last_error = None
        message.sent_at = now
        await self._session.flush()

    async def mark_failed(self, message: Message, *, error: str) -> None:
        message.status = MessageStatus.FAILED
        message.last_error = error
        await self._session.flush()
