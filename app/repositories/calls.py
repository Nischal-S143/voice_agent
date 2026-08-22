from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Call, CallDirection


class CallRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_by_sarvam_call_id(
        self,
        sarvam_call_id: str,
        *,
        lead_id: int,
        direction: CallDirection,
        **values: Any,
    ) -> Call:
        payload = {
            "sarvam_call_id": sarvam_call_id,
            "lead_id": lead_id,
            "direction": direction.value,
            **values,
        }
        statement = insert(Call).values(**payload)
        mutable_keys = {"lead_id", "direction", *values.keys()}
        statement = statement.on_conflict_do_update(
            index_elements=[Call.sarvam_call_id],
            set_={key: getattr(statement.excluded, key) for key in mutable_keys},
        ).returning(Call)
        result = await self._session.execute(statement)
        return result.scalar_one()
