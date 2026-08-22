from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    normalized_phone: Mapped[str] = mapped_column(sa.Text, nullable=False)
    business_type: Mapped[str | None] = mapped_column(sa.Text)
    products_sold: Mapped[list[str] | None] = mapped_column(JSONB)
    product_count: Mapped[int | None] = mapped_column(sa.Integer)
    required_features: Mapped[list[str] | None] = mapped_column(JSONB)
    budget: Mapped[str | None] = mapped_column(sa.Text)
    timeline: Mapped[str | None] = mapped_column(sa.Text)
    urgency: Mapped[str | None] = mapped_column(sa.Text)
    decision_maker: Mapped[str | None] = mapped_column(sa.Text)
    objections: Mapped[list[str] | None] = mapped_column(JSONB)
    preferred_language: Mapped[str | None] = mapped_column(sa.Text)
    classification: Mapped[str | None] = mapped_column(sa.Text)
    classification_reason: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")
    )

    __table_args__ = (sa.UniqueConstraint("normalized_phone", name="uq_leads_normalized_phone"),)
