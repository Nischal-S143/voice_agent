from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import in_values
from app.models.base import Base


class CallDirection(StrEnum):
    INITIAL = "INITIAL"
    CALLBACK = "CALLBACK"


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("sales_agent.leads.id", name="fk_calls_lead_id_leads"),
        nullable=False,
    )
    callback_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        # use_alter breaks the calls <-> callbacks cycle for schema sorting; the
        # column is only set once the callback that spawned this call exists.
        sa.ForeignKey(
            "sales_agent.callbacks.id",
            name="fk_calls_callback_id_callbacks",
            ondelete="SET NULL",
            use_alter=True,
        ),
    )
    sarvam_call_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    direction: Mapped[CallDirection] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str | None] = mapped_column(sa.Text)
    language: Mapped[str | None] = mapped_column(sa.Text)
    summary: Mapped[str | None] = mapped_column(sa.Text)
    important_statements: Mapped[list[str] | None] = mapped_column(JSONB)
    transcript: Mapped[str | None] = mapped_column(sa.Text)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        sa.UniqueConstraint("sarvam_call_id", name="uq_calls_sarvam_call_id"),
        sa.CheckConstraint(
            in_values("direction", CallDirection), name="ck_calls_direction"
        ),
        sa.Index("ix_calls_lead_id", "lead_id"),
        sa.Index("ix_calls_callback_id", "callback_id"),
    )
