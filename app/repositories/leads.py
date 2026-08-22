from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Lead


class LeadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_by_phone(self, normalized_phone: str, **values: Any) -> Lead:
        payload = {"normalized_phone": normalized_phone, **values}
        statement = insert(Lead).values(**payload)
        update_values = {key: getattr(statement.excluded, key) for key in values}
        update_values["updated_at"] = sa.func.now()
        statement = statement.on_conflict_do_update(
            index_elements=[Lead.normalized_phone],
            set_=update_values,
        ).returning(Lead)
        result = await self._session.execute(statement)
        return result.scalar_one()
