from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.audit_event import EventType, in_values
from app.models.base import Base


class MessageKind(StrEnum):
    """The four WhatsApp deliveries the agent owes a lead across one call."""

    HIGH_INTENT = "HIGH_INTENT"
    FOLLOWUP_TEXT = "FOLLOWUP_TEXT"
    FOLLOWUP_RESUME = "FOLLOWUP_RESUME"
    FOLLOWUP_ARCHITECTURE = "FOLLOWUP_ARCHITECTURE"

    @property
    def requested_event(self) -> EventType:
        return EventType[f"{_AUDIT_PREFIX[self]}_REQUESTED"]

    @property
    def sent_event(self) -> EventType:
        return EventType[f"{_AUDIT_PREFIX[self]}_SENT"]

    @property
    def failed_event(self) -> EventType:
        return EventType[f"{_AUDIT_PREFIX[self]}_FAILED"]


_AUDIT_PREFIX = {
    MessageKind.HIGH_INTENT: "HIGH_INTENT_WHATSAPP",
    MessageKind.FOLLOWUP_TEXT: "FOLLOWUP_TEXT",
    MessageKind.FOLLOWUP_RESUME: "FOLLOWUP_RESUME",
    MessageKind.FOLLOWUP_ARCHITECTURE: "FOLLOWUP_ARCHITECTURE",
}


class MessageChannel(StrEnum):
    WHATSAPP = "WHATSAPP"


class MessageStatus(StrEnum):
    RESERVED = "RESERVED"
    SENT = "SENT"
    FAILED = "FAILED"


class Message(Base):
    """One outbound message per (call, kind).

    The unique key is the idempotency boundary: a duplicate tool call loses the
    insert race and never reaches the provider, so a lead cannot be messaged
    twice for the same call.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("sales_agent.leads.id", name="fk_messages_lead_id_leads"),
        nullable=False,
    )
    call_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey(
            "sales_agent.calls.id", name="fk_messages_call_id_calls", ondelete="CASCADE"
        ),
        nullable=False,
    )
    kind: Mapped[MessageKind] = mapped_column(sa.Text, nullable=False)
    channel: Mapped[MessageChannel] = mapped_column(
        sa.Text, nullable=False, server_default=MessageChannel.WHATSAPP.value
    )
    status: Mapped[MessageStatus] = mapped_column(
        sa.Text, nullable=False, server_default=MessageStatus.RESERVED.value
    )
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    provider_message_id: Mapped[str | None] = mapped_column(sa.Text)
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    __table_args__ = (
        sa.UniqueConstraint("call_id", "kind", name="uq_messages_call_id_kind"),
        sa.CheckConstraint(in_values("kind", MessageKind), name="ck_messages_kind"),
        sa.CheckConstraint(in_values("channel", MessageChannel), name="ck_messages_channel"),
        sa.CheckConstraint(in_values("status", MessageStatus), name="ck_messages_status"),
        sa.Index("ix_messages_lead_id", "lead_id"),
        sa.Index("ix_messages_call_id", "call_id"),
    )
