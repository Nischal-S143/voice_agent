"""Secure the private schema and create the private asset bucket.

Revision ID: 20260822_0003
Revises: 20260822_0002
Create Date: 2026-08-22 00:03:00
"""
from __future__ import annotations

from alembic import op


revision = "20260822_0003"
down_revision = "20260822_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("leads", "calls", "callbacks", "events", "delivery_reservations"):
        op.execute(f"ALTER TABLE sales_agent.{table} ENABLE ROW LEVEL SECURITY")

    op.execute(
        "INSERT INTO storage.buckets (id, name, public) "
        "VALUES ('sales-agent-assets', 'sales-agent-assets', false) "
        "ON CONFLICT (id) DO UPDATE SET public = false"
    )


def downgrade() -> None:
    # Bucket contents are deliberately preserved during downgrade.
    for table in ("delivery_reservations", "events", "callbacks", "calls", "leads"):
        op.execute(f"ALTER TABLE sales_agent.{table} DISABLE ROW LEVEL SECURITY")
