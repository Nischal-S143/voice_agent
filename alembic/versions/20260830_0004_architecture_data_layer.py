"""Align the data layer with the published architecture.

Renames ``events`` to ``audit_events``, adds ``callback_attempts`` and
``messages``, links a call to the callback that placed it, and replaces the
callback ``TRIGGERED`` state with ``IN_PROGRESS``.

``messages`` absorbs ``delivery_reservations``: its ``(call_id, kind)`` unique
key is the same atomic idempotency boundary, and the row now also records what
was actually sent.

Legacy ``HIGH_INTENT_WHATSAPP_RESERVED`` audit rows become
``HIGH_INTENT_WHATSAPP_REQUESTED``. The old value was reused for every delivery
kind and never recorded which, so that detail is not recoverable from those
historical rows.

Revision ID: 20260830_0004
Revises: 20260822_0003
Create Date: 2026-08-30 00:04:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260830_0004"
down_revision = "20260822_0003"
branch_labels = None
depends_on = None

SCHEMA = "sales_agent"

EVENT_TYPES = (
    "HIGH_INTENT_WHATSAPP_REQUESTED",
    "HIGH_INTENT_WHATSAPP_SENT",
    "HIGH_INTENT_WHATSAPP_FAILED",
    "FOLLOWUP_TEXT_REQUESTED",
    "FOLLOWUP_TEXT_SENT",
    "FOLLOWUP_TEXT_FAILED",
    "FOLLOWUP_RESUME_REQUESTED",
    "FOLLOWUP_RESUME_SENT",
    "FOLLOWUP_RESUME_FAILED",
    "FOLLOWUP_ARCHITECTURE_REQUESTED",
    "FOLLOWUP_ARCHITECTURE_SENT",
    "FOLLOWUP_ARCHITECTURE_FAILED",
    "CALL_COMPLETED",
    "CALLBACK_SCHEDULED",
    "CALLBACK_ATTEMPTED",
    "CALLBACK_TRIGGERED",
    "CALLBACK_COMPLETED",
    "CALLBACK_FAILED",
)

LEGACY_EVENT_TYPES = (
    "HIGH_INTENT_WHATSAPP_RESERVED",
    "HIGH_INTENT_WHATSAPP_REQUESTED",
    "HIGH_INTENT_WHATSAPP_SENT",
    "HIGH_INTENT_WHATSAPP_FAILED",
    "CALL_COMPLETED",
    "CALLBACK_SCHEDULED",
    "CALLBACK_ATTEMPTED",
    "CALLBACK_TRIGGERED",
    "CALLBACK_FAILED",
    "FOLLOWUP_TEXT_SENT",
    "FOLLOWUP_TEXT_FAILED",
    "FOLLOWUP_RESUME_SENT",
    "FOLLOWUP_RESUME_FAILED",
    "FOLLOWUP_ARCHITECTURE_SENT",
    "FOLLOWUP_ARCHITECTURE_FAILED",
)

CALLBACK_STATUSES = ("PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "CANCELLED")
LEGACY_CALLBACK_STATUSES = ("PENDING", "TRIGGERED", "COMPLETED", "FAILED", "CANCELLED")

MESSAGE_KINDS = (
    "HIGH_INTENT",
    "FOLLOWUP_TEXT",
    "FOLLOWUP_RESUME",
    "FOLLOWUP_ARCHITECTURE",
)
MESSAGE_STATUSES = ("RESERVED", "SENT", "FAILED")
MESSAGE_CHANNELS = ("WHATSAPP",)
CALLBACK_ATTEMPT_STATUSES = ("PLACED", "FAILED")

# delivery_reservations recorded the audit event it was reserving; messages
# record the message kind that event belongs to.
RESERVATION_KIND = {
    "HIGH_INTENT_WHATSAPP_SENT": "HIGH_INTENT",
    "FOLLOWUP_TEXT_SENT": "FOLLOWUP_TEXT",
    "FOLLOWUP_RESUME_SENT": "FOLLOWUP_RESUME",
    "FOLLOWUP_ARCHITECTURE_SENT": "FOLLOWUP_ARCHITECTURE",
}


def _in(column: str, values: tuple[str, ...]) -> str:
    rendered = ", ".join("'" + value + "'" for value in values)
    return column + " IN (" + rendered + ")"


def _case(column: str, mapping: dict[str, str]) -> str:
    branches = " ".join(
        "WHEN '" + value + "' THEN '" + mapped + "'" for value, mapped in mapping.items()
    )
    return "CASE " + column + " " + branches + " END"


def upgrade() -> None:
    _rename_events_to_audit_events()
    _add_callback_link_to_calls()
    _replace_triggered_with_in_progress()
    _create_callback_attempts()
    _create_messages_from_delivery_reservations()

    for table in ("callback_attempts", "messages"):
        op.execute("ALTER TABLE sales_agent." + table + " ENABLE ROW LEVEL SECURITY")


def _rename_events_to_audit_events() -> None:
    op.execute("ALTER TABLE sales_agent.events RENAME TO audit_events")
    for old, new in (
        ("pk_events", "pk_audit_events"),
        ("fk_events_lead_id_leads", "fk_audit_events_lead_id_leads"),
        ("fk_events_call_id_calls", "fk_audit_events_call_id_calls"),
        ("ck_events_event_type", "ck_audit_events_event_type"),
    ):
        op.execute(
            "ALTER TABLE sales_agent.audit_events RENAME CONSTRAINT "
            + old
            + " TO "
            + new
        )
    for old, new in (
        ("ix_events_lead_id", "ix_audit_events_lead_id"),
        ("ix_events_call_id", "ix_audit_events_call_id"),
    ):
        op.execute("ALTER INDEX sales_agent." + old + " RENAME TO " + new)

    op.execute(
        "ALTER TABLE sales_agent.audit_events DROP CONSTRAINT ck_audit_events_event_type"
    )
    op.execute(
        "UPDATE sales_agent.audit_events "
        "SET event_type = 'HIGH_INTENT_WHATSAPP_REQUESTED' "
        "WHERE event_type = 'HIGH_INTENT_WHATSAPP_RESERVED'"
    )
    op.execute(
        "ALTER TABLE sales_agent.audit_events ADD CONSTRAINT "
        "ck_audit_events_event_type CHECK (" + _in("event_type", EVENT_TYPES) + ")"
    )


def _add_callback_link_to_calls() -> None:
    op.add_column("calls", sa.Column("callback_id", sa.BigInteger()), schema=SCHEMA)
    op.create_foreign_key(
        "fk_calls_callback_id_callbacks",
        "calls",
        "callbacks",
        ["callback_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
    )
    op.create_index("ix_calls_callback_id", "calls", ["callback_id"], schema=SCHEMA)


def _replace_triggered_with_in_progress() -> None:
    op.execute("ALTER TABLE sales_agent.callbacks DROP CONSTRAINT ck_callbacks_status")
    op.execute(
        "UPDATE sales_agent.callbacks SET status = 'IN_PROGRESS' "
        "WHERE status = 'TRIGGERED'"
    )
    op.execute(
        "ALTER TABLE sales_agent.callbacks ADD CONSTRAINT ck_callbacks_status "
        "CHECK (" + _in("status", CALLBACK_STATUSES) + ")"
    )


def _create_callback_attempts() -> None:
    op.create_table(
        "callback_attempts",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True)),
        sa.Column("callback_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("call_id", sa.BigInteger()),
        sa.Column("provider_attempt_id", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "retryable", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_callback_attempts"),
        sa.ForeignKeyConstraint(
            ["callback_id"],
            ["sales_agent.callbacks.id"],
            name="fk_callback_attempts_callback_id_callbacks",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["sales_agent.calls.id"],
            name="fk_callback_attempts_call_id_calls",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "callback_id",
            "attempt_number",
            name="uq_callback_attempts_callback_id_attempt_number",
        ),
        sa.CheckConstraint(
            _in("status", CALLBACK_ATTEMPT_STATUSES), name="ck_callback_attempts_status"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_callback_attempts_callback_id",
        "callback_attempts",
        ["callback_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_callback_attempts_call_id", "callback_attempts", ["call_id"], schema=SCHEMA
    )


def _create_messages_from_delivery_reservations() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True)),
        sa.Column("lead_id", sa.BigInteger(), nullable=False),
        sa.Column("call_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False, server_default="WHATSAPP"),
        sa.Column("status", sa.Text(), nullable=False, server_default="RESERVED"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("provider_message_id", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["sales_agent.leads.id"], name="fk_messages_lead_id_leads"
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["sales_agent.calls.id"],
            name="fk_messages_call_id_calls",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("call_id", "kind", name="uq_messages_call_id_kind"),
        sa.CheckConstraint(_in("kind", MESSAGE_KINDS), name="ck_messages_kind"),
        sa.CheckConstraint(
            _in("channel", MESSAGE_CHANNELS), name="ck_messages_channel"
        ),
        sa.CheckConstraint(_in("status", MESSAGE_STATUSES), name="ck_messages_status"),
        schema=SCHEMA,
    )
    op.create_index("ix_messages_lead_id", "messages", ["lead_id"], schema=SCHEMA)
    op.create_index("ix_messages_call_id", "messages", ["call_id"], schema=SCHEMA)

    op.execute(
        "INSERT INTO sales_agent.messages "
        "(lead_id, call_id, kind, channel, status, created_at, sent_at) "
        "SELECT calls.lead_id, reservations.call_id, "
        + _case("reservations.target_event_type", RESERVATION_KIND)
        + ", 'WHATSAPP', "
        "CASE WHEN reservations.completed_at IS NULL THEN 'RESERVED' ELSE 'SENT' END, "
        "reservations.created_at, reservations.completed_at "
        "FROM sales_agent.delivery_reservations AS reservations "
        "JOIN sales_agent.calls AS calls ON calls.id = reservations.call_id"
    )
    op.drop_table("delivery_reservations", schema=SCHEMA)


def downgrade() -> None:
    op.create_table(
        "delivery_reservations",
        sa.Column("call_id", sa.BigInteger(), nullable=False),
        sa.Column("target_event_type", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint(
            "call_id", "target_event_type", name="pk_delivery_reservations"
        ),
        sa.ForeignKeyConstraint(
            ["call_id"],
            ["sales_agent.calls.id"],
            name="fk_delivery_reservations_call_id_calls",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            _in("target_event_type", tuple(RESERVATION_KIND)),
            name="ck_delivery_reservations_target_event_type",
        ),
        schema=SCHEMA,
    )
    reverse_kind = {kind: event for event, kind in RESERVATION_KIND.items()}
    op.execute(
        "INSERT INTO sales_agent.delivery_reservations "
        "(call_id, target_event_type, completed_at, created_at) "
        "SELECT call_id, "
        + _case("kind", reverse_kind)
        + ", sent_at, created_at "
        "FROM sales_agent.messages WHERE status <> 'FAILED'"
    )
    op.drop_table("messages", schema=SCHEMA)
    op.drop_table("callback_attempts", schema=SCHEMA)

    op.execute("ALTER TABLE sales_agent.callbacks DROP CONSTRAINT ck_callbacks_status")
    op.execute(
        "UPDATE sales_agent.callbacks SET status = 'TRIGGERED' "
        "WHERE status = 'IN_PROGRESS'"
    )
    op.execute(
        "ALTER TABLE sales_agent.callbacks ADD CONSTRAINT ck_callbacks_status "
        "CHECK (" + _in("status", LEGACY_CALLBACK_STATUSES) + ")"
    )

    op.drop_index("ix_calls_callback_id", table_name="calls", schema=SCHEMA)
    op.drop_constraint(
        "fk_calls_callback_id_callbacks", "calls", schema=SCHEMA, type_="foreignkey"
    )
    op.drop_column("calls", "callback_id", schema=SCHEMA)

    op.execute(
        "ALTER TABLE sales_agent.audit_events DROP CONSTRAINT ck_audit_events_event_type"
    )
    op.execute(
        "UPDATE sales_agent.audit_events "
        "SET event_type = 'HIGH_INTENT_WHATSAPP_RESERVED' "
        "WHERE event_type IN ('FOLLOWUP_TEXT_REQUESTED', 'FOLLOWUP_RESUME_REQUESTED', "
        "'FOLLOWUP_ARCHITECTURE_REQUESTED', 'CALLBACK_COMPLETED')"
    )
    op.execute(
        "ALTER TABLE sales_agent.audit_events ADD CONSTRAINT "
        "ck_audit_events_event_type CHECK ("
        + _in("event_type", LEGACY_EVENT_TYPES)
        + ")"
    )
    for new, old in (
        ("ix_audit_events_lead_id", "ix_events_lead_id"),
        ("ix_audit_events_call_id", "ix_events_call_id"),
    ):
        op.execute("ALTER INDEX sales_agent." + new + " RENAME TO " + old)
    for new, old in (
        ("pk_audit_events", "pk_events"),
        ("fk_audit_events_lead_id_leads", "fk_events_lead_id_leads"),
        ("fk_audit_events_call_id_calls", "fk_events_call_id_calls"),
        ("ck_audit_events_event_type", "ck_events_event_type"),
    ):
        op.execute(
            "ALTER TABLE sales_agent.audit_events RENAME CONSTRAINT "
            + new
            + " TO "
            + old
        )
    op.execute("ALTER TABLE sales_agent.audit_events RENAME TO events")
