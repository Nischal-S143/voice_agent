"""Add durable delivery reservations.

Revision ID: 20260822_0002
Revises: 20260822_0001
Create Date: 2026-08-22 00:02:00
"""
from alembic import op
import sqlalchemy as sa


revision = "20260822_0002"
down_revision = "20260822_0001"
branch_labels = None
depends_on = None

SCHEMA = "sales_agent"


def upgrade() -> None:
    op.execute("ALTER TABLE sales_agent.events DROP CONSTRAINT ck_events_event_type")
    op.execute(
        "ALTER TABLE sales_agent.events ADD CONSTRAINT ck_events_event_type CHECK "
        "(event_type IN ('HIGH_INTENT_WHATSAPP_RESERVED', "
        "'HIGH_INTENT_WHATSAPP_REQUESTED', 'HIGH_INTENT_WHATSAPP_SENT', "
        "'HIGH_INTENT_WHATSAPP_FAILED', 'CALL_COMPLETED', 'CALLBACK_SCHEDULED', "
        "'CALLBACK_ATTEMPTED', 'CALLBACK_TRIGGERED', 'CALLBACK_FAILED', "
        "'FOLLOWUP_TEXT_SENT', 'FOLLOWUP_TEXT_FAILED', 'FOLLOWUP_RESUME_SENT', "
        "'FOLLOWUP_RESUME_FAILED', 'FOLLOWUP_ARCHITECTURE_SENT', "
        "'FOLLOWUP_ARCHITECTURE_FAILED'))"
    )
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
            "target_event_type IN ('HIGH_INTENT_WHATSAPP_SENT', 'FOLLOWUP_TEXT_SENT', "
            "'FOLLOWUP_RESUME_SENT', 'FOLLOWUP_ARCHITECTURE_SENT')",
            name="ck_delivery_reservations_target_event_type",
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("delivery_reservations", schema=SCHEMA)
    op.execute("ALTER TABLE sales_agent.events DROP CONSTRAINT ck_events_event_type")
    op.execute(
        "ALTER TABLE sales_agent.events ADD CONSTRAINT ck_events_event_type CHECK "
        "(event_type IN ('HIGH_INTENT_WHATSAPP_RESERVED', 'HIGH_INTENT_WHATSAPP_SENT', "
        "'HIGH_INTENT_WHATSAPP_FAILED', 'CALL_COMPLETED', 'CALLBACK_SCHEDULED', "
        "'CALLBACK_ATTEMPTED', 'CALLBACK_TRIGGERED', 'CALLBACK_FAILED', "
        "'FOLLOWUP_TEXT_SENT', 'FOLLOWUP_TEXT_FAILED', 'FOLLOWUP_RESUME_SENT', "
        "'FOLLOWUP_RESUME_FAILED', 'FOLLOWUP_ARCHITECTURE_SENT', "
        "'FOLLOWUP_ARCHITECTURE_FAILED'))"
    )
