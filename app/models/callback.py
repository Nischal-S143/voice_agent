from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CallbackStatus(StrEnum):
    PENDING = "PENDING"
    TRIGGERED = "TRIGGERED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Callback(Base):
    __tablename__ = "callbacks"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("sales_agent.leads.id", name="fk_callbacks_lead_id_leads"),
        nullable=False,
    )
    source_call_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("sales_agent.calls.id", name="fk_callbacks_source_call_id_calls"),
        nullable=False,
    )
    requested_expression: Mapped[str] = mapped_column(sa.Text, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(sa.Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[CallbackStatus] = mapped_column(
        sa.Text, nullable=False, server_default=CallbackStatus.PENDING.value
    )
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        sa.UniqueConstraint(
            "source_call_id", "scheduled_at", name="uq_callbacks_source_call_scheduled_at"
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'TRIGGERED', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_callbacks_status",
        ),
        sa.Index("ix_callbacks_lead_id", "lead_id"),
        sa.Index("ix_callbacks_source_call_id", "source_call_id"),
        sa.Index(
            "ix_callbacks_pending_execution",
            "scheduled_at",
            postgresql_where=sa.text("status = 'PENDING'"),
        ),
    )
