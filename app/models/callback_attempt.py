from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import in_values
from app.models.base import Base


class CallbackAttemptStatus(StrEnum):
    PLACED = "PLACED"
    FAILED = "FAILED"


class CallbackAttempt(Base):
    """One row per outbound dial the worker made for a callback.

    ``callbacks.attempt_count`` says how many times a callback was tried;
    this table says what happened on each of those tries.
    """

    __tablename__ = "callback_attempts"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    callback_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(
            "sales_agent.callbacks.id",
            name="fk_callback_attempts_callback_id_callbacks",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[CallbackAttemptStatus] = mapped_column(sa.Text, nullable=False)
    call_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(
            "sales_agent.calls.id",
            name="fk_callback_attempts_call_id_calls",
            ondelete="SET NULL",
        ),
    )
    provider_attempt_id: Mapped[str | None] = mapped_column(sa.Text)
    error: Mapped[str | None] = mapped_column(sa.Text)
    retryable: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "callback_id", "attempt_number", name="uq_callback_attempts_callback_id_attempt_number"
        ),
        sa.CheckConstraint(
            in_values("status", CallbackAttemptStatus), name="ck_callback_attempts_status"
        ),
        sa.Index("ix_callback_attempts_callback_id", "callback_id"),
        sa.Index("ix_callback_attempts_call_id", "call_id"),
    )
