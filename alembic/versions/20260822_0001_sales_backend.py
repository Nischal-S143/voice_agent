"""Create the private sales-agent business schema.

Revision ID: 20260822_0001
Revises: None
Create Date: 2026-08-22 00:01:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260822_0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "sales_agent"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS sales_agent")
    op.execute("REVOKE ALL ON SCHEMA sales_agent FROM anon")
    op.execute("REVOKE ALL ON SCHEMA sales_agent FROM authenticated")

    op.create_table(
        "leads",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True)),
        sa.Column("normalized_phone", sa.Text(), nullable=False),
        sa.Column("business_type", sa.Text()),
        sa.Column("products_sold", JSONB()),
        sa.Column("product_count", sa.Integer()),
        sa.Column("required_features", JSONB()),
        sa.Column("budget", sa.Text()),
        sa.Column("timeline", sa.Text()),
        sa.Column("urgency", sa.Text()),
        sa.Column("decision_maker", sa.Text()),
        sa.Column("objections", JSONB()),
        sa.Column("preferred_language", sa.Text()),
        sa.Column("classification", sa.Text()),
        sa.Column("classification_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id", name="pk_leads"),
        sa.UniqueConstraint("normalized_phone", name="uq_leads_normalized_phone"),
        schema=SCHEMA,
    )
    op.create_table(
        "calls",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True)),
        sa.Column("lead_id", sa.BigInteger(), nullable=False),
        sa.Column("sarvam_call_id", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("status", sa.Text()),
        sa.Column("language", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("important_statements", JSONB()),
        sa.Column("transcript", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id", name="pk_calls"),
        sa.ForeignKeyConstraint(["lead_id"], ["sales_agent.leads.id"], name="fk_calls_lead_id_leads"),
        sa.UniqueConstraint("sarvam_call_id", name="uq_calls_sarvam_call_id"),
        sa.CheckConstraint("direction IN ('INITIAL', 'CALLBACK')", name="ck_calls_direction"),
        schema=SCHEMA,
    )
    op.create_table(
        "callbacks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True)),
        sa.Column("lead_id", sa.BigInteger(), nullable=False),
        sa.Column("source_call_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_expression", sa.Text(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_callbacks"),
        sa.ForeignKeyConstraint(["lead_id"], ["sales_agent.leads.id"], name="fk_callbacks_lead_id_leads"),
        sa.ForeignKeyConstraint(["source_call_id"], ["sales_agent.calls.id"], name="fk_callbacks_source_call_id_calls"),
        sa.UniqueConstraint("source_call_id", "scheduled_at", name="uq_callbacks_source_call_scheduled_at"),
        sa.CheckConstraint("status IN ('PENDING', 'TRIGGERED', 'COMPLETED', 'FAILED', 'CANCELLED')", name="ck_callbacks_status"),
        schema=SCHEMA,
    )
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True)),
        sa.Column("lead_id", sa.BigInteger(), nullable=False),
        sa.Column("call_id", sa.BigInteger()),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.ForeignKeyConstraint(["lead_id"], ["sales_agent.leads.id"], name="fk_events_lead_id_leads"),
        sa.ForeignKeyConstraint(["call_id"], ["sales_agent.calls.id"], name="fk_events_call_id_calls", ondelete="SET NULL"),
        sa.CheckConstraint(
            "event_type IN ('HIGH_INTENT_WHATSAPP_RESERVED', 'HIGH_INTENT_WHATSAPP_SENT', "
            "'HIGH_INTENT_WHATSAPP_FAILED', 'CALL_COMPLETED', 'CALLBACK_SCHEDULED', "
            "'CALLBACK_ATTEMPTED', 'CALLBACK_TRIGGERED', 'CALLBACK_FAILED', 'FOLLOWUP_TEXT_SENT', "
            "'FOLLOWUP_TEXT_FAILED', 'FOLLOWUP_RESUME_SENT', 'FOLLOWUP_RESUME_FAILED', "
            "'FOLLOWUP_ARCHITECTURE_SENT', 'FOLLOWUP_ARCHITECTURE_FAILED')",
            name="ck_events_event_type",
        ),
        schema=SCHEMA,
    )

    op.create_index("ix_calls_lead_id", "calls", ["lead_id"], schema=SCHEMA)
    op.create_index("ix_callbacks_lead_id", "callbacks", ["lead_id"], schema=SCHEMA)
    op.create_index("ix_callbacks_source_call_id", "callbacks", ["source_call_id"], schema=SCHEMA)
    op.create_index(
        "ix_callbacks_pending_execution",
        "callbacks",
        ["scheduled_at"],
        unique=False,
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index("ix_events_lead_id", "events", ["lead_id"], schema=SCHEMA)
    op.create_index("ix_events_call_id", "events", ["call_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_events_call_id", table_name="events", schema=SCHEMA)
    op.drop_index("ix_events_lead_id", table_name="events", schema=SCHEMA)
    op.drop_index("ix_callbacks_pending_execution", table_name="callbacks", schema=SCHEMA)
    op.drop_index("ix_callbacks_source_call_id", table_name="callbacks", schema=SCHEMA)
    op.drop_index("ix_callbacks_lead_id", table_name="callbacks", schema=SCHEMA)
    op.drop_index("ix_calls_lead_id", table_name="calls", schema=SCHEMA)
    op.drop_table("events", schema=SCHEMA)
    op.drop_table("callbacks", schema=SCHEMA)
    op.drop_table("calls", schema=SCHEMA)
    op.drop_table("leads", schema=SCHEMA)
    op.execute("DROP SCHEMA sales_agent")
