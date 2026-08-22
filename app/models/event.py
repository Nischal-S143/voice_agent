from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class EventType(StrEnum):
    HIGH_INTENT_WHATSAPP_RESERVED = "HIGH_INTENT_WHATSAPP_RESERVED"
    HIGH_INTENT_WHATSAPP_REQUESTED = "HIGH_INTENT_WHATSAPP_REQUESTED"
    HIGH_INTENT_WHATSAPP_SENT = "HIGH_INTENT_WHATSAPP_SENT"
    HIGH_INTENT_WHATSAPP_FAILED = "HIGH_INTENT_WHATSAPP_FAILED"
    CALL_COMPLETED = "CALL_COMPLETED"
    CALLBACK_SCHEDULED = "CALLBACK_SCHEDULED"
    CALLBACK_ATTEMPTED = "CALLBACK_ATTEMPTED"
    CALLBACK_TRIGGERED = "CALLBACK_TRIGGERED"
    CALLBACK_FAILED = "CALLBACK_FAILED"
    FOLLOWUP_TEXT_SENT = "FOLLOWUP_TEXT_SENT"
    FOLLOWUP_TEXT_FAILED = "FOLLOWUP_TEXT_FAILED"
    FOLLOWUP_RESUME_SENT = "FOLLOWUP_RESUME_SENT"
    FOLLOWUP_RESUME_FAILED = "FOLLOWUP_RESUME_FAILED"
    FOLLOWUP_ARCHITECTURE_SENT = "FOLLOWUP_ARCHITECTURE_SENT"
    FOLLOWUP_ARCHITECTURE_FAILED = "FOLLOWUP_ARCHITECTURE_FAILED"


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("sales_agent.leads.id", name="fk_events_lead_id_leads"),
        nullable=False,
    )
    call_id: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("sales_agent.calls.id", name="fk_events_call_id_calls", ondelete="SET NULL"),
    )
    event_type: Mapped[EventType] = mapped_column(sa.Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (
        sa.CheckConstraint(
            "event_type IN ('HIGH_INTENT_WHATSAPP_RESERVED', 'HIGH_INTENT_WHATSAPP_REQUESTED', "
            "'HIGH_INTENT_WHATSAPP_SENT', "
            "'HIGH_INTENT_WHATSAPP_FAILED', 'CALL_COMPLETED', 'CALLBACK_SCHEDULED', "
            "'CALLBACK_ATTEMPTED', 'CALLBACK_TRIGGERED', 'CALLBACK_FAILED', 'FOLLOWUP_TEXT_SENT', "
            "'FOLLOWUP_TEXT_FAILED', 'FOLLOWUP_RESUME_SENT', 'FOLLOWUP_RESUME_FAILED', "
            "'FOLLOWUP_ARCHITECTURE_SENT', 'FOLLOWUP_ARCHITECTURE_FAILED')",
            name="ck_events_event_type",
        ),
        sa.Index("ix_events_lead_id", "lead_id"),
        sa.Index("ix_events_call_id", "call_id"),
    )


class DeliveryReservation(Base):
    __tablename__ = "delivery_reservations"

    call_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(
            "sales_agent.calls.id",
            name="fk_delivery_reservations_call_id_calls",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    target_event_type: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        sa.CheckConstraint(
            "target_event_type IN ('HIGH_INTENT_WHATSAPP_SENT', 'FOLLOWUP_TEXT_SENT', "
            "'FOLLOWUP_RESUME_SENT', 'FOLLOWUP_ARCHITECTURE_SENT')",
            name="ck_delivery_reservations_target_event_type",
        ),
    )
